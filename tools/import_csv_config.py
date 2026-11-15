"""Create a project from the CSV configuration format of the earlier invoice agent prototype.

Usage:
  python tools/import_csv_config.py "<project name>" <invoice_types.csv> <extraction_fields.csv> <compliance_rules.csv>
      [--groups general,aexcid] [--confirm-rules R_VOL_101,R_VOL_001,...]

Imported rules start as "proposed" unless listed in --confirm-rules. Rule types that the
workspace does not support yet (conditional and cross-field checks) are skipped and listed.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys

from common import PROJECTS, WorkspaceError, log, print_json, save_json
from project import create

KINDS = {"decimal": "amount", "date": "date"}
CHECKS = {"required": "required", "regex": "regex", "range": "range", "enum": "enum", "visual_check": "visual"}


def fill_placeholders(text: str) -> str:
    """'{project.file_number|any file number}' becomes 'any file number'; others become a plain phrase."""
    text = re.sub(r"\{[^{}|]+\|([^{}]+)\}", r"\1", text or "")
    return re.sub(r"\{[^{}]+\}", "the configured limit", text)


def read(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("types")
    parser.add_argument("fields")
    parser.add_argument("rules")
    parser.add_argument("--groups", default="general,aexcid")
    parser.add_argument("--confirm-rules", default="")
    args = parser.parse_args()
    groups = {g.strip() for g in args.groups.split(",") if g.strip()}
    confirm = {r.strip() for r in args.confirm_rules.split(",") if r.strip()}
    try:
        slug = create(args.name, None)
        types = [{
            "id": row["invoice_type_id"],
            "name": row.get("display_name") or row["invoice_type_id"],
            "budget_line": row.get("budget_line", ""),
            "description": row.get("description", ""),
            "what_to_look_for": row.get("agent_context", ""),
            "enabled": row.get("enabled", "true").lower() == "true",
        } for row in read(args.types)]
        type_ids = {t["id"] for t in types}
        field_rows = [row for row in read(args.fields) if row["invoice_type_id"] in type_ids]
        field_names = {row["field_id"]: row["field_name"] for row in field_rows}
        fields = [{
            "id": row["field_id"],
            "type_id": row["invoice_type_id"],
            "name": row["field_name"],
            "label": row.get("field_label") or row["field_name"],
            "kind": KINDS.get(row.get("data_type", ""), "text"),
            "required": row.get("required", "false").lower() == "true",
            "hint": row.get("extraction_hint", ""),
        } for row in field_rows]
        rules, skipped = [], []
        for row in read(args.rules):
            if row["invoice_type_id"] not in type_ids or row.get("rule_group", "general") not in groups:
                continue
            check = CHECKS.get(row["check_type"])
            value = fill_placeholders(row.get("check_value", ""))
            if check is None or (check in ("range", "enum") and "configured limit" in value):
                skipped.append(row["rule_id"])
                continue
            is_visual = check == "visual"
            rules.append({
                "id": row["rule_id"],
                "type_id": row["invoice_type_id"],
                "name": row.get("rule_name", row["rule_id"]).replace("_", " "),
                "check": check,
                "field": None if is_visual else field_names.get(row.get("field_id", "")),
                "value": "" if is_visual or check == "required" else value,
                "severity": row.get("severity", "error"),
                "description": value if is_visual else fill_placeholders(row.get("agent_hint") or row.get("error_message", "")),
                "hint": fill_placeholders(row.get("agent_hint", "")) if is_visual else "",
                "source": f"Imported from the prototype configuration ({row.get('rule_group', 'general')})",
                "status": "confirmed" if row["rule_id"] in confirm else "proposed",
                "enabled": row.get("enabled", "true").lower() == "true",
            })
        base = f"projects/{slug}"
        save_json(PROJECTS / slug / "invoice_types.json", types)
        save_json(PROJECTS / slug / "fields.json", fields)
        save_json(PROJECTS / slug / "rules.json", rules)
        log(slug, "staff", "configuration imported", {"types": len(types), "fields": len(fields), "rules": len(rules),
                                                       "skipped": skipped})
        print_json({"project": base, "types": len(types), "fields": len(fields), "rules": len(rules),
                    "confirmed": sum(r["status"] == "confirmed" for r in rules), "skipped": skipped})
    except (WorkspaceError, KeyError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
