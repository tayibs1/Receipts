// End-to-end browser test: drives a real headless Edge over the DevTools protocol.
// No packages needed (Node's built-in WebSocket). Needs the app running on 8765.
//
//   node tests/e2e_browser.mjs [outDir]
//
// It renders the page, runs the labelled sample briefing through the live app,
// opens the evidence drawer, toggles the diff, runs attack mode, and fails on any
// page error or console error. Screenshots go to outDir (default: %TEMP%\receipts_e2e).
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const APP = process.env.RECEIPTS_URL || "http://127.0.0.1:8765";
const OUT = process.argv[2] || path.join(os.tmpdir(), "receipts_e2e");
const EDGE = process.env.EDGE || "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const PORT = 9333;
fs.mkdirSync(OUT, { recursive: true });
const profile = fs.mkdtempSync(path.join(os.tmpdir(), "receipts_edge_"));
const edge = spawn(EDGE, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
  "--no-first-run", "--disable-extensions", "--window-size=1440,900", "about:blank"], { stdio: "ignore" });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const problems = [];
const steps = [];
const ok = (name, cond, detail = "") => { steps.push(`${cond ? "PASS" : "FAIL"} ${name}${detail ? ": " + detail : ""}`); if (!cond) problems.push(name); };

async function json(url, method = "GET") {
  for (let i = 0; i < 50; i++) {
    try { const r = await fetch(url, { method }); return await r.json(); } catch { await sleep(200); }
  }
  throw new Error("Edge DevTools did not start");
}

