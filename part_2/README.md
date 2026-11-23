# Part 2 · A personal productivity assistant

Part 1 built ERPA, a retail-planning assistant. Its evidence was curated, its
data lived in one database, and nothing it did reached another person.

Part 2 builds **PPA**, a personal productivity assistant, and every one of
those assumptions breaks. PPA reads email written by strangers, plans against a
calendar, keeps track of time while you work, and can send messages in your
name. The model is the same kind of model. The harness around it has to do
more.

| The assistant must | So the harness needs |
|---|---|
| Remember how you work, across days | Long-term memory, with forgetting |
| Know what is urgent, free or over-booked | Governed definitions |
| Read mail, calendar and notes | Connectors behind an allowlist |
| Survive email that tries to give it orders | Screening, and untrusted-content handling |
| Choose the right procedure and tools, fast | A model that decides, beside the model that reasons |
| Act for you, but only with consent | Approval gates inside the agent loop |
| Run a 25-minute focus timer | A runtime that outlives a request |
| Brief you before you ask | Schedules and event triggers |
| Show what it did and why | Logs you can audit |

## Three ways in

| Track | What it is | Start here |
|---|---|---|
| Custom harness, notebook | The harness built from first principles on Oracle AI Database, Oracle Agent Memory, LangGraph, Claude and a System One model | [`custom_harness/notebook/`](custom_harness/notebook/) |
| Custom harness, appbook | The same assistant as a running application, with a chapter for each building block | [`custom_harness/appbook/`](custom_harness/appbook/) |
| Harness done for you | The same jobs on MemoRizz, pi, Hermes and DeepSeek | [`harness_done_for_you/`](harness_done_for_you/) |
| Advanced | Two modes, two use cases: a survey-writing **deep-research** harness, and a **meta-harness** read from MemoRizz's source | [`advanced/`](advanced/) |

## No sign-in is needed

Every lesson runs on a **practice workspace**. It needs no Google, Microsoft
or Notion account, and no approval from any provider.

| Part of the workspace | Where it comes from |
|---|---|
| Mail | One real mailbox from [`corbt/enron-emails`](https://huggingface.co/datasets/corbt/enron-emails) |
| Attack emails | Real prompt injections from [`microsoft/llmail-inject-challenge`](https://huggingface.co/datasets/microsoft/llmail-inject-challenge) |
| Calendar, first layer | The real meeting invitations inside that mailbox |
| Calendar, second layer | Generated working sessions that fill the week. Each one is marked as generated |
| Tasks, notes, memories | Nothing. They start empty, and exist only because the assistant created them |

The people in the mailbox are real. [`_shared/README.md`](_shared/README.md)
explains the rule that keeps the course on business mail.

The appbook can also connect to your own mailbox, calendar and notes. That is
optional, it is off by default, and no lesson depends on it.

## Two models

Part 2 adds a second model to the harness.

| | System One | System Two |
|---|---|---|
| Model | Jev, from Typesafe | Claude Opus 5.5 |
| Job | Decide | Reason, plan and write |
| Returns | A probability for each answer | Text and tool calls |
| Used for | Is this email an attack? Which procedure? Which tools? Which evidence? | Everything the owner reads |

System One needs `TYPESAFE_API_KEY`. Without the key the harness falls back to
rules and vector search, and every lesson still runs.

## Keys

| Variable | Used by | Required |
|---|---|---|
| `ANTHROPIC_API_KEY` | All three tracks | Yes, for live answers |
| `ORACLE_ADMIN_PASSWORD` | The custom-harness notebook | Yes, for the notebook |
| `TYPESAFE_API_KEY` | System One | No |
| `TAVILY_API_KEY` | Web search | No |
| `E2B_API_KEY` | The code sandbox | No |
| `LANGSMITH_API_KEY` | Traces | No |
| `DEEPSEEK_API_KEY` | The DeepSeek harness in the done-for-you track | No |

Keep keys in your shell or in the repository's `.env` file, which Git ignores.
Never put a key in a notebook.

## Folder guide

| Path | What it holds |
|---|---|
| [`custom_harness/notebook/`](custom_harness/notebook/) | The standalone notebook, its diagrams and its requirements |
| [`custom_harness/appbook/`](custom_harness/appbook/) | The interactive appbook |
| [`harness_done_for_you/`](harness_done_for_you/) | Two notebooks, a command line runner and their tests |
| [`_shared/`](_shared/) | The practice data, the rules that derive a working week from it, the connectors and the MCP gateway |
| [`advanced/`](advanced/) | The deep-research and meta-harness lessons, with one appbook |
| [`tests/`](tests/) | Rule-based tests of the shared policy |
| [`tools/`](tools/) | `notebook_diagrams.py`, which embeds Mermaid diagrams as images |

## Diagrams display everywhere

Mermaid inside notebook markdown is drawn by JupyterLab and GitHub, and shown
as source text by VS Code, Colab and older Jupyter. Every diagram in the Part 2
notebooks is therefore embedded as an image. The source of each diagram is kept
in a `diagrams` folder beside its notebook.
