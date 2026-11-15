---
name: propose-rules
description: Read the funder guidelines of the selected project and propose checking rules, each with the document and page it comes from. Use when someone adds guidelines, starts a new project, or asks which rules apply.
---

# Propose rules from guidelines

Work from the repository root (use `python3` if `python` is not found).

1. Run `python tools/project.py show` to see the invoice types, their fields and the rules already confirmed.
2. Run `python tools/guidelines.py list`. If there are no files, ask the person to add the guidelines on the workspace page under Rules.
3. Read each guideline: `python tools/guidelines.py text "<file>"` (add `--pages 10-20` for long documents). If it says the PDF is a scan, tell the person you cannot read scanned guidelines yet.
4. Find requirements that can be checked on an invoice or its supporting documents: required stamps, signatures, information that must appear, dates, limits, payment proof.
5. For each one, draft a rule in the format shown in `python tools/rules.py` (run it without arguments to see it):
   - Prefer `visual` for anything you judge by looking at the document, and `required`, `range`, `enum`, `regex` or `date_in_period` when a field value decides it.
   - Write `description` as one plain sentence a reviewer understands, in the language of the guidelines.
   - Fill `hint` with where to look: which document in the bundle (invoice, receipt, funds request, bank statement) and where on it.
   - Fill `reason` with what in the guideline asks for this, in one sentence.
   - `source` must name the file, the page and, if there is one, the section.
   - Skip anything already covered by a confirmed rule.
6. Save the list to `projects/<project>/work/proposed-rules.json` and run `python tools/rules.py propose <that file>`. Fix any problems it reports.
7. Reply with a short list of the proposed rules in plain words, and ask the person to approve or reject each one on the workspace page: they appear at the top of Rules and types. Proposed rules are not applied until someone confirms them.

Do not change rules that are already confirmed.
