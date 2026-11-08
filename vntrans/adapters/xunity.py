"""Unity (và game khác) dùng XUnity.AutoTranslator: file dịch dạng  gốc=bản dịch.

Thường nằm ở BepInEx/Translation/<lang>/Text/*.txt. Dòng có bản dịch trống hoặc
trùng với bản gốc sẽ được đưa đi dịch (thêm --retranslate để dịch lại tất cả).
"""
from __future__ import annotations

import re
from pathlib import Path

from .base import Adapter, read_text


def _split(line: str):
    # tìm dấu '=' đầu tiên không bị escape
    i = 0
    while i < len(line):
        if line[i] == "\\":
            i += 2
            continue
        if line[i] == "=":
            return line[:i], line[i + 1:]
        i += 1
    return None


def _unesc(s):
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "r": "\r", "t": "\t"}.get(m.group(1), m.group(1)), s)


def _esc(s):
    return s.replace("\\", "\\\\").replace("=", "\\=").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")


class XUnityAdapter(Adapter):
    name = "xunity"
    description = "XUnity.AutoTranslator (Unity) *.txt"

    def match(self, path: Path, root: Path):
        rel = path.relative_to(root).as_posix()
        return path.suffix == ".txt" and "Translation/" in rel and "/Text/" in "/" + rel

    def extract(self, path: Path):
        out = []
        for n, ln in enumerate(read_text(path)[0].split("\n")):
            ln = ln.rstrip("\r")
            if not ln or ln.startswith("//") or ln.startswith("r:") or ln.startswith("sr:"):
                continue
            kv = _split(ln)
            if not kv:
                continue
            k, v = _unesc(kv[0]), _unesc(kv[1])
            if not k.strip():
                continue
            if v and v != k and not self.opts.get("retranslate"):
                continue
            out.append(({"line": n}, k, "xunity"))
        return out

    def apply(self, path: Path, out_path: Path, items):
        text, enc = read_text(path)
        lines = text.split("\n")
        for loc, tgt in items:
            ln = lines[loc["line"]]
            cr = "\r" if ln.endswith("\r") else ""
            k, _ = _split(ln.rstrip("\r"))
            lines[loc["line"]] = k + "=" + _esc(tgt) + cr
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines), encoding="utf-8")
