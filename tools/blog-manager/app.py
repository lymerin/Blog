from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.serving import make_server

from services.articles import ArticleService
from services.github_api import GitHubFetchError, fetch_pull_request
from services.open_source import OpenSourceService
from services.paths import BlogPaths
from services.processes import BlogProcessService


def _form_metadata(form: Any) -> dict[str, Any]:
    tags = [tag.strip() for tag in str(form.get("tags", "")).split(",") if tag.strip()]
    return {
        "title": str(form.get("title", "")).strip(),
        "description": str(form.get("description", "")).strip(),
        "pubDate": str(form.get("pubDate", "")).strip(),
        "tags": tags,
        "updatedDate": str(form.get("updatedDate", "")).strip(),
        "author": str(form.get("author", "")).strip(),
        "recommend": form.get("recommend") == "on",
        "postType": str(form.get("postType", "")).strip(),
        "coverLayout": str(form.get("coverLayout", "")).strip(),
        "pinned": form.get("pinned") == "on",
        "draft": form.get("draft") == "on",
        "license": str(form.get("license", "")).strip(),
    }


def _form_contribution(form: Any) -> dict[str, Any]:
    return {
        "number": form.get("number"),
        "url": form.get("url"),
        "title": form.get("title"),
        "mergedAt": form.get("mergedAt"),
        "author": form.get("author"),
        "issueNumber": form.get("issueNumber"),
        "issueUrl": form.get("issueUrl"),
        "summaryZhCn": form.get("summaryZhCn"),
        "summaryZhHk": form.get("summaryZhHk"),
        "article": form.get("article"),
    }


