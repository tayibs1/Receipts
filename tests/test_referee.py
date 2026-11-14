import pytest

from referee import (
    Budget, BudgetExceeded, Claim, Decision, Proposal, Result,
    SUPPORTED, CONTRADICTED, UNVERIFIED, FORWARD,
    check_paragraph, decide, norm_url, quote_in_content, specifics,
)


def res(content, url="https://news.example.com/acme", name="Acme news"):
    return Result(name=name, url=url, content=content)


def run(claim_text, verdict, quote, content, entity="Acme", url="news.example.com/acme"):
    claim = Claim("c1", claim_text, entity)
    prop = Proposal(verdict, url, quote)
    return decide(claim, prop, [res(content)])


# --------------------------------------------- the month "May" is not the word "may"

@pytest.mark.parametrize("quote", [
    "Acme released Orion in May 2025 after a long beta",
    "Acme released Orion on 5 May after a long beta",
    "Acme released Orion on May 5 after a long beta",
])
def test_month_may_does_not_trigger_the_hedge_guard(quote):
    d = run("Acme released Orion in May 2025" if "2025" in quote else "Acme released Orion on May 5",
            SUPPORTED, quote, quote + ".")
    assert d.verdict == SUPPORTED, d.rules


def test_modal_may_still_blocks_a_fact_claim():
    quote = "Acme may release Orion after a long beta"
    d = run("Acme released Orion after a long beta", SUPPORTED, quote, quote + ".")
    assert d.verdict == UNVERIFIED and d.rules[-1][0] == "R7"


# ------------------------------------- fixes from the first real-data checkpoint (#8)

def test_floor_claim_is_met_by_a_larger_figure():
    q = "Acme has raised about $25 billion in equity across 13 rounds"
    d = run("Acme has raised well over $10 billion in total", SUPPORTED, q, q + ".")
    assert d.verdict == SUPPORTED, d.rules


def test_floor_claim_is_not_met_by_a_smaller_figure():
    q = "Acme has raised about $4 billion in equity across 3 rounds"
    d = run("Acme has raised well over $10 billion in total", SUPPORTED, q, q + ".")
    assert d.verdict == UNVERIFIED and d.rules[-1][0] == "R2"


def test_floor_never_applies_to_years():
    q = "Acme crossed a $100 billion valuation in 2026, the company said"
    d = run("Acme crossed a valuation above $100 billion in 2025", SUPPORTED, q, q + ".")
    assert d.verdict == UNVERIFIED and d.rules[-1][0] == "R2"


def test_exact_claim_is_not_loosened_by_a_larger_figure():
    q = "Acme has raised about $25 billion in equity across 13 rounds"
    d = run("Acme has raised $10 billion in total", SUPPORTED, q, q + ".")
    assert d.verdict == UNVERIFIED and d.rules[-1][0] == "R2"


def test_word_forms_match_by_stem():
    q = "She announced her departure from Acme on September 25, 2024"
    d = run("Jane Roe departed Acme in 2024", SUPPORTED, q, "Jane Roe is a former CTO. " + q + ".")
    assert d.verdict == SUPPORTED, d.rules


def test_table_row_is_relevant_when_numbers_and_dates_all_match():
    q = "June 14, 2023 | Seed | 105 million | Lightspeed"
    d = run("Acme raised a seed round of roughly 105 million in mid-2023", SUPPORTED, q,
            "Acme funding | " + q + " |")
    assert d.verdict == SUPPORTED, d.rules


def test_unrelated_quote_with_one_matching_number_is_still_rejected():
    q = "Revenue was 105 million last year"
    d = run("Acme raised a seed round of roughly 105 million in mid-2023", SUPPORTED, q,
            "Acme annual report. " + q + ".")
    assert d.verdict == UNVERIFIED and d.rules[-1][0] in ("R8", "R2")


def test_quote_cut_mid_word_at_the_end_is_still_verbatim():
    content = "Acme is an artificial intelligence company based in Paris, that builds open-weight foundation models."
    assert quote_in_content("Acme is an artificial intelligence company based in Paris, that builds open-weight fou", content)


def test_quote_starting_mid_word_is_rejected():
    content = "Acme is an artificial intelligence company based in Paris."
    assert not quote_in_content("ficial intelligence company based in Paris", content)


# ---------------------------------------------------------------- happy paths

def test_supported_when_quote_matches_and_numbers_match():
    content = "Acme bought Beta for $2B in 2024, the companies said."
    d = run("Acme bought Beta for $2 billion in 2024", SUPPORTED,
            "Acme bought Beta for $2B in 2024", content)
    assert d.verdict == SUPPORTED
    assert not d.downgraded_from


