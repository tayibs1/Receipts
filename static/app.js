/* Receipts UI. Plain JS, no build step, ASCII-only source (symbols are \u escapes).
   All text is inserted as text, never as HTML: claims, quotes and sources are
   untrusted web content. */
"use strict";

const $ = (id) => document.getElementById(id);
const ICON = { supported: "\u2713", contradicted: "\u2715", unverified: "?", forward_looking: "\u25f7" };
const LABEL = {
  supported: "Supported", contradicted: "Contradicted",
  unverified: "Needs your check", forward_looking: "Plan, not a fact",
};
const ORDER = ["contradicted", "supported", "forward_looking", "unverified"];
const RULE_NAME = {
  R0: "Verdict", R1: "Source and quote", R2: "Numbers and dates", R4: "Call budget",
  R6: "Search", R7: "Hedges and denials", R8: "Relevance", ERR: "Error",
};
const DOT = " \u00b7 ";
let lastDone = null;
let sampleActive = false;

function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    e.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return e;
}

/* Search results are untrusted: only http(s) links are ever made clickable. */
function safeHref(u) {
  return /^https?:\/\//i.test(u || "") ? u : "#";
}
const ext = (href, text) => h("a", { href: safeHref(href), target: "_blank", rel: "noopener noreferrer" }, text);

function showBanner(text, info) {
  const b = $("banner");
  b.textContent = text || "";
  b.className = "banner" + (info ? " info" : "");
  b.hidden = !text;
}

/* ---------- status badges ---------- */
async function loadHealth() {
  try {
    const s = await (await fetch("/api/health")).json();
    for (const [id, name] of [["anthropic", "Anthropic"], ["linkup", "Linkup"]]) {
      const b = $("badge-" + id);
      b.textContent = `${name}: ${s[id]}`;
      b.className = "badge " + (s[id] === "live" ? "live" : "offline");
      b.title = (s.detail && s.detail[id]) || "A real API call succeeded";
      if (s[id] !== "live") showBanner(`${name} is offline: ${(s.detail && s.detail[id]) || "no answer"}. Live checks will fail.`);
    }
  } catch (e) {
    showBanner("Could not reach the Receipts server: " + e.message);
  }
}

/* ---------- highlighting: the quote's words that are also in the claim ---------- */
const keyOf = (w) => (w.toLowerCase().match(/[a-z]{4,}|\d[\d.,]*\d|\d/) || [""])[0].slice(0, 5);
function highlighted(quote, claim) {
  const want = new Set((claim.match(/\S+/g) || []).map(keyOf).filter(Boolean));
  const out = h("span", {});
  for (const part of (quote || "").split(/(\s+)/)) {
    const k = keyOf(part);
    out.append(k && want.has(k) ? h("mark", {}, part) : part);
  }
  return out;
}

/* ---------- cards ---------- */
const statusBadge = (v) => h("span", { class: "status " + v }, ICON[v] + " " + LABEL[v]);

function why(c) {
  const last = c.rules.length ? c.rules[c.rules.length - 1] : null;
  if (!last) return "No receipt found.";
  const [r, detail] = last;
  if (r === "R0" && detail === "proposal was unverified") return "No returned source states this.";
  if (r === "R0") return detail.charAt(0).toUpperCase() + detail.slice(1) + ".";
  const lowered = c.downgraded_from ? `The model said "${LABEL[c.downgraded_from].toLowerCase()}"; code refused it. ` : "";
  return `${lowered}${RULE_NAME[r] || r}: ${detail}.`;
}

function card(c) {
  const el = h("article", { class: "card " + c.verdict });
  el.append(statusBadge(c.verdict));
  el.append(h("div", { class: "claim-text" + (c.verdict === "contradicted" ? " struck" : "") }, c.text));
  if (c.verdict !== "unverified" && c.source_url) {
    if (c.verdict === "contradicted") el.append(h("div", { class: "meta strong" }, "A source says otherwise:"));
    el.append(h("blockquote", {}, highlighted(c.quote, c.text)));
    el.append(h("div", { class: "meta" }, ext(c.source_url, c.source_name || c.source_url),
      DOT + "freshness check: " + (c.freshness || "date unknown")));
  } else {
    el.append(h("div", { class: "meta" }, why(c)));
  }
  const actions = h("div", { class: "actions" },
    h("button", { class: "link", type: "button", onclick: () => openDrawer(c) }, "Evidence and rules"));
  if (c.verdict === "unverified") {
    actions.append(ext(c.search_link, "Search manually"));
    const id = "chk-" + c.id + "-" + Math.random().toString(36).slice(2, 7);
    actions.append(h("label", { for: id, class: "inline" }, h("input", { type: "checkbox", id }), "Mark as checked"));
  }
  el.append(actions);
  return el;
}

