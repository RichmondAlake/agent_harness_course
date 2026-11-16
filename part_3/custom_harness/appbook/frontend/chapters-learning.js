/* Chapters 15 to 17: the context and cost ledger, learning from trajectories, and the scorecard. */

PPA.usd = (value) => `$${Number(value || 0).toFixed(Number(value || 0) >= 1 ? 2 : 4)}`;
PPA.outcomeTone = (outcome) => ({ answered: "", approved: "good", declined: "bad", mixed: "warn" }[outcome] ?? "warn");
PPA.short = (text, limit = 70) => { const value = String(text ?? ""); return value.length > limit ? value.slice(0, limit - 1) + "…" : value; };

/* ── 14. Context and cost ───────────────────────────────────────────────── */
PPA.register({
  id: "context_cost", n: 14, title: "Context and cost",
  blurb: "A ledger of every turn: what the harness put in the prompt, layer by layer, and what each model call cost. Input tokens are split into fresh, written to the prompt cache and read from it.",
  tags: ["Context layers", "Prompt caching", "Cost per model call"],
  render: async (root) => {
    const s = await PPA.api("/api/context_cost/status");
    const layers = s.layers, turns = s.turns, shown = turns.slice(-14), t = s.totals;
    const view = { table: false, selected: turns.length ? turns[turns.length - 1].turn_id : null };
    const number = (turn) => turns.indexOf(turn) + 1;

    /* One horizontal bar for each turn, one segment for each layer. Layer colour is fixed by the layer, never by its rank. */
    const chart = () => {
      if (!shown.length) return PPA.empty("No turn yet. Run a request on the Assistant page.");
      const W = 720, LEFT = 44, RIGHT = 96, ROW = 30, BAR = 16, TOP = 8;
      const max = Math.max(1, ...shown.map(turn => turn.context_tokens)), scale = (W - LEFT - RIGHT) / max;
      const rows = shown.map((turn, index) => {
        let x = LEFT;
        const y = TOP + index * ROW;
        const parts = layers.map((layer, slot) => {
          const value = Number(turn.context_layers[layer.name] || 0), width = Math.max(0, value * scale - 2);
          const rect = value ? `<rect class="cc-seg s${slot + 1}" x="${x.toFixed(1)}" y="${y}" width="${width.toFixed(1)}" height="${BAR}" rx="2" data-tip="Turn ${number(turn)} · ${esc(layer.name)}: about ${PPA.number(value)} tokens"><title>Turn ${number(turn)} · ${esc(layer.name)}: about ${PPA.number(value)} tokens</title></rect>` : "";
          x += value * scale;
          return rect;
        }).join("");
        return `<g class="cc-row ${turn.turn_id === view.selected ? "selected" : ""}" data-turn="${esc(turn.turn_id)}"><rect class="cc-hit" x="0" y="${y - 6}" width="${W}" height="${ROW - 2}"/><text class="cc-axis" x="${LEFT - 8}" y="${y + 12}" text-anchor="end">${number(turn)}</text>${parts}<text class="cc-total" x="${(x + 8).toFixed(1)}" y="${y + 12}">${PPA.number(turn.context_tokens)}</text></g>`;
      }).join("");
      const height = TOP + shown.length * ROW;
      return `<div class="cc-scroll"><svg class="cc-chart" viewBox="0 0 ${W} ${height}" role="img" aria-label="Approximate prompt size of the last ${shown.length} turns, split into ${layers.length} layers. The table view lists every number.">${rows}</svg></div><p class="field-help cc-tip" id="cc-tip">Point at a segment to read it. Select a bar to see that turn's model calls. Numbers at the right are the approximate total.</p>`;
    };
    const legend = `<div class="cc-legend">${layers.map((layer, slot) => `<span title="${esc(layer.about)}"><i class="cc-swatch s${slot + 1}"></i>${esc(layer.name)}${layer.stable ? ' <em>fixed</em>' : ""}</span>`).join("")}</div>`;
    const table = () => `<div class="table-wrap"><table class="list"><thead><tr><th>Turn</th><th>Request</th>${layers.map(layer => `<th class="num">${esc(layer.name)}</th>`).join("")}<th class="num">Total</th></tr></thead><tbody>${turns.map(turn => `<tr><td class="mono">${number(turn)}</td><td>${esc(PPA.short(turn.request, 46))}</td>${layers.map(layer => `<td class="num">${PPA.number(turn.context_layers[layer.name] || 0)}</td>`).join("")}<td class="num"><strong>${PPA.number(turn.context_tokens)}</strong></td></tr>`).join("") || `<tr><td colspan="${layers.length + 3}">${PPA.empty("No turn yet.")}</td></tr>`}</tbody></table></div>`;

    /* Cumulative cost, one point for each turn. One series, so the panel title names it and there is no legend. */
    const line = () => {
      if (!turns.length) return PPA.empty("No turn yet.");
      const W = 720, H = 170, LEFT = 56, RIGHT = 16, TOP = 14, BOTTOM = 26;
      const max = Math.max(...turns.map(turn => turn.cumulative_usd)), top = max > 0 ? max : 1;
      const x = (index) => LEFT + (turns.length === 1 ? (W - LEFT - RIGHT) / 2 : index * (W - LEFT - RIGHT) / (turns.length - 1));
      const y = (value) => TOP + (H - TOP - BOTTOM) * (1 - value / top);
      const points = turns.map((turn, index) => `${x(index).toFixed(1)},${y(turn.cumulative_usd).toFixed(1)}`).join(" ");
      const ticks = [0, .5, 1].map(share => `<line class="cc-grid" x1="${LEFT}" x2="${W - RIGHT}" y1="${y(top * share)}" y2="${y(top * share)}"/><text class="cc-axis" x="${LEFT - 8}" y="${y(top * share) + 4}" text-anchor="end">${max > 0 ? PPA.usd(top * share) : (share ? "" : "$0")}</text>`).join("");
      const dots = turns.map((turn, index) => `<g><circle class="cc-dot" cx="${x(index).toFixed(1)}" cy="${y(turn.cumulative_usd).toFixed(1)}" r="4"/><circle class="cc-hit" cx="${x(index).toFixed(1)}" cy="${y(turn.cumulative_usd).toFixed(1)}" r="12" data-tip="After turn ${index + 1}: ${PPA.usd(turn.cumulative_usd)} in total. This turn cost ${PPA.usd(turn.usd)}."><title>After turn ${index + 1}: ${PPA.usd(turn.cumulative_usd)}</title></circle></g>`).join("");
      return `<div class="cc-scroll"><svg class="cc-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Cumulative cost in US dollars after each of ${turns.length} turns. It ends at ${PPA.usd(t.usd)}.">${ticks}<polyline class="cc-line" points="${points}"/>${dots}<text class="cc-axis" x="${LEFT}" y="${H - 6}">turn 1</text><text class="cc-axis" x="${W - RIGHT}" y="${H - 6}" text-anchor="end">turn ${turns.length}</text></svg></div><p class="field-help cc-tip" id="cc-line-tip">${max > 0 ? "Point at a mark to read the running total." : "The line is flat at zero: the scripted responder calls no model, so nothing has been spent."}</p>`;
    };

    const calls = async () => {
      const box = $("#cc-calls");
      if (!view.selected) { box.innerHTML = PPA.empty("Select a turn."); return; }
      const d = await PPA.api(`/api/context_cost/turn/${encodeURIComponent(view.selected)}`);
      if (!box.isConnected) return;
      const turn = turns.find(item => item.turn_id === view.selected);
      box.innerHTML = `<p class="action-copy" style="margin:0 0 10px"><strong>Turn ${turn ? number(turn) : ""}:</strong> ${esc(d.turn.request)} <span class="mono faint">${esc(d.turn.turn_id)}</span></p>
        <div class="table-wrap"><table class="list"><thead><tr><th>Step</th><th class="num">Fresh</th><th class="num">Written to cache</th><th class="num">Read from cache</th><th class="num">Output</th><th class="num">Seconds</th><th class="num">Cost</th><th>Note</th></tr></thead><tbody>${d.calls.map(call => `<tr><td class="mono">${call.step}</td><td class="num">${PPA.number(call.fresh_tokens)}</td><td class="num">${PPA.number(call.cache_write_tokens)}</td><td class="num">${PPA.number(call.cache_read_tokens)}</td><td class="num">${PPA.number(call.output_tokens)}</td><td class="num">${Number(call.seconds).toFixed(2)}</td><td class="num">${PPA.usd(call.usd)}</td><td>${call.note ? PPA.pill(call.note) : ""}</td></tr>`).join("") || `<tr><td colspan="8">${PPA.empty("This turn has no model call in the ledger.")}</td></tr>`}
        ${d.calls.length ? `<tr><td><strong>Total</strong></td><td class="num"><strong>${PPA.number(d.totals.fresh_tokens)}</strong></td><td class="num"><strong>${PPA.number(d.totals.cache_write_tokens)}</strong></td><td class="num"><strong>${PPA.number(d.totals.cache_read_tokens)}</strong></td><td class="num"><strong>${PPA.number(d.totals.output_tokens)}</strong></td><td class="num"><strong>${Number(d.totals.seconds).toFixed(2)}</strong></td><td class="num"><strong>${PPA.usd(d.totals.usd)}</strong></td><td></td></tr>` : ""}</tbody></table></div>
        <p class="field-help">Fresh = input tokens − read from cache − written to cache. Caching saved ${PPA.usd(d.totals.saved_by_cache_usd)} on this turn: the ${PPA.number(d.totals.cache_read_tokens)} tokens read from the cache at the fresh price, less what they did cost.</p>`;
    };
    const drawLayers = () => {
      $("#cc-layers").innerHTML = view.table ? table() : legend + chart();
      $("#cc-toggle").textContent = view.table ? "Show as a chart" : "Show as a table";
    };
    const scripted = t.all_scripted || !s.model_called;
    root.innerHTML = `${scripted ? `<div class="notice" style="margin-top:24px"><strong>No model is being called.</strong> Answers come from the scripted responder. Each of its steps is written to the ledger as a row with zero tokens and zero cost, marked "${esc(s.scripted_note)}". The layer sizes below are still real: they are what the harness assembled for each turn. Set ANTHROPIC_API_KEY and start the appbook again to see token counts and cost.</div>` : ""}
      <div class="tiles" style="margin-top:${scripted ? 16 : 24}px">
        <div class="tile"><span>Turns in the ledger</span><strong>${PPA.number(t.turns)}</strong><small>${PPA.number(t.model_calls)} rows · ${PPA.number(t.scripted_steps)} scripted</small></div>
        <div class="tile"><span>Total cost</span><strong>${PPA.usd(t.usd)}</strong><small>median ${t.median_turn_usd === null ? "n/a" : PPA.usd(t.median_turn_usd)} a turn</small></div>
        <div class="tile"><span>Input read from cache</span><strong>${t.cache_read_share === null ? "n/a" : (t.cache_read_share * 100).toFixed(1) + "%"}</strong><small>${PPA.number(t.cache_read_tokens)} of ${PPA.number(t.input_tokens)} input tokens</small></div>
        <div class="tile"><span>What caching saved</span><strong>${PPA.usd(t.saved_by_cache_usd)}</strong><small>cache reads at the fresh price, less what they cost</small></div>
      </div>
      <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">What each turn put in the prompt</h2><div class="row"><span class="mono faint">approximate: characters ÷ 4</span><button class="secondary small" id="cc-toggle">Show as a table</button></div></div><div class="panel-body" id="cc-layers"></div></div>
      <div class="grid wide-left" style="margin-top:16px">
        <div class="panel"><div class="panel-head"><h2 class="panel-title">Turns</h2><span class="mono faint">ppa_turns · ppa_model_calls</span></div><div class="panel-body flush"><div class="table-wrap"><table class="list"><thead><tr><th>Turn</th><th>Request</th><th class="num">Prompt, approx.</th><th class="num">Model calls</th><th class="num">Cost</th><th class="num">Running</th></tr></thead><tbody id="cc-turns">${[...turns].reverse().map(turn => `<tr class="clickable" data-turn="${esc(turn.turn_id)}"><td class="mono">${number(turn)}</td><td><strong>${esc(PPA.short(turn.request, 60))}</strong><br>${PPA.pill(turn.kind)}${turn.scripted ? " " + PPA.pill("scripted") : ""}${turn.outcome ? " " + PPA.pill(turn.outcome, PPA.outcomeTone(turn.outcome)) : ""}</td><td class="num">${PPA.number(turn.context_tokens)}</td><td class="num">${PPA.number(turn.model_calls)}</td><td class="num">${PPA.usd(turn.usd)}</td><td class="num">${PPA.usd(turn.cumulative_usd)}</td></tr>`).join("") || `<tr><td colspan="6">${PPA.empty("No turn yet. Run a request on the Assistant page.")}</td></tr>`}</tbody></table></div></div></div>
        <div class="stack"><div class="panel"><div class="panel-head"><h2 class="panel-title">Model calls of the selected turn</h2></div><div class="panel-body" id="cc-calls"></div></div>
          <div class="panel"><div class="panel-head"><h2 class="panel-title">Prices</h2><span class="mono faint">US dollars per million tokens</span></div><div class="panel-body flush"><table class="list"><tbody><tr><td>Fresh input</td><td class="num">${s.prices.fresh.toFixed(2)}</td></tr><tr><td>Written to the cache</td><td class="num">${s.prices.cache_write.toFixed(2)}</td></tr><tr><td>Read from the cache</td><td class="num">${s.prices.cache_read.toFixed(2)}</td></tr><tr><td>Output</td><td class="num">${s.prices.output.toFixed(2)}</td></tr></tbody></table></div></div></div>
      </div>
      <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">Cumulative cost, US dollars</h2><span class="mono faint">one mark for each turn</span></div><div class="panel-body">${line()}</div></div>
      <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">How caching is switched on</h2></div><div class="panel-body"><ul class="teach-takeaways">${s.caching.breakpoints.map(item => `<li>A cache breakpoint on ${esc(item)}.</li>`).join("")}</ul><p class="field-help">${esc(s.caching.rule)}</p></div></div>`;
    drawLayers();
    await calls();
    const select = (turnId) => { view.selected = turnId; if (!view.table) drawLayers(); calls().catch(error => { $("#cc-calls").innerHTML = PPA.fail(error); }); };
    $("#cc-toggle").onclick = () => { view.table = !view.table; drawLayers(); };
    $("#cc-layers").onclick = (event) => { const row = event.target.closest("[data-turn]"); if (row) select(row.dataset.turn); };
    $("#cc-turns").onclick = (event) => { const row = event.target.closest("[data-turn]"); if (row) select(row.dataset.turn); };
    root.addEventListener("mouseover", (event) => {
      const tip = event.target.closest?.("[data-tip]");
      if (!tip) return;
      const target = tip.closest("#cc-layers") ? $("#cc-tip") : $("#cc-line-tip");
      if (target) target.textContent = tip.dataset.tip;
    });
  },
});

