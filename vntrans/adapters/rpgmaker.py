"""RPG Maker MV / MZ: các file data/*.json.

Hội thoại (lệnh 401 Show Text, 405 Scroll Text) được gom theo cả khung thoại
để người/máy dịch thấy trọn câu; khi ghi lại, số dòng có thể khác bản gốc.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .base import Adapter, json_get, json_set, read_text

DB_FIELDS = ["name", "nickname", "profile", "description", "message1", "message2", "message3", "message4"]
DB_FILES = {"Actors", "Classes", "Skills", "Items", "Weapons", "Armors", "Enemies", "States"}
SYSTEM_LISTS = ["elements", "skillTypes", "weaponTypes", "armorTypes", "equipTypes"]
_ESC = re.compile(r"\\[A-Za-z]+\[[^\]]*\]|\\[A-Za-z{}\\|.!><^$]")


class RpgMakerAdapter(Adapter):
    name = "rpgmaker"
    description = "RPG Maker MV/MZ (data/*.json)"

    def match(self, path: Path, root: Path) -> bool:
        if path.suffix.lower() != ".json":
            return False
        d = path.parent
        if not ((d / "System.json").exists() and (d / "Actors.json").exists()):
            return False
        s = path.stem
        return s in DB_FILES or s in ("System", "CommonEvents", "Troops") or bool(re.fullmatch(r"Map\d+", s))

    # ------------------------------------------------------------------ extract
    def extract(self, path: Path):
        text, _ = read_text(path)
        data = json.loads(text)
        stem = path.stem
        out: list = []

        def add(p, ctx):
            v = json_get(data, p)
            if isinstance(v, str) and v.strip():
                out.append(({"p": p}, v, ctx))

        if stem in DB_FILES:
            for i, obj in enumerate(data):
                if not obj:
                    continue
                for f in DB_FIELDS:
                    if f in obj:
                        add([i, f], f"{stem}.{f}")
        elif stem == "System":
            for f in ("gameTitle", "currencyUnit"):
                if f in data:
                    add([f], f"System.{f}")
            for f in SYSTEM_LISTS:
                for i, _v in enumerate(data.get(f) or []):
                    add([f, i], f"System.{f}")
            terms = data.get("terms", {})
            for f in ("basic", "commands", "params"):
                for i, _v in enumerate(terms.get(f) or []):
                    if isinstance(terms[f][i], str):
                        add(["terms", f, i], f"System.terms.{f}")
            for k in terms.get("messages", {}) or {}:
                add(["terms", "messages", k], f"System.terms.messages.{k}")
        elif stem == "CommonEvents":
            for i, ev in enumerate(data):
                if ev:
                    out += self._commands(ev.get("list") or [], [i, "list"], f"CommonEvent {ev.get('name', '')}")
        elif stem == "Troops":
            for i, tr in enumerate(data):
                if tr:
                    for j, pg in enumerate(tr.get("pages") or []):
                        out += self._commands(pg.get("list") or [], [i, "pages", j, "list"], f"Troop {tr.get('name', '')}")
        else:  # MapXXX
            if data.get("displayName"):
                add(["displayName"], "Map.displayName")
            for i, ev in enumerate(data.get("events") or []):
                if ev:
                    for j, pg in enumerate(ev.get("pages") or []):
                        out += self._commands(pg.get("list") or [], ["events", i, "pages", j, "list"],
                                              f"{stem} event {ev.get('name', '')}")
        return out

    def _commands(self, lst, base, ctx):
        out = []
        speaker = ""
        i = 0
        while i < len(lst):
            c = lst[i] or {}
            code, prm = c.get("code"), c.get("parameters") or []
            if code in (401, 405):
                j = i
                while j < len(lst) and (lst[j] or {}).get("code") == code:
                    j += 1
                lines = [str((lst[k].get("parameters") or [""])[0]) for k in range(i, j)]
                src = "\n".join(lines)
                if src.strip():
                    out.append(({"block": base, "start": i, "count": j - i, "code": code}, src,
                                f"{ctx} | " + (f"thoại của {speaker}" if speaker else "hội thoại")))
                i = j
                continue
            if code == 101:
                speaker = prm[4] if len(prm) > 4 and isinstance(prm[4], str) else ""
                if speaker.strip():
                    out.append(({"p": base + [i, "parameters", 4]}, speaker, f"{ctx} | tên người nói"))
            elif code == 102 and prm and isinstance(prm[0], list):
                for k, ch in enumerate(prm[0]):
                    if isinstance(ch, str) and ch.strip():
                        out.append(({"p": base + [i, "parameters", 0, k]}, ch, f"{ctx} | lựa chọn"))
            elif code == 402 and len(prm) > 1 and isinstance(prm[1], str) and prm[1].strip():
                out.append(({"p": base + [i, "parameters", 1]}, prm[1], f"{ctx} | nhánh lựa chọn"))
            elif code in (320, 324, 325) and len(prm) > 1 and isinstance(prm[1], str) and prm[1].strip():
                out.append(({"p": base + [i, "parameters", 1]}, prm[1], f"{ctx} | đổi tên/biệt danh/tiểu sử"))
            i += 1
        return out

    # ------------------------------------------------------------------ apply
    def apply(self, path: Path, out_path: Path, items):
        text, enc = read_text(path)
        data = json.loads(text)
        wrap = int(self.opts.get("wrap") or 0)
        blocks: dict[str, list] = {}
        for loc, tgt in items:
            if "p" in loc:
                json_set(data, loc["p"], tgt)
            else:
                blocks.setdefault(json.dumps(loc["block"]), []).append((loc, tgt))
        for key, lst in blocks.items():
            cmds = json_get(data, json.loads(key))
            # thay từ cuối lên đầu để chỉ số phía trước không bị lệch
            for loc, tgt in sorted(lst, key=lambda x: -x[0]["start"]):
                s, n = loc["start"], loc["count"]
                indent = (cmds[s] or {}).get("indent", 0)
                lines = self._wrap(tgt, wrap)
                new = [{"code": loc["code"], "indent": indent, "parameters": [ln]} for ln in lines]
                cmds[s:s + n] = new
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                            encoding="utf-8")

    @staticmethod
    def _wrap(text: str, width: int) -> list[str]:
        lines = text.split("\n")
        if width <= 0:
            return lines
        vis = lambda s: len(_ESC.sub("", s))  # độ dài hiển thị, không tính mã điều khiển
        out = []
        for ln in lines:
            cur = ""
            for word in ln.split(" "):
                cand = word if not cur else cur + " " + word
                if cur and vis(cand) > width:
                    out.append(cur)
                    cur = word
                else:
                    cur = cand
            out.append(cur)
        return out
