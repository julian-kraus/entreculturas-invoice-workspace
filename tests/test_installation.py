"""Installation boundaries shared by the two assistant clients."""

import json
import sys
from pathlib import Path

import tomlkit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import sync_skills


def test_sync_preserves_local_skills_and_unrelated_settings(tmp_path, monkeypatch):
    paths = {
        "ROOT": tmp_path,
        "SOURCE": tmp_path / "skills",
        "CLAUDE_SKILLS": tmp_path / ".claude" / "skills",
        "CODEX_SKILLS": tmp_path / ".agents" / "skills",
        "CLAUDE_SETTINGS": tmp_path / ".claude" / "settings.json",
        "CODEX_CONFIG": tmp_path / ".codex" / "config.toml",
    }
    for name, path in paths.items():
        monkeypatch.setattr(sync_skills, name, path)
    source = paths["SOURCE"] / "check-invoices" / "SKILL.md"
    source.parent.mkdir(parents=True)
    source.write_text("---\nname: check-invoices\n---\nRead the invoice.\n")
    local = paths["CODEX_SKILLS"] / "team-help" / "SKILL.md"
    local.parent.mkdir(parents=True)
    local.write_text("Team instructions")
    paths["CODEX_CONFIG"].parent.mkdir()
    paths["CODEX_CONFIG"].write_text('model = "old"\n# Keep these settings\n[features]\nexample = true\n')
    paths["CLAUDE_SETTINGS"].parent.mkdir()
    paths["CLAUDE_SETTINGS"].write_text('{"permissions":{"allow":[]}}')

    settings = sync_skills.DEFAULT_SETTINGS
    sync_skills.sync(settings)
    assert local.read_text() == "Team instructions"
    output = paths["CODEX_CONFIG"].read_text()
    config = tomlkit.parse(output)
    assert config["features"]["example"] is True
    assert config["model_reasoning_effort"] == settings["codex"]["effort"]
    assert "model" not in config and "# Keep these settings" in output
    assert "permissions" in json.loads(paths["CLAUDE_SETTINGS"].read_text())
    assert sync_skills.out_of_date(settings) == []


def test_example_is_an_importable_rule_template():
    path = Path(__file__).resolve().parents[1] / "templates" / "example-aexcid.json"
    template = json.loads(path.read_text(encoding="utf-8"))
    assert template["format"] == "invoice-workspace-setup/1"
    assert template["invoice_types"] and template["fields"] and template["rules"]
    assert template["learnings"] == []
    assert "proposals" not in template
    assert all(rule["status"] != "confirmed" for rule in template["rules"])
