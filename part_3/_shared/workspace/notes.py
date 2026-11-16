"""Real notes: a Notion workspace, or a folder of Markdown files.

``notion``
    An internal integration token. The integration sees only the pages the
    owner has shared with it, which is the right default for an assistant.

``folder``
    Plain Markdown files in a local folder, for learners who do not use Notion.

Visibility matters for the approval gate. Notion's API does not say who else
can see a page, so every page the assistant did not create itself is treated
as shared, and editing it needs approval. Unknown visibility is gated.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

NOTION_FIELDS = [
    {"name": "token", "label": "Integration token", "type": "password", "required": True,
     "help": "notion.so/my-integrations, new internal integration, then share a page with it."},
    {"name": "parent_page_id", "label": "Parent page ID", "type": "text", "required": True,
     "help": "New pages are created under this page. Copy the 32-character ID from its URL."},
]
FOLDER_FIELDS = [
    {"name": "path", "label": "Notes folder", "type": "text", "required": True,
     "default": "~/ppa-notes", "help": "Markdown files are read from and written to this folder."},
]
NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _chunks(text: str, size: int = 1800) -> list[str]:
    """Notion limits one rich-text item to 2,000 characters."""
    paragraphs = [part for part in text.split("\n") if part.strip()] or [""]
    return [paragraph[index:index + size] for paragraph in paragraphs
            for index in range(0, max(len(paragraph), 1), size)]


class NotionNotes:
    provider_id = "notion"

    def __init__(self, settings: dict[str, Any]) -> None:
        self.token = settings["token"].strip()
        self.parent = settings["parent_page_id"].strip().replace("-", "")
        self.created_here: set[str] = set()

    def _call(self, method: str, path: str, **payload: Any) -> dict[str, Any]:
        import requests

        response = requests.request(
            method, f"{NOTION_API}/{path}", timeout=30, json=payload or None,
            headers={"Authorization": f"Bearer {self.token}", "Notion-Version": NOTION_VERSION})
        if response.status_code >= 400:
            detail = response.json().get("message", response.text[:200])
            raise RuntimeError(f"Notion returned {response.status_code}: {detail}")
        return response.json()

    def check(self) -> dict[str, Any]:
        page = self._call("GET", f"pages/{self.parent}")
        return {"account": "Notion integration", "parent_page": page["id"]}

    def status(self) -> dict[str, Any]:
        return {"provider": self.provider_id, "connected": True, "account": "Notion integration",
                "detail": "Sees only pages shared with the integration"}

    @staticmethod
    def _title(page: dict[str, Any]) -> str:
        for value in page.get("properties", {}).values():
            if value.get("type") == "title":
                return "".join(part.get("plain_text", "") for part in value["title"]) or "(untitled)"
        return "(untitled)"

    def _summary(self, page: dict[str, Any]) -> dict[str, Any]:
        page_id = page["id"].replace("-", "")
        return {"page_id": page_id, "title": self._title(page),
                "shared": page_id not in self.created_here,
                "last_edited": page.get("last_edited_time", "")}

    def search_pages(self, query: str = "") -> dict:
        found = self._call("POST", "search", query=query, page_size=20,
                           filter={"property": "object", "value": "page"})
        return {"pages": [self._summary(page) for page in found.get("results", [])]}

    def get_page(self, page_id: str) -> dict:
        page_id = page_id.replace("-", "")
        page = self._summary(self._call("GET", f"pages/{page_id}"))
        blocks = self._call("GET", f"blocks/{page_id}/children?page_size=100").get("results", [])
        lines = []
        for block in blocks:
            content = block.get(block.get("type", ""), {})
            text = "".join(part.get("plain_text", "") for part in content.get("rich_text", []))
            if text:
                lines.append(text)
        return {"page": dict(page, body="\n".join(lines))}

    @staticmethod
    def _paragraphs(text: str) -> list[dict[str, Any]]:
        return [{"object": "block", "type": "paragraph",
                 "paragraph": {"rich_text": [{"type": "text", "text": {"content": chunk}}]}}
                for chunk in _chunks(text)][:100]

    def create_page(self, title: str, body: str) -> dict:
        created = self._call(
            "POST", "pages", parent={"page_id": self.parent},
            properties={"title": {"title": [{"type": "text", "text": {"content": title[:200]}}]}},
            children=self._paragraphs(body))
        page_id = created["id"].replace("-", "")
        self.created_here.add(page_id)
        return {"page_id": page_id, "status": "created", "shared": False, "delivery": "real",
                "url": created.get("url", "")}

    def append_to_page(self, page_id: str, text: str) -> dict:
        page_id = page_id.replace("-", "")
        self._call("PATCH", f"blocks/{page_id}/children", children=self._paragraphs(text))
        return {"page_id": page_id, "status": "updated", "delivery": "real",
                "shared": page_id not in self.created_here}

    def share_page(self, page_id: str, email: str) -> dict:
        return {"error": "not_supported", "detail": "Sharing is done by the owner in Notion."}

    def delete_page(self, page_id: str) -> dict:
        return {"error": "not_supported", "detail": "This provider never deletes real pages."}


class FolderNotes:
    provider_id = "folder"

    def __init__(self, settings: dict[str, Any]) -> None:
        self.root = Path(settings.get("path") or "~/ppa-notes").expanduser().resolve()

    def check(self) -> dict[str, Any]:
        self.root.mkdir(parents=True, exist_ok=True)
        return {"account": str(self.root), "pages": len(list(self.root.glob("*.md")))}

    def status(self) -> dict[str, Any]:
        return {"provider": self.provider_id, "connected": True, "account": str(self.root),
                "detail": "Local Markdown files. Nobody else can see them."}

    def _path(self, page_id: str) -> Path:
        target = (self.root / f"{Path(page_id).name}.md").resolve()
        if self.root not in target.parents:
            raise ValueError("A page must stay inside the notes folder")
        return target

    def _summary(self, path: Path) -> dict[str, Any]:
        text = path.read_text(encoding="utf-8")
        heading = re.match(r"#\s+(.+)", text)
        edited = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        return {"page_id": path.stem, "title": heading[1].strip() if heading else path.stem,
                "shared": False, "last_edited": edited.isoformat(timespec="minutes")}

    def search_pages(self, query: str = "") -> dict:
        words = query.lower().split()
        rows = [self._summary(path) for path in sorted(self.root.glob("*.md"))
                if not words or any(word in path.read_text(encoding="utf-8").lower() for word in words)]
        return {"pages": rows}

    def get_page(self, page_id: str) -> dict:
        path = self._path(page_id)
        if not path.exists():
            return {"error": "page_not_found", "page_id": page_id}
        return {"page": dict(self._summary(path), body=path.read_text(encoding="utf-8"))}

    def create_page(self, title: str, body: str) -> dict:
        self.root.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "note"
        path, count = self._path(slug), 1
        while path.exists():
            count += 1
            path = self._path(f"{slug}-{count}")
        path.write_text(f"# {title}\n\n{body.strip()}\n", encoding="utf-8")
        return {"page_id": path.stem, "status": "created", "shared": False, "delivery": "real"}

    def append_to_page(self, page_id: str, text: str) -> dict:
        path = self._path(page_id)
        if not path.exists():
            return {"error": "page_not_found", "page_id": page_id}
        path.write_text(path.read_text(encoding="utf-8").rstrip() + "\n\n" + text.strip() + "\n",
                        encoding="utf-8")
        return {"page_id": page_id, "status": "updated", "shared": False, "delivery": "real"}

    def share_page(self, page_id: str, email: str) -> dict:
        return {"error": "not_supported", "detail": "Local files are not shared by the assistant."}

    def delete_page(self, page_id: str) -> dict:
        return {"error": "not_supported", "detail": "This provider never deletes real notes."}
