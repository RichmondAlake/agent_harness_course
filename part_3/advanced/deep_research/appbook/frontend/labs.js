/* One chapter per harness component. Each has the teaching frame from the notebook and a lab that runs
   that component alone, on a small practice paper of its own. */
const COMPONENTS = ["Foundation", "State store", "Model gateway", "Cost control", "Evidence store", "Vocabulary", "Skills", "Tools",
  "Context management", "Research loop", "Memory", "Planner", "Writer", "Verifier", "Quality gate", "Orchestration", "Human approval",
  "Durability", "Observability"];
const lab = (path, body) => APP.post(`/api/lab${path}`, body);
const money = (n) => `$${Number(n || 0).toFixed(Number(n) < 0.1 ? 4 : 2)}`;
const callsTable = (rows) => APP.table(["kind", "fresh", "cache_write", "cache_read", "output", "usd", "seconds"], rows || []);
const panel = (title, body, note = "") => `<div class="panel" style="margin-top:16px"><div class="panel-head"><h2 class="panel-title">${esc(title)}</h2>${note ? `<span class="mono faint">${esc(note)}</span>` : ""}</div><div class="panel-body">${body}</div></div>`;
const run = (root, id, work) => { $(id, root).onclick = (ev) => APP.busy(ev.currentTarget, work); };

