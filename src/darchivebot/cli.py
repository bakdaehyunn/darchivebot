from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
from typing import Any

from darchivebot.config import DEFAULT_ENV_FILE, ROOT, Settings, ensure_local_dirs, get_settings, load_env
from darchivebot.doctor import run_doctor
from darchivebot.graph import default_graph_path, export_graph as export_jsonld_graph
from darchivebot.insights import generate_insight_note, list_insight_notes, show_insight_note
from darchivebot.processor import CaptureProcessor, format_results
from darchivebot.readiness import (
    ISSUE_NAMES,
    concept_summary,
    graph_quality_summary,
    interest_summary,
    related_captures,
    reprocess_plan,
)
from darchivebot.semantic_graph import (
    default_semantic_export_path,
    default_semantic_store_path,
    export_semantic_store,
    init_semantic_store,
    semantic_store_stats,
    sync_semantic_store,
)
from darchivebot.storage import ArchiveStore
from darchivebot.telegram import (
    DEFAULT_BOT_COMMANDS,
    REGISTERED_CHAT_BOT_COMMANDS,
    TelegramApiClient,
    TelegramCaptureBot,
    chat_command_scope,
    discover_chat_candidates,
    format_rooms_report,
    read_room_state,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="darchive")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Create local config, state directories, and SQLite schema")

    p_setup = sub.add_parser("setup", help="Configure .env and optionally install launchd")
    p_setup.add_argument("--dry-run", action="store_true")
    p_setup.add_argument("--non-interactive", action="store_true")
    p_setup.add_argument("--telegram-bot-token")
    p_setup.add_argument("--telegram-chat-id")
    p_setup.add_argument("--telegram-admin-user-id")
    p_setup.add_argument("--allow-all-chats", action="store_true")
    p_setup.add_argument("--install-launchd", action="store_true")

    p_doctor = sub.add_parser("doctor", help="Check local config and optional Telegram connectivity")
    p_doctor.add_argument("--online", action="store_true", help="Also call Telegram getMe when a token is configured")

    p_discover = sub.add_parser("discover-chat", help="Find Telegram chat ids from recent bot updates")
    p_discover.add_argument("--plain", action="store_true")
    p_discover.add_argument("--json", action="store_true")

    sub.add_parser("rooms", help="Show registered Telegram darchive room status")

    p_commands = sub.add_parser("telegram-commands", help="Show or sync Telegram command menu")
    commands_sub = p_commands.add_subparsers(dest="telegram_commands_cmd", required=True)
    commands_sub.add_parser("show", help="Show current Telegram command menu")
    commands_sub.add_parser("sync", help="Sync Telegram command menu")

    sub.add_parser("setup-telegram-commands", help=argparse.SUPPRESS)

    p_send_test = sub.add_parser("send-test", help="Send a test message")
    p_send_test.add_argument("--chat-id")
    p_send_test.add_argument("--registered", action="store_true", help="Use the registered darchive room")
    p_send_test.add_argument("--allowed", action="store_true", help="Use the only TELEGRAM_ALLOWED_CHAT_IDS value")
    p_send_test.add_argument("--dry-run", action="store_true")

    p_telegram = sub.add_parser("telegram", help="Run Telegram polling capture bot")
    p_telegram.add_argument("--poll-interval-sec", type=float, default=1.0)

    p_process = sub.add_parser("process", help="Process pending captures into archive metadata")
    p_process.add_argument("--limit", type=int)
    p_process.add_argument("--dry-run", action="store_true")
    p_process.add_argument("--no-codex", action="store_true", help="Use the deterministic fallback processor")
    p_process.add_argument(
        "--export-graph",
        action="store_true",
        help="Refresh the semantic graph store and JSON-LD export after processing",
    )
    p_process.add_argument("--json", action="store_true")

    p_pending = sub.add_parser("pending", help="Preview pending captures and processor inputs")
    p_pending.add_argument("--limit", type=int)
    p_pending.add_argument("--no-codex", action="store_true")
    p_pending.add_argument("--json", action="store_true")

    p_reprocess_plan = sub.add_parser("reprocess-plan", help="Plan safe archive-quality reprocessing candidates")
    p_reprocess_plan.add_argument("--limit", type=int, default=20)
    p_reprocess_plan.add_argument("--issue", choices=ISSUE_NAMES)
    p_reprocess_plan.add_argument("--fallback-only", action="store_true")
    p_reprocess_plan.add_argument("--needs-review-only", action="store_true")
    p_reprocess_plan.add_argument("--capture-id")
    p_reprocess_plan.add_argument("--json", action="store_true")

    p_reprocess = sub.add_parser("reprocess", help="Reprocess one selected capture, or preview candidates with --dry-run")
    p_reprocess.add_argument("--capture-id")
    p_reprocess.add_argument("--limit", type=int, default=20)
    p_reprocess.add_argument("--issue", choices=ISSUE_NAMES)
    p_reprocess.add_argument("--fallback-only", action="store_true")
    p_reprocess.add_argument("--needs-review-only", action="store_true")
    p_reprocess.add_argument("--dry-run", action="store_true")
    p_reprocess.add_argument("--no-codex", action="store_true", help="Use the deterministic fallback processor")
    p_reprocess.add_argument("--no-export-graph", action="store_true", help="Do not refresh graph outputs after success")
    p_reprocess.add_argument("--json", action="store_true")

    p_list = sub.add_parser("list", help="List recent captures")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.add_argument("--interest", help="Only show archived captures matching an interest")
    p_list.add_argument("--json", action="store_true")

    p_interests = sub.add_parser("interests", help="Inspect archive interest distribution")
    p_interests.add_argument("--limit", type=int, default=20)
    p_interests.add_argument("--json", action="store_true")

    p_concepts = sub.add_parser("concepts", help="Inspect archive concept/tag distribution")
    p_concepts.add_argument("--limit", type=int, default=20)
    p_concepts.add_argument("--json", action="store_true")

    p_related = sub.add_parser("related", help="Inspect read-only related captures from local graph signals")
    p_related.add_argument("capture_id")
    p_related.add_argument("--limit", type=int, default=10)
    p_related.add_argument("--json", action="store_true")

    p_insights = sub.add_parser("insights", help="List or generate local draft insight notes")
    p_insights.add_argument("--limit", type=int, default=20)
    p_insights.add_argument("--json", action="store_true")
    insights_sub = p_insights.add_subparsers(dest="insights_cmd")
    p_insights_generate = insights_sub.add_parser("generate", help="Generate a local draft insight note")
    p_insights_generate.add_argument("--period", choices=["weekly"], default="weekly")
    p_insights_generate.add_argument("--dry-run", action="store_true")
    p_insights_generate.add_argument("--include-needs-review", action="store_true")
    p_insights_generate.add_argument("--limit", type=int, default=20)
    p_insights_generate.add_argument("--json", action="store_true")
    p_insights_show = insights_sub.add_parser("show", help="Show one local draft insight note")
    p_insights_show.add_argument("insight_id")
    p_insights_show.add_argument("--json", action="store_true")

    p_show = sub.add_parser("show", help="Show one capture")
    p_show.add_argument("capture_id")
    p_show.add_argument("--json", action="store_true")

    p_graph = sub.add_parser("graph", help="Export ontology-oriented local graph data")
    graph_sub = p_graph.add_subparsers(dest="graph_cmd", required=True)
    p_graph_init = graph_sub.add_parser("init", help="Initialize the local semantic graph store")
    p_graph_init.add_argument("--path", type=Path)
    p_graph_init.add_argument("--json", action="store_true")
    p_graph_sync = graph_sub.add_parser("sync", help="Rebuild the semantic graph store from SQLite archive rows")
    p_graph_sync.add_argument("--path", type=Path)
    p_graph_sync.add_argument("--limit", type=int)
    p_graph_sync.add_argument("--include-raw-text", action="store_true")
    p_graph_sync.add_argument("--json", action="store_true")
    p_graph_store_export = graph_sub.add_parser("store-export", help="Dump the semantic graph store as N-Quads")
    p_graph_store_export.add_argument("--path", type=Path)
    p_graph_store_export.add_argument("--output", type=Path)
    p_graph_store_export.add_argument("--json", action="store_true")
    p_graph_export = graph_sub.add_parser("export", help="Export archive items as JSON-LD")
    p_graph_export.add_argument("--output", type=Path)
    p_graph_export.add_argument("--limit", type=int)
    p_graph_export.add_argument("--include-raw-text", action="store_true")
    p_graph_export.add_argument("--json", action="store_true")
    p_graph_stats = graph_sub.add_parser("stats", help="Show local semantic graph store stats")
    p_graph_stats.add_argument("--path", type=Path)
    p_graph_stats.add_argument("--json", action="store_true")
    p_graph_quality = graph_sub.add_parser("quality", help="Inspect archive readiness for graph and viewpoint work")
    p_graph_quality.add_argument("--limit", type=int, default=20)
    p_graph_quality.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    load_env()
    settings = get_settings()
    store = ArchiveStore(settings.state_dir)

    if args.cmd == "init":
        return init_cmd(settings, store)
    if args.cmd == "setup":
        return setup_cmd(
            settings,
            dry_run=args.dry_run,
            non_interactive=args.non_interactive,
            telegram_bot_token=args.telegram_bot_token,
            telegram_chat_id=args.telegram_chat_id,
            telegram_admin_user_id=args.telegram_admin_user_id,
            allow_all_chats=args.allow_all_chats,
            install_launchd=args.install_launchd,
        )
    if args.cmd == "doctor":
        code, text = run_doctor(settings, store, online=args.online)
        print(text)
        return code
    if args.cmd == "discover-chat":
        return discover_chat_cmd(settings, plain=args.plain, json_output=args.json)
    if args.cmd == "rooms":
        code, text = format_rooms_report(settings)
        print(text)
        return code
    if args.cmd == "telegram-commands":
        return telegram_commands_cmd(settings, args.telegram_commands_cmd)
    if args.cmd == "setup-telegram-commands":
        return telegram_commands_cmd(settings, "sync")
    if args.cmd == "send-test":
        return send_test_cmd(
            settings,
            chat_id=args.chat_id,
            use_registered=args.registered,
            use_allowed=args.allowed,
            dry_run=args.dry_run,
        )
    if args.cmd == "telegram":
        bot = TelegramCaptureBot(settings, store)
        bot.run_polling(poll_interval_sec=args.poll_interval_sec)
        return 0
    if args.cmd == "process":
        processor = CaptureProcessor(settings, store)
        results = processor.process_pending(
            limit=args.limit,
            dry_run=args.dry_run,
            use_codex=False if args.no_codex else None,
            progress=None if args.json or args.dry_run else print_process_progress,
        )
        semantic_graph_result = None
        jsonld_graph_result = None
        if args.export_graph and not args.dry_run and any(item.get("status") == "processed" for item in results):
            semantic_graph_result = sync_semantic_store(store, default_semantic_store_path(settings.root))
            jsonld_graph_result = export_jsonld_graph(store, default_graph_path(settings.root))
        print(
            format_process_and_graph_results(
                results,
                semantic_graph_result=semantic_graph_result,
                jsonld_graph_result=jsonld_graph_result,
                json_output=args.json,
            )
        )
        return 0 if not any(item.get("status") == "failed" for item in results) else 1
    if args.cmd == "pending":
        processor = CaptureProcessor(settings, store)
        results = processor.process_pending(
            limit=args.limit,
            dry_run=True,
            use_codex=False if args.no_codex else None,
        )
        print(format_results(results, json_output=args.json))
        return 0
    if args.cmd == "reprocess-plan":
        return reprocess_plan_cmd(
            store,
            limit=args.limit,
            issue=args.issue or "",
            fallback_only=args.fallback_only,
            needs_review_only=args.needs_review_only,
            capture_id=args.capture_id or "",
            json_output=args.json,
        )
    if args.cmd == "reprocess":
        if args.dry_run:
            return reprocess_dry_run_cmd(
                store,
                limit=args.limit,
                issue=args.issue or "",
                fallback_only=args.fallback_only,
                needs_review_only=args.needs_review_only,
                capture_id=args.capture_id or "",
                json_output=args.json,
            )
        return reprocess_cmd(
            settings,
            store,
            capture_id=args.capture_id or "",
            use_codex=False if args.no_codex else None,
            export_graph=not args.no_export_graph,
            json_output=args.json,
        )
    if args.cmd == "list":
        return list_cmd(store, limit=args.limit, interest=args.interest or "", json_output=args.json)
    if args.cmd == "interests":
        return interests_cmd(store, limit=args.limit, json_output=args.json)
    if args.cmd == "concepts":
        return concepts_cmd(store, limit=args.limit, json_output=args.json)
    if args.cmd == "related":
        return related_cmd(store, capture_id=args.capture_id, limit=args.limit, json_output=args.json)
    if args.cmd == "insights":
        return insights_cmd(
            store,
            action=args.insights_cmd or "list",
            period=getattr(args, "period", "weekly"),
            dry_run=getattr(args, "dry_run", False),
            include_needs_review=getattr(args, "include_needs_review", False),
            limit=getattr(args, "limit", 20),
            insight_id=getattr(args, "insight_id", ""),
            json_output=args.json,
        )
    if args.cmd == "show":
        return show_cmd(store, capture_id=args.capture_id, json_output=args.json)
    if args.cmd == "graph":
        return graph_cmd(
            settings,
            store,
            action=args.graph_cmd,
            output_path=getattr(args, "output", None),
            stats_path=getattr(args, "path", None),
            limit=getattr(args, "limit", None),
            quality_limit=getattr(args, "limit", 20),
            include_raw_text=getattr(args, "include_raw_text", False),
            json_output=args.json,
        )
    return 2


