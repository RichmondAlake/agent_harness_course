/* Chapters of the survey paper appbook. */
APP.brand = { mark: "SP", name: "Survey paper", line: "PART 3 ADVANCED · DEEP RESEARCH HARNESS" };
APP.topics = ["status", "ledger", "trace", "paper"];
APP.paper = { id: sessionStorage.getItem("paper-id") || null, data: null };
APP.selectPaper = (id) => { APP.paper.id = id; sessionStorage.setItem("paper-id", id || ""); };
APP.loadPaper = async () => { if (!APP.paper.id) return null; try { APP.paper.data = await APP.api(`/api/papers/${APP.paper.id}`); } catch (e) { APP.paper.data = null; APP.selectPaper(null); } return APP.paper.data; };
APP.renderTopbar = () => {
  const s = APP.status || {};
  $("#topbar").innerHTML = `<span class="chip ${s.ready ? "real" : ""}">Store <b>${s.database?.reachable ? "Oracle AI Database " + (s.database.version || "") : "not reachable"}</b></span>
    <span class="chip">Model <b>${esc(s.model || "")}</b> ${s.keys?.anthropic ? APP.pill("key", "good") : APP.pill("no key", "bad")}</span>
    <span class="chip">Search <b>Tavily</b> ${s.keys?.tavily ? APP.pill("key", "good") : APP.pill("no key", "bad")}</span>
    <span class="chip">Model calls <b>${s.usage?.calls ?? 0}</b> · ${APP.pill(`$${Number(s.usage?.cost_usd || 0).toFixed(2)}`)}</span>
    <span class="spacer"></span>${APP.paper.id ? `<span class="chip">Paper <b>${esc(APP.paper.id)}</b></span>` : ""}`;
};
const NODE_POS = { scope: [0, 1], outline_review: [1, 1], rescope: [1, 0], gather: [2, 1], tally: [3, 1], reflect: [3, 2], organise: [4, 1], write: [5, 1], review: [6, 1], assemble: [7, 1], publication_review: [8, 1], publish: [9, 1], close: [9, 0] };
APP.graphSvg = (shape, done = new Set(), now = new Set(), bad = new Set()) => {
  const W = 118, H = 46, GX = 132, GY = 70, pos = (id) => { const [c, r] = NODE_POS[id] || [10, 2]; return [20 + c * GX, 30 + r * GY]; };
  const edges = shape.edges.map(e => { const [x1, y1] = pos(e.source), [x2, y2] = pos(e.target); const back = x2 <= x1; const a = [x1 + (back ? W / 2 : W), y1 + (back ? 0 : H / 2)], b = [x2 + (back ? W / 2 : 0), y2 + (back ? 0 : H / 2)]; const mid = (a[0] + b[0]) / 2; return back ? `<path class="gedge conditional" d="M${a[0]},${a[1]} C${a[0]},${a[1] - 40} ${b[0]},${b[1] - 40} ${b[0]},${b[1]}"/>` : `<path class="gedge ${e.conditional ? "conditional" : ""}" d="M${a[0]},${a[1]} C${mid},${a[1]} ${mid},${b[1]} ${b[0]},${b[1]}"/>`; }).join("");
  const nodes = shape.nodes.map(n => { const [x, y] = pos(n.id); const cls = bad.has(n.id) ? "bad" : now.has(n.id) ? "now" : done.has(n.id) ? "done" : ""; return `<g class="gnode ${cls}" data-node="${n.id}" transform="translate(${x},${y})"><rect width="${W}" height="${H}"/><text x="8" y="19">${esc(n.id.replace("_", " ").slice(0, 16))}</text><text x="8" y="35" style="fill:var(--faint);font-size:9px">${esc(n.id.length > 16 ? n.id.replace("_", " ").slice(16) : "")}</text></g>`; }).join("");
  return `<svg class="graph-svg" viewBox="0 0 ${20 + 10 * GX + 40} ${30 + 2 * GY + 60}"><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="var(--faint)"/></marker></defs>${edges}${nodes}</svg>`;
};
const paperNodes = (data) => ({ done: new Set((data?.ledger || []).map(l => l.node)), now: new Set(data?.busy ? [] : (data?.next || [])), bad: new Set() });
const traceLines = (ledger) => `<div class="trace">${ledger.map(l => `<div class="line"><b>${esc(l.node)}</b><span>${esc(l.kind)}</span><span>${esc(typeof l.detail === "string" ? l.detail.slice(0, 160) : JSON.stringify(l.detail).slice(0, 160))}</span></div>`).join("") || APP.empty("No steps yet.")}</div>`;

