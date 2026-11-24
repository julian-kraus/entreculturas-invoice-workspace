---
name: check-invoices
description: Check invoices in the selected project against its confirmed rules, mark where each value was found, and save the results for review. Use when someone asks to check, read or analyse invoices, or says new invoices were added.
model: sonnet
effort: medium
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

If there are no enabled invoice types, explain that a type must be enabled or added under Project setup → Invoice types and stop before reading or saving invoices.

If no project is selected, ask which project to use (see the switch-project skill).

Before checking any invoices, every proposed rule and proposed change in Project setup → Inbox must be confirmed or rejected. If the Inbox contains items, explain that the person must handle them first and stop. The inspection and save tools enforce this again under the project lock in case a proposal arrives while you are working. Existing invoice reviews remain available.

## 2. Choose the invoices

An initial-check request, including a copied batch request, applies only to invoices that are still unchecked. Run `./.tools/uv run tools/pages.py pending` and intersect its IDs with any IDs named in the request. Report named IDs that are unavailable or already checked, skip them and continue with the rest. If nothing is pending, say so and stop. A recheck must be explicitly requested for one invoice. If it includes a base revision, use that revision for the recheck and refuse to replace work if it no longer matches.

## 3. For each invoice, one at a time

a. Run `./.tools/uv run tools/results.py inspect <invoice>` before reading. For an initial check, proceed only if `revision` is null. For a recheck, require a revision, no candidate and no saved staff draft; if the request supplied a revision, it must match. Record the returned `source_digest`, `config_digest` and, for rechecks, the base `revision`. If a candidate or draft exists, ask the person to review that saved work on the page. Reload `./.tools/uv run tools/project.py show` for this invoice, then inspect again and continue only if both digests and the revision match the first inspection. Use that reloaded configuration while reading. Run `./.tools/uv run tools/pages.py render <invoice>` and look at every page image. Work in a uniquely named scratch directory under the invoice work folder for this attempt and copy the rendered page images there before generating grids, specs and drafts, so another check cannot overwrite them. Compare any visible project identifiers and funder with the selected project. If the document clearly identifies a different project, ask which one to use before saving. For a question about a single existing finding, inspect the named page and explain the evidence rather than saving a check.

b. Choose the invoice type whose description fits best. Write one sentence on why. If none fits well, pick the closest and add a question.

c. Read every field of that type. Copy values as written on the document, keeping the original number format and currency. Set `status` to `found`, `uncertain` (hard to read or partly guessed) or `not_found`. Never invent a value.

d. For each rule in `visual_rules_to_judge` that belongs to this type, decide `pass`, `fail` or `unclear`, with one sentence quoting what you saw. Use `unclear` when you cannot tell. Never pass a rule you could not see evidence for.

e. Mark evidence for every extracted field whose location you can confirm, and each visual verdict that points at something on the page (a stamp, a signature, a payment note). On each page that has items:
   1. `./.tools/uv run tools/grid.py grid <page image>` and look at the grid image. Note a cell range (like `J8:K9`) that covers each item completely.
   2. Write those ranges to `spec.json` in this attempt's scratch directory, e.g. `{"total_amount": "J8:K8", "R_VOL_101": "E6:I8"}`, run `./.tools/uv run tools/grid.py sheet <page image> <spec.json>` and look at the sheet. For each item, choose the sub-range (`a1` to `d4`) that tightly covers it.
   3. Write `{"total_amount": {"cells": "J8:K8", "sub": "a2:d3"}, ...}` to the spec, run `./.tools/uv run tools/grid.py finalize <page image> <spec.json>` and look at the check image. Each value must sit fully inside its red frame.
   4. If a frame cuts off part of a value, widen the range or sub-range and finalize again, once. If it is still not right, leave that item without a box. A wrong mark is worse than no mark.
   5. Use the boxes printed by `finalize`, with the page number.

f. Write the draft as described in [result-format.md](result-format.md) to `draft.json` in this attempt's scratch directory. For an initial check run `./.tools/uv run tools/results.py save <invoice> <draft.json> --intent initial --source-digest <source_digest> --config-digest <config_digest>`. For a recheck use `--intent recheck --revision <revision>` with the same digest arguments. The save checks eligibility and revisions again under the project lock. If the source, configuration or saved result changed, or another candidate appeared, preserve the saved work and report the conflict rather than retrying with a fresh revision. Fix draft validation errors and retry with the original inspection values. Continue other invoices after a conflict or failure.

## 4. Flag unclear descriptions

If a field or rule description was ambiguous for an invoice (for example the bundle has two documents that each carry a number or date and the description doesn't say which one), choose the most likely reading and explain it in the field's `note`. Ask the person to confirm the review, then use the improvement-request action to propose clearer descriptions based on confirmed reviews. Do not change descriptions yourself.

## 5. Report back

Reply in plain words, per invoice: the status, any failed rules, and your questions. List skipped, unavailable and failed invoices so the person can retry. Point the person to the workspace page to review the marks and confirm. Say when no confirmed rules applied. For a staged recheck, explain that the confirmed result remains available until the reviewer accepts the candidate.

## Limits

- Apply only the confirmed rules from step 1. Do not add your own rules.
- Do not edit rules, descriptions, tools or the page. If a rule or description looks wrong, say so in your reply instead.
