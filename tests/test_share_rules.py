"""Rules archives can be shared without changing existing project decisions."""
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import common
import project
import share_rules


def test_rules_archive_import_and_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "PROJECTS", tmp_path / "projects")
    source = project.create("Source", None)
    target = project.create("Target", None)
    path = common.project_dir(source) / "rules.json"
    common.save_json(path, [{"id": "A", "type_id": "INVOICE", "name": "Amount",
        "check": "required", "field": "total_amount", "status": "confirmed", "enabled": True}])
    archive = tmp_path / "rules.zip"
    archive.write_bytes(share_rules.export_bytes(source))
    result = share_rules.import_rules(target, archive)
    assert len(result["added"]) == 1
    assert common.load_config(target)["rules"][0]["status"] == "proposed"
    assert share_rules.import_rules(target, archive)["already_present"] == 1


def test_rejects_extra_archive_members(tmp_path):
    path = tmp_path / "invalid.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("../escape", "bad")
        archive.writestr("rules.json", "{}")
    with pytest.raises(common.WorkspaceError):
        share_rules.read_archive(path)
