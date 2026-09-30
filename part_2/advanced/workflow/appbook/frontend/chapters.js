/* Chapters of the trip workflow appbook. */
APP.brand = { mark: "TW", name: "Trip workflow", line: "PART 2 ADVANCED · WORKFLOW MODE" };
APP.topics = ["status", "ledger", "trip", "crash"];
APP.trip = { id: sessionStorage.getItem("trip-id") || null, data: null };
APP.selectTrip = (id) => { APP.trip.id = id; sessionStorage.setItem("trip-id", id || ""); };
APP.loadTrip = async () => { if (!APP.trip.id) return null; try { APP.trip.data = await APP.api(`/api/trips/${APP.trip.id}`); } catch (e) { APP.trip.data = null; APP.selectTrip(null); } return APP.trip.data; };
APP.renderTopbar = () => {
  const s = APP.status || {};
  $("#topbar").innerHTML = `<span class="chip ${s.ready ? "real" : ""}">Store <b>${s.database?.reachable ? "Oracle AI Database " + (s.database.version || "") : "not reachable"}</b></span>
    <span class="chip">Model <b>${esc(s.model || "")}</b> ${s.keys?.anthropic ? APP.pill("key", "good") : APP.pill("no key", "bad")}</span>
    <span class="chip">Search <b>Tavily</b> ${s.keys?.tavily ? APP.pill("key", "good") : APP.pill("no key", "bad")}</span>
    <span class="chip">System One <b>${s.system_one?.available ? esc(s.system_one.model) : "off"}</b> ${s.system_one?.available ? APP.pill("Jev", "good") : APP.pill("rules decide", "warn")}</span>
    <span class="chip">Model calls <b>${s.usage?.calls ?? 0}</b> · ${APP.pill(`${((s.usage?.input_tokens || 0) / 1000).toFixed(0)}k in`)}</span>
    <span class="spacer"></span>${APP.trip.id ? `<span class="chip">Trip <b>${esc(APP.trip.id)}</b></span>` : ""}`;
};

const NODE_POS = { recall_preferences: [0, 0], understand: [1, 0], ask_traveller: [2, -1], search_flight: [2, 0], search_hotel: [2, 1], search_car: [2, 2], join_offers: [3, 1], plan: [4, 1], review: [5, 1], replan: [5, 2], book_flight: [6, 0], book_hotel: [7, 0], book_car: [8, 0], compensate: [8, 1], confirm: [9, 0], close: [9, 2] };
APP.graphSvg = (shape, doneNodes = new Set(), nowNodes = new Set(), badNodes = new Set()) => {
  const W = 118, H = 46, GX = 132, GY = 68, pos = (id) => { const [c, r] = NODE_POS[id] || [10, 3]; return [20 + c * GX, 90 + r * GY]; };
  const edges = shape.edges.map(e => { const [x1, y1] = pos(e.source), [x2, y2] = pos(e.target); const a = [x1 + W, y1 + H / 2], b = [x2, y2 + H / 2]; const mid = (a[0] + b[0]) / 2; return `<path class="gedge ${e.conditional ? "conditional" : ""}" d="M${a[0]},${a[1]} C${mid},${a[1]} ${mid},${b[1]} ${b[0]},${b[1]}"/>`; }).join("");
  const nodes = shape.nodes.map(n => { const [x, y] = pos(n.id); const cls = badNodes.has(n.id) ? "bad" : nowNodes.has(n.id) ? "now" : doneNodes.has(n.id) ? "done" : ""; return `<g class="gnode ${cls}" data-node="${n.id}" transform="translate(${x},${y})"><rect width="${W}" height="${H}"/><text x="8" y="19">${esc(n.id.replace("_", " ").slice(0, 16))}</text><text x="8" y="35" style="fill:var(--faint);font-size:9px">${esc(n.id.length > 16 ? n.id.replace("_", " ").slice(16) : "")}</text></g>`; }).join("");
  return `<svg class="graph-svg" viewBox="0 0 ${20 + 10 * GX + 40} ${90 + 3 * GY + 60}"><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="var(--faint)"/></marker></defs>${edges}${nodes}</svg>`;
};
APP.tripNodes = (data) => {
  const done = new Set((data?.ledger || []).map(l => l.node)); const bad = new Set((data?.ledger || []).filter(l => l.kind === "provider_error").map(l => l.node));
  const now = new Set(data?.busy ? [] : (data?.next || [])); return { done, now, bad };
};

