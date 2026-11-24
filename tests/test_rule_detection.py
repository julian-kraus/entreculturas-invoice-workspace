"""Rule detection publishes only validated, project-scoped proposals."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import common
import detect_rules
from project import create


def test_detection_validates_citations_and_reserves_project(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "PROJECTS", tmp_path / "projects")
    slug = create("Detection", None)
    guidelines = common.project_dir(slug) / "guidelines"
    (guidelines / "source.txt").write_text("Invoices must include a date.", encoding="utf-8")
    monkeypatch.setattr(detect_rules.shutil, "which", lambda name: "/fake/codex")

    class Completed:
        returncode = 0

    def run(args, **kwargs):
        result = {"rules": [{"name": "Date present", "description": "Include a date.",
            "hint": "Invoice date", "reason": "Required by the guideline.", "type_id": "ALL",
            "source_file": "source.txt", "source_page": 1}]}
        Path(args[args.index("-o") + 1]).write_text(json.dumps(result))
        return Completed()

    monkeypatch.setattr(detect_rules.subprocess, "run", run)
    reservation = detect_rules._reservation(slug)
    with pytest.raises(Exception):
        detect_rules._reservation(slug)
    detect_rules._running.add(slug)
    detect_rules._run(slug, reservation)
    assert detect_rules.status(slug)["count"] == 1
    rule = common.load_config(slug)["rules"][0]
    assert rule["status"] == "proposed"
    assert rule["source"] == "source.txt, page 1"


def test_detection_recovers_interrupted_job(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "PROJECTS", tmp_path / "projects")
    slug = create("Interrupted", None)
    common.save_json(detect_rules._state_path(slug), {"status": "running"})
    assert detect_rules.status(slug)["status"] == "failed"


def test_guideline_added_during_detection_is_in_next_run(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "PROJECTS", tmp_path / "projects")
    slug = create("Race", None)
    guidelines = common.project_dir(slug) / "guidelines"
    (guidelines / "first.txt").write_text("First rule", encoding="utf-8")
    monkeypatch.setattr(detect_rules.shutil, "which", lambda name: "/fake/codex")
    calls = []

    class Completed:
        returncode = 0

    def run(args, **kwargs):
        calls.append(kwargs["input"])
        if len(calls) == 1:
            with detect_rules.review_lock(slug):
                (guidelines / "second.txt").write_text("Second rule", encoding="utf-8")
        else:
            assert "second.txt" in kwargs["input"]
        result = {"rules": [{"name": "First", "description": "First rule",
            "hint": "Invoice", "reason": "Required", "type_id": "ALL",
            "source_file": "first.txt", "source_page": 1}]}
        Path(args[args.index("-o") + 1]).write_text(json.dumps(result))
        return Completed()

    monkeypatch.setattr(detect_rules.subprocess, "run", run)
    reservation = detect_rules._reservation(slug)
    detect_rules._running.add(slug)
    detect_rules._run(slug, reservation)
    assert len(calls) == 2
    assert detect_rules.status(slug)["status"] == "completed"
    assert len(common.load_config(slug)["rules"]) == 1


def test_request_during_final_run_queues_followup(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "PROJECTS", tmp_path / "projects")
    slug = create("Queue", None)
    (common.project_dir(slug) / "guidelines" / "source.txt").write_text("Requirement", encoding="utf-8")
    monkeypatch.setattr(detect_rules.shutil, "which", lambda name: "/fake/codex")
    calls = []

    class Completed:
        returncode = 0

    def run(args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            assert detect_rules.start(slug)["status"] == "running"
        Path(args[args.index("-o") + 1]).write_text('{"rules": []}')
        return Completed()

    monkeypatch.setattr(detect_rules.subprocess, "run", run)
    reservation = detect_rules._reservation(slug)
    detect_rules._running.add(slug)
    detect_rules._run(slug, reservation)
    assert len(calls) == 2
    assert detect_rules.status(slug)["status"] == "completed"
