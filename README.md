# Invoice workspace

Check grant justification invoices with your own AI assistant (Claude Code or Codex), consistently and with evidence.

To set it up, give your assistant the link to this repository (see Setup). Assistant: follow the Setup section in `AGENTS.md`.

You work in two places:

- **The chat** with the assistant, for the jobs that need reading: checking invoices, proposing rules from funder guidelines, running test invoices.
- **The workspace page** in your browser, for everything else: adding invoices, reviewing results, correcting values, confirming rules, editing descriptions, test invoices and history.

Everything stays in this folder on your computer. The assistant reads invoice pages through your own Claude or ChatGPT account.

## Setup

You need only Claude Code (the Claude desktop app) or Codex (the ChatGPT desktop app), signed in with your own account. The assistant installs everything else into the workspace folder: no administrator rights, nothing installed on the rest of your computer.

1. Create an empty folder, for example `Invoice workspace` in your Documents.
2. Open it in your assistant: in Claude Code as a new project, in Codex as a new project (choose to trust the folder when asked).
3. Paste this message:

   > Set up the invoice workspace from https://github.com/julian-kraus/entreculturas-invoice-workspace in this folder.

   The assistant downloads the files, installs its tools into the folder and checks that everything works. Approve its steps when it asks. This takes a few minutes.
4. Start a new chat in the same folder, so the assistant picks up the workspace skills.
5. Ask: **"Open the workspace"**. The page opens at http://localhost:8790. Later you can also double-click `start-workspace.command` (Mac) or `start-workspace.bat` (Windows) in the folder.
6. Choose a project at the top of the page, or **New project**. To work like a colleague, choose **New project** and pick the setup file they shared.
7. Look at **Assistant settings** (last tab). Sonnet with medium effort for checking invoices keeps usage moderate.

## Removing it

Delete the folder. The Python, packages and tools the assistant installed are all inside it (in `.tools` and `.venv`), so nothing stays behind. Deleting the folder also deletes your invoices, results and test invoices, so keep a copy of what you need first, for example the Excel report and **Download setup to share**.

## A normal week

| You want to | Where | How |
|---|---|---|
| Add invoices | Page, Invoices | Drop PDFs or photos on "Add invoices" |
| Check them | Chat | "Check the new invoices" |
| Review a result | Page, Invoices | Click an invoice, look at the numbered marks, correct values, then "Confirm review" |
| Keep a tip for next time | Page, review box | Write it in "Tip for next time" |
| Create the report | Page, Invoices | "Create Excel report" |
| Switch project | Page (top) or chat | Choose it at the top, or "Switch to project …" |

## Setting up a project

1. Start a project: **New project** at the top of the page. You can copy the invoice types and rules of an existing project.
2. Add the funder's guidelines under **Rules and types → Rules → Add guidelines**.
3. In the chat: **"Propose rules from the guidelines"**. Each proposed rule names the page it comes from.
4. Confirm or reject each rule on the page. Only confirmed rules are applied.
5. Check the descriptions under **Invoice types** and **Fields to extract**, and edit them in your own words.

## Improving over time

- When you correct a value, you can also choose **Change how this is read** to make the description clearer straight away.
- Or ask in the chat: **"Suggest improvements"**. The assistant looks at your corrections and proposes clearer descriptions.
- New rules and proposed changes wait at the top of **Rules and types** under **Waiting for your approval**. Nothing changes until you approve.
- After approving, run the test invoices to see whether results improved.

## Sharing with a colleague

- **Download setup to share** (top of Rules and types) saves the invoice types, fields, rules and tips as one file, without invoices.
- Your colleague chooses **New project** and picks that file.
- **Download as Excel** gives a readable copy of the same setup.

## Knowing how well it works

Test invoices are invoices your team already checked, with the right answers saved.

1. Review an invoice and confirm it.
2. Choose **Add to test invoices**. Tick **keep aside** for a few of them: those are never used to make changes, so the score stays honest.
3. After changing rules or descriptions, ask in the chat: **"Run the test invoices"**.
4. See the result under **Test invoices**: per rule, what was right, what was missed and what was a false alarm. Missed problems matter most.

## What changes are safe

- Rules, descriptions, tips and project details: edit them on the page. Every change is saved in the History with before and after.
- How the tools or the page work: ask the assistant, who explains the change first. Run the test invoices afterwards.

## For maintainers

- `tools/`: plain Python tools the skills call. `./.tools/uv run pytest tests` runs the tests.
- Setup uses [uv](https://docs.astral.sh/uv/), installed into `.tools/` together with its own Python (see Setup in `AGENTS.md`). Dependencies are in `pyproject.toml` and `uv.lock`.
- `skills/`: the source of the skills. `./.tools/uv run tools/sync_skills.py` copies them to `.claude/skills/` (Claude Code) and `.agents/skills/` (Codex). Copies are used because Git on Windows often skips symbolic links.
- `AGENTS.md`: instructions for the assistant. `CLAUDE.md` imports it for Claude Code.
- `app/`: the workspace page. It listens only on this computer and never calls an AI.
- `tools/import_csv_config.py`: creates a project from the CSV configuration of the earlier invoice agent prototype.
- Evidence marks: the page image gets a 12 × 16 grid (`tools/grid.py`). The assistant names the cells, refines them on an enlarged 4 × 4 grid and confirms each box on a close-up. Only values a rule checks are marked, and boxes it cannot confirm are left out.
