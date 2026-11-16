/* The first building blocks: the teaching view of the same running system. */

/* ── 2. Systems of record and MCP ───────────────────────────────────────── */
PPA.register({
  id: "systems_of_record", n: 2, title: "Systems of record and MCP",
  blurb: "Three MCP servers offer more than an assistant should use. See every tool beside the harness allowlist, run a read live, and try to reach a tool that is never exposed.",
  tags: ["MCP over streamable HTTP", "Allowlist"],
  render: async (root) => {
    const s = await PPA.api("/api/systems_of_record/status");
    const today = PPA.status.clock.now.slice(0, 10);
    const samples = { mail_search_threads: { label: "INBOX", max_results: 3 }, mail_get_thread: { thread_id: "" }, mail_list_drafts: {}, mail_list_sent: {}, calendar_list_events: { start_date: today }, notes_search: { query: "" }, notes_get_page: { page_id: "" } };
    const tierTone = { automatic: "good", approval: "warn", conditional: "warn", never: "bad" };
    root.innerHTML = `<div class="grid three">${Object.entries(s.servers).map(([name, tools]) => `<div class="panel"><div class="panel-head"><h2 class="panel-title">${esc(name)} server</h2><span class="mono faint">${tools.length} tools</span></div><div class="panel-body flush"><p class="action-copy mono" style="padding:10px 12px 0;margin:0">${esc(s.gateway.servers[name])}</p><div class="tool-list">${tools.map(t => `<div class="tool ${t.exposed ? "" : "never"}"><div><strong>${esc(t.name)}</strong><p>${esc(t.description)}</p></div><div>${PPA.pill(t.tier === "never" ? "never exposed" : t.tier, tierTone[t.tier])}</div></div>`).join("")}</div></div></div>`).join("")}</div>
      <div class="grid two"><div class="panel"><div class="panel-head"><h2 class="panel-title">Effect tiers</h2><div class="row">${PPA.pill(`${s.counts.offered} offered`)}${PPA.pill(`${s.counts.allowlisted} allowlisted`, "good")}${PPA.pill(`${s.counts.never_exposed} never exposed`, "bad")}</div></div><div class="panel-body"><dl class="kv">${Object.entries(s.tier_rules).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl><p class="action-copy" style="margin-top:12px">${esc(s.teaching_point)}</p></div></div>
        <div class="panel"><div class="panel-head"><h2 class="panel-title">Where each kind of data lives</h2></div><div class="panel-body flush"><table class="list"><thead><tr><th>Data</th><th>Home</th><th>Held by the harness</th></tr></thead><tbody>${s.systems_of_record.map(r => `<tr><td><strong>${esc(r.data)}</strong></td><td class="mono">${esc(r.home)}</td><td>${esc(r.held_by_harness)}</td></tr>`).join("")}</tbody></table></div></div></div>
      <div class="grid two"><div class="panel"><div class="panel-head"><h2 class="panel-title">Run a read tool live</h2></div><div class="panel-body"><label for="read-tool">Tool</label><select id="read-tool">${Object.keys(samples).map(n => `<option>${n}</option>`).join("")}</select><label for="read-args">Arguments (JSON)</label><textarea class="code" id="read-args"></textarea><div class="actions"><button class="primary" id="read-run">Call through MCP</button></div></div></div>
        <div class="panel"><div class="panel-head"><h2 class="panel-title">Reach for a tool that is never exposed</h2></div><div class="panel-body"><p class="action-copy">Each of these exists on a server. The harness has no path to any of them.</p><div class="row">${s.never_exposed.map(n => `<button class="danger-button small" data-attempt="${esc(n)}">${esc(n)}</button>`).join("")}</div><div id="attempt-result" style="margin-top:12px"></div></div></div></div>
      <div id="read-result"></div>
      <div class="panel" style="margin-top:16px"><div class="panel-head"><div><span class="eyebrow">THE ASSISTANT'S LAST TURN, SEEN FROM THIS SIDE</span><h2 class="panel-title">What went over MCP</h2></div><div class="row"><a class="secondary small" href="#assistant">Ask in the Assistant</a><button class="secondary small" id="last-turn-refresh">Refresh</button></div></div><div class="panel-body" id="last-turn"></div></div>`;
    const lastTurn = async () => {
      const box = $("#last-turn"); if (!box) return;
      try {
        const t = await PPA.api("/api/systems_of_record/last_turn");
        if (!t.calls.length) { box.innerHTML = `<p class="action-copy">No turn has called a server yet. Ask the Assistant something, such as <em>What is in my inbox?</em>, then come back: every MCP call that turn made appears here, in order.</p>`; return; }
        const total = t.calls.reduce((sum, call) => sum + call.ms, 0);
        box.innerHTML = `<p class="action-copy"><strong>You asked:</strong> ${esc(t.request || "")}</p>
          <p class="mono faint">${t.calls.length} MCP call${t.calls.length === 1 ? "" : "s"} · ${Math.round(total)} ms on the wire · ${t.calls.filter(call => call.cached).length} answered from the 20-second read cache</p>
          ${t.calls.map((call, index) => `<details class="field"><summary><span class="num">${String(index + 1).padStart(2, "0")}</span><span><strong>${esc(call.tool)}</strong> <span class="mono faint">${esc(call.system)} server · ${esc(call.at)}</span></span><span class="row">${PPA.pill(t.tiers[call.tool], tierTone[t.tiers[call.tool]])}${PPA.pill(call.cached ? "cached" : `${call.ms} ms`)}${call.ok ? "" : PPA.pill("error", "bad")}</span></summary>
            <div class="compare" style="margin:10px"><div><span class="eyebrow">ARGUMENTS THE HARNESS SENT</span><pre class="json">${esc(JSON.stringify(call.arguments, null, 1))}</pre></div><div><span class="eyebrow">WHAT THE SERVER RETURNED${call.truncated ? " (CUT AT 2,500 CHARACTERS)" : ""}</span><pre class="json">${esc(call.result)}</pre></div></div></details>`).join("")}
          <p class="mono faint" style="margin-top:10px">${esc(t.note)}</p>`;
      } catch (error) { box.innerHTML = PPA.fail(error); }
    };
    $("#last-turn-refresh").onclick = lastTurn; lastTurn();
    const fill = () => { $("#read-args").value = JSON.stringify(samples[$("#read-tool").value], null, 2); };
    $("#read-tool").onchange = fill; fill();
    $("#read-run").onclick = async (event) => {
      try {
        const r = await PPA.busy(event.currentTarget, () => PPA.post("/api/systems_of_record/read", { name: $("#read-tool").value, arguments: JSON.parse($("#read-args").value || "{}") }));
        $("#read-result").innerHTML = `<div class="compare"><div class="panel"><div class="panel-head"><div><span class="eyebrow">WHAT THE SERVER RETURNED</span><h2>Raw MCP result</h2></div></div><div class="panel-body">${PPA.json(r.raw_mcp_result)}</div></div><div class="panel"><div class="panel-head"><div><span class="eyebrow">WHAT THE MODEL IS SHOWN</span><h2>Model-facing result</h2></div></div><div class="panel-body"><p class="method">${esc(r.difference)}</p>${PPA.json(r.model_facing_result)}</div></div></div>`;
      } catch (error) { $("#read-result").innerHTML = `<div style="margin-top:16px">${PPA.fail(error)}</div>`; }
    };
    $$("[data-attempt]").forEach(button => button.onclick = async () => {
      const args = { mail_trash_thread: { thread_id: "any" }, calendar_delete_event: { event_id: "any" }, notes_share_page: { page_id: "any", email: "someone@example.com" }, notes_delete_page: { page_id: "any" } }[button.dataset.attempt] || {};
      try {
        const r = await PPA.busy(button, () => PPA.post("/api/systems_of_record/attempt", { name: button.dataset.attempt, arguments: args }));
        $("#attempt-result").innerHTML = `<div class="notice good"><strong>${esc(r.tool)} was not reached.</strong> ${esc(r.refusal)}. The gateway's effect log holds ${r.effects_recorded_by_gateway.length} effect${r.effects_recorded_by_gateway.length === 1 ? "" : "s"}, none of them from this attempt.</div>`;
      } catch (error) { $("#attempt-result").innerHTML = PPA.fail(error); }
    });
  },
});

