---
name: suggest-improvements
description: Look at what reviewers corrected and propose clearer descriptions for fields, invoice types or rules, for people to approve on the workspace page. Use when someone asks to suggest improvements, learn from corrections, or why the same mistake keeps happening.
model: opus
effort: high
---

# Suggest improvements from corrections

Resolve the project once at the start. Pin that slug with `INVOICE_PROJECT` on all commands for this task as described in AGENTS.md.

Work from the repository root.

1. Run `./.tools/uv run tools/proposals.py corrections`. It lists every value or rule outcome a reviewer changed, the tips saved with reviews, the differences from the last test invoice run, and proposals still waiting.
2. Run `./.tools/uv run tools/project.py show` to see the current descriptions, and read `projects/<project>/fields.json`, `invoice_types.json` and `rules.json` for the ids and current text of what you want to change.
3. Look for patterns, not single slips. Good reasons to propose a change:
   - the same field was corrected on two or more invoices, or on one invoice where the cause is clearly a vague description (for example two documents in the bundle each have a number)
   - a tip says the same thing a description should say
   - a test invoice keeps failing on the same rule or field
4. For each pattern, write one change in the format shown by `./.tools/uv run tools/proposals.py` (run it without arguments): the item's `kind` and `target` id, the new text in `changes`, a one-sentence `reason` a non-technical reviewer understands, and the invoices it is based on in `evidence`.
   - Rewrite the whole description so it stays readable, keeping what still holds and adding what the corrections showed. Name the document and where on it to look.
   - Do not propose a change that is already waiting.
5. Save the list to `projects/<project>/work/proposed-changes.json` and run `./.tools/uv run tools/proposals.py propose <that file>`. Fix any problems it reports.
6. Reply with a short plain list of what you proposed and why, and ask the person to approve or reject each one under Project setup on the workspace page. Suggest running the test invoices after approving.

Do not change fields, types or rules directly. If you see no clear pattern, say so and propose nothing.
