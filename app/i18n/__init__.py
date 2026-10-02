"""Minimal UI translation layer. All user-facing strings live in JSON files here, not in code."""

import json
from pathlib import Path

_DIR = Path(__file__).parent
_DEFAULT_LOCALE = "sk"
_catalogs: dict[str, dict[str, str]] = {}


def _load(locale: str) -> dict[str, str]:
    if locale not in _catalogs:
        path = _DIR / f"{locale}.json"
        _catalogs[locale] = json.loads(path.read_text(encoding="utf-8"))
    return _catalogs[locale]


def t(key: str, /, locale: str = _DEFAULT_LOCALE, **kwargs: object) -> str:
    """Translate `key`; falls back to the key itself so a missing text is visible, not fatal.

    `key` is positional-only so that messages may themselves use a `{key}` placeholder.
    """
    text = _load(locale).get(key, key)
    return text.format(**kwargs) if kwargs else text
