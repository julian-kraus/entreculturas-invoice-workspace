"""Build project workbooks and select data for individual invoice exports.

Usage:
  ./.tools/uv run tools/report.py
"""

from __future__ import annotations

import sys
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from checks import final_fields, record_for_display
from common import WorkspaceError, current_project, load_config, load_json, log, print_json, project_dir, rel

FILLS = {"fails rules": "F8D7D2", "needs a look": "FBEBC8", "passes": "D6EEE3", "no applicable rules": "FBEBC8"}


SUMMARY_COLUMNS = ["Invoice", "File", "Type", "Status", "Date", "Total", "Currency", "Failed rules", "Reviewed", "Rules checked"]


def summary_row(result: dict, type_names: dict) -> list:
    fields = final_fields(result)
    failed = [o["name"] for o in result.get("rule_results", []) if o["outcome"] == "failed"]
    return [
        result["invoice"], result.get("display_file", result.get("file")), type_names.get(result["type_id"], result["type_id"]),
        result.get("status"), fields.get("invoice_date", {}).get("value"), fields.get("total_amount", {}).get("value"),
        fields.get("currency", {}).get("value"), "; ".join(failed),
        "yes" if (result.get("review") or {}).get("status") == "confirmed" else "no", result.get("rules_checked", 0),
    ]



REGISTER_COLUMNS = [
    "Id", "Invoice Number", "Date", "Supplier/Issuer", "Address", "Client Name",
    "Items/Services", "Description", "Total Amount", "Currency", "Payment Method",
    "Language", "Expense Category", "Source file",
]


def register_row(result: dict, config: dict) -> list:
    """Map explicit extracted values into the team's register columns."""
    fields = final_fields(result)
    labels = {f["name"]: f.get("label", "") for f in config["fields"]
              if f.get("type_id") == result.get("type_id")}

    def value(*names):
        for name in names:
            item = fields.get(name) or {}
            if item.get("status") != "not_found" and item.get("value") not in (None, ""):
                return item["value"]
        return None

    def invoice_value(supplier_name, generic_name):
        # The AEXCID setup uses generic invoice_number/date for a funds request.
        supplier = value(supplier_name)
        if supplier is not None:
            return supplier
        if "funds request" in labels.get(generic_name, "").lower():
            return None
        return value(generic_name)

    return [
        result.get("invoice"),
        invoice_value("supplier_invoice_number", "invoice_number"),
        invoice_value("supplier_invoice_date", "invoice_date"),
        value("vendor_name", "supplier", "supplier_name"),
        value("vendor_address", "supplier_address", "address"),
        value("client_name", "client", "beneficiary"),
        value("item_description", "items_services", "items"),
        value("description", "expense_description"),
        value("total_amount"),
        value("currency"), value("payment_method"), value("language"),
        value("expense_category"),
        result.get("source_url") or result.get("display_file") or result.get("file"),
    ]


def invoice_results(slug: str, invoice_id: str, result: dict) -> dict:
    """Select the saved findings and values for a single-invoice export."""
    config = load_config(slug)
    type_id = result.get("type_id")
    invoice_type = next((item.get("name") for item in config["invoice_types"] if item["id"] == type_id), None)
    labels = {item["name"]: item.get("label") for item in config["fields"] if item["type_id"] == type_id}
    review = result.get("review") or {}
    return {
        "project": slug, "project_name": config["project"].get("name") or slug,
        "invoice": invoice_id, "file": result.get("display_file") or result.get("file") or invoice_id,
        "invoice_type": invoice_type or type_id, "status": result.get("status"),
        "checked_at": result.get("checked_at"), "review_status": review.get("status"),
        "reviewed_at": review.get("at"), "rules_checked": result.get("rules_checked", 0),
        "findings": [
            {"id": finding["rule_id"], "name": finding["name"], "outcome": finding["outcome"],
             "reason": finding.get("message", "")}
            for finding in result.get("rule_results", [])
        ],
        "fields": [
            {"id": name, "name": labels.get(name) or name, "value": field.get("value"),
             "status": field.get("status"), "corrected": field.get("corrected", False)}
            for name, field in final_fields(result).items()
        ],
    }


def build(slug: str, who: str = "assistant") -> str:
    config = load_config(slug)
    type_names = {t["id"]: t.get("name", t["id"]) for t in config["invoice_types"]}
    results_dir = project_dir(slug) / "results"
    results = [record_for_display(load_json(p)) for p in sorted(results_dir.glob("*.json")) if not p.name.startswith(".")]
    book = Workbook()
    summary = book.active
    summary.title = "Invoices"
    summary.append(SUMMARY_COLUMNS)
    register = book.create_sheet("Register")
    register.append(REGISTER_COLUMNS)
    findings = book.create_sheet("Findings")
    findings.append(["Invoice", "Rule", "Outcome", "Severity", "Explanation", "Changed by reviewer",
                     "Assistant outcome", "Assistant explanation", "Reviewer reason"])
    fields_sheet = book.create_sheet("Fields")
    fields_sheet.append(["Invoice", "Field", "Value", "Status", "Corrected by reviewer"])
    for result in results:
        fields = final_fields(result)
        summary.append(summary_row(result, type_names))
        register.append(register_row(result, config))
        fill = FILLS.get(result.get("status"))
        if fill:
            summary.cell(row=summary.max_row, column=4).fill = PatternFill("solid", fgColor=fill)
        for outcome in result.get("rule_results", []):
            findings.append([result.get("invoice"), outcome["name"], outcome["outcome"], outcome["severity"],
                             outcome.get("message", ""), "yes" if outcome.get("overridden") or outcome.get("review_reason") else "",
                             outcome.get("ai_outcome", outcome["outcome"]),
                             outcome.get("ai_message", outcome.get("message", "")), outcome.get("review_reason", "")])
        for name, field in fields.items():
            fields_sheet.append([result.get("invoice"), name, field.get("value"), field.get("status"),
                                 "yes" if field.get("corrected") else ""])
    for sheet in (summary, register, findings, fields_sheet):
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for index, column in enumerate(sheet.columns, start=1):
            for cell in column:
                # Invoice values and review explanations are user text, including a leading "=".
                if cell.data_type == "f":
                    cell.data_type = "s"
            width = max((len(str(c.value)) for c in column if c.value is not None), default=8)
            sheet.column_dimensions[get_column_letter(index)].width = min(max(width + 2, 10), 60)
        sheet.freeze_panes = "A2"
    path = results_dir / f"report-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.xlsx"
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
    results_dir = project_dir(slug) / "results"
    path = results_dir / f"setup-{slug}-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.xlsx"
    path.parent.mkdir(parents=True, exist_ok=True)
    book.save(path)
    log(slug, who, "setup exported", {"file": path.name})
    return rel(path)