/* ---------- evidence drawer ---------- */
function openDrawer(c) {
  const failIdx = c.verdict === "unverified" ? c.rules.length - 1 : -1;
  $("drawer-body").replaceChildren(...[
    statusBadge(c.verdict),
    h("p", { class: "claim-text" }, c.text),
    c.source_url ? h("p", { class: "meta" }, ext(c.source_url, c.source_name || c.source_url),
      c.published_at ? DOT + "published " + c.published_at.slice(0, 10) : DOT + "publication date unknown",
      DOT + "freshness check: " + (c.freshness || "n/a")) : null,
    c.quote ? h("blockquote", {}, highlighted(c.quote, c.text)) : null,
    c.reason ? h("p", { class: "meta" }, "The model's reason (not trusted on its own): " + c.reason) : null,
    h("h3", {}, "What the code checked"),
    h("ul", { class: "rules" }, c.rules.map((r, i) =>
      h("li", { class: i === failIdx && r[1] !== "proposal was unverified" ? "fail" : (i === failIdx ? "" : "pass") },
        h("b", {}, (i === failIdx ? "\u2715 " : "\u2713 ") + (RULE_NAME[r[0]] || r[0]) + ` (${r[0]}) `), r[1]))),
    c.downgraded_from ? h("p", { class: "note" }, `The model proposed "${LABEL[c.downgraded_from]}". The referee lowered it: no receipt, no claim.`) : null,
    h("h3", {}, "Searches"),
    h("ul", { class: "rules" }, c.attempts.map((a, i) =>
      h("li", {}, (i ? "Retry: " : "") + `"${a.query}"` + (a.from_date ? ` (from ${a.from_date})` : " (no date filter)") + DOT +
        (a.error ? "failed: " + a.error : `${a.n_results} results, ${a.cached ? "saved" : "live"}`) + DOT +
        `model: ${a.judge || "n/a"}` + DOT + `code: ${a.referee}`))),
  ].filter(Boolean));
  $("drawer").hidden = false;
  $("drawer-close").focus();
}
$("drawer-close").addEventListener("click", () => { $("drawer").hidden = true; });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("drawer").hidden = true; });

/* ---------- running ---------- */
let total = 0, seen = 0;
const chipEls = new Map();

function resetRun() {
  total = 0; seen = 0; chipEls.clear(); lastDone = null;
  $("empty").hidden = true; $("run").hidden = false; $("result").hidden = true;
  $("counts").hidden = true; $("sample-flag").hidden = true;
  $("memory-text").textContent = ""; $("memory-box").open = false;
  $("claim-chips").replaceChildren(); $("live-cards").replaceChildren(); $("trace").replaceChildren();
  $("trace-panel").open = true; $("attack-out").replaceChildren();
  $("progress").textContent = "Starting"; $("meter").textContent = "";
  $("badge-mode").hidden = true; showBanner("");
}

function onEvent(ev) {
  if (ev.type === "info") {
    $("progress").textContent = ev.msg.charAt(0).toUpperCase() + ev.msg.slice(1);
    $("trace").append(h("li", {}, ev.msg));
  } else if (ev.type === "claims") {
    total = ev.claims.length;
    $("memory-text").textContent = ev.briefing;
    $("progress").textContent = `Checking ${total} of ${ev.extracted} claims, ranked by impact`;
    for (const c of ev.claims) {
      const icon = h("span", { class: "chip-icon pending", "aria-label": "checking" }, "\u2026");
      $("claim-chips").append(h("li", {}, icon, h("span", {}, c.text)));
      chipEls.set(c.id, icon);
    }
  } else if (ev.type === "decision") {
    seen += 1;
    $("progress").textContent = `Checked ${seen} of ${total} claims`;
    $("meter").textContent = `${ev.calls} of ${ev.max_calls} calls used`;
    const icon = chipEls.get(ev.claim_id);
    if (icon) { icon.textContent = ICON[ev.verdict]; icon.className = "chip-icon " + ev.verdict; icon.setAttribute("aria-label", LABEL[ev.verdict]); }
    $("live-cards").append(card(ev.card));
    $("trace").append(h("li", {}, ev.trace));
  } else if (ev.type === "done") {
    finish(ev);
  } else if (ev.type === "error") {
    showBanner("The check stopped: " + ev.message);
    $("progress").textContent = "Stopped";
  }
}