def init_cmd(settings: Settings, store: ArchiveStore) -> int:
    ensure_local_dirs(settings)
    store.init_db()
    if not DEFAULT_ENV_FILE.exists():
        DEFAULT_ENV_FILE.write_text(Path(settings.root / ".env.example").read_text(encoding="utf-8"), encoding="utf-8")
        print(f"created {DEFAULT_ENV_FILE}")
    print(f"initialized SQLite at {store.path}")
    return 0


def setup_cmd(
    settings: Settings,
    *,
    dry_run: bool,
    non_interactive: bool,
    telegram_bot_token: str | None,
    telegram_chat_id: str | None,
    telegram_admin_user_id: str | None,
    allow_all_chats: bool,
    install_launchd: bool,
) -> int:
    print("==> Preparing local files")
    if dry_run:
        print(f"[dry-run] ensure local directories and SQLite under {settings.root}")
    else:
        ensure_local_dirs(settings)
        ArchiveStore(settings.state_dir).init_db()

    token = choose_setup_value(
        label="Telegram bot token",
        current=settings.telegram_bot_token,
        provided=telegram_bot_token,
        secret=True,
        non_interactive=non_interactive,
    )
    admin_user_id = choose_setup_value(
        label="Telegram admin user id",
        current=",".join(settings.telegram_admin_user_ids),
        provided=telegram_admin_user_id,
        secret=False,
        non_interactive=non_interactive,
    )
    chat_id = telegram_chat_id or ",".join(settings.telegram_allowed_chat_ids)
    if not chat_id and token:
        chat_id = discover_chat_for_setup(token, dry_run=dry_run, non_interactive=non_interactive)
    if not chat_id and not non_interactive:
        chat_id = prompt_setup_value("Telegram allowed chat id", "", secret=False)

    if not token:
        print("[FAIL] Telegram bot token is required")
        return 1
    if not chat_id and not allow_all_chats:
        print("[FAIL] Telegram chat id is required unless --allow-all-chats is set")
        return 1

    print("==> Writing .env")
    if dry_run:
        print(f"[dry-run] write {DEFAULT_ENV_FILE}")
    else:
        write_setup_env(
            DEFAULT_ENV_FILE,
            telegram_bot_token=token,
            telegram_allowed_chat_ids=chat_id,
            telegram_admin_user_ids=admin_user_id,
            allow_all_chats=allow_all_chats,
        )

    configured = get_settings()
    print("==> Running doctor")
    if dry_run:
        print("[dry-run] darchive doctor")
    else:
        code, text = run_doctor(configured, ArchiveStore(configured.state_dir), online=False)
        print(text)
        if code != 0:
            return code

    if install_launchd:
        return install_launch_agent(settings.root, dry_run=dry_run)
    print("setup complete")
    print("Normal operation: run `scripts/install_launch_agent.sh` so launchd keeps capture running, processes every 5 minutes, and refreshes the semantic graph after successful processing.")
    print("Test/debug mode: run `darchive telegram`, `darchive pending`, or `darchive process` directly when checking behavior.")
    print("For personal archives, a 1:1 Telegram chat is recommended. For groups, disable BotFather Group Privacy.")
    return 0


