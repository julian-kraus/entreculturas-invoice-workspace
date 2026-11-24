"""Exercise review persistence with synthetic documents, independent of user projects."""
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from openpyxl import load_workbook
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import checks
import common
import report
from marks import marks_for
import results


@pytest.fixture
def project(tmp_path, monkeypatch):
    base = tmp_path / "projects"
    monkeypatch.setattr(common, "PROJECTS", base)
    slug = "demo"
    root = base / slug
    (root / "invoices").mkdir(parents=True)
    Image.new("RGB", (72, 72), "white").save(root / "invoices" / "receipt.png")
    common.save_json(root / "project.json", {"name": "Demo"})
    common.save_json(root / "invoice_types.json", [{"id": "DOC", "name": "Document"}])
    common.save_json(root / "fields.json", [{"id": "TOTAL", "name": "total_amount", "label": "Total", "type_id": "DOC"}])
    common.save_json(root / "rules.json", [{"id": "R1", "type_id": "DOC", "status": "confirmed",
                                           "name": "Total present", "field": "total_amount", "check": "required"}])
    return slug


def reading(amount="100"):
    return {"type_id": "DOC", "fields": {"total_amount": {"status": "found", "value": amount, "page": 1,
                                                          "box": [0.1, 0.2, 0.3, 0.4]}}}


def check(slug, amount="100"):
    return results.save(slug, "receipt", reading(amount))


def detail(slug):
    return results.detail_state(slug, "receipt")


def confirm(slug):
    return results.save_review(slug, "receipt", {"status": "confirmed", "revision": detail(slug)["revision"],
                                                 "fields": {"total_amount": "125"}})


def workbook_row(slug):
    book = load_workbook(report.build(slug), read_only=True)
    try:
        return next(book["Invoices"].iter_rows(min_row=2, values_only=True))
    finally:
        book.close()


def test_repeated_rechecks_preserve_confirmed_export_and_artifact(project):
    check(project)
    confirm(project)
    before = detail(project)
    pdf = Path(before["marked_pdf"]).read_bytes()
    original_row = workbook_row(project)
    assert (original_row[5], original_row[8], original_row[9]) == ("125", "yes", 1)
    assert check(project, "120")["staged"]
    first_proposal = detail(project)["candidate"]
    assert check(project, "130")["staged"]
    pending = detail(project)
    assert pending["revision"] == before["revision"]
    assert pending["confirmed_row"][5] == "125" and workbook_row(project) == original_row
    assert Path(pending["marked_pdf"]).read_bytes() == pdf
    with pytest.raises(common.WorkspaceError, match="proposed result changed"):
        results.accept_recheck(project, "receipt", {"revision": before["revision"],
                                                    "candidate_revision": first_proposal["revision"]})
    results.accept_recheck(project, "receipt", {"revision": before["revision"],
                                                "candidate_revision": pending["candidate"]["revision"]})
    accepted = detail(project)
    assert accepted["candidate"] is None
    assert accepted["confirmed_row"][5] == "130" and workbook_row(project)[5] == "130"
    assert Path(accepted["marked_pdf"]).exists()
    assert Path(before["marked_pdf"]).read_bytes() == pdf
    archive = common.result_path(project, "receipt").parent / "archive" / "receipt" / (before["revision"] + ".json")
    assert common.load_json(archive)["review"]["fields"]["total_amount"] == "125"


def test_concurrent_confirmations_accept_only_one_visible_revision(project):
    check(project)
    viewed = detail(project)["revision"]

    def confirm_as(by):
        try:
            results.save_review(project, "receipt", {"revision": viewed, "status": "confirmed", "by": by})
            return "saved"
        except common.WorkspaceError as error:
            assert "invoice changed" in str(error)
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(confirm_as, ["one", "two"])) == ["saved", "stale"]


def test_no_applicable_rules_new_and_legacy(project):
    root = common.project_dir(project)
    rules = common.load_json(root / "rules.json")
    for status in ("proposed", "confirmed"):
        rules[0]["status"] = status
        common.save_json(root / "rules.json", rules)
        result = check(project)
        assert (result["rules_checked"], result["status"]) == (
            (1, "passes") if status == "confirmed" else (0, "no applicable rules"))
    path = common.result_path(project, "receipt")
    old = {"invoice": "receipt", "type_id": "DOC", "fields": {}, "visual": {},
           "review": {"status": "confirmed"}, "rule_results": [], "status": "passes"}
    common.save_json(path, old)
    view = detail(project)
    assert view["result"]["status"] == "no applicable rules"
    assert view["confirmed_row"][-1] == 0 and workbook_row(project)[3] == "no applicable rules"
    assert common.load_json(path) == old
    candidate = check(project, "150")
    assert candidate["staged"] and detail(project)["revision"] == view["revision"]


def test_failure_keeps_original_and_pending_candidate(project, monkeypatch):
    check(project)
    confirm(project)
    check(project, "120")
    before = detail(project)
    with pytest.raises(common.WorkspaceError):
        results.save(project, "receipt", {"type_id": "unknown", "fields": {}})
    def fail(*args, **kwargs):
        raise OSError("out of space")
    monkeypatch.setattr(results, "draw", fail)
    with pytest.raises(OSError):
        check(project, "140")
    assert detail(project) == before


