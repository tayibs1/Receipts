/* Receipts site. Plain JS, no build step, ASCII-only source (symbols are \u escapes).
   Everything dynamic is inserted as text, never as HTML: claims, quotes and sources are
   untrusted web content. No inline styles or scripts, so a strict CSP applies. */
"use strict";

const $ = (id) => document.getElementById(id);
const ICON = { supported: "\u2713", contradicted: "\u2715", unverified: "?", forward_looking: "\u25f7" };
const LABEL = {
  supported: "Supported", contradicted: "Contradicted",
  unverified: "Needs your check", forward_looking: "Plan, not a fact",
};
const ORDER = ["contradicted", "unverified", "forward_looking", "supported"];
const PRIORITY = { contradicted: 4, unverified: 3, forward_looking: 2, supported: 1 };
const RULE_TEXT = {
  R0: "The judge found no source that states this",
  R1: "The source is one of the returned results and the quote appears in it",
  R2: "Every number and date in the claim appears in the quote",
  R4: "Call budget reached; claim left unchecked",
  R6: "The search failed, so the claim is not guessed",
  R7: "No rumour, plan or denial wording around the quote",
  R8: "The source mentions the company and the quote shares the claim's key words",
  ERR: "A model error stopped this claim",
};
const DOT = " \u00b7 ";
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
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
const safeHref = (u) => (/^https?:\/\//i.test(u || "") ? u : "#");
const ext = (href, text) => h("a", { href: safeHref(href), target: "_blank", rel: "noopener noreferrer" }, text);
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

function showBanner(text, info) {
  const b = $("banner");
  b.textContent = text || "";
  b.className = "banner" + (info ? " info" : "");
  b.hidden = !text;
}

/* ---------- service status ---------- */
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

/* ---------- quote highlighting: words of the quote that are also in the claim ---------- */
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

/* Plain-English reason on the card; the exact rule and detail are in the evidence drawer. */
const PLAIN_WHY = {
  R0: "No source we found states this.",
  R1: "The AI's suggested source or quote could not be verified.",
  R2: "A source was found, but it doesn't contain every number or date in the claim.",
  R4: "The call budget ran out before this claim was checked.",
  R6: "The search failed, so nothing was guessed.",
  R7: "A source mentions this, but only as a rumour, a plan or a denial.",
  R8: "A source was found, but it doesn't clearly say this.",
  ERR: "A model error stopped this check.",
};
function why(c) {
  const last = c.rules.length ? c.rules[c.rules.length - 1] : null;
  if (!last) return "No receipt found. It is yours to check.";
  const base = PLAIN_WHY[last[0]] || (last[1].charAt(0).toUpperCase() + last[1].slice(1) + ".");
  return base + " Not guessed: it is yours to check.";
}

const GROUP_NOTE = {
  contradicted: "A source says otherwise. We do not judge how authoritative it is.",
  unverified: "No verified source. Never guessed: yours to check.",
  forward_looking: "An intention, not a completed fact.",
  supported: "A real source states it and code verified the quote.",
};

function card(c) {
  const el = h("article", { class: "card " + c.verdict, "data-claim": c.id });
  el.append(h("div", { class: "card-head" }, statusBadge(c.verdict), h("span", { class: "claim-no" }, "Claim " + c.id)));
  el.append(h("div", { class: "claim-text" + (c.verdict === "contradicted" ? " struck" : "") }, c.text));
  if (c.verdict !== "unverified" && c.source_url) {
    if (c.verdict === "contradicted") el.append(h("div", { class: "meta strong" }, "A source says otherwise:"));
    el.append(h("div", { class: "src" },
      h("div", { class: "src-name" }, ext(c.source_url, c.source_name || c.source_url)),
      h("span", { class: "chip-date" }, "Freshness: " + (c.freshness || "date unknown"))));
    el.append(h("blockquote", {}, highlighted(c.quote, c.text)));
  } else {
    el.append(h("div", { class: "meta" }, why(c)));
  }
  const actions = h("div", { class: "actions" },
    h("button", { class: "linkbtn", type: "button", onclick: () => openDrawer(c) }, "Evidence and rules"));
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
  const WHY = {
    supported: "A returned source states it, and code verified the quote.",
    contradicted: "A source says something different. We do not judge how authoritative it is.",
    forward_looking: "It is about the future, and the source says the same. We do not call it a fact.",
  };
  $("drawer-body").replaceChildren(...[
    h("p", { class: "eyebrow" }, "Evidence for claim " + c.id),
    statusBadge(c.verdict),
    h("h3", { class: "d-label" }, "Claim"),
    h("p", { class: "claim-text" }, c.text),
    c.quote ? h("h3", { class: "d-label" }, "Full quote") : null,
    c.quote ? h("blockquote", {}, highlighted(c.quote, c.text)) : null,
    c.source_url ? h("h3", { class: "d-label" }, "Source") : null,
    c.source_url ? h("p", { class: "meta" }, ext(c.source_url, c.source_name || c.source_url),
      c.published_at ? DOT + "published " + c.published_at.slice(0, 10) : DOT + "publication date unknown",
      DOT + "freshness check: " + (c.freshness || "n/a")) : null,
    h("h3", { class: "d-label" }, "Why we decided this"),
    h("p", {}, c.verdict === "unverified" ? why(c) : WHY[c.verdict]),
    c.reason ? h("p", { class: "meta" }, "The model's reason (not trusted on its own): " + c.reason) : null,
    h("h3", { class: "d-label" }, "Checker rules"),
    h("ul", { class: "rules" }, c.rules.map((r, i) => {
      const stopped = i === failIdx && r[1] !== "proposal was unverified";
      return h("li", { class: stopped ? "fail" : "" },
        h("span", { class: "rid" }, r[0]),
        h("span", { class: "rmark", "aria-hidden": "true" }, stopped ? "\u2715" : "\u2713"),
        h("div", {}, h("b", {}, RULE_TEXT[r[0]] || r[0]),
          h("span", {}, r[1] + (stopped ? ". Stopped this claim." : ""))));
    })),
    c.downgraded_from ? h("p", { class: "note" }, `The model proposed "${LABEL[c.downgraded_from]}". The referee lowered it: no receipt, no claim.`) : null,
    h("h3", { class: "d-label" }, "Searches"),
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

/* ---------- progress steps ---------- */
const STEPS = ["read", "check", "write"];
function setStep(name) {
  const at = name === "done" ? STEPS.length : STEPS.indexOf(name);
  document.querySelectorAll("#steps li").forEach((li) => {
    const i = STEPS.indexOf(li.dataset.step);
    li.className = i < at ? "done" : i === at ? "active" : "";
  });
}

/* ---------- the AI's text, marked up like an editor's red pen ---------- */
const STOP = new Set(["that", "this", "with", "from", "have", "were", "been", "they", "their", "which", "also", "into",
  "than", "then", "about", "over", "more", "most", "company", "said", "year", "years"]);
const tokens = (t) => new Set(((t || "").toLowerCase().match(/[a-z]{4,}|\d[\d.,]*\d|\d/g) || []).filter((w) => !STOP.has(w)));
const decisions = new Map();   // claim id -> verdict
const cardData = new Map();    // claim id -> card
const claimSent = new Map();   // claim id -> sentence record
let sentences = [];

function looksLikeHeading(line) {
  const words = line.split(/\s+/).length;
  return !/[.!?]$/.test(line) && line.length <= 52 && words <= 7;
}
function titleCase(s) {
  return /[a-z]/.test(s) ? s : s.toLowerCase().replace(/(^|\s)\S/g, (m) => m.toUpperCase());
}

function buildPaper(briefing, claims) {
  const root = $("memory-text");
  root.replaceChildren();
  sentences = []; claimSent.clear();
  const clean = (briefing || "").replace(/\r/g, "").replace(/\*\*/g, "");
  for (const raw of clean.split("\n")) {
    const line = raw.replace(/^[#*\-\s]+/, "").trim();
    if (!line) continue;
    if (looksLikeHeading(line)) { root.append(h("h4", { class: "paper-h" }, titleCase(line))); continue; }
    const p = h("p", {});
    for (const s of line.split(/(?<=[.!?])\s+/)) {
      // the last word sits in a no-wrap tail, so a status icon can never wrap onto its own line
      const m = s.match(/^([\s\S]*?)(\S+)$/);
      const tail = h("span", { class: "tail" }, m ? m[2] : s);
      const el = h("span", { class: "sent" }, m ? m[1] : "", tail);
      p.append(el, " ");
      sentences.push({ el, tail, text: s, tok: tokens(s), claims: [], icon: null });
    }
    root.append(p);
  }
  // attach each claim to the sentence it most likely came from
  for (const c of claims) {
    const ct = tokens(c.text);
    if (!ct.size) continue;
    let best = null, bestScore = 0;
    for (const se of sentences) {
      let n = 0;
      for (const w of ct) if (se.tok.has(w)) n += 1;
      const score = n / ct.size;
      if (score > bestScore) { bestScore = score; best = se; }
    }
    if (best && bestScore >= 0.5) {
      best.claims.push(c.id);
      best.el.classList.add("s-pending");
      claimSent.set(c.id, best);
    }
  }
}

function markSentence(claimId, verdict) {
  decisions.set(claimId, verdict);
  const se = claimSent.get(claimId);
  if (!se) return;
  let worst = null;
  for (const cid of se.claims) {
    const v = decisions.get(cid);
    if (v && (!worst || PRIORITY[v] > PRIORITY[worst])) worst = v;
  }
  if (!worst) return;
  se.el.className = "sent s-" + worst;
  if (!se.icon) {
    se.icon = h("span", { class: "sent-ico", "aria-hidden": "true" });
    se.tail.append(se.icon);
    const open = () => {
      let pick = null;
      for (const cid of se.claims) {
        const v = decisions.get(cid);
        if (v && (!pick || PRIORITY[v] > PRIORITY[decisions.get(pick)])) pick = cid;
      }
      if (pick && cardData.has(pick)) openDrawer(cardData.get(pick));
    };
    se.el.setAttribute("role", "button");
    se.el.setAttribute("tabindex", "0");
    se.el.addEventListener("click", open);
    se.el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } });
  }
  se.icon.textContent = ICON[worst];
  se.el.setAttribute("aria-label", `${LABEL[worst]}: ${se.text.trim()}. Open the receipt.`);
}

/* ---------- running ---------- */
let total = 0, seen = 0;

function resetRun() {
  total = 0; seen = 0; lastDone = null;
  decisions.clear(); cardData.clear();
  $("run").hidden = false; $("result").hidden = true;
  $("verdict").hidden = true; $("counts").hidden = true; $("sample-flag").hidden = true;
  $("memory-text").replaceChildren(); $("live-cards").replaceChildren(); $("trace").replaceChildren();
  $("trace-panel").open = true; $("attack-out").replaceChildren();
  $("progress").textContent = "Starting"; $("meter").textContent = ""; $("step-count").textContent = "";
  $("badge-mode").hidden = true; showBanner("");
  setStep("read");
}

function onEvent(ev) {
  if (ev.type === "info") {
    $("progress").textContent = ev.msg.charAt(0).toUpperCase() + ev.msg.slice(1);
    $("trace").append(h("li", {}, ev.msg));
    if (/rewrit/i.test(ev.msg)) setStep("write");
  } else if (ev.type === "claims") {
    total = ev.claims.length;
    buildPaper(ev.briefing, ev.claims);
    setStep("check");
    $("step-count").textContent = `(0 of ${total})`;
    $("progress").textContent = `Checking ${total} of ${ev.extracted} claims, ranked by impact`;
  } else if (ev.type === "decision") {
    seen += 1;
    $("progress").textContent = `Checked ${seen} of ${total} claims`;
    $("step-count").textContent = `(${seen} of ${total})`;
    $("meter").textContent = `${ev.calls} of ${ev.max_calls} calls used`;
    cardData.set(ev.claim_id, ev.card);
    markSentence(ev.claim_id, ev.verdict);
    $("live-cards").append(card(ev.card));
    $("trace").append(h("li", {}, ev.trace));
  } else if (ev.type === "done") {
    finish(ev);
  } else if (ev.type === "error") {
    showBanner("The check stopped: " + ev.message);
    $("progress").textContent = "Stopped";
  }
}

/* Events are shown one at a time, so each claim lands on its own: a saved replay would
   otherwise appear all at once. Live runs are slower than this, so they are unaffected. */
const GAP_MS = reduceMotion ? 0 : 450;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const queue = [];
let draining = false;
async function drain() {
  draining = true;
  while (queue.length) {
    const ev = queue.shift();
    onEvent(ev);
    if (ev.type === "decision" && GAP_MS) await sleep(GAP_MS);
  }
  draining = false;
}
function enqueue(ev) { queue.push(ev); if (!draining) drain(); }
async function drained() { while (draining || queue.length) await sleep(40); }

async function start() {
  const company = $("company").value.trim();
  const briefing = $("briefing").value.trim();
  if (!company && !briefing) { showBanner("Enter a company name or paste a briefing first."); return; }
  $("go").disabled = true; $("attack-go").disabled = true;
  resetRun();
  $("run").scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
  try {
    const resp = await fetch("/api/run", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company: briefing ? "" : company, briefing,
        sample: sampleActive && !!briefing, fresh: $("fresh").checked }),
    });
    if (!resp.ok) {
      const j = await resp.json().catch(() => ({}));
      showBanner(j.error || `The server answered ${resp.status}.`);
      $("run").hidden = true;
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
        enqueue(ev);
      }
    }
    await drained();
    if (!gotEnd) showBanner("The connection closed before the check finished. Nothing was guessed; run it again.");
  } catch (e) {
    showBanner("Lost the connection to the server: " + e.message);
  } finally {
    $("go").disabled = false; $("attack-go").disabled = false;
  }
}

