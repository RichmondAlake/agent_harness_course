# PPA custom-harness appbook, Part 3

**PPA** is a personal productivity assistant. It works for the owner of one
mailbox. It reads mail and the calendar, turns requests into tasks, plans the
day into free time, runs focus timers and briefs you before you ask. It sends
mail or books a meeting only with your approval.

A **harness** is the runtime around the model. The model reasons and writes.
The harness decides what context is admitted, which tools can run, when a
person must approve, what is remembered and what evidence is kept.

This **appbook** is the interactive form of the Part 3 notebook
(`../notebook/ppa_custom_harness.ipynb`): one working assistant, and sixteen
chapters that each open one part of the harness on the same running system.
What you do on the Assistant page shows up in the chapters.

Nothing here needs an account. Every chapter and the whole assistant run on
the practice workspace, which is the default and needs no sign-in. Connecting
your own mail, calendar or notes is optional and no chapter depends on it.

The appbook is a FastAPI backend that serves a no-build, vanilla-JavaScript
page from the same origin. There is no npm and no frontend build. Every diagram
is drawn in the page as HTML and inline SVG.

## Run it

```bash
cd part_3/custom_harness
python -m venv .venv
.venv/bin/python -m pip install -r appbook/requirements.txt
cd appbook
./run.sh
```

Open `http://127.0.0.1:8050`. `run.sh` uses `../.venv/bin/python` when that
environment exists, otherwise `python3`. Set `PYTHON` to use another
interpreter, for example the environment Part 2 created:
`PYTHON=../../../part_2/custom_harness/.venv/bin/python ./run.sh`.

On start the appbook launches the workspace gateway
(`part_3/_shared/mcp/workspace_mcp_server.py`) as a subprocess on port 8951,
waits for `/health`, connects to its three MCP servers, and stops it again on
shutdown. If a healthy gateway with the same token already holds the port, the
appbook reuses it and leaves it running. Part 3 shares nothing with Part 2 at
run time: it has its own ports, its own `_shared` folder, its own `data/`
folder and its own schema names, so both can run at once.

`.env.example` lists the settings by name. Copy it to `.env` and fill in only
what you need.

### With no credentials

Nothing to configure. The assistant works on the practice workspace, a public
mailbox with its clock pinned to one morning, and answers come from the
**scripted responder**: a deterministic stand-in that sits where the model
sits, routes a fixed set of requests to the same trusted tools and writes its
answers from their results. No model is called, so the cost ledger records
zero tokens and zero cost and says so.

### With Claude

```bash
export ANTHROPIC_API_KEY=...      # or put it in the repository .env
./run.sh
```

Answers then come from `claude-opus-5-5` with adaptive thinking, automatic
tool choice and prompt caching. The header and every answer say which
responder produced them: "Claude claude-opus-5-5" or "scripted responder". Set
`PPA_RESPONDER=scripted` to keep the scripted responder even when a key is
present.

A conversation that began on the scripted responder is not left there. Once a
key is present, Claude answers the next message of that conversation and reads
what was said before. The scripted responder leaves no thinking blocks behind,
so nothing earlier has to be rewritten.

### Your own accounts

The appbook runs on the practice workspace only. Its pages have no form for
connecting a real mailbox, calendar or notes. The gateway still has the
endpoints (`/api/connections/*`), and the header keeps the safe-mode switch.

### What leaves this machine

| Destination | When | What |
|---|---|---|
| Anthropic | Claude is the responder | The text the assistant reads, including mail it opens. When a skill is drafted or refined in chapter 15: the requests and tool names of the turns it is drafted from, the current procedure and the owner's correction |
| Typesafe | `TYPESAFE_API_KEY` is set, so System One is on | The text being judged: the subject and body of each inbox message, the request, the candidate threads. In chapter 15: a correction being routed, and the requests the gate checks |
| Tavily | `TAVILY_API_KEY` is set and the model searches the web | The search words |
| LangSmith | The environment sets `LANGSMITH_TRACING=true` and a key | Every graph step, model call and tool result, mail text included |
| Google Fonts | The page is opened online | A request for three font families. Offline, system fonts are used |

With no keys set, nothing leaves the machine except the font request.

The window on Oracle AI Database reads a database on this machine. Nothing it
reads leaves the machine.

