# Harness Engineering for AI Agents

This repository is the technical companion to Richmond Alake's O'Reilly live
workshop, [Harness Engineering for AI Agents](https://www.oreilly.com/live-events/harness-engineering-for-ai-agents/0642572381264).
It turns the workshop's memory-first architecture into runnable code, narrated
notebooks, interactive appbooks, staged exercises, and a production-oriented
deployment path.

The course has three parts. The first two each build one assistant, and the
third makes the second one measure itself and improve.

| Part | Assistant | What the harness has to handle |
|---|---|---|
| [Part 1](part_1/) | **ERPA**, a retail-planning assistant | Curated evidence in one database. Nothing it does reaches another person |
| [Part 2](part_2/) | **PPA**, a personal productivity assistant | Mail written by strangers, a calendar, timers that outlive a request, and actions taken in your name |
| [Part 3](part_3/) | **PPA**, rebuilt for teaching, that improves | Everything in Part 2, plus a cached prompt with a bill for every turn, a record of every turn, skills the assistant learns from turns you approved, and a scorecard |

## Part 1: ERPA

ERPA is a fictional retail-planning assistant built twice against the same
synthetic Kata dataset:

| Path | Approach | Best for |
|---|---|---|
| [MemoRizz build](part_1/harness_done_for_you/memorizz/assistant/) | A packaged harness with the major decisions made for you | Learning the anatomy of a complete harness |
| [Custom build](part_1/custom_harness/) | An explicit, modular LangGraph-style harness | Understanding how each layer is assembled |
| [Advanced track](part_1/advanced/) | Durable LangGraph/Oracle workflows, Tavily research, MemoRizz MetaHarness, and E2B | Recovery, evidence learning, sandbox governance, and fair evaluation |

Both paths demonstrate working, episodic, semantic, and procedural memory; trusted
tools and progressive capability disclosure; sandboxed execution; semantic caching;
and observable `recall -> decide -> write` traces.

### Part 1 quick start

Local workshop mode is deterministic, credential-free, and uses generated synthetic
data. It requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install \
  -r part_1/harness_done_for_you/memorizz/assistant/appbook/requirements.txt \
  -r part_1/custom_harness/appbook/requirements.txt
python part_1/tests/smoke_test.py
```

Start either interactive appbook:

```bash
# Packaged MemoRizz harness: http://127.0.0.1:8000
cd part_1/harness_done_for_you/memorizz/assistant/appbook
./run.sh

# Or, from the repository root, run the custom harness on port 8001
cd part_1/custom_harness/appbook
PORT=8001 ./run.sh
```

For the narrated exercises, open
[`erpa_memorizz_complete.ipynb`](part_1/harness_done_for_you/memorizz/assistant/notebook/erpa_memorizz_complete.ipynb)
or [`erpa_custom_complete.ipynb`](part_1/custom_harness/notebook/erpa_custom_complete.ipynb)
in Jupyter.

The advanced continuation has four appbooks and five narrated notebooks, including a
fair-evaluation capstone. Install its published PyPI dependencies and begin with the
[advanced guide](part_1/advanced/README.md):

```bash
.venv/bin/python -m pip install --upgrade -r part_1/advanced/requirements.txt
.venv/bin/python -m pytest -q part_1/advanced/tests
```

## Part 2: PPA

PPA reads email, plans against a calendar, keeps time while you work and can
send messages for you, so its harness needs what ERPA's did not: screening of
untrusted mail, approval gates inside the agent loop, a runtime for timers and
schedules, and a second model that decides beside the model that reasons.

| Path | Approach | Best for |
|---|---|---|
| [Custom harness notebook](part_2/custom_harness/notebook/) | The harness built from first principles on Oracle AI Database 26ai, Oracle Agent Memory, LangGraph, Claude and a System One model | Reading and running every line |
| [Custom harness appbook](part_2/custom_harness/appbook/) | The same assistant as a running application, with fourteen chapters and a data explorer | Using the assistant, then opening up its parts |
| [Harness done for you](part_2/harness_done_for_you/) | The same jobs on MemoRizz, pi, Hermes and DeepSeek | Seeing what a packaged harness decides for you |
| [Advanced](part_2/advanced/) | A deep-research harness that writes a cited survey paper; MemoRizz's meta-harness read from its source and run across Claude Code, Codex and pi | Two of the modes an agentic application runs in |

Every lesson runs on a practice workspace built from public data: one mailbox
from [`corbt/enron-emails`](https://huggingface.co/datasets/corbt/enron-emails),
real prompt injections from
[`microsoft/llmail-inject-challenge`](https://huggingface.co/datasets/microsoft/llmail-inject-challenge),
and a calendar derived from that mailbox. No lesson needs a Google, Microsoft
or Notion account.

### Part 2 quick start

The appbook runs with no keys. It then answers from a scripted responder and
nothing leaves the machine.

```bash
python -m venv part_2/custom_harness/.venv
part_2/custom_harness/.venv/bin/python -m pip install \
  -r part_2/custom_harness/appbook/requirements.txt
cd part_2/custom_harness/appbook
./run.sh                        # http://127.0.0.1:8020
```

| To get | Set |
|---|---|
| Answers from Claude | `ANTHROPIC_API_KEY` |
| System One: attack screening and choice of evidence | `TYPESAFE_API_KEY` |
| State kept in Oracle AI Database | Nothing. The appbook uses the database when it is running, and a local store when it is not |

The notebook needs Docker, `ANTHROPIC_API_KEY` and `ORACLE_ADMIN_PASSWORD`. It
starts the database, builds the practice workspace and runs a working day end
to end. Its sections are numbered by part for the outline, and the sections
marked with a star are the ones to show live.

```bash
cd part_2/custom_harness/notebook
python -m pip install -r requirements.txt
jupyter lab ppa_custom_complete.ipynb
```

Begin with the [Part 2 guide](part_2/README.md). The advanced track has its own
[guide](part_2/advanced/README.md), one more appbook on port 8041, and a
survey paper the deep-research harness wrote, in `part_2/advanced/deep_research/samples/`.

## Part 3: PPA that improves

**PPA is a personal productivity assistant.** It works for the owner of one
mailbox: it reads mail and the calendar, turns requests into tasks, plans the
day into free time, runs focus timers, briefs you before you ask, and sends or
books only with your approval. [`part_3/README.md`](part_3/README.md) explains
it in full.

Part 3 is the Part 2 custom harness rewritten to be taught from, with four
additions.

| Addition | What it does |
|---|---|
| Prompt caching, with a bill | The stable start of the prompt is cached, and every model call is priced and stored |
| The turn record | One row per turn: the request, the plan, the tools that ran, the outcome, and the owner's words when declining |
| Learning from its own traces | Work the owner approved twice becomes a skill. A gate of five checks decides whether it goes live, a correction revises it, and a pointer rolls it back |
| A scorecard | The harness's claims as checks with pass marks, and a READY or BLOCKED verdict |

| Path | What it is |
|---|---|
| [Notebook](part_3/custom_harness/notebook/) | The harness built one layer at a time on Oracle AI Database 26ai, Oracle Agent Memory, LangGraph, Claude and a System One model |
| [Appbook](part_3/custom_harness/appbook/) | The same assistant as a running application on port 8050, with a chapter for each building block |
| [Harness done for you](part_3/harness_done_for_you/) | The same assistant on MemoRizz 0.17.25, with a table of what a packaged harness gives you and what you still build |
| [Advanced](part_3/advanced/) | The advanced track: a deep-research harness that writes a cited survey paper, with researchers that work with tools, a vocabulary, reading skills, memory, a budget and two approvals. One more appbook on port 8041 |

```bash
cd part_3/custom_harness/appbook
./run.sh                        # http://127.0.0.1:8050, no keys needed
```

## Repository guide

- [`part_3/README.md`](part_3/README.md) explains what PPA is, what a harness is,
  and what Part 3 adds to the custom harness.
- [`part_2/README.md`](part_2/README.md) explains the three Part 2 tracks, the
  practice workspace, the two models and the keys.
- [`part_2/_shared/`](part_2/_shared/) holds the practice data, the rules that
  derive a working week from it, the connectors and the MCP gateway.

- [`part_1/README.md`](part_1/README.md) explains participant setup, the two builds,
  and the workshop architecture.
- [`part_1/advanced/`](part_1/advanced/) implements the advanced O'Reilly curriculum
  with OracleSaver/OracleStore, Tavily, GPT-5.5, Claude Opus 5, E2B, and MemoRizz
  0.6.3, plus a fair harness-evaluation capstone.
- [`part_1/custom_harness/stages/`](part_1/custom_harness/stages/) contains six small,
  independently runnable construction stages.
- [`part_1/_shared/`](part_1/_shared/) is the source of truth used by both builds for
  the synthetic dataset, fixtures, runtime contracts, and canonical demo.
- [`part_1/scripts/`](part_1/scripts/) contains the cache and cross-process persistence
  acceptance checks used during the workshop.
- [`part_1/INSTRUCTOR_RUNBOOK.md`](part_1/INSTRUCTOR_RUNBOOK.md) provides the live
  teaching sequence and preflight checklist.
- [`part_1/SPEC_COVERAGE.md`](part_1/SPEC_COVERAGE.md) maps the workshop requirements
  to implementation evidence.

## Optional live stack

The local profile needs no keys. The live paths add model providers, Oracle AI
Database, MemoRizz/OAMP memory, E2B, Notion MCP, Tavily, LangSmith, and durable
LangGraph checkpointing. Copy `.env.example` to `.env`, supply only the services you
intend to use, and never commit that file.

The complete custom stack can be launched with Docker Compose after setting
`ANTHROPIC_API_KEY`, `E2B_API_KEY`, `LANGSMITH_API_KEY`, `ORACLE_PASSWORD`, and
`ORA_AGENT_PWD`:

```bash
cd part_1/custom_harness/deploy
docker compose up --build
```

See the [deployment guide](part_1/custom_harness/deploy/README.md) for details.

## Safety and scope

In Part 1, all customer and commercial records are synthetic. The local sandbox exposes only
fixed workshop operations: it cannot execute arbitrary shell commands or make
unrestricted network requests. The examples do not execute payments, mutate the
historical business dataset, or autonomously approve commercial decisions.

In Part 2, the practice mailbox is public data and its people are real, so the
course keeps to business mail. Messages sent in the practice workspace reach
nobody. With your own accounts connected, safe mode is on by default: an
approved message to anyone but you is held as a draft. Text the assistant reads
is sent to the model providers you give keys for, and to nobody else.
