---
name: check-invoices
description: Check invoices in the selected project against its confirmed rules, mark where each value was found, and save the results for review. Use when someone asks to check, read or analyse invoices, or says new invoices were added.
---

# Check invoices

Work from the repository root. Run the commands as written. Every tool prints JSON or a plain error to fix.

To look at an image: in Claude Code, Read the PNG file. In Codex, open it with the image viewing tool.

## 1. Load the project

Resolve the requested project using `tools/project.py list` and pin its slug with `INVOICE_PROJECT` on every command as described in AGENTS.md. Keep the same project through rendering, checking and saving. Then run `./.tools/uv run tools/project.py show`. Keep in mind:
- `invoice_types`: description and `what_to_look_for` for each type
- `fields_by_type`: the fields to read for each type, with hints
- `confirmed_rules` and `visual_rules_to_judge`: the only rules you apply
- `learnings`: tips from earlier corrections; follow them

If no project is selected, ask which project to use (see the switch-project skill).

## 2. Choose the invoices

If the person named invoices, check those. Otherwise run `./.tools/uv run tools/pages.py pending` and check every pending invoice. If nothing is pending, say so and stop.

## 3. For each invoice, one at a time

a. Run `./.tools/uv run tools/pages.py render <invoice>` and look at every page image. Compare any visible project identifiers and funder with the selected project. If the document clearly identifies a different project, ask which one to use before saving. For a question about a single existing finding, inspect the named page and explain the evidence. Save a new check when the person asks for a recheck.

b. Choose the invoice type whose description fits best. Write one sentence on why. If none fits well, pick the closest and add a question.

c. Read every field of that type. Copy values as written on the document, keeping the original number format and currency. Set `status` to `found`, `uncertain` (hard to read or partly guessed) or `not_found`. Never invent a value.

d. For each rule in `visual_rules_to_judge` that belongs to this type, decide `pass`, `fail` or `unclear`, with one sentence quoting what you saw. Use `unclear` when you cannot tell. Never pass a rule you could not see evidence for.

e. Mark evidence for every extracted field whose location you can confirm, and each visual verdict that points at something on the page (a stamp, a signature, a payment note). On each page that has items:
   1. `./.tools/uv run tools/grid.py grid <page image>` and look at the grid image. Note a cell range (like `J8:K9`) that covers each item completely.
   2. Write those ranges to `spec.json` in the invoice's work folder, e.g. `{"total_amount": "J8:K8", "R_VOL_101": "E6:I8"}`, run `./.tools/uv run tools/grid.py sheet <page image> <spec.json>` and look at the sheet. For each item, choose the sub-range (`a1` to `d4`) that tightly covers it.
   3. Write `{"total_amount": {"cells": "J8:K8", "sub": "a2:d3"}, ...}` to the spec, run `./.tools/uv run tools/grid.py finalize <page image> <spec.json>` and look at the check image. Each value must sit fully inside its red frame.
   4. If a frame cuts off part of a value, widen the range or sub-range and finalize again, once. If it is still not right, leave that item without a box. A wrong mark is worse than no mark.
   5. Use the boxes printed by `finalize`, with the page number.

f. Write the draft as described in [result-format.md](result-format.md) to `draft.json` in the invoice's work folder, then run `./.tools/uv run tools/results.py save <invoice> <draft.json>`. If it reports problems, fix the draft and save again.

## 4. Flag unclear descriptions

If a field or rule description was ambiguous for an invoice (for example the bundle has two documents that each carry a number or date and the description doesn't say which one), choose the most likely reading, explain it in the field's `note`, and propose a clearer description with `./.tools/uv run tools/proposals.py propose` as described in the suggest-improvements skill. Do not change descriptions yourself.

## 5. Report back

Reply in plain words, per invoice: the status, any failed rules, and your questions. Point the person to the workspace page to review the marks and confirm. Say when no confirmed rules applied. For a staged recheck, explain that the confirmed result remains available until the reviewer accepts the candidate.

## Limits

- Apply only the confirmed rules from step 1. Do not add your own rules.
- Do not edit rules, descriptions, tools or the page. If a rule or description looks wrong, say so in your reply instead.
