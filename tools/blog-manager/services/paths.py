from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


ARTICLE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)*$")


@dataclass(frozen=True)
class BlogPaths:
    root: Path

    @classmethod
    def discover(cls, explicit_root: str | Path | None = None) -> "BlogPaths":
        configured = explicit_root or os.environ.get("BLOG_MANAGER_ROOT")
        root = Path(configured).expanduser() if configured else Path(__file__).resolve().parents[3]
        root = root.resolve()
        if not (root / "package.json").is_file() or not (root / "src" / "content.config.ts").is_file():
            raise RuntimeError(f"Not a supported blog root: {root}")
        return cls(root=root)

    @property
    def articles(self) -> Path:
        return self.root / "src" / "content" / "posts"

    @property
    def open_source(self) -> Path:
        return self.root / "src" / "data" / "open-source.json"

    def ensure_inside(self, candidate: Path, *, parent: Path | None = None) -> Path:
        resolved = candidate.resolve()
        boundary = (parent or self.root).resolve()
        try:
            resolved.relative_to(boundary)
        except ValueError as exc:
            raise ValueError("Path escapes the blog directory") from exc
        return resolved

    def article_path(self, article_id: str, suffix: str | None = None) -> Path:
        normalized = article_id.strip().replace("\\", "/").strip("/")
        if not normalized or not ARTICLE_ID_RE.fullmatch(normalized) or ".." in normalized.split("/"):
            raise ValueError("Invalid article slug")
        if suffix is None:
            for extension in (".md", ".mdx"):
                candidate = self.ensure_inside(self.articles / f"{normalized}{extension}", parent=self.articles)
                if candidate.is_file():
                    return candidate
            raise FileNotFoundError(f"Article not found: {normalized}")
        if suffix not in {".md", ".mdx"}:
            raise ValueError("Only .md and .mdx files are supported")
        return self.ensure_inside(self.articles / f"{normalized}{suffix}", parent=self.articles)
