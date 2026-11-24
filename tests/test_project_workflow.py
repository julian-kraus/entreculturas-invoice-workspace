"""Cross-project workflows run against a disposable local server and generated pages."""

import base64
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
from pathlib import Path
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
        results.save(slug, "receipt", draft)
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
    alpha = api("/api/export/invoice/receipt?project=alpha")
    beta = api("/api/export/invoice/receipt?project=beta")
    assert alpha["confirmed_row"] == approved["confirmed_row"]
    assert alpha["marked_pdf_url"] == approved["marked_pdf_url"]
    assert alpha["results"]["fields"][0]["value"] == "18"
    assert beta["confirmed_row"] is None
    assert beta["results"]["fields"][0]["value"] == "15"
    assert beta["results"]["review_status"] is None
    assert beta["results"]["rules_checked"] == 0 and beta["results"]["findings"] == []
    with pytest.raises(HTTPError, match="400"):
        api("/api/export/invoice/receipt")


def test_invoice_export_publishes_effective_findings_and_saved_values(api):
    api("/api/project/create", {"name": "Alpha"})
    common.save_json(common.project_dir("alpha") / "rules.json", [
        {"id": "R1", "name": "Supplier present", "type_id": "INVOICE", "status": "confirmed",
         "check": "required", "field": "supplier"},
    ])
    api("/api/invoices/upload?project=alpha", image_upload("Receipt.png"))
    initial = {"type_id": "INVOICE", "fields": {"supplier": {"value": "Original", "status": "found"}}}
    results.save("alpha", "receipt", initial)
    review_url = "/api/result/receipt/review?project=alpha"
    export_url = "/api/export/invoice/receipt?project=alpha"
    value = 'Supplier, "A"\nSecond line'
    reason = 'Needs "proof", which is missing.\nAsk the supplier.'
    review = {"fields": {"supplier": value}, "rules": {"R1": "failed"}, "rule_reasons": {"R1": reason},
              "revision": results.detail_state("alpha", "receipt")["revision"]}
    api(review_url, review | {"status": "draft"})
    draft = api(export_url)
    assert draft["confirmed_row"] is None
    assert draft["results"]["review_status"] == "draft"
    assert draft["results"]["findings"] == [{"id": "R1", "name": "Supplier present", "outcome": "failed", "reason": reason}]
    assert draft["results"]["fields"] == [{"id": "supplier", "name": "Supplier", "value": value, "status": "found",
                                            "corrected": True}]

    api(review_url, review | {"status": "confirmed", "revision": results.detail_state("alpha", "receipt")["revision"]})
    confirmed = api(export_url)
    assert confirmed["results"]["review_status"] == "confirmed"
    assert results.save("alpha", "receipt", initial)["staged"]
    assert api(export_url) == confirmed


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
    base = common.project_dir(slug)
    folder, records = base / "invoices", base / "results"
    (folder / "receipt.jpg").write_bytes(b"jpeg")
    (folder / "receipt.png").write_bytes(b"png")
    common.save_json(records / "receipt.json", {"file": "receipt.jpg"})
    files = common.invoice_files(slug)
    assert files["receipt"].name == "receipt.jpg"
    other_id = next(key for key, value in files.items() if value.name.endswith(".png"))
    assert common.invoice_path(slug, other_id) == folder / "receipt.png"


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


