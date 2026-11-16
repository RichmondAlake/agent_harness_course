/* The assistant workspace and the components the chapters share with it. */
PPA.ui = {};

/* ── Shared components ──────────────────────────────────────────────────── */
PPA.ui.riskTone = (level) => ({ high: "bad", review: "warn", normal: "good" }[level] || "");
PPA.ui.flag = (flag) => {
  const text = flag.flag === "recipient" ? `${flag.recipient}: ${flag.reasons.join(", ").replaceAll("_", " ")}` : `${flag.flag.replaceAll("_", " ")}: ${flag.detail}`;
  return PPA.pill(text, flag.flag === "recipient" || flag.flag === "quarantined_thread" ? "bad" : "warn");
};
PPA.ui.payload = (action) => {
  const p = action.payload, rows = [];
  if (p.to) rows.push(["To", [...p.to, ...(p.cc || []).map(c => `cc ${c}`)].join(", ")]);
  if (p.subject) rows.push(["Subject", p.subject]);
  if (p.title) rows.push(["Title", p.title]);
  if (p.start) rows.push(["When", `${PPA.dayTime(p.start)} to ${PPA.time(p.end)}`]);
  if (p.attendees?.length) rows.push(["Attendees", p.attendees.join(", ")]);
  if (p.event_id) rows.push(["Event", p.event_id]);
  if (p.response) rows.push(["Response", p.response]);
  if (p.page_id) rows.push(["Page", p.page_id]);
  if (p.thread_id) rows.push(["Thread", p.thread_id]);
  const body = p.body || p.text || p.description || p.comment;
  return `<dl class="kv">${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>${body ? `<pre class="json" style="margin-top:9px;max-height:200px">${esc(body)}</pre>` : ""}`;
};
/* One drafted action. `choice` is the decision picked so far, before it is submitted. */
PPA.ui.approvalCard = (action, choice) => {
  const risk = action.risk || {}, decided = action.state !== "DRAFTED";
  return `<article class="approval-card ${risk.level === "high" ? "high" : ""} ${decided ? "decided" : ""}" data-action-id="${esc(action.action_id)}">
    <header><strong>${esc(action.summary)}</strong><span>${PPA.pill(decided ? action.state : "needs your decision", decided ? PPA.stateTone(action.state) : "warn")}</span></header>
    <p class="why"><span class="mono">${esc(action.tool_name)}</span>${action.reason ? " · " + esc(action.reason) : ""}</p>
    <div class="flags">${PPA.pill("risk: " + (risk.level || "not assessed"), PPA.ui.riskTone(risk.level))}${(risk.flags || []).map(PPA.ui.flag).join("")}${risk.safe_mode_effect ? PPA.pill(risk.safe_mode_effect, risk.safe_mode_effect.includes("off") ? "bad" : "") : ""}</div>
    <details><summary>What would be sent or written</summary>${PPA.ui.payload(action)}</details>
    ${decided ? `<div class="decide"><span class="mono muted">${esc(action.delivery || action.state)}</span></div>`
      : `<div class="decide"><button class="${choice === "approve" ? "primary" : "secondary"} small" data-decide="approve">Approve</button><button class="${choice === "reject" ? "danger-button" : "secondary"} small" data-decide="reject">Reject</button><span class="mono faint">${esc(action.action_id)}</span></div>`}
  </article>`;
};
/* Gateway calls behind one tool call, grouped: "mail_get_thread x25 (310 ms, 3 from the read cache)". */
PPA.ui.mcp = (calls) => {
  const groups = new Map();
  for (const call of calls) {
    const g = groups.get(call.tool) || { count: 0, ms: 0, cached: 0 };
    g.count += 1; g.ms += call.ms; g.cached += call.cached ? 1 : 0; groups.set(call.tool, g);
  }
  return [...groups].map(([tool, g]) => `${tool}${g.count > 1 ? " x" + g.count : ""} (${Math.round(g.ms)} ms${g.cached ? `, ${g.cached} from the read cache` : ""})`).join(", ");
};
PPA.ui.trace = (trace) => {
  if (!trace?.spans) return "";
  const tokens = trace.tokens || {};
  const spans = trace.spans.map(span => {
    const a = span.attributes || {}, tone = span.kind === "model" ? "model" : span.kind === "approval" ? "approval" : a.ok === false ? "bad" : "";
    const detail = span.kind === "model" ? `${a.input_tokens || 0} in, ${a.output_tokens || 0} out${a.cache_read_tokens ? `, ${a.cache_read_tokens} cached` : ""}${a.stop_reason ? ` · ${a.stop_reason}` : ""}`
      : span.kind === "tool" ? `${a.tier}${a.decision ? " · " + a.decision : ""}${(a.mcp || []).length ? ` · MCP: ${PPA.ui.mcp(a.mcp)}` : ""}`
      : span.kind === "approval" ? "waited for a person" : Object.entries(a).map(([k, v]) => `${k} ${v}`).join(", ");
    return `<li><i class="${tone}"></i><span>${esc(span.name)} <span class="sub">${esc(detail)}</span></span><em>${esc(PPA.ms(span.ms))}</em></li>`;
  }).join("");
  return `<div class="row" style="gap:6px;margin:4px 0 8px">${PPA.pill(`${trace.model_calls} model call${trace.model_calls === 1 ? "" : "s"}`)}${PPA.pill(`${trace.tool_calls.length} tool calls`)}${PPA.pill(`${PPA.number(tokens.total)} tokens`)}${PPA.pill(PPA.ms(trace.latency_ms))}${trace.approval_wait_ms ? PPA.pill(`approval wait ${PPA.ms(trace.approval_wait_ms)}`, "warn") : ""}</div><ul class="steps">${spans}</ul>`;
};
/* Where a calendar event came from: an invitation in the mailbox, or the generated layer. */
PPA.ui.source = (source) => `<span class="pill source ${source === "generated" ? "warn" : ""}" title="${source === "generated" ? "A working session placed by rule. It did not come from an invitation." : "Derived from an invitation that arrived by mail."}">${esc(source)}</span>`;
PPA.ui.agenda = (agenda) => {
  if (agenda.error) return PPA.fail(agenda.error);
  const broken = new Set((agenda.meeting_rule_violations || []).map(e => e.event_id));
  const events = (agenda.events || []).map(e => `<li class="${broken.has(e.event_id) ? "flag" : ""}"><span class="time">${esc(PPA.time(e.start))}</span><div><strong>${esc(e.title)}</strong><small>${esc(PPA.time(e.start))} to ${esc(PPA.time(e.end))} · ${esc(e.kind)} · ${esc(e.event_id)}${e.response ? " · " + esc(e.response) : ""}${e.source ? " " + PPA.ui.source(e.source) : ""}</small>${broken.has(e.event_id) ? `<small>Breaks the no-meetings-before-${esc(agenda.rules.no_meetings_before)} rule</small>` : ""}</div>${e.kind === "meeting" ? `<button class="secondary small" data-prep="${esc(e.event_id)}">Prep</button>` : "<span></span>"}</li>`).join("");
  const free = (agenda.free_slots || []).map(s => `${s.start_local} to ${s.end_local}`).join(", ");
  return `<ul class="items">${events || `<li><span></span>${PPA.empty("No events today.")}<span></span></li>`}</ul><div class="pad mono muted">Free for focus: ${esc(free || "none")}${agenda.load ? ` · ${agenda.load.meeting_minutes} meeting minutes${agenda.load.overbooked ? " (over-booked)" : ""}` : ""}</div>`;
};
PPA.ui.tasks = (tasks, { limit = 50 } = {}) => {
  const slipping = new Set(tasks.slipping), stale = new Set(tasks.stale);
  const row = (t, done) => `<li class="${done ? "done" : t.urgent ? "flag" : ""}" data-task="${esc(t.task_id)}">
    <button class="check" data-task-act="${done ? "reopen" : "complete"}" aria-label="${done ? "Reopen" : "Complete"} ${esc(t.title)}">${done ? "&#10003;" : ""}</button>
    <div><strong>${esc(t.title)}</strong><small>${esc(t.task_id)} · priority ${t.priority} · ${t.est_pomodoros} Pomodoro${t.est_pomodoros === 1 ? "" : "s"}${t.due_at ? " · due " + esc(PPA.dayTime(t.due_at)) : ""}${t.source_ref ? ` · from <button class="link-button" data-source="${esc(t.source_ref)}" data-source-type="${esc(t.source_type)}">${esc(t.source_ref)}</button>` : ""}</small>
    <small>${t.urgent ? PPA.pill("urgent", "warn") : ""}${slipping.has(t.task_id) ? PPA.pill(`slipping, carried over ${t.carry_over_count}x`, "bad") : ""}${stale.has(t.task_id) ? PPA.pill("stale: drop candidate") : ""}${t.snoozed ? PPA.pill("snoozed until " + PPA.dayTime(t.snoozed_until)) : ""}</small></div>
    <span class="row" style="gap:5px">${done ? "" : `<button class="secondary small" data-task-act="focus">Focus</button><button class="secondary small" data-task-act="${t.snoozed ? "wake" : "snooze"}">${t.snoozed ? "Wake" : "Snooze"}</button>`}</span></li>`;
  const open = tasks.open.slice(0, limit).map(t => row(t, false)).join(""), snoozed = tasks.snoozed.map(t => row(t, false)).join(""), done = tasks.done.slice(0, 5).map(t => row(t, true)).join("");
  return `<ul class="items">${open || `<li><span></span>${PPA.empty("No tasks yet. Triage the inbox or add one.")}<span></span></li>`}${snoozed}${done}</ul>`;
};
/* Wire the buttons of a task list. `refresh` redraws whatever holds the list. */
PPA.ui.bindTasks = (root, refresh) => {
  root.addEventListener("click", async (event) => {
    const source = event.target.closest("[data-source]");
    if (source) { if (source.dataset.sourceType === "mail") PPA.openThread(source.dataset.source); else PPA.toast("Source", `${source.dataset.sourceType}: ${source.dataset.source}`); return; }
    const button = event.target.closest("[data-task-act]");
    if (!button) return;
    const id = button.closest("[data-task]").dataset.task, act = button.dataset.taskAct;
    try {
      if (act === "focus") { const result = await PPA.post("/api/focus_sessions/start", { task_id: id }); PPA.toast(result.status === "started" ? "Focus session started" : "A session is already running", result.session.task_title || "", result.status === "started" ? "" : "warn"); }
      else await PPA.post(`/api/assistant/tasks/${encodeURIComponent(id)}/${act}`, act === "snooze" ? { hours: 24 } : {});
      await refresh();
    } catch (error) { PPA.toast("That did not work", error.message, "bad"); }
  });
};
PPA.ui.timers = (jobs) => `<ul class="items">${jobs.map(j => `<li><span class="time">${esc(j.kind.replaceAll("_", " "))}</span><div><strong>${esc(j.label)}</strong><small>${esc(j.job_id)} · fires ${esc(j.clock === "real" ? PPA.realTime(j.fires_at) + " real time" : PPA.dayTime(j.fires_at) + " harness clock")}</small></div>${PPA.ui.countdown(j)}</li>`).join("") || `<li><span></span>${PPA.empty("No timers or routines are armed.")}<span></span></li>`}</ul>`;
PPA.ui.countdown = (job) => job.state !== "ARMED" ? "<span></span>"
  : job.clock === "real" ? `<span class="countdown" data-until="${esc(job.fires_at)}">${PPA.duration(job.seconds_remaining)}</span>`
    : `<span class="countdown" title="Counts down on the harness clock, which moves when you move it" data-harness-seconds="${job.seconds_remaining}">${PPA.duration(job.seconds_remaining)}</span>`;
