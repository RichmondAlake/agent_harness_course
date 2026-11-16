# PPA custom-harness notebook

`ppa_custom_harness.ipynb` builds PPA, a personal productivity assistant, on a
custom agent harness, one layer at a time. It stands alone: every line of code
it runs is in a cell you can read, and it imports nothing from this
repository. [`../../README.md`](../../README.md) says what PPA is.

## What it builds

| Parts | Layer |
|---|---|
| 1 to 3 | The database with an embedding model inside it, a practice week built from public data, and mail, calendar and notes behind MCP |
| 4 to 6 | What the harness owns: state and governed definitions, a scratch space and long-term memory, skills with versions, and a runtime for timers |
| 7 to 9 | The models: System One chooses the evidence, the procedure and the tools, trusted tools carry out, Claude reasons with a cached prompt and a price on every call |
| 10 | The control loop with approval inside it, and a record of every turn |
| 11 and 12 | A working week run live: six requests and their bill, a proactive brief, an event trigger, the weekly review |
| 13 | The assistant learns a skill from turns the owner approved, passes it through a gate, revises it from a correction and rehearses the rollback |
| 14 | Evidence: the logs, a scorecard with a READY or BLOCKED verdict, and final acceptance |

The notebook has 14 parts and about 260 cells. Run from top to bottom it takes
about eight minutes and costs between one and two US dollars in model calls.

## What you need

| Requirement | Why | Required |
|---|---|---|
| Python 3.11 or newer | The notebook's code | Yes |
| Docker | Runs Oracle AI Database 26ai Free. The notebook starts it for you | Yes |
| `ANTHROPIC_API_KEY` | Claude, and memory extraction | Yes |
| `ORACLE_ADMIN_PASSWORD` | The SYS password of the practice database. Choose any strong password on the first run | Yes |
| `TYPESAFE_API_KEY` | The System One model, Jev. Without it the harness uses vector search | No |
| `TAVILY_API_KEY`, `E2B_API_KEY` | Web search, a code sandbox | No |

No sign-in to a mail or calendar provider is needed. The notebook works on a
practice workspace that it builds from public data.

Give Docker at least 6 GB of memory and 8 GB of free disk. One Oracle database
uses about 5 GB of memory while the notebook runs.

## Run it

```bash
cd part_3/custom_harness/notebook
python -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt

export ANTHROPIC_API_KEY=...
export ORACLE_ADMIN_PASSWORD=...
export TYPESAFE_API_KEY=...        # optional

jupyter lab ppa_custom_harness.ipynb
```

In VS Code, open the notebook and choose the environment above as its kernel.
A key that is not in the environment is asked for with a masked prompt.

The first run downloads the database image and one mailbox from Hugging Face.
Later runs reuse both. The notebook uses the same database container as Part 2
(`ppa-custom-oracle-26ai`, port 1524) and its own schema, `PPA3_AGENT`, so both
notebooks can be run against one database.

## How it is organised

| Marker | Meaning |
|---|---|
| **Part N** | One layer of the harness. Parts are the top level of the outline |
| **N.M** | A numbered section inside a part |
| **What to watch** | The one thing to look for in the output |
| 💡 **Key Term** | A term defined where it is first needed |
| 📌 **Key Takeaways** | The last cell of every part |

The notebook opens with what PPA is, the reference architecture, the list of
components and a table of contents.

Run every cell once before a session and keep the kernel alive. Later cells use
what earlier cells define.

## Diagrams

Every diagram is an image in [`img/`](img/), so it displays in JupyterLab,
VS Code, Colab and on GitHub. Its Mermaid source sits under the image in the
same cell, folded away.

To change a diagram, edit its Mermaid source in the notebook and run:

```bash
python part_3/tools/diagrams/render.py part_3/custom_harness/notebook/ppa_custom_harness.ipynb [name ...]
```

The tool needs Node.js and `@mermaid-js/mermaid-cli` (run
`npx -y @mermaid-js/mermaid-cli --version` once).

## What it leaves behind

| Item | Where | How to remove it |
|---|---|---|
| The database container and its volume | Docker, `ppa-custom-oracle-26ai` | `docker rm -f ppa-custom-oracle-26ai` and `docker volume rm ppa-custom-oracle-26ai-data` |
| The downloaded mailbox and the MCP server file | `ppa_workspace/` beside the notebook | Delete the folder |
| Scheduled jobs in the schema | The database | Set `PPA_KEEP_DATA=0` before running the cleanup cell |

The notebook never drops the schema, the container or the volume on its own.
