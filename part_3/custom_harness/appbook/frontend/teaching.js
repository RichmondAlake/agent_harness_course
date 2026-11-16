/* The teaching frame every chapter opens with. The text and the diagrams are data from /api/teaching. */
PPA.teach = { data: null };

PPA.teach.load = async () => {
  try { PPA.teach.data = await PPA.api("/api/teaching"); } catch (error) { PPA.teach.data = null; }
};

/* A small top-down diagram: nodes on a grid, labelled arrows between rows. */
PPA.teach.KINDS = { person: "A person", harness: "The harness", model: "A model", store: "Stored", gate: "A gate", outside: "Outside the harness" };
PPA.teach.diagram = (d) => {
  const NW = 196, NH = 50, CW = 226, RH = 104, PAD = 6;
  const cols = Math.max(...d.nodes.map(n => n.col)) + 1, rows = Math.max(...d.nodes.map(n => n.row)) + 1;
  const width = PAD * 2 + cols * CW, height = PAD * 2 + (rows - 1) * RH + NH;
  const box = new Map(d.nodes.map(n => [n.id, { ...n, x: PAD + n.col * CW + (CW - NW) / 2, y: PAD + n.row * RH }]));
  const incoming = {}, pairs = new Set(d.edges.map(e => `${e.from}>${e.to}`));
  d.edges.forEach(e => { incoming[e.to] = (incoming[e.to] || 0) + 1; });
  const text = (x, y, label, anchor) => `<text class="tg-label" x="${x}" y="${y}" text-anchor="${anchor}">${esc(label)}</text>`;
  const edges = d.edges.map(e => {
    const a = box.get(e.from), b = box.get(e.to), down = b.row > a.row, both = pairs.has(`${e.to}>${e.from}`);
    const acx = a.x + NW / 2, bcx = b.x + NW / 2;
    let path, label;
    if (a.col === b.col) {
      /* Straight. When arrows run both ways between two nodes, each keeps to its own side. */
      const x = both ? a.x + NW * (down ? .3 : .7) : acx;
      const y1 = down ? a.y + NH : a.y, y2 = down ? b.y - 2 : b.y + NH + 2;
      path = `M${x},${y1} L${x},${y2}`;
      label = both && down ? text(x - 8, (y1 + y2) / 2 + 4, e.label, "end") : text(x + 8, (y1 + y2) / 2 + 4, e.label, "start");
    } else if (down) {
      const y1 = a.y + NH, y2 = b.y - 2;
      path = `M${acx},${y1} C${acx},${y1 + 34} ${bcx},${y2 - 34} ${bcx},${y2}`;
      /* A node with one arrow in is labelled at its own end; a node with several is labelled at the far end. */
      label = (incoming[e.to] || 0) <= 1 ? text(bcx, y2 - 8, e.label, "middle") : text(acx, y1 + 15, e.label, "middle");
    } else {
      const right = a.col > b.col, x2 = right ? b.x + NW + 2 : b.x - 2, y2 = b.y + NH / 2;
      path = `M${acx},${a.y} C${acx},${a.y - 40} ${x2 + (right ? 46 : -46)},${y2} ${x2},${y2}`;
      label = text(x2 + (right ? 12 : -12), y2 - 8, e.label, right ? "start" : "end");
    }
    return `<path class="tg-edge" d="${path}" marker-end="url(#tg-arrow)"/>${label}`;
  }).join("");
  const nodes = d.nodes.map(n => { const p = box.get(n.id); return `<g class="tg-node"><rect x="${p.x}" y="${p.y}" width="${NW}" height="${NH}" rx="9"/><rect class="tg-swatch tg-${esc(n.kind)}" x="${p.x + 10}" y="${p.y + (n.note ? 12 : 20)}" width="9" height="9" rx="2.5"/><text class="tg-name" x="${p.x + 26}" y="${p.y + (n.note ? 21 : 29)}">${esc(n.label)}</text>${n.note ? `<text class="tg-note" x="${p.x + 26}" y="${p.y + 37}">${esc(n.note)}</text>` : ""}</g>`; }).join("");
  const kinds = [...new Set(d.nodes.map(n => n.kind))];
  const spoken = `${d.caption} ${d.edges.map(e => `${box.get(e.from).label} to ${box.get(e.to).label}: ${e.label}`).join("; ")}.`;
  return `<figure class="teach-figure"><div class="tg-scroll"><svg class="tg" viewBox="0 0 ${width} ${height}" style="min-width:${cols * 176}px;max-width:${width}px" role="img" aria-label="${esc(spoken)}"><defs><marker id="tg-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path class="tg-head" d="M0,1 L10,5 L0,9 z"/></marker></defs>${edges}${nodes}</svg></div><figcaption><strong>${esc(d.caption)}</strong><span class="tg-legend">${kinds.map(k => `<span><i class="tg-swatch tg-${esc(k)}"></i>${esc(PPA.teach.KINDS[k] || k)}</span>`).join("")}</span></figcaption></figure>`;
};

