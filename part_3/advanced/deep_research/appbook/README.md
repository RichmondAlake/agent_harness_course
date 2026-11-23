# Survey paper appbook

The deep-research harness as an application. One FastAPI process serves the API and a
no-build page; the harness is the package in `backend/harness/`. The notebook defines
the same functions cell by cell, and the two are kept in step by hand.

```bash
part_3/advanced/deep_research/appbook/run.sh   # http://127.0.0.1:8041
```

Needs Docker, `ANTHROPIC_API_KEY` and `TAVILY_API_KEY`. It starts Oracle AI Database Free
(`ppa-custom-oracle-26ai`, port 1524) when it is not running, and creates it the first
time, which takes a few minutes. Published papers are written to `part_3/advanced/deep_research/output/`.

Every chapter is one component of the harness, in the order the notebook builds them.
Each opens with the same teaching text as the notebook (which component it is, why the
harness needs it, the key term) and most have a lab that runs that component alone, on a
small practice paper of its own, so it can be tried without running a whole survey.

| Chapter | Harness component | What you can try on its own |
|---|---|---|
| Write a survey | Orchestration, human approval, durability | A whole paper with both approvals, and its run trace: the steps, the work of each section, and a live log of every step, model call and tool call, which opens full screen. Tick the box at the outline approval to cut the run off inside `organise`, then continue it |
| 1. Reference architecture | | Select a component, or simulate a run |
| 2. Foundation | Foundation | Embed a phrase inside the database |
| 3. State store | State store | Write a ledger entry and read it back |
| 4. Model gateway and cost control | Model gateway, cost control | One model call and its priced row; two calls that share a cached opening; what the budget would allow |
| 5. Evidence store | Evidence store | A web search on its own; fetch one page; ask the library by meaning |
| 6. Vocabulary | Vocabulary | Draw the agreed terms for a piece of text, see the block a prompt would carry, and count avoided words |
| 7. Skills | Skills | Find the skills nearest to a task, see the short manifest, then load one procedure |
| 8. Tools | Tools | Read the researcher's LangGraph graph and the six tool definitions; run one tool call by hand, including one the harness refuses; send a whole researcher out |
| 9. Context management | Context management | See how much of a stored page stays out of the conversation and look back into it; compact a small conversation and compare sizes |
| 10. Research loop | Research loop | Reflect on what was read; send a researcher out again with the gaps |
| 11. Memory between papers | Memory | Remember, correct (supersede) and recall with Oracle Agent Memory |
| 12. Planner | Planner | Plan a paper, with the vocabulary and what memory holds |
| 13. Writer and verifier | Writer, verifier | Check a quote against a page with no model; split a draft into cited claims; see a source's excerpts; write and check one section |
| 14. Quality gate | Quality gate | Run the release check on a paper: seven counted facts, no model call |
| 15. Orchestration | Orchestration | The compiled graph with the selected paper's path lit |
| 16. Human approval | Human approval | Plan a paper and stop at the outline, then revise it with a note or reject it |
| 17. Durability | Durability | Runs that stopped part-way, what survived, and a Continue button |
| 18. Observability | Observability | The ledger with every decision, checkpoints, model calls and dollars |
| 19. The paper | | The assembled paper, as a page or as Markdown |

A run carries on when you open another chapter: it lives on the server, and a card in the
corner of every page shows the step it is on, what it has spent, and whether it is
waiting for you. The chapter list collapses to a narrow rail with the button beside the
title. Tool calls are recorded in `SURVEY_TOOL_CALLS`, a table the appbook adds for the
trace.

The labs call the same functions a full run calls. Their routes are in `backend/labs.py`,
and their pages in `frontend/labs.js`. What a lab spends is kept on the practice paper
`PAPER-lab`, apart from real papers. A model lab costs a fraction of a cent to a few
cents; sending a researcher out, or writing and checking the practice section, costs about thirty cents each.

A paper may spend up to its budget on the model, six dollars by default. The limits
(budget, sections, sources per section, research rounds, words and citations per section,
revision rounds) are in `backend/harness/config.py`. The publication gate shows the
release check; a paper that is BLOCKED can be overridden or rejected, not approved.

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY`, `TAVILY_API_KEY` | none | Required |
| `ANTHROPIC_MODEL` | `claude-opus-5-5` | The model |
| `SURVEY_EFFORT` | `medium` | Effort passed to the model |
| `SURVEY_BUDGET_USD` | `6.00` | What one paper may spend on the model |
| `SURVEY_OUTPUT_DIR` | `deep_research/output` | Where published papers are written |
| `ADV_ORA_DSN`, `ADV_ORA_USER`, `ADV_ORA_PWD` | `127.0.0.1:1524/FREEPDB1`, `PPA_ADVANCED`, a local default | The database and schema |
| `PORT` | `8041` | Where `run.sh` listens |
