"""Giao diện Việt hoá game: chọn game -> bấm Việt hoá -> chơi."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import traceback
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from . import __version__
from .auto.detect import detect, steam_games
from .auto.jobs import make_job
from .translators import make_translator

APP = "Việt hoá Game"
MODELS = [
    ("claude-opus-5-5", "Opus 5.5 — chất lượng cao nhất"),
    ("claude-sonnet-5-5", "Sonnet 5.5 — nhanh hơn, rẻ hơn"),
    ("claude-haiku-5-5", "Haiku 5.5 — nhanh nhất, rẻ nhất"),
]
SRC_LANGS = [("auto", "Tự nhận diện"), ("English", "Tiếng Anh"), ("Japanese", "Tiếng Nhật"),
             ("Chinese", "Tiếng Trung"), ("Korean", "Tiếng Hàn")]


def config_path() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home() / ".config") / "vntrans"
    base.mkdir(parents=True, exist_ok=True)
    return base / "config.json"


def load_config() -> dict:
    try:
        return json.loads(config_path().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def save_config(cfg: dict):
    config_path().write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = load_config()
        self.q: queue.Queue = queue.Queue()
        self.stop_flag = threading.Event()
        self.worker: threading.Thread | None = None
        self.job = None
        self.info = None
        self.games: list[tuple[str, Path]] = []

        root.title(f"{APP} v{__version__}")
        root.geometry("780x680")
        root.minsize(680, 560)
        style = ttk.Style()
        try:
            style.theme_use("vista" if sys.platform == "win32" else "clam")
        except tk.TclError:
            pass
        style.configure("Big.TButton", font=("Segoe UI", 12, "bold"), padding=8)
        style.configure("H.TLabelframe.Label", font=("Segoe UI", 10, "bold"))

        pad = dict(padx=10, pady=6)
        # ---------------------------------------------------------- 1. game
        f1 = ttk.LabelFrame(root, text="1. Chọn game", style="H.TLabelframe")
        f1.pack(fill="x", **pad)
        row = ttk.Frame(f1)
        row.pack(fill="x", padx=8, pady=6)
        ttk.Label(row, text="Game trên Steam:").pack(side="left")
        self.cb_game = ttk.Combobox(row, state="readonly")
        self.cb_game.pack(side="left", fill="x", expand=True, padx=6)
        self.cb_game.bind("<<ComboboxSelected>>", self.on_pick_steam)
        ttk.Button(row, text="Chọn thư mục game...", command=self.on_browse).pack(side="left")
        self.lbl_path = ttk.Label(f1, text="Chưa chọn game", foreground="#666")
        self.lbl_path.pack(fill="x", padx=8)
        self.lbl_engine = ttk.Label(f1, text="", font=("Segoe UI", 10, "bold"))
        self.lbl_engine.pack(fill="x", padx=8, pady=(0, 6))

        # ---------------------------------------------------------- 2. cài đặt
        f2 = ttk.LabelFrame(root, text="2. Cài đặt dịch", style="H.TLabelframe")
        f2.pack(fill="x", **pad)
        g = ttk.Frame(f2)
        g.pack(fill="x", padx=8, pady=6)
        g.columnconfigure(1, weight=1)
        ttk.Label(g, text="Claude API key:").grid(row=0, column=0, sticky="w")
        self.var_key = tk.StringVar(value=self.cfg.get("api_key", ""))
        ttk.Entry(g, textvariable=self.var_key, show="•").grid(row=0, column=1, sticky="ew", padx=6)
        link = ttk.Label(g, text="Lấy API key", foreground="#0a64d8", cursor="hand2")
        link.grid(row=0, column=2, sticky="w")
        link.bind("<Button-1>", lambda e: webbrowser.open("https://platform.claude.com/settings/keys"))

        ttk.Label(g, text="Model:").grid(row=1, column=0, sticky="w", pady=4)
        self.cb_model = ttk.Combobox(g, state="readonly", values=[m[1] for m in MODELS])
        mi = next((i for i, m in enumerate(MODELS) if m[0] == self.cfg.get("model")), 0)
        self.cb_model.current(mi)
        self.cb_model.grid(row=1, column=1, sticky="ew", padx=6)

        ttk.Label(g, text="Ngôn ngữ gốc:").grid(row=2, column=0, sticky="w")
        self.cb_src = ttk.Combobox(g, state="readonly", values=[s[1] for s in SRC_LANGS])
        si = next((i for i, s in enumerate(SRC_LANGS) if s[0] == self.cfg.get("src")), 0)
        self.cb_src.current(si)
        self.cb_src.grid(row=2, column=1, sticky="ew", padx=6)

        ttk.Label(g, text="Mô tả game:").grid(row=3, column=0, sticky="w", pady=4)
        self.var_ctx = tk.StringVar()
        ttk.Entry(g, textvariable=self.var_ctx).grid(row=3, column=1, sticky="ew", padx=6)
        ttk.Label(g, text="(không bắt buộc, vd: RPG kiếm hiệp, giọng hài)", foreground="#666").grid(row=3, column=2, sticky="w")

        self.var_dry = tk.BooleanVar(value=False)
        ttk.Checkbutton(g, text="Chạy thử miễn phí (không dịch thật, chỉ thêm [VI] trước mỗi câu để kiểm tra)",
                        variable=self.var_dry).grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 0))

        # ---------------------------------------------------------- 3. nút
        f3 = ttk.Frame(root)
        f3.pack(fill="x", **pad)
        self.btn_go = ttk.Button(f3, text="▶  VIỆT HOÁ", style="Big.TButton", command=self.on_go)
        self.btn_go.pack(side="left")
        self.btn_stop = ttk.Button(f3, text="Dừng", command=self.on_stop, state="disabled")
        self.btn_stop.pack(side="left", padx=6)
        self.btn_play = ttk.Button(f3, text="Chơi game", command=self.on_play)
        self.btn_play.pack(side="left", padx=6)
        ttk.Button(f3, text="Mở thư mục", command=self.on_open).pack(side="left")
        ttk.Button(f3, text="Khôi phục bản gốc", command=self.on_restore).pack(side="right")

        # ---------------------------------------------------------- 4. tiến độ
        f4 = ttk.Frame(root)
        f4.pack(fill="both", expand=True, **pad)
        self.pb = ttk.Progressbar(f4, mode="determinate")
        self.pb.pack(fill="x")
        self.lbl_status = ttk.Label(f4, text="Sẵn sàng.")
        self.lbl_status.pack(fill="x", pady=(4, 4))
        self.txt = scrolledtext.ScrolledText(f4, height=12, font=("Consolas", 9), state="disabled", wrap="word")
        self.txt.pack(fill="both", expand=True)

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(100, self.poll)
        threading.Thread(target=self._load_steam, daemon=True).start()
        if self.cfg.get("last_game") and Path(self.cfg["last_game"]).exists():
            self.set_game(self.cfg["last_game"])

    # ============================================================== helpers
    def log(self, msg: str):
        self.q.put(("log", msg))

    def poll(self):
        try:
            while True:
                kind, *a = self.q.get_nowait()
                if kind == "log":
                    self.txt.configure(state="normal")
                    self.txt.insert("end", a[0] + "\n")
                    self.txt.see("end")
                    self.txt.configure(state="disabled")
                elif kind == "progress":
                    d, t = a
                    self.pb["maximum"] = max(1, t)
                    self.pb["value"] = d
                    self.lbl_status.configure(text=f"Đang dịch: {d}/{t} câu")
                elif kind == "status":
                    self.lbl_status.configure(text=a[0])
                elif kind == "steam":
                    self.games = a[0]
                    self.cb_game["values"] = [n for n, _ in self.games] or ["(không tìm thấy game Steam)"]
                elif kind == "confirm":
                    n, cost, ev, box = a
                    box["ok"] = messagebox.askyesno(
                        APP, f"Cần dịch khoảng {n:,} câu.\nChi phí API ước tính: khoảng ${cost:.2f} "
                             f"(có thể chênh lệch).\n\nTiếp tục?")
                    ev.set()
                elif kind == "done":
                    self._set_busy(False)
                    ok, msg = a
                    (messagebox.showinfo if ok else messagebox.showerror)(APP, msg)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def _load_steam(self):
        try:
            self.q.put(("steam", steam_games()))
        except Exception:  # noqa: BLE001
            self.q.put(("steam", []))

    def _set_busy(self, busy: bool, keep_stop=False):
        self.btn_go.configure(state="disabled" if busy else "normal")
        self.btn_stop.configure(state="normal" if busy or keep_stop else "disabled")

    def set_game(self, path):
        self.info = detect(path)
        self.lbl_path.configure(text=str(self.info.root))
        color = "#0a7d32" if self.info.supported else "#c0392b"
        text = f"Engine: {self.info.label}"
        if self.info.supported:
            text += "  ✔ hỗ trợ"
        if self.info.notes:
            text += "  —  " + " ".join(self.info.notes)
        self.lbl_engine.configure(text=text, foreground=color)
        self.cfg["last_game"] = str(self.info.root)

    # ============================================================== events
    def on_pick_steam(self, _e=None):
        i = self.cb_game.current()
        if 0 <= i < len(self.games):
            self.set_game(self.games[i][1])

    def on_browse(self):
        d = filedialog.askdirectory(title="Chọn thư mục chứa game (nơi có file .exe)")
        if d:
            self.set_game(d)

    def on_open(self):
        if self.info:
            if sys.platform == "win32":
                os.startfile(self.info.root)  # noqa: S606
            else:
                subprocess.Popen(["xdg-open", str(self.info.root)])

    def on_play(self):
        if not self.info or not self.info.exe:
            messagebox.showwarning(APP, "Không tìm thấy file .exe của game. Hãy mở game từ Steam.")
            return
        subprocess.Popen([str(self.info.exe)], cwd=str(self.info.root))

    def on_stop(self):
        self.stop_flag.set()
        srv = getattr(self.job, "server", None)
        if srv:
            srv.stop()
            self.log("Đã tắt máy chủ dịch trực tiếp.")
            self.btn_stop.configure(state="disabled")
        self.q.put(("status", "Đang dừng..."))

    def on_close(self):
        srv = getattr(self.job, "server", None)
        if srv and srv.httpd:
            if not messagebox.askyesno(APP, "Máy chủ dịch cho game Unity đang chạy.\n"
                                            "Đóng cửa sổ thì chữ mới trong game sẽ không được dịch nữa. Đóng?"):
                return
            srv.stop()
        self._save_cfg()
        self.root.destroy()

    def _save_cfg(self):
        self.cfg["api_key"] = self.var_key.get().strip()
        self.cfg["model"] = MODELS[self.cb_model.current()][0]
        self.cfg["src"] = SRC_LANGS[self.cb_src.current()][0]
        try:
            save_config(self.cfg)
        except OSError:
            pass

    def _make_translator(self):
        model = MODELS[self.cb_model.current()][0]
        src = SRC_LANGS[self.cb_src.current()][0]
        if self.var_dry.get():
            return make_translator("dummy"), model, src
        key = self.var_key.get().strip()
        if not key:
            raise ValueError("Hãy nhập Claude API key (bấm 'Lấy API key'), hoặc tích 'Chạy thử miễn phí'.")
        os.environ["ANTHROPIC_API_KEY"] = key
        tr = make_translator("claude", model=model, effort="medium", context=self.var_ctx.get().strip(),
                             src_lang="the original language (detect it)" if src == "auto" else src)
        return tr, model, src

    def _confirm(self, n, cost):
        if self.var_dry.get():
            return True
        ev, box = threading.Event(), {}
        self.q.put(("confirm", n, cost, ev, box))
        ev.wait()
        return box.get("ok", False)

    def on_go(self):
        if not self.info:
            messagebox.showwarning(APP, "Hãy chọn game trước.")
            return
        if not self.info.supported:
            messagebox.showerror(APP, f"{self.info.label}: " + (" ".join(self.info.notes) or "chưa hỗ trợ."))
            return
        try:
            tr, model, src = self._make_translator()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(APP, str(e))
            return
        self._save_cfg()
        self.stop_flag.clear()
        self._set_busy(True)
        self.log(f"=== Việt hoá: {self.info.root.name}  ({self.info.label}) ===")

        def work():
            try:
                self.job = make_job(self.info, tr, log=self.log, model=model,
                                    progress=lambda d, t: self.q.put(("progress", d, t)),
                                    should_stop=self.stop_flag.is_set, confirm=self._confirm)
                if hasattr(self.job, "source_lang"):
                    self.job.source_lang = src
                ok = self.job.run()
                if not ok:
                    self.q.put(("status", "Đã huỷ."))
                    self.q.put(("done", True, "Đã huỷ."))
                    return
                if getattr(self.job, "server", None):
                    self.q.put(("status", "Máy chủ dịch đang chạy — mở game để chơi. Giữ cửa sổ này mở."))
                    self.root.after(0, lambda: self._set_busy(False, keep_stop=True))
                    self.q.put(("done", True, "Đã cài xong!\n\nBấm 'Chơi game' (hoặc mở từ Steam). Chữ sẽ được "
                                              "dịch khi hiện lên màn hình.\nGiữ cửa sổ này mở trong lúc chơi."))
                    return
                if self.stop_flag.is_set():
                    self.q.put(("status", "Đã dừng — phần đã dịch vẫn được ghi vào game."))
                    self.q.put(("done", True, "Đã dừng. Phần đã dịch đã được ghi vào game.\n"
                                              "Bấm 'Việt hoá' lần nữa để dịch tiếp."))
                    return
                self.q.put(("status", "Hoàn tất!"))
                self.q.put(("done", True, "Việt hoá xong!\n\nBấm 'Chơi game' (hoặc mở từ Steam) để chơi bằng tiếng Việt."))
            except Exception as e:  # noqa: BLE001
                self.log(traceback.format_exc())
                self.q.put(("status", "Lỗi."))
                self.q.put(("done", False, f"Có lỗi: {e}"))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def on_restore(self):
        if not self.info or not self.info.supported:
            return
        if not messagebox.askyesno(APP, "Gỡ Việt hoá và đưa game về bản gốc?"):
            return
        try:
            make_job(self.info, None, log=self.log).restore()
            messagebox.showinfo(APP, "Đã khôi phục bản gốc.")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(APP, str(e))


def run_headless(argv: list[str]) -> int:
    """VietHoaGame.exe --auto <thư mục game> [--dry] [--restore]  (không mở giao diện)."""
    import anthropic  # noqa: F401  (kiểm tra bản đóng gói có đủ thư viện)

    path = argv[argv.index("--auto") + 1]
    info = detect(path)
    out = open(Path(info.root) / "vntrans_vi.log", "a", encoding="utf-8") if not sys.stdout else sys.stdout
    log = lambda m: print(m, file=out, flush=True)  # noqa: E731
    log(f"{info.root} -> {info.label}")
    if not info.supported:
        log(" ".join(info.notes))
        return 2
    if "--restore" in argv:
        make_job(info, None, log=log).restore()
        return 0
    cfg = load_config()
    if "--dry" in argv:
        tr = make_translator("dummy")
    else:
        if cfg.get("api_key"):
            os.environ.setdefault("ANTHROPIC_API_KEY", cfg["api_key"])
        tr = make_translator("claude", model=cfg.get("model", MODELS[0][0]))
    job = make_job(info, tr, log=log, model=cfg.get("model", MODELS[0][0]))
    ok = job.run()
    if getattr(job, "server", None):
        log("Máy chủ dịch đang chạy. Nhấn Ctrl+C để dừng.")
        threading.Event().wait()
    return 0 if ok else 1


def main():
    if "--auto" in sys.argv:
        sys.exit(run_headless(sys.argv))
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
