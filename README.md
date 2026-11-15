# Invoice workspace

Check grant justification invoices with your own AI assistant (Claude Code or Codex), consistently and with evidence.

You work in two places:

- **The chat** with the assistant, for the jobs that need reading: checking invoices, proposing rules from funder guidelines, running test invoices.
- **The workspace page** in your browser, for everything else: adding invoices, reviewing results, correcting values, confirming rules, editing descriptions, test invoices and history.

Everything stays in this folder on your computer. The assistant reads invoice pages through your own Claude or ChatGPT account.

## Setup

Do this once per computer. It takes about 15 minutes.

1. **Install Python** 3.10 or newer from [python.org](https://www.python.org/downloads/). On Windows, tick "Add Python to PATH" during installation.
2. **Install your assistant:** the Claude desktop app (Claude Code) or the ChatGPT desktop app (Codex). Sign in with your own account.
3. **Get this folder:** download it as a ZIP and unzip it somewhere you keep work files, or paste the repository link into the assistant and ask it to download it.
4. **Open the folder in the assistant.**
   - Claude Code: open the folder as a project.
   - Codex: open the folder, and choose to trust it when asked, so it uses the assistant settings.
5. **Ask: "Set this up".** The assistant installs the Python packages (`pip install -r requirements.txt`) and checks that everything works.
6. **Ask: "Open the workspace".** The page opens at http://localhost:8790. You can also double-click `start-workspace.command` (Mac) or `start-workspace.bat` (Windows).
7. **Choose or create a project** at the top of the page. To work like a colleague, choose **New project** and pick the setup file they shared.
8. **Check the assistant settings** (last tab). Sonnet with medium effort for checking invoices keeps usage moderate. Use Opus only where careful reading matters more than usage.

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

- `tools/`: plain Python tools the skills call. `python -m pytest tests` runs the tests.
- `skills/`: the source of the skills. `python tools/sync_skills.py` copies them to `.claude/skills/` (Claude Code) and `.agents/skills/` (Codex). Copies are used because Git on Windows often skips symbolic links.
- `AGENTS.md`: instructions for the assistant. `CLAUDE.md` imports it for Claude Code.
- `app/`: the workspace page. It listens only on this computer and never calls an AI.
- `tools/import_csv_config.py`: creates a project from the CSV configuration of the earlier invoice agent prototype.
- Evidence marks: the page image gets a 12 × 16 grid (`tools/grid.py`). The assistant names the cells, refines them on an enlarged 4 × 4 grid and confirms each box on a close-up. Only values a rule checks are marked, and boxes it cannot confirm are left out.
