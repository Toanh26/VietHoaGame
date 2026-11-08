"""Unity (Mono): tự cài BepInEx 5 + XUnity.AutoTranslator, rồi chạy máy chủ dịch tại máy.

Chữ trong game Unity nằm trong asset đã biên dịch nên không trích trước được. XUnity bắt
chữ khi nó hiện lên màn hình và hỏi máy chủ dịch nội bộ (http://127.0.0.1:PORT) do ứng
dụng này chạy, máy chủ gọi Claude để dịch. XUnity tự lưu bản dịch vào
BepInEx/Translation/vi/Text/, nên lần sau chơi lại các câu đã gặp hiện ngay, không cần mạng.
"""
from __future__ import annotations

import io
import json
import re
import shutil
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ..translators import translate_texts
from .detect import exe_arch
from .jobs import Job

PORT = 47210
UA = {"User-Agent": "vntrans-game-translator"}
FALLBACK = {
    "bepinex": "https://github.com/BepInEx/BepInEx/releases/download/v5.4.23.2/BepInEx_win_{arch}_5.4.23.2.zip",
    "xunity": "https://github.com/bbepis/XUnity.AutoTranslator/releases/download/v5.4.5/XUnity.AutoTranslator-BepInEx-5.4.5.zip",
}
LANGS = {"auto": "", "English": "en", "Japanese": "ja", "Chinese": "zh-CN", "Korean": "ko"}


def _get(url: str, timeout=60) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _latest_asset(repo: str, pattern: str) -> str | None:
    try:
        data = json.loads(_get(f"https://api.github.com/repos/{repo}/releases/latest", 30))
        for a in data.get("assets", []):
            if re.fullmatch(pattern, a["name"]):
                return a["browser_download_url"]
    except Exception:  # noqa: BLE001
        return None
    return None


def set_ini(path: Path, values: dict[str, dict[str, str]]):
    """Cập nhật file .ini, giữ nguyên các khoá khác."""
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines() if path.exists() else []
    for section, kv in values.items():
        start = next((i for i, l in enumerate(lines) if l.strip().lower() == f"[{section.lower()}]"), None)
        if start is None:
            lines += ["", f"[{section}]"] + [f"{k}={v}" for k, v in kv.items()]
            continue
        end = next((i for i in range(start + 1, len(lines)) if lines[i].strip().startswith("[")), len(lines))
        for k, v in kv.items():
            idx = next((i for i in range(start + 1, end) if lines[i].split("=")[0].strip().lower() == k.lower()), None)
            if idx is None:
                lines.insert(end, f"{k}={v}")
                end += 1
            else:
                lines[idx] = f"{k}={v}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class LiveServer:
    """Máy chủ dịch cho XUnity (CustomTranslate):  GET /translate?from=..&to=..&text=.."""

    def __init__(self, translator, cache_path: Path, log=print, port: int = PORT):
        self.tr, self.cache_path, self.log, self.port = translator, cache_path, log, port
        self.cache: dict[str, str] = {}
        if cache_path.exists():
            try:
                self.cache = json.loads(cache_path.read_text(encoding="utf-8"))
            except ValueError:
                pass
        self.lock = threading.Lock()
        self.queue: list[tuple[str, threading.Event, dict]] = []
        self.cv = threading.Condition()
        self.httpd = None
        self.count = 0

    # gom các yêu cầu gần nhau thành 1 lần gọi API
    def _worker(self):
        while self.httpd:
            with self.cv:
                while not self.queue and self.httpd:
                    self.cv.wait(0.5)
                time.sleep(0.25)
                batch, self.queue = self.queue[:30], self.queue[30:]
            if not batch:
                continue
            uniq = list(dict.fromkeys(t for t, _, _ in batch))
            items = [{"id": str(i), "text": t, "ctx": "chữ trong game (UI hoặc hội thoại)"} for i, t in enumerate(uniq)]
            try:
                res = translate_texts(self.tr, items)
                got = {uniq[int(k)]: v[0] for k, v in res.items()}
            except Exception as e:  # noqa: BLE001
                self.log(f"  ! lỗi dịch: {e}")
                got = {}
            with self.lock:
                self.cache.update(got)
                self.count += len(got)
                self._save()
            for t, ev, box in batch:
                box["r"] = got.get(t)
                ev.set()
            if got:
                sample = next(iter(got.items()))
                self.log(f"  Đã dịch {self.count} câu.  Vd: {sample[0][:40]!r} -> {sample[1][:40]!r}")

    def _save(self):
        tmp = self.cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.cache_path)

    def translate(self, text: str) -> str | None:
        with self.lock:
            if text in self.cache:
                return self.cache[text]
        ev, box = threading.Event(), {}
        with self.cv:
            self.queue.append((text, ev, box))
            self.cv.notify()
        ev.wait(120)
        return box.get("r")

    def start(self):
        srv = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                q = urllib.parse.urlparse(self.path)
                text = urllib.parse.parse_qs(q.query).get("text", [""])[0]
                if q.path != "/translate" or not text:
                    self.send_response(200 if q.path == "/" else 404)
                    self.end_headers()
                    self.wfile.write(b"vntrans OK")
                    return
                r = srv.translate(text)
                if r is None:
                    self.send_response(500)
                    self.end_headers()
                    return
                body = r.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", self.port), H)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        threading.Thread(target=self._worker, daemon=True).start()

    def stop(self):
        if self.httpd:
            h, self.httpd = self.httpd, None
            h.shutdown()
            h.server_close()