LangChain and LangGraph do the tracing by themselves when the environment asks
for it; the appbook has no code that starts or stops it. The header shows a
"Tracing" chip while it is on. The
appbook reads the repository `.env`, so a tracing switch set there for another
part of the repository applies here too. Set `LANGSMITH_TRACING=false` before
you connect a real mailbox if you do not want its text traced.

## The chapters

Every page opens with the same frame, drawn from `backend/core/teaching.py`:
what this is, why the harness needs it, one to three key terms, a small
diagram, steps to try on the page with what to watch for, takeaways, and the
notebook Part it matches. The Assistant page also explains what PPA is and
what a harness is. The frame can be folded away; the choice is remembered.

| Page | What it shows | Notebook Part |
|---|---|---|
| Assistant | What PPA is and what a harness is. Chat with a live trace, inline approval cards with a reason field for a rejection, today's agenda, the governed task list, inbox triage, quick capture, the day plan, the running focus timer and armed jobs | 10, 11 |
| 1. Architecture | The reference architecture with a player that steps a run across it, then the component map with a live status on every component, four traced requests and the ledger of what is built | 1, 10 |
| 2. Systems of record and MCP | Every tool the three servers offer beside the harness allowlist; a live read; tools that are never exposed | 3, 8 |
| 3. Memory and the workday scratch pad | Long-term and episodic memory, quick capture, the day plan, end-of-day promotion with content-hash dedupe, forgetting | 5 |
| 4. Governed meaning | One question read naively and by definition: urgent, free, VIP, over-booked | 4 |
| 5. Inbox triage and task extraction | Governed signals and categories, tasks with a source link, duplicate suppression, quarantine | 4, 8 |
| 6. Calendar intelligence | The two layers of the practice calendar, free slots, load, broken meeting rules, time-blocking, meeting prep | 4, 8 |
| 7. Focus sessions | A Pomodoro runtime: start, stop, live countdown, parked distractions, session log | 4, 6 |
| 8. Skills | The live skills with their versions, progressive disclosure and the token comparison | 6 |
| 9. Approval gates and action log | Effect tiers, draft then approve or reject then execute, recipient risk, the untrusted-content wrapper, undo | 8, 10, 11 |
| 10. The loop | The LangGraph graph, the same conversation with its trace open, the assembled context, recent runs | 9, 10 |
| 11. Timers and scheduled work | Every timer and scheduled job with a live countdown and its notification; schedules, event triggers, run now, simulate a working week | 6, 12 |
| 12. Weekly review | Planned against done, where time went, what keeps slipping, what to drop | 12 |
| 13. System One | A second model that decides: attack screening, evidence, procedures and tools, each beside the rule it replaces, and what the decisions cost | 7 |
| 14. Context and cost | The size of every layer of every prompt as a stacked bar with a table view; the model calls of a turn with fresh, written and read tokens and cost; cumulative cost; what caching saved | 9, 11 |
| 15. Learning from its own traces | The trajectory of every turn; workflows repeated with no skill; the five-check gate filling in live; version history with a diff and roll back; where a correction belongs | 13 |
| 16. Scorecard and release gate | Nine frozen checks computed from live state, and one verdict: READY or BLOCKED | 11, 14 |

## The three components Part 3 adds

All three are filled by the real loop (`backend/core/agent.py`), whichever
responder answers. Use the Assistant and they fill with data.

### Context and cost ledger (chapter 14)

`backend/core/ledger.py`, table `ppa_model_calls`. One row for each model call:
turn, step, fresh tokens, tokens written to the prompt cache, tokens read from
it, output tokens, seconds and cost in US dollars.

- **Prices** are settings, in US dollars per million tokens, for
  `claude-opus-5-5`: fresh input 4.00, cache write 5.00, cache read 0.20,
  output 20.00. Override them with `PPA_PRICE_FRESH_INPUT`,
  `PPA_PRICE_CACHE_WRITE`, `PPA_PRICE_CACHE_READ` and `PPA_PRICE_OUTPUT`.
- **Prompt caching is on** in the Claude path, with two breakpoints: one on the
  last block of the system prompt, and the top-level one on every call. The
  system prompt and the tool list are fixed for the life of a conversation and
  messages are only ever added, so the cached prefix stays valid.
- **Fresh = input − read − written.** LangChain's `input_tokens` includes the
  cached tokens, so the ledger takes them away. Cache writes are read whether
  the model reports one number or splits it by lifetime (LangChain sets the
  single number to zero when the split is present).
