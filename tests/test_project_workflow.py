"""Cross-project workflows run against a disposable local server and generated pages."""

import base64
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
from pathlib import Path
import shutil
import sys
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "app")]

import common
import project
import results
import server


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.delenv("INVOICE_PROJECT", raising=False)
    monkeypatch.setattr(common, "ROOT", tmp_path)
    monkeypatch.setattr(common, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(common, "WORKSPACE_FILE", tmp_path / "workspace.json")
    monkeypatch.setattr(server, "ROOT", tmp_path)
    monkeypatch.setattr(server, "PROJECTS", common.PROJECTS)
    return tmp_path


@pytest.fixture
def api(workspace):
    http = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()

    def call(path, data=None, method=None):
        raw = json.dumps(data).encode() if data is not None else None
        request = Request(f"http://127.0.0.1:{http.server_port}{path}", data=raw, method=method,
                          headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=5) as response:
            if response.headers.get_content_type() == "application/json":
                return json.load(response)
            return response.read()

    try:
        yield call
    finally:
        http.shutdown()
        thread.join(timeout=3)
        http.server_close()


def image_upload(name, fmt="PNG"):
    buf = BytesIO()
    Image.new("RGB", (90, 120), "white").save(buf, fmt)
    return {"name": name, "data": base64.b64encode(buf.getvalue()).decode()}


def test_review_targets_project_screen_was_opened_in(api):
    draft = {"type_id": "INVOICE", "fields": {"total_amount": {"value": "15", "status": "found"}}}
    for slug in ("alpha", "beta"):
        api("/api/project/create", {"name": slug})
        config = api(f"/api/config?project={slug}")
        assert config["invoice_types"] and config["fields"] and config["rules"] == []
        api(f"/api/invoices/upload?project={slug}", image_upload("Receipt.png"))
        results.save(slug, "receipt", draft, "invoices")
    api("/api/project/switch", {"slug": "alpha"})
    detail = api("/api/result/receipt?project=alpha")
    api("/api/project/switch", {"slug": "beta"})
    body = {"status": "confirmed", "fields": {"total_amount": "18"}, "revision": detail["revision"]}
    with pytest.raises(HTTPError, match="400"):
        api("/api/result/receipt/review", body)
    api("/api/result/receipt/review?project=alpha", body)
    approved = api("/api/result/receipt?project=alpha")
    assert approved["result"]["review"]["fields"] == {"total_amount": "18"}
    assert not api("/api/result/receipt?project=beta")["result"].get("review")
    assert api(approved["marked_pdf_url"]).startswith(b"%PDF")
    with pytest.raises(HTTPError, match="403"):
        api(approved["marked_pdf_url"].replace("project=alpha", "project=beta"))


def test_uploads_preserve_display_names_and_distinct_ids(api):
    api("/api/project/create", {"name": "A"})
    payloads = [image_upload("Quarterly Receipt.PNG"), image_upload("Quarterly Receipt.JPG", "JPEG"),
                image_upload("Quarterly Receipt.PNG")]
    with ThreadPoolExecutor(max_workers=3) as pool:
        saved = list(pool.map(lambda upload: api("/api/invoices/upload?project=a", upload), payloads))
    ids = {row["id"] for row in saved}
    assert len(ids) == 3
    rows = api("/api/invoices?project=a")
    assert {row["id"] for row in rows} == ids
    assert sorted(row["file"] for row in rows) == sorted(item["name"] for item in payloads)
    for row in saved:
        assert common.invoice_path("a", row["id"]).suffix.lower() == Path(row["file"]).suffix.lower()


def test_legacy_same_stem_uses_evidence_in_saved_result(workspace):
    slug = project.create("Example", None)
    folder, records = common.set_dirs(slug, "invoices")
    (folder / "receipt.jpg").write_bytes(b"jpeg")
    (folder / "receipt.png").write_bytes(b"png")
    common.save_json(records / "receipt.json", {"file": "receipt.jpg"})
    files = common.invoice_files(slug)
    assert files["receipt"].name == "receipt.jpg"
    other_id = next(key for key, value in files.items() if value.name.endswith(".png"))
    assert common.invoice_path(slug, other_id) == folder / "receipt.png"
    evaluation, _ = common.set_dirs(slug, "evaluation")
    shutil.copy(folder / "receipt.png", evaluation)
    assert common.invoice_path(slug, other_id, "evaluation").name == "receipt.png"


def test_environment_pin_wins_over_selection_and_bad_pin_fails(workspace, monkeypatch):
    project.create("A", None)
    project.create("B", None)
    common.set_current_project("b")
    monkeypatch.setenv("INVOICE_PROJECT", "a")
    assert common.current_project() == "a" and common.selected_project() == "b"
    monkeypatch.setenv("INVOICE_PROJECT", "missing")
    with pytest.raises(common.WorkspaceError, match="no project"):
        common.current_project()


def test_failed_setup_preparation_leaves_project_name_available(workspace):
    with pytest.raises(common.WorkspaceError, match="no project"):
        project.create("New desk", "missing-source")
    assert not (common.PROJECTS / "new-desk").exists()
    with pytest.raises(common.WorkspaceError, match="own id"):
        project.import_setup("New desk", {"format": project.SETUP_FORMAT, "rules": [{"id": "r"}, {"id": "r"}]})
    slug = project.create("New desk", None)
    assert common.load_config(slug)["fields"]


def test_invalid_desktop_config_preserves_local_preference_file(workspace, monkeypatch):
    import sync_skills

    config = workspace / "config.toml"
    config.write_text("unclosed = [")
    local = workspace / "assistant-settings.local.json"
    monkeypatch.setattr(sync_skills, "CODEX_CONFIG", config)
    monkeypatch.setattr(sync_skills, "SETTINGS_FILE", local)
    monkeypatch.setattr(server, "SETTINGS_FILE", local)
    with pytest.raises(ValueError):
        server.save_settings({"value": {"codex": {"effort": "high"}}})
    assert not local.exists()
    assert config.read_text() == "unclosed = ["