async function start() {
  const company = $("company").value.trim();
  const briefing = $("briefing").value.trim();
  if (!company && !briefing) { showBanner("Enter a company name or paste a briefing first."); return; }
  $("go").disabled = true; $("attack-go").disabled = true;
  resetRun();
  try {
    const resp = await fetch("/api/run", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company: briefing ? "" : company, briefing,
        sample: sampleActive && !!briefing, fresh: $("fresh").checked }),
    });
    if (!resp.ok) {
      const j = await resp.json().catch(() => ({}));
      showBanner(j.error || `The server answered ${resp.status}.`);
      $("run").hidden = true; $("empty").hidden = false;
      return;
    }
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "", gotEnd = false;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
        const line = chunk.split("\n").find((l) => l.startsWith("data: "));
        if (!line) continue;
        const ev = JSON.parse(line.slice(6));
        if (ev.type === "done" || ev.type === "error") gotEnd = true;
        onEvent(ev);
      }
    }
    if (!gotEnd) showBanner("The connection closed before the check finished. Nothing was guessed; run it again.");
  } catch (e) {
    showBanner("Lost the connection to the server: " + e.message);
  } finally {
    $("go").disabled = false; $("attack-go").disabled = false;
  }
}

/* ---------- result ---------- */
function plural(n, one, many) { return `${n} ${n === 1 ? one : many}`; }

function finish(d) {
  lastDone = d;
  const c = d.counts;
  const counts = $("counts");
  counts.replaceChildren(
    h("span", {}, `${d.checked} of ${d.extracted} claims checked, ranked by impact:`),
    ...ORDER.filter((v) => c[v]).map((v) => h("span", { class: "status " + v }, `${ICON[v]} ${c[v]} ${LABEL[v].toLowerCase()}`)));
  counts.hidden = false;

  const s = d.searches, m = d.llm_cache || { hits: 0, misses: 0 };
  const live = s.live + m.misses, saved = s.cached + m.hits;
  const mode = $("badge-mode");
  mode.hidden = false;
  mode.textContent = !saved ? "Live run" : !live ? "Replayed from saved results" : "Partly replayed";
  mode.className = "badge " + (!saved ? "live" : !live ? "cached" : "mixed");
  mode.title = `Searches: ${s.live} live, ${s.cached} saved. Model replies: ${m.misses} live, ${m.hits} saved.`;

  const flag = $("sample-flag");
  flag.hidden = !d.sample;
  if (d.sample) flag.textContent = "Sample briefing: written for this demo with some facts deliberately out of date. It is not a real AI draft.";
  if (d.stopped_early) showBanner(d.stopped_early, true);

  const col = $("live-cards");
  col.replaceChildren();
  for (const v of ORDER) {
    const items = d.cards.filter((x) => x.verdict === v);
    if (!items.length) continue;
    col.append(h("h3", { class: "group-h" }, statusBadge(v), " " + items.length));
    items.forEach((x) => col.append(card(x)));
  }
  if (!d.cards.length) col.append(h("p", { class: "muted" }, "No checkable factual claims were found in this text."));

  $("progress").textContent = `Done: ${plural(d.checked, "claim", "claims")} checked`;
  $("meter").textContent = `${d.calls_total} of ${d.max_calls} calls used` + DOT + mode.title;
  $("trace-panel").open = false;
  $("result").hidden = false;
  renderRewrite(d.rewrite, d.cards);
}

