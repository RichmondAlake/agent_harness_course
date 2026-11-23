"""Skills: written procedures the agent loads only when it needs them."""
from __future__ import annotations

from shared.oracle import EMBED, execute, rows

SKILLS = [
    {"name": "read-empirical-paper",
     "description": "How to read a paper that reports experiments: what was tested, against what, and what the numbers show.",
     "body": """1. Find the claim the paper is making, in one sentence.
2. Find the setup: which models, which benchmark or task set, how many tasks, which baselines.
3. Copy each headline number with its unit and its condition (model, benchmark, setting). A number without its condition is not a claim.
4. Look for what was held fixed. A result that changes the model and the harness together says nothing about either.
5. Read the limitations or threats section. Record the limits the authors state themselves.
6. In the note: kind is paper or preprint; evidence names the benchmark and the numbers; each claim is one sentence a survey could cite."""},
    {"name": "read-survey-or-position-paper",
     "description": "How to read a survey, taxonomy or position paper: its framework and definitions, not second-hand results.",
     "body": """1. Record the organising framework: the categories it uses and how it defines them.
2. Record the definitions it gives for key terms, in its own words.
3. Do not cite a survey for a result it only reports from another paper. Note the primary source's name so it can be searched for.
4. Record what the authors say is missing or unsolved.
5. In the note: evidence is usually 'none of its own'; claims are about structure and definitions; relevance is high only if the framework bears on the section."""},
    {"name": "read-benchmark-paper",
     "description": "How to read a paper that introduces a benchmark, a dataset or an evaluation method for agents.",
     "body": """1. Record what is measured: the task, the number of tasks, the metric and how success is judged.
2. Record how agents are run on it: the evaluation harness, time or step limits, what tools are allowed.
3. Record the reported baseline scores with the model and setting for each.
4. Look for known problems: contamination, ambiguous tasks, graders that can be gamed.
5. In the note: method describes the benchmark construction; evidence gives its size and baseline numbers; claims say what the benchmark can and cannot show."""},
    {"name": "read-system-or-tool-documentation",
     "description": "How to read documentation, an engineering write-up or a blog post from a vendor or project about a system.",
     "body": """1. Record what the system does and how, as described. Record the date or version if it is given.
2. Separate a description of a mechanism from a claim about how well it works. Vendors describe both in the same voice.
3. Treat performance statements without a method as the author's claim, and say so in the note.
4. Prefer it as a source for how something is built, not for how good it is.
5. In the note: kind is documentation, blog or report; evidence says whether any measurement is shown; relevance is medium unless the mechanism is central to the section."""},
    {"name": "read-abstract-only-page",
     "description": "What to do when a page gives only an abstract, a landing page or a fragment, not the full text.",
     "body": """1. Say in the note that only the abstract was available.
2. Record only what the abstract states. Do not infer the method or the numbers.
3. Limit claims to at most two, and mark relevance no higher than medium.
4. If the work looks important for the section, search for a full-text version before finishing."""},
]


def seed_skills() -> int:
    """Store the skills. The description is embedded, because the description is what a search has to match."""
    execute("DELETE FROM survey_skills")
    for skill in SKILLS:
        execute(f"INSERT INTO survey_skills (name, description, body, embedding) VALUES (:n, :d, :b, {EMBED})",
                {"n": skill["name"], "d": skill["description"], "b": skill["body"],
                 "text": f"{skill['name'].replace('-', ' ')}: {skill['description']}"})
    return len(SKILLS)


def skills_for(text: str, limit: int = 4) -> list[dict]:
    """The first level of disclosure: names and one-line descriptions of the skills nearest to a task."""
    return rows(f"""SELECT name, description, ROUND(VECTOR_DISTANCE(embedding, {EMBED}, COSINE), 3) AS distance
                      FROM survey_skills ORDER BY distance FETCH FIRST :k ROWS ONLY""", {"text": text[:4000], "k": limit})


def skill_manifest(skills: list[dict]) -> str:
    """The manifest that goes into the prompt: enough to choose a skill, not enough to follow one."""
    return ("SKILLS. Each is a written procedure. You see only its name and what it is for. Call load_skill with the "
            "name to read the procedure before you use it.\n" + "\n".join(f"- {s['name']}: {s['description']}" for s in skills))


def load_skill(name: str) -> str | None:
    """The second level of disclosure: the full procedure, fetched only when the agent asks for it."""
    found = rows("SELECT body FROM survey_skills WHERE name = :n", {"n": name})
    return found[0]["body"] if found else None
