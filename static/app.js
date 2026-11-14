/* Receipts UI. Plain JS, no build step. All text is inserted with textContent,
   never innerHTML, because claims, quotes and sources are untrusted web content. */
"use strict";

const $ = (id) => document.getElementById(id);
const ICON = { supported: "âœ“", contradicted: "âœ•", unverified: "?", forward_looking: "â—·" };
const LABEL = {
  supported: "Supported", contradicted: "Contradicted",
  unverified: "Needs your check", forward_looking: "Plan, not a fact",
};
const ORDER = ["supported", "forward_looking", "contradicted", "unverified"];
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

function showBanner(text, info) {
  const b = $("banner");
  b.textContent = text;
  b.className = "banner" + (info ? " info" : "");
  b.hidden = !text;
}

/* ---------- status badges ---------- */
async function loadHealth(refresh) {
  try {
    const r = await fetch("/api/health" + (refresh ? "?refresh=true" : ""));
    const s = await r.json();
    for (const [id, name] of [["anthropic", "Anthropic"], ["linkup", "Linkup"]]) {
      const b = $("badge-" + id);
      b.textContent = `${name}: ${s[id]}`;
      b.className = "badge " + (s[id] === "live" ? "live" : "offline");
      b.title = (s.detail && s.detail[id]) || "A real call succeeded";
    }
  } catch (e) {
    showBanner("Could not reach the Receipts server: " + e.message);
  }
}

/* ---------- highlighting ---------- */
function words(text) {
  return new Set((text.toLowerCase().match(/[a-z]{4,}|\d[\d.,]*/g) || []));
}
function highlighted(quote, claim) {
  const w = words(claim);
  const out = document.createElement("span");
  for (const part of quote.split(/(\s+)/)) {
    const key = (part.toLowerCase().match(/[a-z]{4,}|\d[\d.,]*/) || [""])[0];
    if (key && w.has(key)) out.append(h("mark", {}, part));
    else out.append(part);
  }
  return out;
}

/* ---------- cards ---------- */
function statusBadge(v) {
  return h("span", { class: "status " + v }, ICON[v] + " " + LABEL[v]);
}

function card(c, opts) {
  opts = opts || {};
  const el = h("article", { class: "card " + c.verdict });
  el.append(statusBadge(c.verdict));
  el.append(h("div", { class: "claim-text" + (c.verdict === "contradicted" ? " struck" : "") }, c.text));
  if (c.verdict === "contradicted") el.append(h("div", { class: "meta" }, "A source says otherwise:"));
  if (c.verdict !== "unverified" && c.source_url) {
    el.append(h("div", { class: "meta" },
      h("a", { href: safeHref(c.source_url), target: "_blank", rel: "noopener noreferrer" }, c.source_name || c.source_url),
      " Â· freshness check: " + (c.freshness || "date unknown")));
    el.append(h("blockquote", {}, highlighted(c.quote, c.text)));
  } else {
    const last = c.rules.length ? c.rules[c.rules.length - 1] : null;
    el.append(h("div", { class: "meta" }, last ? why(last) : "No receipt found."));
  }
  const actions = h("div", { class: "actions" },
    h("button", { class: "link", type: "button", onclick: () => openDrawer(c) }, "Evidence"));
  if (c.verdict === "unverified") {
    actions.append(h("a", { href: c.search_link, target: "_blank", rel: "noopener noreferrer" }, "Search manually"));
    const id = "chk-" + c.id + "-" + Math.random().toString(36).slice(2, 6);
    actions.append(h("label", { for: id, style: "margin:0;display:flex;gap:4px;align-items:center" },
      h("input", { type: "checkbox", id }), "Mark as checked"));
  }
  if (!opts.noActions) el.append(actions);
  return el;
}

function why(rule) {
  const [r, detail] = rule;
  if (r === "R0" && detail === "proposal was unverified") return "The judge found no source that states this.";
  return `${r}: ${detail}`;
}

