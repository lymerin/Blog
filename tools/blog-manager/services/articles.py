from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from .paths import BlogPaths


FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
REQUIRED_FIELDS = ("title", "description", "pubDate")
EDITABLE_FIELDS = (
    "title",
    "description",
    "pubDate",
    "tags",
    "updatedDate",
    "author",
    "recommend",
    "postType",
    "coverLayout",
    "pinned",
    "draft",
    "license",
)


@dataclass
class ParsedArticle:
    metadata: dict[str, Any]
    body: str
    has_frontmatter: bool
    newline: str


def _serializable(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [_serializable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serializable(item) for key, item in value.items()}
    return value


def parse_article(text: str) -> ParsedArticle:
    newline = "\r\n" if "\r\n" in text else "\n"
    match = FRONTMATTER_RE.match(text)
    if not match:
        return ParsedArticle(metadata={}, body=text, has_frontmatter=False, newline=newline)
    loaded = yaml.safe_load(match.group(1)) or {}
    if not isinstance(loaded, dict):
        raise ValueError("Frontmatter must be a YAML mapping")
    return ParsedArticle(metadata=_serializable(loaded), body=text[match.end() :], has_frontmatter=True, newline=newline)


def validate_metadata(metadata: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if not str(metadata.get(field, "")).strip():
            errors.append(f"{field} is required")
    for field in ("pubDate", "updatedDate"):
        value = metadata.get(field)
        if value:
            try:
                date.fromisoformat(str(value)[:10])
            except ValueError:
                errors.append(f"{field} must use YYYY-MM-DD")
    tags = metadata.get("tags", [])
    if tags is not None and (not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags)):
        errors.append("tags must be a list of strings")
    if metadata.get("postType") not in {None, "", "metaOnly", "coverSplit", "coverTop"}:
        errors.append("postType is invalid")
    if metadata.get("coverLayout") not in {None, "", "left", "right"}:
        errors.append("coverLayout is invalid")
    return errors


def render_article(metadata: dict[str, Any], body: str, newline: str = "\n") -> str:
    clean = {key: value for key, value in metadata.items() if value not in (None, "")}
    yaml_text = yaml.safe_dump(clean, allow_unicode=True, sort_keys=False, default_flow_style=False).rstrip("\n")
    yaml_text = yaml_text.replace("\n", newline)
    return f"---{newline}{yaml_text}{newline}---{newline}{body}"


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


class ArticleService:
    def __init__(self, paths: BlogPaths):
        self.paths = paths

    def list_articles(self) -> list[dict[str, Any]]:
        articles: list[dict[str, Any]] = []
        for path in sorted(self.paths.articles.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".md", ".mdx"}:
                continue
            parsed = parse_article(path.read_text(encoding="utf-8-sig"))
            article_id = path.relative_to(self.paths.articles).with_suffix("").as_posix()
            metadata = parsed.metadata
            articles.append(
                {
                    "id": article_id,
                    "slug": article_id,
                    "path": str(path),
                    "suffix": path.suffix.lower(),
                    "title": metadata.get("title") or path.stem,
                    "description": metadata.get("description", ""),
                    "pubDate": str(metadata.get("pubDate", "")),
                    "tags": metadata.get("tags") or [],
                    "draft": bool(metadata.get("draft", False)),
                    "metadata": metadata,
                    "hasFrontmatter": parsed.has_frontmatter,
                }
            )
        return sorted(articles, key=lambda item: (item["pubDate"], item["title"]), reverse=True)

    def get_article(self, article_id: str) -> dict[str, Any]:
        path = self.paths.article_path(article_id)
        parsed = parse_article(path.read_text(encoding="utf-8-sig"))
        return {
            "id": article_id,
            "slug": article_id,
            "path": str(path),
            "suffix": path.suffix.lower(),
            "metadata": parsed.metadata,
            "body": parsed.body,
            "newline": parsed.newline,
            "hasFrontmatter": parsed.has_frontmatter,
        }

    def save_article(self, article_id: str, new_slug: str, updates: dict[str, Any]) -> tuple[str, str]:
        source = self.paths.article_path(article_id)
        parsed = parse_article(source.read_text(encoding="utf-8-sig"))
        metadata = dict(parsed.metadata)
        for field in EDITABLE_FIELDS:
            if field in updates:
                value = updates[field]
                if value in (None, "") and field not in REQUIRED_FIELDS:
                    metadata.pop(field, None)
                else:
                    metadata[field] = value
        errors = validate_metadata(metadata)
        if errors:
            raise ValueError("; ".join(errors))
        destination = self.paths.article_path(new_slug, source.suffix)
        if destination != source and destination.exists():
            raise FileExistsError(f"Article already exists: {new_slug}")
        atomic_write_text(destination, render_article(metadata, parsed.body, parsed.newline))
        if destination != source:
            source.unlink()
        return article_id, new_slug

    def inspect_import(self, filename: str, text: str) -> dict[str, Any]:
        suffix = Path(filename).suffix.lower()
        if suffix not in {".md", ".mdx"}:
            raise ValueError("Only .md and .mdx files are supported")
        parsed = parse_article(text)
        proposed = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(filename).stem).strip("-.").lower() or "article"
        errors = validate_metadata(parsed.metadata)
        return {
            "filename": Path(filename).name,
            "suffix": suffix,
            "slug": proposed,
            "metadata": parsed.metadata,
            "missing": [field for field in REQUIRED_FIELDS if not str(parsed.metadata.get(field, "")).strip()],
            "errors": errors,
            "hasFrontmatter": parsed.has_frontmatter,
            "conflict": self.paths.article_path(proposed, suffix).exists(),
        }

    def import_article(
        self,
        filename: str,
        text: str,
        slug: str,
        metadata: dict[str, Any],
        conflict_action: str,
    ) -> str:
        suffix = Path(filename).suffix.lower()
        parsed = parse_article(text)
        combined = dict(parsed.metadata)
        combined.update(metadata)
        errors = validate_metadata(combined)
        if errors:
            raise ValueError("; ".join(errors))
        destination = self.paths.article_path(slug, suffix)
        if destination.exists():
            if conflict_action == "rename":
                base = slug
                index = 2
                while self.paths.article_path(f"{base}-{index}", suffix).exists():
                    index += 1
                slug = f"{base}-{index}"
                destination = self.paths.article_path(slug, suffix)
            elif conflict_action != "overwrite":
                raise FileExistsError(f"Article already exists: {slug}")
        atomic_write_text(destination, render_article(combined, parsed.body, parsed.newline))
        return slug

    def delete_article(self, article_id: str, confirmation: str) -> None:
        if confirmation != article_id:
            raise ValueError("Deletion confirmation does not match the article slug")
        self.paths.article_path(article_id).unlink()

    def open_article(self, article_id: str) -> Path:
        path = self.paths.article_path(article_id)
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            raise RuntimeError("Open File is currently supported on Windows")
        return path