def test_contradicted_stands_with_a_real_quote():
    content = "Acme now has 1,200 employees across three offices."
    d = run("Acme has 500 employees", CONTRADICTED,
            "Acme now has 1,200 employees across three offices", content)
    assert d.verdict == CONTRADICTED


def test_unverified_proposal_passes_through():
    d = run("Acme has 500 employees", UNVERIFIED, "", "irrelevant")
    assert d.verdict == UNVERIFIED


# ------------------------------------------------- the AI cannot invent a receipt

def test_made_up_quote_is_rejected():
    d = run("Acme bought Beta for $2B in 2024", SUPPORTED,
            "Acme bought Beta for $2B in 2024", "Acme sells widgets and gadgets worldwide.")
    assert d.verdict == UNVERIFIED and d.downgraded_from == SUPPORTED
    assert d.rules[-1][0] == "R1"


def test_source_not_in_results_is_rejected():
    d = run("Acme bought Beta for $2B in 2024", SUPPORTED,
            "Acme bought Beta for $2B in 2024",
            "Acme bought Beta for $2B in 2024.", url="evil.example.org/x")
    assert d.verdict == UNVERIFIED and d.rules[-1][0] == "R1"


def test_quote_too_short_is_rejected():
    d = run("Acme is big", SUPPORTED, "Acme big", "Acme is big and growing.")
    assert d.verdict == UNVERIFIED


def test_url_matching_ignores_scheme_www_and_trailing_slash():
    assert norm_url("https://www.News.Example.com/acme/") == norm_url("news.example.com/acme")


# ------------------------------------------------ numbers and dates (R2)

def test_wrong_number_is_rejected():
    content = "Acme bought Beta for $3B in 2024, the companies said."
    d = run("Acme bought Beta for $2B in 2024", SUPPORTED,
            "Acme bought Beta for $3B in 2024", content)
    assert d.verdict == UNVERIFIED and d.rules[-1][0] == "R2"


@pytest.mark.parametrize("a,b", [
    ("$2B", "$2 billion"), ("$2bn", "$2 billion"), ("2,000 staff", "2000 staff"),
    ("15%", "15 percent"), ("£1.5m", "£1.5 million"),
])
def test_number_formats_are_normalised(a, b):
    assert specifics(a) == specifics(b)


def test_date_formats_are_normalised():
    assert specifics("launched on March 3") >= specifics("launched on 3 March")
    assert specifics("on 3rd March") >= specifics("March 3")


def test_year_alone_is_not_mistaken_for_a_date_pair():
    assert ("date", 3, 20) not in specifics("March 2024")


def test_formatting_difference_does_not_drop_a_true_claim():
    content = "Acme launched Orion on 3 March, the company said."
    d = run("Acme launched Orion on March 3", SUPPORTED,
            "Acme launched Orion on 3 March", content)
    assert d.verdict == SUPPORTED


# -------------------------- hedges and negation (R7), the critic's example

def test_rumour_that_was_denied_does_not_support_the_claim():
    content = "Rumours that Acme would acquire Beta for $2B in 2024 were denied."
    d = run("Acme acquired Beta for $2B in 2024", SUPPORTED,
            "Rumours that Acme would acquire Beta for $2B in 2024 were denied", content)
    assert d.verdict == UNVERIFIED and d.rules[-1][0] == "R7"


def test_negated_statement_does_not_support_the_claim():
    content = "Acme did not raise $50M in 2023, a spokesperson said."
    d = run("Acme raised $50M in 2023", SUPPORTED,
            "Acme did not raise $50M in 2023", content)
    assert d.verdict == UNVERIFIED and d.rules[-1][0] == "R7"


def test_contradiction_may_use_denial_wording():
    content = "Acme denied buying Beta and said the deal never happened."
    d = run("Acme bought Beta", CONTRADICTED,
            "Acme denied buying Beta and said the deal never happened", content)
    assert d.verdict == CONTRADICTED


def test_contradiction_from_a_rumour_is_rejected():
    content = "Acme reportedly has 1,200 employees across three offices."
    d = run("Acme has 500 employees", CONTRADICTED,
            "Acme reportedly has 1,200 employees across three offices", content)
    assert d.verdict == UNVERIFIED and d.rules[-1][0] == "R7"


# ---------------- forward-looking claims are not gutted (R7 modality match)

