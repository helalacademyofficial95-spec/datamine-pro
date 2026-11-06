"""Extract the facts we need from an HTML page using only html.parser."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin

MAX_TEXT_CHARS = 300_000


@dataclass
class PageFacts:
    url: str
    title: str = ""
    text: str = ""
    links: list[tuple[str, str]] = field(default_factory=list)  # (absolute url, anchor text)
    meta: dict[str, str] = field(default_factory=dict)
    resources: list[str] = field(default_factory=list)  # script/link/img sources
    jsonld_types: set[str] = field(default_factory=set)
    has_form: bool = False


def _walk_types(node: object, out: set[str]) -> None:
    if isinstance(node, dict):
        value = node.get("@type")
        if isinstance(value, str):
            out.add(value)
        elif isinstance(value, list):
            out.update(v for v in value if isinstance(v, str))
        for child in node.values():
            _walk_types(child, out)
    elif isinstance(node, list):
        for child in node:
            _walk_types(child, out)


class _Collector(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.facts = PageFacts(url=base_url)
        self._text: list[str] = []
        self._title: list[str] = []
        self._ld: list[str] = []
        self._in_title = False
        self._in_ld = False
        self._skip = 0
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []
        self._size = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "a" and a.get("href"):
            self._anchor_href = urljoin(self.base_url, a["href"].strip())
            self._anchor_text = [a.get("aria-label", ""), a.get("title", "")]
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or "").lower()
            if key and "content" in a:
                self.facts.meta[key] = a["content"]
        elif tag == "script":
            if a.get("type", "").lower() == "application/ld+json":
                self._in_ld = True
            if a.get("src"):
                self.facts.resources.append(urljoin(self.base_url, a["src"]))
            self._skip += 1
        elif tag == "style" or tag == "noscript":
            self._skip += 1
        elif tag == "link" and a.get("href"):
            self.facts.resources.append(urljoin(self.base_url, a["href"]))
        elif tag == "img" and a.get("src"):
            self.facts.resources.append(urljoin(self.base_url, a["src"]))
        elif tag == "form":
            self.facts.has_form = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor_href:
            label = " ".join(p for p in self._anchor_text if p).strip()
            self.facts.links.append((self._anchor_href, " ".join(label.split())))
            self._anchor_href = None
            self._anchor_text = []
        elif tag == "title":
            self._in_title = False
        elif tag == "script":
            if self._in_ld:
                self._in_ld = False
            self._skip = max(0, self._skip - 1)
        elif tag in ("style", "noscript"):
            self._skip = max(0, self._skip - 1)

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title.append(data)
        if self._in_ld:
            self._ld.append(data)
            return
        if self._skip:
            return
        if self._anchor_href is not None:
            self._anchor_text.append(data)
        if self._size < MAX_TEXT_CHARS:
            self._text.append(data)
            self._size += len(data)

    def result(self) -> PageFacts:
        self.facts.title = " ".join("".join(self._title).split())
        self.facts.text = " ".join(" ".join(self._text).split())
        raw = "".join(self._ld)
        for chunk in _split_json_blobs(raw):
            try:
                _walk_types(json.loads(chunk), self.facts.jsonld_types)
            except ValueError:
                continue
        return self.facts


def _split_json_blobs(raw: str) -> list[str]:
    """One <script> may hold one JSON document; several scripts were concatenated, so split on '}{' boundaries."""
    raw = raw.strip()
    if not raw:
        return []
    if "}{" not in raw and "]{" not in raw and "}[" not in raw:
        return [raw]
    parts: list[str] = []
    depth = 0
    start = 0
    in_str = False
    esc = False
    for i, ch in enumerate(raw):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                parts.append(raw[start : i + 1])
                start = i + 1
    return [p for p in parts if p.strip()]


def parse_html(html: str, url: str) -> PageFacts:
    parser = _Collector(url)
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # malformed markup must never crash a batch
        pass
    return parser.result()
