---
name: propose-rules
description: Read the funder guidelines of the selected project and propose checking rules, each with the document and page it comes from. Use when someone adds guidelines, starts a new project, or asks which rules apply.
model: opus
effort: high
---

# Propose rules from guidelines

Resolve the project once at the start. Pin that slug with `INVOICE_PROJECT` on all commands for this task as described in AGENTS.md.

Work from the repository root.

1. Run `./.tools/uv run tools/project.py show` to see the invoice types, their fields and the rules already confirmed.
2. Run `./.tools/uv run tools/guidelines.py list`. If there are no files, ask the person to add the guidelines on the workspace page under Project setup → Project details.
3. Read each guideline: `./.tools/uv run tools/guidelines.py text "<file>"` (add `--pages 10-20` for long documents). If it says the PDF is a scan, tell the person you cannot read scanned guidelines yet.
4. Find requirements that can be checked on an invoice or its supporting documents: required stamps, signatures, information that must appear, dates, limits, payment proof.
5. For each one, draft a rule in the format shown in `./.tools/uv run tools/rules.py` (run it without arguments to see it):
   - Prefer `visual` for anything you judge by looking at the document, and `required`, `range`, `enum`, `regex` or `date_in_period` when a field value decides it.
   - Write `description` as one plain sentence a reviewer understands, in the language of the guidelines.
   - Fill `hint` with where to look: which document in the bundle (invoice, receipt, funds request, bank statement) and where on it.
   - Fill `reason` with what in the guideline asks for this, in one sentence.
   - `source` must name the file, the page and, if there is one, the section.
   - Check existing confirmed, proposed and rejected rules and the rest of this batch. The tool reports matching type and name as skipped, including rejected rules. Tell the person which matches need review before reopening; do not silently drop possible revisions or change rejected rules.
6. Save the list to `projects/<project>/work/proposed-rules.json` and run `./.tools/uv run tools/rules.py propose <that file>`. Fix any problems it reports.
7. Reply with a short list of proposed rules and skipped matches in plain words, and ask the person to review them under Project setup → Inbox. They can edit and confirm one rule or use Confirm all for the displayed items. Proposed rules are not applied until someone confirms them.

Do not change rules that are already confirmed.
