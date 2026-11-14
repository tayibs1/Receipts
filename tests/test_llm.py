"""Pure parsing helpers in llm.py: no network."""

import pytest

import llm


def test_extract_json_ignores_text_after_the_object():
    # seen on the real API: a valid object followed by extra text
    assert llm._extract_json('{"verdict": "supported"}\n\nNote: done.') == {"verdict": "supported"}


def test_extract_json_handles_code_fences_and_leading_text():
    assert llm._extract_json('Here you go:\n```json\n{"query": "a b"}\n```') == {"query": "a b"}


def test_extract_json_rejects_non_objects():
    with pytest.raises(ValueError):
        llm._extract_json("no json here")


def test_excerpt_keeps_the_window_that_mentions_the_claim():
    filler = "lorem ipsum dolor sit amet " * 400
    content = filler + " Acme raised 105 million in seed funding. " + filler
    out = llm.excerpt(content, "Acme raised 105 million seed", limit=500)
    assert "105 million" in out and len(out) == 500