const gatePanel = (data) => {
  if (!data.waiting_for_person) return "";
  const asked = data.asked || {}; const outline = "outline" in asked; const blocked = !outline && asked.release?.verdict === "BLOCKED";
  return `<div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">${outline ? "The outline waits for you" : "The paper waits for you"}</h2>${APP.pill("interrupt()", "warn")}</div><div class="panel-body">
    ${outline ? `<p class="field-help">Nothing has been read and nothing has been paid for beyond one planning call. Approve to search, read, reflect, organise and write; revise with a note to plan again.</p>
      <dl class="kv"><dt>Title</dt><dd><strong>${esc(asked.title)}</strong></dd><dt>Questions</dt><dd>${(asked.scope?.research_questions || []).map(q => esc(q)).join("<br>")}</dd><dt>Criteria</dt><dd>${(asked.scope?.inclusion_criteria || []).map(q => esc(q)).join("<br>")}</dd></dl>
      ${APP.table(["position", "kind", "title", "purpose", "queries"], asked.outline || [], (r, c) => c === "queries" ? esc((r.queries || []).join(" · ")) : esc(r[c]))}
      <label for="note">A note, for "revise"</label><textarea id="note" placeholder="Add a section on evaluation harnesses; merge the two memory sections."></textarea>`
      : `<dl class="kv"><dt>Title</dt><dd><strong>${esc(asked.title)}</strong></dd><dt>Size</dt><dd>${asked.counts?.sections} sections · ${asked.counts?.words} words · ${asked.counts?.sources_read} sources read · ${asked.counts?.sources_cited} cited</dd><dt>Claims</dt><dd>${asked.counts?.checked} cited claims checked · ${asked.counts?.kept} kept with a quote found on the page · ${asked.counts?.removed} removed</dd><dt>Release check</dt><dd>${APP.pill(asked.release?.verdict, asked.release?.verdict === "READY" ? "good" : "bad")} referee: ${esc(asked.release?.referee)} · spent $${asked.release?.spent_usd}</dd><dt>Abstract</dt><dd>${esc(asked.abstract)}</dd></dl>${APP.table(["check", "passed", "detail"], asked.release?.checks || [])}<p class="field-help">${blocked ? "The release check is BLOCKED. A plain approval does not publish a blocked paper: override it, or reject it." : "Approve to publish the paper."} It is readable below, and in chapter 6.</p>`}
    <div class="row" style="margin-top:10px">${outline ? `<label style="display:flex;gap:6px;align-items:center;font-size:12px;color:var(--muted)"><input type="checkbox" id="cut" /> Durability test: cut this run off inside the organise step</label>` : ""}<button class="primary" data-decide="${blocked ? "override" : "approve"}">${blocked ? "Publish anyway (override)" : "Approve"}</button>${outline ? `<button class="secondary" data-decide="revise">Revise the outline</button>` : ""}<button class="danger-button" data-decide="reject">Reject</button></div></div></div>`;
};

