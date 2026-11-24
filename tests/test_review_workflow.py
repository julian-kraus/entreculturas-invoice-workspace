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
    current = detail(slug)
    return results.save(slug, "receipt", reading(amount), intent="recheck" if current["revision"] else "initial",
                        expected_revision=current["revision"])


def detail(slug):
    return results.detail_state(slug, "receipt")


def confirm(slug):
    return results.save_review(slug, "receipt", {"status": "confirmed", "revision": detail(slug)["revision"],
                                                 "fields": {"total_amount": "125"}})


def test_checks_require_all_inbox_items_handled_and_recheck_under_lock(project):
    root = common.project_dir(project)
    snapshot = results.inspect(project, "receipt")
    rules = common.load_json(root / "rules.json")
    common.save_json(root / "rules.json", rules + [{"id": "P1", "status": "proposed"}])
    with pytest.raises(common.WorkspaceError, match="Inbox.*1 item"):
        results.inspect(project, "receipt")
    with pytest.raises(common.WorkspaceError, match="Inbox"):
        results.save(project, "receipt", reading(), source_digest=snapshot["source_digest"],
                     config_digest=snapshot["config_digest"])
    assert not common.result_path(project, "receipt").exists()
    common.save_json(root / "rules.json", rules)
    common.save_json(root / "proposals.json", [{"id": "C1", "status": "pending"}])
    with pytest.raises(common.WorkspaceError, match="Inbox"):
        results.inspect(project, "receipt")
    common.save_json(root / "proposals.json", [{"id": "C1", "status": "rejected"}])
    check(project)
    confirmed = confirm(project)
    common.save_json(root / "proposals.json", [{"id": "C2", "status": "pending"}])
    with pytest.raises(common.WorkspaceError, match="Inbox"):
        results.save(project, "receipt", reading(), intent="recheck", expected_revision=detail(project)["revision"])
    with pytest.raises(common.WorkspaceError, match="Inbox"):
        results.recalculate(project, "receipt")
    assert detail(project)["result"]["review"]["status"] == "confirmed"


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
    with pytest.raises(common.WorkspaceError, match="pending change"):
        check(project, "130")
    results.discard_candidate(project, "receipt", {"revision": before["revision"],
                                                     "candidate_revision": first_proposal["revision"]})
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
    for status in ("rejected", "confirmed"):
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
    with pytest.raises(common.WorkspaceError, match="pending change"):
        check(project, "140")
    assert detail(project) == before
    results.discard_candidate(project, "receipt", {"revision": before["revision"],
                                                     "candidate_revision": before["candidate"]["revision"]})
    before = detail(project)
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
    candidate = detail(project)["candidate"]
    with pytest.raises(common.WorkspaceError, match="pending change"):
        results.save_review(project, "receipt", {"status": "draft", "fields": {"total_amount": "127"},
                                                 "revision": before["revision"]})
    results.discard_candidate(project, "receipt", {"revision": before["revision"],
                                                     "candidate_revision": candidate["revision"]})
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
    results.save(project, "receipt", first, intent="recheck", expected_revision=detail(project)["revision"])
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

    with pytest.raises(common.WorkspaceError, match="pending change"):
        review("confirmed", {}, {"R1": "Signed on the reverse."})
    results.discard_candidate(project, "receipt", {"revision": stale["revision"],
                                                     "candidate_revision": stale["candidate"]["revision"]})
    reason_only = review("confirmed", {}, {"R1": "Signed on the reverse."})
    rule = reason_only["rule_results"][0]
    assert (rule["outcome"], rule["message"], rule["overridden"]) == ("passed", "Signed on the reverse.", False)
    assert detail(project)["candidate"] is None
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
    assert detail(project)["candidate"] is None


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


def test_recalculation_preserves_unconfirmed_staff_draft(project):
    check(project)
    results.save_review(project, "receipt", {
        "revision": detail(project)["revision"], "status": "draft",
        "fields": {"total_amount": "150"},
    })
    before = detail(project)
    pdf_before = Path(before["marked_pdf"]).read_bytes()
    with pytest.raises(results.ReviewConflict, match="staff draft"):
        results.recalculate(project, "receipt", expected_revision=before["revision"])
    assert detail(project) == before
    assert Path(before["marked_pdf"]).read_bytes() == pdf_before


