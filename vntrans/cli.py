"""Giao diện dòng lệnh vntrans.

  vntrans extract   <thư mục game>            -> tạo/cập nhật project.json
  vntrans translate                            -> dịch máy các câu chưa dịch
  vntrans export-csv / import-csv              -> dịch/sửa tay bằng Excel, Google Sheets
  vntrans apply     <thư mục game> -o <out>    -> ghi bản dịch ra thư mục game đã Việt hoá
  vntrans stats | check | export-dict
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .adapters import ADAPTERS, AUTO, iter_files, pick
from .placeholders import codes_of
from .project import Entry, Project, load_glossary, make_id
from .pipeline import translate_project
from .translators import make_translator


def _opts(a) -> dict:
    return {k: getattr(a, k, None) for k in ("wrap", "renpy_lang", "json_keys", "src_col", "dst_col", "retranslate")}


def cmd_extract(a):
    root = Path(a.game_dir).resolve()
    proj_path = Path(a.project)
    proj = Project.load(proj_path) if proj_path.exists() else Project()
    proj.game_dir = str(root)
    proj.source_lang = a.source_lang or proj.source_lang
    names = AUTO if a.adapter == "auto" else [a.adapter]
    opts = _opts(a)
    proj.settings.update({k: v for k, v in opts.items() if v is not None})
    entries, per_file = [], {}
    for path, rel in iter_files(root, a.include):
        ad = pick(path, root, names, opts)
        if not ad:
            continue
        try:
            found = ad.extract(path)
        except Exception as e:  # noqa: BLE001
            print(f"  ! bỏ qua {rel}: {e}", file=sys.stderr)
            continue
        for loc, src, ctx in found:
            entries.append(Entry(id=make_id(rel, loc), file=rel, adapter=ad.name, loc=loc, src=src, ctx=ctx))
        if found:
            per_file[rel] = (ad.name, len(found))
    if not entries:
        print("Không tìm thấy văn bản nào. Kiểm tra --adapter / --include (xem README).")
        return 1
    added, kept, changed = proj.merge(entries)
    proj.save(proj_path)
    for rel, (ad, n) in per_file.items():
        print(f"  [{ad}] {rel}: {n}")
    s = proj.stats()
    print(f"\nĐã lưu {proj_path}: {s['total']} câu ({s['unique_src']} câu khác nhau). "
          f"Mới {added}, giữ bản dịch {kept}, gốc thay đổi {changed}.")
    return 0


def cmd_translate(a):
    proj = Project.load(a.project)
    glossary = load_glossary(a.glossary)
    kw = {}
    if a.engine == "claude":
        kw = dict(model=a.model, effort=a.effort, glossary=glossary, context=a.context or "",
                  src_lang=a.source_lang or proj.source_lang)
    tr = make_translator(a.engine, **kw)

    done = translate_project(proj, tr, a.project, glossary=glossary, batch=a.batch, limit=a.limit,
                             retranslate=a.retranslate, file_filter=a.file,
                             progress=lambda d, t: print(f"  {d}/{t}"))
    s = proj.stats()
    print(f"Xong: dịch thêm {done}. Tổng {s['translated']}/{s['total']}, cần xem lại {s['review']}.")
    return 0


def cmd_apply(a):
    proj = Project.load(a.project)
    root = Path(a.game_dir or proj.game_dir).resolve()
    out = Path(a.output).resolve() if a.output else None
    if not out and not a.inplace:
        sys.exit("Cần -o <thư mục xuất> hoặc --inplace (ghi đè, có sao lưu .bak).")
    opts = dict(proj.settings)
    opts.update({k: v for k, v in _opts(a).items() if v is not None})
    by_file: dict[str, list[Entry]] = {}
    for e in proj.entries:
        if e.tgt or a.keep_empty:
            by_file.setdefault(e.file, []).append(e)
    if out and out != root:
        if out.exists() and any(out.iterdir()) and not a.force:
            sys.exit(f"{out} đã có dữ liệu. Thêm --force để ghi vào đó.")
        if a.copy_all:
            print(f"Sao chép toàn bộ game sang {out} ...")
            shutil.copytree(root, out, dirs_exist_ok=True)
    n_files = n_items = 0
    for rel, ents in sorted(by_file.items()):
        src_path = root / rel
        if not src_path.exists():
            print(f"  ! không thấy {rel}", file=sys.stderr)
            continue
        dst = (out / rel) if out else src_path
        if not out:
            bak = src_path.with_name(src_path.name + ".bak")
            if not bak.exists():
                shutil.copy2(src_path, bak)
            src_path = bak  # luôn đọc từ bản gốc
        ad = ADAPTERS[ents[0].adapter](opts)
        ad.apply(src_path, dst, [(e.loc, e.tgt or e.src) for e in ents])
        n_files += 1
        n_items += len(ents)
    print(f"Đã ghi {n_items} bản dịch vào {n_files} file -> {out or root}")
    if out and not a.copy_all:
        print("(Chỉ các file đã dịch được ghi. Chép chúng đè lên thư mục game, hoặc dùng --copy-all.)")
    return 0


def cmd_csv_out(a):
    n = Project.load(a.project).export_csv(a.output, a.untranslated)
    print(f"Đã xuất {n} dòng -> {a.output}  (sửa cột 'vietnamese', rồi chạy import-csv)")


def cmd_csv_in(a):
    p = Project.load(a.project)
    n = p.import_csv(a.input)
    p.save(a.project)
    print(f"Đã cập nhật {n} dòng.")


def cmd_stats(a):
    s = Project.load(a.project).stats()
    pct = 100 * s["translated"] / max(1, s["total"])
    print(json.dumps(s, ensure_ascii=False, indent=1))
    print(f"Tiến độ: {pct:.1f}%")


def cmd_check(a):
    """Kiểm tra lỗi: thiếu mã điều khiển, dòng quá dài..."""
    p = Project.load(a.project)
    bad = 0
    for e in p.entries:
        if not e.tgt:
            continue
        problems = []
        if codes_of(e.src) != codes_of(e.tgt):
            problems.append(f"mã điều khiển khác: {codes_of(e.src)} vs {codes_of(e.tgt)}")
        if a.max_line and any(len(ln) > a.max_line for ln in e.tgt.split("\n")):
            problems.append(f"có dòng dài hơn {a.max_line} ký tự")
        if problems:
            bad += 1
            e.status = "review"
            print(f"[{e.id}] {e.file}\n  gốc: {e.src!r}\n  dịch: {e.tgt!r}\n  -> " + "; ".join(problems))
    p.save(a.project)
    print(f"\n{bad} câu cần xem lại (đã đánh dấu status=review).")


def cmd_dict(a):
    """Xuất từ điển gốc->dịch cho plugin VietTranslate.js (RPG Maker) hoặc dùng ở runtime."""
    tm = Project.load(a.project).memory()
    Path(a.output).write_text(json.dumps(tm, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"Đã xuất {len(tm)} mục -> {a.output}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="vntrans", description="Bộ công cụ Việt hoá game")
    ap.add_argument("-p", "--project", default="project.json", help="file dự án (mặc định project.json)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--wrap", type=int, help="RPG Maker: tự xuống dòng khi dòng dài hơn N ký tự")
        sp.add_argument("--renpy-lang", help="Ren'Py: tên thư mục ngôn ngữ trong game/tl (vd. vietnamese)")
        sp.add_argument("--json-keys", help="json: chỉ dịch các khoá này (vd. text,name,description)")
        sp.add_argument("--src-col", help="csv: cột nguồn (mặc định en)")
        sp.add_argument("--dst-col", help="csv: cột đích (mặc định vi)")

    s = sub.add_parser("extract", help="quét game, lấy văn bản cần dịch")
    s.add_argument("game_dir")
    s.add_argument("--adapter", default="auto", choices=["auto", *ADAPTERS])
    s.add_argument("--include", action="append", help="glob đường dẫn tương đối, vd. 'www/data/*.json' (lặp lại được)")
    s.add_argument("--source-lang", help="ngôn ngữ gốc, vd. English, Japanese, Chinese")
    s.add_argument("--retranslate", action="store_true", help="xunity/csv: lấy cả dòng đã có bản dịch")
    common(s)
    s.set_defaults(fn=cmd_extract)

    s = sub.add_parser("translate", help="dịch máy các câu chưa dịch")
    s.add_argument("--engine", default="claude", choices=["claude", "dummy"])
    s.add_argument("--model", default="claude-opus-5-5")
    s.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    s.add_argument("--batch", type=int, default=40, help="số câu mỗi lần gọi API")
    s.add_argument("--glossary", help="CSV thuật ngữ: source,vietnamese")
    s.add_argument("--context", help="mô tả game: thể loại, bối cảnh, xưng hô...")
    s.add_argument("--source-lang")
    s.add_argument("--limit", type=int, help="chỉ dịch N câu (để thử)")
    s.add_argument("--file", help="chỉ dịch các file có đường dẫn chứa chuỗi này")
    s.add_argument("--retranslate", action="store_true", help="dịch lại cả câu đã dịch máy (giữ câu status=ok)")
    s.set_defaults(fn=cmd_translate)

    s = sub.add_parser("apply", help="ghi bản dịch vào game")
    s.add_argument("game_dir", nargs="?")
    s.add_argument("-o", "--output", help="thư mục xuất (khuyến nghị)")
    s.add_argument("--inplace", action="store_true", help="ghi đè thẳng vào game (tạo file .bak)")
    s.add_argument("--copy-all", action="store_true", help="chép toàn bộ game sang thư mục xuất trước")
    s.add_argument("--force", action="store_true")
    s.add_argument("--keep-empty", action="store_true", help=argparse.SUPPRESS)
    common(s)
    s.set_defaults(fn=cmd_apply)

    s = sub.add_parser("export-csv", help="xuất bảng để dịch/sửa tay")
    s.add_argument("-o", "--output", default="translation.csv")
    s.add_argument("--untranslated", action="store_true", help="chỉ xuất câu chưa dịch")
    s.set_defaults(fn=cmd_csv_out)

    s = sub.add_parser("import-csv", help="nhập lại bảng đã sửa")
    s.add_argument("input")
    s.set_defaults(fn=cmd_csv_in)

    s = sub.add_parser("stats", help="xem tiến độ")
    s.set_defaults(fn=cmd_stats)

    s = sub.add_parser("check", help="kiểm tra lỗi bản dịch")
    s.add_argument("--max-line", type=int, default=0, help="cảnh báo dòng dài hơn N ký tự")
    s.set_defaults(fn=cmd_check)

    s = sub.add_parser("export-dict", help="xuất từ điển JSON gốc->dịch (cho plugin runtime)")
    s.add_argument("-o", "--output", default="vi_dictionary.json")
    s.set_defaults(fn=cmd_dict)

    a = ap.parse_args(argv)
    for k in ("wrap", "renpy_lang", "json_keys", "src_col", "dst_col", "retranslate"):
        if not hasattr(a, k):
            setattr(a, k, None)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(a.fn(a) or 0)


if __name__ == "__main__":
    main()