/* ---------- drawer ---------- */
function openDrawer(c) {
  const body = $("drawer-body");
  body.replaceChildren(...[
    statusBadge(c.verdict),
    h("p", { class: "claim-text" }, c.text),
    c.source_url ? h("p", { class: "meta" },
      h("a", { href: safeHref(c.source_url), target: "_blank", rel: "noopener noreferrer" }, c.source_name || c.source_url),
      c.published_at ? ` Â· published ${c.published_at.slice(0, 10)}` : " Â· date unknown",
      ` Â· freshness check: ${c.freshness || "n/a"}`) : null,
    c.quote ? h("blockquote", {}, highlighted(c.quote, c.text)) : null,
    c.reason ? h("p", { class: "meta" }, "Judge's reason: " + c.reason) : null,
    h("h2", {}, "Rules the referee applied"),
    h("ul", { class: "rules" }, c.rules.map((r, i) =>
      // the last rule is the one that stopped the claim when it ended as unverified
      h("li", { class: c.verdict === "unverified" && i === c.rules.length - 1 ? "fail" : "" },
        h("b", {}, r[0] + " "), r[1]))),
    c.downgraded_from ? h("p", { class: "meta" }, `The judge proposed "${c.downgraded_from}"; the referee lowered it.`) : null,
    h("h2", { style: "margin-top:24px" }, "Searches"),
    h("ul", { class: "rules" }, c.attempts.map((a) =>
      h("li", {}, `"${a.query}"${a.from_date ? " from " + a.from_date : " (no date filter)"} Â· ` +
        `${a.error ? "failed: " + a.error : a.n_results + " results, " + (a.cached ? "cached" : "live")} Â· ` +
        `judge: ${a.judge || "n/a"} Â· referee: ${a.referee}`))),
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
  $("memory-text").textContent = ""; $("claim-chips").replaceChildren();
  $("live-cards").replaceChildren(); $("trace").replaceChildren();
  $("progress").textContent = "Starting"; $("meter").textContent = "";
  $("badge-mode").hidden = true; showBanner("");
}

function onEvent(ev) {
  if (ev.type === "info") {
    $("progress").textContent = ev.msg;
    $("trace").append(h("li", {}, ev.msg));
  } else if (ev.type === "claims") {
    total = ev.claims.length;
    $("memory-text").textContent = ev.briefing;
    $("progress").textContent = `${total} of ${ev.extracted} claims to check, ranked by impact`;
    for (const c of ev.claims) {
      const icon = h("span", {}, "â€¦");
      const li = h("li", {}, icon, h("span", {}, c.text));
      chipEls.set(c.id, icon);
      $("claim-chips").append(li);
    }
  } else if (ev.type === "decision") {
    seen += 1;
    $("progress").textContent = `Checked ${seen} of ${total} claims`;
    $("meter").textContent = `${ev.calls} of ${ev.max_calls} calls used`;
    const icon = chipEls.get(ev.claim_id);
    if (icon) icon.textContent = ICON[ev.verdict];
    $("live-cards").append(card(ev.card));
    $("trace").append(h("li", {}, ev.trace));
  } else if (ev.type === "done") {
    finish(ev);
  } else if (ev.type === "error") {
    showBanner("The check stopped: " + ev.message);
  }
}

async function start() {
  const company = $("company").value.trim();
  const briefing = $("briefing").value.trim();
  if (!company && !briefing) { showBanner("Enter a company name or paste a briefing first."); return; }
  $("go").disabled = true;
  resetRun();
  try {
    const resp = await fetch("/api/run", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company: briefing ? "" : company, briefing, sample: sampleActive && !!briefing }),
    });
    if (!resp.ok) {
      const j = await resp.json().catch(() => ({}));
      showBanner(j.error || `The server answered ${resp.status}.`);
      $("run").hidden = true; $("empty").hidden = false;
      return;
    }
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
        const line = chunk.split("\n").find((l) => l.startsWith("data: "));
        if (line) onEvent(JSON.parse(line.slice(6)));
      }
    }
  } catch (e) {
    showBanner("Lost the connection to the server: " + e.message);
  } finally {
    $("go").disabled = false;
  }
}

