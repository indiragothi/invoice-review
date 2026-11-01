"""Reading cache keyed by the SHA-256 of the file.

Reading is the slow, deterministic part (OCR takes seconds); the same bytes always give the same
words. Delete the cache folder after changing the reader, or old words would be reused.
"""

import hashlib
from pathlib import Path

from app.reader.schemas import ReadDocument


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ReadingCache:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, sha256: str) -> Path:
        return self.directory / f"{sha256}.json"

    def get(self, sha256: str) -> ReadDocument | None:
        path = self._path(sha256)
        if not path.exists():
            return None
        try:
            return ReadDocument.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError:
            return None  # a damaged or outdated entry is just a miss

    def put(self, sha256: str, document: ReadDocument) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self._path(sha256).write_text(document.model_dump_json(), encoding="utf-8")
