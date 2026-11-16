# Part 3 · Custom harness

PPA, a personal productivity assistant, built explicitly, one layer at a time.
[`../README.md`](../README.md) says what PPA is and what Part 3 adds.

```text
people and time      the owner · scheduled routines · event triggers · focus timers
control loop         assemble_context → call_model → dispatch_tools
                       → draft_effects → human_review → apply_effects → persist
models               System One decides · Claude reasons · embeddings in the database
database             state · governed meaning · memory · skills with versions · time · evidence
connectors           three MCP servers behind an allowlist
systems of record    the practice workspace, or your own accounts
```

| Folder | What it is |
|---|---|
| [`notebook/`](notebook/) | The narrated build. It stands alone, on Oracle AI Database 26ai |
| [`appbook/`](appbook/) | The running assistant, with a chapter for each building block |

## Notebook

```bash
cd notebook
python -m pip install -r requirements.txt
export ANTHROPIC_API_KEY=... ORACLE_ADMIN_PASSWORD=...
jupyter lab ppa_custom_harness.ipynb
```

The notebook starts the database in Docker, builds the practice workspace from
public data, runs a working week end to end, lets the assistant learn a skill
from that week, and finishes with a scorecard. See
[`notebook/README.md`](notebook/README.md).

## Appbook

```bash
cd appbook
./run.sh          # http://127.0.0.1:8050
```

With no key the appbook answers from a scripted responder and nothing leaves
the machine. With `ANTHROPIC_API_KEY` it answers with Claude, and with
`TYPESAFE_API_KEY` System One screens mail and chooses evidence. See
[`appbook/README.md`](appbook/README.md).

## What differs between the two

| | Notebook | Appbook |
|---|---|---|
| Purpose | Read and run every line | Use the assistant, then open up its parts |
| Database | Oracle AI Database 26ai | Oracle AI Database 26ai when it answers, a local store when it does not |
| Memory | Oracle Agent Memory 26.8 | The appbook's own provider, with recall by keyword |
| Workspace | Practice workspace only | Practice workspace, or your own accounts |
| Needs Docker | Yes | No |
| Needs a key | `ANTHROPIC_API_KEY` | None. A scripted responder answers without one |
