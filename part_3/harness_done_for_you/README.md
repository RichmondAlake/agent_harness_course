# Part 3 · The harness done for you

**PPA is a personal productivity assistant.** It works for the owner of one
mailbox: it reads mail and calendar, turns requests into tasks, plans the day,
and sends or books only when the owner approves.

[`custom_harness/`](../custom_harness/) builds the harness around that
assistant by hand. This track builds the same assistant on a harness somebody
else wrote, so that you can see what a packaged harness gives you and what it
leaves for you to build.

## What MemoRizz is

[MemoRizz](https://github.com/RichmondAlake/memorizz) is an open-source agent
framework that puts memory first. One class, `MemAgent`, runs the control
loop. Around it MemoRizz supplies a memory system (conversations, facts about
people and things with dated history, a persona, skills, a toolbox), a client
for MCP servers with an allowlist, an approval gate, a learning loop that
turns repeated work into skills, and token and cost accounting.

The notebook was written against MemoRizz **0.17.25**.

## What is here

| Path | What it is |
|---|---|
| [`notebook/ppa_memorizz.ipynb`](notebook/ppa_memorizz.ipynb) | The notebook, saved with the outputs of a real run |
| `notebook/img/` | The notebook's diagrams, drawn from the Mermaid source kept beside each one |
| [`workspace_gateway.py`](workspace_gateway.py) | Serves the shared practice workspace as three MCP servers (mail, calendar, notes) |
| [`tests/`](tests/) | Offline tests for the gateway |
| `requirements.txt` | The packages |
| `data/` | Everything a run writes. Git ignores it |

## What the notebook covers

| Part | What it shows |
|---|---|
| 1 · Environment | Settings, keys, and MemoRizz's file system memory provider |
| 2 · A working week to practise on | One public mailbox, three real attack emails, a derived calendar and a pinned clock, served over MCP |
| 3 · Tools | `mcp_servers` with an allowlist, an approval store, and the four tools you still write (triage, tasks, a planner) |
| 4 · Persona, guardrails and standing rules | The three tiers of a MemoRizz persona and who may write each |
| 5 · Assemble the agent | One `MemAgent(...)` call, and which layer of the custom harness each argument replaces |
| 6 · Memory | The people the owner works with, as entities whose facts carry dates |
| 7 · One working day | The morning brief, triage into tasks, time-blocking that stops for approval, a refusal, a preference, a focus timer |
| 8 · Untrusted mail | What MemoRizz gives you against hostile email, and what you add |
| 9 · Continual learning | A repeated approved workflow becomes a skill, a repeated correction becomes a standing rule, a failing tool call becomes a usage note, all through the refine cycle |
| 10 · Time | MemoRizz timers and scheduled routines |
| 11 · Context and cost | A ledger per turn, the prompt cache, context snapshots |
| 12 · Built by hand, or done for you | Each part of the custom harness beside the MemoRizz feature that replaces it, or *you still build this* |

The notebook opens with a contents table.

## Requirements

- Python 3.12.
- `ANTHROPIC_API_KEY` for Claude Opus 5.5, the model that reasons and writes.
- `OPENAI_API_KEY` for embeddings (`text-embedding-3-small`), the background
  model (`gpt-6-luna`) and the memory router.
- `TYPESAFE_API_KEY` is optional. With it, mail is screened by Jev. Without
  it, the notebook uses OpenAI Decisions.

No Google, Microsoft or Notion account is needed, and no database.

## Run it

```bash
cd part_3/harness_done_for_you
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt

export ANTHROPIC_API_KEY=...        # or put the keys in a .env file in this folder
export OPENAI_API_KEY=...

# Offline tests: no key, no network, under a second
.venv/bin/python -m pytest tests -q

# Open the notebook with the kernel of .venv, and run it from top to bottom
```

To execute the notebook from the command line and keep its outputs in place:

```bash
.venv/bin/python - <<'PY'
import nbformat
from nbclient import NotebookClient

path = "notebook/ppa_memorizz.ipynb"
nb = nbformat.read(path, as_version=4)
NotebookClient(nb, timeout=900, resources={"metadata": {"path": "notebook"}}).execute()
nbformat.write(nb, path)
PY
```

A run takes about five minutes and makes real model calls. The saved run
cost $1.90 for the chat model (32 turns, 94 model calls, 90% of input tokens
read from cache); the notebook's Part 11 prints the figure for your run. The
background model, the memory router, the decision model and the embeddings
add a few cents.

The notebook starts the gateway itself, on port 8941 (`PPA_GATEWAY_PORT`
changes it), and stops it in its last cell. Every run starts from an empty
`data/` folder.

After a change to a diagram, draw it again:

```bash
python ../tools/diagrams/render.py notebook/ppa_memorizz.ipynb
```

## Use Oracle AI Database instead of files

The notebook keeps memory in files so that it runs anywhere. MemoRizz's
storage sits behind one provider interface, so the agent's code does not
change when the storage does. Install the Oracle extra and replace the one
cell in section 1.4:

```bash
.venv/bin/pip install "memorizz[oracle]"
```

```python
from memorizz import OracleConfig, OracleProvider

provider = OracleProvider(OracleConfig(
    user=os.environ["ORACLE_USER"],
    password=os.environ["ORACLE_PASSWORD"],
    dsn=os.environ["ORACLE_DSN"],          # for example localhost:1521/FREEPDB1
    embedding_provider="openai",
    embedding_config=EMBEDDING,
))
```

The saved run did not use Oracle. Check `OracleConfig` in your MemoRizz
version for its exact fields, and see MemoRizz's `docs/memory-providers/oracle.md`.
The approval store in section 3.2 is a JSON file for the same reason; in
production, put its six methods over a table.

## What leaves the machine

| Goes to | What |
|---|---|
| Anthropic | Each request, the persona and instruction, the tool definitions, and whatever the tools returned: calendar entries, triage results and the text of emails the assistant opens |
| OpenAI | Text to embed (tool descriptions, memory records, requests), the owner's messages for the memory router, and conversation excerpts for background upkeep and learning |
| TypeSafe, when its key is set | The subject and the first 3,000 characters of each inbox email, once, for the attack screen |
| Nobody | Sent mail, calendar events and pages. The practice workspace simulates them and keeps them in `data/` |

The mailbox is public research data (the Enron corpus), and it is still other
people's correspondence. The assistant is told never to store the text of an
email in memory.

## What was not run

- Oracle AI Database as the memory provider.
- A scheduled routine firing. The notebook stores a job and removes it; the
  MemoRizz worker is never started.
- MemoRizz's meta-harness (handing a task to pi, Codex, Claude Code or
  Hermes). This track has no second notebook for it. MemoRizz's own
  `examples/metaharness` notebooks cover it.
- Real mail, calendar or notes accounts.