def create_app(blog_root: str | Path | None = None) -> Flask:
    app = Flask(__name__)
    app.secret_key = os.urandom(24)
    paths = BlogPaths.discover(blog_root)
    articles = ArticleService(paths)
    open_source = OpenSourceService(paths)
    processes = BlogProcessService(paths.root)
    app.config.update(BLOG_PATHS=paths, ARTICLES=articles, OPEN_SOURCE=open_source, PROCESSES=processes)

    @app.before_request
    def csrf_protect():
        token = session.setdefault("csrf_token", secrets.token_urlsafe(32))
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
            if not supplied or not secrets.compare_digest(token, supplied):
                return jsonify({"ok": False, "error": "Invalid or missing CSRF token"}), 400

    @app.context_processor
    def shared_context() -> dict[str, Any]:
        return {"blog_root": str(paths.root), "csrf_token": session["csrf_token"]}

    @app.get("/")
    def dashboard():
        article_rows = articles.list_articles()
        relations = open_source.relations()
        stats = {
            "articles": len(article_rows),
            "published": sum(not item["draft"] for item in article_rows),
            "drafts": sum(item["draft"] for item in article_rows),
            "prs": len(relations),
            "unlinked": sum(not item["contribution"].get("article") for item in relations),
        }
        return render_template("dashboard.html", stats=stats)

    @app.get("/articles")
    def article_list():
        query = request.args.get("q", "").strip().lower()
        status = request.args.get("status", "all")
        rows = articles.list_articles()
        if query:
            rows = [row for row in rows if query in row["title"].lower() or query in row["slug"].lower()]
        if status == "draft":
            rows = [row for row in rows if row["draft"]]
        elif status == "published":
            rows = [row for row in rows if not row["draft"]]
        relation_rows = open_source.relations()
        related = {
            row["id"]: [item for item in relation_rows if item["contribution"].get("article") == row["id"]] for row in rows
        }
        return render_template("articles.html", articles=rows, related=related, query=query, status=status)

    @app.route("/articles/<path:article_id>/edit", methods=["GET", "POST"])
    def article_edit(article_id: str):
        article = articles.get_article(article_id)
        if request.method == "POST":
            new_slug = request.form.get("slug", article_id).strip()
            try:
                old_id, new_id = articles.save_article(article_id, new_slug, _form_metadata(request.form))
                open_source.rename_article_reference(old_id, new_id)
                flash("Article metadata saved.", "success")
                return redirect(url_for("article_edit", article_id=new_id))
            except (ValueError, FileExistsError) as exc:
                flash(str(exc), "error")
        relation_rows = [item for item in open_source.relations() if item["contribution"].get("article") == article_id]
        return render_template("article_edit.html", article=article, relations=relation_rows)

    @app.post("/articles/<path:article_id>/open")
    def article_open(article_id: str):
        try:
            articles.open_article(article_id)
            flash("Opened with the Windows default application.", "success")
        except (ValueError, FileNotFoundError, RuntimeError, OSError) as exc:
            flash(str(exc), "error")
        return redirect(request.referrer or url_for("article_list"))

    @app.post("/articles/<path:article_id>/delete")
    def article_delete(article_id: str):
        try:
            articles.delete_article(article_id, request.form.get("confirmation", ""))
            open_source.unlink_article(article_id)
            flash("Article deleted.", "success")
        except (ValueError, FileNotFoundError) as exc:
            flash(str(exc), "error")
        return redirect(url_for("article_list"))

    @app.get("/import")
    def import_page():
        return render_template("import.html")

    @app.post("/api/import/inspect")
    def import_inspect():
        upload = request.files.get("file")
        if upload is None or not upload.filename:
            return jsonify({"ok": False, "error": "Choose a Markdown file first."}), 400
        try:
            text = upload.read(10 * 1024 * 1024 + 1)
            if len(text) > 10 * 1024 * 1024:
                raise ValueError("Markdown files larger than 10 MB are not supported")
            result = articles.inspect_import(upload.filename, text.decode("utf-8-sig"))
            return jsonify({"ok": True, **result})
        except (UnicodeDecodeError, ValueError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.post("/api/import/commit")
    def import_commit():
        upload = request.files.get("file")
        if upload is None or not upload.filename:
            return jsonify({"ok": False, "error": "Choose a Markdown file first."}), 400
        try:
            text = upload.read(10 * 1024 * 1024 + 1).decode("utf-8-sig")
            conflict_action = request.form.get("conflictAction", "cancel")
            if conflict_action == "overwrite" and request.form.get("overwriteConfirmed") != "1":
                raise ValueError("Overwrite requires explicit confirmation")
            slug = articles.import_article(
                upload.filename,
                text,
                request.form.get("slug", ""),
                _form_metadata(request.form),
                conflict_action,
            )
            return jsonify({"ok": True, "slug": slug, "redirect": url_for("article_edit", article_id=slug)})
        except (UnicodeDecodeError, ValueError, FileExistsError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.get("/open-source")
    def open_source_list():
        return render_template("open_source.html", projects=open_source.list_projects())

    @app.get("/open-source/<project_slug>")
    def open_source_project(project_slug: str):
        try:
            project = open_source.get_project(project_slug)
        except KeyError as exc:
            return str(exc), 404
        return render_template("open_source_project.html", project=project)

    @app.route("/open-source/add", methods=["GET", "POST"])
    def contribution_add():
        projects = open_source.list_projects()
        if request.method == "POST":
            project_slug = request.form.get("project", "")
            article_id = request.form.get("article", "")
            article_ids = {item["id"] for item in articles.list_articles()}
            try:
                if article_id and article_id not in article_ids:
                    raise ValueError("Choose an existing article")
                saved = open_source.save_contribution(project_slug, _form_contribution(request.form))
                flash(f"PR #{saved['number']} added.", "success")
                return redirect(url_for("open_source_project", project_slug=project_slug))
            except (ValueError, FileExistsError, KeyError) as exc:
                flash(str(exc), "error")
        return render_template(
            "contribution_form.html",
            mode="add",
            projects=projects,
            articles=articles.list_articles(),
            selected_project=request.args.get("project", ""),
            contribution={},
        )

    @app.route("/open-source/<project_slug>/<int:number>/edit", methods=["GET", "POST"])
    def contribution_edit(project_slug: str, number: int):
        try:
            contribution = open_source.get_contribution(project_slug, number)
        except KeyError as exc:
            return str(exc), 404
        if request.method == "POST":
            target_project = request.form.get("project", project_slug)
            article_id = request.form.get("article", "")
            article_ids = {item["id"] for item in articles.list_articles()}
            try:
                if article_id and article_id not in article_ids:
                    raise ValueError("Choose an existing article")
                saved = open_source.save_contribution(
                    target_project,
                    _form_contribution(request.form),
                    original_project_slug=project_slug,
                    original_number=number,
                )
                flash(f"PR #{saved['number']} saved.", "success")
                return redirect(url_for("open_source_project", project_slug=target_project))
            except (ValueError, FileExistsError, KeyError) as exc:
                flash(str(exc), "error")
        return render_template(
            "contribution_form.html",
            mode="edit",
            projects=open_source.list_projects(),
            articles=articles.list_articles(),
            selected_project=project_slug,
            contribution=contribution,
        )

    @app.post("/open-source/<project_slug>/<int:number>/delete")
    def contribution_delete(project_slug: str, number: int):
        try:
            open_source.delete_contribution(project_slug, number, request.form.get("confirmation", ""))
            flash(f"PR #{number} deleted.", "success")
        except (ValueError, KeyError) as exc:
            flash(str(exc), "error")
        return redirect(url_for("open_source_project", project_slug=project_slug))

    @app.post("/api/github/fetch")
    def github_fetch():
        payload = request.get_json(silent=True) or {}
        try:
            fetched = fetch_pull_request(str(payload.get("url") or ""), os.environ.get("GITHUB_TOKEN"))
            repository = str(fetched.get("repository") or "").rstrip("/").lower()
            project = next(
                (item for item in open_source.list_projects() if str(item.get("repository", "")).rstrip("/").lower() == repository),
                None,
            )
            return jsonify({"ok": True, "project": project.get("slug") if project else "", **fetched})
        except (ValueError, GitHubFetchError) as exc:
            return jsonify({"ok": False, "error": str(exc), "manual": True}), 400

    @app.get("/relations")
    def relations():
        relation_filter = request.args.get("filter", "all")
        rows = open_source.relations()
        if relation_filter == "linked":
            rows = [row for row in rows if row["contribution"].get("article")]
        elif relation_filter == "unlinked":
            rows = [row for row in rows if not row["contribution"].get("article")]
        return render_template("relations.html", rows=rows, articles=articles.list_articles(), relation_filter=relation_filter)

    @app.post("/relations/<project_slug>/<int:number>")
    def relation_update(project_slug: str, number: int):
        article_id = "" if request.form.get("unlink") == "1" else request.form.get("article", "").strip()
        article_ids = {item["id"] for item in articles.list_articles()}
        try:
            if article_id and article_id not in article_ids:
                raise ValueError("Choose an existing article")
            open_source.set_article(project_slug, number, article_id or None)
            flash("Relation updated.", "success")
        except (ValueError, KeyError) as exc:
            flash(str(exc), "error")
        return redirect(url_for("relations", filter=request.args.get("filter", "all")))

    @app.get("/preview")
    def preview_page():
        return render_template("preview.html", status=processes.preview_status())

    @app.get("/api/preview/status")
    def preview_status():
        return jsonify({"ok": True, **processes.preview_status()})

    @app.post("/api/preview/start")
    def preview_start():
        try:
            return jsonify({"ok": True, **processes.start_preview()})
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc), **processes.preview_status()}), 400

    @app.post("/api/preview/stop")
    def preview_stop():
        return jsonify({"ok": True, **processes.stop_preview()})

    @app.post("/api/build")
    def build_blog():
        try:
            return jsonify({"ok": True, **processes.build()})
        except (RuntimeError, OSError) as exc:
            return jsonify({"ok": False, "success": False, "output": str(exc)}), 500

    return app