/* ── 3. Memory and the workday scratch pad ──────────────────────────────── */
PPA.register({
  id: "memory_layer", n: 3, title: "Memory and the workday scratch pad",
  blurb: "Long-term memory holds what should outlive the day. The scratch pad holds what should not, until the workday ends and the chosen notes are promoted once.",
  tags: ["Long-term · episodic", "ScratchFS · promotion · decay"],
  render: async (root) => {
    const labels = { preference: "Preferences", guideline: "Guidelines", person: "People and roles", commitment: "Commitments", fact: "Facts", episode: "Episodes of past sessions" };
    let tab = sessionStorage.getItem("ppa-memory-tab") || "memory";
    const draw = async () => {
      const s = await PPA.api("/api/memory_layer/status");
      const total = Object.values(s.counts).reduce((a, b) => a + b, 0);
      const memory = () => `<div class="grid wide-left"><div class="stack">${Object.entries(labels).map(([kind, label]) => `<div class="panel"><div class="panel-head"><h2 class="panel-title">${esc(label)}</h2><span class="mono faint">${s.memories[kind].length} · ${s.ttl_days[kind] ? s.ttl_days[kind] + " day TTL" : "kept until changed"}</span></div><div class="panel-body flush"><ul class="items">${s.memories[kind].map(m => `<li><span class="time">${esc(PPA.day(m.created_at))}</span><div><strong>${esc(m.content)}</strong><small>${esc(m.memory_id)} · ${esc(m.metadata.source || "stated")}${m.expires_at ? " · expires " + esc(PPA.day(m.expires_at)) : ""}${m.status !== "ACTIVE" ? " · " + esc(m.status) : ""}${m.use_count ? ` · recalled ${m.use_count}x` : ""}</small></div><button class="secondary small" data-forget="${esc(m.memory_id)}">Forget</button></li>`).join("") || `<li><span></span>${PPA.empty(kind === "episode" ? "An episode is written when a workday ends." : "None yet. Memory starts empty.")}<span></span></li>`}</ul></div></div>`).join("")}</div>
        <div class="stack"><div class="panel"><div class="panel-head"><h2 class="panel-title">Remember something</h2></div><div class="panel-body"><label for="mem-type">Type</label><select id="mem-type">${["preference", "guideline", "fact", "person", "commitment"].map(k => `<option>${k}</option>`).join("")}</select><label for="mem-content">One self-contained sentence</label><textarea id="mem-content"></textarea><div class="actions"><button class="primary" id="mem-write">Write to long-term memory</button></div><div id="mem-result"></div></div></div>
          <div class="panel"><div class="panel-head"><h2 class="panel-title">Recall</h2></div><div class="panel-body"><div class="row"><input id="recall-query" placeholder="What should come back?" aria-label="Recall query" /><button class="secondary" id="recall-run">Recall</button></div><div id="recall-result" style="margin-top:10px"></div></div></div>
          <div class="panel"><div class="panel-head"><h2 class="panel-title">Commitments in the notes</h2></div><div class="panel-body"><p class="action-copy">Reads every page through MCP and remembers the action lines that name ${esc(PPA.firstName())}.</p><button class="secondary" id="scan">Scan the notes</button><div id="scan-result" style="margin-top:10px"></div></div></div>
          <div class="notice"><strong>${esc(s.implementation)}.</strong> ${esc(s.note || "")} Recall: ${esc(s.recall)}.</div></div></div>`;
      const scratch = () => { const sc = s.scratch.session; return `<div class="grid wide-left"><div class="stack"><div class="panel"><div class="panel-head"><h2 class="panel-title">Session ${esc(sc.session_id)}</h2>${PPA.pill(sc.status.replace("_", " ").toLowerCase(), sc.status === "ACTIVE" ? "good" : "")}</div><div class="panel-body flush"><table class="list"><thead><tr><th>Path</th><th>Content</th><th>When the day ends</th><th>State</th></tr></thead><tbody>${sc.files.map(f => `<tr><td class="mono"><strong>${esc(f.path)}</strong><br><span class="faint">${esc(f.kind)}</span></td><td>${esc(f.content.slice(0, 160))}</td><td><label class="inline"><input type="checkbox" data-flag="${esc(f.path)}" ${f.promote_on_end ? "checked" : ""} ${f.promotion_state === "N" ? "" : "disabled"} /> promote</label><br><select data-target="${esc(f.path)}" ${f.promotion_state === "N" ? "" : "disabled"} style="margin-top:5px"><option ${f.promote_target === "task" ? "selected" : ""}>task</option><option ${f.promote_target === "memory" ? "selected" : ""}>memory</option></select></td><td>${PPA.pill(f.promotion_state, f.promotion_state === "Y" ? "good" : f.promotion_state === "D" ? "warn" : "")}</td></tr>`).join("") || `<tr><td colspan="4">${PPA.empty("No working files yet.")}</td></tr>`}</tbody></table><p class="action-copy mono" style="padding:10px 14px;margin:0">${esc(sc.promotion_states)}</p></div></div>
          <div class="panel"><div class="panel-head"><h2 class="panel-title">End the workday</h2></div><div class="panel-body"><p class="action-copy">${esc(s.scratch.promotion)}. Planned tasks that are still open count one more slip, and the day is written as an episode.</p><button class="primary" id="end-day">End the workday and promote</button><div id="end-result" style="margin-top:12px"></div></div></div></div>
          <div class="stack"><div class="panel"><div class="panel-head"><h2 class="panel-title">Quick capture</h2><span class="mono faint">/inbox</span></div><div class="panel-body"><textarea id="cap-text" placeholder="A thought to park"></textarea><div class="actions"><button class="primary" id="cap-run">Capture</button></div></div></div>
          <div class="panel"><div class="panel-head"><h2 class="panel-title">Working note</h2><span class="mono faint">/notes</span></div><div class="panel-body"><label for="note-path">Path</label><input id="note-path" value="/notes/observations.md" /><label for="note-content">Content</label><textarea id="note-content"></textarea><label class="inline" style="margin-top:10px"><input type="checkbox" id="note-promote" /> promote to memory when the day ends</label><div class="actions"><button class="secondary" id="note-run">Write</button></div></div></div>
          <div class="panel"><div class="panel-head"><h2 class="panel-title">Promotion queue</h2></div><div class="panel-body flush"><ul class="items">${s.scratch.queue.map(q => `<li><span class="time">${esc(q.target)}</span><div><strong>${esc(q.chunk.slice(0, 90))}</strong><small>${esc(q.path)} · hash ${esc(q.content_hash.slice(0, 12))}${q.outcome_ref ? " · " + esc(q.outcome_ref) : ""}</small></div>${PPA.pill(q.outcome || "staged", q.outcome === "PROMOTED" ? "good" : q.outcome === "DUPLICATE" ? "warn" : "")}</li>`).join("") || `<li><span></span>${PPA.empty("Nothing has been promoted yet.")}<span></span></li>`}</ul></div></div></div></div>`; };
      const decay = () => { const d = s.decay, list = (rows, line) => rows.map(line).join("") || `<li><span></span>${PPA.empty("None at this moment on the clock.")}<span></span></li>`; return `<div class="notice" style="margin-top:24px"><strong>As of ${esc(PPA.dayTime(d.as_of))}.</strong> Forgetting follows the harness clock. Move the clock forward from the header to watch done items fade, undated tasks go stale and memories reach the end of their time to live.</div>
        <div class="grid two"><div class="panel"><div class="panel-head"><h2 class="panel-title">Done items that have faded</h2><span class="mono faint">${esc(d.rules["done items"])}</span></div><div class="panel-body flush"><ul class="items">${list(d.faded_done, t => `<li><span class="time">${esc(PPA.day(t.completed_at))}</span><div><strong>${esc(t.title)}</strong><small>${esc(t.task_id)}</small></div><span></span></li>`)}</ul></div></div>
          <div class="panel"><div class="panel-head"><h2 class="panel-title">Drop candidates</h2><span class="mono faint">stale</span></div><div class="panel-body flush"><ul class="items">${list(d.drop_candidates, t => `<li><span class="time">${esc(PPA.day(t.touched_at))}</span><div><strong>${esc(t.title)}</strong><small>${esc(t.task_id)} · undated, untouched since then</small></div><button class="secondary small" data-drop="${esc(t.task_id)}">Drop</button></li>`)}</ul></div></div>
          <div class="panel"><div class="panel-head"><h2 class="panel-title">Memories nearing expiry</h2></div><div class="panel-body flush"><ul class="items">${list(d.expiring, m => `<li><span class="time">${m.expires_in_days} d</span><div><strong>${esc(m.content)}</strong><small>${esc(m.memory_type)} · expires ${esc(PPA.day(m.expires_at))}</small></div><span></span></li>`)}</ul></div></div>
          <div class="panel"><div class="panel-head"><h2 class="panel-title">Expired</h2><button class="secondary small" id="sweep">Run the sweep</button></div><div class="panel-body flush"><ul class="items">${list(d.expired, m => `<li><span class="time">${esc(m.memory_type)}</span><div><strong>${esc(m.content)}</strong><small>expired ${esc(PPA.day(m.expires_at))} · kept for the record, never recalled</small></div><span></span></li>`)}</ul></div></div></div>`; };
      root.innerHTML = `<div class="row" style="margin-top:24px;justify-content:space-between"><div class="tabs" id="memory-tabs"><button data-tab="memory">Long-term memory · ${total}</button><button data-tab="scratch">Workday scratch pad · ${s.scratch.session.files.length}</button><button data-tab="decay">Forgetting</button></div><span class="mono faint">${esc(s.provider)} provider</span></div><div id="memory-tab">${{ memory, scratch, decay }[tab]()}</div>`;
      $$("#memory-tabs button").forEach(b => { b.classList.toggle("active", b.dataset.tab === tab); b.onclick = () => { tab = b.dataset.tab; sessionStorage.setItem("ppa-memory-tab", tab); draw(); }; });
      const act = (selector, handler) => { const node = $(selector); if (node) node.onclick = async (event) => { try { await PPA.busy(event.currentTarget, handler); } catch (error) { PPA.toast("That did not work", error.message, "bad"); } }; };
      act("#mem-write", async () => { const r = await PPA.post("/api/memory_layer/write", { memory_type: $("#mem-type").value, content: $("#mem-content").value }); await draw(); $("#mem-result").innerHTML = `<p class="field-help">${r.deduplicated ? "Already known: the content hash matched " : "Written as "}${esc(r.memory_id)}.</p>`; });
      act("#recall-run", async () => { const r = await PPA.post("/api/memory_layer/recall", { query: $("#recall-query").value }); $("#recall-result").innerHTML = `<ul class="items">${r.recalled.map(m => `<li><span class="time">score ${m.score}</span><div><strong>${esc(m.content)}</strong><small>${esc(m.memory_type)}</small></div><span></span></li>`).join("") || `<li><span></span>${PPA.empty("Nothing matched. Standing preferences still apply to every turn.")}<span></span></li>`}</ul><p class="field-help">${esc(r.method)}</p>`; });
      act("#scan", async () => { const r = await PPA.post("/api/memory_layer/commitments/scan"); await draw(); $("#scan-result").innerHTML = `<p class="field-help">${r.pages_read} pages read, ${r.new} new commitments. ${esc(r.rule)}</p>`; });
      act("#cap-run", async () => { await PPA.post("/api/memory_layer/capture", { text: $("#cap-text").value }); await draw(); });
      act("#note-run", async () => { await PPA.post("/api/memory_layer/scratch/write", { path: $("#note-path").value, content: $("#note-content").value, promote_on_end: $("#note-promote").checked, promote_target: "memory" }); await draw(); });
      act("#end-day", async () => { const r = await PPA.post("/api/memory_layer/session/end"); await draw(); $("#end-result").innerHTML = `<div class="notice good"><strong>${r.promoted} promoted, ${r.duplicates} duplicate${r.duplicates === 1 ? "" : "s"} skipped, ${r.carried_over.length} carried over.</strong><br>${r.outcomes.map(o => `${esc(o.path)} to ${esc(o.target)}: ${esc(o.outcome)} (${esc(o.reference)}, hash ${esc(o.content_hash)})`).join("<br>")}<br>Episode: ${esc(r.episode.content)}</div>`; });
      act("#sweep", async () => { const r = await PPA.post("/api/memory_layer/decay/sweep"); PPA.toast("Sweep finished", `${r.expired_now.length} memories expired.`); await draw(); });
      $$("[data-forget]").forEach(b => b.onclick = async () => { await PPA.api(`/api/memory_layer/${encodeURIComponent(b.dataset.forget)}`, { method: "DELETE" }); draw(); });
      $$("[data-drop]").forEach(b => b.onclick = async () => { await PPA.post(`/api/assistant/tasks/${encodeURIComponent(b.dataset.drop)}/drop`); draw(); });
      $$("[data-flag]").forEach(b => b.onchange = async () => { await PPA.post("/api/memory_layer/scratch/flag", { path: b.dataset.flag, promote: b.checked }); draw(); });
      $$("[data-target]").forEach(b => b.onchange = async () => { const flag = $(`[data-flag="${CSS.escape(b.dataset.target)}"]`); await PPA.post("/api/memory_layer/scratch/flag", { path: b.dataset.target, promote: flag.checked, target: b.value }); draw(); });
    };
    await draw();
  },
});

