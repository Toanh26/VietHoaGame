"""File dự án dịch (project.json): danh sách mọi câu cần dịch + bản dịch."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Entry:
    id: str
    file: str          # đường dẫn tương đối trong thư mục game
    adapter: str
    loc: object        # vị trí trong file (adapter tự hiểu)
    src: str           # văn bản gốc
    tgt: str = ""      # bản dịch
    ctx: str = ""      # ngữ cảnh (tên trường, người nói...)
    status: str = ""   # "", "mt" (máy dịch), "ok" (đã duyệt), "review" (cần xem lại)
    note: str = ""


def make_id(file: str, loc: object) -> str:
    raw = file + "|" + json.dumps(loc, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class Project:
    game_dir: str = ""
    source_lang: str = "en"
    target_lang: str = "vi"
    entries: list[Entry] = field(default_factory=list)
    settings: dict = field(default_factory=dict)

    # ---------- IO ----------
    @classmethod
    def load(cls, path: str | Path) -> "Project":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        p = cls(
            game_dir=data.get("game_dir", ""),
            source_lang=data.get("source_lang", "en"),
            target_lang=data.get("target_lang", "vi"),
            settings=data.get("settings", {}),
        )
        p.entries = [Entry(**e) for e in data.get("entries", [])]
        return p

    def save(self, path: str | Path) -> None:
        path = Path(path)
        data = {
            "format": "vntrans-project/1",
            "game_dir": self.game_dir,
            "source_lang": self.source_lang,
            "target_lang": self.target_lang,
            "settings": self.settings,
            "entries": [asdict(e) for e in self.entries],
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)

    # ---------- merge ----------
    def merge(self, new_entries: list[Entry]) -> tuple[int, int, int]:
        """Gộp kết quả extract mới: giữ bản dịch cũ nếu văn bản gốc không đổi.
        Trả về (mới, giữ nguyên, gốc đã thay đổi)."""
        old = {e.id: e for e in self.entries}
        tm = self.memory()
        added = kept = changed = 0
        out = []
        for e in new_entries:
            o = old.get(e.id)
            if o and o.src == e.src:
                e.tgt, e.status, e.note = o.tgt, o.status, o.note
                kept += 1
            else:
                if o:
                    changed += 1
                else:
                    added += 1
                if e.src in tm:
                    e.tgt, e.status = tm[e.src], "mt"
            out.append(e)
        self.entries = out
        return added, kept, changed

    def memory(self) -> dict[str, str]:
        """Bộ nhớ dịch: văn bản gốc -> bản dịch (ưu tiên bản đã duyệt)."""
        tm: dict[str, str] = {}
        for e in sorted(self.entries, key=lambda x: x.status == "ok"):
            if e.tgt:
                tm[e.src] = e.tgt
        return tm

    def stats(self) -> dict:
        total = len(self.entries)
        done = sum(1 for e in self.entries if e.tgt)
        review = sum(1 for e in self.entries if e.status == "review")
        uniq = len({e.src for e in self.entries})
        chars = sum(len(s) for s in {e.src for e in self.entries if not e.tgt})
        return {"total": total, "translated": done, "review": review,
                "unique_src": uniq, "untranslated_chars": chars}

    # ---------- CSV (dịch tay bằng Excel / Google Sheets) ----------
    def export_csv(self, path: str | Path, only_untranslated: bool = False) -> int:
        n = 0
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["id", "file", "context", "source", "vietnamese", "status", "note"])
            for e in self.entries:
                if only_untranslated and e.tgt:
                    continue
                w.writerow([e.id, e.file, e.ctx, e.src, e.tgt, e.status, e.note])
                n += 1
        return n

    def import_csv(self, path: str | Path) -> int:
        by_id = {e.id: e for e in self.entries}
        n = 0
        with open(path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                e = by_id.get(row.get("id", ""))
                if not e:
                    continue
                tgt = row.get("vietnamese", "")
                if tgt != e.tgt or row.get("status", e.status) != e.status:
                    e.tgt = tgt
                    e.status = row.get("status") or ("ok" if tgt else "")
                    e.note = row.get("note", e.note)
                    n += 1
        return n


def load_glossary(path: str | Path | None) -> dict[str, str]:
    """Bảng thuật ngữ CSV 2 cột: source,vietnamese (tên nhân vật, kỹ năng...)."""
    if not path:
        return {}
    g = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if len(row) >= 2 and row[0].strip() and not row[0].startswith("#"):
                if row[0].strip().lower() in ("source", "src", "en"):
                    continue
                g[row[0].strip()] = row[1].strip()
    return g