const itineraryCard = (data) => {
  const it = data.itinerary; if (!it) return "";
  const evidence = Object.fromEntries((data.offers || []).map(o => [o.offer_id, o]));
  return `<div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">Itinerary</h2><span class="mono faint">${APP.money(it.total_gbp)} · ${it.within_budget ? APP.pill("within budget", "good") : APP.pill("over budget", "bad")}</span></div><div class="panel-body">
    <div class="choices">${it.choices.map(c => `<div class="choice"><div class="comp">${esc(c.component)}</div><div><strong>${esc(c.offer.provider)}</strong> <span class="faint">· ${esc(c.offer.summary)}</span><div class="why">${esc(c.why)}</div><div class="row" style="margin-top:6px">${APP.pill(c.offer.confidence + " confidence", c.offer.confidence === "high" ? "good" : c.offer.confidence === "low" ? "warn" : "")}${APP.pill(`${c.alternatives.length} fallbacks`)}<a href="${esc(c.offer.url || "")}" target="_blank" rel="noopener">evidence page</a></div></div><div class="price">${APP.money(c.offer.total_gbp)}<small class="faint" style="display:block;font-weight:400">${esc(c.offer.price)} ${esc(c.offer.currency)} ${esc((c.offer.unit || "").replace("_", " "))}</small></div></div>`).join("")}</div>
    <p style="margin-top:14px">${esc(it.summary)}</p><ul class="plain">${(it.caveats || []).map(c => `<li class="faint">${esc(c)}</li>`).join("")}</ul>
    ${(it.checks || []).length ? `<h3 class="panel-title" style="margin-top:14px">Against the traveller's preferences · System One</h3>${APP.table(["component", "preference", "verdict"], it.checks, (r, c) => c === "verdict" ? APP.pill(r[c], r[c] === "honours" ? "good" : r[c] === "does not" ? "bad" : "") : esc(r[c]))}` : ""}</div></div>`;
};
const decisionPanel = (data) => {
  if (!data.waiting_for_traveller) return "";
  return `<div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">The run is paused at review</h2>${APP.pill("interrupt()", "warn")}</div><div class="panel-body">
    <p class="field-help">The itinerary is saved in Oracle. Nothing is booked. Whatever you decide resumes the same run from its checkpoint (${data.checkpoints} so far).</p>
    <label for="note">A note, for "change"</label><textarea id="note" placeholder="Choose a flight with a stated fare for my exact dates, even if it costs more."></textarea>
    <div class="row" style="margin-top:10px"><button class="primary" data-decide="approve">Approve and book</button><button class="secondary" data-decide="change">Ask for a change</button><button class="danger-button" data-decide="reject">Reject</button></div></div></div>`;
};
const bookingsTable = (data) => APP.table(["component", "status", "provider", "confirmation", "price_gbp", "reason"], data.bookings || [], (r, c) => c === "status" ? APP.pill(r[c], APP.tone(r[c])) : c === "price_gbp" ? APP.money(r[c]) : esc(r[c] ?? ""));
const traceLines = (ledger) => `<div class="trace">${ledger.map(l => `<div class="line"><b>${esc(l.node)}</b><span>${esc(l.kind)}</span><span>${esc(typeof l.detail === "string" ? l.detail.slice(0, 160) : JSON.stringify(l.detail).slice(0, 160))}</span></div>`).join("") || APP.empty("No steps yet.")}</div>`;