APP.register({
  id: "paper", title: "Write a survey",
  blurb: "Give the harness a subject. It plans an outline for you to approve, gathers scholarly sources, reads them into notes, organises a framework, writes every section from its evidence, reviews the draft, and stops again with the paper assembled.",
  render: async (root) => {
    const draw = async () => {
      const papers = (await APP.api("/api/papers")).papers; const data = await APP.loadPaper();
      let survey = null;
      if (data && data.sections.length && !data.busy) {
        try { const text = await (await fetch(`/api/papers/${data.paper_id}/paper.md`)).text(); if (!text.startsWith("{")) survey = text; } catch (e) {}
      }
      if (!root.isConnected) return;
      root.innerHTML = `<div class="grid wide-left" style="margin-top:20px"><div>
        <div class="panel"><div class="panel-head"><h2 class="panel-title">A new paper</h2></div><div class="panel-body">
          <label for="subject">Subject</label><input id="subject" value="agent harness engineering" />
          <label for="audience">Audience</label><input id="audience" value="researchers and engineers building agent systems" />
          <div class="row end" style="margin-top:10px"><button class="primary" id="start">Plan the paper</button></div>
          <p class="field-help">Half a minute to an outline. After approval, about ten minutes and a few dozen model calls to a reviewed, assembled paper.</p></div></div>
        ${data ? `<div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">${esc(data.title || data.paper_id)}</h2><span class="row">${data.busy ? APP.pill("working", "warn") : APP.pill(data.status, APP.tone(data.status))}${data.error ? APP.pill("error", "bad") : ""}</span></div><div class="panel-body">
            ${data.error ? `<div class="error">${esc(data.error)}</div>` : ""}
            ${data.status === "interrupted" ? `<div class="notice">The run stopped inside <strong>${esc(data.resume_from.join(", "))}</strong>. What finished was kept. <button class="secondary small" id="continue">Continue from the last checkpoint</button></div>` : ""}
            ${["published", "awaiting_publication", "awaiting_person"].includes(data.status) && data.sections.length ? `<div class="row" style="margin-bottom:12px"><a class="primary" href="#read">Read the paper</a><a class="secondary" href="/api/papers/${esc(data.paper_id)}/paper.html" target="_blank" rel="noopener">Open as a page</a><a class="secondary" href="/api/papers/${esc(data.paper_id)}/paper.md" target="_blank" rel="noopener">Markdown</a>${data.paper?.file ? `<span class="faint mono">saved as ${esc(data.paper.file)}</span>` : ""}</div>` : ""}
            <div class="tiles" style="margin-top:0"><div class="tile"><span>Sources</span><strong>${data.sources}</strong><small>pages read</small></div><div class="tile"><span>Sections</span><strong>${data.sections.length}</strong><small>of ${data.outline.length}</small></div><div class="tile"><span>Round</span><strong>${data.round}</strong><small>of ${APP.status.limits.max_rounds}</small></div><div class="tile"><span>Checkpoints</span><strong>${data.checkpoints}</strong></div></div>
            ${data.sections.length ? `<div style="margin-top:14px">${APP.table(["title", "words", "citations", "round"], data.sections, (r, c) => c === "words" || c === "citations" ? `${r[c]} ${(c === "words" && r[c] < APP.status.limits.min_words) || (c === "citations" && r[c] < APP.status.limits.min_citations) ? APP.pill("low", "warn") : ""}` : esc(r[c]))}</div>` : ""}
            </div></div>${gatePanel(data)}
          ${survey ? `<div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">The survey</h2><span class="row"><a class="secondary small" href="/api/papers/${esc(data.paper_id)}/paper.html" target="_blank" rel="noopener">Open as a page</a><a class="secondary small" href="/api/papers/${esc(data.paper_id)}/paper.md" target="_blank" rel="noopener">Markdown</a></span></div><div class="panel-body survey-copy result-copy">${APP.markdown(survey)}</div></div>` : ""}` : ""}
        </div><div>
        <div class="panel"><div class="panel-head"><h2 class="panel-title">Papers</h2></div><div class="panel-body flush"><div class="table-wrap"><table class="list"><tbody>${papers.map(p => `<tr data-paper="${esc(p.paper_id)}" style="cursor:pointer"><td><span class="mono">${esc(p.paper_id)}</span><br><small class="faint">${esc((p.title || p.subject || "").slice(0, 48))}</small></td><td>${APP.pill(p.busy ? "working" : p.status, p.busy ? "warn" : APP.tone(p.status))}</td></tr>`).join("") || `<tr><td class="faint">No papers yet.</td></tr>`}</tbody></table></div></div></div>
        <div id="trace-slot" style="margin-top:16px"></div>
        </div></div>`;
      TRACE.mount($("#trace-slot", root), APP.paper.id, data);
      $("#start").onclick = (ev) => APP.busy(ev.currentTarget, async () => { const r = await APP.post("/api/papers", { subject: $("#subject").value, audience: $("#audience").value }); APP.selectPaper(r.paper_id); await draw(); });
      $$("[data-paper]", root).forEach(row => row.onclick = () => { APP.selectPaper(row.dataset.paper); draw(); });
      $$("[data-decide]", root).forEach(b => b.onclick = (ev) => APP.busy(ev.currentTarget, async () => { await APP.post(`/api/papers/${data.paper_id}/decide`, { decision: b.dataset.decide, note: $("#note")?.value || "", cut_off: !!$("#cut")?.checked && b.dataset.decide === "approve" }); await draw(); }));
      const cont = $("#continue", root); if (cont) cont.onclick = (ev) => APP.busy(ev.currentTarget, async () => { await APP.post(`/api/papers/${data.paper_id}/continue`); await draw(); });
    };
    APP.on("ledger", (e) => TRACE.soon(e.paper_id));
    APP.on("trace", (e) => TRACE.soon(e.paper_id));
    APP.stageCleanups.push(TRACE.unmount);
    APP.on("paper", (e) => { if (e.paper_id === APP.paper.id) draw(); APP.refreshStatus(); });
    await draw();
  },
});

