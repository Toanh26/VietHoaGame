# vntrans - Viet hoa tu dong cho Ren'Py.
# Xoa file nay (va zz_vntrans.rpyc, vntrans_vi.json) de tro ve ban goc.
# Trong game: nhan F8 de bat/tat tieng Viet.

init -999 python:
    import io as _vn_io
    import json as _vn_json
    import os as _vn_os
    import re as _vn_re

    vntrans_dict = {}
    vntrans_values = set()
    vntrans_logged = set()
    _vn_dict_path = _vn_os.path.join(config.gamedir, "vntrans_vi.json")
    if _vn_os.path.exists(_vn_dict_path):
        try:
            with _vn_io.open(_vn_dict_path, "r", encoding="utf-8") as _vn_f:
                vntrans_dict = _vn_json.load(_vn_f)
            vntrans_values = set(vntrans_dict.values())
        except Exception:
            vntrans_dict = {}
    _vn_viet = _vn_re.compile(u"[ăâđêôơưẠ-ỹĂÂĐÊÔƠƯ]")
    _vn_letters = _vn_re.compile(r"[^\W\d_]", _vn_re.UNICODE)

    def vntrans_on():
        return not persistent.vntrans_off

    def _vn_log_missing(s):
        try:
            if s in vntrans_logged or s in vntrans_values or len(s) > 400 or len(vntrans_logged) > 5000:
                return
            if not _vn_letters.search(s) or _vn_viet.search(s):
                return
            vntrans_logged.add(s)
            with _vn_io.open(_vn_os.path.join(config.gamedir, "vntrans_missing.txt"), "a", encoding="utf-8") as f:
                f.write(_vn_json.dumps(s) + u"\n")
        except Exception:
            pass

    def vntrans_toggle():
        persistent.vntrans_off = not persistent.vntrans_off
        renpy.notify(u"Tiếng Việt: " + (u"TẮT" if persistent.vntrans_off else u"BẬT"))
        renpy.restart_interaction()

init 999 python:
    # ---------------- chế độ quét: liệt kê câu thoại / lựa chọn rồi thoát
    _vn_flag = _vn_os.path.join(config.gamedir, "vntrans_scan.flag")
    _vn_out_path = None
    if _vn_os.path.exists(_vn_flag):
        # an toàn: xoá cờ NGAY, và bỏ qua cờ cũ (> 10 phút) để game không bao giờ bị kẹt ở chế độ quét
        try:
            import time as _vn_time
            with _vn_io.open(_vn_flag, "r", encoding="utf-8") as _vn_f:
                _vn_out_path = _vn_f.read().strip()
            if _vn_time.time() - _vn_os.path.getmtime(_vn_flag) > 600:
                _vn_out_path = None
        except Exception:
            _vn_out_path = None
        try:
            _vn_os.remove(_vn_flag)
        except Exception:
            pass
    if _vn_out_path:
        _vn_items = []
        _vn_seen = set()
        for _vn_n in renpy.game.script.all_stmts:
            _vn_fn = (getattr(_vn_n, "filename", "") or "").replace("\\", "/")
            if _vn_fn.startswith("renpy/") or "/renpy/" in _vn_fn or "/common/" in _vn_fn:
                continue
            try:
                if isinstance(_vn_n, renpy.ast.Say):
                    _vn_t = _vn_n.what
                    if _vn_t and _vn_t not in _vn_seen:
                        _vn_seen.add(_vn_t)
                        _vn_items.append({"t": _vn_t, "who": _vn_n.who or "", "f": _vn_fn, "l": _vn_n.linenumber, "k": "say"})
                elif isinstance(_vn_n, renpy.ast.Menu):
                    for _vn_it in _vn_n.items:
                        _vn_t = _vn_it[0]
                        if _vn_t and _vn_t not in _vn_seen:
                            _vn_seen.add(_vn_t)
                            _vn_items.append({"t": _vn_t, "f": _vn_fn, "l": _vn_n.linenumber, "k": "menu"})
            except Exception:
                pass
        try:
            with _vn_io.open(_vn_out_path + ".tmp", "w", encoding="utf-8") as _vn_f:
                _vn_f.write(u"" + _vn_json.dumps(_vn_items))
            _vn_os.rename(_vn_out_path + ".tmp", _vn_out_path)
        except Exception:
            pass
        _vn_os._exit(0)

    # ---------------- thay chữ khi chơi
    def _vn_say_filter(s, _old=config.say_menu_text_filter):
        if _old is not None:
            s = _old(s)
        if vntrans_on():
            return vntrans_dict.get(s, s)
        return s
    config.say_menu_text_filter = _vn_say_filter

    def _vn_replace_text(s, _old=config.replace_text):
        if _old is not None:
            s = _old(s)
        if not vntrans_on():
            return s
        t = vntrans_dict.get(s)
        if t is not None:
            return t
        _vn_log_missing(s)
        return s
    config.replace_text = _vn_replace_text

    config.underlay.append(renpy.Keymap(K_F8=vntrans_toggle))

    # ---------------- font có dấu tiếng Việt
    _vn_font_file = _vn_os.path.join(config.gamedir, "vntrans_font.txt")
    if _vn_os.path.exists(_vn_font_file):
        try:
            with _vn_io.open(_vn_font_file, "r", encoding="utf-8") as _vn_f:
                _vn_font = _vn_f.read().strip()
            for _vn_name in ("text_font", "name_text_font", "interface_text_font", "button_text_font", "choice_button_text_font"):
                if hasattr(gui, _vn_name):
                    setattr(gui, _vn_name, _vn_font)
            for _vn_s in list(renpy.style.styles.values()):
                try:
                    _vn_s.font = _vn_font
                except Exception:
                    pass
        except Exception:
            pass
