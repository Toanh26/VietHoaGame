"""Ren'Py: điền vào file dịch game/tl/<ngôn ngữ>/*.rpy.

Bước chuẩn bị: mở Ren'Py Launcher -> Generate Translations -> Language: vietnamese.
Ren'Py tạo các khối:

    translate vietnamese start_1a2b3c4d:
        # e "Hello there!"
        e "Hello there!"

    translate vietnamese strings:
        old "Start"
        new "Start"

Tool lấy chuỗi gốc từ dòng comment / dòng `old` và ghi bản dịch vào dòng phía sau.
"""
from __future__ import annotations

import re
from pathlib import Path

from .base import Adapter, read_text

_STR = re.compile(r'"((?:[^"\\]|\\.)*)"')
_TRANSLATE = re.compile(r"^translate\s+(\w+)\s+(\w+)\s*:")


def unescape(s: str) -> str:
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), s)


def escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class RenpyAdapter(Adapter):
    name = "renpy"
    description = "Ren'Py (game/tl/<lang>/*.rpy)"

    def match(self, path: Path, root: Path) -> bool:
        if path.suffix != ".rpy":
            return False
        parts = path.relative_to(root).parts
        if "tl" not in parts:
            return False
        lang = self.opts.get("renpy_lang")
        i = parts.index("tl")
        return lang is None or (len(parts) > i + 1 and parts[i + 1] == lang)

    def extract(self, path: Path):
        lines = read_text(path)[0].split("\n")
        out = []
        block = ""
        i = 0
        while i < len(lines):
            ln = lines[i]
            m = _TRANSLATE.match(ln)
            if m:
                block = m.group(2)
            st = ln.strip()
            if block == "strings" and st.startswith("old "):
                ms = _STR.search(st)
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if ms and j < len(lines) and lines[j].strip().startswith("new "):
                    src = unescape(ms.group(1))
                    if src.strip():
                        out.append(({"line": j, "kind": "new"}, src, f"renpy strings ({self._origin(lines, i)})"))
                    i = j + 1
                    continue
            elif block and block != "strings" and st.startswith("# ") and not st.startswith("# game/"):
                srcs = _STR.findall(st[2:])
                j = i + 1
                if srcs and j < len(lines) and lines[j].strip() and not lines[j].strip().startswith("#"):
                    if _STR.findall(lines[j]):
                        who = st[2:].split('"')[0].strip()
                        src = unescape(srcs[-1])
                        if src.strip():
                            out.append(({"line": j, "kind": "say"}, src,
                                        f"renpy dialogue {block}" + (f" | nhân vật: {who}" if who else "")))
                        i = j + 1
                        continue
            i += 1
        return out

    @staticmethod
    def _origin(lines, i):
        for k in range(i - 1, max(-1, i - 3), -1):
            if lines[k].strip().startswith("# game/"):
                return lines[k].strip()[2:]
        return ""

    def apply(self, path: Path, out_path: Path, items):
        text, enc = read_text(path)
        lines = text.split("\n")
        for loc, tgt in items:
            ln = lines[loc["line"]]
            spans = list(_STR.finditer(ln))
            if not spans:
                continue
            m = spans[-1]
            lines[loc["line"]] = ln[:m.start()] + '"' + escape(tgt) + '"' + ln[m.end():]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines), encoding="utf-8-sig" if enc == "utf-8-sig" else "utf-8")