def discover_chat_cmd(settings: Settings, plain: bool, json_output: bool) -> int:
    if not settings.telegram_bot_token:
        print("[FAIL] TELEGRAM_BOT_TOKEN is not configured")
        return 1
    payload = TelegramApiClient(settings.telegram_bot_token).get_updates()
    candidates = discover_chat_candidates(payload)
    if json_output:
        print(json.dumps([candidate.__dict__ for candidate in candidates], ensure_ascii=False, indent=2))
        return 0
    if plain:
        for candidate in candidates:
            print(candidate.chat_id)
        return 0
    if not candidates:
        print("no recent Telegram chats found")
        return 0
    for candidate in candidates:
        print(f"{mask_identifier(candidate.chat_id)}\t{candidate.chat_type}\t{candidate.title}")
    return 0


def telegram_commands_cmd(settings: Settings, action: str) -> int:
    if not settings.telegram_bot_token:
        print("[FAIL] TELEGRAM_BOT_TOKEN is not configured")
        return 1
    api = TelegramApiClient(settings.telegram_bot_token)
    state = read_room_state(settings)
    if action == "show":
        print("[default]")
        print_commands(api.get_my_commands())
        if state.darchive_chat_id:
            print(f"[registered chat {mask_identifier(state.darchive_chat_id)}]")
            print_commands(api.get_my_commands(scope=chat_command_scope(state.darchive_chat_id)))
        return 0
    if action == "sync":
        api.set_my_commands(DEFAULT_BOT_COMMANDS)
        if state.darchive_chat_id:
            api.set_my_commands(REGISTERED_CHAT_BOT_COMMANDS, scope=chat_command_scope(state.darchive_chat_id))
            print("Telegram commands synced: default and registered chat")
        else:
            print("Telegram commands synced: default")
        return 0
    return 2


