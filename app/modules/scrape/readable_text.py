"""Readable text extraction from HTML."""

from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
from typing import List

from app.core.textnorm import normalize_whitespace


_SKIP_TAGS = {"script", "style", "noscript", "svg", "head"}
_BLOCK_TAGS = {
    "p",
    "div",
    "br",
    "hr",
    "li",
    "section",
    "article",
    "header",
    "footer",
    "blockquote",
    "pre",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._parts: List[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if data:
            self._parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._skip_depth > 0:
            return
        self._parts.append(unescape(f"&{name};"))

    def handle_charref(self, name: str) -> None:
        if self._skip_depth > 0:
            return
        self._parts.append(unescape(f"&#{name};"))

    def text(self) -> str:
        return "".join(self._parts)


def extract(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return normalize_whitespace(parser.text())
