/* PPA custom-harness appbook: no-build shell. Chapters register themselves on PPA.chapters. */
const PPA = {
  chapters: [],
  status: null,
  listeners: new Map(),
  stageCleanups: [],
  notifications: [],
  unread: 0,
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* ── Formatting ─────────────────────────────────────────────────────────── */
PPA.zone = () => PPA.status?.owner?.timezone;
PPA.time = (iso) => iso ? new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: PPA.zone() }).format(new Date(iso)) : "";
PPA.day = (iso) => iso ? new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: PPA.zone() }).format(new Date(iso.length === 10 ? iso + "T12:00:00Z" : iso)) : "";
PPA.dayTime = (iso) => iso ? `${PPA.day(iso)} ${PPA.time(iso)}` : "";
PPA.realTime = (iso) => iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "";
PPA.duration = (seconds) => {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  if (h >= 24) return `${Math.floor(h / 24)}d ${h % 24}h`;
  return h ? `${h}h ${String(m).padStart(2, "0")}m` : `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
};
PPA.ms = (value) => value >= 1000 ? `${(value / 1000).toFixed(1)} s` : `${Math.round(value)} ms`;
PPA.number = (value) => Number(value || 0).toLocaleString("en-GB");
PPA.firstName = () => (PPA.status?.owner?.name || "the owner").split(" ")[0];

PPA.markdown = (text) => {
  const lines = esc(text).split("\n");
  let list = null, table = null, out = "";
  const inline = (raw) => raw.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`(.+?)`/g, "<code>$1</code>");
  const close = () => {
    if (list) { out += `</${list}>`; list = null; }
    if (table) {
      const [head, ...body] = table;
      out += `<div class="table-wrap"><table class="list"><thead><tr>${head.map(c => `<th>${c}</th>`).join("")}</tr></thead><tbody>${body.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
      table = null;
    }
  };
  for (const raw of lines) {
    const line = inline(raw);
    if (/^\s*\|.*\|\s*$/.test(line)) {
      const cells = line.trim().slice(1, -1).split("|").map(c => c.trim());
      if (list) close();
      if (cells.every(c => /^:?-{2,}:?$/.test(c))) continue;
      (table = table || []).push(cells);
    }
    else if (/^#{3,} /.test(line)) { close(); out += `<h3>${line.replace(/^#+ /, "")}</h3>`; }
    else if (/^#{1,2} /.test(line)) { close(); out += `<h2>${line.replace(/^#+ /, "")}</h2>`; }
    else if (/^\s*[-*] /.test(line)) { if (list !== "ul") { close(); out += "<ul>"; list = "ul"; } out += `<li>${line.replace(/^\s*[-*] /, "")}</li>`; }
    else if (/^\s*\d+\. /.test(line)) { if (list !== "ol") { close(); out += "<ol>"; list = "ol"; } out += `<li>${line.replace(/^\s*\d+\. /, "")}</li>`; }
    else if (!line.trim()) close();
    else { close(); out += `<p>${line}</p>`; }
  }
  close();
  return out;
};
PPA.pill = (text, tone = "") => `<span class="pill ${tone}">${esc(text)}</span>`;
PPA.empty = (text) => `<div class="empty">${esc(text)}</div>`;
PPA.fail = (error) => `<div class="error">${esc(error.message || error)}</div>`;
PPA.json = (value) => `<pre class="json">${esc(JSON.stringify(value, null, 2))}</pre>`;
PPA.categoryTone = (category) => ({ quarantine: "bad", reply: "strong", task: "good", delegate: "good", tracked: "", archive: "" }[category] ?? "");
PPA.stateTone = (state) => ({ EXECUTED: "good", APPROVED: "good", DELIVERED: "good", COMPLETED: "good", DRAFTED: "warn", ARMED: "strong", FIRED: "warn", RUNNING: "strong", REJECTED: "bad", FAILED: "bad", INTERRUPTED: "warn", CANCELLED: "" }[state] ?? "");

/* ── HTTP ───────────────────────────────────────────────────────────────── */
PPA.api = async (path, options = {}) => {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const payload = await response.json().catch(() => ({ detail: "The server sent an unreadable response" }));
  if (!response.ok) {
    const detail = payload.detail;
    throw new Error(typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map(d => `${(d.loc || []).join(".")}: ${d.msg}`).join("; ") : `HTTP ${response.status}`);
  }
  return payload;
};
PPA.post = (path, body = {}) => PPA.api(path, { method: "POST", body: JSON.stringify(body) });
PPA.busy = async (button, work) => {
  const label = button.innerHTML;
  button.disabled = true; button.innerHTML = '<span class="loading">Working</span>';
  try { return await work(); }
  finally { if (button.isConnected) { button.disabled = false; button.innerHTML = label; } }
};

/* ── Events: one stream for runs, timers, notifications, actions, activity ─ */
PPA.on = (topic, handler, { keep = false } = {}) => {
  if (!PPA.listeners.has(topic)) PPA.listeners.set(topic, new Set());
  PPA.listeners.get(topic).add(handler);
  const off = () => PPA.listeners.get(topic)?.delete(handler);
  if (!keep) PPA.stageCleanups.push(off);
  return off;
};
PPA.emit = (topic, event) => (PPA.listeners.get(topic) || []).forEach(handler => { try { handler(event.data, event); } catch (error) { console.error(error); } });
PPA.connectEvents = () => {
  const source = new EventSource("/api/events");
  for (const topic of ["run", "timer", "notification", "action", "focus", "clock", "safe_mode", "workspace", "activity", "mcp", "reset", "scheduler_error", "gate", "learning"])
    source.addEventListener(topic, message => PPA.emit(topic, JSON.parse(message.data)));
  source.onerror = () => { $("#explorer-live-label").textContent = "Reconnecting"; };
  source.addEventListener("ready", () => { $("#explorer-live-label").textContent = "Live view"; });
};
/* A one-second tick keeps every countdown on the page honest without a request. */
PPA.tick = () => {
  const now = Date.now();
  $$("[data-until]").forEach(node => { node.textContent = PPA.duration((new Date(node.dataset.until).getTime() - now) / 1000); });
  $$("[data-harness-seconds]").forEach(node => { node.textContent = PPA.duration(Number(node.dataset.harnessSeconds)); });
};

/* ── Toasts and browser notifications ───────────────────────────────────── */
PPA.toast = (title, body = "", tone = "") => {
  const node = document.createElement("div");
  node.className = `toast ${tone}`;
  node.innerHTML = `<button aria-label="Dismiss">&times;</button><strong>${esc(title)}</strong>${body ? `<p>${esc(body)}</p>` : ""}`;
  node.querySelector("button").onclick = () => node.remove();
  $("#toasts").prepend(node);
  setTimeout(() => node.remove(), 9000);
};
PPA.plain = (markdown) => String(markdown || "").replace(/[#*`]/g, "").replace(/\n{2,}/g, "\n").trim();
PPA.browserNotify = (title, body) => {
  if (!("Notification" in window) || Notification.permission !== "granted") return false;
  try { new Notification(title, { body: PPA.plain(body).slice(0, 240), tag: "ppa" }); return true; } catch (error) { return false; }
};
PPA.askNotificationPermission = async () => {
  if (!("Notification" in window)) return "unsupported";
  return Notification.permission === "default" ? await Notification.requestPermission() : Notification.permission;
};

/* ── Header ─────────────────────────────────────────────────────────────── */
PPA.refreshStatus = async () => {
  const status = await PPA.api("/api/status");
  PPA.status = status;
  const chip = $("#global-status");
  chip.classList.toggle("ready", !!status.ready);
  chip.classList.toggle("failed", !status.ready && !status.warming);
  $("span", chip).textContent = status.ready ? "Harness ready" : status.warming ? "Warming harness" : "Harness failed to start";
  PPA.renderTopbar();
  return status;
};
PPA.renderTopbar = () => {
  const s = PPA.status, bar = $("#topbar");
  if (!s?.ready) { bar.innerHTML = `<span class="chip">${s?.error ? esc(s.error) : "Starting the workspace gateway and the harness"}</span>`; return; }
  const w = s.workspace, systems = Object.entries(w.systems || {});
  const connected = systems.filter(([, item]) => item.connected && item.provider !== "practice").map(([name, item]) => `${name}: ${item.provider}`);
  const workspaceChip = w.practice
    ? `<span class="chip practice" title="${esc(systems[0]?.[1]?.detail || "")}"><b>Practice workspace</b>${esc(s.workspace.provenance?.sources?.mail?.dataset ? "public mailbox, " + s.workspace.provenance.sources.mail.dataset : "")}</span>`
    : `<span class="chip real"><b>Connected accounts</b>${esc(connected.join(" · ") || "none yet")}</span>`;
  const modes = { practice: "practice clock", pinned: "pinned", real: "real clock" };
  bar.innerHTML = `${workspaceChip}
    <span class="chip" title="${esc(s.owner.email)}"><b>${esc(s.owner.name)}</b>${esc(s.owner.timezone)}</span>
    <label class="chip switch ${w.safe_mode ? "" : "danger"}" title="With a real account, approved mail to other people is held as a draft while safe mode is on.">
      <input type="checkbox" id="safe-mode" ${w.safe_mode ? "checked" : ""} /><i></i><span>Safe mode ${w.safe_mode ? "on" : "off"}</span></label>
    <span class="chip" title="${esc(s.responder.note)}">Answers by <b>${esc(s.responder.label)}</b></span>
    ${s.tracing?.active ? `<span class="chip practice" title="${esc(s.tracing.detail)}"><b>Tracing</b>LangSmith</span>` : ""}
    <span class="spacer"></span>
    <button class="chip" id="clock-chip" title="Set the harness clock"><b>${esc(PPA.dayTime(s.clock.now))}</b>${esc(modes[s.clock.mode])}</button>
    <button class="chip" id="bell" aria-label="Notifications">Notifications ${PPA.unread ? `<span class="badge">${PPA.unread}</span>` : ""}</button>
    <button class="chip" id="theme" aria-label="Toggle colour theme">Theme</button>`;
  $("#safe-mode").onchange = async (event) => {
    const enabled = event.target.checked;
    if (!enabled && !w.practice && !confirm("Switch safe mode off? Approved actions will then reach other people.")) { event.target.checked = true; return; }
    try { await PPA.post("/api/connections/safe_mode", { enabled }); await PPA.refreshStatus(); PPA.toast(`Safe mode ${enabled ? "on" : "off"}`, enabled ? "Approved mail to other people is held as a draft." : "Approved actions are delivered for real.", enabled ? "" : "warn"); }
    catch (error) { PPA.toast("Safe mode was not changed", error.message, "bad"); await PPA.refreshStatus(); }
  };
  $("#theme").onclick = () => {
    const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = next; localStorage.setItem("ppa-theme", next);
  };
  $("#clock-chip").onclick = () => PPA.togglePopover("clock", PPA.clockPopover);
  $("#bell").onclick = () => PPA.togglePopover("bell", PPA.bellPopover);
};
PPA.togglePopover = (name, render) => {
  const open = $(".popover");
  if (open) { const same = open.dataset.name === name; open.remove(); if (same) return; }
  const node = document.createElement("div");
  node.className = "popover"; node.dataset.name = name;
  $("#topbar").append(node);
  render(node);
};
PPA.setClock = async (now) => {
  await PPA.post("/api/clock", { now });
  await PPA.refreshStatus();
  PPA.rerender();
};
PPA.clockPopover = async (node) => {
  node.innerHTML = '<span class="loading">Reading the clock</span>';
  let c;
  try { c = await PPA.api("/api/clock"); } catch (error) { node.innerHTML = PPA.fail(error); return; }
  const about = { practice: "The practice workspace pins the clock and replays the mailbox against it. Moving it forward makes mail arrive and meetings get announced.",
    pinned: "The clock is pinned by you. Reset it to return to the real clock.", real: "A real account is connected, so today is the real today. You can pin a moment for a demonstration." }[c.mode];
  node.innerHTML = `<h3>Harness clock</h3><p class="action-copy">${esc(about)} Focus timers always use the real clock.</p>
    <label for="clock-input">Moment (${esc(c.timezone)})</label><div class="row"><input id="clock-input" type="datetime-local" value="${esc(c.now.slice(0, 16))}" /><button class="primary" id="clock-set">Set</button></div>
    <div class="starters" style="padding:10px 0 0;border:0">${c.presets.map(item => `<button data-clock="${esc(item.now)}">${esc(item.label)}</button>`).join("")}</div>
    <div class="actions"><button class="secondary" id="clock-reset">Reset to ${c.mode === "practice" ? "the scenario start" : "the real clock"}</button></div>`;
  const apply = async (value, button) => { try { await PPA.busy(button, () => PPA.setClock(value)); $(".popover")?.remove(); } catch (error) { PPA.toast("The clock was not changed", error.message, "bad"); } };
  $("#clock-set", node).onclick = (event) => apply($("#clock-input", node).value, event.currentTarget);
  $("#clock-reset", node).onclick = (event) => apply(null, event.currentTarget);
  $$("[data-clock]", node).forEach(button => button.onclick = () => apply(button.dataset.clock, button));
};
PPA.loadNotifications = async () => {
  try { const data = await PPA.api("/api/notifications"); PPA.notifications = data.notifications; PPA.unread = data.unread; PPA.renderTopbar(); } catch (error) { /* header only */ }
};
PPA.bellPopover = (node) => {
  const permission = "Notification" in window ? Notification.permission : "unsupported";
  node.innerHTML = `<h3>Notifications</h3>
    <div class="row" style="margin-bottom:10px">${PPA.pill("browser notifications: " + permission, permission === "granted" ? "good" : "")}${permission === "default" ? '<button class="secondary small" id="ask-permission">Allow browser notifications</button>' : ""}</div>
    <ul class="items">${PPA.notifications.map(n => `<li data-id="${esc(n.notification_id)}"><span class="time">${esc(PPA.realTime(n.real_created_at))}</span><div><strong>${esc(n.title)}${n.read_at ? "" : " " + PPA.pill("new", "strong")}</strong><div class="result-copy" style="font-size:12px">${PPA.markdown(n.body)}</div><small>${esc(n.kind)}${n.job_id ? " · " + esc(n.job_id) : ""}</small></div><span></span></li>`).join("") || `<li><span></span>${PPA.empty("Nothing yet. Timers and routines report here.")}<span></span></li>`}</ul>`;
  const ask = $("#ask-permission", node);
  if (ask) ask.onclick = async () => { await PPA.askNotificationPermission(); PPA.bellPopover(node); };
  PPA.notifications.filter(n => !n.read_at).forEach(n => PPA.post(`/api/notifications/${n.notification_id}/read`).catch(() => {}));
  PPA.notifications.forEach(n => { n.read_at = n.read_at || "now"; });
  PPA.unread = 0;
  const badge = $("#bell .badge"); if (badge) badge.remove();
};

/* ── Router ─────────────────────────────────────────────────────────────── */
PPA.register = (chapter) => PPA.chapters.push(chapter);
PPA.renderSidebar = () => {
  const numbered = PPA.chapters.filter(c => c.n).sort((a, b) => a.n - b.n);
  $("#chapters").innerHTML = PPA.chapters.filter(c => !c.n).map(c => `<a class="nav lead" data-id="${c.id}" href="#${c.id}"><span class="num">PPA</span><span>${esc(c.title)}</span></a>`).join("")
    + '<div class="nav-section">Building blocks</div>'
    + numbered.map(c => `<a class="nav" data-id="${c.id}" href="#${c.id}" title="${esc(c.title)}"><span class="num">${String(c.n).padStart(2, "0")}</span><span>${esc(c.title)}</span></a>`).join("");
};
PPA.header = (chapter) => `<header class="stage-head"><div class="eyebrow">${chapter.n ? `CUSTOM HARNESS · CHAPTER ${String(chapter.n).padStart(2, "0")}` : "PERSONAL PRODUCTIVITY ASSISTANT"}</div><h1>${esc(chapter.title)}</h1><p class="blurb">${esc(chapter.blurb)}</p><div class="chapter-meta">${(chapter.tags || []).map(t => PPA.pill(t)).join("")}${PPA.pill(PPA.status?.substrate || "Local store")}</div></header>`;
PPA.current = () => PPA.chapters.find(c => c.id === location.hash.slice(1)) || PPA.chapters[0];
PPA.rerender = () => PPA.renderStage();
PPA.renderStage = async () => {
  PPA.stageCleanups.splice(0).forEach(off => off());
  $(".popover")?.remove();
  const chapter = PPA.current(), stage = $("#stage");
  document.title = `PPA / ${chapter.title}`;
  $$(".nav").forEach(node => node.classList.toggle("active", node.dataset.id === chapter.id));
  stage.innerHTML = `<div class="stage-inner">${PPA.header(chapter)}${PPA.teach.frame(chapter)}<div id="chapter-body"><div class="empty"><span class="loading">Loading</span></div></div></div>`;
  $("#sidebar").classList.remove("open"); $("#scrim").hidden = true;
  PPA.teach.bind();
  if (!PPA.status?.ready) { $("#chapter-body").innerHTML = PPA.status?.error ? PPA.fail(PPA.status.error) : PPA.empty("The harness is starting the workspace gateway."); return; }
  // A chapter that is left before it has finished drawing must not write into the next one.
  const body = $("#chapter-body");
  try { await chapter.render(body, chapter); }
  catch (error) { if (!body.isConnected) return; body.innerHTML = PPA.fail(error); console.error(error); }
};
PPA.modal = (title, html) => {
  const node = document.createElement("div");
  node.className = "modal";
  node.innerHTML = `<div role="dialog" aria-label="${esc(title)}"><div class="panel-head"><h2 class="panel-title">${esc(title)}</h2><button class="secondary small" data-close>Close</button></div><div>${html}</div></div>`;
  node.onclick = (event) => { if (event.target === node || event.target.closest("[data-close]")) node.remove(); };
  document.body.append(node);
  return node;
};
/* One thread, shown to a person. The model never receives this view. */
PPA.openThread = async (threadId) => {
  const node = PPA.modal(`Thread ${threadId}`, '<div class="empty"><span class="loading">Reading through MCP</span></div>');
  try {
    const t = await PPA.api(`/api/inbox_triage/thread/${encodeURIComponent(threadId)}`);
    const quarantined = t.category === "quarantine";
    $("div > div:last-child", node).innerHTML = `<div class="panel-body"><dl class="kv"><dt>From</dt><dd><strong>${esc(t.from_name)}</strong> ${esc(t.from_email)} ${PPA.pill("trust: " + t.trust, t.trust === "unknown" ? "warn" : "")}${t.vip ? PPA.pill("VIP", "strong") : ""}</dd><dt>Subject</dt><dd>${esc(t.subject)}</dd><dt>Received</dt><dd>${esc(PPA.dayTime(t.received_at))}</dd><dt>Governed</dt><dd>${PPA.pill(t.category, PPA.categoryTone(t.category))} ${esc(t.reason)}${t.tracked_task_id ? " · " + esc(t.tracked_task_id) : ""}</dd>${t.injection_patterns.length ? `<dt>Tripwire</dt><dd>${t.injection_patterns.map(p => PPA.pill(p, "bad")).join(" ")}</dd>` : ""}</dl>
      ${quarantined ? `<div class="notice" style="margin-top:12px"><strong>Quarantined.</strong> ${esc(t.warning)}</div><details style="margin-top:10px"><summary class="link-button">Show the quarantined text to me</summary><pre class="body">${esc(t.body)}</pre></details>` : `<pre class="body" style="padding:14px 0 0">${esc(t.body)}</pre>`}
      <details style="margin-top:12px"><summary class="link-button">What the model is shown</summary>${PPA.json(t.model_facing)}</details></div>`;
  } catch (error) { $("div > div:last-child", node).innerHTML = `<div class="panel-body">${PPA.fail(error)}</div>`; }
};

/* ── Boot ───────────────────────────────────────────────────────────────── */
PPA.boot = async () => {
  PPA.renderSidebar();
  PPA.explorer.init();
  $("#menu").onclick = () => { $("#sidebar").classList.add("open"); $("#scrim").hidden = false; };
  $("#scrim").onclick = () => { $("#sidebar").classList.remove("open"); $("#scrim").hidden = true; };
  window.addEventListener("hashchange", PPA.renderStage);
  document.addEventListener("click", (event) => { if (!event.target.closest(".popover, #clock-chip, #bell")) $(".popover")?.remove(); });
  setInterval(PPA.tick, 1000);
  PPA.connectEvents();
  await PPA.teach.load();
  PPA.on("activity", PPA.explorer.onActivity, { keep: true });
  PPA.on("reset", () => PPA.explorer.reload(), { keep: true });
  PPA.on("notification", (n) => {
    PPA.notifications.unshift(n); PPA.unread += 1; PPA.renderTopbar();
    PPA.toast(n.title, PPA.plain(n.body), n.kind === "pomodoro" ? "" : "warn");
    PPA.browserNotify(n.title, n.body);
  }, { keep: true });
  for (const topic of ["clock", "safe_mode", "workspace", "reset"]) PPA.on(topic, () => PPA.refreshStatus().catch(() => {}), { keep: true });
  PPA.on("scheduler_error", (data) => PPA.toast("The scheduler reported an error", data.error, "bad"), { keep: true });
  await PPA.renderStage();
  for (let attempt = 0; attempt < 120; attempt += 1) {
    try { if ((await PPA.refreshStatus()).ready) break; if (PPA.status.error) break; } catch (error) { /* the server is still starting */ }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  await PPA.loadNotifications();
  await PPA.renderStage();
  if (document.body.classList.contains("explorer-open")) PPA.explorer.reload();
};

// Collapse the navigation to a rail of chapter numbers; the choice is a view preference.
(function () {
  const button = document.getElementById("nav-collapse");
  if (!button) return;
  const root = document.documentElement;
  const sync = () => {
    const collapsed = root.dataset.nav === "collapsed";
    const label = collapsed ? "Expand the navigation" : "Collapse the navigation";
    button.setAttribute("aria-expanded", String(!collapsed));
    button.setAttribute("aria-label", label); button.title = label;
  };
  button.addEventListener("click", () => {
    if (root.dataset.nav === "collapsed") delete root.dataset.nav; else root.dataset.nav = "collapsed";
    try { localStorage.setItem("ppa-nav", root.dataset.nav || "open"); } catch (e) {}
    sync();
  });
  sync();
})();
