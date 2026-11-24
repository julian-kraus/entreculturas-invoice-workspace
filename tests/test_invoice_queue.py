"""The list must not mistake historic or unreadable results for unchecked invoices."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "app")]
import common
import server


def test_list_distinguishes_legacy_review_and_unreadable_result(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "PROJECTS", tmp_path / "projects")
    folder = common.PROJECTS / "project"
    (folder / "invoices").mkdir(parents=True)
    (folder / "results").mkdir()
    for name in ("unreadable", "legacy", "pending", "unchecked"):
        (folder / "invoices" / f"{name}.png").write_bytes(b"image")
    (folder / "invoices" / "unreadable.jpg").write_bytes(b"image")
    (folder / "results" / "legacy.json").write_text(json.dumps({"status": "passes", "fields": {}}))
    (folder / "results" / "unreadable.json").write_text("{broken")
    (folder / "results" / "pending.json").write_text(json.dumps({
        "status": "passes", "review": {"status": "confirmed"}, "revision": "base",
        "pending_recheck": {"revision": "candidate", "origin": "staff_draft", "result": {}},
    }))
    rows = {item["id"]: item for item in server.invoice_list("project")}
    assert rows["legacy"]["has_result"] and rows["legacy"]["revision"]
    assert rows["legacy"]["review_status"] is None
    assert rows["unreadable"]["has_result"] and rows["unreadable"]["result_error"]
    assert all(row["identity_error"] for row in rows.values() if row["file"].startswith("unreadable."))
    assert not rows["unchecked"]["has_result"]
    assert rows["pending"]["pending_recheck"] == "candidate"
    assert rows["pending"]["candidate_origin"] == "staff_draft"
