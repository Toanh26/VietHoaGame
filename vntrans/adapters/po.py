"""GNU gettext .po (Godot, nhiều game indie/Linux, mod...)."""
from __future__ import annotations

import re
from pathlib import Path

from .base import Adapter, read_text

_KW = re.compile(r'^(msgctxt|msgid_plural|msgid|msgstr(?:\[\d+\])?)\s+"(.*)"\s*$')
_CONT = re.compile(r'^"(.*)"\s*$')


def _unesc(s):
    return re.sub(r'\\(.)', lambda m: {"n": "\n", "t": "\t", "r": "\r"}.get(m.group(1), m.group(1)), s)


def _esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")


def parse(lines):
    """Trả về list entry: {fields: {kw: str}, spans: {kw: (start, end)}, start}"""
    entries, cur, last = [], None, None
    for n, ln in enumerate(lines):
        m = _KW.match(ln)
        if m:
            kw = m.group(1)
            ctx_pending = cur is not None and "msgctxt" in cur["fields"] and "msgid" not in cur["fields"]
            if kw == "msgctxt" or (kw == "msgid" and not ctx_pending) or cur is None:
                cur = {"fields": {}, "spans": {}}
                entries.append(cur)
            cur["fields"][kw] = _unesc(m.group(2))
            cur["spans"][kw] = [n, n + 1]
            last = kw
            continue
        m = _CONT.match(ln)
        if m and cur is not None and last:
            cur["fields"][last] += _unesc(m.group(1))
            cur["spans"][last][1] = n + 1
            continue
        last = None
    return entries


class PoAdapter(Adapter):
    name = "po"
    description = "gettext .po"

    def match(self, path, root):
        return path.suffix.lower() in (".po", ".pot")

    def extract(self, path: Path):
        lines = read_text(path)[0].split("\n")
        out = []
        for idx, e in enumerate(parse(lines)):
            f = e["fields"]
            mid = f.get("msgid", "")
            if not mid:
                continue  # header
            src = f.get("msgid_plural") or mid
            ctx = "po" + (f" | ctx: {f['msgctxt']}" if "msgctxt" in f else "")
            key = {"msgctxt": f.get("msgctxt"), "msgid": mid}
            out.append((key, src, ctx))
        return out

    def apply(self, path: Path, out_path: Path, items):
        text, enc = read_text(path)
        lines = text.split("\n")
        want = {(loc.get("msgctxt"), loc["msgid"]): tgt for loc, tgt in items}
        repl = []  # (start, end, newlines)
        for e in parse(lines):
            f = e["fields"]
            k = (f.get("msgctxt"), f.get("msgid", ""))
            if k not in want:
                continue
            tgt = want[k]
            strs = [kw for kw in e["spans"] if kw.startswith("msgstr")]
            if not strs:
                continue
            start = min(e["spans"][kw][0] for kw in strs)
            end = max(e["spans"][kw][1] for kw in strs)
            kw = "msgstr[0]" if "msgid_plural" in f else "msgstr"
            repl.append((start, end, [f'{kw} "{_esc(tgt)}"']))
        for start, end, new in sorted(repl, reverse=True):
            lines[start:end] = new
        out = "\n".join(lines)
        out = re.sub(r'"Language: [^"\\]*\\n"', r'"Language: vi\\n"', out, count=1)
        out = re.sub(r'"Plural-Forms: [^"\\]*\\n"', r'"Plural-Forms: nplurals=1; plural=0;\\n"', out, count=1)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(out, encoding="utf-8")
