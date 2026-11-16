/* A small no-build framework shared by the Part 2 advanced appbooks: chapters, a status bar,
   server-sent events, a read-only data explorer. Each appbook registers its own chapters. */
const APP = { chapters: [], status: null, listeners: new Map(), brand: { mark: "AH", name: "Advanced", line: "" } };
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

APP.api = async (path, options = {}) => {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  if (!response.ok) {
    let detail = response.statusText;
    try { detail = (await response.json()).detail || detail; } catch (e) {}
    // a validation error names the field and what was wrong with it
    if (Array.isArray(detail)) detail = detail.map(d => `${(d.loc || []).filter(x => x !== "body").join(".")}: ${d.msg}`).join("; ");
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return response.json();
};
APP.post = (path, body = {}) => APP.api(path, { method: "POST", body: JSON.stringify(body) });
APP.del = (path) => APP.api(path, { method: "DELETE" });
APP.pill = (text, tone = "") => `<span class="pill ${tone}">${esc(text)}</span>`;
APP.empty = (text) => `<div class="empty">${esc(text)}</div>`;
APP.fail = (error) => `<div class="error">${esc(error.message || error)}</div>`;
APP.json = (value) => `<pre class="json">${esc(JSON.stringify(value, null, 2))}</pre>`;
APP.money = (value, currency = "GBP") => value === null || value === undefined ? "" : `${Number(value).toFixed(2)} ${currency}`;
APP.when = (iso) => iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "";
APP.tone = (status) => ({ booked: "good", published: "good", CONFIRMED: "good", BOOKED: "good", PUBLISHED: "good", awaiting_traveller: "warn", awaiting_person: "warn", awaiting_outline: "warn", awaiting_publication: "warn", interrupted: "bad", booking_failed: "bad", unbookable: "bad", declined: "bad", FAILED: "bad", CANCELLED: "bad", DECLINED: "bad", needs_answers: "warn" }[status] || "");
APP.markdown = (text) => {
  const lines = String(text || "").split("\n"); let html = "", list = null, table = false;
  const inline = (t) => esc(t).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`(.+?)`/g, "<code>$1</code>").replace(/(https?:\/\/[^\s)]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
  const closeList = () => { if (list) { html += list === "ul" ? "</ul>" : "</ol>"; list = null; } };
  for (const line of lines) {
    if (line.startsWith("|")) { const cells = line.split("|").slice(1, -1).map(c => c.trim()); if (cells.every(c => /^:?-+:?$/.test(c))) continue; if (!table) { html += "<table class=\"list\">"; table = true; } html += "<tr>" + cells.map(c => `<td>${inline(c)}</td>`).join("") + "</tr>"; continue; }
    if (table) { html += "</table>"; table = false; }
    const h = line.match(/^(#{1,4}) (.*)/); if (h) { closeList(); html += `<h${h[1].length + 1}>${inline(h[2])}</h${h[1].length + 1}>`; continue; }
    const li = line.match(/^(\d+\.|[-*]) (.*)/); if (li) { const kind = li[1] === "-" || li[1] === "*" ? "ul" : "ol"; if (list !== kind) { closeList(); html += `<${kind}>`; list = kind; } html += `<li>${inline(li[2])}</li>`; continue; }
    closeList(); if (line.trim()) html += `<p>${inline(line)}</p>`;
  }
  closeList(); if (table) html += "</table>"; return html;
};
APP.toast = (title, body = "", tone = "") => {
  const node = document.createElement("div"); node.className = `toast ${tone}`;
  node.innerHTML = `<strong>${esc(title)}</strong>${body ? `<span>${esc(body)}</span>` : ""}`;
  $("#toasts").append(node); setTimeout(() => node.remove(), 6000);
};
APP.busy = async (button, work) => {
  const label = button.innerHTML; button.disabled = true; button.innerHTML = `<span class="loading">Working</span>`;
  try { return await work(); }
  catch (error) { APP.toast("That did not work", error.message || String(error), "bad"); }
  finally { if (button.isConnected) { button.disabled = false; button.innerHTML = label; } }
};
APP.on = (topic, handler) => { const found = APP.listeners.get(topic) || []; found.push(handler); APP.listeners.set(topic, found); APP.stageCleanups.push(() => APP.listeners.set(topic, (APP.listeners.get(topic) || []).filter(h => h !== handler))); };
APP.stageCleanups = [];
APP.connectEvents = () => {
  const source = new EventSource("/api/events");
  for (const topic of APP.topics || []) source.addEventListener(topic, (event) => { const data = JSON.parse(event.data); (APP.listeners.get(topic) || []).forEach(h => { try { h(data); } catch (e) { console.error(e); } }); });
  source.onerror = () => { $("#global-status span").textContent = "Reconnecting"; };
};
APP.refreshStatus = async () => {
  try { APP.status = await APP.api("/api/status"); } catch (error) { APP.status = { ready: false, error: error.message }; }
  const chip = $("#global-status"); chip.classList.toggle("ready", !!APP.status.ready);
  chip.querySelector("span").textContent = APP.status.ready ? "Harness ready" : (APP.status.error || "Warming harness");
  APP.renderTopbar();
  return APP.status;
};
APP.register = (chapter) => APP.chapters.push(chapter);
APP.renderSidebar = () => {
  $("#chapters").innerHTML = APP.chapters.map(c => `<a class="nav ${c.n ? "" : "lead"}" href="#${c.id}" data-id="${c.id}"><span class="num">${c.n ? String(c.n).padStart(2, "0") : "▶"}</span><span>${esc(c.title)}</span></a>`).join("");
};
APP.header = (chapter) => `<header class="stage-head"><div class="eyebrow">${chapter.n ? `${esc(APP.brand.line)} · CHAPTER ${String(chapter.n).padStart(2, "0")}` : esc(APP.brand.line)}</div><h1>${esc(chapter.title)}</h1><p class="blurb">${esc(chapter.blurb || "")}</p></header>`;
APP.current = () => APP.chapters.find(c => c.id === location.hash.slice(1)) || APP.chapters[0];
APP.renderStage = async () => {
  APP.stageCleanups.splice(0).forEach(off => off());
  const chapter = APP.current(), stage = $("#stage");
  document.title = `${APP.brand.name} / ${chapter.title}`;
  $$(".nav").forEach(node => node.classList.toggle("active", node.dataset.id === chapter.id));
  stage.innerHTML = `<div class="stage-inner">${APP.header(chapter)}<div id="chapter-body"><div class="empty"><span class="loading">Loading</span></div></div></div>`;
  $("#sidebar").classList.remove("open"); $("#scrim").hidden = true;
  const body = $("#chapter-body");
  if (!APP.status?.ready) { body.innerHTML = APP.status?.error ? APP.fail(APP.status.error) : APP.empty("The harness is starting: the database schema, the embedding model and the graph."); return; }
  try { await chapter.render(body, chapter); }
  catch (error) { if (!body.isConnected) return; body.innerHTML = APP.fail(error); console.error(error); }
};
APP.rerender = () => APP.renderStage();
APP.modal = (title, html) => {
  const node = document.createElement("div"); node.className = "modal";
  node.innerHTML = `<div role="dialog" aria-label="${esc(title)}"><div class="panel-head"><h2 class="panel-title">${esc(title)}</h2><button class="secondary small" data-close>Close</button></div><div>${html}</div></div>`;
  node.onclick = (event) => { if (event.target === node || event.target.closest("[data-close]")) node.remove(); };
  document.body.append(node); return node;
};
APP.table = (columns, rows, cell = (r, c) => esc(r[c])) => `<div class="table-wrap"><table class="list"><thead><tr>${columns.map(c => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${rows.length ? rows.map(r => `<tr>${columns.map(c => `<td>${cell(r, c)}</td>`).join("")}</tr>`).join("") : `<tr><td colspan="${columns.length}" class="faint">Nothing yet.</td></tr>`}</tbody></table></div>`;

/* ── data explorer, docked under every chapter ───────────────────────────── */
APP.explorer = { table: null, offset: 0, search: "" };
APP.explorerRender = async () => {
  const tables = (await APP.api("/api/explorer/tables")).tables;
  $("#explorer-table-list").innerHTML = tables.map(t => `<button class="table-item ${t.name === APP.explorer.table ? "selected" : ""}" data-table="${t.name}"><span><i></i>${esc(t.name.toLowerCase())}</span><b>${t.rows}</b></button>`).join("");
  $$("#explorer-table-list .table-item").forEach(node => node.onclick = () => { APP.explorer.table = node.dataset.table; APP.explorer.offset = 0; APP.explorerRows(); APP.explorerRender(); });
  $("#explorer-summary").textContent = `${tables.length} tables in ${APP.status?.database?.user || "the schema"} · read-only`;
};
APP.explorerRows = async () => {
  const e = APP.explorer; if (!e.table) return;
  const found = await APP.api(`/api/explorer/tables/${e.table}/rows?limit=40&offset=${e.offset}&search=${encodeURIComponent(e.search)}`);
  $("#explorer-toolbar").innerHTML = `<div class="explorer-name"><h2>${esc(found.table.toLowerCase())}</h2><p>${found.total} rows · newest first · read-only</p></div><div class="explorer-tools"><input id="explorer-search" type="text" placeholder="Filter text columns" value="${esc(e.search)}" /><span class="explorer-pagination"><button id="explorer-prev" ${found.offset === 0 ? "disabled" : ""}>&lsaquo;</button><span>${found.offset + 1}–${Math.min(found.offset + found.limit, found.total)}</span><button id="explorer-next" ${found.offset + found.limit >= found.total ? "disabled" : ""}>&rsaquo;</button></span></div>`;
  $("#explorer-grid").innerHTML = `<table class="data-table"><thead><tr>${found.columns.map(c => `<th><button type="button"><span>${esc(c.name.toLowerCase())}</span><small>${esc(c.type)}</small></button></th>`).join("")}</tr></thead><tbody>${found.rows.map(r => `<tr>${found.columns.map(c => `<td title="${esc(r[c.name.toLowerCase()] ?? "")}">${esc(String(r[c.name.toLowerCase()] ?? "").slice(0, 80))}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  $$("#explorer-grid tbody tr").forEach((row, index) => row.onclick = () => APP.modal(found.table.toLowerCase(), `<dl class="kv">${found.columns.map(c => `<dt>${esc(c.name.toLowerCase())}</dt><dd>${esc(found.rows[index][c.name.toLowerCase()] ?? "")}</dd>`).join("")}</dl>`));
  $("#explorer-search").onchange = (ev) => { e.search = ev.target.value; e.offset = 0; APP.explorerRows(); };
  $("#explorer-prev").onclick = () => { e.offset = Math.max(0, e.offset - found.limit); APP.explorerRows(); };
  $("#explorer-next").onclick = () => { e.offset += found.limit; APP.explorerRows(); };
};
APP.explorerBoot = () => {
  $("#explorer-toggle").onclick = () => { const open = $("#explorer-body").hidden; $("#explorer-body").hidden = !open; $("#explorer-toggle").setAttribute("aria-expanded", String(open)); if (open) APP.explorerRender(); };
  $("#explorer-refresh").onclick = () => { APP.explorerRender(); APP.explorerRows(); };
};

APP.boot = async () => {
  APP.renderSidebar();
  $("#menu").onclick = () => { $("#sidebar").classList.add("open"); $("#scrim").hidden = false; };
  $("#scrim").onclick = () => { $("#sidebar").classList.remove("open"); $("#scrim").hidden = true; };
  window.addEventListener("hashchange", APP.renderStage);
  APP.explorerBoot();
  await APP.refreshStatus();
  APP.connectEvents();
  APP.renderStage();
  const poll = setInterval(async () => { const was = APP.status?.ready; await APP.refreshStatus(); if (!was && APP.status.ready) { APP.renderStage(); APP.explorerRender(); } if (APP.status.ready && !APP.status.error) { } }, 4000);
  APP.pollHandle = poll;
};
