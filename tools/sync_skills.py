"""Copy the skills to where Claude Code and Codex read them, and apply the model settings.

Claude Code reads .claude/skills/, Codex reads .agents/skills/. Copies are used instead of
links because Git on Windows often does not create symbolic links.

assistant-settings.json supplies defaults. The website saves preferences in assistant-settings.local.json.
Only skill files present in skills/ and the managed model settings are updated:
- Claude Code: each skill copy gets `model` and `effort` in its header (they apply while the
  skill runs), and .claude/settings.json gets the default for everything else.
- Codex: skills cannot set their own model, so .codex/config.toml gets one model and effort
  for the whole project. Codex only reads it once the project is trusted.

Usage:
  ./.tools/uv run tools/sync_skills.py          # write the copies and settings
  ./.tools/uv run tools/sync_skills.py --check  # exit 1 if anything is out of date
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import tomlkit

from common import ROOT, load_json

SOURCE = ROOT / "skills"
CLAUDE_SKILLS = ROOT / ".claude" / "skills"
CODEX_SKILLS = ROOT / ".agents" / "skills"
SHIPPED_SETTINGS = ROOT / "assistant-settings.json"
SETTINGS_FILE = ROOT / "assistant-settings.local.json"
CLAUDE_SETTINGS = ROOT / ".claude" / "settings.json"
CODEX_CONFIG = ROOT / ".codex" / "config.toml"

JOBS = {"check-invoices": "reading", "run-evaluation": "reading", "propose-rules": "rules", "suggest-improvements": "rules"}
CLAUDE_MODELS = ("haiku", "sonnet", "opus")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
DEFAULT_SETTINGS = {
    "claude": {
        "reading": {"model": "sonnet", "effort": "medium"},
        "rules": {"model": "opus", "effort": "high"},
        "other": {"model": "sonnet", "effort": "low"},
    },
    "codex": {"model": "", "effort": "medium"},
}


def load_settings() -> dict:
    settings = json.loads(json.dumps(DEFAULT_SETTINGS))
    saved = load_json(SETTINGS_FILE) if SETTINGS_FILE.exists() else load_json(SHIPPED_SETTINGS, {})
    saved = saved or {}
    for job, value in (saved.get("claude") or {}).items():
        if job in settings["claude"] and isinstance(value, dict):
            settings["claude"][job].update({k: v for k, v in value.items() if k in ("model", "effort")})
    if isinstance(saved.get("codex"), dict):
        settings["codex"].update({k: v for k, v in saved["codex"].items() if k in ("model", "effort")})
    return settings


def validate(settings: dict) -> list[str]:
    problems = []
    for job, value in settings["claude"].items():
        if value["model"] not in CLAUDE_MODELS:
            problems.append(f"Claude model for {job} must be one of {', '.join(CLAUDE_MODELS)}.")
        if value["effort"] not in EFFORTS:
            problems.append(f"Claude effort for {job} must be one of {', '.join(EFFORTS)}.")
    if settings["codex"]["effort"] not in EFFORTS:
        problems.append(f"Codex effort must be one of {', '.join(EFFORTS)}.")
    model = settings["codex"]["model"]
    if model and (len(model) > 60 or any(c in model for c in "\"'\n\\ ")):
        problems.append("The Codex model name looks wrong. Use a name like the ones in the Codex model menu.")
    return problems


def _with_header(text: str, extra: dict[str, str]) -> str:
    if not extra or not text.startswith("---\n"):
        return text
    end = text.index("\n---", 4)
    header = [line for line in text[4:end].splitlines() if not line.startswith(("model:", "effort:"))]
    header += [f"{key}: {value}" for key, value in extra.items()]
    return "---\n" + "\n".join(header) + text[end:]


def expected_files(settings: dict) -> dict[Path, str]:
    files: dict[Path, str] = {}
    for skill in sorted(p for p in SOURCE.iterdir() if p.is_dir()):
        for path in sorted(p for p in skill.rglob("*") if p.is_file() and p.name != ".DS_Store"):
            relative = path.relative_to(SOURCE)
            text = path.read_text(encoding="utf-8")
            files[CODEX_SKILLS / relative] = text
            if path.name == "SKILL.md" and skill.name in JOBS:
                job = settings["claude"][JOBS[skill.name]]
                text = _with_header(text, {"model": job["model"], "effort": job["effort"]})
            files[CLAUDE_SKILLS / relative] = text
    claude_settings = load_json(CLAUDE_SETTINGS, {}) or {}
    other = settings["claude"]["other"]
    claude_settings["model"] = other["model"]
    claude_settings["effortLevel"] = "xhigh" if other["effort"] == "max" else other["effort"]
    files[CLAUDE_SETTINGS] = json.dumps(claude_settings, indent=2) + "\n"
    codex = settings["codex"]
    config = tomlkit.parse(CODEX_CONFIG.read_text(encoding="utf-8")) if CODEX_CONFIG.exists() else tomlkit.document()
    if codex["model"]:
        config["model"] = codex["model"]
    else:
        config.pop("model", None)
    config["model_reasoning_effort"] = codex["effort"]
    files[CODEX_CONFIG] = config.as_string()
    return files


def out_of_date(settings: dict) -> list[str]:
    files = expected_files(settings)
    stale = [str(p.relative_to(ROOT)) for p, text in files.items()
             if not p.exists() or p.read_text(encoding="utf-8") != text]
    return stale


def sync(settings: dict) -> None:
    files = expected_files(settings)
    for path, text in files.items():
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def main() -> int:
    settings = load_settings()
    problems = validate(settings)
    if problems:
        print("Error: " + " ".join(problems), file=sys.stderr)
        return 1
    if "--check" in sys.argv:
        stale = out_of_date(settings)
        if stale:
            print("Out of date: " + ", ".join(stale))
            return 1
        print("Skills and settings are in sync.")
        return 0
    sync(settings)
    print("Updated .claude/skills, .agents/skills, .claude/settings.json and .codex/config.toml.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
