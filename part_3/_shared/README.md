# Part 3 shared workspace

**PPA** is a personal productivity assistant. It reads one person's mail and
calendar, decides what deserves attention, turns requests into tracked tasks,
protects time for focused work, and asks before anything reaches another
person.

This folder holds what the appbook, the command line runner and the tests
share: the practice data, the rules that derive a working week from it, the
optional connectors to real accounts, and the gateway that serves all of it
over MCP.

The notebooks do not import from here. Each notebook stands alone and contains
its own copy of the rules, so a learner can read every line it runs. The tests
check that those copies agree with the rules in this folder.

| Path | What it holds |
|---|---|
| `data/practice_slice.json.gz` | One real mailbox, cut from the public datasets below, with its provenance |
| `data/build_practice_slice.py` | Builds that slice from the datasets at pinned revisions |
| `workspace/practice.py` | The practice workspace: the mailbox replayed against a clock |
| `workspace/invitations.py` | Turns meeting invitations found in mail into calendar events |
| `workspace/generated.py` | The generated calendar layer that fills the working week |
| `workspace/contacts.py` | Derives contacts and VIPs from the mail the owner sent |
| `workspace/imap_mail.py`, `calendars.py`, `notes.py` | Optional connectors to real accounts |
| `workspace/gateway.py` | One workspace over swappable providers, with safe mode and an effect log |
| `mcp/workspace_mcp_server.py` | The gateway: three MCP servers and the admin routes the appbook uses |
| `runtime/policy.py` | Governed meanings as pure functions: triage, urgency, free time, time-blocking |
| `demo_script.md` | The canonical scenario and what each turn must prove |

## No sign-in is needed

Everything runs on the practice workspace. Nothing here requires a
Google, Microsoft or Notion account, and nothing requires approval from a
provider.

The connectors to real accounts exist for learners who want to try the
assistant on their own mail after the session. They are optional, and they
have not been tested against live accounts in this repository, because no
account credentials were available when it was built.

## The practice data

| Source | What it provides | Licence |
|---|---|---|
| [`corbt/enron-emails`](https://huggingface.co/datasets/corbt/enron-emails), revision `cfc06c75` | One mailbox: received mail, sent mail and meeting invitations | Public corpus released by the US Federal Energy Regulatory Commission |
| [`microsoft/llmail-inject-challenge`](https://huggingface.co/datasets/microsoft/llmail-inject-challenge), revision `1063bdf0` | Prompt-injection emails that succeeded against a working email assistant | MIT |

The slice holds 321 received messages, 527 sent messages and 3 attack emails.

**The people in the mailbox are real.** The Enron corpus is a standard research
dataset, and it is still other people's correspondence. One rule keeps the
practice data on business mail: a message from outside the owner's organisation is
kept only when a colleague also wrote on the same thread. That rule removed 63
messages from this slice. The assistant is also told never to store the text of
a message in long-term memory.

Nothing about the owner is written in code. The owner is whoever wrote the
mail in the sent folders. The timezone is the one Outlook printed in the
invitations. VIPs are the five people the owner wrote to most in the last 90
days, provided there were at least three messages.

## The clock

The practice workspace replays the mailbox against a clock. Moving the clock
forward makes mail arrive and meetings get announced, as they did. The
assistant never sees a message from its own future.

The scenario opens at 08:30 on Tuesday 7 August 2001, in the owner's timezone.
The focus timer is the one exception: it uses the real clock, because a real
job has to fire.

## What the assistant writes

Drafts, sent mail, events, answers to invitations and pages are held in memory
by the practice workspace, so a notebook starts from the same mailbox every
time. Set `PPA_PRACTICE_STATE` to a file path, or pass `state_path`, and the
same writes are kept in that file and read back on the next start. The appbook
does this, so an approved event survives a restart. A reset empties the file.

## The calendar has two layers

| Layer | Where it comes from | `source` |
|---|---|---|
| Invitations | Real meeting invitations in the mailbox. An update replaces the event and a cancellation removes it | `invitation` |
| Generated | Working sessions that fill the week, made by one rule | `generated` |

Invitations that travel by email are only part of a calendar, and the scenario
week holds two of them. The generated layer makes the week busy enough to
test time-blocking and the over-booked rule.

The rule: for each week, the threads the owner wrote on most during the
fortnight before each get one working session, in a fixed weekly pattern. The
title is the real subject of the thread, and the event points at that thread.
The owner is the only attendee, so no real person is placed in a meeting that
never happened. A generated session that overlaps an invitation is dropped.

The layer is off by default in this folder, so existing tests keep their
meaning. Switch it on with `PracticeWorkspace(generated_calendar=True)` or
`PPA_GENERATED_CALENDAR=1`. The appbook switches it on.

## Real accounts, when you want them

| System | Connector | What it can do |
|---|---|---|
| Mail | IMAP and SMTP with an app password | Read without marking as read. Save a draft. Send only after approval |
| Calendar | An ICS address, or Google Calendar | Read events. Create an event only after approval |
| Notes | A folder of Markdown files, or Notion | Read and create pages. Append only after approval when a page is shared |

Two rules hold for every connector.

- **Nothing is deleted or moved.** No connector can trash a message, delete an
  event or remove a page.
- **Safe mode is on by default.** An approved message leaves only when every
  recipient is the owner. Anything addressed to another person is saved as a
  draft. An approved event is created without other attendees.

Credentials are stored in one file under `PPA_HOME`, readable only by your
user account. They are never returned by the gateway and never logged.

## Tests

```bash
cd part_3
../part_2/custom_harness/.venv/bin/python -m pytest -q custom_harness/appbook/tests
```

The tests state rules, not hand-picked answers, because the data is real. A
rule such as *an unknown sender never outranks a known person* must hold for
whatever the mailbox contains.