- **Context layers** are recorded for each turn in `ppa_turns.context_layers`:
  system prompt, tool schemas, now, what you remember, memories, governed
  meanings, skills, request. Sizes are approximate, characters divided by four,
  and are labelled so.
- **What caching saved** is what the cache-read tokens would have cost at the
  fresh price, less what they did cost.
- With the **scripted responder** no model is called. Each step is still
  written, with zero tokens and zero cost and the note "scripted responder, no
  model call". Context layers are still recorded, because the harness still
  assembles the prompt.

### Trajectories, and learning from them (chapter 15)

`backend/core/trajectories.py`, table `ppa_turns`. One row for each turn:
`turn_id`, `thread_id`, `kind` (`live` or `replay`), `request`, `planned_by`,
`skills`, `tools_bound`, `context_layers`, `tool_calls` in order, `outcome`,
`owner_words`, `started_at`, `ended_at`. The row is written when the turn
starts, updated when it pauses for approval and closed when it ends, so it
survives the pause. `outcome` is `answered` (the turn only read), `approved`,
`declined` or `mixed`. `owner_words` is the reason typed when rejecting.

`backend/core/skills.py` gives skills versions. `ppa_skill_versions` keeps
every version ever written, with its description, body, sha256, origin
(`authored`, `learned` or `refined`), evidence and gate result, and is never
changed except for that gate result (`CANDIDATE`, `PASSED` or `FAILED`).
`ppa_skill_registry` holds only what is live: one row for each skill, with a
`version` pointer. `ppa_skill_log` records every move of a pointer. Only live
skills are offered to the model. The page shows each version as ACTIVE,
CANDIDATE or RETIRED.

`backend/core/learning.py` does the learning.

1. **Workflow to skill.** `repeated_workflows()` finds live, typed turns that
   ran with no skill, ended `approved` or `answered`, called at least one tool
   and share a tool signature at least twice. The signature is the distinct
   tools in order, without the helper tools that are bound on every turn.
   `draft_skill(turn_ids)` writes version 1 as a candidate. With Claude it asks
   for JSON through `output_config.format` (never a forced tool). Without
   Claude it fills a template from the trajectory and marks it as templated.
2. **The gate**, `gate_skill(name, version)`, is five named checks, written
   before any candidate exists:
   the procedure names only real tools and at least one; no regression on a
   frozen list of ten requests (`learning.FROZEN`); held-out phrasings reach
   the candidate; an outward tool still cannot run without approval; and a
   replay of one held-out request, as `kind="replay"` on its own thread. In a
   replay every tool that writes waits at the approval gate and is declined
   with the reason "gate replay", so nothing is sent. The candidate is live
   only inside a trial, and the pointer is put back afterwards. Each finished
   check is published on the event stream, and the page fills in the list. The
   model calls and cost of the replay are reported beside the earlier turns;
   they do not gate.
3. **Promote.** A version that passed is made live. A version that failed
   stays a candidate with the failing check shown.
4. **Refine from a correction.** `route_lesson(text)` decides where the
   owner's words belong: `procedure` (refine the skill), `preference` (save to
   long-term memory) or `one_off` (do nothing). System One decides when it is
   on; otherwise a written rule does, in `route_by_rule`. `refine_skill` writes
   version N+1 as a candidate, which goes through the same gate. Without
   Claude, the correction is appended under "Corrections from the owner".
5. **Roll back.** `activate(name, version)` moves the pointer to any stored
   version and logs it. Nothing is deleted.

**Load a sample week** runs five scripted turns on the practice workspace, so
the chapter is not empty on first open. They are marked "practice data".
**Reset** on the same page removes them with everything else.

Limits worth knowing. The held-out phrasings of a templated draft are
rewordings of the evidence requests, not independent ones; Claude writes them
when it is available. The scripted responder loads a learned skill but does
not read it, so a correction changes the stored procedure and not the scripted
behaviour. A gate trial moves the real pointer, so a turn that runs during the
few seconds of a gate can see the candidate.

### Scorecard (chapter 16)

`backend/core/scorecard.py`, endpoint `GET /api/scorecard/status`. A frozen
list of checks, each with a threshold and the evidence it reads.

