"""Local image store for inspected frames.

Images live under IMAGE_DIR (git-ignored `data/` by default). The database keeps only a
relative key, so the store can later move to object storage without a schema change.
"""

import os
import uuid
from pathlib import Path

IMAGE_DIR = os.getenv("IMAGE_DIR", "data/images")


class ImageStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def save(self, lot_code: str, data: bytes, ext: str) -> str:
        """Write image bytes and return the storage key, e.g. 'S01/3f2a....jpg'.

        The filename is a random UUID so a key exists before the inspection row does,
        and two frames can never overwrite each other.
        """
        directory = self.root / lot_code
        directory.mkdir(parents=True, exist_ok=True)
        key = f"{lot_code}/{uuid.uuid4().hex}{ext}"
        (self.root / key).write_bytes(data)
        return key

    def path(self, key: str) -> Path:
        """Resolve a key to a file path, refusing anything outside the store root."""
        candidate = (self.root / key).resolve()
        if not candidate.is_relative_to(self.root):
            raise ValueError(f"key escapes image store: {key!r}")
        return candidate