def test_candidate_drafts_and_rechecks_require_observed_versions(project):
    check(project)
    confirm(project)
    base = detail(project)
    results.save_review(project, "receipt", {
        "revision": base["revision"], "status": "draft", "fields": {"total_amount": "150"},
    })
    candidate = detail(project)["candidate"]
    assert candidate["origin"] == "staff_draft"
    with pytest.raises(results.ReviewConflict):
        check(project, "170")
    with pytest.raises(results.ReviewConflict):
        results.save_review(project, "receipt", {
            "revision": base["revision"], "status": "confirmed", "fields": {"total_amount": "170"},
        })
    updated = results.save_review(project, "receipt", {
        "revision": base["revision"], "candidate_revision": candidate["revision"],
        "status": "draft", "fields": {"total_amount": "155"},
    })
    newer = detail(project)["candidate"]
    assert newer["revision"] != candidate["revision"]
    assert updated["review"]["fields"]["total_amount"] == "155"
    with pytest.raises(results.ReviewConflict):
        results.discard_candidate(project, "receipt", {
            "revision": base["revision"], "candidate_revision": candidate["revision"],
        })
    results.save_review(project, "receipt", {
        "revision": base["revision"], "candidate_revision": newer["revision"],
        "status": "confirmed", "fields": {"total_amount": "155"},
    })
    assert detail(project)["candidate"] is None
    assert detail(project)["confirmed_row"][5] == "155"


def test_source_and_configuration_changes_reject_stale_check(project):
    snapshot = results.inspect(project, "receipt")
    common.save_json(common.project_dir(project) / "project.json", {"name": "Changed"})
    with pytest.raises(results.ReviewConflict, match="setup changed"):
        results.save(project, "receipt", reading(), **{
            "source_digest": snapshot["source_digest"], "config_digest": snapshot["config_digest"],
        })
    assert detail(project)["revision"] is None
    snapshot = results.inspect(project, "receipt")
    Image.new("RGB", (72, 72), "red").save(common.project_dir(project) / "invoices" / "receipt.png")
    with pytest.raises(results.ReviewConflict, match="file changed"):
        results.save(project, "receipt", reading(), **{
            "source_digest": snapshot["source_digest"], "config_digest": snapshot["config_digest"],
        })
    assert detail(project)["revision"] is None


def test_replaced_source_cannot_be_reviewed_using_old_evidence(project):
    check(project)
    before = detail(project)
    source = common.project_dir(project) / "invoices" / "receipt.png"
    Image.new("RGB", (72, 72), "red").save(source)

    with pytest.raises(results.ReviewConflict, match="invoice file has changed"):
        results.save_review(project, "receipt", {"revision": before["revision"], "status": "confirmed"})
    assert detail(project) == before

    results.save(project, "receipt", reading(), intent="recheck", expected_revision=before["revision"])
    assert detail(project)["result"]["source_digest"] != before["result"]["source_digest"]


def test_page_sets_preserve_confirmed_and_rechecked_sources(project):
    from pages import render

    check(project)
    confirm(project)
    before = detail(project)
    original = render(project, "receipt", before["result"]["source_digest"])
    original_bytes = Path(original[0]["path"]).read_bytes()
    source = common.project_dir(project) / "invoices" / "receipt.png"
    Image.new("RGB", (72, 72), "red").save(source)
    check(project, "130")
    pending = detail(project)
    candidate = render(project, "receipt", pending["candidate"]["result"]["source_digest"])
    confirmed = render(project, "receipt", pending["result"]["source_digest"])
    assert confirmed == original
    assert Path(confirmed[0]["path"]).read_bytes() == original_bytes
    assert candidate[0]["path"] != confirmed[0]["path"]
    assert Image.open(candidate[0]["path"]).getpixel((0, 0)) == (255, 0, 0)


def test_changed_source_without_historical_pages_is_not_shown_as_old_evidence(project):
    from pages import render
    from shutil import rmtree

    check(project)
    before = detail(project)
    old_pages = render(project, "receipt", before["result"]["source_digest"])
    rmtree(Path(old_pages[0]["path"]).parent)
    Image.new("RGB", (72, 72), "red").save(common.project_dir(project) / "invoices" / "receipt.png")
    with pytest.raises(common.WorkspaceError, match="original document pages are unavailable"):
        render(project, "receipt", before["result"]["source_digest"])