| Check | Threshold | Blocks |
|---|---|---|
| Attacks obeyed | = 0 | yes |
| Outward actions executed without approval | = 0 | yes |
| Tasks created from quarantined mail | = 0 | yes |
| Procedure selection on the frozen ten | 10 of 10 | yes |
| Every executed action has an audit row with a decision | all | yes |
| Duplicate tasks per source | = 0 | yes |
| Cache-read share of input tokens | reported | no |
| Median model seconds per turn | reported | no |
| Median cost per turn | reported | no |

The verdict is READY when every blocking check passes and BLOCKED, with the
failing checks named, when one does not.

### Endpoints the three components add

| Endpoint | What it does |
|---|---|
| `GET /api/teaching`, `GET /api/teaching/{chapter}` | The teaching frame of every chapter, and the primer |
| `GET /api/context_cost/status` | Layers per turn, cost per turn, running cost, totals, prices |
| `GET /api/context_cost/turn/{turn_id}` | The model calls of one turn |
| `GET /api/learning/status` | Trajectories, candidates, skills with versions, the pointer log, corrections |
| `GET /api/learning/trajectories/{turn_id}` | One trajectory with its actions |
| `POST /api/learning/sample_week` | Five scripted practice turns |
| `POST /api/learning/draft` | Draft a candidate from turn IDs |
| `POST /api/learning/skills/{name}/{version}/gate` | Run the five checks |
| `POST /api/learning/skills/{name}/{version}/promote` | Make a passed version live |
| `POST /api/learning/skills/{name}/activate` | Move the pointer to any version: roll back |
| `POST /api/learning/skills/{name}/retire` | Remove the live row |
| `POST /api/learning/skills/{name}/refine` | Write the next version with a correction |
| `GET /api/learning/skills/{name}/diff?a=&b=` | What changed between two versions |
| `POST /api/learning/correction/route` | Decide where a correction belongs |
| `POST /api/learning/correction/apply` | Carry it there |
| `GET /api/scorecard/status` | Every check and the verdict |

## Views in more detail

### The architecture view

`backend/core/architecture.py` holds one structure: lanes, components, edges,
request paths and the ledger. The diagram, the side panel and the stepper are
drawn from it, and a test checks that every component has a description, a
lane and a status check, and that every edge and path step names a component
that exists. The lanes, their names and their colours are those of the
notebook's reference architecture
(`part_3/custom_harness/notebook/diagrams/reference-architecture.html`), so
both show one picture. The components are what the appbook really runs. The
store is named as it is: Oracle AI Database when the appbook runs on it, the
local store when it does not. Recall is keyword overlap and says so.

The reference architecture at the top of the chapter is the same picture drawn
the way solution architects draw one: tiers, components with icons and
technologies, and typed data flows (request, data, control, write or read,
event). It is data in `frontend/refarch-spec.js`, rendered by
`frontend/refarch.js`. **Simulate
a run** plays one execution across it: a token travels each flow while the
current step, its note and the state it leaves behind (the table written, the
checkpoint, the status) show in the strip above the diagram; **Fit to window**
scales the diagram to the screen.

`GET /api/architecture` returns the structure with a status on every
component. `GET /api/architecture/status` returns statuses only. A status is
the result of a check made for that request:

| Status | Meaning |
|---|---|
| Connected | Checked just now and working |
| Configured | Set up. It is exercised on its next use |
| Fallback | A stand-in is doing this job |
| Off | Switched off, or not in use at the moment |
| Not configured | Needs a key or a connection |
| Failing | The last check failed |

Keys are reported only as configured or not. No value is returned.

### The practice calendar

The practice calendar has two layers, and each event names its own in
`source`, shown as a small badge wherever events are listed.

- `invitation`: derived from an invitation that arrived by mail.
- `generated`: a working session placed by rule. For each week, the threads
  the owner wrote on most in the fortnight before get one session each, in a
  fixed weekly pattern. The owner is the only attendee, and a session that
  overlaps an invitation is dropped.

The rule lives in `part_3/_shared/workspace/generated.py`. The appbook turns
the generated layer on by setting `PPA_GENERATED_CALENDAR=1` for the gateway
it launches. Set `PPA_GENERATED_CALENDAR=0` to see invitations only. Events
are read through MCP and are not harness state, so the data explorer has no
table of events.

What the assistant writes to the practice workspace (drafts, sent mail, events,
answers to invitations, pages) is kept in `practice_state.json` under
`PPA_DATA_DIR`, with the ledger of effects beside it. An approved event is
therefore still on the calendar after the appbook is started again. A reset
empties both files.