def test_setup_inbox_uses_stored_status_and_preserves_decisions(api):
    import proposals

    rules = [{"id": rid, "name": rid, "type_id": "ALL", "status": status, **extra}
             for rid, status, extra in [
                 ("Legacy", "proposed", {}), ("Assistant", "proposed", {"proposed_by": "assistant"}),
                 ("Manual", "proposed", {"proposed_by": "staff"}), ("Active", "confirmed", {}),
                 ("Declined", "rejected", {})]]
    api("/api/project/import", {"name": "Alpha", "setup": {"format": project.SETUP_FORMAT, "rules": rules}})
    api("/api/project/create", {"name": "Beta", "copy_rules_from": "alpha"})
    change, = proposals.propose("alpha", [{"kind": "rule", "target": "Active",
                                           "changes": {"description": "Check the date."}, "reason": "Clarify timing."}])

    def pending(slug):
        data = api(f"/api/proposals?project={slug}")
        return {r["id"] for r in data["rules"]}, {c["id"] for c in data["changes"]}

    assert pending("alpha") == ({"Legacy", "Assistant", "Manual"}, {change})
    assert pending("beta") == ({"Legacy", "Assistant", "Manual", "Active"}, set())
    setup = api("/api/config?inbox=1&project=alpha")
    assert setup["pending_changes"][0]["id"] == change
    assert "description" not in setup["rules"][3]
    for rule, status in zip(rules[:3], ("confirmed", "rejected", "rejected")):
        api(f"/api/rules/{rule['id']}/status?project=alpha", {"status": status, "expected": rule})
    # A second open page cannot reverse a decision or overwrite it from an old editor.
    with pytest.raises(HTTPError, match="400"):
        api("/api/rules/Legacy/status?project=alpha", {"status": "rejected", "expected": rules[0]})
    with pytest.raises(HTTPError, match="400"):
        api("/api/config/rules?project=alpha", {"value": rules, "expected": rules}, method="PUT")
    api(f"/api/proposals/{change}?project=alpha", {"approve": True})
    assert pending("alpha") == (set(), set())
    assert pending("beta") == ({"Legacy", "Assistant", "Manual", "Active"}, set())
    after = api("/api/config?inbox=1&project=alpha")
    assert {r["id"] for r in after["rules"] if r["status"] == "confirmed"} == {"Legacy", "Active"}
    assert {r["id"] for r in after["rules"] if r["status"] == "rejected"} == {"Declined", "Assistant", "Manual"}
    assert after["rules"][3]["description"] == "Check the date."
    assert after["pending_changes"] == []
    history = common.read_history("alpha")
    assert any(e["action"] == "proposal approved" for e in history)
    decisions = [c for e in history if e["action"] == "rules edited" for c in e["detail"]["changed"]]
    assert any(c["what"] == "Assistant" and c["after"] == {"status": "rejected"} for c in decisions)


def test_bundled_template_creates_named_project_with_extraction_fields(api):
    template = json.loads((ROOT / "templates" / "example-aexcid.json").read_text(encoding="utf-8"))
    assert api("/api/state")["projects"] == []
    assert template["project"]["name"] == "Template project"
    result = api("/api/project/create", {"name": "Our grant", "template": True})
    config = api(f"/api/config?project={result['current']}")
    assert config["project"] == template["project"] | {"name": "Our grant"}
    assert config["fields"] == template["fields"]
    assert config["invoice_types"] == template["invoice_types"]
    assert config["rules"] == template["rules"]
    assert all(rule["status"] == "proposed" for rule in config["rules"])