/* ── 15. Learning from its own traces ───────────────────────────────────── */
PPA.register({
  id: "learning", n: 15, title: "Learning from its own traces",
  blurb: "Every turn leaves a trajectory. A workflow the assistant repeats with no skill can be drafted as one. A fixed gate of five checks decides whether it goes live, and a correction from the owner can refine it. Any stored version can be made live again.",
  tags: ["Trajectories", "Workflow to skill", "Promotion gate", "Roll back"],
  render: async (root) => {
    const view = { gate: null, diff: null, route: null, text: null };
    const chain = (names) => names.map(name => `<code>${esc(name)}</code>`).join(' <span class="faint">→</span> ') || '<span class="faint">none</span>';
    const statusTone = (status) => ({ ACTIVE: "good", CANDIDATE: "warn", RETIRED: "" }[status] ?? "");
    const gateTone = (state) => ({ PASSED: "good", FAILED: "bad", CANDIDATE: "" }[state] ?? "");
    const checklist = (spec, checks, running) => `<ol class="gate-list">${spec.map((item, index) => {
      const done = checks.find(check => check.id === item.id);
      const state = done ? (done.passed ? "pass" : "fail") : running && index === checks.length ? "running" : "waiting";
      return `<li class="${state}"><span class="gate-mark">${{ pass: "pass", fail: "fail", running: "running", waiting: "not run" }[state]}</span><div><strong>${esc(item.name)}</strong><small>${esc(done ? done.detail : item.explains)}</small></div></li>`;
    }).join("")}</ol>`;

    const draw = async () => {
      const s = await PPA.api("/api/learning/status");
      if (!root.isConnected) return;
      const liveSkills = s.skills.filter(skill => skill.live_version);
      const learned = s.skills.filter(skill => skill.versions.some(v => v.origin !== "authored"));
      const authored = s.skills.filter(skill => !learned.includes(skill));
      if (view.text === null) view.text = s.corrections.length ? s.corrections[s.corrections.length - 1].owner_words : "";

      const version = (skill, v) => {
        const running = view.gate && view.gate.name === skill.name && view.gate.version === v.version;
        const checks = running ? view.gate.checks : (v.gate.checks || []);
        const cost = v.gate.cost_report;
        return `<article class="version" data-skill="${esc(skill.name)}" data-version="${v.version}">
          <header><strong>version ${v.version}</strong>${PPA.pill(v.status, statusTone(v.status))}${v.status === "ACTIVE" ? "" : PPA.pill("gate: " + (v.state === "CANDIDATE" ? "not run" : v.state.toLowerCase()), gateTone(v.state))}${PPA.pill(v.origin)}<span class="mono faint">sha256 ${esc(v.body_sha256.slice(0, 12))} · ${esc(v.drafted_by)}</span></header>
          <p class="action-copy">${esc(v.description)}</p>
          ${v.evidence.correction ? `<p class="field-help"><b>Correction it carries:</b> ${esc(v.evidence.correction)}</p>` : ""}
          ${(v.evidence.turn_ids || []).length ? `<p class="field-help"><b>Evidence:</b> ${v.evidence.turn_ids.map(id => `<button class="link-button" data-open-turn="${esc(id)}">${esc(id)}</button>`).join(", ")}${v.evidence.templated ? " · templated, no model wrote it" : ""}</p>` : ""}
          <details><summary class="link-button">Read the procedure</summary><div class="result-copy" style="margin-top:8px">${PPA.markdown(v.body)}</div>${(v.evidence.held_out || []).length ? `<p class="field-help"><b>Held-out phrasings:</b> ${v.evidence.held_out.map(esc).join(" · ")}</p>` : ""}</details>
          ${checks.length || running ? `<div class="gate-box" id="gate-${esc(skill.name)}-${v.version}">${checklist(s.gate, checks, running)}${!running && v.gate.failing?.length ? `<p class="field-help"><b>Failing:</b> ${v.gate.failing.map(esc).join("; ")}. The version stays a candidate.</p>` : ""}${!running && cost ? `<p class="field-help"><b>Reported, not gated:</b> the replay took ${cost.replay ? cost.replay.model_calls : 0} step${cost.replay?.model_calls === 1 ? "" : "s"}${cost.replay && cost.replay.scripted_steps === cost.replay.model_calls ? ", all scripted with no model call," : ""} for ${PPA.usd(cost.replay?.usd)}${cost.earlier_turns_without_the_skill ? `; the ${cost.earlier_turns_without_the_skill.turns} earlier turns with no skill averaged ${cost.earlier_turns_without_the_skill.mean_model_calls} steps for ${PPA.usd(cost.earlier_turns_without_the_skill.mean_usd)}` : ""}.</p>` : ""}</div>` : ""}
          <div class="actions">${v.status !== "ACTIVE" ? `<button class="secondary small" data-gate>Run the gate</button>` : ""}${v.status !== "ACTIVE" && v.state === "PASSED" ? `<button class="primary small" data-promote>Promote</button>` : ""}${v.status === "RETIRED" || (v.status === "CANDIDATE" && v.state === "PASSED" && skill.live_version) ? `<button class="secondary small" data-activate>Roll back to this version</button>` : ""}${v.version > 1 ? `<button class="secondary small" data-diff="${v.version - 1}">Compare with version ${v.version - 1}</button>` : ""}</div>
          ${view.diff && view.diff.name === skill.name && view.diff.b === v.version ? `<div class="diff" aria-label="Changes from version ${view.diff.a} to version ${view.diff.b}">${view.diff.lines.filter(line => line.kind !== "meta").map(line => `<div class="${line.kind}"><span>${{ added: "+", removed: "−", same: " " }[line.kind]}</span><code>${esc(line.text) || "&nbsp;"}</code></div>`).join("") || '<div class="same"><span> </span><code>The two procedures are identical.</code></div>'}</div>` : ""}
        </article>`;
      };
      const skillCard = (skill) => `<div class="panel skill-card"><div class="panel-head"><h2 class="panel-title">${esc(skill.name)}</h2><div class="row">${skill.live_version ? PPA.pill(`live: version ${skill.live_version}`, "good") : PPA.pill("not live")}${skill.live_version ? `<button class="secondary small" data-retire="${esc(skill.name)}">Retire</button>` : ""}</div></div><div class="panel-body">${skill.versions.map(v => version(skill, v)).join("")}</div></div>`;
      const routed = view.route;

      root.innerHTML = `<div class="panel" style="margin-top:24px"><div class="panel-body"><div class="row"><button class="primary" id="sample-week">Load a sample week</button><button class="secondary" id="reset-all">Reset</button>${PPA.pill(s.written_by)}${PPA.pill(s.routed_by)}</div><p class="field-help">The sample week runs five turns with the scripted responder on the practice workspace: a brief, a calendar question, two replies you approve and one you decline with a reason. It is scripted practice data, marked as such below. Reset empties the harness state, the sample week included.</p></div></div>

        <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">1 · Trajectories</h2><span class="mono faint">ppa_turns · ${s.counts.turns} turns · ${s.counts.live} live · ${s.counts.replay} replay</span></div><div class="panel-body flush"><div class="table-wrap"><table class="list"><thead><tr><th>Started</th><th>Request</th><th>Skills</th><th>Tools that ran, in order</th><th>Outcome</th><th>Owner's words</th></tr></thead><tbody id="turn-rows">${s.trajectories.map(turn => `<tr class="clickable" data-open-turn="${esc(turn.turn_id)}"><td class="mono">${esc(PPA.realTime(turn.started_at))}</td><td><strong>${esc(PPA.short(turn.request, 64))}</strong><br>${PPA.pill(turn.kind, turn.kind === "replay" ? "warn" : "")}${turn.sample ? " " + PPA.pill("practice data") : ""}</td><td>${turn.skills.map(name => PPA.pill(name)).join(" ") || '<span class="faint">none</span>'}</td><td>${chain(turn.tool_calls)}</td><td>${turn.outcome ? PPA.pill(turn.outcome, PPA.outcomeTone(turn.outcome)) : PPA.pill(turn.state, "warn")}</td><td>${esc(turn.owner_words)}</td></tr>`).join("") || `<tr><td colspan="6">${PPA.empty("No turn yet. Load a sample week, or use the Assistant page.")}</td></tr>`}</tbody></table></div></div></div>

        <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">2 · Candidates: workflows repeated with no skill</h2><span class="mono faint">at least ${s.minimum_repeats} live turns · approved or answered</span></div><div class="panel-body">${s.candidates.map((item, index) => `<article class="candidate"><header><div>${chain(item.signature)}</div>${PPA.pill(`${item.count} turns`)}${item.sample ? PPA.pill("practice data") : ""}</header><ul>${item.requests.map(request => `<li>${esc(request)}</li>`).join("")}</ul><div class="actions">${item.drafted ? `<span class="mono faint">Drafted as ${esc(item.drafted.name)}, version ${item.drafted.version}${item.drafted.live ? ", live" : ""}.</span>` : ""}<button class="${item.drafted ? "secondary" : "primary"} small" data-draft="${index}">${item.drafted ? "Draft again" : "Draft a skill"}</button></div></article>`).join("") || PPA.empty("No repeated workflow yet. Two live turns must run the same tools, with no skill, and end approved or answered.")}<p class="field-help">Tools that are bound on every turn are left out of a workflow: ${s.helper_tools.map(esc).join(", ")}. A replay never counts as evidence.</p></div></div>

        <h2 class="panel-title" style="margin:28px 0 10px">3 · The gate and 4 · version history</h2>
        <div class="panel"><div class="panel-head"><h2 class="panel-title">The gate, written before any candidate exists</h2><span class="mono faint">five checks · the same for every candidate</span></div><div class="panel-body">${checklist(s.gate, [], false)}</div></div>
        ${learned.map(skillCard).join("") || `<div class="panel" style="margin-top:16px"><div class="panel-body">${PPA.empty("No learned or refined version yet. Draft a skill from a candidate, or apply a correction to a skill.")}</div></div>`}
        <details class="advanced" ${learned.length ? "" : "open"}><summary>Authored skills (${authored.length}): one version each, live since start-up</summary>${authored.map(skillCard).join("")}</details>

        <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">Pointer history</h2><span class="mono faint">ppa_skill_log · nothing is deleted</span></div><div class="panel-body flush"><div class="table-wrap" style="max-height:260px"><table class="list"><thead><tr><th>When</th><th>Skill</th><th>Version</th><th>Action</th><th>Reason</th></tr></thead><tbody>${s.log.map(row => `<tr><td class="mono">${esc(PPA.realTime(row.created_at))}</td><td class="mono">${esc(row.skill_name)}</td><td class="mono">${row.version ?? ""}</td><td>${PPA.pill(row.action, { promote: "good", retire: "bad", trial: "warn", restore: "warn" }[row.action] ?? "")}</td><td>${esc(row.reason)}</td></tr>`).join("")}</tbody></table></div></div></div>

        <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">5 · Where does a correction belong?</h2><span class="mono faint">${esc(s.routed_by)}</span></div><div class="panel-body">
          ${s.corrections.length ? `<p class="field-help" style="margin:0 0 8px">Said when declining an action: ${s.corrections.map((item, index) => `<button class="link-button" data-use-correction="${index}">"${esc(PPA.short(item.owner_words, 60))}"</button>`).join(" · ")}</p>` : ""}
          <label for="correction-text">What the owner said</label><div class="row"><input id="correction-text" maxlength="600" value="${esc(view.text)}" placeholder="For example: always check my calendar before you offer a time" /><button class="primary" id="correction-route">Route it</button></div>
          <div class="destinations">${Object.entries(s.destinations).map(([key, item]) => `<article class="${routed?.destination === key ? "chosen" : ""}"><header><strong>${esc(item.title)}</strong>${routed?.destination === key ? '<span class="chosen-label">chosen</span>' : ""}</header><p>${esc(item.about)}</p><small>goes to ${esc(item.goes_to)}${routed?.probabilities ? ` · ${(routed.probabilities[key] * 100).toFixed(0)}%` : ""}</small></article>`).join("")}</div>
          ${routed ? `<p class="field-help"><b>Decided by ${esc(routed.by)}.</b> ${esc(routed.reason)}</p><div class="row">${routed.destination === "procedure" ? `<label class="inline" for="correction-skill">Skill to refine</label><select id="correction-skill">${liveSkills.map(skill => `<option ${skill.name === view.skill ? "selected" : ""}>${esc(skill.name)}</option>`).join("")}</select>` : ""}<button class="secondary" id="correction-apply">${{ procedure: "Write the next version of the skill", preference: "Save to long-term memory", one_off: "Do nothing" }[routed.destination]}</button></div>` : ""}
        </div></div>`;

      $("#sample-week").onclick = async (event) => { try { const r = await PPA.busy(event.currentTarget, () => PPA.post("/api/learning/sample_week")); PPA.toast("Sample week loaded", `${r.turns.length} scripted turns. ${r.candidates.length} repeated workflow${r.candidates.length === 1 ? "" : "s"} found.`); view.text = null; await draw(); } catch (error) { PPA.toast("The sample week did not load", error.message, "bad"); } };
      $("#reset-all").onclick = async (event) => { if (!confirm("Empty the harness state? Tasks, memory, the action log, trajectories and learned skills are removed.")) return; try { await PPA.busy(event.currentTarget, () => PPA.post("/api/reset", { confirm: "reset" })); Object.assign(view, { gate: null, diff: null, route: null, text: null }); await PPA.refreshStatus(); await draw(); } catch (error) { PPA.toast("Reset failed", error.message, "bad"); } };
      $("#correction-text").oninput = (event) => { view.text = event.target.value; };
      $("#correction-route").onclick = async (event) => { try { view.route = await PPA.busy(event.currentTarget, () => PPA.post("/api/learning/correction/route", { text: view.text })); const source = s.corrections.find(item => item.owner_words === view.text); view.skill = source?.suggested_skill || liveSkills[liveSkills.length - 1]?.name; view.turn = source?.turn_id || null; await draw(); $("#correction-text")?.scrollIntoView({ block: "center" }); } catch (error) { PPA.toast("The correction was not routed", error.message, "bad"); } };
      const apply = $("#correction-apply");
      if (apply) apply.onclick = async (event) => { try { const r = await PPA.busy(event.currentTarget, () => PPA.post("/api/learning/correction/apply", { text: routed.text, destination: routed.destination, skill: $("#correction-skill")?.value || null, turn_id: view.turn || null })); PPA.toast({ procedure: `Version ${r.version} of ${r.skill} written`, preference: "Saved to long-term memory", one_off: "Nothing was changed" }[r.destination], r.note); view.route = null; await draw(); } catch (error) { PPA.toast("The correction was not applied", error.message, "bad"); } };

      root.onclick = async (event) => {
        const target = event.target;
        const openTurn = target.closest("[data-open-turn]"), draft = target.closest("[data-draft]"), use = target.closest("[data-use-correction]"), retire = target.closest("[data-retire]");
        const card = target.closest(".version"), name = card?.dataset.skill, number = Number(card?.dataset.version);
        try {
          if (use) { view.text = s.corrections[Number(use.dataset.useCorrection)].owner_words; view.route = null; await draw(); }
          else if (openTurn) await PPA.openTurn(openTurn.dataset.openTurn);
          else if (draft) { const made = await PPA.busy(draft, () => PPA.post("/api/learning/draft", { turn_ids: s.candidates[Number(draft.dataset.draft)].turn_ids })); PPA.toast(`${made.skill_name} version ${made.version} drafted`, "It is a candidate. It is not offered to the model until it passes the gate and is promoted."); await draw(); }
          else if (retire) { if (!confirm(`Retire ${retire.dataset.retire}? Its versions stay in the history.`)) return; await PPA.post(`/api/learning/skills/${retire.dataset.retire}/retire`, {}); await draw(); }
          else if (card && target.closest("[data-gate]")) {
            view.gate = { name, version: number, checks: [] }; await draw();
            try { await PPA.post(`/api/learning/skills/${name}/${number}/gate`); } finally { view.gate = null; }
            await draw();
          }
          else if (card && target.closest("[data-promote]")) { await PPA.busy(target.closest("[data-promote]"), () => PPA.post(`/api/learning/skills/${name}/${number}/promote`)); PPA.toast(`${name} version ${number} is live`, "It is now offered to the model."); await draw(); }
          else if (card && target.closest("[data-activate]")) { await PPA.post(`/api/learning/skills/${name}/activate`, { version: number, reason: "rolled back by the owner" }); PPA.toast(`${name} is back on version ${number}`, "The pointer moved. No version was deleted."); await draw(); }
          else if (card && target.closest("[data-diff]")) { const a = Number(target.closest("[data-diff]").dataset.diff); view.diff = view.diff && view.diff.name === name && view.diff.b === number ? null : { name, ...(await PPA.api(`/api/learning/skills/${name}/diff?a=${a}&b=${number}`)) }; await draw(); }
        } catch (error) { PPA.toast("That did not work", error.message, "bad"); }
      };
    };
    /* The gate publishes each finished check. The open checklist fills in as they arrive. */
    PPA.on("gate", (data) => {
      if (!view.gate || data.skill !== view.gate.name || data.version !== view.gate.version || data.status !== "check") return;
      view.gate.checks.push(data.check);
      const box = $(`#gate-${CSS.escape(data.skill)}-${data.version} .gate-list`);
      if (!box) return;
      const items = $$("li", box), index = view.gate.checks.length - 1;
      if (items[index]) { items[index].className = data.check.passed ? "pass" : "fail"; $(".gate-mark", items[index]).textContent = data.check.passed ? "pass" : "fail"; $("small", items[index]).textContent = data.check.detail; }
      if (items[index + 1]) { items[index + 1].className = "running"; $(".gate-mark", items[index + 1]).textContent = "running"; }
    });
    await draw();
  },
});

