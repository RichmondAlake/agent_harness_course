/* The data explorer's second source: a read-only window on the notebook's Oracle AI Database. */
PPA.oracle = (() => {
  const state = { overview: null, selected: null, page: null, row: null, filter: "" };
  const objects = () => (state.overview?.groups || []).flatMap(group => group.objects);

  const preview = (value) => {
    if (value === null || value === undefined) return '<span class="null">NULL</span>';
    if (typeof value !== "object") { const text = String(value); return esc(text.length > 120 ? text.slice(0, 120) + "…" : text); }
    if (value.kind === "vector") return `<span class="cell-kind">vector</span>${value.dimension} dimensions · ${esc(value.first.join(", "))}, …`;
    if (value.kind === "json") { const text = JSON.stringify(value.value); return `<span class="cell-kind">json</span>${esc(text.length > 120 ? text.slice(0, 120) + "…" : text)}`; }
    return `<span class="cell-kind">${esc(value.kind)}</span>${PPA.number(value.length)} ${esc(value.unit)} · ${esc(value.first.slice(0, 80))}${value.truncated || value.first.length > 80 ? "…" : ""}`;
  };
  const full = (value) => {
    if (value === null || value === undefined) return { tag: "null", text: "NULL", size: "" };
    if (typeof value !== "object") return { tag: typeof value === "number" ? "number" : "text", text: String(value), size: "" };
    if (value.kind === "vector") return { tag: "vector", text: `[${value.first.join(", ")}, …]`, size: `${value.dimension} dimensions · format ${value.format} · the first ${value.first.length} numbers` };
    if (value.kind === "json") return { tag: "json", text: JSON.stringify(value.value, null, 2), size: "JSON, as the database returned it" };
    return { tag: value.kind, text: value.first, size: `${PPA.number(value.length)} ${value.unit}${value.truncated ? ` · the first ${value.unit === "bytes" ? "bytes" : "characters"} only` : ""} · ${value.encoding}` };
  };

  const renderList = () => {
    const o = state.overview, list = $("#oracle-table-list");
    if (!o) { list.innerHTML = PPA.empty("Asking the database"); return; }
    if (!o.reachable) { list.innerHTML = ""; return; }
    const filter = state.filter.toLowerCase();
    list.innerHTML = o.groups.map(group => {
      const items = group.objects.filter(item => !filter || `${item.name} ${group.name}`.toLowerCase().includes(filter));
      return items.length ? `<div class="table-group" title="${esc(group.about)}">${esc(group.name)}</div>` + items.map(item => `<button class="table-item ${state.selected === item.name ? "selected" : ""}" data-object="${esc(item.name)}" title="${esc(item.name)} · ${esc(item.kind)}"><span><i></i>${esc(item.name)}</span><b>${item.rows === null ? "?" : PPA.number(item.rows)}</b></button>`).join("") : "";
    }).join("") || PPA.empty("No table matches.");
  };
  const renderAbsent = () => {
    const o = state.overview;
    $("#oracle-toolbar").innerHTML = `<div class="explorer-name"><span class="eyebrow">ORACLE AI DATABASE · NOT REACHABLE</span><h2>${esc(o.dsn)}</h2><p>read as ${esc(o.user)} · ${esc(o.driver)}</p></div><div class="explorer-tools"><button class="secondary small" id="oracle-reload">Try again</button></div>`;
    $("#oracle-grid").innerHTML = `<div class="empty"><strong>${esc(o.detail)}</strong><br>The appbook keeps its own state in its local store, so nothing else here depends on this database.</div>`;
    $("#oracle-inspector").innerHTML = PPA.empty("The window is read-only. It never writes to the notebook's database.");
    $("#oracle-reload").onclick = () => open({ fresh: true });
  };
  const renderToolbar = () => {
    const p = state.page, o = state.overview;
    $("#oracle-toolbar").innerHTML = `<div class="explorer-name"><span class="eyebrow">${esc(p.group)} · ${esc(p.kind)} · ${p.columns.length} columns · ${p.ordered_by ? `newest first by ${esc(p.ordered_by)}` : "in the order the database returned them"}</span><h2>${esc(p.name)}</h2><p>${p.row_count === null ? "" : `${PPA.number(p.row_count)} rows · `}the newest ${p.limit} are shown · Oracle AI Database ${esc(o.version)} · read-only</p></div>
      <div class="explorer-tools"><button class="secondary small" id="oracle-reload">Refresh</button></div>`;
    $("#oracle-reload").onclick = () => open({ fresh: true });
  };
  const renderGrid = () => {
    const p = state.page;
    if (!p.rows.length) { $("#oracle-grid").innerHTML = PPA.empty(`${p.name} holds no rows.`); return; }
    $("#oracle-grid").innerHTML = `<table class="data-table"><thead><tr>${p.columns.map(c => `<th><div class="th-label"><span>${esc(c.name)}</span><small>${esc(c.type)}${c.nullable ? "" : " · NOT NULL"}</small></div></th>`).join("")}</tr></thead>
      <tbody>${p.rows.map((row, index) => `<tr data-row="${index}" class="${state.row === index ? "selected" : ""}" tabindex="0">${p.columns.map(c => `<td>${preview(row[c.name])}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  };
  const renderInspector = () => {
    const p = state.page, body = $("#oracle-inspector");
    if (!p || state.row === null || !p.rows[state.row]) { body.innerHTML = PPA.empty("Select a row to read its values. A vector shows its dimension and first numbers; a large object shows its length and first characters."); return; }
    body.innerHTML = `<p class="inspector-note">${esc(p.name)} · row ${state.row + 1} of the ${p.rows.length} shown</p>` + p.columns.map((column, index) => {
      const f = full(p.rows[state.row][column.name]), long = f.text.length > 80 || f.text.includes("\n") || f.size;
      return long ? `<details class="field" ${index < 0 ? "open" : ""}><summary><span class="item-index">${String(index + 1).padStart(2, "0")}</span><span>${esc(column.name)}</span><span class="origin-tag">${esc(f.tag)}</span></summary><div class="field-content"><pre>${esc(f.text)}</pre><div class="source-line">${esc(column.type)}${f.size ? " · " + esc(f.size) : ""}</div></div></details>`
        : `<div class="field short"><span class="item-index">${String(index + 1).padStart(2, "0")}</span><span>${esc(column.name)}</span><code class="${f.tag === "null" ? "null" : ""}">${esc(f.text)}</code></div>`;
    }).join("");
  };

  const select = async (name) => {
    state.selected = name; state.row = null;
    renderList();
    $("#oracle-grid").innerHTML = PPA.empty("Reading rows");
    try {
      const page = await PPA.api(`/api/oracle/objects/${encodeURIComponent(name)}`);
      if (name !== state.selected) return;
      if (!page.reachable) { state.overview = page; state.page = null; renderList(); renderAbsent(); return; }
      state.page = page;
      renderToolbar(); renderGrid(); renderInspector();
    } catch (error) { problem(error); }
  };
  /* A busy database is said plainly, with a way to ask again. */
  const problem = (error) => {
    $("#oracle-grid").innerHTML = `<div class="empty"><strong>${esc(error.message)}</strong><br><button class="secondary small" id="oracle-again" style="margin-top:10px">Try again</button></div>`;
    $("#oracle-again").onclick = () => open({ fresh: true });
  };
  const open = async ({ fresh = false } = {}) => {
    if (state.overview?.reachable && !fresh && state.page) return;
    $("#oracle-summary").textContent = "Asking the database";
    try { state.overview = await PPA.api("/api/oracle"); }
    catch (error) { $("#oracle-summary").textContent = "no answer in time"; problem(error); return; }
    const o = state.overview;
    $("#oracle-summary").textContent = o.reachable
      ? `${o.tables} tables · ${o.views} views · ${PPA.number(o.rows)} rows${o.uncounted ? ` (${o.uncounted} not counted: the database is busy)` : ""} · ${o.scheduler_jobs} scheduler jobs · ${o.models.map(m => m.name).join(", ") || "no model"}`
      : "not reachable";
    renderList();
    if (!o.reachable) { renderAbsent(); return; }
    const names = objects().map(item => item.name);
    await select(names.includes(state.selected) ? state.selected : (names.find(name => name === "PPA_TASKS") || names[0]));
  };

  const init = () => {
    $("#oracle-filter").oninput = (event) => { state.filter = event.target.value; renderList(); };
    $("#oracle-refresh").onclick = () => open({ fresh: true });
    $("#oracle-table-list").onclick = (event) => { const b = event.target.closest("[data-object]"); if (b) select(b.dataset.object); };
    const pick = (row) => { state.row = Number(row.dataset.row); $$("#oracle-grid tr").forEach(tr => tr.classList.toggle("selected", tr === row)); renderInspector(); };
    $("#oracle-grid").onclick = (event) => { const row = event.target.closest("[data-row]"); if (row) pick(row); };
    $("#oracle-grid").onkeydown = (event) => { const row = event.target.closest("[data-row]"); if (row && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); pick(row); } };
  };
  return { init, open, select, state };
})();