/* ── 4. Governed meaning ────────────────────────────────────────────────── */
PPA.register({
  id: "governed_meaning", n: 4, title: "Governed meaning",
  blurb: "Ask one question two ways over the same live data: by surface features, and by a written definition that a person can read and a test can assert.",
  tags: ["Naive reading against definition", "Shared policy"],
  render: async (root) => {
    const s = await PPA.api("/api/governed_meaning/status");
    root.innerHTML = `<div class="panel" style="margin-top:24px"><div class="panel-body"><label>One question, two readings</label><div class="row" id="questions">${Object.entries(s.questions).map(([k, v]) => `<button class="secondary" data-question="${k}">${esc(v)}</button>`).join("")}</div></div></div><div id="comparison"></div>
      <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">The definitions</h2><span class="mono faint">${esc(s.teaching_point)}</span></div><div class="panel-body flush"><table class="list"><thead><tr><th>Term</th><th>Definition</th><th>Decided by</th></tr></thead><tbody>${s.definitions.map(d => `<tr><td><strong>${esc(d.term)}</strong></td><td>${esc(d.definition)}</td><td class="mono">${esc(d.source)}</td></tr>`).join("")}</tbody></table></div></div>`;
    const item = (x) => x.start_local ? `<li><span class="time">${esc(x.start_local)}</span><div><strong>${esc(x.start_local)} to ${esc(x.end_local)}</strong><small>${x.minutes} minutes</small></div><span></span></li>`
      : x.weekday ? `<li class="${x.overbooked ? "flag" : ""}"><span class="time">${esc(x.weekday.slice(0, 3))}</span><div><strong>${x.meeting_minutes} meeting minutes</strong><small>${esc(x.day)} · ${x.free_minutes} free${x.overbooked ? " · " + esc(x.reason) : ""}</small></div>${x.overbooked ? PPA.pill("over-booked", "bad") : "<span></span>"}</li>`
        : `<li><span></span><div><strong>${esc(x.label)}</strong><small>${esc(x.id)} · ${esc(x.why)}</small></div><span></span></li>`;
    const list = (rows, nothing) => `<ul class="items">${rows.map(item).join("") || `<li><span></span>${PPA.empty(nothing)}<span></span></li>`}</ul>`;
    const run = async (question) => {
      $$("#questions button").forEach(b => b.className = b.dataset.question === question ? "primary" : "secondary");
      $("#comparison").innerHTML = `<div style="margin-top:16px"><span class="loading">Reading live data</span></div>`;
      try {
        const r = await PPA.post("/api/governed_meaning/compare", { question });
        $("#comparison").innerHTML = `<div class="compare"><div class="panel"><div class="panel-head"><div><span class="eyebrow">NAIVE READING</span><h2>${esc(r.text)}</h2></div>${PPA.pill(`${r.naive.answer.length} found`)}</div><div class="panel-body"><p class="method">${esc(r.naive.method)}</p>${list(r.naive.answer, "The naive reading found nothing.")}${r.naive.flaws.length ? `<div class="notice" style="margin-top:12px"><strong>What it gets wrong here</strong><br>${r.naive.flaws.map(esc).join("<br>")}</div>` : ""}</div></div>
          <div class="panel"><div class="panel-head"><div><span class="eyebrow">GOVERNED DEFINITION</span><h2>${esc(r.text)}</h2></div>${PPA.pill(r.governed.source, "good")}</div><div class="panel-body"><p class="method">${esc(r.governed.definition)}</p>${list(r.governed.answer, "Nothing meets the definition at this moment. With no tasks yet, nothing can be urgent.")}${r.governed.also?.length ? `<h3 class="panel-title" style="margin:14px 0 6px">${esc(r.governed.also_label)}</h3>${list(r.governed.also, "")}` : ""}</div></div></div>`;
      } catch (error) { $("#comparison").innerHTML = `<div style="margin-top:16px">${PPA.fail(error)}</div>`; }
    };
    $("#questions").onclick = (event) => { if (event.target.dataset.question) run(event.target.dataset.question); };
    run("free");
  },
});

