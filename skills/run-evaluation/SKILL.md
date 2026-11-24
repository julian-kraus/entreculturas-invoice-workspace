---
name: run-evaluation
description: Check all test invoices of the selected project again and compare the results with the answers people confirmed. Use when someone asks how well the checks work, after rules or descriptions changed, or asks to run the test invoices.
---

# Run the test invoices

Resolve the project once at the start. Pin that slug with `INVOICE_PROJECT` on all commands for this task as described in AGENTS.md.

Work from the repository root.

1. Run `./.tools/uv run tools/evaluate.py clear-latest` so every test invoice is checked fresh.
2. Run `./.tools/uv run tools/pages.py pending --set evaluation` to list the test invoices. If there are none, explain that test invoices are added under Evaluation from confirmed invoices, and stop.
3. Check each one exactly as described in the check-invoices skill, steps 1 to 3, but add `--set evaluation` to `pages.py render` and `results.py save`. Do not look at the confirmed answers in `evaluation/truth/` while checking.
4. Run `./.tools/uv run tools/evaluate.py score`.
5. Reply in plain words:
   - how many test invoices were checked, and how many are kept aside
   - per rule: matched, missed problems, false alarms, unclear. Missed problems matter most.
   - fields that were read wrongly
   - compare with the previous run if the person changed something since
   Point them to Evaluation on the workspace page for the details.
