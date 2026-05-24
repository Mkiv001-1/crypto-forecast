"""Shared security helpers."""


def mask_secret(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "<empty>"
    if len(text) <= 8:
        return "***"
    return f"{text[:4]}...{text[-4:]}"
