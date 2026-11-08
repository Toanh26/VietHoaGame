"""Vòng lặp dịch dùng chung cho dòng lệnh và giao diện."""
from __future__ import annotations

import sys
import time
from typing import Callable

from .project import Entry, Project
from .translators import Translator, translate_texts

# giá USD / 1 triệu token (input, output)
PRICES = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}


def pending(proj: Project, glossary: dict | None = None, retranslate: bool = False,
            file_filter: str | None = None) -> dict[str, list[Entry]]:
    """Các câu gốc còn phải dịch (đã gộp trùng). Đồng thời điền sẵn từ thuật ngữ / bộ nhớ dịch."""
    glossary = glossary or {}
    for e in proj.entries:
        if retranslate and e.status != "ok":
            e.tgt = ""
        if not e.tgt and e.src.strip() in glossary:
            e.tgt, e.status = glossary[e.src.strip()], "ok"
    tm = proj.memory()
    todo: dict[str, list[Entry]] = {}
    for e in proj.entries:
        if e.tgt:
            continue
        if e.src in tm:
            e.tgt, e.status = tm[e.src], "mt"
            continue
        if file_filter and file_filter not in e.file:
            continue
        todo.setdefault(e.src, []).append(e)
    return todo


def estimate_cost(todo: dict[str, list[Entry]], model: str) -> float:
    """Ước tính thô chi phí (USD)."""
    chars = sum(len(s) for s in todo)
    n = len(todo)
    in_tok = chars / 3 + n * 25 + (n / 40 + 1) * 700
    out_tok = chars / 2 * 1.3 + n * 15 + chars / 2  # bản dịch + phần suy nghĩ
    pin, pout = PRICES.get(model, (4.0, 20.0))
    return (in_tok * pin + out_tok * pout) / 1e6


def translate_project(proj: Project, tr: Translator, save_path, *, glossary=None, batch: int = 40,
                      limit: int | None = None, retranslate: bool = False, file_filter: str | None = None,
                      progress: Callable[[int, int], None] | None = None,
                      log: Callable[[str], None] = print,
                      should_stop: Callable[[], bool] | None = None) -> int:
    todo = pending(proj, glossary, retranslate, file_filter)
    srcs = list(todo)
    if limit:
        srcs = srcs[:limit]
    total = len(srcs)
    log(f"Cần dịch {total} câu khác nhau ({sum(len(todo[s]) for s in srcs)} vị trí).")
    done = 0
    if progress:
        progress(0, total)
    for b in range(0, total, batch):
        if should_stop and should_stop():
            log("Đã dừng theo yêu cầu. Lần sau chạy lại sẽ dịch tiếp.")
            break
        chunk = srcs[b: b + batch]
        items = [{"id": str(i), "text": s, "ctx": todo[s][0].ctx} for i, s in enumerate(chunk)]
        res = None
        for attempt in range(3):
            try:
                res = translate_texts(tr, items)
                break
            except Exception as e:  # noqa: BLE001
                log(f"  ! lỗi lô {b // batch + 1} (lần {attempt + 1}): {e}")
                if "authentication" in str(e).lower() or "api_key" in str(e).lower() or "401" in str(e):
                    raise
                time.sleep(2 ** attempt * 2)
        if res:
            for it in items:
                if it["id"] in res:
                    tgt, st = res[it["id"]]
                    for e in todo[it["text"]]:
                        e.tgt, e.status = tgt, st
                    done += 1
        proj.save(save_path)  # lưu sau mỗi lô -> dừng giữa chừng vẫn giữ kết quả
        if progress:
            progress(min(b + batch, total), total)
    return done
