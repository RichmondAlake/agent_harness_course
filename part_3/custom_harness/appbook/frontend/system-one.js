/* System One: a second model that decides, beside the model that reasons. */

/* ── 13. System One ─────────────────────────────────────────────────────── */
PPA.register({
  id: "system_one", n: 13, title: "System One",
  blurb: "Claude reasons, plans and writes. Before Claude is asked anything, the harness has decisions to make that have a closed set of answers. A System One model answers each with a probability, in about a third of a second. It writes no text and takes no action. The harness owns the threshold.",
  tags: ["Decide with one model, reason with another", "Attack screening · evidence · procedures and tools"],
  render: async (root) => {
    const pct = (value) => value === null || value === undefined ? "" : Number(value).toFixed(2);
    const mark = (flag) => flag ? PPA.pill("flagged", "bad") : `<span class="faint">clear</span>`;
    const results = { attack: null, select: null, rerank: null };
    const EXAMPLES = ["I need ninety quiet minutes on the Anadarko schedules. Hold everything else until I am done.",
      "Get me ready for Eva at nine.", "Which of these emails actually need me?",
      "Start a Pomodoro on the first task in my list.", "What is the capital of France?"];
    let request = EXAMPLES[0];

    const two = `<div class="grid two" style="margin-top:16px">
      <div class="panel"><div class="panel-head"><h2 class="panel-title">System One decides</h2>${PPA.pill("Jev", "strong")}</div><div class="panel-body"><dl class="kv"><dt>Job</dt><dd>Answer a closed question about some data</dd><dt>Returns</dt><dd>A probability, or one of the labels the harness wrote</dd><dt>Time</dt><dd>About a third of a second</dd><dt>Can act</dt><dd>No. It has no tools and writes no text</dd></dl></div></div>
      <div class="panel"><div class="panel-head"><h2 class="panel-title">System Two reasons</h2>${PPA.pill("Claude", "strong")}</div><div class="panel-body"><dl class="kv"><dt>Job</dt><dd>Reason, plan and write</dd><dt>Returns</dt><dd>Text and tool calls</dd><dt>Time</dt><dd>Seconds to a minute</dd><dt>Can act</dt><dd>Yes, through tools, and effects stop at the approval gate</dd></dl></div></div></div>`;

    const attackTable = (r) => `<div class="tiles" style="margin-top:0"><div class="tile"><span>Threads screened</span><strong>${r.threads}</strong><small>${r.seconds} s</small></div><div class="tile"><span>Tripwire flagged</span><strong>${r.flagged_by_tripwire}</strong><small>pattern matching</small></div><div class="tile"><span>System One flagged</span><strong>${r.note ? "off" : r.flagged_by_system_one}</strong><small>threshold ${r.threshold}</small></div><div class="tile"><span>Either</span><strong>${r.flagged_by_either}</strong><small>what triage uses</small></div></div>
      ${r.note ? `<div class="notice" style="margin-top:12px">${esc(r.note)}</div>` : ""}
      <div class="table-wrap" style="margin-top:12px"><table class="list"><thead><tr><th>Thread</th><th>Sender</th><th>Tripwire</th><th>System One</th><th class="num">Probability</th></tr></thead><tbody>${r.rows.map(row => `<tr><td class="mono">${esc(row.thread_id)}</td><td>${esc(row.from_email)}</td><td>${mark(row.tripwire)}</td><td>${r.note ? `<span class="faint">off</span>` : mark(row.system_one)}</td><td class="num mono">${pct(row.attack_probability)}</td></tr>`).join("")}</tbody></table></div>
      <p class="field-help" style="margin-top:10px">${esc(r.rule)}</p>`;

    const selectResult = (r) => {
      const one = r.by_system_one;
      const top = (odds, floor) => Object.entries(odds).filter(([, value]) => value >= floor).sort((a, b) => b[1] - a[1]);
      return `<div class="grid two" style="margin-top:0;gap:12px">
        <div><h3 class="panel-title">By rule</h3><dl class="kv"><dt>Procedure</dt><dd><strong>${esc(r.by_rule.skill || "none matched")}</strong></dd><dt>Tools offered</dt><dd>${r.by_rule.tools_offered}</dd><dt>Method</dt><dd>${esc(r.by_rule.method)}</dd></dl></div>
        <div><h3 class="panel-title">By System One</h3>${one ? `<dl class="kv"><dt>Procedure</dt><dd><strong>${esc(one.skills.join(", ") || "none applies")}</strong></dd><dt>Tools needed</dt><dd>${one.tools_offered} of ${r.by_rule.tools_offered}</dd><dt>Time</dt><dd>${one.seconds} s, one request</dd></dl>` : `<div class="notice">${esc(r.note)}</div>`}</div></div>
        ${one ? `<div class="grid two" style="margin-top:12px;gap:12px"><div class="table-wrap"><table class="list"><thead><tr><th>Procedure</th><th class="num">Share</th></tr></thead><tbody>${top(one.skill_probabilities, 0.02).map(([name, value]) => `<tr><td>${esc(name)}</td><td class="num mono">${pct(value)}</td></tr>`).join("")}</tbody></table></div>
        <div class="table-wrap"><table class="list"><thead><tr><th>Tool</th><th class="num">Needed</th></tr></thead><tbody>${top(one.tool_probabilities, 0.2).map(([name, value]) => `<tr><td class="mono">${esc(name)}</td><td class="num mono">${pct(value)}${value >= 0.4 ? " " + PPA.pill("kept", "good") : ""}</td></tr>`).join("")}</tbody></table></div></div>` : ""}`;
    };

    const rerankResult = (r) => `<dl class="kv"><dt>Meeting</dt><dd><strong>${esc(r.event.title)}</strong> <span class="mono faint">${esc(r.event.event_id)}</span></dd><dt>Chosen by</dt><dd>${esc(r.chosen_by)}</dd><dt>Kept</dt><dd>${r.kept.length ? r.kept.map(t => `${esc(t.subject || "")} <span class="mono faint">${esc(t.thread_id)}</span>`).join("<br>") : "Nothing. The search found no thread about this matter."}</dd></dl>${r.note ? `<div class="notice" style="margin-top:12px">${esc(r.note)}</div>` : ""}`;

    const draw = async () => {
      const s = await PPA.api("/api/system_one/status");
      const day = await PPA.api("/api/calendar_intel/status").catch(() => null);
      const events = day && day.day && day.day.events ? day.day.events : [];
      if (!root.isConnected) return;
      root.innerHTML = `<div class="notice ${s.available ? "good" : ""}" style="margin-top:24px"><strong>${esc(s.label)}.</strong> ${s.available ? `${s.decisions} decisions logged, ${s.messages_screened} messages screened.` : `Rules decide instead: ${esc(s.fallbacks.attack)} screens mail, and evidence keeps ${esc(s.fallbacks.rerank)}.`} ${esc(s.sends)}</div>
        ${two}
        <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">Four decisions</h2><span class="mono faint">the harness owns every threshold</span></div><div class="panel-body flush"><div class="table-wrap"><table class="list"><thead><tr><th>Decision</th><th>Question</th><th>Used by</th><th>In the assistant</th></tr></thead><tbody>${s.decisions_made_for.map(d => `<tr><td><strong>${esc(d.decision)}</strong></td><td>${esc(d.question)}</td><td>${esc(d.used_by)}</td><td>${d.in_the_loop ? PPA.pill("yes", "good") : PPA.pill("lab only")}</td></tr>`).join("")}</tbody></table></div></div></div>
        <div class="notice" style="margin-top:16px"><strong>Why every tool stays bound.</strong> ${esc(s.why_tools_stay_bound)}</div>

        <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">Lab 1 · Is this email an attack?</h2><button class="primary small" id="run-attack">Screen the inbox</button></div><div class="panel-body" id="attack-out">${results.attack ? attackTable(results.attack) : `<p class="field-help">Runs the pattern tripwire and System One over the same inbox threads. Three real attack emails are among them.</p>`}</div></div>

        <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">Lab 2 · Which procedure, and which tools?</h2></div><div class="panel-body"><label for="select-request">A request</label><div class="row"><input id="select-request" value="${esc(request)}" /><button class="primary" id="run-select">Decide</button></div><div class="row" style="margin-top:8px;flex-wrap:wrap;gap:6px">${EXAMPLES.map((text, index) => `<button class="secondary small" data-example="${index}">${esc(text)}</button>`).join("")}</div><div id="select-out" style="margin-top:14px">${results.select ? selectResult(results.select) : `<p class="field-help">The first request uses none of the words a skill is matched on, so keyword matching finds no procedure. Compare that with what System One chooses, and with how many of the tools it says the request needs.</p>`}</div></div></div>

        <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">Lab 3 · Which evidence is worth reading?</h2></div><div class="panel-body"><label for="rerank-event">A meeting</label><div class="row"><select id="rerank-event">${events.map(e => `<option value="${esc(e.event_id)}">${esc((e.start || "").slice(11, 16))} ${esc(e.title)}</option>`).join("")}</select><button class="primary" id="run-rerank">Choose the evidence</button></div><div id="rerank-out" style="margin-top:14px">${results.rerank ? rerankResult(results.rerank) : `<p class="field-help">A search returns up to ten threads. System One keeps at most three, and keeps none when the search found noise.</p>`}</div></div></div>

        <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">What the decisions cost</h2><span class="mono faint">ppa_decision_log · ${s.price_per_million_input_tokens_usd} USD per million input tokens</span></div><div class="panel-body flush"><div class="table-wrap"><table class="list"><thead><tr><th>Kind</th><th class="num">Calls</th><th class="num">Questions</th><th class="num">Mean seconds</th><th class="num">Input tokens</th><th class="num">USD</th></tr></thead><tbody>${s.costs.length ? s.costs.map(c => `<tr><td>${esc(c.kind)}</td><td class="num">${c.calls}</td><td class="num">${c.questions}</td><td class="num mono">${c.mean_seconds}</td><td class="num mono">${c.input_tokens}</td><td class="num mono">${c.usd}</td></tr>`).join("") : `<tr><td colspan="6" class="faint">No decision has been logged yet.</td></tr>`}</tbody></table></div></div></div>`;

      const run = (selector, work) => { const node = $(selector, root); if (node) node.onclick = async (event) => { try { await PPA.busy(event.currentTarget, work); await draw(); } catch (error) { PPA.toast("That did not work", error.message, "bad"); } }; };
      run("#run-attack", async () => { results.attack = await PPA.post("/api/system_one/attack_lab"); });
      run("#run-select", async () => { request = $("#select-request", root).value; results.select = await PPA.post("/api/system_one/select_lab", { query: request }); });
      $$("[data-example]", root).forEach(node => { node.onclick = () => { $("#select-request", root).value = EXAMPLES[Number(node.dataset.example)]; $("#run-select", root).click(); }; });
      run("#run-rerank", async () => { const chosen = $("#rerank-event", root).value; if (chosen) results.rerank = await PPA.post("/api/system_one/rerank_lab", { query: chosen }); });
    };
    await draw();
  },
});