/* ---------- result ---------- */
function verdictHead(d) {
  const c = d.counts, el = $("verdict");
  const bits = [];
  if (c.contradicted) bits.push(h("span", { class: "v-bad" }, `${c.contradicted} contradicted by a source`));
  if (c.supported) bits.push(h("span", { class: "v-ok" }, `${c.supported} supported`));
  if (c.forward_looking) bits.push(h("span", { class: "v-plan" }, plural(c.forward_looking, "plan", "plans")));
  if (c.unverified) bits.push(h("span", { class: "v-chk" }, `${c.unverified} ${c.unverified === 1 ? "needs" : "need"} your check`));
  el.replaceChildren();
  if (!bits.length) { el.append("No checkable factual claims were found in this text."); }
  else {
    el.append(`Of ${plural(d.checked, "claim", "claims")} checked: `);
    bits.forEach((b, i) => { if (i) el.append(i === bits.length - 1 ? " and " : ", "); el.append(b); });
    el.append(".");
  }
  el.hidden = false;
}

function finish(d) {
  lastDone = d;
  const c = d.counts;
  verdictHead(d);
  const counts = $("counts");
  counts.replaceChildren(h("span", {},
    `${d.checked} of ${d.extracted} claims checked, ranked by impact (numbers and dates first).`));
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
    col.append(h("h4", { class: "group-h" }, statusBadge(v), `${items.length} ${items.length === 1 ? "claim" : "claims"}`,
      h("span", { class: "group-note" }, GROUP_NOTE[v])));
    items.forEach((x) => { cardData.set(x.id, x); col.append(card(x)); });
  }
  if (!d.cards.length) col.append(h("p", { class: "muted" }, "No checkable factual claims were found in this text."));

  setStep("done");
  $("step-count").textContent = "";
  $("progress").textContent = `Done: ${plural(d.checked, "claim", "claims")} checked`;
  $("meter").textContent = `${d.calls_total} of ${d.max_calls} calls used` + DOT + mode.textContent.toLowerCase();
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
function updateChars() {
  const n = $("briefing").value.length;
  $("chars").textContent = n ? `${n.toLocaleString()} of 8,000 characters` : "";
}
function clearSample() { sampleActive = false; $("sample-note").hidden = true; }

async function loadSample() {
  try {
    const s = await (await fetch("/api/sample")).json();
    $("briefing").value = s.text; $("company").value = ""; sampleActive = true;
    $("sample-note").textContent = s.label; $("sample-note").hidden = false;
    updateChars();
    return true;
  } catch (e) { showBanner("Could not load the sample: " + e.message); return false; }
}

$("go").addEventListener("click", start);
$("company").addEventListener("keydown", (e) => { if (e.key === "Enter") start(); });
$("tab-verified").addEventListener("click", () => tab("verified"));
$("tab-diff").addEventListener("click", () => tab("diff"));
for (const name of ["OpenAI", "Databricks", "Anthropic", "Mistral AI"]) {
  $("chips").append(h("button", { class: "chip", type: "button", onclick: () => {
    $("company").value = name; $("briefing").value = ""; clearSample(); updateChars(); $("company").focus();
  } }, name));
}
$("briefing").addEventListener("input", () => { clearSample(); updateChars(); });
$("sample").addEventListener("click", loadSample);
$("hero-try").addEventListener("click", async () => {
  if (await loadSample()) {
    $("try").scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
    $("go").focus({ preventScroll: true });
  }
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
