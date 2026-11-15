"""Static site: ASCII-only source (no encoding round-trip can garble icons) and every element
id the script looks up exists in the page. No network, no browser."""

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"
FILES = ["index.html", "style.css", "app.js", "label.html", "label.js", "labels.css"]


def test_static_sources_are_ascii():
    for name in FILES:
        text = (STATIC / name).read_text(encoding="utf-8")
        bad = sorted({hex(ord(c)) for c in text if ord(c) > 127})
        assert not bad, f"{name} has non-ASCII characters {bad}; write symbols as \\u escapes or HTML entities"


def test_every_id_the_script_uses_exists_in_the_page():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    ids = set(re.findall(r'\bid="([^"]+)"', html))
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    used = set(re.findall(r'\$\("([^"]+)"\)', js))
    missing = sorted(used - ids)
    assert not missing, f"app.js looks up ids that index.html does not have: {missing}"


def test_page_has_no_inline_script_or_style_so_a_strict_csp_works():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "Content-Security-Policy" in html
    assert not re.search(r"<script(?![^>]*\bsrc=)", html), "inline <script> would be blocked by the CSP"
    assert "<style" not in html and ' style="' not in html, "inline styles would be blocked by the CSP"
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js, "dynamic text must never be inserted as HTML"