/* One trajectory, opened from any table that lists turns. */
PPA.openTurn = async (turnId) => {
  const node = PPA.modal(`Trajectory ${turnId}`, '<div class="empty"><span class="loading">Reading the turn</span></div>');
  const body = $("div > div:last-child", node);
  try {
    const [turn, cost] = await Promise.all([PPA.api(`/api/learning/trajectories/${encodeURIComponent(turnId)}`), PPA.api(`/api/context_cost/turn/${encodeURIComponent(turnId)}`)]);
    const layers = Object.entries(turn.context_layers);
    body.innerHTML = `<div class="panel-body"><dl class="kv"><dt>Request</dt><dd><strong>${esc(turn.request)}</strong></dd><dt>Kind</dt><dd>${PPA.pill(turn.kind, turn.kind === "replay" ? "warn" : "")}${turn.sample ? " " + PPA.pill("practice data") : ""} <span class="mono faint">${esc(turn.thread_id)}</span></dd><dt>Planned by</dt><dd>${esc(turn.planned_by)}</dd><dt>Skills loaded</dt><dd>${turn.skills.map(name => PPA.pill(name)).join(" ") || "none"}</dd><dt>Tools that ran</dt><dd>${turn.tool_calls.map(name => `<code>${esc(name)}</code>`).join(" → ") || "none"}</dd><dt>Tools bound</dt><dd>${turn.tools_bound.length} tools, the same list on every turn</dd><dt>Outcome</dt><dd>${turn.outcome ? PPA.pill(turn.outcome, PPA.outcomeTone(turn.outcome)) : PPA.pill(turn.state, "warn")}</dd>${turn.owner_words ? `<dt>Owner's words</dt><dd>${esc(turn.owner_words)}</dd>` : ""}<dt>Started, ended</dt><dd class="mono">${esc(PPA.realTime(turn.started_at))} · ${esc(turn.ended_at ? PPA.realTime(turn.ended_at) : "still open")}</dd><dt>Model calls</dt><dd>${cost.totals.model_calls} row${cost.totals.model_calls === 1 ? "" : "s"} in the ledger, ${PPA.usd(cost.totals.usd)}${cost.totals.scripted_steps ? ` · ${cost.totals.scripted_steps} scripted, no model call` : ""}</dd></dl>
      ${turn.actions.length ? `<h3 class="panel-title" style="margin:16px 0 6px">Actions in this turn</h3><table class="list"><tbody>${turn.actions.map(action => `<tr><td><strong>${esc(action.summary)}</strong><br><span class="mono faint">${esc(action.tool_name)} · ${esc(action.tier)}</span></td><td>${PPA.pill(action.state, PPA.stateTone(action.state))}</td><td>${esc(action.decision_note || action.delivery || "")}</td></tr>`).join("")}</tbody></table>` : ""}
      <h3 class="panel-title" style="margin:16px 0 6px">Context layers, approximate tokens</h3><table class="list"><tbody>${layers.map(([name, value]) => `<tr><td>${esc(name)}</td><td class="num">${PPA.number(value)}</td></tr>`).join("") || `<tr><td>${PPA.empty("Not recorded.")}</td></tr>`}</tbody></table></div>`;
  } catch (error) { body.innerHTML = `<div class="panel-body">${PPA.fail(error)}</div>`; }
};

/* ── 16. Scorecard and release gate ─────────────────────────────────────── */
PPA.register({
  id: "scorecard", n: 16, title: "Scorecard and release gate",
  blurb: "A frozen list of checks, each with a threshold and the evidence it reads, computed from the live state of the harness. Safety checks block. Cost and time are reported.",
  tags: ["Frozen checks", "READY or BLOCKED", "Computed from evidence"],
  render: async (root) => {
    const draw = async () => {
      const s = await PPA.api("/api/scorecard/status");
      if (!root.isConnected) return;
      const ready = s.verdict === "READY";
      root.innerHTML = `<div class="verdict ${ready ? "ready" : "blocked"}" style="margin-top:24px"><div><span class="verdict-label">${esc(s.verdict)}</span><p>${ready ? `All ${s.blocking_checks} blocking checks pass. ${s.reported} more are reported and do not block.` : `${s.failing.length} blocking check${s.failing.length === 1 ? "" : "s"} failing: ${s.failing.map(esc).join("; ")}.`}</p></div><div class="row"><span class="mono faint">computed ${esc(PPA.realTime(s.computed_at))}</span><button class="secondary" id="score-again">Compute again</button></div></div>
        ${s.note ? `<div class="notice" style="margin-top:12px">${esc(s.note)}</div>` : ""}
        <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">The checks</h2><span class="mono faint">${esc(s.frozen)}</span></div><div class="panel-body flush"><div class="table-wrap" style="max-height:none"><table class="list"><thead><tr><th>Check</th><th>Threshold</th><th>Value</th><th>Result</th><th>What it found, and where it looked</th></tr></thead><tbody>${s.checks.map(check => `<tr><td style="min-width:220px"><strong>${esc(check.title)}</strong><br>${esc(check.explains)}</td><td class="mono">${esc(check.threshold)}</td><td class="mono"><strong>${check.value === null || check.value === undefined ? "n/a" : esc(check.value)}</strong></td><td>${PPA.pill(check.status, { pass: "good", fail: "bad", reported: "" }[check.status])}${check.blocking ? "" : "<br>" + PPA.pill("does not block")}</td><td>${esc(check.detail)}<br><span class="mono faint">evidence: ${esc(check.evidence)}</span></td></tr>`).join("")}</tbody></table></div></div></div>`;
      $("#score-again").onclick = async (event) => { try { await PPA.busy(event.currentTarget, draw); } catch (error) { PPA.toast("The scorecard was not computed", error.message, "bad"); } };
    };
    await draw();
  },
});