def print_commands(commands: list[dict[str, str]]) -> None:
    if not commands:
        print("(empty)")
        return
    for item in commands:
        print(f"/{item.get('command', '')} - {item.get('description', '')}")


def send_test_cmd(
    settings: Settings,
    *,
    chat_id: str | None,
    use_registered: bool,
    use_allowed: bool,
    dry_run: bool,
) -> int:
    if not settings.telegram_bot_token:
        print("[FAIL] TELEGRAM_BOT_TOKEN is not configured")
        return 1
    target_count = sum(1 for value in (chat_id, use_registered, use_allowed) if bool(value))
    if target_count != 1:
        print("[FAIL] choose exactly one target: --chat-id, --registered, or --allowed")
        return 2
    target = ""
    if chat_id:
        target = chat_id
    elif use_registered:
        target = read_room_state(settings).darchive_chat_id
    elif use_allowed:
        target = only_allowed_chat_id(settings)
    if not target:
        print("[FAIL] selected target is not configured")
        return 1
    if dry_run:
        print(f"[dry-run] would send test message to {mask_identifier(target)}")
        return 0
    TelegramApiClient(settings.telegram_bot_token).send_message(target, "다카이브봇 테스트 메시지입니다.")
    print(f"sent test message to {mask_identifier(target)}")
    return 0


