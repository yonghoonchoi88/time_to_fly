import json

import cv2
import numpy as np
import pytest

from tools.line_replay import Frame, iter_frames, main, paced


def write_image(path, value: int = 128) -> None:
    """Write a small synthetic image (no real data is used in tests)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    assert cv2.imwrite(str(path), np.full((16, 16, 3), value, dtype=np.uint8))


@pytest.fixture
def replay_root(tmp_path):
    root = tmp_path / "replay"
    # Created out of order on purpose; iteration must still be sorted.
    write_image(root / "S02" / "0001.png")
    write_image(root / "S01" / "0002.jpg")
    write_image(root / "S01" / "0001.jpg")
    write_image(root / "S01" / "0003.JPEG")
    (root / "S01" / "0001.jpg:Zone.Identifier").write_text("[ZoneTransfer]")
    (root / "S01" / "notes.txt").write_text("not an image")
    (root / "loose.jpg").write_bytes(b"")  # files directly under root are not a Lot
    return root


class FakeClock:
    """Deterministic clock: time only advances when sleep() is called."""

    def __init__(self, work_s: float = 0.0):
        self.now = 100.0
        self.work_s = work_s  # simulated processing time per clock read
        self.sleeps: list[float] = []

    def clock(self) -> float:
        self.now += self.work_s
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_lots_and_files_are_sorted_by_name(replay_root):
    names = [(f.lot_code, f.path.name) for f in iter_frames(replay_root)]
    assert names == [
        ("S01", "0001.jpg"),
        ("S01", "0002.jpg"),
        ("S01", "0003.JPEG"),
        ("S02", "0001.png"),
    ]


def test_non_image_files_are_skipped(replay_root):
    suffixes = {f.path.suffix.lower() for f in iter_frames(replay_root)}
    assert suffixes <= {".jpg", ".jpeg", ".png"}
    assert all("Zone.Identifier" not in f.path.name for f in iter_frames(replay_root))


def test_lot_code_matches_subfolder_name(replay_root):
    for f in iter_frames(replay_root):
        assert f.lot_code == f.path.parent.name


def test_paced_schedule_with_fake_clock(tmp_path):
    fake = FakeClock()
    frames = [Frame("S01", tmp_path / f"{i:04d}.jpg") for i in range(10)]

    out = list(paced(frames, fps=5, clock=fake.clock, sleep=fake.sleep))

    assert [pf.index for pf in out] == list(range(10))
    assert [pf.scheduled_s for pf in out] == pytest.approx([i * 0.2 for i in range(10)])
    assert [pf.sent_s for pf in out] == pytest.approx([i * 0.2 for i in range(10)])


def test_paced_does_not_drift_with_processing_time(tmp_path):
    # Each clock read costs 10 ms; a naive sleep(1/fps) loop would fall behind.
    fake = FakeClock(work_s=0.01)
    frames = [Frame("S01", tmp_path / f"{i:04d}.jpg") for i in range(10)]

    out = list(paced(frames, fps=5, clock=fake.clock, sleep=fake.sleep))

    for pf in out:
        assert pf.sent_s - pf.scheduled_s < 0.05


def test_paced_rejects_non_positive_fps():
    with pytest.raises(ValueError):
        list(paced([], fps=0))


@pytest.mark.parametrize("fps", ["0", "-1"])
def test_cli_rejects_non_positive_fps(replay_root, fps):
    with pytest.raises(SystemExit) as exc:
        main(["--source", str(replay_root), "--fps", fps, "--dry-run"])
    assert exc.value.code != 0


def test_cli_dry_run_prints_json_lines_and_summary(replay_root, capsys):
    assert main(["--source", str(replay_root), "--fps", "200", "--dry-run"]) == 0

    captured = capsys.readouterr()
    rows = [json.loads(line) for line in captured.out.splitlines()]
    assert [r["frame"] for r in rows] == [0, 1, 2, 3]
    assert [r["lot_code"] for r in rows] == ["S01", "S01", "S01", "S02"]
    assert set(rows[0]) == {"lot_code", "path", "frame", "scheduled_s", "sent_s"}
    assert "frames=4" in captured.err
    assert "actual_fps=" in captured.err
    