APP.register({
  id: "trip", title: "Book a trip",
  blurb: "One sentence in. The harness recalls the traveller, searches the real web for flights, hotels and cars at the same time, plans an itinerary from what it found, and stops for approval before it books anything.",
  render: async (root) => {
    // three travellers to start from; any name works, and a new name starts with no memories
    const EXAMPLES = [
      { traveller: "richmond", label: "richmond · London → Lisbon: flight, hotel and car", text: "Book me a trip from London to Lisbon, out on 12 October 2026 and back on 15 October 2026. I need a flight, a hotel and a car. Budget £900." },
      { traveller: "ada-okafor", label: "ada-okafor · Manchester → Barcelona for two, no car", text: "Book a trip for two from Manchester to Barcelona, out on 3 November 2026 and back on 6 November 2026. We need a flight and a hotel near the beach; no car. Budget £700." },
      { traveller: "sam-lee", label: "sam-lee · Edinburgh → Dublin: a hotel and a small car", text: "Fly me from Edinburgh to Dublin on 20 November 2026, back on 22 November 2026. A hotel near Temple Bar and a small car for the two days. Budget £500." },
    ];
    const form = { text: EXAMPLES[0].text, traveller: EXAMPLES[0].traveller };
    const draw = async () => {
      const trips = (await APP.api("/api/trips")).trips; const data = await APP.loadTrip();
      if (!root.isConnected) return;
      // keep what is being typed across redraws: a running trip redraws this view at every step
      if ($("#text", root)) { form.text = $("#text", root).value; form.traveller = $("#traveller", root).value; }
      root.innerHTML = `<div class="grid wide-left" style="margin-top:20px"><div>
        <div class="panel"><div class="panel-head"><h2 class="panel-title">A new trip</h2><select id="example" style="max-width:360px"><option value="">Start from an example…</option>${EXAMPLES.map((e, i) => `<option value="${i}">${esc(e.label)}</option>`).join("")}</select></div><div class="panel-body">
          <label for="text">What the traveller wants</label><textarea id="text">${esc(form.text)}</textarea>
          <div class="row" style="margin-top:8px"><label class="inline">Traveller <input id="traveller" value="${esc(form.traveller)}" placeholder="any name" style="width:180px" /></label><span class="spacer"></span><button class="primary" id="start">Plan the trip</button></div>
          <p class="field-help">About a minute: memory recall, one typed call to understand, one Tavily search per component wanted, typed extraction of offers, one typed call to plan. Any traveller name works (it is kept as a lower-case id, so "Ada Okafor" is ada-okafor); a new traveller has no memories yet, so the plan follows the request alone. To see memory shape a plan, seed what they prefer in chapter 3 first.</p></div></div>
        ${data ? `<div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">${esc(data.trip_id)}</h2><span class="row">${data.busy ? APP.pill("working", "warn") : APP.pill(data.status, APP.tone(data.status))}${data.error ? APP.pill("error", "bad") : ""}</span></div><div class="panel-body">
            ${data.error ? `<div class="error">${esc(data.error)}</div>` : ""}
            ${data.status === "interrupted" ? `<div class="notice">The run stopped inside <strong>${esc(data.resume_from.join(", "))}</strong> without finishing that step. <button class="secondary small" id="continue">Continue from the last checkpoint</button></div>` : ""}
            ${data.status === "needs_answers" ? `<div class="notice"><strong>The harness needs an answer:</strong><ul class="plain">${data.questions.map(q => `<li>${esc(q)}</li>`).join("")}</ul></div>` : ""}
            <dl class="kv" style="margin-top:10px"><dt>Preferences used</dt><dd>${(data.preferences || []).map(p => esc(p)).join("<br>") || "none"}</dd><dt>Understood as</dt><dd>${data.request ? esc(`${data.request.origin} → ${data.request.destination}, ${data.request.depart} to ${data.request.back}, ${data.request.nights} nights, wants ${data.request.wants.join(", ")}, budget ${data.request.budget_gbp} GBP`) : "…"}</dd><dt>Offers found</dt><dd>${Object.entries(data.offers_count || {}).map(([k, v]) => `${k}: ${v}`).join(" · ") || Object.entries(data.offers || {}).length ? "" : ""}${(data.offers || []).length} typed offers from ${(data.evidence || []).length} pages</dd><dt>Checkpoints</dt><dd>${data.checkpoints}</dd></dl></div></div>
          ${itineraryCard(data)}${decisionPanel(data)}
          <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">Bookings · the system of record</h2></div><div class="panel-body flush">${bookingsTable(data)}</div></div>` : ""}
        </div><div>
        <div class="panel"><div class="panel-head"><h2 class="panel-title">Trips</h2></div><div class="panel-body flush"><div class="table-wrap"><table class="list"><tbody>${trips.map(t => `<tr data-trip="${esc(t.trip_id)}" style="cursor:pointer"><td class="mono">${esc(t.trip_id)}</td><td>${APP.pill(t.busy ? "working" : t.status, t.busy ? "warn" : APP.tone(t.status))}</td></tr>`).join("") || `<tr><td class="faint">No trips yet.</td></tr>`}</tbody></table></div></div></div>
        <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">Live trace</h2><span class="mono faint" id="trace-count">${(data?.ledger || []).length} steps</span></div><div class="panel-body" id="trace">${traceLines(data?.ledger || [])}</div></div>
        </div></div>`;
      $("#example", root).onchange = (ev) => { const e = EXAMPLES[Number(ev.target.value)]; if (!e) return; $("#text", root).value = e.text; $("#traveller", root).value = e.traveller; };
      $("#start").onclick = (ev) => APP.busy(ev.currentTarget, async () => { const r = await APP.post("/api/trips", { text: $("#text").value, traveller_id: $("#traveller").value }); APP.selectTrip(r.trip_id); APP.toast("Trip started", `${r.trip_id} · traveller ${r.traveller_id}`); await draw(); });
      $$("[data-trip]", root).forEach(row => row.onclick = () => { APP.selectTrip(row.dataset.trip); draw(); });
      $$("[data-decide]", root).forEach(b => b.onclick = (ev) => APP.busy(ev.currentTarget, async () => { await APP.post(`/api/trips/${data.trip_id}/decide`, { decision: b.dataset.decide, note: $("#note")?.value || "" }); await draw(); }));
      const cont = $("#continue", root); if (cont) cont.onclick = (ev) => APP.busy(ev.currentTarget, async () => { await APP.post(`/api/trips/${data.trip_id}/continue`); await draw(); });
    };
    APP.on("ledger", (e) => { if (e.trip_id !== APP.trip.id) return; const box = $("#trace", root); if (!box) return; const line = document.createElement("div"); line.className = "line new"; line.innerHTML = `<b>${esc(e.node)}</b><span>${esc(e.kind)}</span><span>${esc(typeof e.detail === "string" ? e.detail.slice(0, 160) : JSON.stringify(e.detail).slice(0, 160))}</span>`; box.querySelector(".trace")?.append(line) || box.append(line); box.scrollTop = box.scrollHeight; });
    APP.on("trip", (e) => { if (e.trip_id === APP.trip.id) draw(); else APP.toast("Trip finished a step", e.trip_id); APP.refreshStatus(); });
    await draw();
  },
});

APP.register({
  id: "refarch", n: 1, title: "Reference architecture",
  blurb: "The application as built: six tiers, every component with its technology, and the data that flows between them. Select a component to read its role; play a run to watch one execution move through the system.",
  render: async (root) => {
    root.innerHTML = `<div id="refarch"></div><div class="notice" style="margin-top:16px"><strong>How to read it.</strong> Solid green lines are requests from a person; grey lines carry data; dashed amber lines are control (a decision, a pause, a resume); purple lines write to or read from Oracle AI Database; dotted lines are events. The run player replays a real execution's steps: each step names the flow it uses and what the state looks like afterwards.</div>`;
    RefArch.render($("#refarch", root), TRIP_REFARCH);
  },
});

APP.register({
  id: "architecture", n: 2, title: "The compiled graph",
  blurb: "The components the harness is made of, and the graph LangGraph compiles from the node functions. When a trip is selected, the nodes it has passed through light up.",
  render: async (root) => {
    const shape = await APP.api("/api/graph"); const data = await APP.loadTrip(); const { done, now, bad } = APP.tripNodes(data);
    const s = APP.status;
    const parts = [["Traveller", "A person who types one sentence and decides at the gate", "always"], ["LangGraph StateGraph", "Owns the shape: order, parallel branches, the interrupt, the saga, compensation", "connected"], ["OracleSaver", "A checkpoint in Oracle AI Database after every step, one thread per trip", s.database?.reachable ? "connected" : "failing"], ["Oracle Agent Memory", "What the traveller prefers, searched by meaning inside the database", s.database?.reachable ? "connected" : "failing"], ["Tavily", "Real web search; every page read becomes evidence", s.keys?.tavily ? "configured" : "not configured"], ["Claude " + (s.model || ""), "Typed answers only: understand, extract offers, plan", s.keys?.anthropic ? "configured" : "not configured"], ["System One · " + (s.system_one?.model || "Jev"), "Closed questions answered with a probability: memories, pages, preference checks, like-for-like fallbacks", s.system_one?.available ? "connected" : "fallback"], ["Booking system of record", "TRIP_BOOKINGS: idempotent bookings that stand for providers", "connected"], ["Ledger", "TRIP_LEDGER: every step of every run", "connected"]];
    root.innerHTML = `<div class="panel" style="margin-top:20px"><div class="panel-head"><h2 class="panel-title">Components</h2></div><div class="panel-body flush">${APP.table(["component", "role", "status"], parts.map(p => ({ component: p[0], role: p[1], status: p[2] })), (r, c) => c === "status" ? APP.pill(r[c], r[c] === "connected" || r[c] === "always" ? "good" : r[c] === "configured" ? "" : "bad") : esc(r[c]))}</div></div>
      <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">The compiled graph</h2><span class="mono faint">${shape.nodes.length} nodes · ${shape.edges.length} edges · dashed = conditional</span></div><div class="panel-body">${APP.graphSvg(shape, done, now, bad)}<p class="field-help" id="node-note">Select a node to read what it does.</p></div></div>
      <div class="notice" style="margin-top:16px"><strong>Three searches run in the same step.</strong> <code>after_understand</code> returns a list of node names; LangGraph runs them together and <code>join_offers</code> waits for all of them. The saga is the opposite: three steps in a fixed order, each safe to run twice.</div>`;
    $$(".gnode", root).forEach(g => g.onclick = () => { const n = shape.nodes.find(x => x.id === g.dataset.node); $("#node-note", root).textContent = `${n.id}: ${n.note}`; });
    APP.on("ledger", async (e) => { if (e.trip_id !== APP.trip.id) return; const d = await APP.loadTrip(); const t = APP.tripNodes(d); $$(".gnode", root).forEach(g => { g.classList.toggle("done", t.done.has(g.dataset.node)); g.classList.toggle("now", t.now.has(g.dataset.node)); g.classList.toggle("bad", t.bad.has(g.dataset.node)); }); });
  },
});

APP.register({
  id: "memory", n: 3, title: "Traveller memory",
  blurb: "Oracle Agent Memory keeps what a traveller prefers, across trips. The harness writes memories on purpose and recalls them by meaning when a request arrives.",
  render: async (root) => {
    const draw = async () => {
      const traveller = $("#mem-traveller", root)?.value || "richmond";
      const found = await APP.api(`/api/memory/${traveller}?query=${encodeURIComponent($("#mem-query", root)?.value || "travel preferences")}`);
      if (!root.isConnected) return;
      root.innerHTML = `<div class="grid two" style="margin-top:20px"><div class="panel"><div class="panel-head"><h2 class="panel-title">Recall by meaning</h2></div><div class="panel-body">
        <div class="row"><label class="inline">Traveller <input id="mem-traveller" value="${esc(traveller)}" style="width:120px" /></label><input id="mem-query" value="${esc($("#mem-query", root)?.value || "travel preferences")}" /><button class="secondary" id="mem-search">Recall</button></div>
        <ul style="margin-top:12px">${found.recalled.map(m => `<li>${esc(m)}</li>`).join("") || "<li class='faint'>Nothing is known about this traveller yet.</li>"}</ul></div></div>
        <div class="panel"><div class="panel-head"><h2 class="panel-title">Remember something</h2></div><div class="panel-body"><label for="mem-text">A statement about the traveller</label><textarea id="mem-text" placeholder="Prefers a direct flight and a morning departure."></textarea><div class="row" style="margin-top:8px"><select id="mem-kind" style="width:auto"><option value="preference">preference</option><option value="fact">fact</option><option value="guideline">guideline</option></select><button class="primary" id="mem-add">Remember</button><span class="spacer"></span><button class="danger-button small" id="mem-forget">Forget this traveller</button></div><p class="field-help">The same statement stored twice is stored once: the memory id is a hash of the text.</p></div></div></div>
        <div class="notice" style="margin-top:16px"><strong>Where it lives.</strong> The memory store's tables are in the same schema as the workflow tables, under the prefix <code>TRIPMEM</code>, with vectors made by the ONNX model inside the database.</div>`;
      $("#mem-search", root).onclick = draw;
      $("#mem-add", root).onclick = (ev) => APP.busy(ev.currentTarget, async () => { const r = await APP.post(`/api/memory/${$("#mem-traveller", root).value}`, { content: $("#mem-text", root).value, kind: $("#mem-kind", root).value }); APP.toast(r.stored ? "Remembered" : "Already known", r.memory_id); await draw(); });
      $("#mem-forget", root).onclick = (ev) => APP.busy(ev.currentTarget, async () => { await APP.del(`/api/memory/${$("#mem-traveller", root).value}`); await draw(); });
    };
    await draw();
  },
});

APP.register({
  id: "evidence", n: 4, title: "Real search evidence",
  blurb: "Every page the harness read for the selected trip, and every typed offer it extracted. An offer always names the page it came from, and carries a confidence.",
  render: async (root) => {
    const data = await APP.loadTrip();
    if (!data) { root.innerHTML = APP.empty("Select or start a trip first."); return; }
    const kept = data.evidence.filter(e => e.kept !== 0).length;
    root.innerHTML = `<div class="panel" style="margin-top:20px"><div class="panel-head"><h2 class="panel-title">Offers</h2><span class="mono faint">${data.offers.length} extracted</span></div><div class="panel-body flush">${APP.table(["component", "provider", "summary", "price", "currency", "price_gbp", "confidence"], data.offers, (r, c) => c === "confidence" ? APP.pill(r[c], r[c] === "high" ? "good" : r[c] === "low" ? "warn" : "") : esc(r[c] ?? ""))}</div></div>
      <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">Pages found</h2><span class="mono faint">${data.evidence.length} pages · ${kept} read by the model · screened by System One</span></div><div class="panel-body flush">${APP.table(["component", "title", "url", "relevance", "attack", "kept"], data.evidence, (r, c) => c === "url" ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.url.slice(0, 50))}</a>` : c === "kept" ? (r.kept === 0 ? APP.pill("skipped", "warn") : APP.pill("read", "good")) : (c === "relevance" || c === "attack") ? (r[c] === null || r[c] === undefined ? "" : Number(r[c]).toFixed(2)) : esc(r[c] ?? ""))}</div></div>
      <div class="notice" style="margin-top:16px"><strong>Indicative, and labelled.</strong> A price on a search page is what that page showed at the time, not a fare held for this traveller. High confidence means the page stated a price for these dates; low means a "from" teaser.</div>`;
  },
});

APP.register({
  id: "saga", n: 5, title: "The booking saga and compensation",
  blurb: "Flight, hotel, car: three steps in a fixed order against a system of record. Make a provider fail on purpose and watch the harness cancel what it booked, fall back to the next offer, and ask the traveller again.",
  render: async (root) => {
    const draw = async () => {
      const data = await APP.loadTrip(); const faults = (await APP.api("/api/faults")).faults;
      if (!root.isConnected) return;
      const hotel = data?.itinerary?.choices?.find(c => c.component === "hotel");
      root.innerHTML = `<div class="grid two" style="margin-top:20px"><div class="panel"><div class="panel-head"><h2 class="panel-title">Make a provider fail</h2></div><div class="panel-body">
        <div class="row"><select id="fault-component" style="width:auto"><option value="hotel">hotel</option><option value="flight">flight</option><option value="car">car</option></select><input id="fault-match" placeholder="provider name to match" value="${esc(hotel?.offer?.provider || "")}" /><select id="fault-kind" style="width:auto"><option>sold_out</option><option>price_changed</option><option>provider_down</option></select><button class="primary" id="fault-add">Arm the fault</button></div>
        <p class="field-help">The next booking whose provider contains this text fails once. Arm it, then approve the itinerary in "Book a trip".</p>
        ${APP.table(["component", "match", "fault", "remaining"], faults)}</div></div>
        <div class="panel"><div class="panel-head"><h2 class="panel-title">Bookings for ${esc(data?.trip_id || "no trip")}</h2></div><div class="panel-body flush">${data ? bookingsTable(data) : APP.empty("Select a trip.")}</div></div></div>
        <div class="notice" style="margin-top:16px"><strong>Idempotency key</strong> = <code>trip:component:offer:attempt</code>. A crash and a resume keep the attempt, so they replay the confirmation. A compensation raises it, so booking the same offer again is a new booking.</div>`;
      $("#fault-add", root).onclick = (ev) => APP.busy(ev.currentTarget, async () => { await APP.post("/api/faults", { component: $("#fault-component", root).value, match: $("#fault-match", root).value, fault: $("#fault-kind", root).value }); await draw(); });
    };
    APP.on("trip", draw);
    await draw();
  },
});

APP.register({
  id: "crash", n: 6, title: "Crash and resume",
  blurb: "Two real processes. The first plans a trip, approves it, and is killed inside book_flight after the booking is committed. The second continues from the last checkpoint: the flight is replayed, not booked twice.",
  render: async (root) => {
    root.innerHTML = `<div class="panel" style="margin-top:20px"><div class="panel-head"><h2 class="panel-title">Run the two-process proof</h2><button class="primary" id="crash-run">Kill a process and continue</button></div><div class="panel-body"><p class="field-help">About two minutes: the child process searches and plans, then exits with code 3 on purpose. The parent then continues the same trip. The script is <code>part_2/advanced/scripts/trip_crash_and_resume.py</code>.</p><div class="console" id="crash-console">Press the button.</div></div></div>`;
    const box = $("#crash-console", root);
    APP.on("crash", (e) => { if (e.line) { box.textContent += (box.textContent === "Press the button." ? "" : "\n") + e.line; if (box.textContent.startsWith("Press the button.")) box.textContent = e.line; } if (e.done) { box.textContent += `\n[parent finished, exit ${e.exit_code}]`; APP.selectTrip(e.trip_id); } box.scrollTop = box.scrollHeight; });
    $("#crash-run", root).onclick = (ev) => APP.busy(ev.currentTarget, async () => { box.textContent = "starting…"; await APP.post("/api/crash_demo"); });
  },
});

APP.register({
  id: "system_one", n: 7, title: "System One: a model that decides",
  blurb: "Claude reasons, plans and writes. Four decisions in this workflow have a closed set of answers, and a System One model (Jev) answers each with a probability in about a third of a second. The harness owns the threshold, falls back to a rule without the key, and logs every call.",
  render: async (root) => {
    const s = await APP.api("/api/system_one/status"); const data = await APP.loadTrip();
    const decisions = data ? (await APP.api(`/api/trips/${data.trip_id}/decisions`)).decisions : [];
    root.innerHTML = `<div class="notice ${s.available ? "good" : ""}" style="margin-top:20px"><strong>${esc(s.label)}.</strong> ${s.available ? "The text being judged goes to Typesafe: memories, search results, offers." : "Set TYPESAFE_API_KEY and start the appbook again. Until then the rules on the right decide."}</div>
      <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">Four decisions</h2><span class="mono faint">thresholds: ${Object.entries(s.thresholds).map(([k, v]) => `${k} ${v}`).join(" · ")}</span></div><div class="panel-body flush">${APP.table(["decision", "question", "used_by", "fallback"], s.decisions_made_for)}</div></div>
      <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">Decisions for ${esc(data?.trip_id || "no trip")}</h2><span class="mono faint">${decisions.length} calls</span></div><div class="panel-body flush">${APP.table(["kind", "summary", "questions", "seconds", "input_tokens", "outcome", "answers"], decisions, (r, c) => c === "answers" ? `<button class="secondary small" data-detail="${esc(r.decision_id)}">show</button>` : esc(r[c] ?? ""))}</div></div>
      <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">What the decisions cost</h2><span class="mono faint">${s.price_per_million_input_tokens_usd} USD per million input tokens · output is free</span></div><div class="panel-body flush">${APP.table(["kind", "calls", "questions", "mean_seconds", "input_tokens", "usd"], s.costs)}</div></div>`;
    $$("[data-detail]", root).forEach(b => b.onclick = () => { const d = decisions.find(x => x.decision_id === b.dataset.detail); APP.modal(`${d.kind}: ${d.summary}`, APP.json(d.detail)); });
  },
});

