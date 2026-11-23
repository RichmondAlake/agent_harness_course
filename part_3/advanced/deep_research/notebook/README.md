# Write a survey paper: a deep-research harness

`advanced_survey_paper_harness.ipynb` builds a deep-research harness from an empty
schema to a published paper. Given a subject, it plans a survey, asks a person to
approve the outline, sends out researchers that search and read with tools and take typed
notes, decides from what was read what to research next, writes each section from excerpts of
the pages, checks every cited claim for a quote that is really on the page, has a
referee pass review the draft, asks a person before it publishes, and remembers what it
learned in Oracle Agent Memory for the next paper.

Needs Docker (Oracle AI Database Free), `ANTHROPIC_API_KEY` and `TAVILY_API_KEY`.
About sixteen minutes and about $6.70 to run: $5.69 and 139 model calls for the paper, inside
the default budget of $6.00, and $1.00 for the small samples on the way; the outputs of the last run are saved in the notebook. The paper is written to `output/`. The paper from the saved run is
`../samples/agent-harness-engineering-survey-checked.md`; a longer one written by the
earlier version of the harness, without the claim check, is beside it.

| Part | Harness component | What it does |
|---|---|---|
| 1 | | The use case: a survey paper written from evidence, the nineteen components of the harness, and the other work the same harness can do |
| 2 | Foundation | Packages and what each is for, keys, the database, the embedding model inside it |
| 3 | State store | The tables and the settings that size a paper |
| 4 | Model gateway, cost control | One function for every model call: typed answers, a priced row, a cached prefix; the budget |
| 5 | Evidence store | Search, fetch, store with an embedding, ask by meaning, cut a page into passages |
| 6 | Vocabulary | The semantic layer: agreed terms and their meanings in the database, drawn into prompts by meaning, and counted in what comes back |
| 7 | Skills | Procedures for reading sources, stored with embeddings and disclosed in two levels: a short manifest, then the full text on request |
| 8 | Tools, context management | A researcher: a LangGraph graph of an agent node, a tool node and a compaction node. The model searches, reads, loads skills and takes notes, with limits the harness enforces, whole pages kept in the database, and compaction on demand |
| 9 | Research loop | Reflecting on what was read, and deciding whether a researcher goes out again |
| 10 | Memory | Oracle Agent Memory: preferences and lessons, scoped to a reader, superseded when corrected, recalled within a token budget |
| 11 | Planner | The outline, planned with the vocabulary and what memory holds; the framework built from the notes |
| 12 | Writer, verifier | Evidence packs, the claim check, repair, enforcement |
| 13 | Quality gate | The referee and the release check |
| 14 | Orchestration | The graph: thirteen nodes, two loops, two stops for a person |
| 15 | Human approval | Start a paper: the plan and the first approval |
| 16 | Durability | Cut off inside `organise`, and continued from the last checkpoint |
| 17 | Observability | What the harness decided: each researcher, the research rounds, claims, the revision, the bill |
| 18 | Human approval, memory | The release check, the second approval, the paper in full, what is remembered, and the plan of a next paper |
| 19 | | Where this harness goes next: enterprise search over institutional knowledge, and other uses |

Each part opens with a strip that shows which component it builds and which are
already built. Every code cell is short and has an explanation above it. Parts 4 to 12 try each piece on a small sample before the full run, so the notebook can
be read and run a part at a time.

The notebook file is the source: edit it directly. Each diagram is an image in `img/` with its
Mermaid source under a fold in the same cell, and `part_3/tools/diagrams/render.py` redraws
the images from it. The
appbook's `backend/harness/` package holds the same functions, kept in step by hand; a test
names any that drift.
