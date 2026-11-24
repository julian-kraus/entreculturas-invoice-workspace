"""Share confirmed rules as a ZIP and add shared rules to a project's Inbox.

Usage:
  ./.tools/uv run tools/share_rules.py export <zip-file>
  ./.tools/uv run tools/share_rules.py import <zip-file>
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

from common import WorkspaceError, current_project, load_config, log, now_iso, print_json, project_dir, save_json
from review_lock import review_lock
from rules import CHECKS

MAX_BYTES = 10 * 1024 * 1024
RULE_KEYS = ("type_id", "name", "check", "field", "value", "severity", "description", "hint", "source", "reason", "enabled")


def export_bytes(slug: str) -> bytes:
    with review_lock(slug):
        config = load_config(slug)
        payload = {
            "format": "invoice-workspace-rules/1",
            "project": config["project"].get("name", slug),
            "exported_at": now_iso(),
            "invoice_types": config["invoice_types"],
            "fields": config["fields"],
            "rules": [r for r in config["rules"] if r.get("status") == "confirmed"],
        }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("rules.json", json.dumps(payload, ensure_ascii=False, indent=2))
    return buffer.getvalue()


def read_archive(path: Path) -> dict:
    try:
        if path.stat().st_size > MAX_BYTES:
            raise WorkspaceError("The rules ZIP is too large.")
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) != 1 or entries[0].filename != "rules.json" or entries[0].file_size > MAX_BYTES:
                raise WorkspaceError("This rules ZIP must contain exactly one rules.json file.")
            raw = archive.read(entries[0])
        payload = json.loads(raw)
    except (OSError, zipfile.BadZipFile, UnicodeError, json.JSONDecodeError, RuntimeError) as error:
        raise WorkspaceError(f"Could not read the rules ZIP: {error}") from error
    if not isinstance(payload, dict) or payload.get("format") != "invoice-workspace-rules/1":
        raise WorkspaceError("This is not an invoice workspace rules ZIP.")
    if not isinstance(payload.get("rules"), list) or any(not isinstance(r, dict) for r in payload["rules"]):
        raise WorkspaceError("The rules ZIP contains invalid rules.")
    return payload


def fingerprint(rule: dict) -> str:
    content = {key: rule.get(key) for key in RULE_KEYS}
    return hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def import_rules(slug: str, path: Path) -> dict:
    payload = read_archive(path)
    with review_lock(slug):
        config = load_config(slug)
        types = {t["id"] for t in config["invoice_types"]} | {"ALL"}
        fields = {(f["type_id"], f["name"]) for f in config["fields"]}
        problems = []
        for rule in payload["rules"]:
            label = str(rule.get("name") or rule.get("id") or "Unnamed rule")
            kind = rule.get("check")
            type_id = rule.get("type_id")
            if any(key in rule and rule[key] is not None and not isinstance(rule[key], str)
                   for key in RULE_KEYS if key != "enabled"):
                problems.append(f"{label}: rule properties must be text")
                continue
            if "enabled" in rule and not isinstance(rule["enabled"], bool):
                problems.append(f"{label}: enabled must be true or false")
                continue
            if type_id not in types:
                problems.append(f"{label}: invoice type {type_id!r} is missing")
            elif kind not in CHECKS:
                problems.append(f"{label}: unsupported check {kind!r}")
            elif kind != "visual" and type_id != "ALL" and (type_id, rule.get("field")) not in fields:
                problems.append(f"{label}: field {rule.get('field')!r} is missing")
        if problems:
            raise WorkspaceError("Add the required invoice types and fields before importing:\n- " + "\n- ".join(problems))
        rules = config["rules"]
        known = {fingerprint(r) for r in rules}
        taken = {r["id"] for r in rules}
        added, skipped = [], 0
        for rule in payload["rules"]:
            key = fingerprint(rule)
            if key in known:
                skipped += 1
                continue
            number = 1
            while f"P{number:03d}" in taken:
                number += 1
            identifier = f"P{number:03d}"
            taken.add(identifier)
            known.add(key)
            proposed = {k: rule[k] for k in RULE_KEYS if k in rule}
            proposed.update({"id": identifier, "status": "proposed", "proposed_by": "shared rules",
                             "proposed_at": now_iso(), "shared_from": str(payload.get("project", "")),
                             "shared_rule_id": str(rule.get("id", ""))})
            rules.append(proposed)
            added.append(identifier)
        if added:
            save_json(project_dir(slug) / "rules.json", rules)
            log(slug, "assistant", "shared rules imported", {"rules": added, "source project": payload.get("project", "")})
    return {"added": added, "already_present": skipped, "source_project": payload.get("project", "")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("export", "import"))
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    try:
        slug = current_project()
        if args.command == "export":
            data = export_bytes(slug)
            with args.file.open("xb") as output:
                output.write(data)
            print_json({"file": str(args.file)})
        else:
            print_json(import_rules(slug, args.file))
    except (WorkspaceError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
