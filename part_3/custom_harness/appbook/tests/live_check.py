"""Run the five canonical turns against a running appbook and check the anchors.

This is a live check, not a pytest module: it talks to whatever responder the
appbook is using, so with ANTHROPIC_API_KEY set on the server it calls Claude
and costs tokens. Start the appbook first, then:

    python tests/live_check.py                      # http://127.0.0.1:8050
    python tests/live_check.py http://127.0.0.1:8050 --reset

Nothing here names a thread, a person or an event. Every anchor is derived
from what the workspace and the shared policy report at the moment of the run.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid

CHECKS: list[tuple[str, bool, str]] = []


class Appbook:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        request = urllib.request.Request(
            self.base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            raise SystemExit(f"{method} {path} answered {error.code}: {error.read().decode()[:400]}") from error

    def get(self, path: str) -> dict:
        return self.call("GET", path)

    def post(self, path: str, body: dict | None = None) -> dict:
        return self.call("POST", path, body or {})


def check(name: str, passed: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(passed), detail))
    print(f"    {'PASS' if passed else 'FAIL'}  {name}{'  [' + detail + ']' if detail else ''}")


def turn(app: Appbook, number: int, message: str, **fields) -> dict:
    print(f"\nTurn {number}: {message}")
    started = time.perf_counter()
    outcome = app.post("/api/assistant/turn", {"message": message, **fields})
    outcome["label"] = str(number) if outcome["status"] == "completed" else f"{number} to the gate"
    report(outcome, time.perf_counter() - started)
    return outcome


def report(outcome: dict, seconds: float) -> None:
    trace, tokens = outcome["trace"], outcome["trace"]["tokens"]
    print(f"    {outcome['status']} · {outcome['responder']} · {seconds:.1f} s wall · "
          f"{trace['model_calls']} model calls · {len(trace['tool_calls'])} tool calls · "
          f"{tokens.get('input_tokens', 0)} in, {tokens.get('output_tokens', 0)} out, "
          f"{tokens.get('cache_read_tokens', 0)} cache read")
    print(f"    tools: {', '.join(call['name'] for call in trace['tool_calls']) or 'none'}")
    outcome["seconds"] = round(seconds, 1)
    for line in (outcome.get("answer") or "").splitlines():
        print(f"      | {line}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("base", nargs="?", default="http://127.0.0.1:8050")
    parser.add_argument("--reset", action="store_true", help="empty the harness state first")
    parser.add_argument("--focus-seconds", type=int, default=0,
                        help="also start a compressed timer of this many seconds and wait for it to fire")
    args = parser.parse_args()
    app = Appbook(args.base)

    status = app.get("/api/status")
    if not status.get("ready"):
        raise SystemExit(f"The appbook is not ready: {status}")
    if args.reset:
        app.post("/api/reset", {"confirm": "reset"})
        status = app.get("/api/status")
    print(f"Appbook: {args.base}\nOwner: {status['owner']['name']} · {status['workspace']['mode']} workspace · "
          f"safe mode {'on' if status['workspace']['safe_mode'] else 'off'} · clock {status['clock']['now']}"
          f"\nResponder: {status['responder']['label']}")
    thread = f"live-{uuid.uuid4().hex[:8]}"
    runs = []

    # 1. Morning brief
    rows = app.get("/api/inbox_triage/status")["rows"]
    day = app.get("/api/calendar_intel/status")["day"]
    brief = turn(app, 1, "Prepare my morning brief.", thread_id=thread)
    runs.append(brief)
    answer = brief["answer"] or ""
    actionable = [row for row in rows if row["category"] in ("reply", "task", "delegate")]
    mentioned = [row["thread_id"] for row in rows if row["thread_id"] in answer]
    called = [call["name"] for call in brief["trace"]["tool_calls"]]
    check("completed without an approval", brief["status"] == "completed")
    check("loaded the morning-brief skill", "load_skill" in called)
    check("read mail and calendar through the harness tools",
          {"triage_inbox", "day_overview"} & set(called) == {"triage_inbox", "day_overview"}
          or {"mail_search_threads", "calendar_list_events"} <= set(called), ", ".join(called))
    check("leads with the first triage row", bool(actionable) and bool(mentioned)
          and mentioned and min(mentioned, key=answer.index) == actionable[0]["thread_id"],
          actionable[0]["thread_id"] if actionable else "no actionable thread")
    check("names every event today", all(event["event_id"] in answer or event["title"] in answer
                                         for event in day["events"]), f"{len(day['events'])} events")
    check("flags meetings that break the earliest-meeting rule",
          not day["meeting_rule_violations"] or day["rules"]["no_meetings_before"] in answer,
          f"{len(day['meeting_rule_violations'])} violations")
    check("reports the quarantined threads by ID", all(row["thread_id"] in answer for row in rows
                                                      if row["category"] == "quarantine"))

    # 2. Triage
    triage = turn(app, 2, "Triage my inbox and turn anything actionable into tasks.", thread_id=thread)
    runs.append(triage)
    tasks = app.get("/api/assistant/tasks")["open"]
    after = {row["thread_id"]: row for row in app.get("/api/inbox_triage/status")["rows"]}
    quarantined = {row["thread_id"] for row in rows if row["category"] == "quarantine"}
    linked = [item for item in tasks if item["source_ref"] in after]
    drafts = app.post("/api/systems_of_record/read", {"name": "mail_list_drafts"})["raw_mcp_result"]["drafts"]
    sent = app.post("/api/systems_of_record/read", {"name": "mail_list_sent"})["raw_mcp_result"]["sent"]
    check("created tasks", bool(tasks), f"{len(tasks)} open tasks")
    check("new tasks link back to their threads", bool(linked) and all(
        item["source_type"] == "mail" for item in linked), f"{len(linked)} of {len(tasks)} linked")
    check("no thread has two open tasks", len({item["source_ref"] for item in linked}) == len(linked))
    check("every tracked thread cites its task", all(
        after[item["source_ref"]]["tracked_task_id"] == item["task_id"] for item in linked))
    check("no task or draft came from a quarantined thread", not quarantined & (
        {item["source_ref"] for item in tasks} | {item["thread_id"] for item in drafts}))
    check("drafts were saved and nothing was sent", sent == [], f"{len(drafts)} drafts, {len(sent)} sent")

    # 3. Time-blocking, with the approval interrupt
    before = app.get("/api/calendar_intel/status")["day"]["events"]
    blocks = turn(app, 3, "Time-block my top three tasks for today.", thread_id=thread)
    runs.append(blocks)
    pending = blocks["pending_actions"]
    check("the run pauses at an approval interrupt", blocks["status"] == "awaiting_approval" and bool(pending),
          f"{len(pending)} drafted")
    check("every drafted action is a calendar event",
          all(item["tool_name"] == "calendar_create_event" for item in pending))
    overlaps = [item["action_id"] for item in pending for event in before
                if item["payload"]["start"] < event["end"] and item["payload"]["end"] > event["start"]]
    check("no block overlaps an existing event", not overlaps)
    check("the calendar is untouched before the decision",
          len(app.get("/api/calendar_intel/status")["day"]["events"]) == len(before))
    if pending:
        print(f"\nTurn 3, resumed: approving {len(pending)} drafted actions")
        started = time.perf_counter()
        resumed = app.post("/api/assistant/resume", {
            "thread_id": thread, "decisions": {item["action_id"]: "approve" for item in pending}})
        resumed["label"] = "3 after it"
        report(resumed, time.perf_counter() - started)
        runs.append(resumed)
        check("the same run resumed and completed",
              resumed["status"] == "completed" and resumed["run_id"] == blocks["run_id"])
        check("approved blocks appear on the calendar",
              len(app.get("/api/calendar_intel/status")["day"]["events"]) == len(before) + len(pending))

    # 4. Focus session and a stated preference
    target = app.get("/api/assistant/tasks")["open"][0]
    focus = turn(app, 4, f"Start a Pomodoro on \"{target['title']}\". Also, from now on keep Friday "
                         "afternoons free of meetings.", thread_id=thread)
    runs.append(focus)
    running = app.get("/api/focus_sessions/status")["running"]
    jobs = app.get("/api/routines/jobs")["jobs"]
    memories = app.get("/api/memory_layer/status")["memories"]["preference"]
    check("a focus session row exists and is tied to the task",
          bool(running) and running["task_id"] == target["task_id"], running["session_id"] if running else "")
    check("a one-shot timer is armed for it", bool(running) and any(
        job["job_id"] == running["job_id"] and job["state"] == "ARMED" and job["kind"] == "pomodoro"
        for job in jobs))
    check("the preference is in long-term memory",
          any("friday" in item["content"].lower() for item in memories),
          "; ".join(item["content"] for item in memories))
    if running:
        app.post("/api/focus_sessions/stop", {"reason": "Stopped by the live check."})

    # 5. Recall in a new session and a new thread
    recall = turn(app, 5, "What should I know before I plan Friday?",
                  thread_id=f"live-{uuid.uuid4().hex[:8]}", session_id="workday-live-check-recall")
    runs.append(recall)
    text = (recall["answer"] or "").lower()
    check("the answer recalls the Friday preference", "friday" in text and "afternoon" in text
          and ("free" in text or "no meetings" in text))
    fresh = app.get(f"/api/assistant/thread/{recall['thread_id']}")
    check("it came from memory, not from the conversation", len(fresh["messages"]) == 2)

    if args.focus_seconds:
        print(f"\nTimer: a compressed focus session of {args.focus_seconds} s")
        started = app.post("/api/focus_sessions/start", {"task_id": target["task_id"],
                                                        "demo_seconds": args.focus_seconds})
        deadline = time.monotonic() + args.focus_seconds + 20
        note = None
        while time.monotonic() < deadline and note is None:
            time.sleep(0.5)
            note = next((item for item in app.get("/api/notifications")["notifications"]
                         if item["job_id"] == started["job"]["job_id"]), None)
        check("the timer fired and produced a notification", note is not None, note["body"] if note else "")

    print("\nSummary")
    print("    Seconds are wall time for that request. Calls and tokens are totals for the run so far,")
    print("    so the two rows of turn 3 describe one run before and after the approval gate.")
    print(f"    {'turn':<16}{'status':<20}{'seconds':>8}{'model calls':>13}{'tools':>7}{'input':>9}"
          f"{'output':>8}{'cache read':>12}")
    for outcome in runs:
        tokens = outcome["trace"]["tokens"]
        print(f"    {outcome['label']:<16}{outcome['status']:<20}{outcome['seconds']:>8}"
              f"{outcome['trace']['model_calls']:>13}{len(outcome['trace']['tool_calls']):>7}"
              f"{tokens.get('input_tokens', 0):>9}{tokens.get('output_tokens', 0):>8}"
              f"{tokens.get('cache_read_tokens', 0):>12}")
    failed = [name for name, passed, _ in CHECKS if not passed]
    print(f"\n{len(CHECKS) - len(failed)} of {len(CHECKS)} anchors held." + (
        " Failed: " + "; ".join(failed) if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
