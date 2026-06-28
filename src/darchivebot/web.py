from __future__ import annotations

import html
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

from darchivebot.insights import list_insight_notes, show_insight_note
from darchivebot.search import archive_detail, rebuild_search_index, review_queue, search_archive
from darchivebot.storage import ArchiveStore


LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def serve_local_web(store: ArchiveStore, *, host: str = "127.0.0.1", port: int = 8765) -> None:
    if host not in LOCAL_HOSTS:
        raise ValueError("Darchivebot web UI is local-only; use 127.0.0.1, localhost, or ::1")
    handler = make_handler(store)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"darchive local web UI listening on http://{host}:{server.server_port}")
    server.serve_forever()


def make_handler(store: ArchiveStore) -> type[BaseHTTPRequestHandler]:
    class DarchiveWebHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            try:
                if parsed.path == "/":
                    self.respond_html(render_home(store))
                elif parsed.path == "/search":
                    self.respond_html(render_search(store, query))
                elif parsed.path == "/review":
                    self.respond_html(render_review(store, query))
                elif parsed.path.startswith("/captures/"):
                    capture_id = unquote(parsed.path.removeprefix("/captures/"))
                    self.respond_html(render_capture_detail(store, capture_id))
                elif parsed.path == "/insights":
                    self.respond_html(render_insights(store))
                elif parsed.path.startswith("/insights/"):
                    insight_id = unquote(parsed.path.removeprefix("/insights/"))
                    self.respond_html(render_insight_detail(store, insight_id))
                elif parsed.path == "/healthz":
                    self.respond_json({"status": "ok", "local_only": True})
                else:
                    self.respond_html(page("Not found", "<p>Not found.</p>"), HTTPStatus.NOT_FOUND)
            except Exception as exc:  # pragma: no cover - defensive request boundary
                self.respond_html(page("Error", f"<p>{escape(str(exc))}</p>"), HTTPStatus.INTERNAL_SERVER_ERROR)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def respond_html(self, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def respond_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return DarchiveWebHandler


def render_home(store: ArchiveStore) -> str:
    rows = store.list_capture_summaries(30)
    items = []
    for row in rows:
        title = str(row["archive_title"] or row["text"] or row["caption"] or "Untitled capture")
        summary = str(row["archive_core_summary"] or "")
        meta = " / ".join(part for part in [row["archive_primary_interest"], row["archive_topic"], row["status"]] if part)
        items.append(
            card(
                f"<a href='/captures/{quote(str(row['id']))}'>{escape(title)}</a>",
                f"<p>{escape(summary)}</p><p class='meta'>{escape(meta)}</p>",
            )
        )
    content = search_form() + nav_links() + section("Recent archive", "".join(items) or "<p>No captures yet.</p>")
    return page("Darchivebot Local Archive", content)


def render_search(store: ArchiveStore, query: dict[str, list[str]]) -> str:
    q = first(query, "q")
    if first(query, "rebuild"):
        rebuild_search_index(store)
    content = search_form(q) + nav_links()
    if not q:
        return page("Search", content + "<p>Enter a search query.</p>")
    result = search_archive(store, q, limit=int_or_default(first(query, "limit"), 30))
    rows = []
    for item in result["results"]:
        rows.append(
            card(
                f"<a href='/captures/{quote(item['capture_id'])}'>{escape(item['title'])}</a>",
                "<p class='meta'>"
                + escape(" / ".join(part for part in [item["primary_interest"], item["topic"], item["match_explanation"]] if part))
                + "</p>"
                + f"<p>{escape(item.get('snippet') or item['summary'])}</p>",
            )
        )
    content += section(f"Search results for '{escape(q)}'", "".join(rows) or "<p>No results.</p>")
    return page("Search", content)


def render_review(store: ArchiveStore, query: dict[str, list[str]]) -> str:
    mode = first(query, "mode") or "all"
    result = review_queue(
        store,
        limit=int_or_default(first(query, "limit"), 30),
        needs_review_only=mode == "needs-review",
        revisit_only=mode == "revisit",
    )
    tabs = (
        "<div class='tabs'>"
        "<a href='/review'>All</a>"
        "<a href='/review?mode=needs-review'>Needs review</a>"
        "<a href='/review?mode=revisit'>Revisit</a>"
        "</div>"
    )
    cards = []
    for item in result["items"]:
        flags = []
        if item["needs_review"]:
            flags.append("needs review")
        if item["revisit_priority"]:
            flags.append(f"revisit {item['revisit_priority']}")
        cards.append(
            card(
                f"<a href='/captures/{quote(item['capture_id'])}'>{escape(item['title'])}</a>",
                f"<p>{escape(item['summary'])}</p>"
                f"<p class='meta'>{escape(' / '.join(flags + [item['primary_interest'], item['topic']]))}</p>",
            )
        )
    return page("Review", nav_links() + tabs + section(f"Review queue: {escape(result['mode'])}", "".join(cards) or "<p>No review items.</p>"))


def render_capture_detail(store: ArchiveStore, capture_id: str) -> str:
    detail = archive_detail(store, capture_id)
    if detail is None:
        return page("Capture not found", "<p>Capture not found.</p>")
    capture = detail["capture"]
    archive = detail["archive_item"]
    content = nav_links()
    content += section(
        "Source capture",
        f"<p class='meta'>id={escape(capture['id'])} kind={escape(capture['content_kind'])} status={escape(capture['status'])}</p>"
        f"<pre>{escape(capture.get('text') or capture.get('caption') or '')}</pre>",
    )
    if archive:
        fields = [
            ("Summary", archive.get("core_summary") or archive.get("summary")),
            ("Why saved", archive.get("why_saved")),
            ("Interest", archive.get("primary_interest")),
            ("Topic", archive.get("topic")),
            ("Tags", ", ".join(archive.get("tags") or [])),
            ("Revisit", " / ".join(part for part in [archive.get("revisit_priority"), archive.get("revisit_reason")] if part)),
            ("Insight seed", archive.get("insight_seed")),
            ("Needs review", str(archive.get("needs_review")).lower()),
        ]
        body = "".join(f"<dt>{escape(label)}</dt><dd>{escape(value)}</dd>" for label, value in fields if value)
        if archive.get("key_points"):
            body += "<h3>Key points</h3><ul>" + "".join(f"<li>{escape(point)}</li>" for point in archive["key_points"]) + "</ul>"
        if archive.get("questions"):
            body += "<h3>Questions</h3><ul>" + "".join(f"<li>{escape(question)}</li>" for question in archive["questions"]) + "</ul>"
        body += f"<h3>Extracted text</h3><pre>{escape(archive.get('raw_extracted_text') or archive.get('extracted_text') or '')}</pre>"
        content += section("Archive item", f"<h2>{escape(archive['title'])}</h2><dl>{body}</dl>")
    related_cards = []
    for item in detail["related"]:
        related_cards.append(
            card(
                f"<a href='/captures/{quote(item['capture_id'])}'>{escape(item['title'])}</a>",
                f"<p class='meta'>score={escape(item['score'])} reasons={escape('; '.join(item['reasons']))}</p>",
            )
        )
    content += section("Related items", "".join(related_cards) or "<p>No related items.</p>")
    return page("Capture detail", content)


def render_insights(store: ArchiveStore) -> str:
    result = list_insight_notes(store, limit=30)
    cards = []
    for note in result["notes"]:
        cards.append(
            card(
                f"<a href='/insights/{quote(note['id'])}'>{escape(note['title'])}</a>",
                f"<p>{escape(note['summary'])}</p><p class='meta'>{escape(note['review_status'])} evidence={escape(note['evidence_count'])}</p>",
            )
        )
    return page("Insights", nav_links() + section("Insight notes", "".join(cards) or "<p>No insight notes.</p>"))


def render_insight_detail(store: ArchiveStore, insight_id: str) -> str:
    result = show_insight_note(store, insight_id)
    if result is None:
        return page("Insight not found", "<p>Insight not found.</p>")
    body = f"<p class='meta'>{escape(result['review_status'])} / {escape(result['period_type'])}</p><p>{escape(result['summary'])}</p>"
    body += "<h3>Evidence</h3><ul>"
    for item in result["evidence_items"]:
        body += f"<li><a href='/captures/{quote(item['capture_id'])}'>{escape(item['title'])}</a></li>"
    body += "</ul>"
    return page("Insight detail", nav_links() + section(result["title"], body))


def page(title: str, content: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} - Darchivebot</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; color: #17211d; background: #f6f8f7; }}
    header {{ background: #12251f; color: white; padding: 22px 28px; }}
    main {{ max-width: 1040px; margin: 0 auto; padding: 24px; }}
    a {{ color: #0f6b57; font-weight: 700; text-decoration: none; }}
    form {{ display: flex; gap: 8px; margin: 0 0 16px; }}
    input {{ flex: 1; padding: 10px 12px; border: 1px solid #bccac5; border-radius: 6px; font-size: 16px; }}
    button, .tabs a {{ padding: 10px 12px; border: 1px solid #9ab4ad; border-radius: 6px; background: white; color: #143c33; font-weight: 700; }}
    section {{ margin: 18px 0; }}
    .nav, .tabs {{ display: flex; gap: 8px; flex-wrap: wrap; margin: 12px 0 18px; }}
    .card {{ background: white; border: 1px solid #d6dfdc; border-radius: 8px; padding: 14px 16px; margin: 10px 0; box-shadow: 0 1px 2px rgba(0,0,0,0.03); }}
    .meta {{ color: #5d6f69; font-size: 13px; }}
    pre {{ white-space: pre-wrap; background: #eef3f1; padding: 12px; border-radius: 6px; overflow-wrap: anywhere; }}
    dl {{ display: grid; grid-template-columns: minmax(120px, 180px) 1fr; gap: 8px 14px; }}
    dt {{ font-weight: 700; color: #3f5550; }}
    dd {{ margin: 0; }}
  </style>
</head>
<body>
  <header><h1>Darchivebot Local Archive</h1><p>Local search, review, related captures, and insight notes.</p></header>
  <main>{content}</main>
</body>
</html>"""


def search_form(query: str = "") -> str:
    return (
        "<form action='/search' method='get'>"
        f"<input name='q' value='{escape(query)}' placeholder='Search saved captures'>"
        "<button type='submit'>Search</button>"
        "</form>"
    )


def nav_links() -> str:
    return "<nav class='nav'><a href='/'>Archive</a><a href='/review'>Review</a><a href='/insights'>Insights</a></nav>"


def section(title: str, body: str) -> str:
    return f"<section><h2>{escape(title)}</h2>{body}</section>"


def card(title: str, body: str) -> str:
    return f"<div class='card'><h3>{title}</h3>{body}</div>"


def first(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key) or []
    return values[0] if values else ""


def int_or_default(value: str, default: int) -> int:
    try:
        return max(1, int(value))
    except ValueError:
        return default


def escape(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)