APP.register({
  id: "ledger", n: 8, title: "Ledger, checkpoints and cost",
  blurb: "What the database holds about the selected trip: every step in the ledger, the checkpoints LangGraph wrote, and what the model calls cost.",
  render: async (root) => {
    const data = await APP.loadTrip(); const s = APP.status;
    root.innerHTML = `<div class="tiles" style="margin-top:20px"><div class="tile"><span>Model calls</span><strong>${s.usage.calls}</strong><small>this process</small></div><div class="tile"><span>Input tokens</span><strong>${(s.usage.input_tokens / 1000).toFixed(1)}k</strong></div><div class="tile"><span>Output tokens</span><strong>${(s.usage.output_tokens / 1000).toFixed(1)}k</strong></div><div class="tile"><span>Checkpoints</span><strong>${data?.checkpoints ?? "–"}</strong><small>${esc(data?.trip_id || "no trip")}</small></div></div>
      <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">Ledger</h2></div><div class="panel-body">${data ? traceLines(data.ledger) : APP.empty("Select a trip.")}</div></div>
      <div class="row" style="margin-top:16px"><button class="danger-button small" id="reset">Empty the workflow tables and its checkpoints</button></div>`;
    $("#reset", root).onclick = (ev) => APP.busy(ev.currentTarget, async () => { await APP.post("/api/reset"); APP.selectTrip(null); APP.toast("Reset", "The trip tables and their checkpoints are empty."); APP.rerender(); });
  },
});
