---
name: check-invoices
description: Check invoices in the selected project against its confirmed rules, mark where each value was found, and save the results for review. Use when someone asks to check, read or analyse invoices, or says new invoices were added.
---

# Check invoices

Work from the repository root. Run the commands as written (use `python3` if `python` is not found). Every tool prints JSON or a plain error to fix.

To look at an image: in Claude Code, Read the PNG file. In Codex, open it with the image viewing tool.

## 1. Load the project

Run `python tools/project.py show`. Keep in mind:
- `invoice_types`: description and `what_to_look_for` for each type
- `fields_by_type`: the fields to read for each type, with hints
- `confirmed_rules` and `visual_rules_to_judge`: the only rules you apply
- `learnings`: tips from earlier corrections; follow them

If no project is selected, ask which project to use (see the switch-project skill).

## 2. Choose the invoices

If the person named invoices, check those. Otherwise run `python tools/pages.py pending` and check every pending invoice. If nothing is pending, say so and stop.

## 3. For each invoice, one at a time

a. Run `python tools/pages.py render <invoice>` and look at every page image.

b. Choose the invoice type whose description fits best. Write one sentence on why. If none fits well, pick the closest and add a question.

c. Read every field of that type. Copy values as written on the document, keeping the original number format and currency. Set `status` to `found`, `uncertain` (hard to read or partly guessed) or `not_found`. Never invent a value.

d. For each rule in `visual_rules_to_judge` that belongs to this type, decide `pass`, `fail` or `unclear`, with one sentence quoting what you saw. Use `unclear` when you cannot tell. Never pass a rule you could not see evidence for.

e. Mark the evidence, only where a rule needs it: each found field that a confirmed rule of this type checks (the rule's `field`), and each visual verdict that points at something on the page (a stamp, a signature, a payment note). Other fields are read but not marked. On each page that has items:
   1. `python tools/grid.py grid <page image>` and look at the grid image. Note a cell range (like `J8:K9`) that covers each item completely.
   2. Write those ranges to `spec.json` in the invoice's work folder, e.g. `{"total_amount": "J8:K8", "R_VOL_101": "E6:I8"}`, run `python tools/grid.py sheet <page image> <spec.json>` and look at the sheet. For each item, choose the sub-range (`a1` to `d4`) that tightly covers it.
   3. Write `{"total_amount": {"cells": "J8:K8", "sub": "a2:d3"}, ...}` to the spec, run `python tools/grid.py finalize <page image> <spec.json>` and look at the check image. Each value must sit fully inside its red frame.
   4. If a frame cuts off part of a value, widen the range or sub-range and finalize again, once. If it is still not right, leave that item without a box. A wrong mark is worse than no mark.
   5. Use the boxes printed by `finalize`, with the page number.

f. Write the draft as described in [result-format.md](result-format.md) to `draft.json` in the invoice's work folder, then run `python tools/results.py save <invoice> <draft.json>`. If it reports problems, fix the draft and save again.

## 4. Flag unclear descriptions

If a field or rule description was ambiguous for an invoice (for example the bundle has two documents that each carry a number or date and the description doesn't say which one), choose the most likely reading, explain it in the field's `note`, and propose a clearer description with `python tools/proposals.py propose` as described in the suggest-improvements skill. Do not change descriptions yourself.

## 5. Report back

Reply in plain words, per invoice: the status, any failed rules, and your questions. Point the person to the workspace page to review the marks and confirm. Do not paste JSON.

## Limits

- Apply only the confirmed rules from step 1. Do not add your own rules.
- Do not edit rules, descriptions, tools or the page. If a rule or description looks wrong, say so in your reply instead.
- To check test invoices, the run-evaluation skill uses these same steps with `--set evaluation` on `pages.py` and `results.py`.