let ws, seq = 0;
const pending = new Map();
function cdp(method, params = {}) {
  const id = ++seq;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject, method }));
}
async function evaluate(expr) {
  const r = await cdp("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error("evaluate failed: " + (r.exceptionDetails.exception?.description || r.exceptionDetails.text));
  return r.result.value;
}
async function waitFor(expr, ms, label) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if (await evaluate(expr)) return true; await sleep(300); }
  throw new Error("timed out waiting for " + label);
}
async function shot(name) {
  const m = await cdp("Page.getLayoutMetrics");
  const h = Math.min(Math.ceil(m.cssContentSize.height), 6000);
  const r = await cdp("Page.captureScreenshot", { format: "png", captureBeyondViewport: true, clip: { x: 0, y: 0, width: 1440, height: h, scale: 1 } });
  const file = path.join(OUT, name + ".png");
  fs.writeFileSync(file, Buffer.from(r.data, "base64"));
  return file;
}
const click = (sel) => evaluate(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) return false; e.click(); return true; })()`);

try {
  await json(`http://127.0.0.1:${PORT}/json/version`);
  const target = await json(`http://127.0.0.1:${PORT}/json/new?about:blank`, "PUT");
  ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.id && pending.has(msg.id)) {
      const p = pending.get(msg.id); pending.delete(msg.id);
      msg.error ? p.reject(new Error(p.method + ": " + msg.error.message)) : p.resolve(msg.result);
    } else if (msg.method === "Runtime.exceptionThrown") {
      problems.push("page exception: " + (msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text));
    } else if (msg.method === "Runtime.consoleAPICalled" && msg.params.type === "error") {
      problems.push("console error: " + msg.params.args.map((a) => a.value ?? a.description).join(" "));
    } else if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error") {
      problems.push("browser log error: " + msg.params.entry.text + " " + (msg.params.entry.url || ""));
    }
  };
  await cdp("Runtime.enable"); await cdp("Page.enable"); await cdp("Log.enable");
  await cdp("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });

  // 1. input view and health badges
  await cdp("Page.navigate", { url: APP + "/" });
  await waitFor(`document.getElementById("badge-linkup") && !/checking/.test(document.getElementById("badge-linkup").textContent)`, 60000, "health badges");
  const badges = await evaluate(`[...document.querySelectorAll(".badges .badge:not([hidden])")].map(b => b.textContent).join(" | ")`);
  ok("health badges show live", /Anthropic: live/.test(badges) && /Linkup: live/.test(badges), badges);
  await shot("01-input");

  // 2. sample run
  ok("sample button", await click("#sample"));
  await waitFor(`document.getElementById("briefing").value.length > 100`, 10000, "sample text");
  ok("sample note shown", /deliberately out of date/.test(await evaluate(`document.getElementById("sample-note").textContent`)));
  ok("start run", await click("#go"));
  await waitFor(`document.querySelectorAll("#live-cards .card").length >= 1`, 120000, "first live card");
  await shot("02-running");
  await waitFor(`!document.getElementById("result").hidden`, 300000, "result");
  await sleep(800);
  const counts = await evaluate(`document.getElementById("counts").textContent`);
  ok("counts bar", /claims checked, ranked by impact/.test(counts), counts);
  ok("sample flag on result", !(await evaluate(`document.getElementById("sample-flag").hidden`)));
  const groups = await evaluate(`[...document.querySelectorAll("#live-cards .group-h")].map(h => h.textContent.trim())`);
  ok("result groups", groups.length >= 1, groups.join(", "));
  ok("mode badge", !(await evaluate(`document.getElementById("badge-mode").hidden`)), await evaluate(`document.getElementById("badge-mode").textContent`));
  ok("trace lines", (await evaluate(`document.querySelectorAll("#trace li").length`)) >= 3);
  const banner = await evaluate(`document.getElementById("banner").hidden ? "" : document.getElementById("banner").textContent`);
  ok("no error banner", !banner || /budget/.test(banner), banner);
  await shot("03-result");

  // 3. evidence drawer
  ok("open evidence", await click("#live-cards .card .actions button"));
  await waitFor(`!document.getElementById("drawer").hidden`, 5000, "drawer");
  ok("drawer lists rules", (await evaluate(`document.querySelectorAll("#drawer-body .rules li").length`)) >= 1);
  await shot("04-drawer");
  await click("#drawer-close");
  ok("drawer closes", await evaluate(`document.getElementById("drawer").hidden`));

  // 4. rewrite and diff
  ok("rewrite panel", !(await evaluate(`document.getElementById("rewrite").hidden`)));
  ok("verified text", (await evaluate(`document.getElementById("verified").textContent.length`)) > 100);
  const unsafe = await evaluate(`[...document.querySelectorAll("a[href]")].filter(a => /^\\s*(javascript|data):/i.test(a.getAttribute("href"))).length`);
  ok("no unsafe links", unsafe === 0, String(unsafe));
  await evaluate(`document.getElementById("rewrite").scrollIntoView()`);
  await click("#tab-diff");
  ok("diff view", !(await evaluate(`document.getElementById("diff").hidden`)) && (await evaluate(`document.querySelectorAll("#diff .removed, #diff .added").length`)) > 0);
  await shot("05-diff");
  await click("#tab-verified");

  // 5. attack mode
  await evaluate(`document.getElementById("attack-claim").value = "Anthropic was founded in 2021"`);
  await click("#attack-go");
  await waitFor(`document.querySelector("#attack-out .card") || document.querySelector("#attack-out .banner")`, 120000, "attack result");
  const attack = await evaluate(`document.getElementById("attack-out").textContent`);
  ok("attack mode returns a card", await evaluate(`!!document.querySelector("#attack-out .card")`), attack.slice(0, 120));
  await shot("06-attack");

  // 6. labelling page renders (read only: nothing is clicked, so no label is written)
  await cdp("Page.navigate", { url: APP + "/label.html" });
  await waitFor(`document.querySelectorAll("#rows .lrow").length > 0 || !document.getElementById("banner").hidden`, 15000, "label rows");
  const rows = await evaluate(`document.querySelectorAll("#rows .lrow").length`);
  ok("label page lists claims", rows > 0, `${rows} rows`);
  ok("label page shows no verdict", !(await evaluate(`/supported|contradicted|unverified/i.test(document.getElementById("rows").textContent)`)));
  await shot("07-label");

  // 7. narrow screen
  await cdp("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await cdp("Page.navigate", { url: APP + "/" });
  await sleep(1500);
  const overflow = await evaluate(`document.documentElement.scrollWidth - window.innerWidth`);
  ok("no horizontal overflow at 390px", overflow <= 1, `${overflow}px`);
} catch (e) {
  problems.push("error: " + e.message);
} finally {
  console.log(steps.join("\n"));
  console.log(problems.length ? "\nPROBLEMS:\n- " + problems.join("\n- ") : "\nALL PASSED");
  console.log("screenshots:", OUT);
  try { ws && ws.close(); } catch {}
  edge.kill();
  await sleep(500);
  try { fs.rmSync(profile, { recursive: true, force: true }); } catch {}
  process.exit(problems.length ? 1 : 0);
}