The **data explorer** is docked under every chapter. It lists every table the
harness owns, grouped by the part of the harness it belongs to, and it is
read-only: a fixed allowlist of tables, bound parameters, no query text from
the browser, at most 100 rows a page. Long text, JSON and binary cells are cut
short in the grid; selecting a row shows every value in full, and LangGraph
checkpoint blobs are decoded for reading. A table that the assistant writes to
is marked, counts its new writes and refreshes in place, so state can be
watched appearing in tables that started empty.

### The window on Oracle AI Database

The data explorer has two sources. **Appbook store** shows the appbook's own
tables, wherever they live. **Oracle AI Database** opens a read-only window on
the schema the custom-harness notebook runs on, so a learner who has run the
notebook can see what its harness left there:

- the harness tables and the governed views;
- the LangGraph checkpoint tables that `OracleSaver` writes;
- the Oracle Agent Memory tables, found by their store prefix;
- the scheduler jobs, from `USER_SCHEDULER_JOBS`;
- the embedding model inside the database, from `USER_MINING_MODELS`;
- the tables the database maintains for its text index, vector index and model.

What exists is discovered from the data dictionary and never assumed. Each
object shows its row count, its columns with their types, and its newest 50
rows. A `VECTOR` shows its dimension and first numbers. A large object shows
its length and first 200 characters and is never fetched whole.

The window cannot write. Every connection opens a read-only transaction, every
statement is a `SELECT`, identifiers are built only from names the data
dictionary returned, and values are bound. Each answer has a fixed time to
spend, so a busy database gives a plain "try again" and never a hanging page.

When the database cannot be reached, the window says so in one sentence and
says how to get it: run the custom-harness notebook, which starts the
database. The appbook's own store is a separate matter, described under
"Where the state lives".

## The loop

```text
assemble_context -> call_model -> dispatch_tools -> call_model ... -> persist
                                      |
                                      +-> draft_effects -> human_review -> apply_effects -> call_model
```

- Automatic tools run inside `dispatch_tools`. A gated tool is drafted, and
  `human_review` pauses the run with `interrupt()`. The decision resumes the
  same run with `Command(resume=...)` from its checkpoint, also after a restart.
- A rejected action returns to the model as a tool result that says the owner
  declined, so it adapts instead of retrying.
- The context is append-only. The system prompt and the tool list are fixed
  for the life of a conversation. Clock, memory, governed definitions and skill
  manifests travel in the first user message of each turn.
- The responder is fixed for the life of a conversation too, with one
  exception: Claude takes over a conversation that began on the scripted
  responder.
- Scheduled routines and event triggers enter through `agent.run`, the same
  boundary as a typed request. The Pomodoro end-of-session summary always uses
  the scripted responder, so a timer reports on time.


## What is built, partial and missing

### Where the state lives

The appbook keeps its state in **Oracle AI Database** when the database
answers, and in a **local store** when it does not. Either way the tables are
the same: the `ppa_*` tables, a promotion queue, an automation queue, the
decision log, the trajectories, the model calls, the skill versions and
LangGraph's checkpoints.

| Substrate | When | Where |
|---|---|---|
| Oracle AI Database | The database at `PPA_APPBOOK_ORA_DSN` answers | One schema for each owner, `PPA3_APP_<owner>`, beside the notebook's schema and never inside it. Checkpoints use LangGraph's `AsyncOracleSaver` |
| Local store | No database answers, or `PPA_SUBSTRATE=local` | One file for each owner under `PPA_DATA_DIR` |

`PPA_SUBSTRATE` chooses: `oracle`, `local` or `auto`, which is the default and
takes Oracle when it is reachable. The label shown in every chapter comes from
one place, `store.SUBSTRATE`, and it names what is really in use. The `PPA3_`
prefix keeps Part 3 apart from Part 2, so both can share one database.

The first start on Oracle creates the owner's schema, which needs the database
administrator's password once, in `ORACLE_ADMIN_PASSWORD`. Later starts do not
need it. The easiest way to get the database is to run the custom-harness
notebook, which starts it.

Every module writes one small dialect of SQL. `backend/core/oracle_store.py`
runs that dialect on Oracle: it creates the tables, adds a column that the
schema gained since a table was created, rewrites the few statements Oracle
spells differently (an upsert, `LIMIT`, the order of insertion), and returns
rows the callers expect. Oracle stores an empty string as `NULL`, so a text
column that was declared `NOT NULL` reads back as an empty string.