/* ---------- result ---------- */
function finish(d) {
  lastDone = d;
  const c = d.counts;
  $("counts").textContent =
    `${d.checked} of ${d.extracted} claims checked, ranked by impact: ${c.supported} supported, ` +
    `${c.contradicted} contradicted, ${c.forward_looking} plan${c.forward_looking === 1 ? "" : "s"}, ` +
    `${c.unverified} need${c.unverified === 1 ? "s" : ""} your check`;
  const mode = $("badge-mode");
  const { live, cached } = d.searches;
  mode.hidden = false;
  mode.textContent = live && !cached ? `Live: ${live} searches` : !live && cached ? `Cached: ${cached} saved searches`
    : `Mixed: ${live} live, ${cached} cached`;
  mode.className = "badge " + (live && !cached ? "live" : !live && cached ? "cached" : "mixed");
  const flag = $("sample-flag");
  flag.hidden = !d.sample;
  if (d.sample) flag.textContent = "Sample briefing: written for this demo with some facts deliberately out of date. It is not a real AI draft.";
  if (d.stopped_early) showBanner(d.stopped_early, true);

  const groups = $("groups");
  groups.replaceChildren();
  for (const v of ORDER) {
    const items = d.cards.filter((x) => x.verdict === v);
    if (!items.length) continue;
    groups.append(h("div", { class: "group" },
      h("h2", {}, statusBadge(v), ` ${items.length}`),
      h("div", { class: "cards" }, items.map((x) => card(x)))));
  }
  $("progress").textContent = `Done: ${d.checked} claims, ${d.calls_total} of ${d.max_calls} calls used`;
  $("meter").textContent = "";
  $("result").hidden = false;
  renderRewrite(d.rewrite, d.cards);
  $("result").scrollIntoView({ behavior: "smooth" });
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
    v.append(h("p", { class: "muted" }, "No claim had a receipt, so there is nothing to rewrite. The claims that need your check are listed above."));
  let section = null;
  for (const p of rw.paragraphs) {
    if (p.section !== section) { section = p.section; v.append(h("h3", {}, section || "Briefing")); }
    v.append(h("p", {}, p.text, " ", p.notes.map((n) => h("sup", {}, h("a", { href: "#fn" + n }, `[${n}]`)))));
  }
  if (rw.listed_not_rewritten.length) {
    v.append(h("h3", {}, "Verified facts (checked, not rewritten)"));
    v.append(h("ul", {}, rw.listed_not_rewritten.map((id) => h("li", {}, byId[id].text))));
  }
  if (rw.rejected.length)
    v.append(h("p", { class: "note" },
      `The number check (R9) refused ${rw.rejected.length} rewritten paragraph${rw.rejected.length === 1 ? "" : "s"} ` +
      `(${rw.rejected.map((r) => r.reason).join("; ")}). Their claims are listed as checked instead.`));
  if (rw.dropped_sections.length)
    v.append(h("p", { class: "muted" }, "Left out, no receipted claim: " + rw.dropped_sections.join(", ")));
  if (rw.footnotes.length) {
    v.append(h("h3", {}, "Sources"));
    v.append(h("ol", { class: "sources" }, rw.footnotes.map((f) =>
      h("li", { id: "fn" + f.n, value: f.n },
        h("a", { href: safeHref(f.url), target: "_blank", rel: "noopener noreferrer" }, f.source), ` (freshness check: ${f.freshness || "n/a"}) "${f.quote}"`))));
  }
  v.append(h("p", { class: "muted" }, "The number check covers numbers and dates. It does not prove that the wording adds nothing else."));
  const df = $("diff");
  df.className = "diff";
  df.replaceChildren(...rw.diff.map((x) => h("span", { class: x.op }, x.text + " ")));
  if (!rw.diff.length) df.textContent = "No rewritten text to compare.";
}

function tab(which) {
  const verified = which === "verified";
  $("verified").hidden = !verified; $("diff").hidden = verified;
  $("tab-verified").classList.toggle("on", verified); $("tab-diff").classList.toggle("on", !verified);
  $("tab-verified").setAttribute("aria-selected", verified); $("tab-diff").setAttribute("aria-selected", !verified);
}

/* ---------- wiring ---------- */
$("go").addEventListener("click", start);
$("company").addEventListener("keydown", (e) => { if (e.key === "Enter") start(); });
$("tab-verified").addEventListener("click", () => tab("verified"));
$("tab-diff").addEventListener("click", () => tab("diff"));
for (const name of ["OpenAI", "Databricks", "Anthropic", "Mistral AI"]) {
  $("chips").append(h("button", { class: "chip", type: "button", onclick: () => {
    $("company").value = name; $("briefing").value = ""; sampleActive = false; $("sample-note").textContent = "";
  } }, name));
}
$("briefing").addEventListener("input", () => { sampleActive = false; $("sample-note").textContent = ""; });
$("sample").addEventListener("click", async () => {
  try {
    const s = await (await fetch("/api/sample")).json();
    $("briefing").value = s.text; $("company").value = ""; sampleActive = true;
    $("sample-note").textContent = s.label;
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
  a.click(); URL.revokeObjectURL(a.href);
});
$("attack-go").addEventListener("click", async () => {
  const claim = $("attack-claim").value.trim();
  const out = $("attack-out");
  if (claim.length < 8) { out.replaceChildren(h("p", { class: "muted" }, "Type a full claim (at least 8 characters).")); return; }
  $("attack-go").disabled = true;
  out.replaceChildren(h("p", { class: "muted" }, "Searching the live web..."));
  try {
    const r = await fetch("/api/attack", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ claim }) });
    const j = await r.json();
    out.replaceChildren(r.ok ? card(j) : h("p", { class: "banner" }, j.error || `Server answered ${r.status}`));
  } catch (e) { out.replaceChildren(h("p", { class: "banner" }, "Check failed: " + e.message)); }
  finally { $("attack-go").disabled = false; }
});
loadHealth(false);
