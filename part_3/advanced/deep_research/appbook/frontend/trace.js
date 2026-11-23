/* The run trace of one paper: its steps, and a log of everything that happened, kept up to date while it runs.
   Steps and decisions come from the ledger, model calls from the bill, tool calls from the researchers. */
const TRACE = { paper: null, data: null, events: [], busy: false, view: "steps", filter: "all", step: null, follow: true,
                max: false, el: null, slot: null, timer: null, poll: null, shown: 0 };

const STEP_NAMES = { scope: "Plan the paper", outline_review: "Outline approval", rescope: "Plan again", gather: "Research",
  tally: "Count the library", reflect: "Reflect on the evidence", organise: "Organise the evidence", write: "Write and check",
  review: "Review the draft", assemble: "Assemble the paper", publication_review: "Publication approval", publish: "Publish", close: "Close" };
const TYPE_NAMES = { step: "step", budget: "budget", model: "model", tool: "tool" };
const rtMoney = (n) => `$${Number(n || 0).toFixed(Number(n) < 0.1 ? 3 : 2)}`;
const rtClock = (ms) => { const s = Math.max(0, Math.round(ms / 1000)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
const rtSpan = (ms) => { const s = Math.round(ms / 1000); return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`; };
const rtList = (items, none = "none") => (items && items.length ? items.join(", ") : none);

/* One event, said in words. Returns [headline, the rest]. */
TRACE.say = (e) => {
  const d = e.detail ?? {};
  if (e.type === "model") {
    const t = e.tokens || {}; const sent = (t.fresh || 0) + (t.cache_write || 0) + (t.cache_read || 0);
    return [`Model call: ${e.kind}`, `${rtMoney(e.usd)} · ${e.seconds} s · ${sent.toLocaleString()} tokens in, ${(t.cache_read || 0).toLocaleString()} of them from the cache · ${(t.output || 0).toLocaleString()} out`];
  }
  if (e.type === "tool") {
    const a = e.arguments || {};
    const asked = { search_web: `“${a.query}”`, read_page: a.url, load_skill: a.name, recall: `${a.source_id}: “${a.question}”`,
      take_note: `${a.source_id} · ${a.kind}, relevance ${a.relevance}`, finish: `evidence is ${a.coverage}, ${(a.missing || []).length} gaps named` }[e.kind] || JSON.stringify(a);
    return [`Tool call: ${e.kind}`, `${asked}${e.kind === "finish" ? "" : ` → ${e.outcome}`}`];
  }
  if (e.type === "budget") return [`Budget decision: ${d.for}`, `asked for ${d.asked}, granted ${d.granted} · ${rtMoney(d.each_usd)} each · ${rtMoney(d.spent_usd)} spent and ${rtMoney(d.reserved_usd)} kept back, of ${rtMoney(d.budget_usd)}`];
  const k = `${e.step}/${e.kind}`;
  if (k === "scope/outline") return [`Planned ${d.length} sections`, d.map(s => s[1]).join(" · ")];
  if (e.kind === "decision" && e.step !== "reflect") return [`The person said: ${d.decision}`, d.note ? `Note: ${d.note}` : ""];
  if (k === "rescope/note") return ["Planning again", d ? `With the note: ${d}` : ""];
  if (k === "gather/sources") return [`Researcher finished: ${d.section}`, `round ${d.round} · ${d.turns} turns · ${d.kept} pages read · ${d.notes} notes · ${d.compactions} summaries · skills: ${rtList(d.skills)} · says the evidence is ${d.coverage}`];
  if (k === "gather/compaction") return [`Conversation summarised: ${d.section}`, `at turn ${d.turn}, when it had reached ${Number(d.tokens_before).toLocaleString()} tokens`];
  if (k === "tally/library") return ["The researchers have joined", `the library holds ${d.sources} sources and ${d.notes} notes`];
  if (k === "reflect/decision") return [`After round ${d.round}: ${d.decision}`, `thin sections: ${rtList(d.thin)}${Object.keys(d.searching || {}).length ? ` · going out again for: ${Object.keys(d.searching).join(", ")}` : ""}`];
  if (k === "organise/taxonomy") return ["Framework built", `${d.framework} · ${(d.categories || []).length} categories · ${d.compared} sources compared`];
  if (k === "organise/kept") return ["Framework already saved, kept", String(d)];
  if (k === "write/section") return [`Section written: ${d.key}`, `${d.words} words · ${d.citations} sources cited · ${d.claims} claims checked · ${d.repaired} repaired · ${d.removed} removed`];
  if (k === "review/verdict") return [`Referee says: ${d.verdict}`, `${(d.problems || []).length} of the harness's rules broken · writing again: ${rtList(d.revising, "nothing")}${d.summary ? ` · ${d.summary}` : ""}`];
  if (k === "assemble/paper") return ["Paper assembled", `${d.sections} sections · ${d.words} words · ${d.sources_cited} sources cited · ${d.kept} of ${d.checked} checked claims kept · release check ${d.release}`];
  if (k === "publish/files") return ["Published", `${d.file}${d.overridden ? " · by override" : ""} · ${d.lessons_remembered} guidelines remembered`];
  if (k === "close/closed") return ["Closed without publishing", String(d)];
  return [`${e.step}: ${e.kind}`, typeof d === "string" ? d : Object.entries(d).map(([key, v]) => `${key}: ${typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ")];
};

/* A call's row is written when the call ends, so it began that many seconds earlier. */
TRACE.began = (e) => new Date(e.at) - (e.type === "model" || e.type === "tool" ? (e.seconds || 0) * 1000 : 0);
TRACE.start = () => TRACE.events.length ? Math.min(...TRACE.events.slice(0, 5).map(TRACE.began)) : 0;

/* Consecutive events of one step are one run of that step. Research after a reflection is a new run of it. */
TRACE.steps = () => {
  const steps = [];
  TRACE.events.forEach((e, i) => {
    let s = steps[steps.length - 1];
    if (!s || s.step !== e.step) { s = { step: e.step, first: i, events: [], usd: 0, calls: 0, tools: 0 }; steps.push(s); }
    s.events.push(e); s.last = i; e.run = steps.length - 1;
    if (e.type === "model") { s.usd += e.usd || 0; s.calls += 1; }
    if (e.type === "tool") s.tools += 1;
  });
  const started = TRACE.start();
  steps.forEach((s, n) => {
    s.from = Math.max(0, Math.min(...s.events.map(TRACE.began)) - started); s.to = new Date(s.events[s.events.length - 1].at) - started;
    s.running = TRACE.busy && n === steps.length - 1;
    s.round = s.step === "gather" ? steps.slice(0, n + 1).filter(x => x.step === "gather").length : null;
  });
  return steps;
};

/* Inside research and writing, the work of each section, side by side. */
TRACE.lanes = (s) => {
  if (!["gather", "write"].includes(s.step)) return [];
  const lanes = new Map();
  for (const e of s.events) {
    const key = e.section || e.detail?.section || e.detail?.key; if (!key) continue;
    const lane = lanes.get(key) || { key, usd: 0, calls: 0, tools: {}, done: null, last: "" };
    if (e.type === "model") { lane.usd += e.usd || 0; lane.calls += 1; lane.last = e.kind; }
    if (e.type === "tool") lane.tools[e.kind] = (lane.tools[e.kind] || 0) + 1;
    if (e.type === "step" && ["sources", "section"].includes(e.kind)) lane.done = e.detail;
    lanes.set(key, lane);
  }
  return [...lanes.values()].map(l => {
    const t = l.tools; const state = l.done ? "done" : s.running ? "working" : "stopped";
    const doing = { section: "drafting", claims: "checking claims", repair: "repairing" }[l.last] || "working";
    const d = l.done || {};
    const text = s.step === "gather"
      ? (l.done ? `${d.turns} turns · ${(d.searches || []).length} searches · ${d.kept} pages · ${(d.skills || []).length} skills · ${d.notes} notes · ${d.compactions} summaries · says ${d.coverage}`
                : `${t.search_web || 0} searches · ${t.read_page || 0} pages · ${t.load_skill || 0} skills · ${t.take_note || 0} notes so far`)
      : l.done ? `${l.done.words} words · ${l.done.claims} claims checked · ${l.done.repaired} repaired` : doing;
    return { ...l, state, text };
  });
};

TRACE.skeleton = () => {
  const el = document.createElement("div"); el.className = "panel rt";
  el.innerHTML = `<div class="panel-head rt-head"><h2 class="panel-title">Run trace</h2><span class="rt-live" id="rt-live"></span><span class="rt-totals" id="rt-totals"></span>
      <span class="rt-tabs" role="tablist"><button data-view="steps" role="tab">Steps</button><button data-view="log" role="tab">Log</button></span>
      <button class="rt-size" id="rt-size"></button></div>
    <div class="rt-body"><div class="rt-steps" id="rt-steps"></div>
      <div class="rt-logpane"><div class="rt-bar"><span class="rt-filters" id="rt-filters"></span><label class="rt-follow"><input type="checkbox" id="rt-follow" checked /> Follow the newest</label></div><div class="rt-log" id="rt-log"></div></div></div>`;
  el.querySelectorAll("[data-view]").forEach(b => b.onclick = () => { TRACE.view = b.dataset.view; TRACE.render(); });
  el.querySelector("#rt-size").onclick = () => TRACE.maximise(!TRACE.max);
  el.querySelector("#rt-follow").onchange = (ev) => { TRACE.follow = ev.target.checked; if (TRACE.follow) TRACE.render(); };
  el.querySelector("#rt-log").addEventListener("wheel", (ev) => { if (ev.deltaY < 0 && TRACE.follow) { TRACE.follow = false; el.querySelector("#rt-follow").checked = false; } }, { passive: true });
  return el;
};

TRACE.maximise = (on) => {
  TRACE.max = on;
  document.querySelector(".rt-backdrop")?.remove();
  if (on) {
    const shade = document.createElement("div"); shade.className = "rt-backdrop"; shade.onclick = () => TRACE.maximise(false);
    document.body.append(shade, TRACE.el);
    if (TRACE.slot) TRACE.slot.innerHTML = `<div class="panel"><div class="panel-body faint">The run trace is open full screen. Press Esc to bring it back here.</div></div>`;
  } else if (TRACE.slot?.isConnected) { TRACE.slot.innerHTML = ""; TRACE.slot.append(TRACE.el); }
  else TRACE.el.remove();
  TRACE.render();
};
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && TRACE.max) TRACE.maximise(false); });

/* Called each time the page is drawn: put the trace in its place and point it at the selected paper. */
TRACE.mount = (slot, paperId, data) => {
  TRACE.el = TRACE.el || TRACE.skeleton(); TRACE.slot = slot; TRACE.data = data;
  if (TRACE.max) slot.innerHTML = `<div class="panel"><div class="panel-body faint">The run trace is open full screen. Press Esc to bring it back here.</div></div>`;
  else slot.append(TRACE.el);
  if (paperId !== TRACE.paper) { TRACE.paper = paperId; TRACE.events = []; TRACE.step = null; TRACE.shown = 0; TRACE.follow = true; TRACE.el.querySelector("#rt-follow").checked = true; }
  if (TRACE.wantMax) { TRACE.wantMax = false; if (!TRACE.max) return TRACE.maximise(true), TRACE.load(); }
  TRACE.render(); TRACE.load();
};
TRACE.unmount = () => { clearTimeout(TRACE.timer); clearTimeout(TRACE.poll); document.querySelector(".rt-backdrop")?.remove(); TRACE.el?.remove(); TRACE.max = false; TRACE.slot = null; };
TRACE.soon = (paperId) => { if (paperId !== TRACE.paper) return; clearTimeout(TRACE.timer); TRACE.timer = setTimeout(TRACE.load, 350); };
TRACE.load = async () => {
  clearTimeout(TRACE.poll);
  if (!TRACE.paper) { TRACE.events = []; TRACE.busy = false; return TRACE.render(); }
  const asked = TRACE.paper;
  try { const got = await APP.api(`/api/papers/${asked}/trace`); if (asked !== TRACE.paper) return; TRACE.events = got.events; TRACE.busy = got.busy; } catch (e) { return; }
  TRACE.render();
  if (TRACE.busy && TRACE.el.isConnected) TRACE.poll = setTimeout(TRACE.load, 4000);      // a safety net under the live events
};

TRACE.render = () => {
  const el = TRACE.el; if (!el) return;
  const events = TRACE.events, steps = TRACE.steps(), data = TRACE.data || {};
  const started = TRACE.start(), ended = events.length ? new Date(events[events.length - 1].at) : 0;
  el.classList.toggle("rt-max", TRACE.max); el.dataset.view = TRACE.view;
  el.querySelector("#rt-size").textContent = TRACE.max ? "Close ✕" : "Maximise ⤢";
  el.querySelector("#rt-size").title = TRACE.max ? "Back to the page (Esc)" : "Open the trace full screen";
  el.querySelectorAll("[data-view]").forEach(b => b.classList.toggle("on", b.dataset.view === TRACE.view));
  const waiting = !TRACE.busy && data.waiting_for_person, stopped = !TRACE.busy && data.status === "interrupted";
  el.querySelector("#rt-live").innerHTML = TRACE.busy ? `<i class="rt-dot on"></i>live` : waiting ? `<i class="rt-dot wait"></i>waiting for you` : stopped ? `<i class="rt-dot bad"></i>stopped` : `<i class="rt-dot"></i>${events.length ? "at rest" : "no run"}`;
  const calls = events.filter(e => e.type === "model"), tools = events.filter(e => e.type === "tool");
  el.querySelector("#rt-totals").textContent = events.length ? `${rtSpan(ended - started)} · ${calls.length} model calls · ${tools.length} tool calls · ${rtMoney(calls.reduce((n, e) => n + (e.usd || 0), 0))}` : "";

  /* steps */
  const box = el.querySelector("#rt-steps"), at = box.scrollTop;
  const tail = waiting ? `<div class="rt-step wait"><i class="rt-mark"></i><div class="rt-step-main"><div class="rt-step-top"><strong>${esc(STEP_NAMES[(data.next || [])[0]] || "A person decides")}</strong><span class="rt-node">${esc((data.next || []).join(", "))}</span></div><div class="rt-sum">The run has stopped and is saved. It carries on when you decide.</div></div></div>`
    : stopped ? `<div class="rt-step bad"><i class="rt-mark"></i><div class="rt-step-main"><div class="rt-step-top"><strong>Stopped inside ${esc((data.resume_from || []).join(", "))}</strong></div><div class="rt-sum">What finished was kept. Continue the run to carry on from its last checkpoint.</div></div></div>` : "";
  box.innerHTML = steps.map((s, n) => {
    const inLanes = ["gather", "write"].includes(s.step) ? ["sources", "compaction", "section"] : [];
    const lines = s.events.filter(e => e.type !== "model" && e.type !== "tool" && !inLanes.includes(e.kind)).map(e => { const [head, rest] = TRACE.say(e); return `<div class="rt-sum"><b>${esc(head)}</b>${rest ? ` · ${esc(rest)}` : ""}</div>`; }).join("");
    const lanes = TRACE.lanes(s).map(l => `<div class="rt-lane ${l.state}"><span class="rt-lane-key">${esc(l.key)}</span><span>${esc(l.text)}</span><span class="rt-lane-end">${l.calls} calls · ${rtMoney(l.usd)} · ${l.state}</span></div>`).join("");
    return `<div class="rt-step ${s.running ? "now" : "done"} ${TRACE.step === n ? "picked" : ""}" data-step="${n}" tabindex="0" role="button" aria-pressed="${TRACE.step === n}"><i class="rt-mark"></i><div class="rt-step-main">
      <div class="rt-step-top"><strong>${esc(STEP_NAMES[s.step] || s.step)}${s.round ? ` · round ${s.round}` : ""}</strong><span class="rt-node">${esc(s.step)}</span>
        <span class="rt-when">${rtClock(s.from)} → ${s.running ? "now" : rtClock(s.to)}${s.calls ? ` · ${s.calls} model calls` : ""}${s.tools ? ` · ${s.tools} tool calls` : ""}${s.usd ? ` · ${rtMoney(s.usd)}` : ""}</span></div>
      ${lines}${lanes ? `<div class="rt-lanes">${lanes}</div>` : ""}</div></div>`;
  }).join("") + tail || APP.empty("No steps yet. Plan a paper, or choose one from the list.");
  box.scrollTop = at;
  box.querySelectorAll("[data-step]").forEach(node => { const pick = () => { const n = Number(node.dataset.step); TRACE.step = TRACE.step === n ? null : n; if (!TRACE.max) TRACE.view = "log"; TRACE.render(); }; node.onclick = pick; node.onkeydown = (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); pick(); } }; });

  /* log */
  const kinds = [["all", "Everything"], ["step", "Steps and decisions"], ["model", "Model calls"], ["tool", "Tool calls"]];
  const picked = TRACE.step !== null && steps[TRACE.step] ? steps[TRACE.step] : null;
  el.querySelector("#rt-filters").innerHTML = kinds.map(([id, name]) => `<button data-filter="${id}" class="${TRACE.filter === id ? "on" : ""}">${name}</button>`).join("")
    + (picked ? `<button class="rt-clear" id="rt-clear" title="Show every step">${esc(STEP_NAMES[picked.step] || picked.step)}${picked.round ? ` · round ${picked.round}` : ""} ✕</button>` : "");
  el.querySelectorAll("[data-filter]").forEach(b => b.onclick = () => { TRACE.filter = b.dataset.filter; TRACE.render(); });
  const clear = el.querySelector("#rt-clear"); if (clear) clear.onclick = () => { TRACE.step = null; TRACE.render(); };
  const log = el.querySelector("#rt-log"), was = log.scrollTop;
  const rows = events.map((e, i) => ({ e, i })).filter(({ e }) => (TRACE.filter === "all" || (TRACE.filter === "step" ? ["step", "budget"].includes(e.type) : e.type === TRACE.filter)) && (!picked || e.run === TRACE.step));
  log.innerHTML = rows.map(({ e, i }) => { const [head, rest] = TRACE.say(e); const section = e.section || e.detail?.section || "";
    return `<div class="rt-row ${e.type} ${i >= TRACE.shown && TRACE.shown ? "new" : ""}"><time>${rtClock(new Date(e.at) - started)}</time><span class="rt-type">${TYPE_NAMES[e.type]}</span>
      <div><div class="rt-row-top"><b>${esc(head)}</b><span class="rt-node">${esc(e.step)}${section && e.type !== "step" ? ` · ${esc(section)}` : ""}</span></div>${rest ? `<p>${esc(rest)}</p>` : ""}</div></div>`; }).join("")
    || APP.empty(events.length ? "Nothing of this kind in this step." : "Nothing has happened yet.");
  log.scrollTop = TRACE.follow ? log.scrollHeight : was;
  TRACE.shown = events.length;
};

/* A small card that follows the working paper on every page. The run itself lives on the server,
   so it carries on whichever chapter is open; this only keeps it in view. */
const PROGRESS = { el: null, state: null, hidden: null, timer: null, tick: null };
const MILESTONES = ["scope", "outline_review", "gather", "reflect", "organise", "write", "review", "assemble", "publication_review", "publish"];
const MILESTONE_OF = { rescope: "scope", tally: "gather", close: "publish" };

PROGRESS.soon = () => { clearTimeout(PROGRESS.timer); PROGRESS.timer = setTimeout(PROGRESS.load, 500); };
PROGRESS.load = async () => {
  clearTimeout(PROGRESS.tick);
  try { PROGRESS.state = (await APP.api(`/api/progress?paper_id=${encodeURIComponent(APP.paper.id || "")}`)).paper; } catch (e) { return; }
  PROGRESS.render();
  if (PROGRESS.state?.busy) PROGRESS.tick = setTimeout(PROGRESS.load, 3000);
};
PROGRESS.open = (full) => {
  const p = PROGRESS.state; if (!p) return;
  APP.selectPaper(p.paper_id); TRACE.wantMax = !!full;
  if (location.hash === "#paper" || location.hash === "") APP.renderStage(); else location.hash = "paper";
};
PROGRESS.render = () => {
  const p = PROGRESS.state;
  const worth = p && (p.busy || p.waiting_for_person || p.status === "interrupted" || p.error);
  const key = p ? `${p.paper_id}|${p.busy}|${p.status}|${(p.next || []).join()}` : "";
  if (PROGRESS.hidden && PROGRESS.hidden !== key) PROGRESS.hidden = null;       // a new state brings the card back
  if (!worth || PROGRESS.hidden === key) { PROGRESS.el?.remove(); return; }
  if (!PROGRESS.el) { PROGRESS.el = document.createElement("aside"); PROGRESS.el.className = "run-card"; PROGRESS.el.setAttribute("aria-label", "The paper being written"); PROGRESS.el.setAttribute("aria-live", "polite"); }
  if (!PROGRESS.el.isConnected) document.body.append(PROGRESS.el);
  const step = p.busy ? (p.last?.step || "scope") : (p.next || [])[0] || (p.resume_from || [])[0] || p.last?.step;
  const at = MILESTONES.indexOf(MILESTONE_OF[step] || step);
  const state = p.error ? "bad" : p.busy ? "on" : p.waiting_for_person ? "wait" : "bad";
  const head = p.error ? "The run stopped with an error" : p.busy ? "Writing a survey" : p.waiting_for_person ? "Waiting for you" : "The run stopped part-way";
  const doing = p.error ? p.error : p.waiting_for_person && !p.busy ? `${STEP_NAMES[step] || step}: the run is saved and carries on when you decide.`
    : !p.busy ? `Stopped inside ${(p.resume_from || []).join(", ")}. What finished was kept.`
    : `${STEP_NAMES[step] || step}${p.last?.section_key ? ` · ${p.last.section_key}` : ""}${p.last && p.last.type !== "step" ? ` · ${p.last.type === "tool" ? "tool" : "model"} call: ${p.last.kind}` : ""}`;
  PROGRESS.el.dataset.state = state;
  PROGRESS.el.innerHTML = `<div class="run-top"><i class="rt-dot ${state}"></i><strong>${esc(head)}</strong>${p.seconds != null ? `<time>${rtClock(p.seconds * 1000)}</time>` : ""}<button class="run-x" title="Hide until something changes" aria-label="Hide this card">✕</button></div>
    <div class="run-title" title="${esc(p.title)}">${esc(p.title)}</div>
    <div class="run-bar" role="progressbar" aria-valuemin="0" aria-valuemax="${MILESTONES.length}" aria-valuenow="${Math.max(0, at)}">${MILESTONES.map((m, i) => `<i class="${i < at ? "done" : i === at ? "now" : ""}" title="${esc(STEP_NAMES[m])}"></i>`).join("")}</div>
    <div class="run-doing">${esc(doing)}</div>
    <div class="run-foot"><span>${p.calls} model calls · ${p.tool_calls} tool calls · ${p.sources} pages · $${Number(p.usd).toFixed(2)} of $${Number(p.budget_usd).toFixed(2)}</span></div>
    <div class="run-acts"><button class="secondary small" data-go="paper">${p.waiting_for_person && !p.busy ? "Decide" : "Open the paper"}</button><button class="secondary small" data-go="trace">Open the trace</button></div>`;
  PROGRESS.el.querySelector(".run-x").onclick = () => { PROGRESS.hidden = key; PROGRESS.render(); };
  PROGRESS.el.querySelectorAll("[data-go]").forEach(b => b.onclick = () => PROGRESS.open(b.dataset.go === "trace"));
};
/* Listeners that outlive a change of chapter. */
PROGRESS.start = () => {
  for (const topic of ["ledger", "trace", "paper"]) APP.listeners.set(topic, [...(APP.listeners.get(topic) || []), PROGRESS.soon]);
  window.addEventListener("hashchange", PROGRESS.soon);
  PROGRESS.load();
};