def list_cmd(store: ArchiveStore, limit: int, interest: str, json_output: bool) -> int:
    rows = store.list_capture_summaries(limit, interest=interest)
    if json_output:
        print(json.dumps([row_to_dict(row) for row in rows], ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("no captures" if not interest else f"no captures for interest: {interest}")
        return 0
    for row in rows:
        text = str(row["text"] or row["caption"] or "").replace("\n", " ")
        file_status = format_file_status(row)
        archive_status = "archived" if int(row["has_archive_item"] or 0) else "not_archived"
        title = str(row["archive_title"] or "").replace("\n", " ").strip()
        core_summary = str(row["archive_core_summary"] or "").replace("\n", " ").strip()
        primary_interest = str(row["archive_primary_interest"] or "").replace("\n", " ").strip()
        topic = str(row["archive_topic"] or "").replace("\n", " ").strip()
        classification = format_classification_preview(primary_interest, topic)
        preview = title or core_summary or text[:80] or "(no text)"
        print(
            f"{row['id']}\t{row['status']}\t{row['content_kind']}\t"
            f"files={file_status}\tarchive={archive_status}{classification}\t{preview[:100]}"
        )
    return 0


def reprocess_plan_cmd(
    store: ArchiveStore,
    *,
    limit: int,
    issue: str,
    fallback_only: bool,
    needs_review_only: bool,
    capture_id: str,
    json_output: bool,
) -> int:
    result = reprocess_plan(
        store,
        limit=limit,
        issue=issue,
        fallback_only=fallback_only,
        needs_review_only=needs_review_only,
        capture_id=capture_id,
    )
    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    print(f"candidate_count={result['candidate_count']} showing={len(result['candidates'])}")
    if not result["candidates"]:
        print("no reprocess candidates")
        return 0
    for item in result["candidates"]:
        reasons = ",".join(reason["name"] for reason in item["candidate_reasons"])
        history = ",".join(f"{run['processor']}:{run['status']}" for run in item["processor_history"]) or "none"
        history_count = item.get("processor_history_count", len(item["processor_history"]))
        history_suffix = f"+{history_count - len(item['processor_history'])}" if history_count > len(item["processor_history"]) else ""
        current = item["current"]
        print(
            f"{item['capture_id']}\tkind={item['content_kind']}\t"
            f"interest={current['primary_interest'] or '-'} topic={current['topic'] or '-'} "
            f"confidence={current['confidence']} needs_review={str(current['needs_review']).lower()}\t"
            f"reasons={reasons}\thistory={history}{history_suffix}\t{item['title']}"
        )
    print(result["next_step"])
    return 0


def reprocess_dry_run_cmd(
    store: ArchiveStore,
    *,
    limit: int,
    issue: str,
    fallback_only: bool,
    needs_review_only: bool,
    capture_id: str,
    json_output: bool,
) -> int:
    result = reprocess_plan(
        store,
        limit=limit,
        issue=issue,
        fallback_only=fallback_only,
        needs_review_only=needs_review_only,
        capture_id=capture_id,
    )
    payload = {
        "dry_run": True,
        "would_reprocess": result["candidates"],
        "candidate_count": result["candidate_count"],
        "message": "No SQLite rows were changed. Run `darchive reprocess --capture-id <capture-id>` to reprocess one selected capture.",
    }
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(f"[dry-run] would reprocess {len(result['candidates'])} of {result['candidate_count']} candidates")
    for item in result["candidates"]:
        reasons = ",".join(reason["name"] for reason in item["candidate_reasons"])
        print(f"{item['capture_id']}\treasons={reasons}\t{item['title']}")
    print(payload["message"])
    return 0


def reprocess_cmd(
    settings: Settings,
    store: ArchiveStore,
    *,
    capture_id: str,
    use_codex: bool | None,
    export_graph: bool,
    json_output: bool,
) -> int:
    if not capture_id:
        message = "reprocess requires --capture-id for actual rewrites; use --dry-run to preview candidates"
        if json_output:
            print(json.dumps({"status": "error", "message": message}, ensure_ascii=False, indent=2))
        else:
            print(message)
        return 2
    processor = CaptureProcessor(settings, store)
    result = processor.reprocess_capture(
        capture_id,
        use_codex=use_codex,
        progress=None if json_output else print_process_progress,
    )
    semantic_graph_result = None
    jsonld_graph_result = None
    if export_graph and result.get("status") == "processed":
        semantic_graph_result = sync_semantic_store(store, default_semantic_store_path(settings.root))
        jsonld_graph_result = export_jsonld_graph(store, default_graph_path(settings.root))
    print(
        format_process_and_graph_results(
            [result],
            semantic_graph_result=semantic_graph_result,
            jsonld_graph_result=jsonld_graph_result,
            json_output=json_output,
        )
    )
    return 0 if result.get("status") == "processed" else 1


def interests_cmd(store: ArchiveStore, limit: int, json_output: bool) -> int:
    result = interest_summary(store, limit=limit)
    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if not result["interests"]:
        print("no interests")
        return 0
    print(f"archive_items={result['archive_items']}")
    for item in result["interests"]:
        print(
            f"{item['interest']}\ttotal={item['total_count']} "
            f"primary={item['primary_count']} secondary={item['secondary_count']}"
        )
    return 0


def concepts_cmd(store: ArchiveStore, limit: int, json_output: bool) -> int:
    result = concept_summary(store, limit=limit)
    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if not result["concepts"]:
        print("no concepts")
        return 0
    print(f"archive_items={result['archive_items']}")
    for item in result["concepts"]:
        print(f"{item['concept']}\tcount={item['count']}")
    return 0


def related_cmd(store: ArchiveStore, capture_id: str, limit: int, json_output: bool) -> int:
    result = related_captures(store, capture_id, limit=limit)
    if result is None:
        print(f"[FAIL] archived capture not found: {capture_id}")
        return 1
    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if not result["related"]:
        print(f"no related captures for {result['capture_id']}")
        return 0
    print(f"capture_id={result['capture_id']} archive_item_id={result['archive_item_id']}")
    for item in result["related"]:
        reasons = "; ".join(item["reasons"]) if item["reasons"] else "-"
        print(f"{item['capture_id']}\tscore={item['score']}\t{item['title']}\t{reasons}")
    return 0


def insights_cmd(
    store: ArchiveStore,
    *,
    action: str,
    period: str,
    dry_run: bool,
    include_needs_review: bool,
    limit: int,
    insight_id: str,
    json_output: bool,
) -> int:
    if action == "list":
        result = list_insight_notes(store, limit=limit)
        if json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if not result["notes"]:
            print("no insight notes")
            return 0
        for note in result["notes"]:
            print(
                f"{note['id']}\t{note['review_status']}\t{note['period_type']}\t"
                f"evidence={note['evidence_count']}\t{note['title']}"
            )
        return 0
    if action == "generate":
        result = generate_insight_note(
            store,
            period=period,
            dry_run=dry_run,
            include_needs_review=include_needs_review,
            limit=limit,
        )
        if json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["status"] in {"created", "dry-run"} else 1
        if result["status"] == "created":
            note = result["note"]
            print(
                f"created draft insight note {result['insight_id']} "
                f"evidence={len(note['notable_archive_item_ids'])}"
            )
            print(note["title"])
            print(note["summary"])
            return 0
        if result["status"] == "dry-run":
            note = result["would_create"]
            print(f"[dry-run] would create draft insight note evidence={len(note['notable_archive_item_ids'])}")
            print(note["title"])
            print(note["summary"])
            return 0
        print(f"[SKIP] {result['message']}")
        if result.get("next_step"):
            print(f"next_step: {result['next_step']}")
        return 1
    if action == "show":
        result = show_insight_note(store, insight_id)
        if result is None:
            print(f"[FAIL] insight note not found: {insight_id}")
            return 1
        if json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        print(f"id: {result['id']}")
        print(f"status: {result['review_status']}")
        print(f"period: {result['period_type']} {result['period_start']}..{result['period_end']}")
        print(f"title: {result['title']}")
        print(f"summary: {result['summary']}")
        for theme in result["recurring_themes"]:
            print(f"theme: {theme.get('type')} {theme.get('name')} evidence={theme.get('evidence_count')}")
        for item in result["evidence_items"]:
            print(f"evidence: {item['archive_item_id']} {item['title']}")
        return 0
    return 2


def show_cmd(store: ArchiveStore, capture_id: str, json_output: bool) -> int:
    row = store.get_capture(capture_id)
    if row is None:
        print(f"[FAIL] capture not found: {capture_id}")
        return 1
    files = store.files_for_capture(capture_id)
    archive = store.get_archive_item(capture_id)
    data = row_to_dict(row)
    data["files"] = [row_to_dict(file_row) for file_row in files]
    data["archive_item"] = archive_item_to_dict(archive) if archive is not None else None
    if json_output:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    print(f"id: {data['id']}")
    print(f"status: {data['status']}")
    print(f"kind: {data['content_kind']}")
    if data.get("text"):
        print(f"text: {data['text']}")
    if data.get("caption"):
        print(f"caption: {data['caption']}")
    for file_row in data["files"]:
        print(f"file: {file_row.get('download_status')} {file_row.get('local_path')}")
    if data["archive_item"]:
        archive_item = data["archive_item"]
        print(f"archive_title: {archive_item.get('title')}")
        if archive_item.get("core_summary"):
            print(f"core_summary: {archive_item.get('core_summary')}")
        if archive_item.get("key_points"):
            for point in archive_item["key_points"]:
                print(f"key_point: {point}")
        if archive_item.get("context"):
            print(f"context: {archive_item.get('context')}")
        if archive_item.get("why_saved"):
            print(f"why_saved: {archive_item.get('why_saved')}")
        if archive_item.get("tags"):
            print(f"tags: {', '.join(archive_item['tags'])}")
        if archive_item.get("primary_interest"):
            print(f"primary_interest: {archive_item.get('primary_interest')}")
        if archive_item.get("secondary_interests"):
            print(f"secondary_interests: {', '.join(archive_item['secondary_interests'])}")
        if archive_item.get("topic"):
            print(f"topic: {archive_item.get('topic')}")
        if archive_item.get("subtopic"):
            print(f"subtopic: {archive_item.get('subtopic')}")
        if archive_item.get("classification_reason"):
            print(f"classification_reason: {archive_item.get('classification_reason')}")
        if archive_item.get("revisit_priority"):
            print(f"revisit_priority: {archive_item.get('revisit_priority')}")
        if archive_item.get("revisit_reason"):
            print(f"revisit_reason: {archive_item.get('revisit_reason')}")
        if archive_item.get("insight_seed"):
            print(f"insight_seed: {archive_item.get('insight_seed')}")
        print(f"needs_review: {archive_item.get('needs_review')}")
    return 0


def graph_cmd(
    settings: Settings,
    store: ArchiveStore,
    *,
    action: str,
    output_path: Path | None,
    stats_path: Path | None,
    limit: int | None,
    quality_limit: int,
    include_raw_text: bool,
    json_output: bool,
) -> int:
    if action == "init":
        path = stats_path or default_semantic_store_path(settings.root)
        result = init_semantic_store(path)
        if json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"initialized semantic graph store at {result['path']}")
        return 0
    if action == "sync":
        path = stats_path or default_semantic_store_path(settings.root)
        result = sync_semantic_store(store, path, limit=limit, include_raw_text=include_raw_text)
        if json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            raw_note = " with raw text" if result.get("raw_text_included") else ""
            print(
                f"synced {result['synced_archive_items']} archive items "
                f"({result['quads']} quads){raw_note} to {result['path']}"
            )
        return 0
    if action == "store-export":
        path = stats_path or default_semantic_store_path(settings.root)
        out_path = output_path or default_semantic_export_path(settings.root)
        try:
            result = export_semantic_store(path, out_path)
        except FileNotFoundError as exc:
            print(f"[FAIL] {exc}")
            return 1
        if json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"exported semantic graph store ({result['quads']} quads) to {result['export_path']}")
        return 0
    if action == "export":
        path = output_path or default_graph_path(settings.root)
        result = export_jsonld_graph(store, path, limit=limit, include_raw_text=include_raw_text)
        if json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            raw_note = " with raw text" if result.get("raw_text_included") else ""
            print(f"exported {result['archive_items']} archive items ({result['nodes']} nodes){raw_note} to {result['path']}")
        return 0
    if action == "stats":
        path = stats_path or default_semantic_store_path(settings.root)
        result = semantic_store_stats(path)
        if json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif result["exists"]:
            print(
                f"semantic_graph={result['path']} archive_items={result['archive_items']} "
                f"quads={result['quads']} generated_at={result.get('generated_at', '')} "
                f"raw_text_included={str(result['raw_text_included']).lower()}"
            )
        else:
            print(f"semantic graph store not found: {result['path']}")
        return 0 if result["exists"] else 1
    if action == "quality":
        result = graph_quality_summary(store, limit=quality_limit)
        if json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(
                f"archive_items={result['archive_items']} "
                f"ready_for_synthesis={str(result['ready_for_synthesis']).lower()}"
            )
            for issue in result["issues"]:
                print(f"{issue['name']}\tcount={issue['count']}")
            print(f"next_step: {result['next_step']}")
        return 0
    return 2