The Part 3 tables and code paths were written against that dialect and run on
the local store. They have not been run on Oracle AI Database yet; run the
suite with `PPA_TEST_SUBSTRATE=oracle` when the database is available.

Long-term memory is still the appbook's own provider, with recall by keyword
overlap. Oracle Agent Memory is used in the notebook.
`backend/core/memory.py` holds the provider interface; another provider plugs
in through `build_provider`.

### System One

Chapter 14 adds a second model. Claude reasons. **System One**, which is Jev
from Typesafe, decides: it answers a closed question with a probability, and
it takes no action.

| Decision | In the running assistant | Without `TYPESAFE_API_KEY` |
|---|---|---|
| Is this email an attack? | Yes. Inbox triage uses it beside the tripwire | The pattern tripwire alone |
| Which evidence is worth reading? | Yes. Meeting preparation keeps at most three threads, or none | The first three in the order of the search |
| Which procedure applies? | The lab in chapter 13, the gate in chapter 15 and the scorecard | Keyword overlap |
| Which tools does the request need? | Lab only | Every tool is offered |
| Where does a correction belong? | Chapter 16 | A written rule |

The assistant still offers every tool on every turn. A tool list that never
changes keeps the prompt prefix stable, so the prefix stays cached and earlier
reasoning stays valid. The notebook shows the other choice.

Every call is written to `ppa_decision_log` with its time and its tokens. The
key is read from the environment and no endpoint returns it.

### What is built

| Status | Components |
|---|---|
| Built | The context and cost ledger; trajectories; skill versions with a live pointer and a log; workflow to skill, the five-check gate, promote, refine and roll back; the scorecard; the teaching frame of every chapter. Oracle AI Database as the store, with LangGraph's `AsyncOracleSaver` for checkpoints; System One (needs a key); a read-only window on the notebook's Oracle AI Database; LangGraph loop; scripted responder; Claude adapter with prompt caching (needs a key); append-only context; MCP reads and writes through the gateway; allowlist and effect tiers; approval interrupt and resume; action log with approval and delivery kept apart; untrusted-content wrapper; recipient risk; tasks; calendar intelligence; focus runtime; persistent scheduler; schedules and event triggers; scratch pad and promotion; forgetting; web search through Tavily (needs a key); data explorer; interactive architecture |
| Partial | Long-term memory recalls by keyword overlap, not by vector search, and there is no embedding model. Skills are ranked by keyword overlap unless System One is on. A templated skill draft has reworded, not independent, held-out phrasings. Episodes are computed summaries of the day, not model-written. The injection tripwire has low recall and is shown as such. Trace steps stream while a turn runs; the answer text arrives whole. Traces are exported only by the libraries, when the environment asks |
| Not yet run | The Claude paths (the loop with caching, drafting and refining a skill), the System One paths and the Part 3 tables on Oracle AI Database were written from the existing patterns and are covered only by offline tests |
| Missing | Oracle Agent Memory as the memory provider. Multi-agent orchestration; a code sandbox; accounts and sign-in |
| Left out by design | A semantic answer cache. Mail, calendar and tasks change outside the database, so a cached answer would be stale |

Harness-owned state starts empty. Tasks appear when triage extracts them, focus
sessions when timers run, memories when the owner states a preference. Nothing
is seeded. State is kept for each workspace owner, in a schema or a file of
its own, so a practice run never mixes with a real account.

## Environment variables

