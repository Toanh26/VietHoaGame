"""Adapter = bộ đọc/ghi cho từng định dạng game.

Mỗi adapter có:
  match(path, root)            -> bool   (file này có phải định dạng của mình không)
  extract(path)                -> list[(loc, src, ctx)]
  apply(path, out_path, items, opts)     items = list[(loc, tgt)]
"""
from __future__ import annotations

import fnmatch
from pathlib import Path

from .base import Adapter
from .csvtable import CsvAdapter
from .jsonkv import JsonAdapter
from .po import PoAdapter
from .renpy import RenpyAdapter
from .rpgmaker import RpgMakerAdapter
from .xunity import XUnityAdapter

ADAPTERS: dict[str, type[Adapter]] = {
    a.name: a for a in (RpgMakerAdapter, RenpyAdapter, PoAdapter, XUnityAdapter, JsonAdapter, CsvAdapter)
}
# Adapter được thử tự động (an toàn: nhận diện chắc chắn được định dạng).
AUTO = ["rpgmaker", "renpy", "po", "xunity"]

SKIP_DIRS = {".git", "node_modules", "__pycache__", "www/js/libs", "js/libs", "cache", "saves", "save"}


def iter_files(root: Path, includes: list[str] | None):
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if any(part in SKIP_DIRS for part in rel.split("/")[:-1]):
            continue
        if includes and not any(fnmatch.fnmatch(rel, pat) for pat in includes):
            continue
        yield p, rel


def pick(path: Path, root: Path, names: list[str], opts: dict) -> Adapter | None:
    for n in names:
        a = ADAPTERS[n](opts)
        if a.match(path, root):
            return a
    return None