PPA.teach.parts = (frame) => frame.notebook.map(p => `Part ${p.part}`).join(" · ");

/* What PPA is and what a harness is: shown once, at the top of the Assistant page. */
PPA.teach.primer = () => {
  const p = PPA.teach.data?.primer;
  if (!p) return "";
  return `<section class="primer" aria-label="Start here"><div class="primer-card"><span class="eyebrow">START HERE</span><h2>${esc(p.ppa.title)}</h2><p>${esc(p.ppa.text)}</p><ul class="primer-does">${p.ppa.does.map(item => `<li>${esc(item)}</li>`).join("")}</ul></div>
    <div class="primer-card"><span class="eyebrow">THE IDEA</span><h2>${esc(p.harness.title)}</h2><p>${esc(p.harness.text)}</p><dl class="primer-decides">${p.harness.decides.map(item => `<div><dt>${esc(item.question)}</dt><dd>${esc(item.answer)}</dd></div>`).join("")}</dl></div>
    <p class="primer-how">${esc(p.how_to_read)}</p></section>`;
};

PPA.teach.frame = (chapter) => {
  const frame = PPA.teach.data?.chapters?.[chapter.id];
  if (!frame) return "";
  let open = true;
  try { open = localStorage.getItem("ppa-teach-open") !== "0"; } catch (error) { /* private mode */ }
  return `${chapter.id === "assistant" ? PPA.teach.primer() : ""}<details class="teach" id="teach" ${open ? "open" : ""}>
    <summary><span class="teach-title">About this ${chapter.n ? "chapter" : "page"}</span><span class="teach-parts" title="${esc(frame.notebook.map(p => `Part ${p.part}: ${p.title}`).join("; "))}">Notebook ${esc(PPA.teach.parts(frame))}</span></summary>
    <div class="teach-grid">
      <div class="teach-copy"><h3>What this is</h3><p>${esc(frame.what)}</p><h3>Why the harness needs it</h3><p>${esc(frame.why)}</p>
        <h3>Key terms</h3><dl class="teach-terms">${frame.terms.map(t => `<div><dt>${esc(t.term)}</dt><dd>${esc(t.definition)}</dd></div>`).join("")}</dl></div>
      ${frame.diagram ? PPA.teach.diagram(frame.diagram) : ""}
    </div>
    <div class="teach-grid">
      <div class="teach-copy"><h3>Try this</h3><ol class="teach-steps">${frame.try.map(s => `<li><strong>${esc(s.do)}</strong><span><b>Watch for</b> ${esc(s.watch)}</span></li>`).join("")}</ol></div>
      <div class="teach-copy"><h3>Takeaways</h3><ul class="teach-takeaways">${frame.takeaways.map(t => `<li>${esc(t)}</li>`).join("")}</ul>
        <h3>In the notebook</h3><p class="teach-notebook">${frame.notebook.map(p => `<span><b>Part ${p.part}</b> ${esc(p.title)}</span>`).join("")}</p></div>
    </div></details>`;
};
PPA.teach.bind = () => {
  const node = $("#teach");
  if (node) node.addEventListener("toggle", () => { try { localStorage.setItem("ppa-teach-open", node.open ? "1" : "0"); } catch (error) { /* private mode */ } });
};
