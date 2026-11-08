"""Bảo vệ mã điều khiển (control code) khỏi bị dịch/làm hỏng.

Ví dụ: RPG Maker  \\C[2] \\N[1] \\V[3] \\! \\.   Ren'Py  {b} {/b} [player_name]
printf  %s %d %(name)s   .NET/Unity  {0} {name}   HTML/rich text  <color=red> </b>

Trước khi gửi đi dịch, mỗi mã được thay bằng token ⟦n⟧; sau khi dịch xong thì khôi phục.
"""
from __future__ import annotations

import re

_PATTERNS = [
    r"\\[A-Za-z]+\[[^\]]*\]",          # \C[2], \N[1], \V[10], \FS[24]
    r"\\[A-Za-z]+<[^>]*>",              # \FN<Arial> (Yanfly)
    r"\\[{}\\|.!><^$GgIi]",             # \{ \} \\ \| \. \! \> \< \^ \$ \G
    r"\{[^{}\n]*\}",                     # {b} {/b} {0} {name} {w=0.5}
    r"\[[^\[\]\n]*\]",                   # [player] (Ren'Py interpolation)
    r"%(?:\([^)]+\))?[-+ 0#]*\d*(?:\.\d+)?[sdifxXeEgGcr%]",  # printf
    r"</?[A-Za-z][^<>\n]*>",             # <color=#fff> </b> <br>
    r"\$\{[^}]*\}",                      # ${var}
]
_RE = re.compile("|".join(f"(?:{p})" for p in _PATTERNS))
_TOKEN_RE = re.compile(r"⟦(\d+)⟧")


def protect(text: str) -> tuple[str, list[str]]:
    tokens: list[str] = []

    def repl(m: re.Match) -> str:
        tokens.append(m.group(0))
        return f"⟦{len(tokens) - 1}⟧"

    return _RE.sub(repl, text), tokens


def restore(text: str, tokens: list[str]) -> str:
    return _TOKEN_RE.sub(lambda m: tokens[int(m.group(1))] if int(m.group(1)) < len(tokens) else m.group(0), text)


def check(masked_translation: str, tokens: list[str]) -> list[str]:
    """Trả về danh sách lỗi (rỗng = ổn)."""
    found = [int(x) for x in _TOKEN_RE.findall(masked_translation)]
    errors = []
    for i in range(len(tokens)):
        c = found.count(i)
        if c == 0:
            errors.append(f"thiếu mã {tokens[i]!r}")
        elif c > 1:
            errors.append(f"mã {tokens[i]!r} bị lặp")
    for i in found:
        if i >= len(tokens):
            errors.append(f"token lạ ⟦{i}⟧")
    return errors


def codes_of(text: str) -> list[str]:
    return sorted(_RE.findall(text))