APP.register({
  id: "refarch", n: 1, title: "Reference architecture",
  blurb: "The application as built: six tiers, every component with its technology, and the data that flows between them. Select a component to read its role; play a run to watch one paper move through the system.",
  render: async (root) => {
    root.innerHTML = `<div id="refarch"></div><div class="notice" style="margin-top:16px"><strong>How to read it.</strong> Solid green lines are requests from a person; grey lines carry data; dashed amber lines are control (a check, a pause, a resume); purple lines write to or read from Oracle AI Database; dotted lines are events. The run player replays a real execution's steps: each step names the flow it uses and what the state looks like afterwards.</div>`;
    RefArch.render($("#refarch", root), SURVEY_REFARCH);
  },
});

APP.register({
  id: "architecture", n: 2, title: "The compiled graph",
  blurb: "The components, and the graph LangGraph compiles. gather and write are one node each in the graph but run once per section, made with Send.",
  render: async (root) => {
    const shape = await APP.api("/api/graph"); const data = await APP.loadPaper(); const { done, now, bad } = paperNodes(data); const s = APP.status;
    const parts = [["Person", "Approves the outline and the paper", "always"], ["LangGraph StateGraph", "The fixed shape, the Send fan-outs, two interrupts, the bounded revision loop", "connected"], ["OracleSaver", "A checkpoint after every step; a stopped run keeps the tasks that finished", s.database?.reachable ? "connected" : "failing"], ["Evidence library", "SURVEY_SOURCES with page text and a VECTOR embedding made inside the database", s.database?.reachable ? "connected" : "failing"], ["Tavily", "Search on scholarly venues; extract reads pages in full", s.keys?.tavily ? "configured" : "not configured"], ["Claude " + (s.model || ""), "Typed answers only: scope, notes, framework, sections, review, abstract", s.keys?.anthropic ? "configured" : "not configured"], ["Harness rules", `At least ${s.limits.min_words} words and ${s.limits.min_citations} citations per evidence section; every citation must resolve`, "connected"]];
    root.innerHTML = `<div class="panel" style="margin-top:20px"><div class="panel-head"><h2 class="panel-title">Components</h2></div><div class="panel-body flush">${APP.table(["component", "role", "status"], parts.map(p => ({ component: p[0], role: p[1], status: p[2] })), (r, c) => c === "status" ? APP.pill(r[c], r[c] === "connected" || r[c] === "always" ? "good" : r[c] === "configured" ? "" : "bad") : esc(r[c]))}</div></div>
      <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">The compiled graph</h2><span class="mono faint">${shape.nodes.length} nodes · dashed = conditional or Send</span></div><div class="panel-body">${APP.graphSvg(shape, done, now, bad)}<p class="field-help" id="node-note">Select a node to read what it does.</p></div></div>`;
    $$(".gnode", root).forEach(g => g.onclick = () => { const n = shape.nodes.find(x => x.id === g.dataset.node); $("#node-note", root).textContent = `${n.id}: ${n.note}`; });
    APP.on("ledger", async (e) => { if (e.paper_id !== APP.paper.id) return; const d = await APP.loadPaper(); const t = paperNodes(d); $$(".gnode", root).forEach(g => { g.classList.toggle("done", t.done.has(g.dataset.node)); g.classList.toggle("now", t.now.has(g.dataset.node)); }); });
  },
});

