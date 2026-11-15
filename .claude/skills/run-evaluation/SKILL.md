---
name: run-evaluation
description: Check all test invoices of the selected project again and compare the results with the answers people confirmed. Use when someone asks how well the checks work, after rules or descriptions changed, or asks to run the test invoices.
model: sonnet
effort: medium
---

# Run the test invoices

Work from the repository root (use `python3` if `python` is not found).

1. Run `python tools/evaluate.py clear-latest` so every test invoice is checked fresh.
2. Run `python tools/pages.py pending --set evaluation` to list the test invoices. If there are none, explain that test invoices are added on the workspace page from reviewed invoices, and stop.
3. Check each one exactly as described in the check-invoices skill, steps 1 to 3, but add `--set evaluation` to `pages.py render` and `results.py save`. Do not look at the confirmed answers in `evaluation/truth/` while checking.
4. Run `python tools/evaluate.py score`.
5. Reply in plain words:
   - how many test invoices were checked, and how many are kept aside
   - per rule: matched, missed problems, false alarms, unclear. Missed problems matter most.
   - fields that were read wrongly
   - compare with the previous run if the person changed something since
   Point them to the Test invoices tab on the workspace page for the details.
