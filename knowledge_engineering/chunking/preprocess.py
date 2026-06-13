"""Text normalization helpers used before chunking."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any


_WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\ufeff", "").strip()
    text = _WHITESPACE_RE.sub(" ", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


def join_non_empty(parts: Iterable[Any], separator: str = "\n") -> str:
    cleaned = [clean_text(part) for part in parts]
    return separator.join(part for part in cleaned if part)


def split_sentences(text: str) -> list[str]:
    cleaned = clean_text(text)
    if not cleaned:
        return []
    return [part.strip() for part in _SENTENCE_BOUNDARY_RE.split(cleaned) if part.strip()]


def split_markdown_sections(text: str) -> list[tuple[str, str]]:
    """Return (breadcrumb, body) sections from a Markdown-like CMS document."""

    sections: list[tuple[str, str]] = []
    breadcrumb: list[str] = []
    current_title = "Document"
    current_lines: list[str] = []

    def flush() -> None:
        body = clean_text("\n".join(current_lines))
        if body:
            sections.append((current_title, body))

    for line in text.splitlines():
        match = _HEADING_RE.match(line.strip())
        if not match:
            current_lines.append(line)
            continue

        flush()
        level = len(match.group(1))
        title = clean_text(match.group(2))
        breadcrumb[:] = breadcrumb[: level - 1]
        breadcrumb.append(title)
        current_title = " > ".join(breadcrumb)
        current_lines = []

    flush()
    return sections


def make_context_prefix(title: str, section: str | None = None) -> str:
    title = clean_text(title)
    section = clean_text(section)
    if title and section:
        return f"{title} - {section}."
    if title:
        return f"{title}."
    if section:
        return f"{section}."
    return ""