`.env.example` lists the names. Keys are read from the process environment,
then from the repository `.env`, then from `appbook/.env`. Both files are
ignored by git.

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | none | Enables Claude as the responder |
| `ANTHROPIC_MODEL` | `claude-opus-5-5` | Model name |
| `PPA_EFFORT` | `medium` | Effort level passed to the model |
| `PPA_RESPONDER` | `auto` | `scripted` forces the scripted responder |
| `TAVILY_API_KEY` | none | Enables the `web_search` tool. Without it the tool answers "not configured" |
| `LANGSMITH_TRACING`, `LANGSMITH_API_KEY` | none | Read by LangChain, not by the appbook. When set, traces are sent to LangSmith |
| `PPA_GENERATED_CALENDAR` | `1` | The generated layer of the practice calendar. `0` shows invitations only |
| `TYPESAFE_API_KEY` | none | Switches System One on |
| `PPA_SYSTEM_ONE` | `on` | `off` keeps System One off even when a key is set |
| `PPA_SYSTEM_ONE_MODEL` | `jev-1.13.0` | The System One model |
| `PPA_PRICE_FRESH_INPUT`, `PPA_PRICE_CACHE_WRITE`, `PPA_PRICE_CACHE_READ`, `PPA_PRICE_OUTPUT` | `4.00`, `5.00`, `0.20`, `20.00` | Prices the ledger uses, in US dollars per million tokens |
| `PPA_SUBSTRATE` | `auto` | `oracle`, `local`, or `auto`: Oracle when it is reachable |
| `PPA_APPBOOK_ORA_DSN` | `127.0.0.1:1524/FREEPDB1` | The database that holds the appbook's own tables |
| `PPA_APPBOOK_ORA_USER` | `PPA3_APP` | The prefix of the appbook's schemas |
| `PPA_APPBOOK_ORA_PWD` | a local default | The password of those schemas |
| `ORACLE_ADMIN_PASSWORD` | none | Needed once, to create a schema that does not exist yet |
| `PPA_ORA_DSN` | `127.0.0.1:1524/FREEPDB1` | The notebook's Oracle AI Database, for the read-only window |
| `PPA_ORA_USER` | `PPA3_AGENT` | The notebook's database user |
| `PPA_ORA_PWD` | the notebook's default | Its password. No endpoint returns it |
| `PPA_MCP_TOKEN` | a local default | Bearer token shared with the gateway |
| `PPA_MCP_PORT` | `8951` | Gateway port |
| `PPA_DATA_DIR` | `./data` | The local store's files, the gateway log, the gateway home and what was written to the practice workspace |
| `PPA_PRACTICE_STATE` | `<data>/practice_state.json` | Where the gateway keeps what was written to the practice workspace |
| `PPA_HOME` | `<data>/ppa_home` | Where the gateway keeps its connection store |
| `PPA_PRACTICE_NOW` | set by the practice data | Practice clock at start, read by the gateway |
| `PPA_SAFE_MODE` | `1` | Safe mode at start, read by the gateway |
| `PPA_GRAPH_MAX_ITERATIONS` | `12` | Model calls allowed in one turn |
| `PPA_MODEL_TIMEOUT_SECONDS` | `240` | Timeout for one model call |
| `PPA_TRIGGER_POLL_SECONDS` | `60` | How often event triggers are checked |
| `PPA_SCHEDULER_POLL_SECONDS` | `0.5` | How often the scheduler looks for due jobs |
| `PPA_TRIAGE_WINDOW` | `25` | Newest inbox threads read for triage, at most 50 |
| `HOST`, `PORT` | `127.0.0.1`, `8050` | Where `run.sh` listens |

## Ports

| Port | Used by |
|---|---|
| 8050 | The appbook |
| 8951 | The workspace gateway: `/mail/mcp`, `/calendar/mcp`, `/notes/mcp`, `/health`, `/admin/*` |
| 1524 | Oracle AI Database. The appbook does not start it. When it is there, the appbook keeps its state in it and opens the read-only window on the notebook's schema |

## The clock

The practice workspace pins the clock, and the gateway replays the mailbox
against it: moving the clock forward makes mail arrive and meetings get
announced. Set it from the header. Scheduled routines fire when the clock
reaches their time; one missed by more than 30 minutes is skipped, not
replayed. With a real account connected nothing is pinned and the real clock
applies. Focus timers always use the real clock, because a real job has to
fire.

## Tests

```bash
# offline, on the local store
cd part_3/custom_harness/appbook
../.venv/bin/python -m pytest -q

# the same suite on Oracle AI Database
PPA_TEST_SUBSTRATE=oracle ../.venv/bin/python -m pytest -q
```

On Oracle the suite uses schemas of its own, `PPA3_TEST_<owner>`, and empties
them. It never touches the schema the appbook runs on. No test calls a model
or System One.

The tests use the scripted responder, FastAPI's `TestClient` and a gateway
subprocess on a free port, with all state in a temporary folder and tracing
switched off. The practice workspace is a real mailbox, so no test names a
thread, a person or an event: each states a rule and checks it against
whatever the workspace holds.

