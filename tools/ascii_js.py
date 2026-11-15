"""Rewrite non-ASCII characters in JS files as \\uXXXX escapes (all of ours are
inside string literals), so the browser decodes the same characters whatever
charset it assumes. Run: python tools/ascii_js.py static/app.js static/label.js"""
import sys
from pathlib import Path

for name in sys.argv[1:]:
    p = Path(name)
    text = p.read_text(encoding="utf-8-sig")
    out = "".join(c if ord(c) < 128 else "\\u%04x" % ord(c) for c in text)
    p.write_text(out, encoding="utf-8", newline="")
    print(f"{name}: {sum(1 for c in text if ord(c) >= 128)} characters escaped")
