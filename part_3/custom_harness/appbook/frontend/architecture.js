/* Chapter 1. Architecture: one structure from the backend draws the diagram, the side panel and the stepper. */
(() => {
  const STATUS_ORDER = ["connected", "configured", "fallback", "off", "not_configured", "failing"];
  const STEP_MS = 4500, REFRESH_MS = 7000, LABEL_LIMIT = 12;
  const BUILD_NOTES = {
    partial: "Partial: it works, with a limit that the ledger below names.",
    mirror: "A local mirror of a component that the notebook runs on Oracle.",
  };
  const key = (from, to) => `${from}>${to}`;
  const chapterOf = (id) => PPA.chapters.find(chapter => chapter.id === id);

  /* Geometry: a curve from one node to another, leaving and arriving on the sides that face each other. */
  const route = (a, b, slotA, slotB) => {
    const ax = a.x + a.w / 2, ay = a.y + a.h / 2, bx = b.x + b.w / 2, by = b.y + b.h / 2;
    if (Math.abs(ay - by) < Math.min(a.h, b.h) / 2) {
      const forward = bx > ax, gap = forward ? b.x - (a.x + a.w) : a.x - (b.x + b.w);
      if (gap < 40) {
        const x1 = forward ? a.x + a.w : a.x, x2 = forward ? b.x : b.x + b.w, y = ay + (forward ? -7 : 7);
        return { d: `M${x1},${y} L${x2},${y}`, x: (x1 + x2) / 2, y: forward ? a.y - 8 : a.y + a.h + 8 };
      }
      const y1 = forward ? a.y : a.y + a.h, y2 = forward ? b.y : b.y + b.h;
      const lift = (forward ? -1 : 1) * Math.min(30, 12 + Math.abs(bx - ax) / 14);
      return { d: `M${ax},${y1} C${ax},${y1 + lift} ${bx},${y2 + lift} ${bx},${y2}`, x: (ax + bx) / 2, y: y1 + lift * .8 };
    }
    const down = by > ay, x1 = a.x + a.w * slotA, x2 = b.x + b.w * slotB;
    const y1 = down ? a.y + a.h : a.y, y2 = down ? b.y : b.y + b.h;
    const bend = Math.max(16, Math.abs(y2 - y1) * .45) * (down ? 1 : -1);
    return { d: `M${x1},${y1} C${x1},${y1 + bend} ${x2},${y2 - bend} ${x2},${y2}`, x: (x1 + x2) / 2, y: (y1 + y2) / 2 };
  };

  PPA.register({
    id: "architecture", n: 1, title: "Architecture",
    blurb: "The whole system before its parts. Select a component to read what it is, why the harness needs it and where it lives in the code. Each status is checked while you look. Trace a request to see which components a turn really touches.",
    tags: ["Every component", "Live status", "Trace a request", "Component ledger"],
    render: async (root) => {
      let data;
      try { data = await PPA.api("/api/architecture"); }
      catch (error) {
        /* The page is served from disk, so it can be newer than a backend that is still running. */
        if (error.message !== "Not Found") throw error;
        root.innerHTML = `<div class="notice" style="margin-top:24px"><strong>This view needs the backend to be started again.</strong> The page was updated after the running backend was started. Stop the appbook and run ./run.sh once more.</div>`;
        return;
      }
      const parts = new Map(data.components.map(part => [part.id, part]));
      const lanes = new Map(data.lanes.map(lane => [lane.id, lane]));
      const edges = new Map(data.edges.map(edge => [key(edge.from, edge.to), edge]));
      const view = { mode: "explore", selected: null, path: 0, step: 0, timer: null, checked: data.checked_at };
      const tone = (status) => status.startsWith("missing") ? "missing" : status.startsWith("partial") ? "partial" : status.startsWith("not-") ? "design" : "built";
      const label = (status) => data.statuses[status].label.toLowerCase();
      const metric = (part) => part.metric && part.metric.value !== null && part.metric.value !== undefined
        ? (typeof part.metric.value === "number" ? PPA.number(part.metric.value) : String(part.metric.value)) : "";
      const spoken = (part) => `${part.title}. ${lanes.get(part.lane).title}. ${label(part.status)}${part.metric ? `, ${metric(part)} ${part.metric.label}` : ""}`;
      const chapterBadge = (part) => { const chapter = chapterOf(part.jump.chapter); return chapter?.n ? `<em title="Chapter ${chapter.n}: ${esc(chapter.title)}">ch ${chapter.n}</em>` : ""; };
      /* A connected component shows its dot and its number. Any other status is spelled out. */
      const nodeState = (part) => `${part.status === "connected" ? "" : `<span class="node-word">${esc(label(part.status))}</span>`}<span class="node-state"><i class="dot ${part.status}"></i><span></span>${metric(part) ? `<b title="${esc(part.metric.label)}">${esc(metric(part))}</b>` : ""}${chapterBadge(part)}</span>`;

      const node = (part) => `<button class="arch-node" data-id="${esc(part.id)}" data-kind="${esc(part.id)}" aria-pressed="false" aria-label="${esc(spoken(part))}" title="${esc(part.label)}"><span class="node-title">${esc(part.title)}</span><span class="node-live">${nodeState(part)}</span></button>`;
      /* A lane whose components carry a group is drawn as captioned groups, as the notebook draws its cards. */
      const laneBody = (members) => {
        if (!members.some(part => part.group)) return `<div class="arch-nodes">${members.map(node).join("")}</div>`;
        const groups = new Map();
        for (const part of members) groups.set(part.group, [...(groups.get(part.group) || []), part]);
        return `<div class="arch-groups">${[...groups].map(([name, items]) => `<div class="arch-group" style="--n:${items.length}"><h4>${esc(name)}</h4><div class="arch-nodes">${items.map(node).join("")}</div></div>`).join("")}</div>`;
      };

      root.innerHTML = `<section id="refarch-section"><h2 class="panel-title" style="margin:20px 0 6px">Reference architecture</h2><p class="field-help">The application as built: six tiers, every component with its technology, and the data that flows between them. Select a component to read its role; play a run to watch one request move through the system. The component map below it is drawn from the same backend and checks every status live.</p><div id="refarch"></div></section>
        <h2 class="panel-title" style="margin:28px 0 6px">Component map, checked live</h2><section class="arch" id="arch">
        <div class="arch-bar">
          <div class="arch-modes" role="group" aria-label="What the diagram shows">
            <button data-mode="explore" aria-pressed="true">Explore components</button>
            <button data-mode="trace" aria-pressed="false">Trace a request</button>
          </div>
          <div class="arch-legend" aria-label="Status colours">${STATUS_ORDER.map(status => `<span title="${esc(data.statuses[status].meaning)}"><i class="dot ${status}"></i>${esc(data.statuses[status].label)}</span>`).join("")}</div>
          <span class="arch-checked" id="arch-checked"></span>
        </div>
        <div class="arch-trace" id="arch-trace" hidden>
          <div class="arch-paths" role="group" aria-label="Request to trace">${data.paths.map((path, index) => `<button data-path="${index}" aria-pressed="false" title="${esc(path.about)}"><small>${esc(path.kind)}</small>${esc(path.title)}</button>`).join("")}</div>
          <div class="arch-stepper">
            <button class="secondary small" id="arch-previous">Previous</button>
            <button class="primary small" id="arch-play">Play</button>
            <button class="secondary small" id="arch-next">Next</button>
            <span class="arch-count" id="arch-count"></span>
            <div class="arch-progress" id="arch-progress" role="group" aria-label="Steps"></div>
          </div>
          <div class="arch-step" id="arch-step" aria-live="polite"></div>
        </div>
        <div class="arch-layout">
          <div class="arch-diagram" id="arch-diagram" role="group" aria-label="Components, in lanes">
            <svg class="arch-edges" id="arch-edges" aria-hidden="true" focusable="false"></svg>
            ${data.lanes.map(lane => `<section class="arch-lane" data-lane="${esc(lane.id)}" aria-labelledby="lane-${esc(lane.id)}">
              <header><h3 id="lane-${esc(lane.id)}">${esc(lane.title)}</h3><p>${esc(lane.about)}</p></header>
              ${laneBody(data.components.filter(part => part.lane === lane.id))}
            </section>`).join("")}
          </div>
          <aside class="arch-panel" id="arch-panel" aria-label="Component details"></aside>
        </div>
        <section class="component-ledger"><header><div><span class="eyebrow">IMPLEMENTATION LEDGER</span><h2>What is built, partial and missing</h2></div><div class="row">${Object.entries(data.counts).map(([name, total]) => PPA.pill(`${name.replaceAll("_", " ")} ${total}`)).join("")}</div></header>
          <p class="action-copy">${esc(data.teaching_point)} Select a row to find its component in the diagram.</p>
          <div class="component-grid">${data.ledger.map(row => {
            const inner = `<i class="${tone(row.status)}"></i><div><strong>${esc(row.concern)}</strong><span>${esc(row.component)}</span><p>${esc(row.role)}</p></div><em>${esc(row.status.replaceAll("-", " "))}</em>`;
            return row.part ? `<button data-part="${esc(row.part)}">${inner}</button>` : `<article>${inner}</article>`;
          }).join("")}</div></section>
      </section>`;

      if (typeof RefArch !== "undefined" && typeof PPA_REFARCH !== "undefined") RefArch.render($("#refarch", root), PPA_REFARCH);
      const arch = $("#arch", root), diagram = $("#arch-diagram", root), svg = $("#arch-edges", root), panel = $("#arch-panel", root);
      const nodes = new Map($$(".arch-node", diagram).map(node => [node.dataset.id, node]));
      const path = () => data.paths[view.path], step = () => path().steps[view.step];

      /* What is lit: the step in a trace, or the selected component and its neighbours. */
      const lit = () => {
        if (view.mode === "trace") return { hot: new Set(step().components), near: new Set(), drawn: step().edges.map(([from, to]) => ({ ...edges.get(key(from, to)), tone: "hot" })) };
        if (!view.selected) return { hot: new Set(), near: new Set(), drawn: data.edges.filter(edge => edge.main).map(edge => ({ ...edge, tone: "rest" })) };
        const touching = data.edges.filter(edge => edge.from === view.selected || edge.to === view.selected);
        return { hot: new Set(), near: new Set(touching.flatMap(edge => [edge.from, edge.to])), drawn: touching.map(edge => ({ ...edge, tone: "near" })) };
      };

      const draw = () => {
        if (!diagram.isConnected) return;
        const box = diagram.getBoundingClientRect(), { drawn } = lit();
        const at = (id) => { const r = nodes.get(id).getBoundingClientRect(); return { x: r.left - box.left, y: r.top - box.top, w: r.width, h: r.height }; };
        /* Edges that share a side of a node are spread along it, ordered by where they go. */
        const sides = new Map();
        const place = (id, other, side, edge, end) => {
          const name = `${id}:${side}`;
          if (!sides.has(name)) sides.set(name, []);
          sides.get(name).push({ edge, end, x: other.x + other.w / 2 });
        };
        const shaped = drawn.map(edge => ({ ...edge, a: at(edge.from), b: at(edge.to) }));
        for (const edge of shaped) {
          const down = edge.b.y + edge.b.h / 2 > edge.a.y + edge.a.h / 2;
          place(edge.from, edge.b, down ? "bottom" : "top", edge, "slotA");
          place(edge.to, edge.a, down ? "top" : "bottom", edge, "slotB");
        }
        for (const list of sides.values()) list.sort((one, two) => one.x - two.x).forEach((item, index) => { item.edge[item.end] = (index + 1) / (list.length + 1); });
        const labelled = shaped.length <= LABEL_LIMIT && (view.mode === "trace" || view.selected);
        svg.innerHTML = `<defs>${["rest", "near", "hot"].map(name => `<marker id="arch-arrow-${name}" viewBox="0 0 8 8" refX="7.2" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path class="arrow-${name}" d="M0,0 L8,4 L0,8 z"/></marker>`).join("")}</defs>`
          + shaped.map(edge => { edge.line = route(edge.a, edge.b, edge.slotA, edge.slotB); return `<path class="${edge.tone}" d="${edge.line.d}" marker-end="url(#arch-arrow-${edge.tone})"/>`; }).join("")
          + (labelled ? shaped.map(edge => {
            const width = edge.label.length * 5.5 + 10;
            return `<g><rect x="${edge.line.x - width / 2}" y="${edge.line.y - 8}" width="${width}" height="15" rx="4"/><text x="${edge.line.x}" y="${edge.line.y + 3}" text-anchor="middle">${esc(edge.label)}</text></g>`;
          }).join("") : "");
      };

      const paint = () => {
        const { hot, near } = lit();
        diagram.classList.toggle("focused", view.mode === "trace" || !!view.selected);
        arch.classList.toggle("tracing", view.mode === "trace");
        for (const [id, node] of nodes) {
          node.classList.toggle("hot", hot.has(id));
          node.classList.toggle("near", near.has(id) && id !== view.selected);
          node.setAttribute("aria-pressed", String(id === view.selected));
        }
        draw();
      };
      const paintStatus = () => {
        for (const [id, node] of nodes) {
          const part = parts.get(id);
          $(".node-live", node).innerHTML = nodeState(part);
          node.setAttribute("aria-label", spoken(part));
        }
        $("#arch-checked").textContent = `Checked ${PPA.realTime(view.checked)} · ${data.responder} · ${data.substrate}`;
      };

      /* The side panel. */
      const list = (items) => `<ul class="arch-list">${items.join("")}</ul>`;
      const folded = (title, items, open = 8) => items.length > open ? `<details><summary>${esc(title)} (${items.length})</summary>${list(items)}</details>` : list(items);
      const overview = () => {
        const totals = STATUS_ORDER.map(status => [status, data.components.filter(part => parts.get(part.id).status === status).length]);
        return `<header><span class="eyebrow">HOW TO READ THIS VIEW</span><h2>${data.components.length} components in ${data.lanes.length} lanes</h2><p>Select a component in the diagram.</p></header>
          <section><h3>Status</h3>${list(totals.map(([status, total]) => `<li><i class="dot ${status}"></i><span><strong>${esc(data.statuses[status].label)}</strong> ${total}. ${esc(data.statuses[status].meaning)}</span></li>`))}</section>
          <section><h3>Lanes</h3>${list(data.lanes.map(lane => `<li><i class="lane-key" data-lane="${esc(lane.id)}"></i><span><strong>${esc(lane.title)}.</strong> ${esc(lane.about)}</span></li>`))}</section>
          <section><h3>Lines</h3><p>A line is something one component sends to another. With nothing selected the diagram shows the main flow of a request. Select a component to see every line that touches it.</p></section>`;
      };
      const steps = () => `<header><span class="eyebrow">TRACE · ${esc(path().kind)}</span><h2>${esc(path().title)}</h2><p>${esc(path().about)}</p></header>
        <section><h3>Steps</h3><ol class="arch-steps">${path().steps.map((item, index) => `<li><button data-step="${index}" ${index === view.step ? 'aria-current="step"' : ""}><span>${index + 1}</span>${esc(item.title)}</button></li>`).join("")}</ol></section>
        <section><h3>Lit in this step</h3>${list(step().components.map(id => `<li><i class="dot ${parts.get(id).status}"></i><button data-select="${esc(id)}">${esc(parts.get(id).title)}</button><em>${esc(lanes.get(parts.get(id).lane).title)}</em></li>`))}</section>`;
      const details = (part) => {
        const artefacts = part.artefacts, chapter = chapterOf(part.jump.chapter);
        const incoming = data.edges.filter(edge => edge.to === part.id), outgoing = data.edges.filter(edge => edge.from === part.id);
        const link = (edge, id) => `<li><button data-select="${esc(id)}">${esc(parts.get(id).title)}</button><em>${esc(edge.label)}</em></li>`;
        return `<header><span class="eyebrow">${esc(lanes.get(part.lane).title)}${part.group ? ` · ${esc(part.group)}` : ""}</span><h2>${esc(part.title)}</h2><p>${esc(part.label)}</p>${view.mode === "trace" ? '<div class="arch-jumps" style="margin-top:9px"><button class="secondary small" data-select="">Back to the steps</button></div>' : ""}</header>
          <section id="arch-live"><h3>Status, checked ${esc(PPA.realTime(view.checked))}</h3><div class="arch-status"><i class="dot ${part.status}"></i>${esc(data.statuses[part.status].label)}${part.metric ? `<b>${esc(metric(part))}</b><small>${esc(part.metric.label)}</small>` : ""}</div><p style="margin-top:7px">${esc(part.detail)}</p></section>
          <section><h3>What it is</h3><p>${esc(part.what)}</p></section>
          <section><h3>Why the harness needs it</h3><p>${esc(part.why)}</p></section>
          <section><h3>Technology and version</h3><p>${esc(part.technology)}${part.version ? `. Installed: ${esc(part.version)}.` : ""}</p>${BUILD_NOTES[part.build] ? `<p>${esc(BUILD_NOTES[part.build])}</p>` : ""}</section>
          ${part.tier ? `<section><h3>Trust tier</h3><p>${esc(part.tier)}</p>${list(Object.entries(data.tiers).map(([name, rule]) => `<li><span>${PPA.pill(name, name === "approval" ? "warn" : name === "never" ? "bad" : "")} ${esc(rule)}</span></li>`))}</section>` : ""}
          ${artefacts.tables.length ? `<section><h3>Tables</h3>${list(artefacts.tables.map(name => `<li><button data-table="${esc(name)}">${esc(name)}</button><em>open in the data explorer</em></li>`))}</section>` : ""}
          ${artefacts.tools.length ? `<section><h3>Tools</h3>${folded("Show the tools", artefacts.tools.map(tool => `<li><span>${esc(tool.name)}</span>${PPA.pill(tool.tier, tool.tier === "approval" ? "warn" : tool.tier === "never" ? "bad" : "")}</li>`))}</section>` : ""}
          ${artefacts.endpoints.length ? `<section><h3>Endpoints</h3>${list(artefacts.endpoints.map(name => `<li><span>${esc(name)}</span></li>`))}</section>` : ""}
          <section><h3>In the repository</h3>${list(artefacts.files.map(name => `<li><span>${esc(name)}</span></li>`))}</section>
          ${incoming.length ? `<section><h3>Receives from</h3>${folded("Show the components", incoming.map(edge => link(edge, edge.from)))}</section>` : ""}
          ${outgoing.length ? `<section><h3>Sends to</h3>${folded("Show the components", outgoing.map(edge => link(edge, edge.to)))}</section>` : ""}
          ${chapter || part.jump.table ? `<section><h3>See it live</h3><div class="arch-jumps">${chapter ? `<a class="secondary small" href="#${esc(chapter.id)}">${chapter.n ? `Chapter ${String(chapter.n).padStart(2, "0")}: ` : ""}${esc(chapter.title)}</a>` : ""}${part.jump.table ? `<button class="secondary small" data-table="${esc(part.jump.table)}">Table ${esc(part.jump.table)}</button>` : ""}</div></section>` : ""}`;
      };
      const renderPanel = () => {
        const part = view.selected && parts.get(view.selected);
        panel.innerHTML = part ? details(part) : view.mode === "trace" ? steps() : overview();
        panel.scrollTop = 0;
      };

      /* The stepper. */
      const renderTrace = () => {
        $("#arch-trace").hidden = view.mode !== "trace";
        $$("[data-mode]", arch).forEach(button => button.setAttribute("aria-pressed", String(button.dataset.mode === view.mode)));
        $$("[data-path]", arch).forEach(button => button.setAttribute("aria-pressed", String(Number(button.dataset.path) === view.path)));
        const total = path().steps.length;
        $("#arch-count").textContent = `Step ${view.step + 1} of ${total}`;
        $("#arch-previous").disabled = view.step === 0;
        $("#arch-next").disabled = view.step === total - 1;
        $("#arch-play").textContent = view.timer ? "Pause" : view.step === total - 1 ? "Play again" : "Play";
        $("#arch-progress").innerHTML = path().steps.map((item, index) => `<button data-step="${index}" class="${index < view.step ? "done" : ""}" ${index === view.step ? 'aria-current="step"' : ""} aria-label="Step ${index + 1}: ${esc(item.title)}" title="${esc(item.title)}"><i></i></button>`).join("");
        $("#arch-step").innerHTML = `<strong>${view.step + 1}. ${esc(step().title)}</strong><p>${esc(step().text)}</p>`;
        arch.style.setProperty("--arch-trace", `${$("#arch-trace").offsetHeight}px`);
      };
      /* Bring the lit components into view, below the header and the stepper. */
      const follow = () => {
        const lit = $$(".arch-node.hot", diagram).map(node => node.getBoundingClientRect());
        if (!lit.length) return;
        const top = Math.min(...lit.map(r => r.top)), bottom = Math.max(...lit.map(r => r.bottom));
        const clear = $("#topbar").offsetHeight + $("#arch-trace").offsetHeight + 22, floor = window.innerHeight - 60;
        if (top >= clear && bottom <= floor) return;
        window.scrollBy({ top: top - clear, behavior: "instant" });
      };
      const pause = () => { clearInterval(view.timer); view.timer = null; };
      const show = ({ follows = false } = {}) => { renderTrace(); paint(); renderPanel(); if (follows) requestAnimationFrame(follow); };
      const go = (index) => { view.step = Math.min(Math.max(index, 0), path().steps.length - 1); view.selected = null; show({ follows: true }); };
      const play = () => {
        if (view.timer) { pause(); renderTrace(); return; }
        if (view.step === path().steps.length - 1) view.step = -1;
        const advance = () => { if (view.step >= path().steps.length - 1) { pause(); renderTrace(); return; } go(view.step + 1); };
        view.timer = setInterval(advance, STEP_MS);
        advance();
      };
      const select = (id) => { view.selected = id && id !== view.selected ? id : null; if (view.mode === "trace") pause(); show(); };
      const openTable = (name) => PPA.explorer.select(name);

      arch.addEventListener("click", (event) => {
        const target = event.target.closest("button, a");
        if (!target || !arch.contains(target)) return;
        const d = target.dataset;
        if (target.classList.contains("arch-node")) select(d.id);
        else if (d.mode) { pause(); Object.assign(view, { mode: d.mode, selected: null, step: 0 }); show({ follows: d.mode === "trace" }); }
        else if (d.path !== undefined) { pause(); Object.assign(view, { path: Number(d.path), step: 0, selected: null }); show({ follows: true }); }
        else if (d.step !== undefined) { pause(); go(Number(d.step)); }
        else if (d.select !== undefined) { select(d.select || view.selected); if (d.select) nodes.get(d.select).scrollIntoView({ block: "nearest", behavior: "instant" }); }
        else if (d.table) openTable(d.table).catch(error => PPA.toast("The table was not opened", error.message, "bad"));
        else if (d.part) { pause(); Object.assign(view, { mode: "explore", selected: null }); select(d.part); nodes.get(d.part).scrollIntoView({ block: "center", behavior: "instant" }); nodes.get(d.part).focus({ preventScroll: true }); }
        else if (target.id === "arch-previous") { pause(); go(view.step - 1); }
        else if (target.id === "arch-next") { pause(); go(view.step + 1); }
        else if (target.id === "arch-play") play();
      });
      $("#arch-trace").addEventListener("keydown", (event) => {
        if (event.key === "ArrowRight") { pause(); go(view.step + 1); event.preventDefault(); }
        if (event.key === "ArrowLeft") { pause(); go(view.step - 1); event.preventDefault(); }
      });
      const escape = (event) => { if (event.key === "Escape" && view.selected && arch.contains(document.activeElement)) { const last = nodes.get(view.selected); select(null); last.focus(); } };
      document.addEventListener("keydown", escape);

      /* Live status: asked again on a timer and whenever the harness reports a change. */
      let asking = false, again = false, pending = 0;
      const refresh = async () => {
        if (!arch.isConnected) return;
        if (asking) { again = true; return; }        /* a change that arrives meanwhile is not lost */
        asking = true;
        try {
          const fresh = await PPA.api("/api/architecture/status");
          for (const [id, state] of Object.entries(fresh.components)) Object.assign(parts.get(id), state);
          view.checked = fresh.checked_at;
          paintStatus();
          if (view.selected) { const live = $("#arch-live", panel), top = panel.scrollTop; if (live) { const holder = document.createElement("div"); holder.innerHTML = details(parts.get(view.selected)); live.replaceWith($("#arch-live", holder)); panel.scrollTop = top; } }
          else if (view.mode === "explore") { const top = panel.scrollTop; panel.innerHTML = overview(); panel.scrollTop = top; }
        } catch (error) { $("#arch-checked").textContent = `The status could not be read: ${error.message}`; }
        finally { asking = false; if (again) { again = false; refresh(); } }
      };
      const soon = () => { clearTimeout(pending); pending = setTimeout(refresh, 500); };
      /* A read is not a change. Only writes, and the events of the harness itself, ask for a new status. */
      PPA.on("activity", (change) => { if (change.operation !== "READ") soon(); });
      for (const topic of ["run", "timer", "action", "notification", "safe_mode", "workspace", "clock", "focus", "reset"]) PPA.on(topic, soon);
      const ticking = setInterval(refresh, REFRESH_MS);
      /* The lines are drawn from where the components are, so they are drawn again when the layout moves. */
      const sized = new ResizeObserver(() => { arch.style.setProperty("--arch-top", `${$("#topbar").offsetHeight + 10}px`); draw(); });
      sized.observe(diagram); sized.observe($("#topbar"));
      document.fonts?.ready.then(draw);
      PPA.stageCleanups.push(() => { pause(); clearInterval(ticking); clearTimeout(pending); sized.disconnect(); document.removeEventListener("keydown", escape); });

      paintStatus();
      show();
    },
  });
})();
