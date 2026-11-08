"""Bộ dịch: Claude (Anthropic API) hoặc dummy (để thử quy trình, không tốn tiền)."""
from __future__ import annotations

import json
import sys

from .placeholders import check, protect, restore

SYSTEM_PROMPT = """You are a professional video game localizer translating from {src} into Vietnamese (tiếng Việt).

Rules:
- Produce natural, fluent Vietnamese that a Vietnamese gamer would enjoy; keep the tone, humour and personality of each character. Do not translate word-for-word.
- Use correct Vietnamese diacritics (Unicode NFC).
- Pick pronouns (tôi/ta/tớ/mình/anh/em/cậu/ngươi/ông/bà...) that fit the speaker, the listener and the setting; stay consistent across lines of the same scene.
- Tokens like ⟦0⟧, ⟦1⟧ are game control codes. Copy every token exactly once, unchanged, and place it where it belongs in the Vietnamese sentence.
- Keep line breaks: the translation must contain the same number of "\\n" line breaks as the source unless a line becomes too long.
- UI strings (menus, buttons, item names, stats) must stay short.
- Proper names of people and places are kept unless the glossary says otherwise. Always follow the glossary.
- If a string is not natural language (a file name, code, an ID), return it unchanged.
{extra}"""


class Translator:
    def translate(self, items: list[dict]) -> dict[str, str]:
        """items: [{id, text, ctx}] (text đã được protect). Trả về {id: bản dịch}."""
        raise NotImplementedError


class DummyTranslator(Translator):
    """Không dịch thật: thêm tiền tố [VI] — để kiểm tra quy trình extract/apply."""

    def translate(self, items):
        return {it["id"]: "[VI] " + it["text"] for it in items}


class ClaudeTranslator(Translator):
    def __init__(self, model: str = "claude-opus-5-5", effort: str = "medium",
                 glossary: dict | None = None, context: str = "", src_lang: str = "English"):
        try:
            import anthropic
        except ImportError:
            sys.exit("Cần cài thư viện: pip install anthropic   (và đặt biến môi trường ANTHROPIC_API_KEY)")
        self.anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model = model
        self.effort = effort
        self.glossary = glossary or {}
        extra = ""
        if context:
            extra += f"\nGame information: {context}\n"
        self.system = SYSTEM_PROMPT.format(src=src_lang, extra=extra)

    def _glossary_for(self, items):
        blob = "\n".join(it["text"] for it in items).lower()
        hits = {k: v for k, v in self.glossary.items() if k.lower() in blob}
        if not hits:
            return ""
        return "Glossary (must follow):\n" + "\n".join(f"- {k} => {v}" for k, v in hits.items()) + "\n\n"

    def translate(self, items):
        payload = [{"id": it["id"], "context": it.get("ctx", ""), "text": it["text"]} for it in items]
        user = (self._glossary_for(items)
                + "Translate the `text` of each item into Vietnamese. Items are in game order, so use "
                  "neighbouring lines as context. Return every id exactly once.\n\n"
                + json.dumps(payload, ensure_ascii=False, indent=0))
        schema = {
            "type": "object",
            "properties": {
                "translations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"id": {"type": "string"}, "vi": {"type": "string"}},
                        "required": ["id", "vi"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["translations"],
            "additionalProperties": False,
        }
        kwargs = dict(
            model=self.model,
            max_tokens=64000,
            system=self.system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
        )
        # Nếu bộ lọc an toàn từ chối nhầm (vd. game có cảnh bạo lực), API tự chuyển sang model dự phòng.
        if self.model.startswith(("claude-opus-5", "claude-fable-5", "claude-sonnet-5-5")):
            kwargs["betas"] = ["server-side-fallback-2026-07-01"]
            kwargs["fallbacks"] = "default"
            with self.client.beta.messages.stream(**kwargs) as stream:
                msg = stream.get_final_message()
        else:
            with self.client.messages.stream(**kwargs) as stream:
                msg = stream.get_final_message()
        if msg.stop_reason == "refusal":
            raise RuntimeError("Model từ chối dịch lô này (refusal).")
        if msg.stop_reason == "max_tokens":
            raise RuntimeError("Câu trả lời bị cắt (max_tokens) — giảm --batch.")
        text = next(b.text for b in msg.content if b.type == "text")
        data = json.loads(text)
        return {t["id"]: t["vi"] for t in data["translations"]}


def make_translator(engine: str, **kw) -> Translator:
    if engine == "dummy":
        return DummyTranslator()
    if engine == "claude":
        return ClaudeTranslator(**kw)
    raise SystemExit(f"Engine không hỗ trợ: {engine}")


def translate_texts(tr: Translator, items: list[dict]) -> dict[str, tuple[str, str]]:
    """items: [{id, text(gốc), ctx}] -> {id: (bản dịch, status)}  ('mt' hoặc 'review')."""
    masked = []
    toks = {}
    for it in items:
        m, t = protect(it["text"])
        toks[it["id"]] = t
        masked.append({"id": it["id"], "text": m, "ctx": it.get("ctx", "")})
    res = tr.translate(masked)
    out = {}
    retry = []
    for it in masked:
        v = res.get(it["id"])
        if v is None or check(v, toks[it["id"]]):
            retry.append(it)
        else:
            out[it["id"]] = (restore(v, toks[it["id"]]), "mt")
    # dịch lại từng câu lỗi (thiếu/thừa mã điều khiển) một lần
    for it in retry:
        try:
            v = tr.translate([it]).get(it["id"])
        except Exception as e:  # noqa: BLE001
            print(f"  ! lỗi khi dịch lại {it['id']}: {e}", file=sys.stderr)
            v = None
        if v is None:
            continue
        errs = check(v, toks[it["id"]])
        out[it["id"]] = (restore(v, toks[it["id"]]), "review" if errs else "mt")
    return out