class LocalServer:
    def __init__(self, app: Flask, host: str, port: int):
        self.server = make_server(host, port, app, threaded=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=3)


def _available_port(preferred: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            probe.bind(("127.0.0.1", 0))
            return int(probe.getsockname()[1])


def main() -> None:
    parser = argparse.ArgumentParser(description="Local Blog Manager")
    parser.add_argument("--blog-root", help="Path to the Astro blog root")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--browser", action="store_true", help="Use the system browser instead of pywebview")
    parser.add_argument("--serve", action="store_true", help="Run the local Flask server without opening a window")
    args = parser.parse_args()
    configured_root = args.blog_root
    if not configured_root and getattr(sys, "frozen", False):
        config_path = Path(sys.executable).resolve().parent / "blog-manager.json"
        if config_path.is_file():
            configured_root = json.loads(config_path.read_text(encoding="utf-8")).get("blogRoot")
    app = create_app(configured_root)
    port = _available_port(args.port)
    url = f"http://127.0.0.1:{port}/"
    if args.serve:
        app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
        return
    if args.browser:
        webbrowser.open(url)
        app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
        return
    try:
        import webview
    except ImportError:
        webbrowser.open(url)
        app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
        return
    server = LocalServer(app, "127.0.0.1", port)
    server.start()
    try:
        webview.create_window("Blog Manager", url, width=1180, height=780, min_size=(900, 620))
        webview.start()
    finally:
        app.config["PROCESSES"].stop_preview()
        server.stop()


if __name__ == "__main__":
    main()
