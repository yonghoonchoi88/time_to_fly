"""Line replay: stream images from a folder as if they came off a production line.

Each subfolder of ``--source`` is one Lot; its name becomes ``lot_code``.
Frames are emitted in a deterministic order (Lot name, then file name) at a
fixed rate so throughput and latency measurements are reproducible.

Usage:
    python -m tools.line_replay --source data/replay --fps 2 --dry-run
    python -m tools.line_replay --source data/replay --fps 5 --api http://localhost:8000 --loop
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


@dataclass(frozen=True)
class Frame:
    """One image to replay, tagged with the Lot it belongs to."""

    lot_code: str
    path: Path


@dataclass(frozen=True)
class PacedFrame:
    """A frame together with its schedule.

    ``scheduled_s`` is when the frame should go out and ``sent_s`` is when it
    was actually released, both in seconds since the replay started.
    """

    index: int
    frame: Frame
    scheduled_s: float
    sent_s: float


def iter_frames(root: Path) -> Iterator[Frame]:
    """Yield image frames under ``root``, one Lot per immediate subfolder.

    Order is Lot folder name, then file name, so every run sees the same
    sequence. Only .jpg/.jpeg/.png files are returned (case-insensitive);
    anything else, such as ``*:Zone.Identifier`` files, is skipped.
    """
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(f"source folder not found: {root}")
    for lot_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for path in sorted(p for p in lot_dir.iterdir() if p.is_file()):
            if path.suffix.lower() in IMAGE_SUFFIXES:
                yield Frame(lot_code=lot_dir.name, path=path)


def paced(
    frames: Iterable[Frame],
    fps: float,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Iterator[PacedFrame]:
    """Release frames at ``fps`` frames per second.

    Frame ``i`` is scheduled at ``start + i / fps`` and we wait only until
    that moment. Sleeping a fixed ``1 / fps`` per frame would accumulate the
    processing time of every frame and drift behind schedule.
    """
    if fps <= 0:
        raise ValueError(f"fps must be positive, got {fps}")
    start = clock()
    for i, frame in enumerate(frames):
        scheduled = i / fps
        delay = start + scheduled - clock()
        if delay > 0:
            sleep(delay)
        yield PacedFrame(index=i, frame=frame, scheduled_s=scheduled, sent_s=clock() - start)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.line_replay",
        description="Replay images from a folder to the inspection API at a fixed rate.",
    )
    parser.add_argument("--source", required=True, type=Path,
                        help="root folder; each subfolder name is used as lot_code")
    parser.add_argument("--fps", type=float, default=2.0, help="frames per second (default: 2.0)")
    parser.add_argument("--api", default="http://localhost:8000",
                        help="inspection API base URL (unused with --dry-run)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print one JSON line per frame instead of sending")
    parser.add_argument("--loop", action="store_true",
                        help="start over after the last frame (stop with Ctrl+C)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.fps <= 0:
        parser.error(f"--fps must be greater than 0 (got {args.fps})")
    if not args.source.is_dir():
        parser.error(f"--source is not a folder: {args.source}")
    if not args.dry_run:
        # Sending to POST /inspections is wired up in a follow-up PR.
        parser.error("sending to the API is not implemented yet; use --dry-run")

    frames_list = list(iter_frames(args.source))
    if not frames_list:
        parser.error(f"no .jpg/.jpeg/.png images found under {args.source}/<lot>/")
    frames = itertools.cycle(frames_list) if args.loop else iter(frames_list)

    sent = 0
    last_sent_s = 0.0
    try:
        for pf in paced(frames, args.fps):
            last_sent_s = pf.sent_s
            print(json.dumps({
                "lot_code": pf.frame.lot_code,
                "path": pf.frame.path.as_posix(),
                "frame": pf.index,
                "scheduled_s": round(pf.scheduled_s, 3),
                "sent_s": round(pf.sent_s, 3),
            }), flush=True)
            sent += 1
    except KeyboardInterrupt:
        pass
    # N frames span N - 1 intervals: frame 0 goes out at t=0, frame N-1 at
    # t=last_sent_s. Dividing N by that span would overstate the rate.
    actual_fps = (sent - 1) / last_sent_s if sent > 1 and last_sent_s > 0 else 0.0
    print(f"summary: frames={sent} elapsed_s={last_sent_s:.3f} target_fps={args.fps:g} "
          f"actual_fps={actual_fps:.2f}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
    