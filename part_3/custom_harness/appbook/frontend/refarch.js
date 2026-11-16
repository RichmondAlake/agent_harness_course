/* A technical reference architecture: tiers, components with icons, labelled data flows, a legend, and a
   player that simulates one execution step by step. Standalone: it needs only a root element and a spec.

   spec = {
     tiers: [{ id, title, note }],                           // drawn top to bottom
     components: [{ id, tier, col, name, tech, kind, note }], // kind picks the icon and the legend entry
     flows: [{ id, from, to, label, kind, dx, dy }],         // kind: request | data | control | store | event
     runs: [{ id, title, blurb, steps: [{ flow, note, state }] }],
   }
   RefArch.render(root, spec) draws it and wires the player.

   Routing: a flow between tiers leaves the bottom (or top) of its box and arrives at the top (or bottom)
   of the other; several flows on one edge are spread along it so they do not fan from one point. A flow
   between boxes of the same tier never crosses a box: left to right it runs in a lane under the boxes,
   right to left in a lane above them. Labels are drawn last, so nothing hides them. */
const RefArch = (() => {
  const ICONS = {
    person: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-7 8-7s8 3 8 7"/>',
    browser: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M7 6.5h.01M10 6.5h.01"/>',
    api: '<rect x="3" y="5" width="18" height="6" rx="1.5"/><rect x="3" y="13" width="18" height="6" rx="1.5"/><path d="M7 8h.01M7 16h.01"/>',
    loop: '<path d="M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3"/><path d="M18 3v4h-4M6 21v-4h4"/>',
    model: '<path d="M12 3a4 4 0 0 1 4 4c2 0 4 2 4 4s-2 4-4 4a4 4 0 0 1-8 0c-2 0-4-2-4-4s2-4 4-4a4 4 0 0 1 4-4z"/><path d="M12 7v12M8 11h8"/>',
    decide: '<circle cx="12" cy="13" r="8"/><path d="M12 13l4-4M12 5V3M5 13H3M21 13h-2"/>',
    gate: '<path d="M4 20V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v14"/><path d="M8 12l3 3 5-6"/>',
    tools: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18v3h3l6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.1-2.1z"/>',
    mcp: '<circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="M8.3 11l7.4-3.7M8.3 13l7.4 3.7"/>',
    search: '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/>',
    database: '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    vector: '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 10h16M4 14h16M10 4v16M14 4v16"/>',
    memory: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3"/>',
    checkpoint: '<path d="M5 21V4"/><path d="M5 4h12l-3 4 3 4H5"/>',
    ledger: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/>',
    timer: '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l3 2M10 2h4"/>',
    mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
    calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    doc: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/>',
    file: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/>',
    shield: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
    cloud: '<path d="M7 18a4 4 0 0 1-.6-8A6 6 0 0 1 18 9a4 4 0 0 1 1 8.9H7z"/>',
    booking: '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M3 11h18M7 15h4"/>',
    bell: '<path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 21h4"/>',
    sse: '<path d="M4 12h4l2-6 4 12 2-6h4"/>',
    output: '<path d="M4 4h10l6 6v10H4z"/><path d="M14 4v6h6M8 15l3 3 5-6"/>',
    agent: '<rect x="4" y="7" width="16" height="12" rx="3"/><circle cx="9" cy="13" r="1.5"/><circle cx="15" cy="13" r="1.5"/><path d="M12 3v4M8 19v2M16 19v2"/>',
    skills: '<path d="M4 6h16v12H4z"/><path d="M8 10h8M8 14h5"/><path d="M4 6l2-3h12l2 3"/>',
  };
  const KINDS = {
    person: ["People", "person"], channel: ["Channel", "browser"], control: ["Control plane", "api"],
    model: ["Reasoning model", "model"], decide: ["System One model", "decide"], gate: ["Human gate", "gate"],
    tool: ["Tool or connector", "tools"], external: ["External service", "cloud"], store: ["Data store", "database"],
    output: ["Output", "output"], observe: ["Observability", "ledger"],
  };
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const icon = (name) => `<svg viewBox="0 0 24 24" class="ra-icon" aria-hidden="true">${ICONS[name] || ICONS.api}</svg>`;

  // geometry: a box is W×H at NODE_Y inside its tier band; lanes for same-tier flows sit above and below the boxes
  const W = 200, H = 60, COLW = 216, TIERH = 140, LEFT = 24, TOP = 8, NODE_Y = 38, R = 8, LANE_UP = 30, LANES_DOWN = [112, 128];
  const TECH_CHARS = 25;  // what fits on one line of the tech text at 10px mono

  const wrapTech = (text) => {
    // at most two lines, broken at spaces; the second line is cut with an ellipsis when it still does not fit
    const words = String(text || "").split(" "), lines = [""];
    for (const w of words) {
      const cur = lines[lines.length - 1];
      if (!cur) lines[lines.length - 1] = w;
      else if ((cur + " " + w).length <= TECH_CHARS) lines[lines.length - 1] = cur + " " + w;
      else if (lines.length < 2) lines.push(w);
      else { lines[1] = (lines[1] + " " + w); break; }
    }
    if (lines[1] && lines[1].length > TECH_CHARS) lines[1] = lines[1].slice(0, TECH_CHARS - 1).trimEnd() + "…";
    return lines;
  };

  const place = (spec) => {
    const tierIndex = Object.fromEntries(spec.tiers.map((t, i) => [t.id, i]));
    const pos = {};
    for (const c of spec.components) pos[c.id] = { x: LEFT + c.col * COLW, y: TOP + tierIndex[c.tier] * TIERH + NODE_Y, tier: tierIndex[c.tier] };
    const cols = Math.max(...spec.components.map(c => c.col)) + 1;
    return { pos, width: LEFT + cols * COLW + 8, height: TOP + spec.tiers.length * TIERH + 4 };
  };

  const orth = (sx, sy, ex, ey, ly) => {
    // from (sx,sy) to the lane, along it, and back to (ex,ey), with rounded corners
    const dir = ly > sy ? 1 : -1, side = ex > sx ? 1 : -1;
    return `M${sx},${sy} L${sx},${ly - dir * R} Q${sx},${ly} ${sx + side * R},${ly} L${ex - side * R},${ly} Q${ex},${ly} ${ex},${ly - dir * R} L${ex},${ey}`;
  };

  const route = (spec, pos) => {
    const paths = {};
    // flows between tiers: spread the exits and the entries along each box edge, ordered by where they go
    const ports = {};  // "node:bottom" -> [{ flow, other }]
    const port = (node, side, flow, other) => (ports[`${node}:${side}`] = ports[`${node}:${side}`] || []).push({ flow, other });
    const cross = spec.flows.filter(f => pos[f.from].tier !== pos[f.to].tier);
    for (const f of cross) {
      const a = pos[f.from], b = pos[f.to], down = b.tier > a.tier;
      port(f.from, down ? "bottom" : "top", f.id, b.x);
      port(f.to, down ? "top" : "bottom", f.id, a.x);
    }
    const at = {};  // flow id -> { node: x }
    for (const [key, list] of Object.entries(ports)) {
      const [node] = key.split(":"); list.sort((p, q) => p.other - q.other);
      list.forEach((p, i) => { (at[p.flow] = at[p.flow] || {})[node] = pos[node].x + 28 + (W - 56) * (i + 0.5) / list.length; });
    }
    for (const f of cross) {
      const a = pos[f.from], b = pos[f.to], down = b.tier > a.tier;
      const sx = at[f.id][f.from], ex = at[f.id][f.to], sy = down ? a.y + H : a.y, ey = down ? b.y : b.y + H, my = (sy + ey) / 2;
      const points = []; for (let i = 0; i <= 40; i++) { const t = i / 40, u = 1 - t; points.push([u * u * u * sx + 3 * u * u * t * sx + 3 * u * t * t * ex + t * t * t * ex, u * u * u * sy + 3 * u * u * t * my + 3 * u * t * t * my + t * t * t * ey]); }
      paths[f.id] = { d: `M${sx},${sy} C${sx},${my} ${ex},${my} ${ex},${ey}`, points };
    }
    // flows within a tier run in lanes: two under the boxes, one above; a lane is shared only when nothing else is free
    const LANES = { up: LANE_UP, a: LANES_DOWN[0], b: LANES_DOWN[1] };
    const busy = {}, arrivals = {};
    for (const f of spec.flows.filter(f => pos[f.from].tier === pos[f.to].tier)) {
      const a = pos[f.from], b = pos[f.to], tierTop = TOP + a.tier * TIERH, forward = b.x > a.x;
      const sx = forward ? a.x + W - 30 : a.x + 30, ex0 = forward ? b.x + 30 : b.x + W - 30, lo = Math.min(sx, ex0), hi = Math.max(sx, ex0);
      const lanes = busy[a.tier] = busy[a.tier] || { up: [], a: [], b: [] };
      const order = forward ? ["a", "b", "up"] : ["up", "a", "b"];
      const lane = order.find(l => !lanes[l].some(([l0, h0]) => l0 < hi && h0 > lo)) || order[0];
      lanes[lane].push([lo, hi]);
      const below = lane !== "up", key = `${f.to}:${below ? "bottom" : "top"}`, k = arrivals[key] = (arrivals[key] || 0);
      arrivals[key] += 1;
      const ex = ex0 + (forward ? 1 : -1) * k * 20, sy = below ? a.y + H : a.y, ey = below ? b.y + H : b.y, ly = tierTop + LANES[lane];
      paths[f.id] = { d: orth(sx, sy, ex, ey, ly), points: [[sx, sy], [sx, ly], [ex, ly], [ex, ey]] };
    }
    return paths;
  };

  const labelWidth = (text) => String(text || "").length * 6 + 6;
  const overlap = (a, b) => Math.max(0, Math.min(a[0] + a[2], b[0] + b[2]) - Math.max(a[0], b[0])) * Math.max(0, Math.min(a[1] + a[3], b[1] + b[3]) - Math.max(a[1], b[1]));
  const along = (points, fraction) => {
    // the point at a fraction of the polyline's length
    const seg = []; let total = 0;
    for (let i = 1; i < points.length; i++) { const d = Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]); seg.push(d); total += d; }
    let want = fraction * total;
    for (let i = 1; i < points.length; i++) {
      if (want <= seg[i - 1] || i === points.length - 1) { const t = seg[i - 1] ? want / seg[i - 1] : 0; return [points[i - 1][0] + (points[i][0] - points[i - 1][0]) * t, points[i - 1][1] + (points[i][1] - points[i - 1][1]) * t]; }
      want -= seg[i - 1];
    }
    return points[points.length - 1];
  };
  const placeLabels = (spec, pos, paths) => {
    // each label tries several points along its own flow and takes the one that covers the least: boxes first,
    // then tier titles and labels already placed; a spec's dx/dy still nudges the result
    const boxes = spec.components.map(c => [pos[c.id].x - 4, pos[c.id].y - 4, W + 8, H + 8]);
    const titles = spec.tiers.map((t, i) => [12, TOP + i * TIERH + 4, t.title.length * 7.4 + 14 + (t.note || "").length * 5.6 + 12, 18]);
    const placed = [], out = {};
    const fractions = [0.5, 0.44, 0.56, 0.38, 0.62, 0.32, 0.68, 0.26, 0.74, 0.2, 0.8, 0.14, 0.86];
    const order = [...spec.flows].sort((f, g) => (pos[f.from].tier === pos[f.to].tier ? 0 : 1) - (pos[g.from].tier === pos[g.to].tier ? 0 : 1));
    for (const f of order) {
      const w = labelWidth(f.label), same = pos[f.from].tier === pos[f.to].tier;
      let best = null;
      for (const fr of fractions) {
        const [x, y0] = along(paths[f.id].points, fr);
        const y = same ? y0 - 10 : y0;  // a lane label sits just above its lane
        const box = [x - w / 2, y - 6, w, 12];
        const roomy = [box[0] - 10, box[1] - 3, box[2] + 20, box[3] + 6];  // labels keep a little distance from each other
        const cost = boxes.reduce((s, b) => s + overlap(box, b) * 3, 0) + titles.reduce((s, b) => s + overlap(box, b) * 2, 0) + placed.reduce((s, b) => s + overlap(roomy, b) * 2, 0) + Math.abs(fr - 0.5) * 40;
        if (!best || cost < best.cost) best = { cost, box, x, y };
        if (cost === Math.abs(fr - 0.5) * 40) break;  // nothing covered: take it
      }
      placed.push(best.box);
      out[f.id] = { x: best.x + (f.dx || 0), y: best.y + 3.5 + (f.dy || 0) };
    }
    return out;
  };

  const draw = (spec) => {
    const { pos, width, height } = place(spec);
    const paths = route(spec, pos), labelAt = placeLabels(spec, pos, paths);
    const tiers = spec.tiers.map((t, i) => `<g class="ra-tier"><rect x="8" y="${TOP + i * TIERH}" width="${width - 16}" height="${TIERH - 8}" rx="10"/><text x="20" y="${TOP + i * TIERH + 17}"><tspan class="ra-tier-title">${esc(t.title)}</tspan>${t.note ? `<tspan class="ra-tier-note" dx="14">${esc(t.note)}</tspan>` : ""}</text></g>`).join("");
    const flows = spec.flows.map(f => `<g class="ra-flow ra-flow-${f.kind || "data"}" data-flow="${esc(f.id)}"><path d="${paths[f.id].d}" class="ra-edge" marker-end="url(#ra-arrow)"/><path d="${paths[f.id].d}" class="ra-edge-glow"/></g>`).join("");
    const labels = spec.flows.map(f => `<text x="${labelAt[f.id].x.toFixed(1)}" y="${labelAt[f.id].y.toFixed(1)}" class="ra-label" data-flow-label="${esc(f.id)}">${esc(f.label)}</text>`).join("");
    const nodes = spec.components.map(c => {
      const p = pos[c.id], k = KINDS[c.kind] || KINDS.control, tech = wrapTech(c.tech);
      return `<g class="ra-node ra-kind-${c.kind}" data-node="${esc(c.id)}" transform="translate(${p.x},${p.y})" tabindex="0">
        <rect width="${W}" height="${H}" rx="10"/>
        <foreignObject x="10" y="8" width="30" height="44"><div xmlns="http://www.w3.org/1999/xhtml" class="ra-iconbox">${icon(c.icon || k[1])}</div></foreignObject>
        <text x="46" y="${tech.length > 1 ? 22 : 26}" class="ra-name">${esc(c.name)}</text>
        ${tech.map((t, i) => `<text x="46" y="${(tech.length > 1 ? 36 : 42) + i * 12}" class="ra-tech">${esc(t)}</text>`).join("")}</g>`;
    }).join("");
    return `<svg class="ra-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Reference architecture">
      <defs><marker id="ra-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z"/></marker></defs>
      ${tiers}${flows}${nodes}${labels}
      <circle class="ra-token" r="7" style="display:none"/></svg>`;
  };

  const legend = (spec) => {
    const kinds = [...new Set(spec.components.map(c => c.kind))].filter(k => KINDS[k]);
    const flowKinds = { request: "request", data: "data", control: "control", store: "write or read", event: "event or timer" };
    return `<div class="ra-legend"><div>${kinds.map(k => `<span class="ra-legend-item ra-kind-${k}">${icon(KINDS[k][1])}${esc(KINDS[k][0])}</span>`).join("")}</div>
      <div>${Object.entries(flowKinds).filter(([k]) => spec.flows.some(f => (f.kind || "data") === k)).map(([k, t]) => `<span class="ra-legend-item"><i class="ra-swatch ra-flow-${k}"></i>${t}</span>`).join("")}</div></div>`;
  };

  const render = (root, spec) => {
    root.innerHTML = `<div class="ra">
      <div class="ra-bar"><label for="ra-run">Simulate a run</label><select id="ra-run">${spec.runs.map(r => `<option value="${esc(r.id)}">${esc(r.title)}</option>`).join("")}</select>
        <div class="ra-controls"><button type="button" id="ra-play" class="primary small">Play</button><button type="button" id="ra-step" class="secondary small">Step</button><button type="button" id="ra-reset" class="secondary small">Reset</button><label class="ra-speed">speed <input id="ra-speed" type="range" min="1" max="4" value="2"></label><button type="button" id="ra-fit" class="secondary small" aria-pressed="false" title="Scale the diagram to the height of the window">Fit to window</button></div></div>
      <div class="ra-now" id="ra-now"></div>
      <div class="ra-diagram-wrap">${draw(spec)}</div>${legend(spec)}
      <div class="ra-side"><div class="ra-detail" id="ra-detail"><strong>Select a component</strong><span>to read what it is, what it runs on and what flows through it.</span></div>
      <div class="ra-player"><label>The run, step by step</label><p class="ra-blurb" id="ra-blurb"></p><ol class="ra-steps" id="ra-steps"></ol></div></div></div>`;
    const svg = root.querySelector(".ra-svg"), byId = Object.fromEntries(spec.components.map(c => [c.id, c]));
    const flowsById = Object.fromEntries(spec.flows.map(f => [f.id, f]));
    const detail = root.querySelector("#ra-detail");
    const showComponent = (id) => {
      const c = byId[id]; if (!c) return;
      const ins = spec.flows.filter(f => f.to === id).map(f => `${byId[f.from]?.name}: ${f.label}`);
      const outs = spec.flows.filter(f => f.from === id).map(f => `${f.label} → ${byId[f.to]?.name}`);
      detail.innerHTML = `<strong>${esc(c.name)}</strong><em>${esc(c.tech || "")}</em><span>${esc(c.note || "")}</span>
        ${ins.length ? `<b>Receives</b><ul>${ins.map(t => `<li>${esc(t)}</li>`).join("")}</ul>` : ""}${outs.length ? `<b>Sends</b><ul>${outs.map(t => `<li>${esc(t)}</li>`).join("")}</ul>` : ""}`;
      root.querySelectorAll(".ra-node").forEach(n => n.classList.toggle("selected", n.dataset.node === id));
    };
    root.querySelectorAll(".ra-node").forEach(n => { n.onclick = () => showComponent(n.dataset.node); n.onkeydown = (e) => { if (e.key === "Enter") showComponent(n.dataset.node); }; });
    root.querySelector("#ra-fit").onclick = (e) => { const on = root.querySelector(".ra-diagram-wrap").classList.toggle("fit"); e.currentTarget.setAttribute("aria-pressed", String(on)); };

    // the player: the current step is shown above the diagram, so a run can be followed without scrolling
    let run = spec.runs[0], index = -1, timer = null, animating = false;
    const stepsBox = root.querySelector("#ra-steps"), blurb = root.querySelector("#ra-blurb"), now = root.querySelector("#ra-now"), token = svg.querySelector(".ra-token");
    const playButton = root.querySelector("#ra-play");
    const stepLine = (s) => { const f = flowsById[s.flow]; return f ? `<b>${esc(byId[f.from]?.name || "")}</b> → <b>${esc(byId[f.to]?.name || "")}</b><span>${esc(f.label || "")}</span>` : `<b>No flow</b><span>the process, not a message</span>`; };
    const showNow = () => {
      if (index < 0) { now.innerHTML = `<b>${esc(run.title)}</b><em>${esc(run.blurb || "")}</em><code>Play runs every step; Step moves one flow at a time. The current step is shown here while the token travels the diagram.</code>`; return; }
      const s = run.steps[index];
      now.innerHTML = `<b>Step ${index + 1} of ${run.steps.length}${index === run.steps.length - 1 ? " · done" : ""}</b><div>${stepLine(s)}</div><em>${esc(s.note || "")}</em>${s.state ? `<code>${esc(s.state)}</code>` : ""}`;
    };
    const listSteps = () => { blurb.textContent = run.blurb || ""; stepsBox.innerHTML = run.steps.map((s, i) => `<li data-i="${i}">${stepLine(s)}<em>${esc(s.note || "")}</em>${s.state ? `<code>${esc(s.state)}</code>` : ""}</li>`).join(""); showNow(); };
    const clear = () => { root.querySelectorAll(".ra-node.active, .ra-node.done, .ra-flow.active, .ra-flow.done").forEach(n => n.classList.remove("active", "done")); root.querySelectorAll(".ra-steps li").forEach(l => l.classList.remove("active", "done")); token.style.display = "none"; };
    const reset = () => { clearTimeout(timer); timer = null; animating = false; index = -1; clear(); playButton.textContent = "Play"; showNow(); stepsBox.scrollTop = 0; };
    const speed = () => Number(root.querySelector("#ra-speed").value);
    const animateAlong = (path, done) => {
      const length = path.getTotalLength(); const duration = 1400 / speed(); const start = performance.now(); token.style.display = "";
      const frame = (now) => { const t = Math.min(1, (now - start) / duration); const p = path.getPointAtLength(t * length); token.setAttribute("cx", p.x); token.setAttribute("cy", p.y); if (t < 1 && animating) requestAnimationFrame(frame); else done(); };
      requestAnimationFrame(frame);
    };
    const playStep = (then) => {
      if (index >= run.steps.length - 1) { playButton.textContent = "Play"; timer = null; animating = false; return; }
      index += 1; const step = run.steps[index], flow = flowsById[step.flow];
      root.querySelectorAll(".ra-node.active, .ra-flow.active").forEach(n => { n.classList.remove("active"); n.classList.add("done"); });
      root.querySelectorAll(".ra-steps li").forEach((l, i) => { l.classList.toggle("active", i === index); l.classList.toggle("done", i < index); });
      showNow();
      // keep the current step in view inside the list only; the page itself never moves
      const li = stepsBox.querySelector(`li[data-i="${index}"]`); if (li) stepsBox.scrollTo({ top: Math.max(0, li.offsetTop - stepsBox.clientHeight / 2 + li.offsetHeight / 2), behavior: "smooth" });
      if (!flow) { then && then(); return; }
      const g = svg.querySelector(`.ra-flow[data-flow="${flow.id}"]`); g && g.classList.add("active");
      svg.querySelector(`.ra-node[data-node="${flow.from}"]`)?.classList.add("active");
      animating = true;
      animateAlong(g.querySelector(".ra-edge"), () => { animating = false; svg.querySelector(`.ra-node[data-node="${flow.to}"]`)?.classList.add("active"); showComponent(flow.to); then && then(); });
    };
    const play = () => {
      if (timer || animating) { clearTimeout(timer); timer = null; animating = false; playButton.textContent = "Play"; return; }
      if (index >= run.steps.length - 1) reset();
      playButton.textContent = "Pause";
      const loop = () => playStep(() => { if (index < run.steps.length - 1 && playButton.textContent === "Pause") timer = setTimeout(loop, 500 / speed()); else { playButton.textContent = "Play"; timer = null; } });
      loop();
    };
    playButton.onclick = play;
    root.querySelector("#ra-step").onclick = () => { if (animating) return; clearTimeout(timer); timer = null; playButton.textContent = "Play"; playStep(); };
    root.querySelector("#ra-reset").onclick = reset;
    root.querySelector("#ra-run").onchange = (e) => { run = spec.runs.find(r => r.id === e.target.value); reset(); listSteps(); };
    listSteps();
    return { showComponent, reset };
  };
  return { render, draw, ICONS };
})();
