# Invoice workspace: instructions for the assistant

This folder helps a non-technical team check invoices for grant justification. People work in two places:

- **The chat with you**, for the jobs that need reading and judgment: checking invoices, proposing rules from guidelines, running the test invoices, switching projects.
- **The workspace page** (`app/`, at http://localhost:8790), for everything else: adding invoices and guidelines, reviewing and correcting results, confirming rules, editing descriptions, test invoices and history.

## How to work

- Use the skills in this repository: check-invoices, propose-rules, suggest-improvements, run-evaluation, switch-project, open-workspace, invoice-help. Follow their steps exactly.
- Run tools from the repository root with `python tools/<tool>.py` (use `python3` if `python` is not found). They print JSON or a plain error explaining what to fix.
- Speak plainly. The people you help are not technical. Don't show JSON, file paths or commands unless they ask.
- Keep invoice details in the chat to what the person needs. The invoices contain personal data.

## What you may change

- **Yes, through the tools:** results (`tools/results.py`), proposed rules (`tools/rules.py`), proposed changes to descriptions (`tools/proposals.py`), the selected project (`tools/project.py`), test invoice runs (`tools/evaluate.py`).
- **Only when the person asks for it explicitly:** invoice types, fields, rules, learnings and project details. Prefer pointing them to the page, where changes are logged with before and after. If you edit these files directly, describe the change and log it with `common.log` in the same way.
- **Not without a clear request and a confirmation:** anything in `tools/`, `app/`, `skills/` or this file. If the person asks for such a change, explain what you would change and why, make the change, run `python -m pytest tests` and `python tools/sync_skills.py`, and suggest running the test invoices afterwards.
- **Never:** delete invoices, results, test invoices or history; send data anywhere outside this computer; push to a remote repository.

## Where things are

- `projects/<project>/`: `project.json`, `invoice_types.json`, `fields.json`, `rules.json`, `learnings.json`, `invoices/`, `results/`, `guidelines/`, `evaluation/`, `history.jsonl`
- `workspace.json`: which project is selected
- `skills/`: the skills; `tools/sync_skills.py` copies them to `.claude/skills/` and `.agents/skills/`

## Setup

When someone asks to set things up, or a tool fails with a missing module: run `python -m pip install -r requirements.txt`, then `python tools/project.py list`. If no project is selected, help them choose or create one (switch-project skill), then offer to open the workspace page.
