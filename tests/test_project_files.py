from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_gitignore_covers_private_runtime_files():
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in text
    assert ".local/" in text
    assert "*.sqlite3" in text
    assert "*.log" in text


def test_launchd_scripts_reference_bot_and_processor():
    install = (ROOT / "scripts" / "install_launch_agent.sh").read_text(encoding="utf-8")
    assert "com.hennei.darchivebot.telegram" in install
    assert "com.hennei.darchivebot.processor" in install
    assert "<string>telegram</string>" in install
    assert "<string>process</string>" in install
    assert "<string>--export-graph</string>" in install
    assert "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" in install


def test_preflight_script_checks_private_runtime_files_and_secrets():
    preflight = (ROOT / "scripts" / "preflight_public.sh").read_text(encoding="utf-8")
    assert "git ls-files --error-unmatch .env" in preflight
    assert "*.sqlite3" in preflight
    assert "TELEGRAM_BOT_TOKEN" in preflight


def test_readme_frames_product_as_interest_aware_archive_without_mvp_language():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "아이디어 주머니" in text
    assert "AI, 커리어, 테크놀로지, 스포츠 같은 관심사" in text
    assert "Viewpoint Layer" in text
    assert "insight seed" in text
    assert "darchive insights generate --period weekly" in text
    assert "docs/viewpoint-layer.md" in text
    assert "docs/ontology-graph.md" in text
    assert "MVP" not in text


def test_viewpoint_layer_docs_define_final_product_layer():
    text = (ROOT / "docs" / "viewpoint-layer.md").read_text(encoding="utf-8")
    assert "The Viewpoint Layer is the long-term product layer" in text
    assert "Capture Layer" in text
    assert "Archive Layer" in text
    assert "Semantic Graph Layer" in text
    assert "Viewpoint Layer" in text
    assert "SQLite remains the operational source of truth" in text
    assert "Raw text is excluded from normal graph and viewpoint outputs" in text
    assert "add `darchive graph quality`" in text


def test_ontology_graph_docs_define_semantic_store_with_lightweight_jsonld_export():
    text = (ROOT / "docs" / "ontology-graph.md").read_text(encoding="utf-8")
    assert ".local/graph/darchivebot.jsonld" in text
    assert ".local/graph/semantic-store/" in text
    assert "lightweight portable export" in text
    assert "not a complete backup of every RDF fact" in text
    assert "darch:Capture" in text
    assert "darch:ArchiveItem" in text
    assert "darch:hasInterest" in text
    assert "SQLite remains the source of truth" in text
    assert "raw extracted text is not exported or stored in the semantic graph by default" in text