function renderRewrite(rw, cards) {
  const panel = $("rewrite");
  if (!rw) { panel.hidden = true; return; }
  panel.hidden = false;
  const byId = Object.fromEntries(cards.map((c) => [c.id, c]));
  const v = $("verified");
  v.className = "verified";
  v.replaceChildren();
  if (rw.error) v.append(h("p", { class: "note" }, rw.error));
  if (!rw.paragraphs.length && !rw.listed_not_rewritten.length && !rw.error)
    v.append(h("p", { class: "muted" }, "No claim had a receipt, so there is nothing to state as fact. See the claims above."));
  let section = null;
  for (const p of rw.paragraphs) {
    if (p.section !== section) { section = p.section; v.append(h("h3", {}, section || "Briefing")); }
    v.append(h("p", {}, p.text, " ", p.notes.map((n) => h("sup", {}, h("a", { href: "#fn" + n }, `[${n}]`)))));
  }
  if (rw.listed_not_rewritten.length) {
    v.append(h("h3", {}, "Verified facts (checked, not rewritten)"));
    v.append(h("ul", {}, rw.listed_not_rewritten.map((id) => h("li", {}, byId[id].text))));
  }
  const wrong = cards.filter((c) => c.verdict === "contradicted");
  if (wrong.length) {
    v.append(h("h3", {}, "Corrections"));
    v.append(h("ul", {}, wrong.map((c) => h("li", {}, h("s", {}, c.text), " ", h("span", { class: "muted" }, "(a source says otherwise; see above)")))));
  }
  const check = cards.filter((c) => c.verdict === "unverified");
  if (check.length) {
    v.append(h("h3", {}, "Needs your check"));
    v.append(h("ul", {}, check.map((c) => h("li", {}, c.text, " ", ext(c.search_link, "search")))));
  }
  if (rw.rejected.length)
    v.append(h("p", { class: "note" },
      `The number check (R9) refused ${plural(rw.rejected.length, "rewritten paragraph", "rewritten paragraphs")} ` +
      `(${rw.rejected.map((r) => r.reason).join("; ")}). Their claims are listed as checked instead.`));
  if (rw.dropped_sections.length)
    v.append(h("p", { class: "muted" }, "Left out, no receipted claim: " + rw.dropped_sections.join(", ")));
  if (rw.footnotes.length) {
    v.append(h("h3", {}, "Sources"));
    v.append(h("ol", { class: "sources" }, rw.footnotes.map((f) =>
      h("li", { id: "fn" + f.n, value: f.n }, ext(f.url, f.source), ` (freshness check: ${f.freshness || "n/a"}) "${f.quote}"`))));
  }
  v.append(h("p", { class: "muted" }, "Code checked that every number and date above appears in a cited quote. It does not prove the wording adds nothing else."));
  const df = $("diff");
  df.className = "diff";
  df.replaceChildren(h("p", { class: "muted" }, "Struck through: in the AI draft, not kept. Highlighted: in the verified briefing."),
    h("div", {}, ...rw.diff.map((x) => h("span", { class: x.op }, x.text + " "))));
  if (!rw.diff.length) df.replaceChildren(h("p", { class: "muted" }, "No rewritten text to compare."));
}

function tab(which) {
  const verified = which === "verified";
  $("verified").hidden = !verified; $("diff").hidden = verified;
  $("tab-verified").classList.toggle("on", verified); $("tab-diff").classList.toggle("on", !verified);
  $("tab-verified").setAttribute("aria-selected", String(verified)); $("tab-diff").setAttribute("aria-selected", String(!verified));
}

/* ---------- wiring ---------- */
$("go").addEventListener("click", start);
$("company").addEventListener("keydown", (e) => { if (e.key === "Enter") start(); });
$("tab-verified").addEventListener("click", () => tab("verified"));
$("tab-diff").addEventListener("click", () => tab("diff"));
function clearSample() { sampleActive = false; $("sample-note").hidden = true; }
for (const name of ["OpenAI", "Databricks", "Anthropic", "Mistral AI"]) {
  $("chips").append(h("button", { class: "chip", type: "button", onclick: () => {
    $("company").value = name; $("briefing").value = ""; clearSample(); $("company").focus();
  } }, name));
}
$("briefing").addEventListener("input", clearSample);
$("sample").addEventListener("click", async () => {
  try {
    const s = await (await fetch("/api/sample")).json();
    $("briefing").value = s.text; $("company").value = ""; sampleActive = true;
    $("sample-note").textContent = s.label; $("sample-note").hidden = false;
  } catch (e) { showBanner("Could not load the sample: " + e.message); }
});
$("copy-md").addEventListener("click", async () => {
  if (!lastDone || !lastDone.rewrite) return;
  try { await navigator.clipboard.writeText(lastDone.rewrite.markdown); $("copy-note").textContent = "Copied."; }
  catch (e) { $("copy-note").textContent = "Copy failed: " + e.message; }
});
$("download").addEventListener("click", () => {
  if (!lastDone) return;
  const a = h("a", { href: URL.createObjectURL(new Blob([JSON.stringify(lastDone, null, 2)], { type: "application/json" })),
    download: `receipt-pack-${lastDone.run_id}.json` });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
});
async function attack() {
  const claim = $("attack-claim").value.trim();
  const out = $("attack-out");
  if (claim.length < 8) { out.replaceChildren(h("p", { class: "muted" }, "Type a full claim (at least 8 characters).")); return; }
  $("attack-go").disabled = true;
  out.replaceChildren(h("p", { class: "muted" }, "Planning a query, searching the live web, judging, refereeing..."));
  try {
    const r = await fetch("/api/attack", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ claim }) });
    const j = await r.json();
    out.replaceChildren(r.ok ? card(j) : h("p", { class: "banner" }, j.error || `Server answered ${r.status}`));
  } catch (e) { out.replaceChildren(h("p", { class: "banner" }, "Check failed: " + e.message)); }
  finally { $("attack-go").disabled = false; }
}
$("attack-go").addEventListener("click", attack);
$("attack-claim").addEventListener("keydown", (e) => { if (e.key === "Enter") attack(); });
loadHealth();