APP.register({
  id: "library", n: 3, title: "The evidence library",
  blurb: "Every page the harness read for the selected paper, stored with its text and an embedding made inside Oracle AI Database. Ask it by meaning.",
  render: async (root) => {
    const data = await APP.loadPaper(); if (!data) { root.innerHTML = APP.empty("Select or start a paper first."); return; }
    const sources = (await APP.api(`/api/papers/${data.paper_id}/sources`)).sources;
    root.innerHTML = `<div class="panel" style="margin-top:20px"><div class="panel-head"><h2 class="panel-title">Ask by meaning</h2></div><div class="panel-body"><div class="row"><input id="q" value="how agents compress and manage their context window" /><button class="primary" id="ask">Search the library</button></div><div id="hits" style="margin-top:12px"></div><p class="field-help">VECTOR_DISTANCE between the query's embedding and each source's, both computed by the ONNX model in the database. Smaller is closer.</p></div></div>
      <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">Sources</h2><span class="mono faint">${sources.length} pages</span></div><div class="panel-body flush">${APP.table(["section_key", "title", "url", "published", "content_chars", "round"], sources, (r, c) => c === "url" ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.url.slice(0, 50))}</a>` : esc(r[c] ?? ""))}</div></div>`;
    $("#ask", root).onclick = (ev) => APP.busy(ev.currentTarget, async () => { const r = await APP.post(`/api/papers/${data.paper_id}/similar`, { query: $("#q", root).value }); $("#hits", root).innerHTML = APP.table(["distance", "section_key", "title"], r.sources); });
  },
});

APP.register({
  id: "notes", n: 4, title: "Typed reading and the framework",
  blurb: "What the model read each source into, and the framework it organised from the notes: categories, a comparison table, open questions.",
  render: async (root) => {
    const data = await APP.loadPaper(); if (!data) { root.innerHTML = APP.empty("Select or start a paper first."); return; }
    const notes = (await APP.api(`/api/papers/${data.paper_id}/notes`)).notes; const t = data.taxonomy;
    root.innerHTML = `${t ? `<div class="panel" style="margin-top:20px"><div class="panel-head"><h2 class="panel-title">${esc(t.framework_name)}</h2></div><div class="panel-body">${APP.table(["name", "definition", "sources"], t.categories.map(c => ({ ...c, sources: c.source_ids.length })))}<h3 class="panel-title" style="margin-top:16px">Comparison</h3>${APP.table(["work", ...t.comparison.columns], t.comparison.rows.map(r => Object.fromEntries([["work", r.work], ...t.comparison.columns.map((c, i) => [c, r.cells[i] || ""])])))}<h3 class="panel-title" style="margin-top:16px">Open questions</h3><ul>${t.open_questions.map(q => `<li>${esc(q)}</li>`).join("")}</ul></div></div>` : `<div class="notice" style="margin-top:20px">The framework is built after the sources are read.</div>`}
      <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">Notes</h2><span class="mono faint">${notes.length}</span></div><div class="panel-body flush">${APP.table(["source_id", "title", "kind", "year", "relevance", "contribution"], notes, (r, c) => c === "relevance" ? APP.pill(r[c], r[c] === "high" ? "good" : r[c] === "low" ? "warn" : "") : esc(String(r[c] ?? "").slice(0, 140)))}</div></div>`;
  },
});

