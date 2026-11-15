import json
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import common  # noqa: E402
import evaluate  # noqa: E402
import grid  # noqa: E402
import results  # noqa: E402
from checks import evaluate as evaluate_rules  # noqa: E402
from values import parse_amount, parse_date, same_value  # noqa: E402


@pytest.fixture()
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(common, "WORKSPACE_FILE", tmp_path / "workspace.json")
    base = tmp_path / "projects" / "demo"
    (base / "invoices").mkdir(parents=True)
    common.save_json(base / "project.json", {"name": "Demo", "period_start": "2025-01-01", "period_end": "2025-12-31"})
    common.save_json(base / "invoice_types.json", [{"id": "VOL", "name": "Volunteers", "enabled": True}])
    common.save_json(base / "fields.json", [
        {"id": "F1", "type_id": "VOL", "name": "total_amount", "label": "Amount", "kind": "amount", "required": True},
        {"id": "F2", "type_id": "VOL", "name": "invoice_date", "label": "Date", "kind": "date", "required": True},
        {"id": "F3", "type_id": "VOL", "name": "invoice_number", "label": "Number", "kind": "text", "required": False},
    ])
    common.save_json(base / "rules.json", [
        {"id": "R1", "type_id": "VOL", "name": "amount present", "check": "required", "field": "total_amount",
         "severity": "error", "status": "confirmed", "enabled": True},
        {"id": "R2", "type_id": "VOL", "name": "date in period", "check": "date_in_period", "field": "invoice_date",
         "severity": "error", "status": "confirmed", "enabled": True},
        {"id": "R3", "type_id": "VOL", "name": "stamp", "check": "visual", "severity": "error",
         "status": "confirmed", "enabled": True},
        {"id": "R4", "type_id": "VOL", "name": "not yet confirmed", "check": "visual", "severity": "error",
         "status": "proposed", "enabled": True},
    ])
    common.save_json(base / "learnings.json", [])
    Image.new("RGB", (600, 800), "white").save(base / "invoices" / "receipt-a.png")
    common.set_current_project("demo")
    return "demo"


def draft(date="28 août 2025", stamp="pass", number="A-1"):
    return {
        "type_id": "VOL",
        "fields": {
            "total_amount": {"value": "30.000", "status": "found", "page": 1, "box": [0.7, 0.4, 0.9, 0.45]},
            "invoice_date": {"value": date, "status": "found", "page": 1, "box": [0.6, 0.1, 0.9, 0.15]},
            "invoice_number": {"value": number, "status": "found"},
        },
        "visual": {"R3": {"verdict": stamp, "reason": "Stamp seen", "page": 1, "box": [0.2, 0.5, 0.6, 0.7]}},
        "questions": [],
        "summary": "Test",
    }


def test_values():
    assert parse_amount("30.000") == 30000
    assert parse_amount("1.234,56 EUR") == 1234.56
    assert parse_amount("1,234.56") == 1234.56
    assert parse_amount("30 000 FCFA") == 30000
    assert parse_date("28 août 2025").isoformat() == "2025-08-28"
    assert parse_date("12 de marzo de 2026").isoformat() == "2026-03-12"
    assert parse_date("03/04/2025").isoformat() == "2025-04-03"
    assert same_value("30.000", "30000", "amount")
    assert same_value("Relais  Communautaire", "relais communautaire")


def test_grid_boxes():
    assert grid.range_box("A1") == [0, 0, 1 / 12, 1 / 16]
    assert grid.refine_box("K9:J8", None) == [round(9 / 12, 4), round(7 / 16, 4), round(11 / 12, 4), round(9 / 16, 4)]
    box = grid.refine_box("A1:B2", "b2:c3")
    assert box == [round(2 / 12 * 1 / 4, 4), round(2 / 16 * 1 / 4, 4), round(2 / 12 * 3 / 4, 4), round(2 / 16 * 3 / 4, 4)]
    with pytest.raises(grid.GridError):
        grid.range_box("M1")


def test_save_checks_and_marks(project):
    summary = results.save(project, "receipt-a", draft(), "invoices")
    assert summary["status"] == "passes"
    saved = common.load_json(common.result_path(project, "receipt-a"))
    outcomes = {o["rule_id"]: o["outcome"] for o in saved["rule_results"]}
    assert outcomes == {"R1": "passed", "R2": "passed", "R3": "passed"}
    assert Path(summary["marked_pdf"]).exists()


