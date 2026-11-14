/* Hand-labelling page. Shows claims and links only, never a verdict. */
"use strict";
const $ = (id) => document.getElementById(id);

function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) e.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return e;
}
const safeHref = (u) => (/^https?:\/\//i.test(u || "") ? u : "#");
function banner(t) { const b = $("banner"); b.textContent = t; b.hidden = !t; }

const who = $("who");
who.value = localStorage.getItem("labeller") || "";
who.addEventListener("input", () => localStorage.setItem("labeller", who.value.trim()));

let labelled = 0, total = 0;
function progress() { $("progress").textContent = `${labelled} of ${total} labelled`; }

async function save(row, el, label, notes) {
  const name = who.value.trim();
  if (!name) { banner("Enter your name at the top first: it is recorded as the labeller."); return false; }
  const had = !!row.label;
  const send = (change) => fetch("/api/label", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key: row.key, label, labeller: name, notes, change }) });
  let r = await send(false);
  if (r.status === 409) {
    if (!confirm((await r.json()).error + "\n\nChange it? This is logged.")) return false;
    r = await send(true);
  }
  const j = await r.json();
  if (!r.ok) { banner(j.error || `Server answered ${r.status}`); return false; }
  banner("");
  if (!had) labelled = j.labelled;
  row.label = label;
  el.classList.add("done");
  el.querySelector(".saved").textContent = "Saved";
  progress();
  return true;
}

function rowEl(row) {
  const el = h("div", { class: "lrow" + (row.label ? " done" : "") });
  const notes = h("input", { type: "text", placeholder: "Notes (optional): which page settled it", value: row.notes || "" });
  const opts = h("div", { class: "opts" });
  for (const v of ["true", "false", "unknowable"]) {
    const radio = h("input", { type: "radio", name: "l-" + row.key, value: v });
    if (row.label === v) radio.checked = true;
    radio.addEventListener("change", async () => {
      const ok = await save(row, el, v, notes.value);
      if (!ok) { radio.checked = false; const prev = el.querySelector(`input[value="${row.label}"]`); if (prev) prev.checked = true; }
    });
    opts.append(h("label", {}, radio, v));
  }
  opts.append(notes, h("span", { class: "saved" }, row.label ? "Saved" : ""));
  notes.addEventListener("change", () => { if (row.label) save(row, el, row.label, notes.value); });
  el.append(
    h("div", { class: "claim-text" }, `${row.company}: ${row.claim}`),
    // No system source is shown: whether Receipts found one would hint at its verdict.
    h("div", { class: "meta" },
      h("a", { href: safeHref(row.search_link), target: "_blank", rel: "noopener noreferrer" }, "Search the web")),
    opts);
  return el;
}

(async () => {
  try {
    const r = await fetch("/api/labels");
    const rows = await r.json();
    if (!r.ok) { banner(rows.error || "Could not load the claims."); return; }
    total = rows.length; labelled = rows.filter((x) => x.label).length; progress();
    $("rows").replaceChildren(...rows.map(rowEl));
    $("rows").style.display = "grid"; $("rows").style.gap = "16px";
  } catch (e) { banner("Could not reach the server: " + e.message); }
})();
