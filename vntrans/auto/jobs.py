"""Các 'job' Việt hoá tự động một game, theo từng engine.

Mỗi job làm việc trong thư mục <game>/vntrans_vi/ (dự án, sao lưu, nhật ký) để có thể:
  - chạy lại -> dịch tiếp phần còn dở
  - khôi phục bản gốc bất cứ lúc nào
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from ..adapters.rpgmaker import RpgMakerAdapter
from ..pipeline import estimate_cost, pending, translate_project
from ..project import Entry, Project, make_id
from .detect import GameInfo

WORK = "vntrans_vi"


def asset(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    for cand in (base / "assets" / name, base / "vntrans" / "assets" / name):
        if cand.exists():
            return cand
    raise FileNotFoundError(name)


def system_font() -> Path | None:
    """Font hệ thống có đủ dấu tiếng Việt."""
    windir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for f in ("arial.ttf", "segoeui.ttf", "tahoma.ttf", "verdana.ttf", "times.ttf"):
        if (windir / f).exists():
            return windir / f
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",):
        if Path(f).exists():
            return Path(f)
    return None


class Job:
    def __init__(self, info: GameInfo, translator, *, log: Callable[[str], None] = print,
                 progress: Callable[[int, int], None] | None = None,
                 should_stop: Callable[[], bool] | None = None,
                 confirm: Callable[[int, float], bool] | None = None,
                 model: str = "claude-opus-5-5", glossary: dict | None = None):
        self.info, self.tr, self.log = info, translator, log
        self.progress, self.should_stop, self.confirm = progress, should_stop, confirm
        self.model, self.glossary = model, glossary or {}
        self.work = info.root / WORK
        self.work.mkdir(exist_ok=True)
        self.proj_path = self.work / "project.json"

    # -------- dùng chung
    def _translate(self, proj: Project) -> bool:
        todo = pending(proj, self.glossary)
        if todo and self.confirm:
            if not self.confirm(len(todo), estimate_cost(todo, self.model)):
                self.log("Đã huỷ.")
                return False
        if todo:
            translate_project(proj, self.tr, self.proj_path, glossary=self.glossary, log=self.log,
                              progress=self.progress, should_stop=self.should_stop)
        else:
            self.log("Tất cả đã được dịch từ trước.")
        proj.save(self.proj_path)
        s = proj.stats()
        self.log(f"Đã dịch {s['translated']}/{s['total']} câu.")
        return True

    def run(self) -> bool:  # pragma: no cover
        raise NotImplementedError

    def restore(self) -> None:  # pragma: no cover
        raise NotImplementedError


# =============================================================== RPG Maker MV/MZ
class RpgMakerJob(Job):
    """Dịch thẳng vào data/*.json (giữ bản gốc trong vntrans_vi/backup) + plugin font/từ điển."""

    @property
    def base(self) -> Path:          # thư mục chứa data/, js/, fonts/
        return self.info.data_dir.parent

    @property
    def backup(self) -> Path:
        return self.work / "backup"

    def _ensure_backup(self):
        bdata = self.backup / "data"
        if not bdata.exists():
            self.log("Sao lưu dữ liệu gốc...")
            bdata.mkdir(parents=True)
            for f in self.info.data_dir.glob("*.json"):
                if f.name != "vi_dictionary.json":
                    shutil.copy2(f, bdata / f.name)
            pj = self.base / "js" / "plugins.js"
            if pj.exists():
                shutil.copy2(pj, self.backup / "plugins.js")
        return bdata

    def run(self) -> bool:
        bdata = self._ensure_backup()
        ad = RpgMakerAdapter({})
        entries = []
        for f in sorted(bdata.glob("*.json")):
            if ad.match(f, bdata):
                for loc, src, ctx in ad.extract(f):
                    entries.append(Entry(id=make_id(f.name, loc), file=f.name, adapter="rpgmaker",
                                         loc=loc, src=src, ctx=ctx))
        proj = Project.load(self.proj_path) if self.proj_path.exists() else Project()
        proj.game_dir = str(self.info.root)
        proj.merge(entries)
        proj.save(self.proj_path)
        self.log(f"Tìm thấy {len(entries)} đoạn văn bản.")
        if not self._translate(proj):
            return False
        self.install(proj)
        return True

    def install(self, proj: Project):
        self.log("Ghi bản dịch vào game...")
        by_file: dict[str, list] = {}
        for e in proj.entries:
            if e.tgt:
                by_file.setdefault(e.file, []).append((e.loc, e.tgt))
        ad = RpgMakerAdapter({})
        for name, items in by_file.items():
            ad.apply(self.backup / "data" / name, self.info.data_dir / name, items)
        # từ điển runtime (dịch cả chữ trong plugin khác)
        (self.info.data_dir / "vi_dictionary.json").write_text(
            json.dumps(proj.memory(), ensure_ascii=False), encoding="utf-8")
        # font
        font_name = ""
        f = system_font()
        if f:
            fonts = self.base / "fonts"
            fonts.mkdir(exist_ok=True)
            font_name = "vntrans_font" + f.suffix
            shutil.copy2(f, fonts / font_name)
        else:
            self.log("  ! không tìm thấy font tiếng Việt trong hệ thống, giữ font gốc.")
        # plugin
        plugdir = self.base / "js" / "plugins"
        plugdir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(asset("VietTranslate.js"), plugdir / "VietTranslate.js")
        self._register_plugin(font_name)
        self.log("Đã cài plugin VietTranslate (font tiếng Việt, tự xuống dòng).")

    def _register_plugin(self, font_name: str):
        pj = self.base / "js" / "plugins.js"
        src = (self.backup / "plugins.js") if (self.backup / "plugins.js").exists() else pj
        text = src.read_text(encoding="utf-8-sig") if src.exists() else "var $plugins =\n[];\n"
        i, j = text.find("["), text.rfind("]")
        plugins = json.loads(text[i:j + 1]) if i >= 0 and j > i else []
        plugins = [p for p in plugins if p.get("name") != "VietTranslate"]
        plugins.append({"name": "VietTranslate", "status": True,
                        "description": "Viet hoa (vntrans)",
                        "parameters": {"DictionaryFile": "vi_dictionary.json", "FontFile": font_name,
                                       "FontSize": "0", "TranslateDrawText": "true", "AutoWrap": "true"}})
        body = ",\n".join(json.dumps(p, ensure_ascii=False) for p in plugins)
        pj.write_text("// Generated by RPG Maker.\n// Do not edit this file directly.\nvar $plugins =\n[\n"
                      + body + "\n];\n", encoding="utf-8")

    def restore(self):
        bdata = self.backup / "data"
        if not bdata.exists():
            self.log("Chưa có bản sao lưu — game đang là bản gốc.")
            return
        for f in bdata.glob("*.json"):
            shutil.copy2(f, self.info.data_dir / f.name)
        if (self.backup / "plugins.js").exists():
            shutil.copy2(self.backup / "plugins.js", self.base / "js" / "plugins.js")
        for p in (self.info.data_dir / "vi_dictionary.json", self.base / "js" / "plugins" / "VietTranslate.js"):
            p.unlink(missing_ok=True)
        for p in (self.base / "fonts").glob("vntrans_font.*"):
            p.unlink()
        self.log("Đã khôi phục bản gốc (bản dịch vẫn giữ trong vntrans_vi, chạy lại sẽ không tốn phí dịch).")


# =============================================================== Ren'Py
class RenpyJob(Job):
    """Không sửa script gốc: thêm 1 file zz_vntrans.rpy vào game/, file này
    1) chế độ 'quét': liệt kê mọi câu thoại/lựa chọn rồi tự thoát,
    2) khi chơi: thay câu gốc bằng bản dịch, ghi lại chữ giao diện còn thiếu.
    Nhấn F8 trong game để bật/tắt tiếng Việt."""

    HOOK = "zz_vntrans.rpy"

    @property
    def gdir(self) -> Path:
        return self.info.data_dir

    def _install_hook(self):
        shutil.copy2(asset("zz_vntrans.rpy"), self.gdir / self.HOOK)
        f = system_font()
        if f:
            shutil.copy2(f, self.gdir / ("vntrans_font" + f.suffix))
            (self.gdir / "vntrans_font.txt").write_text("vntrans_font" + f.suffix, encoding="utf-8")

    def _scan(self) -> list[dict]:
        out_file = self.work / "scan.json"
        out_file.unlink(missing_ok=True)
        flag = self.gdir / "vntrans_scan.flag"
        flag.write_text(str(out_file), encoding="utf-8")
        exe = self.info.exe
        if not exe:
            raise RuntimeError("Không tìm thấy file .exe của game.")
        self.log("Đang quét kịch bản (game sẽ tự mở rồi đóng, có thể mất 1-2 phút)...")
        proc = subprocess.Popen([str(exe)], cwd=str(self.info.root))
        t0 = time.time()
        while time.time() - t0 < 600:
            if out_file.exists() and out_file.stat().st_size > 0:
                time.sleep(1)
                break
            if proc.poll() is not None and not out_file.exists():
                time.sleep(3)
                if not out_file.exists():
                    break
            time.sleep(1)
        flag.unlink(missing_ok=True)
        if proc.poll() is None:
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
        if not out_file.exists():
            log = self.info.root / "log.txt"
            hint = ""
            if log.exists():
                hint = "\n" + log.read_text(encoding="utf-8", errors="replace")[-1500:]
            raise RuntimeError("Không quét được kịch bản (game không tạo file kết quả)." + hint)
        return json.loads(out_file.read_text(encoding="utf-8"))

    def _missing(self) -> list[str]:
        f = self.gdir / "vntrans_missing.txt"
        out = []
        if f.exists():
            for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    out.append(json.loads(ln))
                except ValueError:
                    pass
        return out

    def run(self) -> bool:
        self._install_hook()
        items = self._scan()
        entries = []
        for it in items:
            loc = {"f": it.get("f"), "l": it.get("l"), "k": it.get("k"), "t": it["t"]}
            who = it.get("who") or ""
            ctx = "lựa chọn" if it.get("k") == "menu" else (f"thoại — nhân vật: {who}" if who else "lời dẫn/thoại")
            entries.append(Entry(id=make_id(it.get("f") or "", loc), file=it.get("f") or "",
                                 adapter="renpy_rt", loc=loc, src=it["t"], ctx=ctx))
        for s in self._missing():
            loc = {"ui": s}
            entries.append(Entry(id=make_id("ui", loc), file="ui", adapter="renpy_rt", loc=loc, src=s,
                                 ctx="chữ giao diện (menu, nút bấm)"))
        proj = Project.load(self.proj_path) if self.proj_path.exists() else Project()
        proj.game_dir = str(self.info.root)
        proj.merge(entries)
        proj.save(self.proj_path)
        self.log(f"Tìm thấy {len(items)} câu thoại/lựa chọn và {len(self._missing())} chữ giao diện.")
        if not self._translate(proj):
            return False
        (self.gdir / "vntrans_vi.json").write_text(json.dumps(proj.memory(), ensure_ascii=False), encoding="utf-8")
        self.log("Đã ghi bản dịch. Trong game nhấn F8 để chuyển Tiếng Việt <-> bản gốc.")
        self.log("Mẹo: chữ giao diện chưa dịch sẽ được ghi lại khi bạn chơi; bấm 'Việt hoá' lần nữa để dịch nốt.")
        return True

    def restore(self):
        for p in [self.gdir / self.HOOK, self.gdir / (self.HOOK + "c"), self.gdir / "vntrans_vi.json",
                  self.gdir / "vntrans_font.txt", self.gdir / "vntrans_scan.flag"] + list(self.gdir.glob("vntrans_font.*")):
            p.unlink(missing_ok=True)
        self.log("Đã gỡ Việt hoá (bản dịch vẫn giữ trong vntrans_vi).")


def make_job(info: GameInfo, translator, **kw) -> Job:
    if info.engine.startswith("rpgmaker"):
        return RpgMakerJob(info, translator, **kw)
    if info.engine == "renpy":
        return RenpyJob(info, translator, **kw)
    if info.engine == "unity_mono":
        from .unity import UnityJob
        return UnityJob(info, translator, **kw)
    raise RuntimeError(" ".join(info.notes) or "Engine chưa được hỗ trợ.")