def only_allowed_chat_id(settings: Settings) -> str:
    if len(settings.telegram_allowed_chat_ids) == 1:
        return settings.telegram_allowed_chat_ids[0]
    return ""


def row_to_dict(row: Any) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def archive_item_to_dict(row: Any) -> dict[str, Any]:
    data = row_to_dict(row)
    data["core_summary"] = data.get("core_summary") or data.get("summary") or ""
    data["raw_extracted_text"] = data.get("raw_extracted_text") or data.get("extracted_text") or ""
    data["key_points"] = load_json_list(data.get("key_points_json"))
    data["tags"] = load_json_list(data.get("tags_json"))
    data["primary_interest"] = data.get("primary_interest") or ""
    data["secondary_interests"] = load_json_list(data.get("secondary_interests_json"))
    data["topic"] = data.get("topic") or ""
    data["subtopic"] = data.get("subtopic") or ""
    data["classification_reason"] = data.get("classification_reason") or ""
    data["revisit_priority"] = data.get("revisit_priority") or ""
    data["revisit_reason"] = data.get("revisit_reason") or ""
    data["insight_seed"] = data.get("insight_seed") or ""
    data["dates_mentioned"] = load_json_list(data.get("dates_mentioned_json"))
    data["people_mentioned"] = load_json_list(data.get("people_mentioned_json"))
    data["action_candidates"] = load_json_list(data.get("action_candidates_json"))
    data["needs_review"] = bool(data.get("needs_review"))
    return data


