"""Bảng dịch CSV/TSV (Godot translation CSV, Unity Localization export, I2 Localization...).

Dạng:  keys,en,ja        ->  tool đọc cột --src-col (mặc định "en") và ghi cột --dst-col
(mặc định "vi"; nếu chưa có cột thì thêm vào cuối).
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from .base import Adapter, read_text


class CsvAdapter(Adapter):
    name = "csv"
    description = "Bảng dịch CSV/TSV có cột ngôn ngữ"

    def match(self, path, root):
        return path.suffix.lower() in (".csv", ".tsv")

    def _read(self, path):
        text, enc = read_text(path)
        delim = "\t" if path.suffix.lower() == ".tsv" else ","
        rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delim))
        return rows, delim, enc

    def _cols(self, header):
        src = self.opts.get("src_col") or "en"
        dst = self.opts.get("dst_col") or "vi"
        low = [h.strip().lower() for h in header]
        if src.lower() not in low:
            return None, None
        return low.index(src.lower()), (low.index(dst.lower()) if dst.lower() in low else None)

    def extract(self, path: Path):
        rows, _, _ = self._read(path)
        if not rows:
            return []
        si, di = self._cols(rows[0])
        if si is None:
            return []
        out = []
        for r, row in enumerate(rows[1:], start=1):
            if si < len(row) and row[si].strip():
                if di is not None and di < len(row) and row[di].strip() and not self.opts.get("retranslate"):
                    continue
                out.append(({"row": r}, row[si], f"csv key: {row[0] if row else ''}"))
        return out

    def apply(self, path: Path, out_path: Path, items):
        rows, delim, enc = self._read(path)
        si, di = self._cols(rows[0])
        if di is None:
            rows[0].append(self.opts.get("dst_col") or "vi")
            di = len(rows[0]) - 1
        for loc, tgt in items:
            row = rows[loc["row"]]
            while len(row) <= di:
                row.append("")
            row[di] = tgt
        buf = io.StringIO()
        csv.writer(buf, delimiter=delim, lineterminator="\n").writerows(rows)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(buf.getvalue(), encoding="utf-8-sig" if enc == "utf-8-sig" else "utf-8")
