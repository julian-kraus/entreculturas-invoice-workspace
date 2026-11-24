"""Projects: list, show, switch and create.

Usage:
  ./.tools/uv run tools/project.py list
  ./.tools/uv run tools/project.py show            # what the assistant needs to check invoices
  ./.tools/uv run tools/project.py switch <project>
  ./.tools/uv run tools/project.py create "<name>" [--template | --copy-rules-from <project>]
"""

from __future__ import annotations

import argparse
import errno
import sys
import tempfile
from pathlib import Path

from common import (
    WorkspaceError, current_project, existing_project, invoice_files, list_projects, load_config,
    load_json, log, now_iso, print_json, project_dir, result_path, save_json, set_current_project, slugify, storage_slug,
)


def project_summary(slug: str) -> dict:
    config = load_config(slug)
    invoices = invoice_files(slug)
    checked = [i for i in invoices if result_path(slug, i).exists()]
    rules = config["rules"]
    return {
        "slug": slug,
        "name": config["project"].get("name", slug),
        "invoices": len(invoices),
        "checked": len(checked),
        "rules_confirmed": sum(1 for r in rules if r.get("status") == "confirmed" and r.get("enabled", True)),
        "rules_proposed": sum(1 for r in rules if r.get("status") == "proposed"),
    }


def show(slug: str) -> dict:
    """Everything needed to read invoices for this project, without proposed or rejected rules."""
    config = load_config(slug)
    types = [t for t in config["invoice_types"] if t.get("enabled", True)]
    fields_by_type: dict[str, list] = {}
    for field in config["fields"]:
        fields_by_type.setdefault(field["type_id"], []).append({
            "name": field["name"], "label": field["label"], "kind": field.get("kind", "text"),
            "required": field.get("required", False), "hint": field.get("hint", ""),
        })
    rules = [
        {k: r.get(k) for k in ("id", "type_id", "name", "check", "field", "value", "severity", "description", "hint")}
        for r in config["rules"]
        if r.get("status") == "confirmed" and r.get("enabled", True)
    ]
    learnings = [l for l in config["learnings"] if l.get("active", True)]
    return {
        "project": config["project"] | {"slug": slug},
        "invoice_types": types,
        "fields_by_type": fields_by_type,
        "confirmed_rules": rules,
        "visual_rules_to_judge": [r["id"] for r in rules if r["check"] == "visual"],
        "learnings": learnings,
    }


def _publish_project(name: str, setup: dict) -> str:
    name = name.strip()
    if not name:
        raise WorkspaceError("Give the project a name.")
    slug = storage_slug(name)
    target = project_dir(slug)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise WorkspaceError(f"A project called '{slug}' already exists.")
    # Publish only after the complete setup is readable; a failed copy/import
    # must not leave a half-created project that blocks a retry.
    with tempfile.TemporaryDirectory(prefix=".new-project-", dir=target.parent) as tmp:
        staging = Path(tmp) / "project"
        for sub in ("invoices", "results", "guidelines"):
            (staging / sub).mkdir(parents=True)
        for key in ("invoice_types", "fields", "rules", "learnings"):
            save_json(staging / f"{key}.json", setup[key])
        save_json(staging / "project.json", setup["project"] | {"name": name})
        try:
            staging.rename(target)
        except OSError as error:
            if error.errno in (errno.EEXIST, errno.ENOTEMPTY) or target.exists():
                raise WorkspaceError(f"A project called '{slug}' already exists.") from error
            raise
    return slug


def create(name: str, copy_from: str | None, *, template: bool = False) -> str:
    if template:
        if copy_from:
            raise WorkspaceError("Choose one starting setup for your project.")
        bundled = Path(__file__).resolve().parents[1] / "templates" / "example-aexcid.json"
        return import_setup(name, load_json(bundled))
    if copy_from:
        config = load_config(existing_project(copy_from))
        for rule in config["rules"]:
            if rule.get("status") == "confirmed":
                rule["status"] = "proposed"
    else:
        config = {"rules": [], "invoice_types": [{
            "id": "INVOICE", "name": "Invoice", "enabled": True,
            "description": "An invoice or receipt documenting an expense.",
            "what_to_look_for": "Look for the supplier, date, invoice number, total and currency.",
        }]}
        starter_fields = [
            ("supplier", "Supplier", "text"), ("invoice_number", "Invoice number", "text"),
            ("invoice_date", "Invoice date", "date"), ("total_amount", "Total amount", "amount"),
            ("currency", "Currency", "text"),
        ]
        config["fields"] = [
            {"id": f"INVOICE_{key}", "type_id": "INVOICE", "name": key, "label": label,
             "kind": kind, "hint": "", "required": False} for key, label, kind in starter_fields
        ]
    config["project"] = {"funder": "", "period_start": "", "period_end": "", "currency": ""}
    config["learnings"] = []
    slug = _publish_project(name, config)
    log(slug, "staff", "project created", {"name": name, "copied_rules_from": copy_from})
    return slug


SETUP_FORMAT = "invoice-workspace-setup/1"


def export_setup(slug: str) -> dict:
    """Everything a colleague needs to work the same way, without invoices or results."""
    config = load_config(slug)
    return {"format": SETUP_FORMAT, "exported_at": now_iso(), "project": config["project"],
            "invoice_types": config["invoice_types"], "fields": config["fields"], "rules": config["rules"],
            "learnings": config["learnings"]}


def import_setup(name: str, setup: dict) -> str:
    if not isinstance(setup, dict) or setup.get("format") != SETUP_FORMAT:
        raise WorkspaceError("This file is not a setup exported from the invoice workspace.")
    config = {"project": setup.get("project", {})}
    if not isinstance(config["project"], dict):
        raise WorkspaceError("The project's details are invalid.")
    for key in ("invoice_types", "fields", "rules", "learnings"):
        rows = setup.get(key, [])
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise WorkspaceError(f"The setup file has an invalid '{key}' part.")
        ids = [row.get("id") for row in rows]
        if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
            raise WorkspaceError(f"Every entry in '{key}' needs its own id.")
        config[key] = rows
    slug = _publish_project(name, config)
    log(slug, "staff", "project created from a setup file", {"exported_at": setup.get("exported_at"),
        "rules": len(setup.get("rules", [])), "types": len(setup.get("invoice_types", []))})
    return slug


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    sub.add_parser("show")
    switch = sub.add_parser("switch")
    switch.add_argument("project")
    new = sub.add_parser("create")
    new.add_argument("name")
    source = new.add_mutually_exclusive_group()
    source.add_argument("--copy-rules-from")
    source.add_argument("--template", action="store_true", help="Start from the bundled AEXCID Template project.")
    args = parser.parse_args()
    try:
        if args.command == "list":
            try:
                current = current_project()
            except WorkspaceError:
                current = None
            print_json({"current": current, "projects": [project_summary(p["slug"]) for p in list_projects()]})
        elif args.command == "show":
            print_json(show(current_project()))
        elif args.command == "switch":
            wanted = args.project
            matches = [p["slug"] for p in list_projects()
                       if wanted == p["slug"] or slugify(wanted) == p["slug"] or wanted.lower() in p["name"].lower()]
            if len(matches) != 1:
                raise WorkspaceError(f"Found {len(matches)} projects matching '{wanted}': {matches or 'none'}.")
            set_current_project(matches[0])
            log(matches[0], "assistant", "project selected", {})
            print_json({"current": matches[0]})
        elif args.command == "create":
            slug = create(args.name, args.copy_rules_from, template=args.template)
            set_current_project(slug)
            print_json({"created": slug, "current": slug})
    except WorkspaceError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