/* ── 5. Inbox triage and task extraction ────────────────────────────────── */
PPA.register({
  id: "inbox_triage", n: 5, title: "Inbox triage and task extraction",
  blurb: "Every thread gets governed signals and a category. Actionable threads become tasks that link back to their source; a thread that already has a task is cited, never raised twice.",
  tags: ["Governed signals", "Source links · duplicate suppression · quarantine"],
  render: async (root) => {
    const draw = async (result = null) => {
      const s = await PPA.api("/api/inbox_triage/status");
      const u = s.unknown_senders;
      root.innerHTML = `<div class="tiles" style="margin-top:24px">${Object.entries(s.counts).map(([k, n]) => `<div class="tile"><span>${esc(k)}</span><strong>${n}</strong></div>`).join("")}<div class="tile"><span>Open tasks</span><strong>${s.open_tasks}</strong></div></div>
        <div class="notice" style="margin-top:16px"><strong>The tripwire is not a defence.</strong> ${esc(s.tripwire.statement)} In this inbox ${u.threads} thread${u.threads === 1 ? "" : "s"} came from senders ${esc(PPA.firstName())} has never written to; the tripwire flagged ${u.flagged_by_tripwire}.${u.passed_the_tripwire.length ? " It passed " + u.passed_the_tripwire.map(t => `<button class="link-button" data-open="${esc(t)}">${esc(t)}</button>`).join(", ") + "." : ""} <span class="mono faint">Measured on ${esc(s.tripwire.measured_on)}.</span></div>
        ${result ? `<div class="notice good" style="margin-top:16px"><strong>${result.created.length} tasks created, ${result.suppressed_duplicates.length} duplicates suppressed, ${result.drafts.length} drafts saved and none sent.</strong>${result.created.length ? "<br>" + result.created.map(c => `${esc(c.task_id)} from ${esc(c.thread_id)}`).join(" · ") : ""}${result.suppressed_duplicates.length ? "<br>No duplicate: " + result.suppressed_duplicates.map(c => `${esc(c.thread_id)} is covered by ${esc(c.task_id)}`).join(" · ") : ""}${result.quarantined.length ? "<br>Quarantined and untouched: " + result.quarantined.map(esc).join(", ") : ""}</div>` : ""}
        <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">${s.window} threads · ${esc(s.order)}</h2><div class="row"><span class="mono faint">as of ${esc(PPA.dayTime(s.as_of))}</span><button class="primary small" id="extract-all">Extract all actionable</button></div></div><div class="panel-body flush">${PPA.ui.triageTable(s)}</div></div>`;
      const extract = async (ids, button) => { try { const r = await PPA.busy(button, () => PPA.post("/api/inbox_triage/extract", { thread_ids: ids })); await draw(r); } catch (error) { PPA.toast("Extraction failed", error.message, "bad"); } };
      $("#extract-all").onclick = (event) => extract([], event.currentTarget);
      root.onclick = (event) => {
        const open = event.target.closest("[data-open]"), button = event.target.closest("[data-extract]"), row = event.target.closest("[data-thread]");
        if (open) PPA.openThread(open.dataset.open);
        else if (button) extract([button.dataset.extract], button);
        else if (row) PPA.openThread(row.dataset.thread);
      };
    };
    await draw();
  },
});

