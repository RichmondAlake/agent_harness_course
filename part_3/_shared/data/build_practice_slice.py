"""Build the practice workspace slice from public Hugging Face datasets.

Nothing in the practice workspace is hand-written. This script selects a real
mailbox and period from the Enron email corpus, adds real prompt-injection
emails from Microsoft's LLMail-Inject challenge, and writes one small
compressed file with full provenance:

    part_3/_shared/data/practice_slice.json.gz

Sources, pinned by revision so the slice is reproducible:

    corbt/enron-emails                  (Enron corpus, 517,401 messages)
    microsoft/llmail-inject-challenge   (MIT licence)

Run it once; learners never need to. The loader reads the committed slice.

    python build_practice_slice.py                 # read from the Hub with pandas
    python build_practice_slice.py --parquet DIR   # use downloaded shards
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

ENRON = {"dataset": "corbt/enron-emails",
         "revision": "cfc06c758093d90993abce1a43668fb7357258a6"}
LLMAIL = {"dataset": "microsoft/llmail-inject-challenge",
          "revision": "1063bdf01ec8762b812d5e06ee768a06faa5a6f7", "licence": "MIT"}
OUTPUT = Path(os.environ.get("PPA_SLICE_OUTPUT") or
              Path(__file__).resolve().parent / "practice_slice.json.gz")

RECEIVED_FOLDERS = ("inbox", "notes_inbox")
SENT_FOLDERS = ("sent", "sent_items", "_sent_mail")
PREFIX = re.compile(r"^\s*((re|fw|fwd|updated|canceled|accepted|declined|tentative)\s*:\s*)+", re.I)


def normalise_subject(subject: str) -> str:
    return re.sub(r"\s+", " ", PREFIX.sub("", subject or "")).strip().lower()


def domain(address: str) -> str:
    return address.rsplit("@", 1)[-1].lower() if "@" in address else ""


def clean_addresses(values) -> list[str]:
    return [item.strip().lower() for item in (values or []) if item and "@" in item]


def enron_source(parquet_dir: str | None) -> str:
    if parquet_dir:
        return Path(parquet_dir).as_posix()
    return f"hf://datasets/{ENRON['dataset']}@{ENRON['revision']}/data"


def read_mailbox(mailbox: str, start: str, end: str, sent_start: str, parquet_dir: str | None):
    """Read one mailbox with pandas. The filters let the reader skip every block of rows
    that cannot contain the mailbox, so only a few megabytes are downloaded."""
    import pandas as pd

    box = pd.read_parquet(
        enron_source(parquet_dir),
        columns=["message_id", "subject", "from", "to", "cc", "date", "body", "file_name"],
        filters=[("file_name", ">=", f"{mailbox}/"), ("file_name", "<", f"{mailbox}0")])
    box = box.rename(columns={"from": "sender", "to": "recipients"})
    box["folder"] = box.file_name.str.split("/").str[1]
    box["stamp"] = box.date.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    names = ["message_id", "subject", "sender", "recipients", "cc", "stamp", "body", "folder"]

    def moment(value: str):
        return pd.Timestamp(value).tz_convert("UTC")

    def rows(low: str, high: str, folders: tuple[str, ...]) -> list[dict]:
        part = box[(box.date >= moment(low)) & (box.date < moment(high)) & box.folder.isin(folders)]
        unique = {}
        for record in part[names].to_dict("records"):
            for field in ("recipients", "cc"):
                record[field] = [] if record[field] is None else list(record[field])
            unique.setdefault(record["message_id"], record)
        return sorted(unique.values(), key=lambda item: (item["stamp"], item["message_id"]))

    return rows(start, end, RECEIVED_FOLDERS), rows(sent_start, end, SENT_FOLDERS)


def apply_hygiene(received: list[dict], owner_domain: str, owner: str) -> tuple[list[dict], dict]:
    """Keep external mail only when a colleague also wrote on the same thread.

    A thread between the owner and outside people, in which no colleague ever
    wrote, is most likely private correspondence. It is left out of the
    practice slice. Mail from the owner's own organisation is always kept.
    """
    internal_threads = {normalise_subject(item["subject"]) for item in received
                        if domain(item["sender"]) == owner_domain and item["sender"] != owner}
    kept, dropped = [], []
    for item in received:
        thread = normalise_subject(item["subject"])
        if domain(item["sender"]) == owner_domain or (thread and thread in internal_threads):
            kept.append(item)
        else:
            dropped.append(item["message_id"])
    return kept, {"rule": "external mail is kept only on threads where a colleague also wrote",
                  "received_before": len(received), "received_after": len(kept),
                  "dropped_private_external": len(dropped)}


def select_injections(count: int) -> list[dict]:
    """Pick real attacks that triggered the send tool in the original challenge."""
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(LLMAIL["dataset"], "data/labelled_unique_submissions_phase2.json",
                           repo_type="dataset", revision=LLMAIL["revision"])
    labelled = json.loads(Path(path).read_text(encoding="utf-8"))
    pattern = re.compile(r"^Subject of the email:\s*(?P<subject>.*?)\.\s+Body:\s*(?P<body>.*)$", re.S)
    chosen = []
    for text, label in labelled.items():
        match = pattern.match(text)
        if not match or label.get("reason") != "api_triggered":
            continue
        subject, body = match["subject"].strip(), match["body"].strip()
        if not (8 <= len(subject) <= 90 and 300 <= len(body) <= 1100 and text.isascii()):
            continue
        digest = hashlib.sha256(text.encode()).hexdigest()
        chosen.append((digest, {"source_sha256": digest, "subject": subject, "body": body,
                                "label": label}))
    chosen.sort(key=lambda pair: pair[0])
    return [item for _, item in chosen[:count]]


def benign_probe() -> list[dict]:
    """The challenge's benign emails: a false-positive test set for the tripwire."""
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(LLMAIL["dataset"], "data/emails_for_fp_tests.json",
                           repo_type="dataset", revision=LLMAIL["revision"])
    pattern = re.compile(r"^Subject of the email:\s*(?P<subject>.*?)\.\s+Body:\s*(?P<body>.*)$", re.S)
    rows = []
    for text in json.loads(Path(path).read_text(encoding="utf-8")):
        match = pattern.match(text)
        if match:
            rows.append({"subject": match["subject"].strip(), "body": match["body"].strip()})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--mailbox", default="nemec-g")
    parser.add_argument("--start", default="2001-07-01 00:00:00+00")
    parser.add_argument("--end", default="2001-09-01 00:00:00+00")
    parser.add_argument("--sent-start", default="2001-04-01 00:00:00+00")
    parser.add_argument("--injections", type=int, default=3)
    parser.add_argument("--scenario-now", default="2001-08-07T08:30",
                        help="Default practice clock, in the mailbox owner's local time.")
    parser.add_argument("--parquet", default=None, help="Folder holding the Enron parquet shards.")
    args = parser.parse_args()

    received, sent = read_mailbox(args.mailbox, args.start, args.end, args.sent_start, args.parquet)
    for item in received + sent:
        item["recipients"] = clean_addresses(item["recipients"])
        item["cc"] = clean_addresses(item["cc"])
        item["sender"] = item["sender"].strip().lower()
    owner = max({item["sender"] for item in sent},
                key=lambda address: sum(item["sender"] == address for item in sent))
    sent = [item for item in sent if item["sender"] == owner]
    received = [item for item in received if item["sender"] != owner]
    received, hygiene = apply_hygiene(received, domain(owner), owner)

    payload = {
        "meta": {
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sources": {"mail": ENRON, "injections": LLMAIL},
            "mailbox": args.mailbox, "owner_email": owner,
            "received_window": [args.start, args.end],
            "sent_window": [args.sent_start, args.end],
            "received_folders": RECEIVED_FOLDERS, "sent_folders": SENT_FOLDERS,
            "hygiene": hygiene,
            "scenario": {"now": args.scenario_now,
                         "note": "Default practice clock, local to the mailbox owner."},
            "counts": {"received": len(received), "sent": len(sent)},
        },
        "received": received,
        "sent": sent,
        "injections": select_injections(args.injections),
        "benign_probe": benign_probe(),
    }
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    payload["meta"]["content_sha256"] = hashlib.sha256(body).hexdigest()
    OUTPUT.write_bytes(gzip.compress(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"), mtime=0))
    print(json.dumps({**payload["meta"], "injections": len(payload["injections"]),
                      "benign_probe": len(payload["benign_probe"]),
                      "file": OUTPUT.name, "bytes": OUTPUT.stat().st_size}, indent=2))


if __name__ == "__main__":
    main()