const FRAMES = {
  paper: { parts: ["Orchestration", "Human approval", "Durability"], part: "Parts 15 to 18",
    why: "A run takes minutes and many model calls, and two of its steps belong to a person: accepting the plan before anything is read, and accepting the paper before it is published. The run waits as a checkpoint in the database, so it survives being stopped.",
    term: ["checkpoint", "A saved copy of the run's state after a step. A run that stops is continued from its last checkpoint, by the same process or by another one."],
    test: "Start a paper, then tick the cut-off box when you approve the outline. The run stops inside the organise step, after all the research. Press Continue and watch it carry on without building the framework twice." },
  approval: { parts: ["Human approval"], part: "Parts 15 and 18",
    why: "Two steps belong to a person: accepting the plan before anything is read, and accepting the paper before it is published. At each, the run stops, its state is saved as a checkpoint, and nothing happens until an answer arrives. The first stop comes when changing direction is still nearly free.",
    term: ["interrupt", "A node asks a question and the run ends there, saved. It starts again when the answer is sent, by this process or another."],
    test: "Plan a paper and stop at the outline. It costs a few cents. Then revise it with a note, or reject it. Approving would start the whole run, so that is done from Write a survey." },
  durability: { parts: ["Durability"], part: "Part 16",
    why: "A run takes minutes and many calls, and sooner or later a process dies in the middle. A checkpoint after every step says where the run was. Tables say what work exists. A step that may run twice asks the database whether its work is already there, so nothing is paid for twice.",
    term: ["checkpoint", "A saved copy of the run's state after a step. A run that stops is continued from its last checkpoint."],
    test: "Runs that stopped part-way are listed here with a Continue button. To cut one off on purpose, tick the box when you approve an outline in Write a survey." },
  refarch: { parts: [], part: "Part 1",
    why: "The whole harness on one page: what sits outside the database (the person, the model, the search service) and what the harness keeps inside it.", test: "Select a component to read its role, or simulate a run." },
  foundation: { parts: ["Foundation"], part: "Part 2",
    why: "Everything the harness keeps is in one Oracle AI Database: the evidence, the drafts, the bill, the memory and the checkpoints. The database also makes the embeddings itself, with a sentence model loaded into it, so no text leaves the database to be embedded.",
    term: ["embedding", "A list of numbers that stands for the meaning of a piece of text. Two texts about the same thing have embeddings that are close together."],
    test: "Embed a phrase. The numbers come from a model running inside the database." },
  state: { parts: ["State store"], part: "Part 3",
    why: "Anything the harness would be sorry to lose is a row, written the moment it exists: a page that was fetched, a note that was taken, a model call that was paid for. If the process stops, the rows are still there.",
    term: ["ledger", "The harness's diary. Every step writes what it did, and every decision writes why."],
    test: "Write a line to the ledger and read it back. The data explorer at the bottom of the page shows every table." },
  gateway: { parts: ["Model gateway", "Cost control"], part: "Part 4",
    why: "Every model call in the harness goes through one function. It gets an answer in a fixed shape, prices the call and writes a row. When several calls begin with the same long text, that text is cached and read back at a twentieth of the price. The budget is then a query over those rows, and one function decides which optional work still fits.",
    term: ["prompt cache", "The provider keeps the processed start of a prompt for a few minutes. A later call that begins with exactly the same text reuses it."],
    test: "Ask a question and read its bill. Then send two calls that share a long opening and compare their rows. Then ask the budget what it would allow." },
  library: { parts: ["Evidence store"], part: "Part 5",
    why: "The model cannot read forty papers it has never seen. The harness searches the web, fetches the best pages and stores each one with its full text and an embedding. Keeping the text is what later lets a claim be checked against the page.",
    term: ["evidence library", "The table of pages a paper has read. It can be asked by meaning, and every citation resolves to one of its rows."],
    test: "Run a web search on its own. Fetch one page. Ask the practice library a question once a researcher has stored pages in it." },
  vocabulary: { parts: ["Vocabulary"], part: "Part 6",
    why: "Sources use many words for one thing: scaffold, wrapper, agent runtime. The harness keeps a short list of the terms it has agreed to use, with their meanings and the words they replace. Each term is a row with an embedding, so only the terms that bear on a task are drawn into a prompt, and the avoided words can be counted in what comes back.",
    term: ["semantic layer", "A governed set of names and meanings that sits between raw material and whatever uses it, so the same thing is called the same thing everywhere."],
    test: "Type a sentence or a section purpose. See which terms it draws, the block a prompt would carry, and any avoided words found in your text." },
  skills: { parts: ["Skills"], part: "Part 7",
    why: "Reading an experiment paper is a different job from reading a survey or a vendor's blog post. Each procedure is a skill: a name, a one-line description and a body of steps, stored in the database with an embedding. The model is shown only names and descriptions, and loads a body when it needs it.",
    term: ["progressive disclosure", "Showing a little first and the rest on request: the description is always in view, the full procedure is loaded only when used."],
    test: "Describe a reading task. See which skills are nearest and the short manifest a prompt would carry. Then load one and compare its length." },
  tools: { parts: ["Tools"], part: "Part 8",
    why: "A researcher is the model in a loop with six tools: search the web, read a page, load a skill, take a note, look back at a page, finish. It chooses its own next step. The loop is a LangGraph graph of its own: an agent node that calls the model, a tools node that runs the tool calls, and an edge between them. The harness decides what each tool is allowed to do: only links a search returned may be read, only so many pages, only so many turns.",
    term: ["tool", "A function the model may ask the harness to run. The model sees a name, a description and the shape of the arguments; the harness runs the function and sends the result back."],
    test: "Read the researcher's graph and the six tool definitions. Run one tool call by hand and see exactly what the model would be shown, including a refusal. Then send a whole researcher out." },
  context: { parts: ["Context management"], part: "Part 8",
    why: "A tool loop sends its whole conversation again on every turn, so what goes into it matters. The harness does two things. Offloading: a page is stored whole in the database and only the first part enters the conversation, with a way to look back. Compaction: when the conversation passes a size limit, the harness asks for a summary and continues from that.",
    term: ["context compaction", "Replacing a long conversation with a summary of it and continuing from the summary. Offloading is its companion: keeping bulky content in storage the agent can read back."],
    test: "Pick a stored page and see how much of it stays out of the conversation, then look back into it with a question. Then compact a small conversation and compare its size before and after." },
  notes: { parts: ["Research loop"], part: "Part 9",
    why: "This is the step that makes it deep research and not a fixed pipeline. After the researchers have worked, the harness asks the model which sections are thin and what to look for next, and then decides for itself whether a researcher goes out again.",
    term: ["research loop", "Search, read, reflect, search again. The queries of the second round do not exist when the run starts. They are written from what the first round read."],
    test: "Reflect on what the practice researcher read. If it names gaps, send a researcher out again with them." },
  memory: { parts: ["Memory"], part: "Part 10",
    why: "The library is what one paper read. Memory is what the harness carries to the next paper: what a reader said they want, and what earlier referees found missing. It is kept in Oracle Agent Memory, scoped to a reader, and recalled when a paper is planned.",
    term: ["agent memory", "What an agent keeps across runs, stored outside the model and recalled when it bears on the task at hand."],
    test: "Store a preference. Correct it: the new one supersedes the old one, and the old one stops being recalled. Then recall by subject." },
  planner: { parts: ["Planner"], part: "Part 11",
    why: "One call turns a subject into research questions and an outline, with search queries for every section. What memory holds for the reader goes into that call. The outline is what a person approves, at a point where almost nothing has been spent.",
    term: ["outline", "The sections of the paper, each with a purpose and its first searches."],
    test: "Plan a paper. Nothing is searched or read. If you stored preferences in the memory chapter, look for them in the plan." },
  writer: { parts: ["Writer", "Verifier"], part: "Part 12",
    why: "A model asked to cite will write fluent sentences and attach citations to them, and some will say more than the source does. So each section is written from excerpts of the pages, every cited claim needs a quote, and the harness checks that the quote really is on the stored page. What fails is repaired once, then removed by code.",
    term: ["claim check", "For each cited sentence the model gives a verdict and copies a quote. The harness looks for the quote on the page. A claim passes on the quote, not on the verdict."],
    test: "Check a quote against a page with no model involved. Split a draft into its cited claims. Then write the practice section and read its claims." },
  review: { parts: ["Quality gate"], part: "Part 13",
    why: "Two different judgements are made on the whole paper. The referee is a model call and gives an opinion. The release check is seven things the harness can count. Only the counted facts can block a release.",
    term: ["release check", "Seven pass-or-fail facts with a verdict of READY or BLOCKED."],
    test: "Run the release check on the selected paper. It counts rows and calls no model." },
  architecture: { parts: ["Orchestration"], part: "Part 14",
    why: "The graph adds no new ability. It gives the functions an order, two loops and two stops, and writes a checkpoint after every step.", test: "Select a paper and its path through the graph lights up." },
  read: { parts: [], part: "Part 18", why: "The published paper. Citations are numbers that point at the reference list, and the last section is written by the harness from its own counts.", test: "Open it as a page, or as Markdown." },
  ledger: { parts: ["Observability"], part: "Part 17",
    why: "A run can be explained afterwards only if decisions were written down as they were made. The ledger holds every step, every budget decision and its reasons.", test: "Look for the reflect and budget entries: they say what the harness decided and why." },
};