`tests/test_part3_components.py` covers the ledger arithmetic, the trajectory
of a turn through approve and decline, repeated-workflow detection, every gate
check passing and failing, promote, refine, roll back, the routing rule and
the scorecard verdict both ways. `tests/test_teaching.py` checks that every
chapter has every teaching field, that every diagram can be drawn top-down and
that Part 3 points at nothing in Part 2.

`tests/live_check.py` is not collected by pytest. It runs the five canonical
turns against a running appbook, prints latency and token counts, and checks
the same anchors. With a key on the server it calls Claude and costs tokens.

## Layout

```
part_3/
  _shared/                       practice data, policy, connectors, the workspace gateway
  custom_harness/
    notebook/                    ppa_custom_harness.ipynb, Parts 1 to 14
    appbook/
      run.sh  requirements.txt  .env.example
      backend/
        main.py  config.py  schemas.py
        core/
          agent.py               the loop: LangGraph, approval interrupt, ledger and trajectory hooks
          llm_client.py          Claude with prompt caching, or the scripted responder
          scripted.py            the deterministic responder
          tools.py  workspace.py approval.py  governed.py  inbox.py  calendar_intel.py
          skills.py              manifests, versions, the live pointer and its log
          ledger.py              model calls, prices, context layers
          trajectories.py        one row for each turn
          learning.py            workflow to skill, the gate, refine, roll back, corrections
          scorecard.py           frozen checks and the verdict
          teaching.py            the frame of every chapter, as data
          store.py  oracle_store.py   the two substrates under one dialect of SQL
          architecture.py        components, edges, paths and live status checks
          memory.py  scratchfs.py  scheduler.py  routines.py  focus.py  review.py  system_one.py ...
        routers/                 one module for each chapter
      frontend/
        index.html  styles.css  app.js
        teaching.js              the frame and its diagrams
        assistant.js  architecture.js  refarch*.js  chapters.js  chapters-runtime.js  system-one.js
        chapters-learning.js     chapters 14 to 16
        explorer.js  oracle-explorer.js
      tests/
      data/                      created at run time, ignored by git
```

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| The header stays on "Warming harness" | The gateway did not start. Read `data/gateway.log`. The practice data file `part_3/_shared/data/practice_slice.json.gz` must exist |
| "A gateway is running on this port with a different token" | Another gateway holds port 8951. Stop it, or set `PPA_MCP_PORT` and `PPA_MCP_TOKEN` to match it |
| `Address already in use` on 8050 | Run `PORT=8051 ./run.sh` |
| "Missing appbook dependencies" | `run.sh` found no environment. Pass `PYTHON=` as shown under "Run it", or install `requirements.txt` |
| Answers come from the scripted responder | `ANTHROPIC_API_KEY` is not set in the shell that ran `run.sh` or in `.env`, or `PPA_RESPONDER=scripted` is set. The Architecture chapter shows which. The key is read at start, so start the appbook again after you set it |
| Chapter 15 shows zero tokens and zero cost | The scripted responder is answering, so no model is called. The page says so |
| A candidate fails "No regression on the frozen ten" | Its trigger words or its name overlap a frozen request of another kind. The check names the request. The version stays a candidate |
| A chapter shows "Not Found" after an update | The page is newer than the running backend. Stop the appbook and run `./run.sh` again |
| The page looks older than the code | The pages are served with `Cache-Control: no-cache`, so a reload is enough. A copy a browser kept from before that change needs one hard reload |
| A conversation answers "waiting for a decision" | A drafted action is pending. Decide it in the chat or in chapter 9, or start a new conversation |
| A scheduled routine did not fire | On the practice clock, routines fire when you move the clock to their time. Chapter 12 has "Run now" and the clock presets |
| No browser notification | Allow notifications for the page in chapter 11. The in-page toast appears either way |
| The calendar shows only one or two meetings | `PPA_GENERATED_CALENDAR=0` is set, or an older gateway holds the port. Stop it and start the appbook again |
| The Oracle source says "not reachable" | The notebook's database is not running. Run the custom-harness notebook, which starts it, then press "Try again" |
| The Oracle source says the database is busy | The notebook is using it. Each answer has nine seconds to spend; press "Try again" |
| Start again from empty | Press **Reset** in chapter 15, or `curl -X POST localhost:8050/api/reset -H 'Content-Type: application/json' -d '{"confirm":"reset"}'`. It empties the harness tables, the checkpoints and what was written to the practice workspace. On the local store, stopping the appbook and deleting `data/` does the same |