def load_json_list(value: Any) -> list[str]:
    try:
        payload = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [str(item) for item in payload]


def mask_identifier(value: str) -> str:
    raw = str(value or "")
    if len(raw) <= 4:
        return "***"
    return f"***{raw[-4:]}"


def format_file_status(row: Any) -> str:
    file_count = int(row["file_count"] or 0)
    if file_count == 0:
        return "none"
    statuses = str(row["file_download_statuses"] or "").replace(",", "+") or "unknown"
    return f"{file_count}:{statuses}"


def format_classification_preview(primary_interest: str, topic: str) -> str:
    parts = []
    if primary_interest:
        parts.append(f"interest={primary_interest}")
    if topic:
        parts.append(f"topic={topic}")
    return "\t" + " ".join(parts) if parts else ""


def format_process_and_graph_results(
    results: list[dict[str, Any]],
    *,
    semantic_graph_result: dict[str, Any] | None,
    jsonld_graph_result: dict[str, Any] | None,
    json_output: bool,
) -> str:
    if json_output:
        if semantic_graph_result is None and jsonld_graph_result is None:
            return format_results(results, json_output=True)
        payload: dict[str, Any] = {"results": results}
        if semantic_graph_result is not None:
            payload["semantic_graph"] = semantic_graph_result
        if jsonld_graph_result is not None:
            payload["jsonld_graph"] = jsonld_graph_result
        return json.dumps(payload, ensure_ascii=False, indent=2)
    text = format_results(results, json_output=False)
    if semantic_graph_result is not None:
        text += (
            f"\nsemantic graph synced {semantic_graph_result['synced_archive_items']} archive items "
            f"({semantic_graph_result['quads']} quads) to {semantic_graph_result['path']}"
        )
    if jsonld_graph_result is not None:
        text += (
            f"\njsonld graph exported {jsonld_graph_result['archive_items']} archive items "
            f"({jsonld_graph_result['nodes']} nodes) to {jsonld_graph_result['path']}"
        )
    return text