APP.register({
  id: "review", n: 5, title: "Rules and the referee",
  blurb: "Two kinds of quality gate: what the harness can count, and what the model judges. Every cited claim is checked for a quote found on its page. A revise verdict sends back the sections the budget allows, once.",
  render: async (root) => {
    const data = await APP.loadPaper(); if (!data) { root.innerHTML = APP.empty("Select or start a paper first."); return; }
    const reviews = data.reviews.map(r => ({ ...r, findings: JSON.parse(r.findings || "{}") }));
    root.innerHTML = `<div class="panel" style="margin-top:20px"><div class="panel-head"><h2 class="panel-title">Harness rules</h2></div><div class="panel-body">${data.problems.length ? APP.table(["key", "problem"], data.problems) : `<p class="faint">Every section meets the word and citation minimums.</p>`}${APP.table(["title", "words", "citations", "claims", "supported", "repaired", "removed", "round"], data.sections || [])}</div></div>
      ${reviews.map(r => `<div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">Referee pass ${r.round}</h2>${APP.pill(r.verdict, r.verdict === "accept" ? "good" : "warn")}</div><div class="panel-body"><p>${esc(r.findings.summary || "")}</p>${APP.table(["key", "unsupported_claims", "missing", "needs_more_evidence", "queries"], r.findings.sections || [], (x, c) => Array.isArray(x[c]) ? esc(x[c].join(" · ").slice(0, 200)) : esc(String(x[c])))}</div></div>`).join("") || APP.empty("No referee pass yet.")}`;
  },
});

APP.register({
  id: "read", n: 6, title: "The paper",
  blurb: "The assembled paper, as the harness wrote it: numbered citations in order of first use, a reference list in which every entry is a page it read, and a closing note on how it was made.",
  render: async (root) => {
    const data = await APP.loadPaper(); if (!data) { root.innerHTML = APP.empty("Select or start a paper first."); return; }
    let md = null; try { md = await (await fetch(`/api/papers/${data.paper_id}/paper.md`)).text(); } catch (e) {}
    if (!md || md.startsWith("{")) { root.innerHTML = APP.empty("The paper is not assembled yet."); return; }
    root.innerHTML = `<div class="row" style="margin-top:20px"><a class="secondary" href="/api/papers/${esc(data.paper_id)}/paper.html" target="_blank">Open as a page</a><a class="secondary" href="/api/papers/${esc(data.paper_id)}/paper.md" target="_blank">Markdown</a>${data.paper?.file ? APP.pill("published to " + data.paper.file.split("/").slice(-2).join("/"), "good") : ""}</div><div class="panel" style="margin-top:16px"><div class="panel-body result-copy">${APP.markdown(md)}</div></div>`;
  },
});

APP.register({
  id: "ledger", n: 7, title: "Ledger, checkpoints and cost",
  blurb: "Every step of the selected paper, the checkpoints LangGraph wrote, and what the model calls cost.",
  render: async (root) => {
    const data = await APP.loadPaper(); const s = APP.status;
    root.innerHTML = `<div class="tiles" style="margin-top:20px"><div class="tile"><span>Model calls</span><strong>${s.usage.calls}</strong><small>all papers</small></div><div class="tile"><span>Spent</span><strong>$${Number(s.usage.cost_usd).toFixed(2)}</strong><small>all papers</small></div><div class="tile"><span>Read from cache</span><strong>${(s.usage.cache_read_tokens / 1000).toFixed(1)}k</strong><small>tokens</small></div><div class="tile"><span>Output tokens</span><strong>${(s.usage.output_tokens / 1000).toFixed(1)}k</strong></div><div class="tile"><span>Checkpoints</span><strong>${data?.checkpoints ?? "–"}</strong><small>${esc(data?.paper_id || "no paper")}</small></div></div>
      <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">Ledger</h2></div><div class="panel-body">${data ? traceLines(data.ledger) : APP.empty("Select a paper.")}</div></div>
      <div class="row" style="margin-top:16px"><button class="danger-button small" id="reset">Empty the survey tables and their checkpoints</button></div>`;
    $("#reset", root).onclick = (ev) => APP.busy(ev.currentTarget, async () => { await APP.post("/api/reset"); APP.selectPaper(null); APP.rerender(); });
  },
});