PPA.ui.triageTable = (data, { actions = true } = {}) => `<div class="table-wrap"><table class="list"><thead><tr><th class="num">Rank</th><th>Category</th><th>From</th><th>Subject</th><th>Signals</th>${actions ? "<th></th>" : ""}</tr></thead><tbody>${data.rows.map(r => `<tr class="clickable ${r.category === "quarantine" ? "quarantine" : ""}" data-thread="${esc(r.thread_id)}">
    <td class="num">${r.attention_rank}</td><td>${PPA.pill(r.category, PPA.categoryTone(r.category))}</td>
    <td><strong>${esc(r.from_name)}</strong><br><span class="mono faint">${esc(r.from_email)}</span></td>
    <td><strong>${esc(r.subject)}</strong><br><span class="faint">${esc(r.reason)}</span></td>
    <td>${r.vip ? PPA.pill("VIP", "strong") : ""}${r.direct ? PPA.pill("direct") : ""}${PPA.pill(r.trust, r.trust === "unknown" ? "warn" : "")}${r.tracked_task_id ? PPA.pill(r.tracked_task_id, "good") : ""}${r.injection_patterns.map(p => PPA.pill(p, "bad")).join("")}<br><span class="mono faint">${esc(PPA.dayTime(r.received_at))} · ${r.age_hours} h old</span></td>
    ${actions ? `<td>${r.proposal ? `<button class="secondary small" data-extract="${esc(r.thread_id)}">Extract</button>` : ""}</td>` : ""}</tr>`).join("")}</tbody></table></div>`;

