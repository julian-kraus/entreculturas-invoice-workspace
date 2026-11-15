"""Create the Excel report for the selected project.

Usage:
  python tools/report.py
"""

from __future__ import annotations

import sys
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from checks import final_fields
from common import WorkspaceError, current_project, load_config, load_json, log, print_json, rel, set_dirs

FILLS = {"fails rules": "F8D7D2", "needs a look": "FBEBC8", "passes": "D6EEE3"}


def build(slug: str, who: str = "assistant") -> str:
    config = load_config(slug)
    type_names = {t["id"]: t.get("name", t["id"]) for t in config["invoice_types"]}
    _, results_dir = set_dirs(slug, "invoices")
    results = [load_json(p) for p in sorted(results_dir.glob("*.json"))] if results_dir.exists() else []
    book = Workbook()
    summary = book.active
    summary.title = "Invoices"
    summary.append(["Invoice", "File", "Type", "Status", "Date", "Total", "Currency", "Failed rules", "Reviewed"])
    findings = book.create_sheet("Findings")
    findings.append(["Invoice", "Rule", "Outcome", "Severity", "Explanation", "Changed by reviewer"])
    fields_sheet = book.create_sheet("Fields")
    fields_sheet.append(["Invoice", "Field", "Value", "Status", "Corrected by reviewer"])
    for result in results:
        fields = final_fields(result)
        value = lambda name: (fields.get(name) or {}).get("value")
        failed = [o["name"] for o in result.get("rule_results", []) if o["outcome"] == "failed"]
        review = result.get("review") or {}
        summary.append([result.get("invoice"), result.get("file"), type_names.get(result.get("type_id"), result.get("type_id")),
                        result.get("status", "not checked"), value("invoice_date"), value("total_amount"), value("currency"),
                        "; ".join(failed), "yes" if review.get("status") == "confirmed" else "no"])
        fill = FILLS.get(result.get("status"))
        if fill:
            summary.cell(row=summary.max_row, column=4).fill = PatternFill("solid", fgColor=fill)
        for outcome in result.get("rule_results", []):
            findings.append([result.get("invoice"), outcome["name"], outcome["outcome"], outcome["severity"],
                             outcome.get("message", ""), "yes" if outcome.get("overridden") else ""])
        for name, field in fields.items():
            fields_sheet.append([result.get("invoice"), name, field.get("value"), field.get("status"),
                                 "yes" if field.get("corrected") else ""])
    for sheet in (summary, findings, fields_sheet):
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for index, column in enumerate(sheet.columns, start=1):
            width = max((len(str(c.value)) for c in column if c.value is not None), default=8)
            sheet.column_dimensions[get_column_letter(index)].width = min(max(width + 2, 10), 60)
        sheet.freeze_panes = "A2"
    path = results_dir / f"report-{datetime.now().strftime('%Y%m%d-%H%M')}.xlsx"
    path.parent.mkdir(parents=True, exist_ok=True)
    book.save(path)
    log(slug, who, "report created", {"file": path.name, "invoices": len(results)})
    return rel(path)


def main() -> int:
    try:
        print_json({"report": build(current_project())})
    except WorkspaceError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())


def build_setup(slug: str, who: str = "staff") -> str:
    """A readable Excel copy of the project setup: invoice types, fields to extract, rules and tips."""
    config = load_config(slug)
    book = Workbook()
    sheets = [
        ("Invoice types", ["id", "name", "budget_line", "description", "what_to_look_for", "enabled"], config["invoice_types"]),
        ("Fields to extract", ["id", "type_id", "label", "name", "kind", "required", "hint"], config["fields"]),
        ("Rules", ["id", "type_id", "status", "name", "check", "field", "value", "severity", "description", "hint", "source", "enabled"], config["rules"]),
        ("Tips", ["id", "type_id", "text", "source_invoice", "created", "active"], config["learnings"]),
    ]
    for index, (title, columns, rows) in enumerate(sheets):
        sheet = book.active if index == 0 else book.create_sheet()
        sheet.title = title
        sheet.append(columns)
        for row in rows:
            sheet.append([str(row.get(c)) if isinstance(row.get(c), (list, dict)) else row.get(c) for c in columns])
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for col, _ in enumerate(columns, start=1):
            sheet.column_dimensions[get_column_letter(col)].width = 18 if col < 4 else 45
        sheet.freeze_panes = "A2"
    _, results_dir = set_dirs(slug, "invoices")
    path = results_dir / f"setup-{slug}-{datetime.now().strftime('%Y%m%d-%H%M')}.xlsx"
    path.parent.mkdir(parents=True, exist_ok=True)
    book.save(path)
    log(slug, who, "setup exported", {"file": path.name})
    return rel(path)
