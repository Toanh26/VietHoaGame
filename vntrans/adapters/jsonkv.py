"""JSON chung: dịch mọi giá trị chuỗi (file ngôn ngữ kiểu en.json, locale/*.json...).

Không bật tự động — dùng:  --adapter json --include "lang/en.json"
Tuỳ chọn --json-keys "text,name,desc" để chỉ dịch các khoá có tên đó.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .base import Adapter, json_set, read_text

_LOOKS_LIKE_CODE = re.compile(r"^(?:[\w./\\-]+\.(?:png|jpg|ogg|wav|mp3|json|js|ttf|otf)|#[0-9a-fA-F]{3,8}|[A-Z0-9_]+|https?://\S+)$")


class JsonAdapter(Adapter):
    name = "json"
    description = "JSON chung (mọi giá trị chuỗi)"

    def match(self, path, root):
        return path.suffix.lower() == ".json"

    def extract(self, path: Path):
        data = json.loads(read_text(path)[0])
        keys = {k.strip() for k in (self.opts.get("json_keys") or "").split(",") if k.strip()}
        out = []

        def walk(node, p):
            if isinstance(node, dict):
                for k, v in node.items():
                    walk(v, p + [k])
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, p + [i])
            elif isinstance(node, str) and node.strip():
                last = next((x for x in reversed(p) if isinstance(x, str)), "")
                if keys and last not in keys:
                    return
                if _LOOKS_LIKE_CODE.match(node.strip()):
                    return
                out.append(({"p": p}, node, "json " + ".".join(map(str, p))))

        walk(data, [])
        return out

    def apply(self, path: Path, out_path: Path, items):
        text, _ = read_text(path)
        data = json.loads(text)
        for loc, tgt in items:
            json_set(data, loc["p"], tgt)
        indent = 2 if "\n" in text.strip() else None
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")
