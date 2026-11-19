"""End-to-end smoke test against a running server: inspect -> review -> act.

Usage: python /tmp/smoke.py [base_url]
"""

import sys
import uuid

import cv2
import httpx
import numpy as np

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
LOT = f"SMOKE-{uuid.uuid4().hex[:6]}"


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f"  ({detail})" if detail else ""))
    if not ok:
        sys.exit(1)


def main() -> None:
    c = httpx.Client(base_url=BASE, timeout=10)
    check("health", c.get("/health").json().get("db") == "ok", BASE)

    _, jpg = cv2.imencode(".jpg", np.full((480, 640, 3), 90, np.uint8))
    ng_defect, verdicts = None, []
    for i in range(40):
        r = c.post("/inspections", files={"file": (f"{i:04d}.jpg", jpg.tobytes(), "image/jpeg")},
                   data={"lot_code": LOT, "source": "replay"})
        if r.status_code != 201:
            check(f"inspection {i}", False, r.text[:120])
        body = r.json()
        verdicts.append(body["verdict"])
        if body["verdict"] == "NG" and ng_defect is None:
            ng_defect = body["defects"][0]["id"]
    counts = {v: verdicts.count(v) for v in ("OK", "NG", "REVIEW")}
    check("40 inspections stored", len(verdicts) == 40, str(counts))
    check("at least one NG", ng_defect is not None)

    tasks = [t for t in c.get("/review-tasks", params={"limit": 200}).json() if t["inspection"]["lot_code"] == LOT]
    check("review queue filled", len(tasks) > 0, f"{len(tasks)} pending for {LOT}")
    check("timestamps are UTC", tasks[0]["created_at"].endswith("Z"), tasks[0]["created_at"])
    tid = tasks[0]["id"]
    r = c.post(f"/review-tasks/{tid}/decision", json={"decision": "confirm", "reviewer": "smoke"})
    check("review decision", r.status_code == 200 and r.json()["status"] == "done")
    r = c.post(f"/review-tasks/{tid}/decision", json={"decision": "reject", "reviewer": "smoke"})
    check("second decision rejected", r.status_code == 409, str(r.status_code))

    r = c.post("/actions", json={"lot_code": LOT, "action_type": "hold_lot", "owner": "smoke", "defect_id": ng_defect})
    check("hold lot", r.status_code == 201 and r.json()["lot_status"] == "on_hold", r.text[:120])
    hold = r.json()["id"]
    check("hold twice rejected", c.post("/actions", json={"lot_code": LOT, "action_type": "hold_lot",
                                                           "owner": "smoke"}).status_code == 409)
    c.post(f"/actions/{hold}/status", json={"status": "in_progress", "actor": "smoke"})
    done = c.post(f"/actions/{hold}/status", json={"status": "done", "actor": "smoke"}).json()
    check("hold action done", done["status"] == "done", f"detection_to_done_s={done['detection_to_done_s']}")

    rel = c.post("/actions", json={"lot_code": LOT, "action_type": "release_lot", "owner": "smoke"}).json()["id"]
    c.post(f"/actions/{rel}/status", json={"status": "in_progress", "actor": "smoke"})
    released = c.post(f"/actions/{rel}/status", json={"status": "done", "actor": "smoke"}).json()
    check("lot released", released["lot_status"] == "released")

    img = c.get(f"/review-tasks", params={"status": "done", "limit": 200}).json()
    check("image served", c.get(img[-1]["inspection"]["image_url"]).status_code == 200)
    print(f"\nALL PASSED  lot={LOT}  verdicts={counts}")


if __name__ == "__main__":
    main()
