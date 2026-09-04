from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.articles import ArticleService, parse_article
from services.open_source import OpenSourceService
from services.paths import BlogPaths


COMPLETE_MARKDOWN = """---
title: Complete article
description: Complete description
pubDate: 2026-09-04
tags:
  - Java
draft: true
---
# Body

Keep this body exactly.
"""


class BlogFixture(unittest.TestCase):
    def setUp(self) -> None:
        test_parent = Path(__file__).resolve().parents[1] / ".test-workspace"
        test_parent.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=test_parent)
        self.root = Path(self.temporary.name)
        (self.root / "package.json").write_text("{}", encoding="utf-8")
        (self.root / "src" / "content" / "posts").mkdir(parents=True)
        (self.root / "src" / "content.config.ts").write_text("// fixture", encoding="utf-8")
        data_dir = self.root / "src" / "data"
        data_dir.mkdir(parents=True)
        (data_dir / "open-source.json").write_text(
            json.dumps(
                [
                    {
                        "slug": "example",
                        "name": "Example",
                        "repository": "https://github.com/example/repo",
                        "description": "Example project",
                        "tags": ["Java"],
                        "contributions": [],
                        "accent": "otel",
                    },
                    {
                        "slug": "second",
                        "name": "Second",
                        "repository": "https://github.com/example/second",
                        "description": "Second project",
                        "tags": [],
                        "contributions": [],
                        "accent": "shenyu",
                    },
                ],
                indent=2,
            ),
            encoding="utf-8",
        )
        self.paths = BlogPaths.discover(self.root)
        self.articles = ArticleService(self.paths)
        self.open_source = OpenSourceService(self.paths)

    def tearDown(self) -> None:
        self.temporary.cleanup()


class ArticleServiceTests(BlogFixture):
    def test_complete_import_and_metadata_edit_preserve_body(self) -> None:
        inspected = self.articles.inspect_import("complete.md", COMPLETE_MARKDOWN)
        self.assertTrue(inspected["hasFrontmatter"])
        self.assertEqual([], inspected["missing"])
        slug = self.articles.import_article("complete.md", COMPLETE_MARKDOWN, "complete", {}, "cancel")
        before = self.articles.get_article(slug)
        self.articles.save_article(
            slug,
            "renamed",
            {"title": "Edited title", "description": "Edited description", "pubDate": "2026-09-05", "tags": ["Java", "Test"], "draft": False},
        )
        after = self.articles.get_article("renamed")
        self.assertEqual(before["body"], after["body"])
        self.assertEqual("Edited title", after["metadata"]["title"])
        self.assertFalse((self.paths.articles / "complete.md").exists())

    def test_missing_frontmatter_can_be_completed(self) -> None:
        markdown = "# Imported body\n\nNo frontmatter yet.\n"
        inspected = self.articles.inspect_import("missing.mdx", markdown)
        self.assertEqual(["title", "description", "pubDate"], inspected["missing"])
        slug = self.articles.import_article(
            "missing.mdx",
            markdown,
            "missing",
            {"title": "Added", "description": "Completed manually", "pubDate": "2026-09-04", "tags": [], "draft": True},
            "cancel",
        )
        article = self.articles.get_article(slug)
        self.assertEqual(markdown, article["body"])
        self.assertEqual("Added", article["metadata"]["title"])

    def test_conflicts_require_explicit_choice(self) -> None:
        self.articles.import_article("complete.md", COMPLETE_MARKDOWN, "same", {}, "cancel")
        with self.assertRaises(FileExistsError):
            self.articles.import_article("complete.md", COMPLETE_MARKDOWN, "same", {}, "cancel")
        renamed = self.articles.import_article("complete.md", COMPLETE_MARKDOWN, "same", {}, "rename")
        self.assertEqual("same-2", renamed)
        overwritten = COMPLETE_MARKDOWN.replace("Complete article", "Replacement")
        self.articles.import_article("complete.md", overwritten, "same", {}, "overwrite")
        self.assertEqual("Replacement", self.articles.get_article("same")["metadata"]["title"])

    def test_delete_requires_exact_confirmation(self) -> None:
        self.articles.import_article("complete.md", COMPLETE_MARKDOWN, "delete-me", {}, "cancel")
        with self.assertRaises(ValueError):
            self.articles.delete_article("delete-me", "yes")
        self.articles.delete_article("delete-me", "delete-me")
        self.assertFalse((self.paths.articles / "delete-me.md").exists())

    def test_path_escape_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.paths.article_path("../outside", ".md")
        with self.assertRaises(ValueError):
            self.paths.article_path("C:/outside", ".md")


class OpenSourceServiceTests(BlogFixture):
    def payload(self, number: int = 10) -> dict[str, object]:
        return {
            "number": number,
            "url": f"https://github.com/example/repo/pull/{number}",
            "title": "Manual PR",
            "mergedAt": "2026-09-04T10:00",
            "author": "tester",
            "issueNumber": 3,
            "issueUrl": "https://github.com/example/repo/issues/3",
            "summaryZhCn": "摘要",
            "summaryZhHk": "摘要",
            "article": "",
        }

    def test_add_edit_issue_and_delete_pr(self) -> None:
        saved = self.open_source.save_contribution("example", self.payload())
        self.assertEqual(10, saved["number"])
        self.assertEqual("2026-09-04T10:00:00Z", saved["mergedAt"])
        updated = self.payload(11)
        updated["issueNumber"] = 4
        updated["issueUrl"] = "https://github.com/example/repo/issues/4"
        self.open_source.save_contribution("second", updated, original_project_slug="example", original_number=10)
        self.assertEqual(0, self.open_source.list_projects()[0]["mergedCount"])
        self.assertEqual(1, self.open_source.list_projects()[1]["mergedCount"])
        self.assertEqual(4, self.open_source.get_contribution("second", 11)["issueNumber"])
        with self.assertRaises(ValueError):
            self.open_source.delete_contribution("second", 11, "yes")
        self.open_source.delete_contribution("second", 11, "PR #11")
        self.assertEqual(0, self.open_source.list_projects()[1]["mergedCount"])

    def test_manual_fallback_allows_missing_issue_and_summary(self) -> None:
        payload = self.payload()
        payload.update(issueNumber="", issueUrl="", summaryZhCn="", summaryZhHk="")
        saved = self.open_source.save_contribution("example", payload)
        self.assertNotIn("issueNumber", saved)
        self.assertEqual("", saved["summary"]["zh-cn"])

    def test_link_change_unlink_and_rename_reference(self) -> None:
        self.articles.import_article("complete.md", COMPLETE_MARKDOWN, "article-one", {}, "cancel")
        self.articles.import_article("complete.md", COMPLETE_MARKDOWN, "article-two", {}, "cancel")
        self.open_source.save_contribution("example", self.payload())
        self.open_source.set_article("example", 10, "article-one")
        self.assertEqual("article-one", self.open_source.get_contribution("example", 10)["article"])
        self.open_source.set_article("example", 10, "article-two")
        self.assertEqual("article-two", self.open_source.get_contribution("example", 10)["article"])
        self.open_source.rename_article_reference("article-two", "article-renamed")
        self.assertEqual("article-renamed", self.open_source.get_contribution("example", 10)["article"])
        self.open_source.set_article("example", 10, None)
        self.assertNotIn("article", self.open_source.get_contribution("example", 10))


if __name__ == "__main__":
    unittest.main()
