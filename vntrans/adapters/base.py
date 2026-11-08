from __future__ import annotations

from pathlib import Path


class Adapter:
    name = "base"
    description = ""

    def __init__(self, opts: dict | None = None):
        self.opts = opts or {}

    def match(self, path: Path, root: Path) -> bool:  # pragma: no cover
        raise NotImplementedError

    def extract(self, path: Path) -> list[tuple[object, str, str]]:  # pragma: no cover
        raise NotImplementedError

    def apply(self, path: Path, out_path: Path, items: list[tuple[object, str]]) -> None:  # pragma: no cover
        raise NotImplementedError


def read_text(path: Path) -> tuple[str, str]:
    """Đọc file văn bản, trả về (nội dung, encoding) — giữ BOM nếu có."""
    raw = path.read_bytes()
    for enc in ("utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8", "cp1252"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8"


def json_get(data, path):
    for k in path:
        data = data[k]
    return data


def json_set(data, path, value):
    for k in path[:-1]:
        data = data[k]
    data[path[-1]] = value