def test_invalid_draft_is_rejected_and_not_kept(project):
    bad = draft()
    bad["fields"]["unknown_field"] = {"value": "x", "status": "found"}
    with pytest.raises(common.WorkspaceError):
        results.save(project, "receipt-a", bad, "invoices")
    assert not common.result_path(project, "receipt-a").exists()


def test_date_outside_period_fails(project):
    summary = results.save(project, "receipt-a", draft(date="12/03/2026"), "invoices")
    assert summary["status"] == "fails rules"
    assert "date in period" in summary["failed"]


def test_review_overrides_and_evaluation(project):
    results.save(project, "receipt-a", draft(stamp="fail"), "invoices")
    path = common.result_path(project, "receipt-a")
    result = common.load_json(path)
    result["ai_original"] = {k: v for k, v in result.items() if k != "review"}
    result["review"] = {"fields": {"total_amount": "35.000"}, "rules": {"R3": "passed"}, "status": "confirmed"}
    config = common.load_config(project)
    result.update(evaluate_rules(result, config, {}))
    common.save_json(path, result)
    assert result["status"] == "passes"
    truth = evaluate.add(project, "receipt-a", aside=False)
    assert truth["fields"]["total_amount"] == "35.000"
    assert truth["rules"]["R3"] == "passed"
    run = evaluate.score(project)
    totals = run["groups"]["main"]["totals"]
    assert totals["false_alarm"] == 1  # the assistant failed the stamp; the reviewer passed it
    assert run["groups"]["main"]["fields_right"] == 2  # the amount was read wrongly


def test_duplicate_invoice_numbers(project):
    base = common.PROJECTS / project / "invoices"
    Image.new("RGB", (600, 800), "white").save(base / "receipt-b.png")
    results.save(project, "receipt-a", draft(number="A-1"), "invoices")
    summary = results.save(project, "receipt-b", draft(number="a-1 "), "invoices")
    assert "Invoice number used only once" in summary["failed"]


def test_history_is_written(project):
    results.save(project, "receipt-a", draft(), "invoices")
    actions = [e["action"] for e in common.read_history(project)]
    assert "invoice checked" in actions


def test_skills_have_frontmatter():
    root = Path(__file__).resolve().parents[1] / "skills"
    for skill in root.iterdir():
        if skill.is_dir():
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            assert text.startswith("---\n")
            header = text.split("---")[1]
            assert f"name: {skill.name}" in header and "description:" in header


def test_proposals_apply_only_after_approval(project):
    import proposals
    ids = proposals.propose(project, [{"kind": "field", "target": "F3", "changes": {"hint": "Use the funds request number."},
                                       "reason": "Reviewers expected the funds request number.", "evidence": ["receipt-a"]}])
    fields = {f["id"]: f for f in common.load_json(common.PROJECTS / project / "fields.json")}
    assert "hint" not in fields["F3"]
    proposals.decide(project, ids[0], approve=True)
    fields = {f["id"]: f for f in common.load_json(common.PROJECTS / project / "fields.json")}
    assert fields["F3"]["hint"] == "Use the funds request number."
    assert proposals.pending(project) == []
    with pytest.raises(common.WorkspaceError):
        proposals.decide(project, ids[0], approve=True)


def test_proposal_rejected_when_item_changed_meanwhile(project):
    import proposals
    ids = proposals.propose(project, [{"kind": "rule", "target": "R3", "changes": {"hint": "Look at the stamp."},
                                       "reason": "Stamps were missed."}])
    rules = common.load_json(common.PROJECTS / project / "rules.json")
    next(r for r in rules if r["id"] == "R3")["hint"] = "Edited by a person"
    common.save_json(common.PROJECTS / project / "rules.json", rules)
    with pytest.raises(common.WorkspaceError):
        proposals.decide(project, ids[0], approve=True)


def test_setup_export_and_import(project):
    import project as project_tool
    setup = project_tool.export_setup(project)
    assert "invoices" not in json.dumps(setup)
    slug = project_tool.import_setup("Colleague copy", setup)
    assert common.load_json(common.PROJECTS / slug / "rules.json") == setup["rules"]
    assert common.load_json(common.PROJECTS / slug / "project.json")["name"] == "Colleague copy"
    with pytest.raises(common.WorkspaceError):
        project_tool.import_setup("Bad", {"format": "something else"})
