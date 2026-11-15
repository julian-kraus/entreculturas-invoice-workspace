"""Projects: list, show, switch and create.

Usage:
  python tools/project.py list
  python tools/project.py show            # what the assistant needs to check invoices
  python tools/project.py switch <project>
  python tools/project.py create "<name>" [--copy-rules-from <project>]
"""

from __future__ import annotations

import argparse
import shutil
import sys

from common import (
    PROJECTS, WorkspaceError, current_project, invoice_files, list_projects, load_config,
    load_json, log, now_iso, print_json, project_dir, result_path, save_json, set_current_project, slugify,
)

CONFIG_FILES = ("invoice_types.json", "fields.json", "rules.json")


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


def create(name: str, copy_from: str | None) -> str:
    slug = slugify(name)
    target = PROJECTS / slug
    if target.exists():
        raise WorkspaceError(f"A project called '{slug}' already exists.")
    target.mkdir(parents=True)
    for sub in ("invoices", "results", "guidelines", "evaluation/invoices", "evaluation/latest", "evaluation/runs"):
        (target / sub).mkdir(parents=True, exist_ok=True)
    save_json(target / "project.json", {"name": name, "funder": "", "period_start": "", "period_end": "", "currency": ""})
    if copy_from:
        source = project_dir(copy_from)
        for filename in CONFIG_FILES:
            if (source / filename).exists():
                shutil.copy(source / filename, target / filename)
        rules = load_json(target / "rules.json", [])
        for rule in rules:
            if rule.get("status") == "confirmed":
                rule["status"] = "proposed"
        save_json(target / "rules.json", rules)
    else:
        for filename in CONFIG_FILES:
            save_json(target / filename, [])
    save_json(target / "learnings.json", [])
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
    for key in ("invoice_types", "fields", "rules", "learnings"):
        if not isinstance(setup.get(key, []), list):
            raise WorkspaceError(f"The setup file has an invalid '{key}' part.")
    slug = create(name, None)
    target = PROJECTS / slug
    info = setup.get("project") if isinstance(setup.get("project"), dict) else {}
    save_json(target / "project.json", info | {"name": name})
    for key in ("invoice_types", "fields", "rules", "learnings"):
        save_json(target / f"{key}.json", setup.get(key, []))
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
    new.add_argument("--copy-rules-from")
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
            slug = create(args.name, args.copy_rules_from)
            set_current_project(slug)
            print_json({"created": slug, "current": slug})
    except WorkspaceError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