def test_rerunning_rules_or_saving_draft_keeps_confirmed_outcome(project):
    check(project)
    confirm(project)
    before = detail(project)
    common.save_json(common.project_dir(project) / "rules.json", [])
    assert checks.run(project, "receipt")["status"] == "no applicable rules"
    assert detail(project)["result"]["rules_checked"] == 1
    results.save_review(project, "receipt", {"status": "draft", "fields": {"total_amount": "127"},
                                             "revision": before["revision"]})
    assert workbook_row(project)[5] == "125"
    assert detail(project)["candidate"]["result"]["review"]["fields"]["total_amount"] == "127"


def test_finding_decisions_and_reasons_survive_review_and_recheck(project):
    root = common.project_dir(project)
    common.save_json(root / "rules.json", [{"id": "R1", "type_id": "DOC", "status": "confirmed",
                                            "name": "Receipt signed", "check": "visual"}])
    first = reading() | {"visual": {"R1": {"verdict": "pass", "reason": "Signature seen.",
                                          "page": 1, "box": [0.2, 0.2, 0.3, 0.4]}}}
    results.save(project, "receipt", first)

    def review(status, decisions, reasons):
        return results.save_review(project, "receipt", {"revision": detail(project)["revision"], "status": status,
                                                        "rules": decisions, "rule_reasons": reasons})

    draft = review("draft", {"R1": "unclear"}, {"R1": "The stamp covers the signature."})
    assert draft == detail(project)["result"]
    rule = draft["rule_results"][0]
    assert (rule["outcome"], rule["message"]) == ("unclear", "The stamp covers the signature.")
    assert (rule["ai_outcome"], rule["ai_message"]) == ("passed", "Signature seen.")
    assert draft["ai_original"]["visual"] == first["visual"]

    confirmation = review("confirmed", {"R1": "not_applicable"}, {"R1": "This receipt is exempt."})
    assert marks_for(confirmation)[0]["kind"] == "not_applicable"
    results.save(project, "receipt", first)
    stale = detail(project)
    assert stale["result"]["review"]["rule_reasons"] == {"R1": "This receipt is exempt."}
    book = load_workbook(report.build(project), read_only=True)
    try:
        headers, row = book["Findings"].values
        exported = dict(zip(headers, row))
        assert exported["Outcome"] == "not_applicable"
        assert exported["Explanation"] == exported["Reviewer reason"] == "This receipt is exempt."
        assert exported["Assistant outcome"] == "passed" and exported["Assistant explanation"] == "Signature seen."
    finally:
        book.close()

    reason_only = review("confirmed", {}, {"R1": "Signed on the reverse."})
    rule = reason_only["rule_results"][0]
    assert (rule["outcome"], rule["message"], rule["overridden"]) == ("passed", "Signed on the reverse.", False)
    assert detail(project)["candidate"]["revision"] == stale["candidate"]["revision"]
    with pytest.raises(common.WorkspaceError, match="invoice changed"):
        results.accept_recheck(project, "receipt", {"revision": stale["revision"],
                                                    "candidate_revision": stale["candidate"]["revision"]})
    archived = common.load_json(root / "results" / "archive" / "receipt" / (confirmation["revision"] + ".json"))
    assert archived["rule_results"][0]["review_reason"] == "This receipt is exempt."
    formula_text = "=The total includes the second receipt."
    review("confirmed", {}, {"R1": formula_text})
    book = load_workbook(report.build(project), read_only=True)
    try:
        explanation = book["Findings"]["E2"]
        assert explanation.data_type == "s" and explanation.value == formula_text
    finally:
        book.close()
    reset = review("confirmed", {}, {})
    assert reset["rule_results"][0]["message"] == "Signature seen."
    assert reset["review"]["rule_reasons"] == {}
    assert detail(project)["candidate"]["revision"] == stale["candidate"]["revision"]


def test_review_of_legacy_decision_without_reason(project):
    result_path = common.result_path(project, "receipt")
    check(project)
    stored = common.load_json(result_path)
    legacy_rule = stored["rule_results"][0]
    legacy_rule.update({"ai_outcome": "passed", "outcome": "failed", "overridden": True,
                        "message": "The invoice has a total."})
    stored["review"] = {"status": "draft", "rules": {"R1": "failed"}}
    common.save_json(result_path, stored)
    loaded = detail(project)
    rule = loaded["result"]["rule_results"][0]
    assert (rule["outcome"], rule["message"], rule["review_reason"]) == ("failed", "", "")
    assert (rule["ai_outcome"], rule["ai_message"]) == ("passed", "The invoice has a total.")
    assert common.load_json(result_path) == stored
    for invalid in ({"rules": {"R1": "nonsense"}}, {"rule_reasons": {"R1": 10}}):
        with pytest.raises(common.WorkspaceError):
            results.save_review(project, "receipt", {"revision": loaded["revision"], "status": "draft", **invalid})
        assert common.load_json(result_path) == stored
    updated = results.save_review(project, "receipt", {"revision": loaded["revision"], "status": "confirmed",
                                                       "rules": {"R1": "failed"},
                                                       "rule_reasons": {"R1": "Total is for a different receipt."}})
    assert updated["rule_results"][0]["ai_message"] == "The invoice has a total."
    with pytest.raises(common.WorkspaceError, match="invoice changed"):
        results.save_review(project, "receipt", {"revision": loaded["revision"], "status": "confirmed"})
