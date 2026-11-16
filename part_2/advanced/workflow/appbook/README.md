# Trip workflow appbook

The trip-booking workflow harness as an application. One FastAPI process serves the API
and a no-build page; the harness itself is the package in `backend/harness/`, which the
notebook inlines cell by cell.

```bash
part_2/advanced/workflow/appbook/run.sh        # http://127.0.0.1:8040
```

Needs Oracle AI Database Free in Docker (`ppa-custom-oracle-26ai`, port 1524),
`ANTHROPIC_API_KEY` and `TAVILY_API_KEY` in the shell or the repository `.env`. On start
the appbook creates the `PPA_ADVANCED` schema through the container if it is missing,
loads the embedding model into it once, creates the workflow tables and sets up
LangGraph's checkpoint tables.

| View | What it shows |
|---|---|
| Book a trip | A form with three example travellers to start from (any name works: it is kept as a lower-case id, and a new traveller starts with no memories); the selected trip's status, preferences used, understood request, the itinerary card with approve, change and reject, the bookings, and a live trace of every node |
| 1. Reference architecture | Six tiers, fifteen components with icons and technologies, nineteen typed data flows; select a component to read its role; simulate a run (plan and book, a provider fails, crash and resume) step by step, with the current step shown above the diagram |
| 2. The compiled graph | The components with a live status, and the compiled graph with the selected trip's path lit |
| 3. Traveller memory | Recall by meaning, remember a statement, forget a traveller |
| 4. Real search evidence | Every page read and every typed offer, with its confidence |
| 5. The booking saga and compensation | Arm a provider fault, then approve: the flight is cancelled, the next hotel is chosen, the traveller is asked again |
| 6. Crash and resume | Runs the two-process proof and streams its lines |
| 7. System One: a model that decides | The four closed decisions Jev answers, the calls made for the selected trip with their answers, and what they cost |
| 8. Ledger, checkpoints and cost | The ledger, the checkpoint count, the model calls of this process; a reset |

The data explorer under every view lists the workflow's tables, the memory store's tables
(`TRIPMEM_*`) and LangGraph's checkpoint tables, read-only, newest rows first.

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY`, `TAVILY_API_KEY` | none | Required |
| `TYPESAFE_API_KEY` | none | Switches System One (Jev) on; without it the four decisions fall back to rules |
| `TRIP_SYSTEM_ONE` | `on` | `off` keeps System One off even with a key |
| `ANTHROPIC_MODEL` | `claude-opus-5-5` | The model |
| `ADV_ORA_DSN` | `127.0.0.1:1524/FREEPDB1` | The database |
| `ADV_ORA_USER`, `ADV_ORA_PWD` | `PPA_ADVANCED`, a workshop default | The schema |
| `ADV_ORACLE_CONTAINER` | `ppa-custom-oracle-26ai` | The container used to create the schema |
| `ORACLE_ADMIN_PASSWORD` | none | Used instead of the container when the database is not in Docker here |
| `PORT` | `8040` | Where `run.sh` listens |