const frame = (f) => `<div class="frame">
  ${f.parts.length ? `<div class="frame-tag"><span>Harness component</span>${f.parts.map(p => `<b>${esc(p)}</b>`).join("")}<span class="frame-part">Notebook ${esc(f.part)}</span></div>
  <div class="strip">${COMPONENTS.map(c => `<i class="${f.parts.includes(c) ? "on" : ""}">${esc(c)}</i>`).join("")}</div>` : `<div class="frame-tag"><span class="frame-part">Notebook ${esc(f.part)}</span></div>`}
  <p class="frame-why">${esc(f.why)}</p>
  ${f.term ? `<p class="frame-term"><b>Key term: ${esc(f.term[0])}.</b> ${esc(f.term[1])}</p>` : ""}
  ${f.test ? `<p class="frame-test"><b>Try it.</b> ${esc(f.test)}</p>` : ""}</div>`;

/* ── the labs ─────────────────────────────────────────────────────────────── */
const LABS = {
  foundation: async (root) => {
    const s = APP.status.database || {};
    root.innerHTML = panel("The database", `<dl class="kv"><dt>Version</dt><dd>Oracle AI Database ${esc(s.version || "")}</dd><dt>Address</dt><dd class="mono">${esc(s.dsn || "")}</dd><dt>Account</dt><dd class="mono">${esc(s.user || "")}</dd></dl>`)
      + panel("Embed a phrase inside the database", `<div class="row"><input id="t" value="how agents manage their context window" /><button class="primary" id="go">Embed</button></div><div id="o" style="margin-top:12px"></div>`);
    run(root, "#go", async () => { const r = await lab("/embed", { text: $("#t", root).value }); $("#o", root).innerHTML = `<dl class="kv"><dt>Model</dt><dd class="mono">${esc(r.model)}</dd><dt>Dimensions</dt><dd>${r.dimensions}</dd><dt>First numbers</dt><dd class="mono">${esc(r.first.join(", "))} …</dd><dt>Time</dt><dd>${r.seconds} s</dd></dl>`; });
  },
  state: async (root) => {
    const tables = (await APP.api("/api/explorer/tables")).tables;
    root.innerHTML = panel("The tables", APP.table(["name", "rows"], tables), "one row for everything worth keeping")
      + panel("Write to the ledger, and read it back", `<div class="row"><input id="t" value="a note written from the state store chapter" /><button class="primary" id="go">Write a ledger entry</button></div><div id="o" style="margin-top:12px"></div>`);
    run(root, "#go", async () => { const r = await lab("/ledger", { text: $("#t", root).value }); $("#o", root).innerHTML = APP.table(["node", "kind", "detail", "at"], r.ledger); });
  },
  gateway: async (root) => {
    const papers = (await APP.api("/api/papers")).papers;
    root.innerHTML = panel("1. One model call, and its row", `<div class="row"><input id="q" value="What is an agent harness, and what is one decision it makes?" /><button class="primary" id="ask">Ask the model</button></div><div id="a" style="margin-top:12px"></div><p class="field-help">The reply is constrained to a JSON schema, so the harness gets an object with known fields. The row below it is what the call cost.</p>`)
      + panel("2. Two calls that share a long opening", `<button class="primary" id="cache">Send both calls</button><div id="c" style="margin-top:12px"></div><p class="field-help">The first call pays to write the shared text into the cache. The second reads it back. Compare cache_write and cache_read, and the price of each call.</p>`)
      + panel("3. What would the budget allow?", `<div class="row"><label>Paper <select id="bp"><option value="">the practice paper</option>${papers.filter(p => p.status !== "LAB").map(p => `<option value="${esc(p.paper_id)}">${esc(p.paper_id)} · ${esc(p.status)}</option>`).join("")}</select></label><label>Budget $ <input id="bb" type="number" step="0.5" value="5" style="width:90px" /></label><label>Optional work <select id="bw"><option value="follow_up">follow-up searches</option><option value="revise">sections to revise</option></select></label><label>Asked <input id="ba" type="number" value="6" style="width:70px" /></label><button class="primary" id="grant">Ask the budget</button></div><div id="g" style="margin-top:12px"></div><p class="field-help">Optional work may only use what is left after the reserve, which is what the paper still needs in order to be finished.</p>`);
    run(root, "#ask", async () => { const r = await lab("/ask", { text: $("#q", root).value }); $("#a", root).innerHTML = APP.json(r.answer) + callsTable(r.call); APP.refreshStatus(); });
    run(root, "#cache", async () => { const r = await lab("/cache"); $("#c", root).innerHTML = `<p>${r.answers.map(a => esc(a)).join("<br>")}</p>` + callsTable(r.calls) + `<p class="field-help">${r.shared_chars.toLocaleString()} characters were shared by both calls.</p>`; APP.refreshStatus(); });
    run(root, "#grant", async () => { const r = await lab("/budget", { budget_usd: Number($("#bb", root).value), asked: Number($("#ba", root).value), work: $("#bw", root).value, paper_id: $("#bp", root).value || null }); $("#g", root).innerHTML = `<div class="tiles"><div class="tile"><span>Spent</span><strong>$${r.spent_usd}</strong></div><div class="tile"><span>Reserved to finish</span><strong>$${r.reserved_usd}</strong></div><div class="tile"><span>Room</span><strong>$${r.room_usd}</strong></div><div class="tile"><span>One item costs</span><strong>$${r.each_usd}</strong></div><div class="tile"><span>Granted</span><strong>${r.granted} of ${r.asked}</strong></div></div>`; });
  },
  library: async (root) => {
    const draw = async () => {
      const s = await APP.api("/api/lab");
      root.innerHTML = panel("1. A web search, on its own", `<div class="row"><input id="q" value="context engineering for LLM agents survey" /><label><input type="checkbox" id="sch" checked /> scholarly sites only</label><button class="primary" id="search">Search</button></div><div id="r" style="margin-top:12px"></div><p class="field-help">One search through Tavily. Nothing is stored. The key column shows how the harness recognises the same paper under different links.</p>`)
        + panel("2. Fetch one page", `<div class="row"><input id="u" placeholder="paste an address from the results above" /><button class="primary" id="fetch">Fetch the text</button></div><div id="f" style="margin-top:12px"></div>`)
        + panel("3. Ask the practice library by meaning", `<div class="row"><input id="m" value="how agents compress and manage their context window" /><button class="primary" id="sim">Ask</button></div><div id="s" style="margin-top:12px"></div><p class="field-help">A vector search in SQL. Smaller distance is closer in meaning. The practice library holds ${s.sources.length} pages; a researcher in the Tools chapter stores them.</p>`);
      run(root, "#search", async () => { const r = await lab("/search", { query: $("#q", root).value, scholarly: $("#sch", root).checked }); $("#r", root).innerHTML = `<p class="faint">${r.results.length} results in ${r.seconds} s</p>` + APP.table(["score", "title", "url", "key"], r.results, (x, c) => c === "url" ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.url.slice(0, 48))}</a>` : c === "score" ? esc(Number(x.score || 0).toFixed(3)) : esc(x[c] ?? "")); if (r.results[0]) $("#u", root).value = r.results[0].url; });
      run(root, "#fetch", async () => { const r = await lab("/fetch", { text: $("#u", root).value }); $("#f", root).innerHTML = `<p class="faint">${r.chars.toLocaleString()} characters</p><pre class="console">${esc(r.start)}</pre>`; });
      run(root, "#sim", async () => { const r = await lab("/similar", { text: $("#m", root).value }); $("#s", root).innerHTML = APP.table(["distance", "title"], r.sources); });
    };
    await draw();
  },
  vocabulary: async (root) => {
    root.innerHTML = panel("Draw the vocabulary for a piece of text", `<div class="row"><input id="t" value="The agent wrapper applies context compression before each HITL gate." /><button class="primary" id="go">Draw the terms</button></div><div id="o" style="margin-top:12px"></div><p class="field-help">A vector search over the terms and their definitions. The block is what a prompt would carry. Slips are avoided words found in your text, counted without a model.</p>`);
    run(root, "#go", async () => { const r = await lab("/vocabulary", { text: $("#t", root).value }); const slips = Object.entries(r.slips); $("#o", root).innerHTML = APP.table(["distance", "term", "definition", "avoid"], r.terms, (x, c) => c === "avoid" ? esc(x.avoid.join(", ")) : esc(x[c])) + `<p style="margin-top:10px">${slips.length ? slips.map(([w, n]) => APP.pill(`${w} × ${n}`, "bad")).join(" ") : APP.pill("no avoided words in your text", "good")}</p><pre class="console">${esc(r.prompt_text)}</pre>`; });
  },
  skills: async (root) => {
    root.innerHTML = panel("1. Which skills fit this task?", `<div class="row"><input id="t" value="reading a paper that reports benchmark results for coding agents" /><button class="primary" id="go">Find skills</button></div><div id="o" style="margin-top:12px"></div><p class="field-help">The first level of disclosure: names and one-line descriptions, nearest in meaning first. This manifest is all the model sees until it asks for more.</p>`)
      + panel("2. Load one", `<div id="b"><p class="faint">Find skills first, then load one to see the second level.</p></div>`);
    run(root, "#go", async () => { const r = await lab("/skills", { text: $("#t", root).value }); $("#o", root).innerHTML = APP.table(["distance", "name", "description"], r.skills) + `<pre class="console">${esc(r.manifest)}</pre><div class="row">${r.skills.map(s => `<button class="secondary small" data-skill="${esc(s.name)}">Load ${esc(s.name)}</button>`).join("")}</div>`;
      $$("[data-skill]", root).forEach(b => b.onclick = (ev) => APP.busy(ev.currentTarget, async () => { const s = await APP.api(`/api/lab/skills/${b.dataset.skill}`); $("#b", root).innerHTML = `<p class="faint">${esc(s.name)} · ${s.chars} characters, against ${r.manifest.length} for the whole manifest</p><pre class="console">${esc(s.body)}</pre>`; })); });
  },
  tools: async (root) => {
    const s = await APP.api("/api/lab"); const defs = await APP.api("/api/lab/tools");
    const examples = { search_web: { query: "context engineering for LLM agents survey" }, read_page: { url: "https://example.org/not-from-a-search" }, load_skill: { name: "read-empirical-paper" }, recall: { source_id: s.sources[0]?.source_id || "S-0000000000", question: "how is context compacted" }, finish: { coverage: "thin", missing: ["evidence on cost"] }, take_note: { source_id: s.sources[0]?.source_id || "S-0000000000", kind: "paper", year: "2026", venue: "arXiv", contribution: "One sentence.", method: "One sentence.", evidence: "One sentence.", claims: ["One claim."], relevance: "medium" } };
    root.innerHTML = panel("1. The researcher's graph, and the tools as the model sees them", `<p class="mono" style="margin:0 0 12px">${defs.graph.map(e => `${esc(e.from)} → ${esc(e.to)}${e.chosen_at_run_time ? "?" : ""}`).join(" &nbsp;·&nbsp; ")}</p><p class="field-help" style="margin-top:0">The edges of the compiled LangGraph graph. An edge with a question mark is chosen at run time: after the agent, by whether the reply has tool calls; after the tools, by the harness.</p>` + APP.table(["name", "description", "arguments"], defs.tools, (x, c) => c === "arguments" ? esc(x.arguments.join(", ")) : esc(x[c])) + `<p class="field-help">Limits the harness enforces: ${Object.entries(defs.limits).map(([k, v]) => `${esc(k)} ${v.toLocaleString()}`).join(" · ")}.</p>`)
      + panel("2. Run one tool call by hand", `<div class="row"><select id="tn">${defs.tools.map(x => `<option>${esc(x.name)}</option>`).join("")}</select><button class="primary" id="call">Run the tool call</button></div><textarea id="ta" rows="3" style="margin-top:8px"></textarea><div id="tr" style="margin-top:12px"></div><p class="field-help">This runs the same function the harness runs for the model, and no model is called. Try read_page with a link no search returned: it is refused. Run search_web, then read_page with one of its links: the page is stored whole and only the first part comes back.</p>`)
      + panel("3. Send one researcher out", `<p class="field-help">Section: <b>${esc(s.section.title)}</b> of a paper on <b>${esc(s.subject)}</b>. The practice library holds ${s.sources.length} pages and ${s.notes} notes. One researcher takes about a minute and costs about thirty cents.</p><div class="row"><input id="q1" value="context engineering for LLM agents survey" /><input id="q2" value="agent memory management long-horizon tasks" /><button class="primary" id="go">Research</button></div><div id="o" style="margin-top:12px"></div>`);
    const fill = () => { $("#ta", root).value = JSON.stringify(examples[$("#tn", root).value], null, 1); }; fill(); $("#tn", root).onchange = fill;
    run(root, "#call", async () => { const r = await lab("/tool", { name: $("#tn", root).value, args: JSON.parse($("#ta", root).value) }); if (r.links[0]) examples.read_page = { url: r.links[0] };
      $("#tr", root).innerHTML = `<p class="faint">${r.chars.toLocaleString()} characters shown to the model · ${Object.entries(r.state).map(([k, v]) => `${esc(k)}: ${esc(typeof v === "object" ? JSON.stringify(v) : v)}`).join(" · ")}</p><pre class="console">${esc(r.shown_to_the_model)}</pre>`; });
    run(root, "#go", async () => { const r = await lab("/research", { queries: [$("#q1", root).value, $("#q2", root).value].filter(Boolean) }); const d = r.done;
      $("#o", root).innerHTML = `<div class="tiles"><div class="tile"><span>Turns</span><strong>${d.turns}</strong></div><div class="tile"><span>Pages read</span><strong>${r.pages.length}</strong></div><div class="tile"><span>Notes taken</span><strong>${d.notes}</strong></div><div class="tile"><span>Compactions</span><strong>${d.compactions}</strong></div><div class="tile"><span>Its verdict</span><strong>${esc(d.coverage)}</strong></div></div>
        <dl class="kv" style="margin-top:12px"><dt>Searches it chose</dt><dd class="mono">${d.searches.map(esc).join("<br>")}</dd><dt>Skills it loaded</dt><dd class="mono">${d.skills.map(esc).join(", ") || "none"}</dd><dt>Still missing</dt><dd>${d.missing.map(esc).join("<br>") || "nothing named"}</dd></dl>
        <h3 class="section-rule">The bill, one row per model call</h3>${callsTable(r.calls)}<p class="field-help">cache_read grows from turn to turn. A compact row is a summary taking the conversation's place: after it, cache_read starts again from a small number.</p>
        <h3 class="section-rule">Pages stored in full</h3>${APP.table(["source_id", "chars", "title"], r.pages)}
        <h3 class="section-rule">Notes taken through the take_note tool</h3>${APP.table(["relevance", "year", "kind", "title", "contribution"], r.notes, (x, c) => esc(String(x[c] ?? "").slice(0, 220)))}`; APP.refreshStatus(); });
  },
  context: async (root) => {
    const s = await APP.api("/api/lab");
    if (!s.sources.length) { root.innerHTML = APP.empty("The practice library is empty. Send a researcher out in the Tools chapter first, then come back."); return; }
    root.innerHTML = panel("1. Offloading: how much of a page stays out of the conversation", `<div class="row"><select id="src">${s.sources.map(x => `<option value="${esc(x.source_id)}">${esc(x.title.slice(0, 70))}</option>`).join("")}</select><input id="qq" value="how is the context window kept small" /><button class="primary" id="off">Show</button></div><div id="oo" style="margin-top:12px"></div><p class="field-help">The page is a row in the database. A researcher is shown the first part and a source id. The recall tool brings back the passages that best match a question.</p>`)
      + panel("2. Compaction: replace a conversation with its summary", `<button class="primary" id="cmp">Compact a small conversation</button><div id="co" style="margin-top:12px"></div><p class="field-help">The conversation holds the start of two stored pages. The harness sends it with one extra parameter and gets a summary back instead of a reply. One model call, a few cents. Compare the sizes, and the price of the call: at this size compaction keeps the window small but does not save money.</p>`);
    run(root, "#off", async () => { const r = await lab(`/offload/${$("#src", root).value}`, { text: $("#qq", root).value }); $("#oo", root).innerHTML = `<div class="tiles"><div class="tile"><span>Stored in the database</span><strong>${r.stored_chars.toLocaleString()}</strong><small>characters</small></div><div class="tile"><span>Shown to the model</span><strong>${r.shown_chars.toLocaleString()}</strong><small>characters</small></div><div class="tile"><span>Kept out of the conversation</span><strong>${r.kept_out_of_the_conversation.toLocaleString()}</strong><small>characters</small></div></div><h3 class="section-rule">Recalled for your question</h3>${r.recalled.map(e => `<pre class="console">${esc(e)}</pre>`).join("")}`; });
    run(root, "#cmp", async () => { const r = await lab("/compact"); $("#co", root).innerHTML = `<div class="tiles"><div class="tile"><span>Before</span><strong>${r.chars_before.toLocaleString()}</strong><small>characters in ${r.messages_before} messages</small></div><div class="tile"><span>After</span><strong>${r.chars_after.toLocaleString()}</strong><small>characters in one summary</small></div></div>${callsTable(r.call)}<pre class="console">${esc(r.summary)}</pre>`; APP.refreshStatus(); });
  },
  approval: async (root) => {
    root.innerHTML = panel("Plan a paper, and stop for a person", `<div class="row"><input id="sub" value="prompt caching for LLM agents" /><button class="primary" id="plan">Plan and stop</button></div><div id="gate" style="margin-top:12px"></div>`);
    const show = async (id) => { let d; for (let i = 0; i < 40; i++) { d = await APP.api(`/api/papers/${id}`); if (!d.busy) break; await new Promise(r => setTimeout(r, 2000)); }
      const asked = d.asked || {};
      $("#gate", root).innerHTML = `<p>${APP.pill(d.status, d.waiting_for_person ? "warn" : "")} checkpoints saved: <b>${d.checkpoints}</b> · spent $${Number(d.usage.cost_usd).toFixed(2)} · waiting at <span class="mono">${esc((d.next || []).join(", ") || "nothing")}</span></p>
        ${d.waiting_for_person && asked.outline ? `<h3 class="serif">${esc(asked.title)}</h3>${APP.table(["position", "kind", "title", "queries"], asked.outline, (x, c) => c === "queries" ? esc((x.queries || []).join(" · ")) : esc(x[c]))}
          <label for="gnote" style="margin-top:10px">A note for the planner</label><textarea id="gnote" placeholder="Merge the two memory sections and add one on cost."></textarea>
          <div class="row" style="margin-top:10px"><button class="secondary" data-say="revise">Revise with this note</button><button class="danger-button" data-say="reject">Reject</button></div>
          <p class="field-help">The run is not waiting in memory. It is a checkpoint in the database. Revise sends the note back to the planner and stops here again. Reject ends the run. Approving starts the full run, so that is done from Write a survey.</p>` : `<p class="field-help">This run has ended or moved on.</p>`}`;
      $$("[data-say]", root).forEach(b => b.onclick = (ev) => APP.busy(ev.currentTarget, async () => { await APP.post(`/api/papers/${id}/decide`, { decision: b.dataset.say, note: $("#gnote", root)?.value || "" }); await show(id); })); };
    run(root, "#plan", async () => { const r = await APP.post("/api/papers", { subject: $("#sub", root).value }); $("#gate", root).innerHTML = APP.empty("Planning. About twenty seconds."); await show(r.paper_id); });
  },
  durability: async (root) => {
    const papers = (await APP.api("/api/papers")).papers.filter(p => p.status !== "LAB" && p.status !== "SAMPLE");
    const rowsHtml = await Promise.all(papers.slice(0, 8).map(async p => { try { const d = await APP.api(`/api/papers/${p.paper_id}`); return { paper: p.paper_id, status: d.status, stopped_in: (d.resume_from || []).join(", "), checkpoints: `${d.checkpoints} + ${d.researcher_checkpoints || 0} of its researchers`, pages: d.sources, spent: `$${Number(d.usage.cost_usd).toFixed(2)}` }; } catch (e) { return { paper: p.paper_id, status: p.status, stopped_in: "", checkpoints: "", pages: "", spent: "" }; } }));
    root.innerHTML = panel("Runs, where they stopped, and what survived", APP.table(["paper", "status", "stopped_in", "checkpoints", "pages", "spent"], rowsHtml, (x, c) => c === "status" ? APP.pill(x.status, APP.tone(x.status)) + (x.status === "interrupted" ? ` <button class="secondary small" data-continue="${esc(x.paper)}">Continue</button>` : "") : esc(x[c])) + `<p class="field-help">An interrupted run kept its pages, its notes and its bill. Continue carries on from its last checkpoint, and a researcher that was cut off carries on from its own last step. A run cut off before this harness was changed may not continue, because its checkpoint names a step that no longer exists.</p>`);
    $$("[data-continue]", root).forEach(b => b.onclick = (ev) => APP.busy(ev.currentTarget, async () => { await APP.post(`/api/papers/${b.dataset.continue}/continue`); APP.toast("Continuing", "Follow it in Write a survey."); APP.selectPaper(b.dataset.continue); }));
  },
  notes: async (root) => {
    const s = await APP.api("/api/lab");
    root.innerHTML = panel("Reflect: is this enough?", `<p class="field-help">${s.sources.length} pages and ${s.notes} notes in the practice library. Send a researcher out in the Tools chapter first.</p><button class="primary" id="reflect">Ask which parts are thin</button><div id="v" style="margin-top:12px"></div><p class="field-help">The model sees one line per source, not the pages. Its answer is advice. In a full run the harness then checks rounds and budget before a researcher goes out again.</p>`);
    run(root, "#reflect", async () => { const r = await lab("/reflect"); const v = r.verdict; $("#v", root).innerHTML = v ? `<dl class="kv"><dt>Coverage</dt><dd>${APP.pill(v.coverage, v.coverage === "enough" ? "good" : "warn")}</dd><dt>Missing</dt><dd>${v.missing.map(esc).join("<br>") || "nothing named"}</dd><dt>Next searches</dt><dd class="mono">${v.queries.map(esc).join("<br>") || "none"}</dd></dl>${v.queries.length ? `<button class="secondary" id="again">Send a researcher out again with these gaps</button>` : ""}` + callsTable(r.call) : APP.empty("No verdict."); if (v?.queries.length) run(root, "#again", async () => { const k = await lab("/research", { queries: v.queries, missing: v.missing }); APP.toast("Second round done", `${k.pages.length} new pages, ${k.done.notes} notes`); APP.rerender(); }); });
  },
  memory: async (root) => {
    const list = (rows) => APP.table(["kind", "distance", "content", "memory_id"], rows);
    root.innerHTML = panel("1. Remember", `<div class="row"><select id="kind"><option>preference</option><option>guideline</option><option>fact</option></select><input id="c" value="Always include a section on evaluation, and name the benchmarks." /><button class="primary" id="rem">Remember</button></div><div class="row" style="margin-top:8px"><input id="rep" placeholder="memory_id this one replaces (optional)" /><button class="danger-button small" id="forget">Forget this reader</button></div><p class="field-help">Leave the second box empty to add. Paste a memory_id from the table to correct that memory: the new one is linked to it as "supersedes" and the old one is marked invalid.</p>`)
      + panel("2. Recall", `<div class="row"><input id="q" value="a survey on agent harness engineering" /><button class="primary" id="rec">Recall</button></div><div id="m" style="margin-top:12px"></div><p class="field-help">Only this reader's memories, only valid ones, and no more than 600 tokens of them.</p>`);
    run(root, "#rem", async () => { const r = await lab("/remember", { content: $("#c", root).value, kind: $("#kind", root).value, replaces: $("#rep", root).value.trim() || null }); APP.toast(r.stored ? "Remembered" : "Already remembered", r.memory_id); $("#m", root).innerHTML = list(r.memories); $("#rep", root).value = ""; });
    run(root, "#rec", async () => { $("#m", root).innerHTML = list((await lab("/recall", { text: $("#q", root).value })).memories); });
    run(root, "#forget", async () => { await lab("/forget"); $("#m", root).innerHTML = list([]); });
  },
  planner: async (root) => {
    root.innerHTML = panel("Plan a paper", `<div class="row"><input id="s" value="context engineering for coding agents" /><button class="primary" id="plan">Plan</button></div><div id="p" style="margin-top:12px"></div><p class="field-help">One model call, a few cents. Nothing is searched or read.</p>`);
    run(root, "#plan", async () => { const r = await lab("/plan", { text: $("#s", root).value }); $("#p", root).innerHTML = `<h3 class="serif">${esc(r.plan.title)}</h3><p class="faint">Recalled from memory and given to the planner: ${r.remembered.length ? r.remembered.map(m => esc(m.content)).join(" · ") : "nothing. Store a preference in the memory chapter and plan again."}</p>` + APP.table(["kind", "title", "purpose", "queries"], r.plan.sections, (x, c) => c === "queries" ? esc(x.queries.join(" · ")) : esc(x[c])) + callsTable(r.call); APP.refreshStatus(); });
  },
  writer: async (root) => {
    const s = await APP.api("/api/lab");
    root.innerHTML = panel("1. Is a quote really on a page?", `<label>Page</label><textarea id="pg" rows="3">In our study the harness raised task success from 41% to 58% on SWE-bench Verified. Compaction cut token use by a third.</textarea><div class="row" style="margin-top:8px"><input id="qt" value="the harness raised task success from 41% to 58%" /><button class="primary" id="quote">Check</button><span id="qo"></span></div><p class="field-help">No model is involved. Words are compared in order, ignoring case, spacing and punctuation. Change a number in the quote and check again.</p>`)
      + panel("2. Find the cited claims in a draft", `<textarea id="dr" rows="3">A loop helps agents recover from errors [S-aa11]. It also costs more tokens [S-bb22][S-cc33]. This sentence cites nothing.</textarea><div class="row" style="margin-top:8px"><button class="primary" id="split">Split into claims</button></div><div id="cl" style="margin-top:12px"></div>`)
      + panel("3. The excerpts a source would travel with", `<div class="row"><select id="src">${s.sources.map(x => `<option value="${esc(x.source_id)}">${esc(x.title.slice(0, 70))}</option>`).join("")}</select><button class="primary" id="exc" ${s.notes ? "" : "disabled"}>Choose excerpts</button></div><div id="ex" style="margin-top:12px"></div><p class="field-help">For each thing the note says the page shows, the harness picks the passage that shares the most uncommon words with it. No model is asked. These passages are what the writer may rely on.</p>`)
      + panel("4. Write the practice section, and check it", `<p class="field-help">Needs notes: ${s.notes} so far. This builds a small framework, writes the section from excerpts of the stored pages, checks every cited claim, repairs once and removes what still fails. About a minute and thirty cents.</p><button class="primary" id="write" ${s.notes ? "" : "disabled"}>Write and check the section</button><div id="w" style="margin-top:12px"></div>`);
    run(root, "#quote", async () => { const r = await lab("/quote", { quote: $("#qt", root).value, page: $("#pg", root).value }); $("#qo", root).innerHTML = APP.pill(r.on_the_page ? "on the page" : "not on the page", r.on_the_page ? "good" : "bad"); });
    run(root, "#split", async () => { const r = await lab("/claims", { text: $("#dr", root).value }); $("#cl", root).innerHTML = APP.table(["n", "source_ids", "text"], r.claims, (x, c) => c === "source_ids" ? esc(x.source_ids.join(", ")) : esc(x[c])); });
    run(root, "#exc", async () => { const r = await APP.api(`/api/lab/excerpts/${$("#src", root).value}`); $("#ex", root).innerHTML = `<p class="faint">What the note points at: ${r.pointers.map(esc).join(" · ").slice(0, 400)}</p>` + r.excerpts.map((e, i) => `<pre class="console">Excerpt ${i + 1}: ${esc(e)}</pre>`).join(""); });
    run(root, "#write", async () => { const r = await lab("/write"); const x = r.result; $("#w", root).innerHTML = `<div class="tiles"><div class="tile"><span>Words</span><strong>${x.words}</strong></div><div class="tile"><span>Claims checked</span><strong>${x.claims}</strong></div><div class="tile"><span>Sent for repair</span><strong>${x.repaired}</strong></div><div class="tile"><span>Removed by the harness</span><strong>${x.removed}</strong></div></div>` + callsTable(r.calls) + APP.table(["n", "verdict", "on_page", "outcome", "claim", "quote"], r.claims, (y, c) => c === "on_page" ? APP.pill(y.on_page ? "found" : "not found", y.on_page ? "good" : "bad") : esc(String(y[c] ?? "").slice(0, 200))) + `<pre class="console">${esc(r.draft)}</pre>`; APP.refreshStatus(); });
  },
  review: async (root) => {
    if (!APP.paper.id) { root.innerHTML = ""; return; }
    root.innerHTML = panel("Run the release check now", `<button class="primary" id="rel">Count</button><div id="ro" style="margin-top:12px"></div><p class="field-help">Six facts read from the tables. No model is called, so it costs nothing and can be run at any point in a paper's life.</p>`);
    run(root, "#rel", async () => { const r = await APP.api(`/api/papers/${APP.paper.id}/release`); $("#ro", root).innerHTML = `<p>${APP.pill(r.verdict, r.verdict === "READY" ? "good" : "bad")} referee: ${esc(r.referee)} · spent $${r.spent_usd}</p>` + APP.table(["check", "passed", "detail"], r.checks, (x, c) => c === "passed" ? APP.pill(x.passed ? "pass" : "fail", x.passed ? "good" : "bad") : esc(x[c])); });
  },
};

/* ── new chapters, the order of the notebook, and the frame around every chapter ───────── */
const blank = async (root) => { root.innerHTML = ""; };
[["foundation", "Foundation: the database"], ["state", "State store: where the work is kept"], ["gateway", "Model gateway and cost control"],
 ["vocabulary", "Vocabulary: the semantic layer"], ["skills", "Skills, loaded when needed"], ["tools", "Tools: a researcher"],
 ["context", "Context management: offloading and compaction"], ["approval", "Human approval"], ["durability", "Durability"],
 ["memory", "Memory between papers"], ["planner", "Planner"], ["writer", "Writer and verifier"]].forEach(([id, title]) =>
  APP.register({ id, title, blurb: "", render: blank }));
const ORDER = ["paper", "refarch", "foundation", "state", "gateway", "library", "vocabulary", "skills", "tools", "context", "notes", "memory", "planner", "writer", "review", "architecture", "approval", "durability", "ledger", "read"];
const TITLES = { library: "Evidence store", notes: "Research loop: reflect and decide", review: "Quality gate", architecture: "Orchestration: the graph", ledger: "Observability: ledger and cost" };
APP.chapters.sort((a, b) => ORDER.indexOf(a.id) - ORDER.indexOf(b.id));
APP.chapters.forEach((chapter, index) => {
  chapter.n = index || undefined;
  chapter.title = TITLES[chapter.id] || chapter.title;
  const inner = chapter.render, f = FRAMES[chapter.id];
  if (!f) return;
  chapter.blurb = "";
  chapter.render = async (root) => {
    root.innerHTML = frame(f) + `<div class="lab"></div><div class="full"></div>`;
    const tasks = [];
    if (LABS[chapter.id]) tasks.push(LABS[chapter.id]($(".lab", root)).catch(error => { $(".lab", root).innerHTML = APP.fail(error); }));
    if (inner !== blank) {
      if (LABS[chapter.id]) $(".full", root).insertAdjacentHTML("beforebegin", `<h2 class="section-rule">In a full paper</h2>`);
      tasks.push(inner($(".full", root)));
    }
    await Promise.all(tasks);
  };
});