class UnityJob(Job):
    source_lang = "auto"

    def _install(self, key: str, url: str | None):
        self.log(f"Đang tải {url.rsplit('/', 1)[-1]} ...")
        data = _get(url, 180)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            z.extractall(self.info.root)

    def run(self) -> bool:
        root = self.info.root
        marker = self.work / "installed.json"
        installed = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else {}
        arch = exe_arch(self.info.exe)
        if not (root / "BepInEx" / "core" / "BepInEx.dll").exists():
            url = _latest_asset("BepInEx/BepInEx", rf"BepInEx_(win_)?{arch}_5[\d.]+\.zip") or FALLBACK["bepinex"].format(arch=arch)
            self._install("bepinex", url)
            installed["bepinex"] = True
        if not list((root / "BepInEx" / "plugins").glob("**/XUnity.AutoTranslator.Plugin.Core.dll")):
            url = _latest_asset("bbepis/XUnity.AutoTranslator", r"XUnity\.AutoTranslator-BepInEx-\d[\d.]*\.zip") or FALLBACK["xunity"]
            self._install("xunity", url)
            installed["xunity"] = True
        marker.write_text(json.dumps(installed), encoding="utf-8")
        set_ini(root / "BepInEx" / "config" / "AutoTranslatorConfig.ini", {
            "Service": {"Endpoint": "CustomTranslate", "FallbackEndpoint": ""},
            "General": {"Language": "vi", "FromLanguage": LANGS.get(self.source_lang, "") or "en"},
            "Custom": {"Url": f"http://127.0.0.1:{PORT}/translate", "EnableShortDelay": "True",
                       "DisableSpamChecks": "True"},
            "Behaviour": {"OverrideFont": "Arial", "MaxCharactersPerTranslation": "500"},
        })
        self.log("Đã cài BepInEx + XUnity.AutoTranslator.")
        self.server = LiveServer(self.tr, self.work / "live_cache.json", self.log)
        self.server.start()
        self.log("")
        self.log("==> MỞ GAME VÀ CHƠI. Chữ sẽ được dịch sang tiếng Việt khi hiện lên màn hình.")
        self.log("    Giữ cửa sổ này mở trong lúc chơi. Lần mở đầu tiên game khởi động lâu hơn bình thường.")
        self.log("    Phím trong game: Alt+T bật/tắt bản dịch, Alt+0 mở bảng XUnity.")
        return True

    def restore(self):
        root = self.info.root
        marker = self.work / "installed.json"
        installed = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else {}
        if installed.get("bepinex"):
            for p in ("winhttp.dll", "doorstop_config.ini", ".doorstop_version", "changelog.txt"):
                (root / p).unlink(missing_ok=True)
            shutil.rmtree(root / "BepInEx", ignore_errors=True)
            self.log("Đã gỡ BepInEx và XUnity.AutoTranslator.")
        elif installed.get("xunity"):
            for p in (root / "BepInEx" / "plugins").glob("XUnity*"):
                shutil.rmtree(p, ignore_errors=True)
            self.log("Đã gỡ XUnity.AutoTranslator (BepInEx có từ trước nên giữ lại).")
        else:
            self.log("Không có gì để gỡ.")
        marker.unlink(missing_ok=True)
