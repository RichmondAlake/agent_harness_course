# Survey paper appbook

The deep-research harness as an application. One FastAPI process serves the API and a
no-build page; the harness is the package in `backend/harness/`, which the notebook
inlines cell by cell.

```bash
part_2/advanced/deep_research/appbook/run.sh   # http://127.0.0.1:8041
```

Needs Oracle AI Database Free in Docker (`ppa-custom-oracle-26ai`, port 1524),
`ANTHROPIC_API_KEY` and `TAVILY_API_KEY`. Published papers are written to `part_2/advanced/deep_research/output/`.

| View | What it shows |
|---|---|
| Write a survey | A form; the selected paper's progress by section, the outline to approve, the paper to approve, and a live trace |
| 1. Reference architecture | Six tiers, fifteen components with icons and technologies, twenty-one typed data flows; select a component to read its role; simulate a run (a survey with both gates, a stopped run continues) step by step, with the current step shown above the diagram |
| 2. The compiled graph | The components, and the compiled graph with the selected paper's path lit |
| 3. The evidence library | Every page read, and a search of the library by meaning through the database's vectors |
| 4. Typed reading and the framework | The notes, the categories, the comparison table, the open questions |
| 5. Rules and the referee | What the harness counted, and what the referee found, per pass |
| 6. The paper | The assembled paper, readable in place, with links to the HTML and the Markdown |
| 7. Ledger, checkpoints and cost | The ledger, checkpoints, model calls; a reset |

A paper costs about forty model calls. The limits (sections, sources per section, words
and citations per section, revision rounds) are in `backend/harness/config.py` and shown
in the status bar.

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY`, `TAVILY_API_KEY` | none | Required |
| `ANTHROPIC_MODEL` | `claude-opus-5-5` | The model |
| `SURVEY_EFFORT` | `medium` | Effort passed to the model |
| `SURVEY_OUTPUT_DIR` | `deep_research/output` | Where published papers are written |
| `ADV_ORA_DSN`, `ADV_ORA_USER`, `ADV_ORA_PWD` | `127.0.0.1:1524/FREEPDB1`, `PPA_ADVANCED`, a local default | The database and schema |
| `PORT` | `8041` | Where `run.sh` listens |