/* ── Chat ───────────────────────────────────────────────────────────────── */
PPA.chat = { thread: sessionStorage.getItem("ppa-thread") || null, messages: [], pending: [], choices: {}, steps: [], running: false, responder: null };
PPA.chat.newThread = () => {
  const c = PPA.chat;
  c.thread = `thread-${Math.random().toString(36).slice(2, 12)}`;
  sessionStorage.setItem("ppa-thread", c.thread);
  Object.assign(c, { messages: [], pending: [], choices: {}, steps: [], responder: null });
};
PPA.chat.html = () => `<div class="chat panel" id="chat">
  <div class="panel-head"><h2 class="panel-title">Conversation</h2><div class="row"><span class="mono faint" id="chat-thread"></span><button class="secondary small" id="chat-new">New conversation</button></div></div>
  <div class="messages" id="chat-messages" aria-live="polite"></div>
  <div class="starters" id="chat-starters"></div>
  <form class="composer" id="chat-form"><textarea id="chat-input" placeholder="Ask the assistant" aria-label="Message"></textarea><button class="primary">Send</button></form>
</div>`;
PPA.chat.render = () => {
  const c = PPA.chat, box = $("#chat-messages");
  if (!box) return;
  $("#chat-thread").textContent = `${c.thread}${c.responder ? " · " + c.responder : ""}`;
  const messages = c.messages.map((m, index) => m.role === "user" ? `<div class="message user">${esc(m.content)}</div>`
    : m.role === "notice" ? `<div class="message notice-line">${esc(m.content)}</div>`
      : `<div class="message assistant"><div class="result-copy">${PPA.markdown(m.content)}</div><div class="message-meta"><span class="by">${esc(m.responder || "")}</span>${m.trigger && m.trigger !== "chat" ? PPA.pill(m.trigger) : ""}${m.trace ? `<span>${PPA.number(m.trace.tokens?.total)} tokens · ${esc(PPA.ms(m.trace.latency_ms))} · ${m.trace.tool_calls.length} tool calls</span><button class="link-button" data-trace="${index}">trace</button>` : ""}</div>${m.showTrace ? PPA.ui.trace(m.trace) : ""}</div>`).join("");
  const pending = c.pending.length ? `<div class="message notice-line">The run is paused. ${c.pending.length} drafted action${c.pending.length === 1 ? "" : "s"} need${c.pending.length === 1 ? "s" : ""} your decision.</div>${c.pending.map(a => PPA.ui.approvalCard(a, c.choices[a.action_id])).join("")}
    <div class="row" style="margin:10px 0"><button class="primary" id="submit-decisions" ${c.pending.every(a => c.choices[a.action_id]) ? "" : "disabled"}>Submit decisions and resume</button><button class="secondary small" data-all="approve">Approve all</button><button class="secondary small" data-all="reject">Reject all</button></div>
    <label class="decline-why" for="decline-note">If you reject, say why <span class="faint">(optional; kept with the turn as a correction)</span><input id="decline-note" maxlength="300" placeholder="For example: always check my calendar before you offer a time" value="${esc(c.note || "")}" /></label>` : "";
  const live = c.running ? `<div class="message assistant"><span class="loading">${c.steps.length ? "Working" : "Assembling context"}</span><ul class="steps">${c.steps.map(s => `<li><i class="${s.tone}"></i><span>${esc(s.text)}</span><em>${esc(s.ms ? PPA.ms(s.ms) : "")}</em></li>`).join("")}</ul></div>` : "";
  box.innerHTML = (messages || (c.pending.length || c.running ? "" : PPA.empty(`Ask for a morning brief, a triage of the inbox or a plan for the day. Answers come from ${PPA.status.responder.label}.`))) + pending + live;
  box.scrollTop = box.scrollHeight;
};
PPA.chat.onRun = (data) => {
  const c = PPA.chat;
  if (data.thread_id !== c.thread) return;
  if (!c.running) {
    /* The run moved on somewhere else, for example a decision made in the approvals chapter. */
    if (["completed", "awaiting_approval"].includes(data.phase)) PPA.chat.load().then(PPA.chat.render);
    return;
  }
  if (data.phase === "node") c.steps.push({ text: data.node, tone: "" });
  else if (data.phase === "model" && data.status === "start") c.steps.push({ text: `call_model, step ${data.iteration}`, tone: "model", open: true });
  else if (data.phase === "model") { const step = c.steps.findLast(s => s.open); if (step) Object.assign(step, { open: false, ms: data.ms, text: `${step.text}: ${data.tool_calls.length ? data.tool_calls.length + " tool calls" : "answer"}` }); }
  else if (data.phase === "tool") c.steps.push({ text: `${data.tool} (${data.tier})${data.status === "gated" ? ": needs approval" : ""}`, tone: data.status === "gated" ? "gated" : data.ok === false ? "bad" : "", ms: data.ms });
  else if (data.phase === "interrupt") c.steps.push({ text: "human_review: paused for approval", tone: "approval" });
  PPA.chat.render();
};
PPA.chat.settle = (outcome) => {
  const c = PPA.chat;
  c.responder = outcome.responder;
  c.pending = outcome.pending_actions || [];
  c.choices = {}; c.note = "";
  if (outcome.status === "completed") c.messages.push({ role: "assistant", content: outcome.answer, responder: outcome.responder, trigger: outcome.trigger, trace: outcome.trace });
};
PPA.chat.send = async (text) => {
  const c = PPA.chat;
  if (c.running || !text.trim()) return;
  if (c.pending.length) { PPA.toast("Decide the drafted actions first", "This conversation is paused at an approval gate.", "warn"); return; }
  c.messages.push({ role: "user", content: text.trim() });
  Object.assign(c, { running: true, steps: [] }); PPA.chat.render();
  try { PPA.chat.settle(await PPA.post("/api/assistant/turn", { message: text.trim(), thread_id: c.thread })); }
  catch (error) { c.messages.push({ role: "notice", content: `The request failed: ${error.message}` }); }
  c.running = false; PPA.chat.render(); PPA.chat.afterRun?.();
};
PPA.chat.resume = async () => {
  const c = PPA.chat, decisions = { ...c.choices };
  Object.assign(c, { running: true, steps: [{ text: "human_review: decisions recorded, resuming the same run", tone: "approval" }], pending: [] }); PPA.chat.render();
  try { PPA.chat.settle(await PPA.post("/api/assistant/resume", { thread_id: c.thread, decisions, note: Object.values(decisions).includes("reject") ? (c.note || "") : "" })); }
  catch (error) { c.messages.push({ role: "notice", content: `The run could not resume: ${error.message}` }); await PPA.chat.load(); }
  c.running = false; PPA.chat.render(); PPA.chat.afterRun?.();
};
PPA.chat.load = async () => {
  const c = PPA.chat;
  if (!c.thread) PPA.chat.newThread();
  try {
    const t = await PPA.api(`/api/assistant/thread/${encodeURIComponent(c.thread)}`);
    const traces = t.last_trace ? { [t.last_trace.run_id]: t.last_trace } : {};
    c.messages = t.messages.map(m => ({ role: m.role, content: m.content, responder: m.responder, trigger: m.trigger, trace: m.role === "assistant" ? traces[m.run_id] : null }));
    c.pending = t.pending_actions; c.responder = t.responder;
    if (t.waiting_for_approval && t.last_trace) c.messages.push({ role: "user", content: t.last_trace.request });
  } catch (error) { c.messages = [{ role: "notice", content: error.message }]; }
};
PPA.chat.mount = async (root, { starters = [], afterRun = null } = {}) => {
  root.innerHTML = PPA.chat.html();
  PPA.chat.afterRun = afterRun;
  $("#chat-starters").innerHTML = starters.map(s => `<button type="button">${esc(s)}</button>`).join("");
  $("#chat-starters").onclick = (event) => { if (event.target.matches("button")) PPA.chat.send(event.target.textContent); };
  $("#chat-form").onsubmit = (event) => { event.preventDefault(); const input = $("#chat-input"); PPA.chat.send(input.value); input.value = ""; };
  $("#chat-input").onkeydown = (event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); $("#chat-form").requestSubmit(); } };
  $("#chat-new").onclick = () => { PPA.chat.newThread(); PPA.chat.render(); };
  $("#chat-messages").oninput = (event) => { if (event.target.id === "decline-note") PPA.chat.note = event.target.value; };
  $("#chat-messages").onclick = (event) => {
    const c = PPA.chat, trace = event.target.closest("[data-trace]"), decide = event.target.closest("[data-decide]"), all = event.target.closest("[data-all]");
    if (trace) { const m = c.messages[Number(trace.dataset.trace)]; m.showTrace = !m.showTrace; PPA.chat.render(); }
    else if (decide) { c.choices[decide.closest("[data-action-id]").dataset.actionId] = decide.dataset.decide; PPA.chat.render(); }
    else if (all) { c.pending.forEach(a => { c.choices[a.action_id] = all.dataset.all; }); PPA.chat.resume(); }
    else if (event.target.closest("#submit-decisions")) PPA.chat.resume();
  };
  PPA.on("run", PPA.chat.onRun);
  await PPA.chat.load();
  PPA.chat.render();
};

