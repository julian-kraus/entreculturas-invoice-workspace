# Invoice workspace: instructions for the assistant

This folder helps a non-technical team check invoices for grant justification. People work in two places:

- **The chat with you**, for the jobs that need reading and judgment: checking invoices, proposing rules from guidelines, running the test invoices, switching projects.
- **The workspace page** (`app/`, at http://localhost:8790), for everything else: adding invoices and guidelines, reviewing and correcting results, confirming rules, editing descriptions, test invoices and history.

## How to work

- Use the skills in this repository: check-invoices, propose-rules, suggest-improvements, run-evaluation, switch-project, open-workspace, invoice-help. Follow their steps exactly.
- Run tools from the repository root with `./.tools/uv run tools/<tool>.py`. They print JSON or a plain error explaining what to fix.
- Speak plainly. The people you help are not technical. Don't show JSON, file paths or commands unless they ask.
- Keep invoice details in the chat to what the person needs. The invoices contain personal data.

## What you may change

- **Yes, through the tools:** results (`tools/results.py`), proposed rules (`tools/rules.py`), proposed changes to descriptions (`tools/proposals.py`), the selected project (`tools/project.py`), test invoice runs (`tools/evaluate.py`).
- **Only when the person asks for it explicitly:** invoice types, fields, rules, learnings and project details. Prefer pointing them to the page, where changes are logged with before and after. If you edit these files directly, describe the change and log it with `common.log` in the same way.
- **Not without a clear request and a confirmation:** anything in `tools/`, `app/`, `skills/` or this file. If the person asks for such a change, explain what you would change and why, make the change, run `./.tools/uv run pytest tests` and `./.tools/uv run tools/sync_skills.py`, and suggest running the test invoices afterwards.
- **Never:** delete invoices, results, test invoices or history; send data anywhere outside this computer; push to a remote repository.

## Where things are

- `projects/<project>/`: `project.json`, `invoice_types.json`, `fields.json`, `rules.json`, `learnings.json`, `invoices/`, `results/`, `guidelines/`, `evaluation/`, `history.jsonl`
- `workspace.json`: which project is selected
- `skills/`: the skills; `tools/sync_skills.py` copies them to `.claude/skills/` and `.agents/skills/`

## Setup

Everything the workspace needs is installed inside this folder (`.tools/` and `.venv/`), so deleting the folder removes it completely. Nothing is installed system-wide and nothing needs administrator rights.

When someone asks to set things up, opens this folder for the first time, or a tool fails because `.tools/uv` or a module is missing, do these steps from the repository root. Explain in one sentence that you are installing the tools into this folder, then:

1. **Install uv into `.tools/`** (skip if `./.tools/uv --version` works). uv is a small program that brings its own Python.
   - Mac or Linux: `curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$PWD/.tools" UV_NO_MODIFY_PATH=1 sh`
   - Windows (PowerShell): `$env:UV_INSTALL_DIR="$PWD\.tools"; $env:UV_NO_MODIFY_PATH="1"; irm https://astral.sh/uv/install.ps1 | iex`
   - If the program ended up in `.tools/bin/`, move it (and `uvx`) up into `.tools/`.
2. **Install Python and the packages into this folder:**
   - Mac or Linux: `UV_PYTHON_INSTALL_DIR=.tools/python ./.tools/uv sync --python 3.12 --python-preference only-managed`
   - Windows (PowerShell): `$env:UV_PYTHON_INSTALL_DIR=".tools\python"; ./.tools/uv sync --python 3.12 --python-preference only-managed`
3. **Check:** `./.tools/uv run pytest -q tests` and `./.tools/uv run tools/project.py list`.
4. If no project is selected, help them choose or create one (switch-project skill), then offer to open the workspace page.

If the person started from the repository link in an empty folder, first get the files: `git clone <link> .` if git is available, otherwise download `<link>/archive/refs/heads/main.zip` and unpack its contents into this folder. Then do the steps above, and tell them to start a new chat in this folder so the skills load.

To remove the workspace, the person deletes this folder. Remind them that this also deletes their invoices, results and test invoices, so they should keep a copy of anything they need (for example the Excel report and "Download setup to share").