def print_process_progress(event: dict[str, Any]) -> None:
    name = event.get("event")
    capture_id = event.get("capture_id", "-")
    processor = event.get("processor", "-")
    kind = event.get("content_kind", "-")
    if name == "start":
        print(f"[process:start] capture={capture_id} kind={kind} processor={processor}")
    elif name == "finish":
        print(
            f"[process:done] capture={capture_id} kind={kind} "
            f"processor={processor} elapsed={event.get('elapsed_sec')}s"
        )
    elif name == "failed":
        print(
            f"[process:failed] capture={capture_id} kind={kind} processor={processor} "
            f"elapsed={event.get('elapsed_sec')}s error={event.get('error')}"
        )
    elif name == "skipped":
        print(
            f"[process:skip] capture={capture_id} kind={kind} "
            f"reason={event.get('reason', '-')}"
        )


def choose_setup_value(
    *,
    label: str,
    current: str,
    provided: str | None,
    secret: bool,
    non_interactive: bool,
) -> str:
    if provided is not None:
        return provided.strip()
    if non_interactive:
        return current.strip()
    return prompt_setup_value(label, current, secret=secret)


def prompt_setup_value(label: str, current: str, *, secret: bool) -> str:
    if current:
        prompt = f"{label} [configured]: " if secret else f"{label} [{current}]: "
    else:
        prompt = f"{label}: "
    value = getpass.getpass(prompt) if secret else input(prompt)
    return current if not value else value.strip()


def discover_chat_for_setup(token: str, *, dry_run: bool, non_interactive: bool) -> str:
    print("Telegram chat id can be discovered after the bot receives one message.")
    if dry_run:
        print("[dry-run] darchive discover-chat --plain")
        return ""
    if not non_interactive and not ask_yes_no("Try chat id auto discovery?", default=True):
        return ""
    candidates = discover_chat_candidates(TelegramApiClient(token).get_updates())
    if not candidates:
        return ""
    latest = candidates[-1]
    print(f"discovered chat id: {mask_identifier(latest.chat_id)} ({latest.chat_type or 'unknown'})")
    return latest.chat_id


def write_setup_env(
    env_file: Path,
    *,
    telegram_bot_token: str,
    telegram_allowed_chat_ids: str,
    telegram_admin_user_ids: str,
    allow_all_chats: bool,
) -> None:
    values = {
        "TELEGRAM_BOT_TOKEN": telegram_bot_token,
        "TELEGRAM_ALLOWED_CHAT_IDS": telegram_allowed_chat_ids,
        "TELEGRAM_ADMIN_USER_IDS": telegram_admin_user_ids,
        "DARCHIVE_ALLOW_ALL_CHATS": str(allow_all_chats).lower(),
        "DARCHIVE_STATE_DIR": ".local/state",
        "DARCHIVE_LOG_DIR": ".local/logs",
        "DARCHIVE_MEDIA_DIR": ".local/captures",
        "DARCHIVE_CODEX_ENABLED": "true",
        "DARCHIVE_CODEX_BIN": "codex",
        "DARCHIVE_CODEX_MODEL": "",
        "DARCHIVE_CODEX_SANDBOX": "read-only",
        "DARCHIVE_CODEX_EPHEMERAL": "true",
        "DARCHIVE_CODEX_TIMEOUT_SEC": "900",
        "DARCHIVE_PROCESSOR_BATCH_SIZE": "10",
        "DARCHIVE_TESSERACT_BIN": "tesseract",
    }
    env_file.write_text(
        f"TELEGRAM_BOT_TOKEN={telegram_bot_token}\n"
        f"TELEGRAM_ALLOWED_CHAT_IDS={telegram_allowed_chat_ids}\n"
        f"TELEGRAM_ADMIN_USER_IDS={telegram_admin_user_ids}\n"
        f"DARCHIVE_ALLOW_ALL_CHATS={str(allow_all_chats).lower()}\n"
        "DARCHIVE_STATE_DIR=.local/state\n"
        "DARCHIVE_LOG_DIR=.local/logs\n"
        "DARCHIVE_MEDIA_DIR=.local/captures\n"
        "DARCHIVE_CODEX_ENABLED=true\n"
        "DARCHIVE_CODEX_BIN=codex\n"
        "DARCHIVE_CODEX_MODEL=\n"
        "DARCHIVE_CODEX_SANDBOX=read-only\n"
        "DARCHIVE_CODEX_EPHEMERAL=true\n"
        "DARCHIVE_CODEX_TIMEOUT_SEC=900\n"
        "DARCHIVE_PROCESSOR_BATCH_SIZE=10\n"
        "DARCHIVE_TESSERACT_BIN=tesseract\n",
        encoding="utf-8",
    )
    os.environ.update(values)


def ask_yes_no(prompt: str, *, default: bool) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    raw = input(f"{prompt} {suffix} ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes"}


def install_launch_agent(root: Path, *, dry_run: bool) -> int:
    script = root / "scripts" / "install_launch_agent.sh"
    if dry_run:
        print(f"[dry-run] {script}")
        return 0
    if not script.exists():
        print(f"[FAIL] launchd install script missing: {script}")
        return 1
    proc = subprocess_run_script(script)
    return proc


def subprocess_run_script(script: Path) -> int:
    import subprocess

    return subprocess.run([str(script)], cwd=script.parents[1], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