def test_inbox_confirms_reviewed_snapshots_and_returns_partial_results(api):
    import proposals

    rules = [{"id": name, "name": name, "type_id": "T", "status": "proposed", "check": "visual"}
             for name in ("First", "Stale", "Hidden")]
    setup = {"format": project.SETUP_FORMAT, "rules": rules, "invoice_types": [{"id": "T", "name": "Type"}],
             "fields": [{"id": "F", "name": "amount", "type_id": "T", "hint": "Before", "required": False}]}
    for slug in ("alpha", "beta"):
        api("/api/project/import", {"name": slug, "setup": setup})
    change_id, = proposals.propose("alpha", [{"kind": "field", "target": "F", "changes": {"hint": "Proposed", "required": True},
                                               "reason": "Clarify the source."}])
    change = api("/api/config?project=alpha&inbox=1")["pending_changes"][0]
    entries = [{"kind": "rule", "expected": rules[0], "edits": {"name": "Reviewed"}},
               {"kind": "rule", "expected": rules[1]}, {"kind": "change", "expected": change, "edits": {"hint": "Reviewed hint"}}]
    updated = [dict(rule) for rule in rules]
    updated[1]["description"] = "Another reviewer’s text"
    api("/api/config/rules?project=alpha", {"value": updated, "expected": rules}, method="PUT")

    def decide(items, approve=True):
        return api("/api/inbox/decide?project=alpha", {"items": items, "approve": approve})["results"]

    # Invalid UI-independent submissions leave a pending rule intact.
    invalid, = decide([{"kind": "rule", "expected": rules[0], "edits": {"check": "required", "field": ""}}])
    assert "Choose a field" in invalid["error"] and invalid["current"] == rules[0]
    first, stale, applied = decide(entries)
    assert first["item"]["name"] == "Reviewed" and first["item"]["status"] == "confirmed"
    assert "changed" in stale["error"] and stale["current"] == updated[1]
    assert applied["item"]["after"]["hint"] == "Proposed" and applied["item"]["reviewed_after"]["hint"] == "Reviewed hint"
    assert applied["item"]["id"] == change_id
    before_retry = common.read_history("alpha")
    assert all("error" in result for result in decide(entries))
    assert common.read_history("alpha") == before_retry
    declined, = decide([{"kind": "rule", "expected": stale["current"]}], approve=False)
    assert declined["item"]["status"] == "rejected" and declined["item"]["description"] == updated[1]["description"]
    after = api("/api/config?project=alpha&inbox=1")
    assert after["fields"][0]["required"] is True and after["fields"][0]["hint"] == "Reviewed hint"
    assert after["rules"][2] == rules[2]
    assert api("/api/config?project=beta")["rules"] == rules
    assert not after["pending_changes"]
    detail = next(e["detail"] for e in before_retry if e["action"] == "proposal approved")
    assert (detail["before"]["hint"], detail["proposed"]["hint"], detail["after"]["hint"]) == ("Before", "Proposed", "Reviewed hint")


def test_cli_addition_survives_an_in_flight_inbox_decision(api, workspace, monkeypatch):
    import subprocess

    api("/api/project/create", {"name": "Alpha"})
    rule = {"id": "R1", "name": "Existing", "type_id": "ALL", "check": "visual", "status": "proposed"}
    api("/api/config/rules?project=alpha", {"value": [rule]}, method="PUT")
    at_save, release = threading.Event(), threading.Event()
    save = server.save_json

    def pause_at_save(path, value):
        if path.name == "rules.json":
            at_save.set()
            assert release.wait(5)
        return save(path, value)

    monkeypatch.setattr(server, "save_json", pause_at_save)
    candidate = {"name": "New proposal", "type_id": "ALL", "check": "visual",
                 "source": "Guide", "description": "Check payment.", "hint": "Read the receipt."}
    draft = workspace / "draft.json"
    draft.write_text(json.dumps([candidate]))
    # Trace the child reaching SQLite's write reservation while the web handler
    # is paused between its expected-value check and its atomic replacement.
    child = """
import os, sqlite3, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import common, rules
common.PROJECTS = Path(sys.argv[2]) / "projects"
os.environ["INVOICE_PROJECT"] = "alpha"
connect = sqlite3.connect
def traced(*args, **kwargs):
    db = connect(*args, **kwargs)
    db.set_trace_callback(lambda sql: print("taking lock", flush=True) if sql == "BEGIN IMMEDIATE" else None)
    return db
sqlite3.connect = traced
sys.argv = ["rules.py", "propose", sys.argv[3]]
sys.exit(rules.main())
"""
    with ThreadPoolExecutor(max_workers=2) as pool:
        decision = pool.submit(api, "/api/inbox/decide?project=alpha",
                               {"approve": True, "items": [{"kind": "rule", "expected": rule}]})
        assert at_save.wait(3)
        with subprocess.Popen([sys.executable, "-c", child, str(ROOT / "tools"), str(workspace), str(draft)],
                              stdout=subprocess.PIPE, text=True) as process:
            try:
                assert pool.submit(process.stdout.readline).result(timeout=3).strip() == "taking lock"
            finally:
                release.set()
            assert process.wait(timeout=4) == 0
        assert decision.result()["results"][0]["item"]["status"] == "confirmed"
    rules = api("/api/config?project=alpha")["rules"]
    assert [(r["name"], r["status"]) for r in rules] == [("Existing", "confirmed"), ("New proposal", "proposed")]