def test_forward_looking_claim_is_kept_as_a_plan_not_dropped():
    content = "Acme plans to launch Orion in 2026, the company said."
    d = run("Acme will launch Orion in 2026", SUPPORTED,
            "Acme plans to launch Orion in 2026", content)
    assert d.verdict == FORWARD


def test_fact_claim_is_not_supported_by_a_plan():
    content = "Acme plans to launch Orion in 2026, the company said."
    d = run("Acme launched Orion in 2026", SUPPORTED,
            "Acme plans to launch Orion in 2026", content)
    assert d.verdict == UNVERIFIED and d.rules[-1][0] == "R7"


def test_forward_claim_is_rejected_if_the_source_says_cancelled():
    content = "Acme cancelled plans to launch Orion in 2026."
    d = run("Acme will launch Orion in 2026", SUPPORTED,
            "Acme cancelled plans to launch Orion in 2026", content)
    assert d.verdict == UNVERIFIED and d.rules[-1][0] == "R7"


def test_forward_claim_is_rejected_if_the_source_is_a_rumour():
    content = "Acme reportedly plans to launch Orion in 2026."
    d = run("Acme will launch Orion in 2026", SUPPORTED,
            "Acme reportedly plans to launch Orion in 2026", content)
    assert d.verdict == UNVERIFIED


def test_hedge_elsewhere_in_a_long_sentence_does_not_sink_a_true_claim():
    content = "Acme bought Beta for $2B in 2024, but analysts expect more deals."
    d = run("Acme bought Beta for $2B in 2024", SUPPORTED,
            "Acme bought Beta for $2B in 2024", content)
    assert d.verdict == SUPPORTED


# -------------------------------------------------- rewrite check (R9)

def _decisions():
    return {
        "a": Decision("a", SUPPORTED, quote="Acme bought Beta for $2B in 2024"),
        "b": Decision("b", UNVERIFIED, quote="x"),
    }


def test_paragraph_with_cited_supported_claim_and_matching_numbers_passes():
    ok, _ = check_paragraph("Acme bought Beta for $2 billion in 2024 [1].", ["a"], _decisions())
    assert ok


def test_paragraph_without_citation_is_rejected():
    assert not check_paragraph("Acme is doing great.", [], _decisions())[0]


def test_paragraph_citing_a_claim_with_no_receipt_is_rejected():
    assert not check_paragraph("Acme is doing great.", ["b"], _decisions())[0]
    assert not check_paragraph("Acme is doing great.", ["missing"], _decisions())[0]


def test_paragraph_with_an_invented_number_is_rejected():
    ok, why = check_paragraph("Acme bought Beta for $3 billion in 2024 [1].", ["a"], _decisions())
    assert not ok and "numbers" in why


def test_footnote_markers_are_not_mistaken_for_numbers():
    ok, _ = check_paragraph("Acme bought Beta in 2024 [1][2]^3.", ["a"], _decisions())
    assert ok


# -------------------------------------------------- relevance (R8)

def test_generic_quote_from_an_unrelated_source_is_rejected():
    content = "The company was founded in 2010 and employs 40 people."
    d = run("Acme was founded in 2010", SUPPORTED,
            "The company was founded in 2010 and employs 40 people", content)
    assert d.verdict == UNVERIFIED and d.rules[-1][0] == "R8"


# -------------------------------------------------- failures and budget

def test_failed_search_is_unverified_never_a_guess():
    claim = Claim("c1", "Acme has 500 employees", "Acme")
    d = decide(claim, Proposal(SUPPORTED, "x.com", "Acme has 500 employees"), [], search_error="timeout")
    assert d.verdict == UNVERIFIED and d.rules[0][0] == "R6"


def test_unknown_verdict_is_unverified():
    d = run("Acme has 500 employees", "definitely true", "x", "y")
    assert d.verdict == UNVERIFIED


def test_ellipsis_quotes_are_matched_fragment_by_fragment():
    content = "Acme said revenue grew strongly last quarter, driven by cloud sales, and costs fell."
    assert quote_in_content("revenue grew strongly ... driven by cloud sales", content)
    assert not quote_in_content("revenue grew strongly ... driven by hardware sales", content)


def test_budget_caps_claims_and_calls():
    b = Budget(max_claims=2, max_calls=3)
    assert len(b.cap_claims([Claim(str(i), "x") for i in range(5)])) == 2
    b.spend(2)
    b.spend(1)
    with pytest.raises(BudgetExceeded):
        b.spend(1, "retry")