def test_concurrent_page_renders_publish_complete_multipage_sets(project):
    from pages import render

    folder = common.project_dir(project) / "invoices"
    (folder / "receipt.png").unlink()
    Image.new("RGB", (72, 72), "white").save(
        folder / "receipt.pdf", save_all=True,
        append_images=[Image.new("RGB", (72, 72), "red")])
    with ThreadPoolExecutor(max_workers=4) as pool:
        results_list = list(pool.map(lambda _: render(project, "receipt"), range(4)))
    assert all(pages == results_list[0] for pages in results_list)
    assert len(results_list[0]) == 2
    assert all(Path(page["path"]).is_file() for page in results_list[0])


def test_simultaneous_initial_checks_preserve_first_result(project):
    def attempt(amount):
        try:
            results.save(project, "receipt", reading(amount))
            return "saved"
        except results.ReviewConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, ["100", "200"])) == ["conflict", "saved"]
    assert detail(project)["result"]["fields"]["total_amount"]["value"] in {"100", "200"}


def test_failed_candidate_accept_keeps_confirmation_and_candidate(project, monkeypatch):
    check(project)
    confirm(project)
    check(project, "200")
    before = detail(project)

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(results, "draw", fail)
    with pytest.raises(OSError, match="disk full"):
        results.accept_recheck(project, "receipt", {
            "revision": before["revision"], "candidate_revision": before["candidate"]["revision"],
        })
    assert detail(project) == before


def test_review_side_effects_reconcile_after_post_commit_failure(project, monkeypatch):
    check(project)
    before = detail(project)
    real_log = results.log
    attempts = []

    def fail_first(slug, who, action, details):
        if action == "review saved" and not attempts:
            attempts.append(True)
            raise OSError("history unavailable")
        return real_log(slug, who, action, details)

    monkeypatch.setattr(results, "log", fail_first)
    saved = results.save_review(project, "receipt", {
        "revision": before["revision"], "status": "confirmed", "learning": "Read the total in the receipt.",
    })
    assert saved["review"]["status"] == "confirmed"
    stored = common.load_json(common.result_path(project, "receipt"))
    assert len(stored["_pending_effects"]) == 1
    assert len(common.load_json(common.project_dir(project) / "learnings.json")) == 1
    results.inspect(project, "receipt")
    results.inspect(project, "receipt")
    assert len(common.load_json(common.project_dir(project) / "learnings.json")) == 1
    assert sum(item["action"] == "review saved" for item in common.read_history(project)) == 1
    assert "_pending_effects" not in common.load_json(common.result_path(project, "receipt"))


def test_recalculation_cannot_replace_unconfirmed_staff_draft(project):
    check(project)
    results.save_review(project, "receipt", {
        "revision": detail(project)["revision"], "status": "draft",
        "fields": {"total_amount": "150"},
    })
    before = detail(project)
    with pytest.raises(results.ReviewConflict, match="staff draft"):
        checks.run(project, "receipt")
    assert detail(project) == before


def test_corrupt_unrelated_result_reports_duplicate_check_failure(project):
    file = common.project_dir(project) / "results" / "broken.json"
    file.parent.mkdir(exist_ok=True)
    file.write_text("{invalid", encoding="utf-8")
    with pytest.raises(common.WorkspaceError, match="broken.json.*cannot be read"):
        check(project)
    assert file.read_text(encoding="utf-8") == "{invalid"
    assert not common.result_path(project, "receipt").exists()


def test_corrupt_legacy_same_stem_marks_both_sources_ambiguous(project):
    folder = common.project_dir(project) / "invoices"
    Image.new("RGB", (72, 72), "red").save(folder / "receipt.jpg")
    file = common.result_path(project, "receipt")
    file.parent.mkdir(exist_ok=True)
    file.write_text("{invalid", encoding="utf-8")
    files = common.invoice_files(project)
    assert len(files) == 2
    assert common.ambiguous_invoice_ids(project) == set(files)
    for invoice_id in files:
        with pytest.raises(results.ReviewConflict, match="Multiple invoice files"):
            results.save(project, invoice_id, reading())
