from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .paths import BlogPaths


def _atomic_write_json(path: Path, data: list[dict[str, Any]]) -> None:
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _github_url(value: str, kind: str) -> str:
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in {"github.com", "www.github.com"}:
        raise ValueError(f"{kind} must be an https://github.com URL")
    return value


class OpenSourceService:
    def __init__(self, paths: BlogPaths):
        self.paths = paths

    def load(self) -> list[dict[str, Any]]:
        data = json.loads(self.paths.open_source.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("Open Source data must be a JSON array")
        return data

    def save(self, projects: list[dict[str, Any]]) -> None:
        _atomic_write_json(self.paths.open_source, projects)

    def list_projects(self) -> list[dict[str, Any]]:
        projects = deepcopy(self.load())
        for project in projects:
            project["mergedCount"] = len(project.get("contributions", []))
        return projects

    def get_project(self, slug: str, projects: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        for project in projects or self.load():
            if project.get("slug") == slug:
                return project
        raise KeyError(f"Unknown Open Source project: {slug}")

    def get_contribution(self, project_slug: str, number: int) -> dict[str, Any]:
        project = self.get_project(project_slug)
        for contribution in project.get("contributions", []):
            if int(contribution.get("number", 0)) == int(number):
                return deepcopy(contribution)
        raise KeyError(f"PR #{number} was not found")

    def _validated_contribution(self, payload: dict[str, Any]) -> dict[str, Any]:
        number = int(payload.get("number") or 0)
        if number <= 0:
            raise ValueError("PR number must be a positive integer")
        title = str(payload.get("title") or "").strip()
        merged_at = str(payload.get("mergedAt") or "").strip()
        if not title or not merged_at:
            raise ValueError("PR title and merged date are required")
        try:
            parsed_merged_at = datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Merged date must be a valid ISO date and time") from exc
        if parsed_merged_at.tzinfo is None:
            merged_at = f"{parsed_merged_at.isoformat(timespec='seconds')}Z"
        else:
            merged_at = parsed_merged_at.isoformat(timespec="seconds").replace("+00:00", "Z")
        contribution: dict[str, Any] = {
            "number": number,
            "title": title,
            "url": _github_url(str(payload.get("url") or ""), "PR URL"),
            "mergedAt": merged_at,
            "summary": {
                "zh-cn": str(payload.get("summaryZhCn") or "").strip(),
                "zh-hk": str(payload.get("summaryZhHk") or payload.get("summaryZhCn") or "").strip(),
            },
        }
        issue_number = payload.get("issueNumber")
        issue_url = str(payload.get("issueUrl") or "").strip()
        if issue_number or issue_url:
            if not issue_number or not issue_url:
                raise ValueError("Issue number and Issue URL must be provided together")
            contribution["issueNumber"] = int(issue_number)
            contribution["issueUrl"] = _github_url(issue_url, "Issue URL")
        author = str(payload.get("author") or "").strip()
        if author:
            contribution["author"] = author
        article = str(payload.get("article") or "").strip()
        if article:
            contribution["article"] = article
        return contribution

    def save_contribution(
        self,
        target_project_slug: str,
        payload: dict[str, Any],
        *,
        original_project_slug: str | None = None,
        original_number: int | None = None,
    ) -> dict[str, Any]:
        projects = self.load()
        target = self.get_project(target_project_slug, projects)
        contribution = self._validated_contribution(payload)
        if original_project_slug is not None and original_number is not None:
            original = self.get_project(original_project_slug, projects)
            original["contributions"] = [
                item for item in original.get("contributions", []) if int(item.get("number", 0)) != int(original_number)
            ]
        if any(int(item.get("number", 0)) == contribution["number"] for item in target.get("contributions", [])):
            raise FileExistsError(f"PR #{contribution['number']} already exists in {target_project_slug}")
        target.setdefault("contributions", []).append(contribution)
        target["contributions"].sort(key=lambda item: str(item.get("mergedAt", "")), reverse=True)
        self.save(projects)
        return contribution

    def delete_contribution(self, project_slug: str, number: int, confirmation: str) -> None:
        expected = f"PR #{number}"
        if confirmation != expected:
            raise ValueError(f"Type {expected} to confirm deletion")
        projects = self.load()
        project = self.get_project(project_slug, projects)
        before = len(project.get("contributions", []))
        project["contributions"] = [item for item in project.get("contributions", []) if int(item.get("number", 0)) != int(number)]
        if len(project["contributions"]) == before:
            raise KeyError(f"PR #{number} was not found")
        self.save(projects)

    def set_article(self, project_slug: str, number: int, article: str | None) -> None:
        projects = self.load()
        project = self.get_project(project_slug, projects)
        for contribution in project.get("contributions", []):
            if int(contribution.get("number", 0)) == int(number):
                if article:
                    contribution["article"] = article
                else:
                    contribution.pop("article", None)
                self.save(projects)
                return
        raise KeyError(f"PR #{number} was not found")

    def rename_article_reference(self, old_id: str, new_id: str) -> None:
        projects = self.load()
        changed = False
        for project in projects:
            for contribution in project.get("contributions", []):
                if contribution.get("article") == old_id:
                    contribution["article"] = new_id
                    changed = True
        if changed:
            self.save(projects)

    def unlink_article(self, article_id: str) -> None:
        projects = self.load()
        changed = False
        for project in projects:
            for contribution in project.get("contributions", []):
                if contribution.get("article") == article_id:
                    contribution.pop("article", None)
                    changed = True
        if changed:
            self.save(projects)

    def relations(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for project in self.load():
            for contribution in project.get("contributions", []):
                result.append({"project": project, "contribution": contribution})
        return result
