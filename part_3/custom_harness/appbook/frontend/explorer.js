/* The data explorer: every table the harness owns, read-only, docked under every chapter. */
PPA.explorer = (() => {
  const state = {
    tables: [], limits: { rows_per_page: 100 }, selected: null, page: null, limit: 25, offset: 0,
    sort: null, direction: "desc", search: "", tab: "row", record: null, recordKey: null,
    seen: {}, flashes: new Map(), activity: [], auto: true, known: null, fresh: new Set(), open: new Set(),
    source: localStorage.getItem("ppa-explorer-source") === "oracle" ? "oracle" : "sqlite",
  };
  /* `known` holds the row ids already shown for this view; null means the view has not been drawn yet. */
  const isOpen = () => $("#data-explorer").classList.contains("open");
  const table = (name = state.selected) => state.tables.find(t => t.name === name);
  const unseen = (t) => Math.max(0, t.writes - (state.seen[t.name] ?? t.writes));

  /* Two sources: the appbook's own SQLite store, and a read-only window on the notebook's Oracle database. */
  const show = (source = state.source, { load = true } = {}) => {
    state.source = source; localStorage.setItem("ppa-explorer-source", source);
    const open = isOpen();
    $("#explorer-sources").hidden = !open;
    $("#explorer-body").hidden = !open || source !== "sqlite";
    $("#oracle-body").hidden = !open || source !== "oracle";
    $$("#explorer-sources [data-source]").forEach(tab => tab.setAttribute("aria-selected", String(tab.dataset.source === source)));
    if (!open || !load) return;
    if (source === "oracle") PPA.oracle.open(); else reload();
  };
  const toggle = (force) => {
    const node = $("#data-explorer"), opening = force ?? !node.classList.contains("open");
    node.classList.toggle("open", opening);
    $("#explorer-toggle").setAttribute("aria-expanded", String(opening)); document.body.classList.toggle("explorer-open", opening);
    localStorage.setItem("ppa-explorer-open", opening ? "1" : "0");
    show();
  };

  /* Table list, grouped by the part of the harness each table belongs to. */
  const loadTables = async () => {
    const data = await PPA.api("/api/data_explorer/tables");
    state.tables = data.tables; state.limits = data.limits;
    for (const t of data.tables) if (!(t.name in state.seen)) state.seen[t.name] = t.writes;
    const changed = data.tables.filter(t => unseen(t)).length;
    $("#explorer-summary").textContent = `${data.tables.length} tables · ${PPA.number(data.rows)} rows · read-only · ${data.substrate}${changed ? ` · ${changed} changed` : ""}`;
    renderTables();
  };
  const renderTables = () => {
    const filter = ($("#explorer-filter").value || "").toLowerCase(), groups = new Map();
    for (const t of state.tables) {
      if (filter && !`${t.name} ${t.group} ${t.about}`.toLowerCase().includes(filter)) continue;
      if (!groups.has(t.group)) groups.set(t.group, []);
      groups.get(t.group).push(t);
    }
    $("#explorer-table-list").innerHTML = [...groups].map(([group, items]) => `<div class="table-group">${esc(group)}</div>` + items.map(t => {
      const flash = state.flashes.get(t.name), news = unseen(t);
      return `<button class="table-item ${state.selected === t.name ? "selected" : ""} ${flash ? "flash-" + flash : ""}" data-table="${esc(t.name)}" title="${esc(t.about)}"><span><i></i>${esc(t.name)}</span>${news ? `<em title="${news} writes since you last looked">+${news}</em>` : ""}<b>${PPA.number(t.row_count)}</b></button>`;
    }).join("")).join("") || PPA.empty("No table matches.");
  };

  /* Rows: newest first unless a column is chosen; search is literal and runs on the server. */
  const select = async (name, keep = {}) => {
    const same = name === state.selected;
    Object.assign(state, { selected: name, offset: keep.offset ?? 0, sort: same ? state.sort : null, direction: same ? state.direction : "desc", search: same ? state.search : "" });
    if (!same) { state.record = null; state.recordKey = null; state.known = null; state.fresh = new Set(); }
    await loadRows();
  };
  const loadRows = async ({ quiet = false } = {}) => {
    const name = state.selected;
    if (!name) return;
    const query = new URLSearchParams({ limit: state.limit, offset: state.offset, direction: state.direction });
    if (state.sort) query.set("sort", state.sort);
    if (state.search) query.set("search", state.search);
    const wrap = $("#explorer-grid"), top = wrap.scrollTop;
    if (!quiet) wrap.innerHTML = PPA.empty("Reading rows");
    try {
      const page = await PPA.api(`/api/data_explorer/tables/${encodeURIComponent(name)}/rows?${query}`);
      if (name !== state.selected) return;
      state.fresh = new Set(state.known ? page.rows.filter(r => !state.known.has(r.rowid)).map(r => r.rowid) : []);
      state.known = state.known || new Set();
      page.rows.forEach(r => state.known.add(r.rowid));
      state.page = page;
      const t = table();
      if (t) state.seen[name] = t.writes;
      renderTables(); renderToolbar(); renderGrid();
      if (quiet) wrap.scrollTop = top;
      if (state.recordKey?.startsWith(name + ":")) openRecord(Number(state.recordKey.split(":")[1]), { quiet: true });
      else renderInspector();
    } catch (error) { wrap.innerHTML = PPA.fail(error); }
  };
  const renderToolbar = () => {
    const p = state.page, t = table();
    if (!p || !t) return;
    const start = p.matched ? p.offset + 1 : 0, end = Math.min(p.offset + p.rows.length, p.matched);
    $("#explorer-toolbar").innerHTML = `<div class="explorer-name"><span class="eyebrow">${esc(t.group)} · ${p.columns.length} columns · ${esc(p.sort === "rowid" ? "newest first" : `${p.sort} ${p.direction === "asc" ? "ascending" : "descending"}`)}</span><h2>${esc(t.name)}</h2><p>${esc(t.about)}</p></div>
      <div class="explorer-tools"><form id="explorer-search-form" role="search"><input id="explorer-search" value="${esc(state.search)}" placeholder="Search this table" aria-label="Search this table" /></form>
        <label class="inline"><input type="checkbox" id="explorer-auto" ${state.auto ? "checked" : ""} /> refresh on change</label>
        <select id="explorer-limit" aria-label="Rows per page">${[25, 50, 100].map(n => `<option ${n === state.limit ? "selected" : ""}>${n}</option>`).join("")}</select>
        <div class="explorer-pagination"><button id="explorer-prev" aria-label="Previous page" ${p.offset === 0 ? "disabled" : ""}>&#8592;</button><span>${start}-${end} of ${PPA.number(p.matched)}${p.matched !== p.total ? ` (${PPA.number(p.total)} in all)` : ""}</span><button id="explorer-next" aria-label="Next page" ${end >= p.matched ? "disabled" : ""}>&#8594;</button></div>
        <button class="secondary small" id="explorer-reload">Refresh</button><a class="secondary small" href="/api/data_explorer/tables/${encodeURIComponent(t.name)}/export" download>Export</a></div>`;
    $("#explorer-search-form").onsubmit = (event) => { event.preventDefault(); state.search = $("#explorer-search").value.trim(); state.offset = 0; state.known = null; loadRows(); };
    $("#explorer-auto").onchange = (event) => { state.auto = event.target.checked; };
    $("#explorer-limit").onchange = (event) => { state.limit = Number(event.target.value); state.offset = 0; state.known = null; loadRows(); };
    $("#explorer-prev").onclick = () => { state.offset = Math.max(0, state.offset - state.limit); state.known = null; loadRows(); };
    $("#explorer-next").onclick = () => { state.offset += state.limit; state.known = null; loadRows(); };
    $("#explorer-reload").onclick = () => reload();
  };
  const cell = (value) => {
    if (value === null) return '<span class="null">NULL</span>';
    if (typeof value !== "object") return esc(value);
    return `<span class="cell-kind">${esc(value.kind)}</span>${esc(value.preview)}${value.truncated && value.kind !== "binary" ? "…" : ""}`;
  };
  const renderGrid = () => {
    const p = state.page;
    if (!p.rows.length) { $("#explorer-grid").innerHTML = PPA.empty(p.search ? `Nothing in ${p.table} matches "${p.search}".` : "This table is empty. Harness state starts empty and fills as the assistant is used."); return; }
    const mark = (name) => p.sort === name ? (p.direction === "asc" ? " &#9650;" : " &#9660;") : "";
    $("#explorer-grid").innerHTML = `<table class="data-table"><thead><tr>${p.columns.map(c => `<th><button data-sort="${esc(c.name)}" title="Sort by ${esc(c.name)}"><span>${esc(c.name)}${mark(c.name)}</span><small>${esc(c.type)}${c.primary_key ? " · PK" : ""}</small></button></th>`).join("")}</tr></thead>
      <tbody>${p.rows.map(r => `<tr data-rowid="${r.rowid}" class="${state.fresh.has(r.rowid) ? "fresh" : ""} ${state.recordKey === `${p.table}:${r.rowid}` ? "selected" : ""}" tabindex="0">${p.columns.map(c => `<td>${cell(r.cells[c.name])}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  };

  /* Inspector: one row in full, or the live activity list. */
  const openRecord = async (rowid, { quiet = false } = {}) => {
    state.recordKey = `${state.selected}:${rowid}`; state.tab = quiet ? state.tab : "row";
    $$("#explorer-grid tr").forEach(tr => tr.classList.toggle("selected", Number(tr.dataset.rowid) === rowid));
    try { state.record = await PPA.api(`/api/data_explorer/tables/${encodeURIComponent(state.selected)}/rows/${rowid}`); }
    catch (error) { state.record = null; state.recordKey = null; }
    renderInspector();
  };
  const full = (value) => {
    if (value === null) return { tag: "null", text: "NULL", size: "" };
    if (typeof value !== "object") return { tag: typeof value === "number" ? "number" : "text", text: String(value), size: "" };
    const text = value.kind === "json" ? JSON.stringify(value.value, null, 2) : String(value.value);
    const note = value.decoded_from ? ` · decoded from a ${value.decoded_from}` : value.encoding ? ` · ${value.encoding}${value.truncated ? ", first bytes only" : ""}` : "";
    return { tag: value.kind, text, size: `${PPA.number(value.length)} ${value.kind === "binary" || value.decoded_from ? "bytes" : "characters"}${note}` };
  };
  const renderInspector = () => {
    const changed = state.tables.filter(t => unseen(t)).length;
    $("#explorer-tabs").innerHTML = `<button role="tab" data-tab="row" aria-selected="${state.tab === "row"}" class="${state.tab === "row" ? "active" : ""}">Row</button><button role="tab" data-tab="activity" aria-selected="${state.tab === "activity"}" class="${state.tab === "activity" ? "active" : ""}">Activity${changed ? `<span>${changed}</span>` : ""}</button><span class="live-word">LIVE VIEW</span>`;
    const body = $("#explorer-inspector"), top = body.scrollTop;
    $$("details[data-column]", body).forEach(d => d.open ? state.open.add(d.dataset.column) : state.open.delete(d.dataset.column));
    if (state.tab === "activity") {
      body.innerHTML = state.activity.map(e => `<div class="activity-event ${e.operation.toLowerCase()}"><i></i><div><strong>${esc(e.operation)} <button class="link-button" data-goto="${esc(e.table)}">${esc(e.table)}</button></strong><small>${esc(e.route)}</small></div><time>${esc(PPA.realTime(e.at))}</time></div>`).join("") || PPA.empty("Waiting for the harness to read or write a table.");
    } else if (!state.record) {
      body.innerHTML = PPA.empty("Select a row to read every value in full. Long text, JSON and binary cells are cut short in the grid.");
    } else {
      const entries = Object.entries(state.record.values);
      body.innerHTML = `<p class="inspector-note">${esc(state.record.table)} · row ${state.record.rowid}</p>` + entries.map(([name, value], index) => {
        const f = full(value), long = f.text.length > 80 || f.text.includes("\n");
        return long ? `<details class="field" data-column="${esc(name)}" ${state.open.has(name) || (state.open.size === 0 && index < 0) ? "open" : ""}><summary><span class="item-index">${String(index + 1).padStart(2, "0")}</span><span>${esc(name)}</span><span class="origin-tag">${esc(f.tag)}</span></summary><div class="field-content"><pre>${esc(f.text)}</pre><div class="source-line">${esc(f.size)}</div></div></details>`
          : `<div class="field short"><span class="item-index">${String(index + 1).padStart(2, "0")}</span><span>${esc(name)}</span><code class="${f.tag === "null" ? "null" : ""}">${esc(f.text)}</code></div>`;
      }).join("");
      body.scrollTop = top;
    }
  };

  /* Live change: mark the table, count what is new, and refresh the grid when it is the one in view. */
  const onActivity = (data, event) => {
    state.activity.unshift({ ...data, at: event.at }); state.activity = state.activity.slice(0, 80);
    const t = table(data.table), writing = data.operation === "WRITE";
    if (t && writing) t.writes += 1;
    state.flashes.set(data.table, data.operation.toLowerCase());
    $("#data-explorer").classList.toggle("transacting", true);
    $("#explorer-live-label").textContent = `${data.operation === "WRITE" ? "Wrote" : "Read"} ${data.table}`;
    clearTimeout(state.calm);
    state.calm = setTimeout(() => { state.flashes.clear(); $("#data-explorer").classList.remove("transacting"); $("#explorer-live-label").textContent = "Live view"; if (isOpen()) renderTables(); }, 1400);
    if (!isOpen()) return;
    renderTables();
    if (state.tab === "activity") renderInspector();
    if (writing && data.table === state.selected && state.auto && state.offset === 0 && data.route !== "/api/data_explorer/tables") {
      clearTimeout(state.refresh);
      state.refresh = setTimeout(() => { loadTables().then(() => loadRows({ quiet: true })).catch(() => {}); }, 350);
    }
  };
  const reload = async () => {
    if (!PPA.status?.ready) return;
    try { await loadTables(); if (state.source === "sqlite") await select(table() ? state.selected : "ppa_tasks", { offset: state.offset }); }
    catch (error) { $("#explorer-summary").textContent = error.message; }
  };

  const init = () => {
    const node = $("#data-explorer"), handle = $("#explorer-resizer");
    const saved = Number(localStorage.getItem("ppa-explorer-height"));
    if (Number.isFinite(saved) && saved >= 240) document.documentElement.style.setProperty("--explorer-height", `${Math.min(saved, window.innerHeight - 80)}px`);
    handle.addEventListener("pointerdown", (event) => {
      if (!isOpen()) return;
      event.preventDefault(); handle.setPointerCapture(event.pointerId);
      const startY = event.clientY, startHeight = node.getBoundingClientRect().height;
      node.classList.add("resizing"); document.body.classList.add("explorer-resizing");
      const move = (e) => document.documentElement.style.setProperty("--explorer-height", `${Math.round(Math.max(240, Math.min(window.innerHeight - 80, startHeight + (startY - e.clientY))))}px`);
      const stop = () => {
        handle.removeEventListener("pointermove", move); handle.removeEventListener("pointerup", stop); handle.removeEventListener("pointercancel", stop);
        node.classList.remove("resizing"); document.body.classList.remove("explorer-resizing");
        localStorage.setItem("ppa-explorer-height", String(Math.round(node.getBoundingClientRect().height)));
      };
      handle.addEventListener("pointermove", move); handle.addEventListener("pointerup", stop); handle.addEventListener("pointercancel", stop);
    });
    $("#explorer-toggle").onclick = () => toggle();
    $("#explorer-sources").onclick = (event) => { const tab = event.target.closest("[data-source]"); if (tab) show(tab.dataset.source); };
    PPA.oracle.init();
    $("#explorer-refresh").onclick = () => reload();
    $("#explorer-filter").oninput = renderTables;
    $("#explorer-table-list").onclick = (event) => { const b = event.target.closest("[data-table]"); if (b) select(b.dataset.table); };
    /* Internal calls use the plain select; only a caller from outside has to change the source. */
    $("#explorer-grid").onclick = (event) => {
      const sort = event.target.closest("[data-sort]"), row = event.target.closest("[data-rowid]");
      if (sort) { const name = sort.dataset.sort; state.direction = state.sort === name && state.direction === "asc" ? "desc" : "asc"; state.sort = name; state.offset = 0; state.known = null; loadRows(); }
      else if (row) openRecord(Number(row.dataset.rowid));
    };
    $("#explorer-grid").onkeydown = (event) => { const row = event.target.closest("[data-rowid]"); if (row && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); openRecord(Number(row.dataset.rowid)); } };
    $("#explorer-tabs").onclick = (event) => { const b = event.target.closest("[data-tab]"); if (b) { state.tab = b.dataset.tab; renderInspector(); } };
    $("#explorer-inspector").onclick = (event) => { const b = event.target.closest("[data-goto]"); if (b && table(b.dataset.goto)) { state.tab = "row"; select(b.dataset.goto); } };
    document.addEventListener("keydown", (event) => { if (event.key === "Escape" && isOpen() && !$(".modal")) toggle(false); });
    renderInspector();
    if (localStorage.getItem("ppa-explorer-open") === "1") setTimeout(() => toggle(true), 0);
  };
  /* A table of the appbook's own store, asked for from outside the explorer. */
  const openTable = async (name) => { if (!isOpen()) toggle(true); if (state.source !== "sqlite") show("sqlite", { load: false }); await loadTables(); await select(name); };
  return { init, reload, toggle, onActivity, state, select: openTable, show };
})();