/* ── The workspace ──────────────────────────────────────────────────────── */
PPA.register({
  id: "assistant", title: "Assistant",
  blurb: "One assistant over mail, calendar, notes and tasks. It reads on its own, asks before anything reaches another person, and keeps its timers and routines in view.",
  tags: ["Chat · approvals · agenda · tasks · triage · capture"],
  render: async (root) => {
    root.innerHTML = `<section class="workspace"><div class="stack"><div class="tabs" id="left-tabs"><button class="active" data-tab="chat">Conversation</button><button data-tab="inbox">Inbox triage</button></div><div id="left-chat"></div><div id="left-inbox" hidden></div></div>
      <aside class="stack rail">
        <div class="panel"><div class="panel-head"><h2 class="panel-title">Focus</h2><span class="mono faint" id="rail-session"></span></div><div class="panel-body" id="rail-focus"></div></div>
        <div class="panel"><div class="panel-head"><h2 class="panel-title">Today</h2><span class="mono faint" id="rail-day"></span></div><div class="panel-body" id="rail-agenda"></div></div>
        <div class="panel"><div class="panel-head"><h2 class="panel-title">Tasks</h2><span class="mono faint">governed order</span></div><div class="panel-body"><form class="pad row" id="task-form"><input id="task-title" placeholder="Add a task" aria-label="New task" /><button class="secondary small">Add</button></form><div id="rail-tasks"></div></div></div>
        <div class="panel"><div class="panel-head"><h2 class="panel-title">Day plan</h2><button class="secondary small" id="plan-edit">Edit</button></div><div class="panel-body" id="rail-plan"></div></div>
        <div class="panel"><div class="panel-head"><h2 class="panel-title">Quick capture</h2><span class="mono faint">/inbox</span></div><div class="panel-body"><form class="pad row" id="capture-form"><input id="capture-text" placeholder="Park a thought" aria-label="Quick capture" /><button class="secondary small">Capture</button></form><div id="rail-inbox"></div></div></div>
        <div class="panel"><div class="panel-head"><h2 class="panel-title">Timers and routines</h2><a class="link-button" href="#routines">all jobs</a></div><div class="panel-body" id="rail-timers"></div></div>
      </aside></section>`;
    const refresh = async () => {
      const s = await PPA.api("/api/assistant/status");
      if (!$("#rail-agenda")) return;
      $("#rail-day").textContent = PPA.day(s.clock.now);
      $("#rail-session").textContent = `${s.session.session_id} · ${s.session.status.toLowerCase().replace("_", " ")}`;
      $("#rail-agenda").innerHTML = PPA.ui.agenda(s.agenda);
      $("#rail-tasks").innerHTML = PPA.ui.tasks(s.tasks, { limit: 8 }) + (s.tasks.open.length > 8 ? `<div class="pad mono faint">${s.tasks.open.length - 8} more open tasks</div>` : "");
      $("#rail-plan").innerHTML = s.plan ? `<pre class="plan-text">${esc(s.plan)}</pre>` : PPA.empty("No plan yet. Ask the assistant to time-block the top tasks.");
      $("#rail-plan").dataset.plan = s.plan;
      $("#rail-inbox").innerHTML = `<ul class="items">${s.inbox.map(f => `<li><span class="time">${esc(f.kind)}</span><div><strong>${esc(f.content)}</strong><small>${esc(f.path)} · ${f.promotion_state === "N" ? "becomes a " + esc(f.promote_target) + " when the day ends" : "promotion state " + esc(f.promotion_state)}</small></div><label class="inline" title="Promote when the workday ends"><input type="checkbox" data-promote="${esc(f.path)}" ${f.promote_on_end ? "checked" : ""} ${f.promotion_state === "N" ? "" : "disabled"} /></label></li>`).join("") || `<li><span></span>${PPA.empty("Nothing captured today.")}<span></span></li>`}</ul>`;
      $("#rail-timers").innerHTML = PPA.ui.timers(s.timers);
      $("#rail-focus").innerHTML = s.focus
        ? `<div class="pad"><div class="big-countdown" data-until="${esc(s.focus.real_ends_at)}">${PPA.duration(s.focus.seconds_remaining)}</div><p class="action-copy" style="margin:8px 0 10px"><strong>${esc(s.focus.task_title || "Unplanned focus")}</strong><br><span class="mono faint">${esc(s.focus.session_id)} · ${s.focus.planned_minutes} minutes${s.focus.compressed ? " · compressed timer" : ""}</span></p><button class="secondary small" id="focus-stop">Stop early</button></div>`
        : `<div class="pad"><p class="action-copy" style="margin:0">No session running. Press Focus on a task, or ask the assistant to start a Pomodoro.</p></div>`;
      const stop = $("#focus-stop");
      if (stop) stop.onclick = async () => { await PPA.post("/api/focus_sessions/stop", { reason: "Stopped from the workspace." }); refresh(); };
    };
    PPA.ui.bindTasks($("#rail-tasks"), refresh);
    $("#rail-agenda").onclick = (event) => { const prep = event.target.closest("[data-prep]"); if (prep) { show("chat"); PPA.chat.send(`Prepare me for the meeting with event ID \`${prep.dataset.prep}\`.`); } };
    $("#task-form").onsubmit = async (event) => { event.preventDefault(); const input = $("#task-title"); if (!input.value.trim()) return; try { const made = await PPA.post("/api/assistant/tasks", { title: input.value }); if (made.status === "already_tracked") PPA.toast("Already tracked", made.message, "warn"); input.value = ""; refresh(); } catch (error) { PPA.toast("The task was not added", error.message, "bad"); } };
    $("#capture-form").onsubmit = async (event) => { event.preventDefault(); const input = $("#capture-text"); if (!input.value.trim()) return; await PPA.post("/api/memory_layer/capture", { text: input.value }); input.value = ""; refresh(); };
    $("#rail-inbox").onchange = async (event) => { const box = event.target.closest("[data-promote]"); if (box) { await PPA.post("/api/memory_layer/scratch/flag", { path: box.dataset.promote, promote: box.checked }); refresh(); } };
    $("#plan-edit").onclick = () => {
      const node = PPA.modal("Day plan: /plans/today.md", `<div class="panel-body"><textarea class="code" id="plan-text" style="min-height:260px">${esc($("#rail-plan").dataset.plan || "")}</textarea><div class="actions"><button class="primary" id="plan-save">Save</button></div></div>`);
      $("#plan-save", node).onclick = async () => { await PPA.api("/api/memory_layer/plan", { method: "PUT", body: JSON.stringify({ content: $("#plan-text", node).value }) }); node.remove(); refresh(); };
    };
    const loadInbox = async () => {
      const box = $("#left-inbox");
      box.innerHTML = `<div class="panel"><div class="panel-body">${'<span class="loading">Reading the inbox through MCP</span>'}</div></div>`;
      try {
        const data = await PPA.api("/api/inbox_triage/status");
        box.innerHTML = `<div class="panel"><div class="panel-head"><h2 class="panel-title">Inbox · ${data.window} threads</h2><div class="row">${Object.entries(data.counts).filter(([, n]) => n).map(([k, n]) => PPA.pill(`${k} ${n}`, PPA.categoryTone(k))).join("")}<button class="primary small" id="extract-all">Extract all actionable</button></div></div><div class="panel-body flush">${PPA.ui.triageTable(data)}</div></div>`;
        const extract = async (ids, button) => { try { const r = await PPA.busy(button, () => PPA.post("/api/inbox_triage/extract", { thread_ids: ids })); PPA.toast("Extraction finished", `${r.created.length} tasks created, ${r.suppressed_duplicates.length} duplicates suppressed, ${r.drafts.length} drafts saved, none sent.`); await loadInbox(); refresh(); } catch (error) { PPA.toast("Extraction failed", error.message, "bad"); } };
        $("#extract-all").onclick = (event) => extract([], event.currentTarget);
        $("table", box).onclick = (event) => { const button = event.target.closest("[data-extract]"); if (button) { event.stopPropagation(); extract([button.dataset.extract], button); return; } const row = event.target.closest("[data-thread]"); if (row) PPA.openThread(row.dataset.thread); };
      } catch (error) { box.innerHTML = PPA.fail(error); }
    };
    const show = (tab) => { $$("#left-tabs button").forEach(b => b.classList.toggle("active", b.dataset.tab === tab)); $("#left-chat").hidden = tab !== "chat"; $("#left-inbox").hidden = tab !== "inbox"; if (tab === "inbox") loadInbox(); };
    $("#left-tabs").onclick = (event) => { if (event.target.dataset.tab) show(event.target.dataset.tab); };
    const status = await PPA.api("/api/assistant/status");
    await PPA.chat.mount($("#left-chat"), { starters: status.starters, afterRun: refresh });
    await refresh();
    let queued = null;
    const soon = () => { clearTimeout(queued); queued = setTimeout(() => refresh().catch(() => {}), 250); };
    for (const topic of ["timer", "focus", "action", "clock", "notification"]) PPA.on(topic, soon);
  },
});