/* ── 6. Calendar intelligence ───────────────────────────────────────────── */
PPA.register({
  id: "calendar_intel", n: 6, title: "Calendar intelligence",
  blurb: "Free time, broken meeting rules and over-booked days are computed from real events and the owner's own settings. Time blocks fit around them and wait for approval.",
  tags: ["Free slots · load", "Time-blocking · meeting prep"],
  render: async (root) => {
    let date = PPA.status.clock.now.slice(0, 10);
    const draw = async (extra = "") => {
      const s = await PPA.api(`/api/calendar_intel/status?date=${date}`);
      const d = s.day, limit = Number(d.rules.max_meeting_minutes_per_day), layers = s.layers || [];
      const broken = new Set(d.meeting_rule_violations.map(e => e.event_id));
      root.innerHTML = `<div class="row" style="margin-top:24px"><label class="inline" for="cal-date">Day</label><input id="cal-date" type="date" value="${esc(date)}" style="max-width:190px" />${PPA.pill(`working hours ${d.rules.working_hours}`)}${PPA.pill(`no meetings before ${d.rules.no_meetings_before}`)}${PPA.pill(`a slot holds at least ${d.rules.minimum_slot_minutes} minutes`)}${PPA.pill(`over-booked above ${limit} meeting minutes`)}</div>
        ${layers.length ? `<div class="notice good" style="margin-top:14px"><strong>The practice calendar has ${layers.length === 1 ? "one layer" : "two layers"}, and each event names its own.</strong><ul class="plain">${layers.map(l => `<li>${PPA.ui.source(l.source)} ${esc(l.about)} ${l.events} on this day.</li>`).join("")}</ul></div>` : ""}
        <div class="grid two"><div class="panel"><div class="panel-head"><h2 class="panel-title">${esc(d.weekday)} ${esc(d.day)}</h2>${d.load.overbooked ? PPA.pill("over-booked", "bad") : PPA.pill(`${d.load.meeting_minutes} meeting minutes`)}</div><div class="panel-body flush"><ul class="items">${d.events.map(e => `<li class="${broken.has(e.event_id) ? "flag" : ""}"><span class="time">${esc(PPA.time(e.start))}</span><div><strong>${esc(e.title)}</strong><small>${esc(PPA.time(e.start))} to ${esc(PPA.time(e.end))} · ${esc(e.kind)} · ${esc(e.event_id)} · organiser ${esc(e.organizer)}${e.source ? " " + PPA.ui.source(e.source) : ""}</small>${broken.has(e.event_id) ? `<small>Breaks the no-meetings-before-${esc(d.rules.no_meetings_before)} rule</small>` : ""}</div><button class="secondary small" data-prep="${esc(e.event_id)}">Prep</button></li>`).join("") || `<li><span></span>${PPA.empty("No events on this day.")}<span></span></li>`}</ul></div></div>
          <div class="panel"><div class="panel-head"><h2 class="panel-title">Free by definition</h2><span class="mono faint">${d.load.free_minutes} minutes${d.is_today ? " · from now" : ""}</span></div><div class="panel-body flush"><ul class="items">${d.free_slots.map(f => `<li><span class="time">${esc(f.start_local)}</span><div><strong>${esc(f.start_local)} to ${esc(f.end_local)}</strong><small>${f.minutes} minutes · holds ${Math.floor(f.minutes / d.rules.pomodoro_unit_minutes)} Pomodoro units of ${d.rules.pomodoro_unit_minutes} minutes</small></div><span></span></li>`).join("") || `<li><span></span>${PPA.empty("No slot can hold a Pomodoro.")}<span></span></li>`}</ul></div></div></div>
        <div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">Load, each day judged on its own</h2></div><div class="panel-body"><table class="list"><tbody>${s.week.map(w => `<tr><td style="width:150px"><strong>${esc(w.weekday)}</strong><br><span class="mono faint">${esc(w.day)}</span></td><td><div class="meter ${w.overbooked ? "over" : ""}" role="img" aria-label="${w.meeting_minutes} of ${limit} meeting minutes"><i style="width:${Math.min(100, w.meeting_minutes / limit * 100)}%"></i></div></td><td class="num" style="width:170px">${w.meeting_minutes} of ${limit} min</td><td style="width:130px">${w.overbooked ? PPA.pill("over-booked", "bad") : PPA.pill(`${w.free_minutes} min free`)}</td></tr>`).join("")}</tbody></table></div></div>
        <div class="grid two"><div class="panel"><div class="panel-head"><h2 class="panel-title">Time-block the top tasks</h2></div><div class="panel-body"><p class="action-copy">${s.top_tasks.length ? "In governed order: " + s.top_tasks.map(t => `${esc(t.title)} (${t.est_pomodoros})`).join("; ") + "." : "There are no open tasks yet. Extract some in the inbox triage chapter."}</p><div class="actions"><button class="primary" id="plan-run" ${s.top_tasks.length ? "" : "disabled"}>Plan the blocks</button><button class="secondary" id="plan-approve" ${s.top_tasks.length ? "" : "disabled"}>Plan and draft calendar events</button></div><div id="plan-result" style="margin-top:12px"></div></div></div>
          <div class="panel"><div class="panel-head"><h2 class="panel-title">Meeting prep</h2></div><div class="panel-body" id="prep-result">${PPA.empty("Press Prep on an event to gather its thread, page, people and earlier mail.")}</div></div></div>${extra}`;
      $("#cal-date").onchange = (event) => { date = event.target.value || date; draw(); };
      const blocks = (r) => `<ul class="items">${r.blocks.map(b => `<li><span class="time">${esc(b.start_local)}</span><div><strong>${esc(b.title)}</strong><small>${esc(b.start_local)} to ${esc(b.end_local)} · ${esc(b.task_id)} · part ${esc(b.part)} · ${b.pomodoros} Pomodoro${b.pomodoros === 1 ? "" : "s"}</small></div><span></span></li>`).join("")}${r.unplaced.map(u => `<li class="flag"><span class="time">none</span><div><strong>${esc(u.title)}</strong><small>${esc(u.reason)}</small></div><span></span></li>`).join("")}</ul><p class="field-help">${esc(r.rule)} Written to ${esc(r.plan_path)}.</p>`;
      $("#plan-run").onclick = async (event) => { try { const r = await PPA.busy(event.currentTarget, () => PPA.post("/api/calendar_intel/plan", { date })); $("#plan-result").innerHTML = blocks(r); } catch (error) { $("#plan-result").innerHTML = PPA.fail(error); } };
      $("#plan-approve").onclick = async (event) => { try { const r = await PPA.busy(event.currentTarget, () => PPA.post("/api/calendar_intel/plan/request_approval", { date })); $("#plan-result").innerHTML = blocks(r) + `<div class="notice" style="margin-top:10px"><strong>${r.drafted.length} calendar events drafted.</strong> Nothing is on the calendar yet. Decide them in <a href="#approvals">Approval gates and action log</a>.</div>`; } catch (error) { $("#plan-result").innerHTML = PPA.fail(error); } };
      $$("[data-prep]").forEach(b => b.onclick = async () => {
        $("#prep-result").innerHTML = '<span class="loading">Reading the thread, the notes and earlier mail</span>';
        try {
          const p = await PPA.api(`/api/calendar_intel/prep/${encodeURIComponent(b.dataset.prep)}`);
          $("#prep-result").innerHTML = `<dl class="kv"><dt>Event</dt><dd><strong>${esc(p.event.title)}</strong> · ${esc(PPA.dayTime(p.event.start))} · starts in ${p.starts_in_minutes} minutes${p.event.source ? " " + PPA.ui.source(p.event.source) : ""}</dd>${p.topic ? `<dt>Searched for</dt><dd>${esc(p.topic)}</dd>` : ""}<dt>People</dt><dd>${p.people.map(x => `${esc(x.name || x.email)}${x.is_vip ? " " + PPA.pill("VIP", "strong") : ""}${x.known ? "" : " " + PPA.pill("not a known contact", "warn")}`).join("<br>") || "Only the owner"}</dd>
            <dt>Thread</dt><dd>${p.related_thread ? `<button class="link-button" data-open="${esc(p.related_thread.thread_id)}">${esc(p.related_thread.thread_id)}</button> ${esc(p.related_thread.subject)}` : "none"}</dd><dt>Page</dt><dd>${p.related_page ? esc(p.related_page.title) : "none yet"}</dd><dt>Open actions</dt><dd>${p.owner_actions.map(esc).join("<br>") || "none recorded"}</dd>
            <dt>Mail on this matter</dt><dd>${p.earlier_threads.map(t => `<button class="link-button" data-open="${esc(t.thread_id)}">${esc(t.thread_id)}</button> ${esc(PPA.day(t.received_at))} ${esc(t.subject)}`).join("<br>") || "none found"}</dd></dl>`;
          $$("#prep-result [data-open]").forEach(x => x.onclick = () => PPA.openThread(x.dataset.open));
        } catch (error) { $("#prep-result").innerHTML = PPA.fail(error); }
      });
    };
    await draw();
  },
});
