# Invoice workspace

Check grant justification invoices with your own AI assistant (Claude Code or Codex), consistently and with evidence.

To set it up, give your assistant the link to this repository (see Setup). Assistant: follow the Setup section in `AGENTS.md`.

You work in two places:

- **The chat** with the assistant, for the jobs that need reading: checking invoices, proposing rules from funder guidelines, running test invoices.
- **The workspace page** in your browser, for everything else: adding invoices, reviewing results, correcting values, confirming rules, editing descriptions, test invoices and history.

The website stores project files on your computer. When you ask for a check, your assistant processes invoice pages through your Claude or ChatGPT account.

For the team's agreed scope and pilot priorities, see [Product direction](#product-direction), the [original setup audit](#current-setup-audit), the [design and feature audit](#design-and-feature-audit), the [file structure audit](#file-structure-audit) and the [implementation plan](PILOT-PLAN.md).

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
7. The installed defaults are ready to use. Assistant settings are available from the workspace header.

## Removing it

Follow [Backup, update and recovery](#backup-update-and-recovery) before removing the folder. The workspace includes the project data as well as the locally installed Python and packages.

## A normal week

| You want to | Where | How |
|---|---|---|
| Add and check invoices | Invoices, then chat | Drop PDFs or photos on **Add invoices**. Open one and choose **Copy check request**, or expand the pending batch to see its filenames. Paste the request into Claude Code or Codex in this workspace. |
| Verify a rule | Invoice review | Select a finding's numbered mark to see its evidence. **Copy question** includes the project, invoice, rule and marked page. |
| Correct and confirm | Invoice review | Open **Extracted values → Edit value** or **Rule findings → Change decision**. Review the proposed corrections and choose **Confirm review**. A project tip or edit to a field's instructions applies to future checks. |
| Recheck a confirmed invoice | Invoice review, then chat | Copy the recheck request. Compare the candidate with the confirmed decision when it returns. The existing confirmed row stays available until you accept the recheck. |
| Record or share the decision | Invoices or invoice review | Download the project workbook from the list. Within one invoice, download the marked PDF or copy its confirmed spreadsheet row. |
| Share pilot feedback | History | Select entries, expand their details, then download the selected entries as a text file. |

## Setting up a project

1. Choose **New project**. Start with five standard fields, copy an existing project's types and rules, or import a shared setup. The bundled [AEXCID example](templates/example-aexcid.json) is an importable starting point. Its rules start as proposed.
2. Under **Project setup**, add the funder's guidelines and copy the request to propose rules into chat. Proposed rules include the document and page that support them.
3. Review each proposal and approve the rules that apply. Use the type and status filters to inspect the confirmed rules. An invoice with no applicable project rules is labeled explicitly.
4. Under **Invoice types** and **Fields to extract**, add definitions or edit descriptions in the team's own words.

## Improving and sharing the setup

- Choose **Edit project field instructions** when the assistant should read that field differently on future invoices. **Suggest improvements** in chat uses previous corrections to propose changes for review.
- Under **Project setup**, **Download setup to share** exports project details, invoice types, fields, rules and tips. Your colleague can import that file into a new project. Review the tips and source references before sharing. **Download as Excel** provides a readable version of the setup.
- Under **Evaluation**, select a confirmed invoice to save the reviewed answers as a test case. Keep some cases aside for an independent check. After changing the setup, ask the assistant to **run the test invoices** and inspect missed problems and false alarms under **Evaluation**.

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

## Product direction

Entreculturas staff must verify invoices themselves. The goal is to reduce the time from opening an invoice to recording a defensible decision in their existing spreadsheet. A reviewer should be able to see which rule applied, find its evidence, correct a mistake and share the result with a colleague or partner.

| Area | Direction from the discussion |
|---|---|
| First version | Work locally, one project at a time. Select a project, upload its guidelines, review the proposed rules, then check invoices against the confirmed rules for their document type. Offer standard fields that staff can adapt. Pause when the document appears to belong to another project. |
| Setup and ownership | Staff should be able to install and use the tool on an ordinary work laptop, ask for help in plain language and operate with approval prompts and access to the designated folder. Keep invoices and decisions separate from replaceable application files. Staff need to maintain rules, fields and tips after handover. |
| Chat and website | Use chat for reading documents, requesting checks and asking for corrections. Use the website for reviewing evidence and recording decisions. A request about “this invoice” should identify the project and invoice the reviewer is viewing. Whether staff prefer adding files in chat or on the page is a pilot question. |
| Review design | Proposed changes include a dedicated invoice view, a scrollable document, click-to-select evidence, separate views of values and rule findings, explicit overrides, and a prominent marked-PDF download. Keep questions and explanations visible. Give history, model settings and evaluation less prominence in daily work. |
| Sharing | Staff need to share two things separately: reviewed results for reporting, and reusable project knowledge for colleagues. Match exports to the team's Excel layout. A copyable row or CSV could help staff who register one invoice at a time. A marked PDF could explain a finding to a partner. |
| Later or undecided | Shared team state, Google Drive synchronization and write permissions, a repair function, guided changes to the software, model delegation and user-facing evaluation can follow the local pilot. Movable evidence boxes, a PDF findings cover sheet, branding and licensing or liability wording remain open. |

## Current setup audit

**Baseline on 24 November 2026, revision `a2f45a1`.** This and the design audit below describe the prototype at that revision. See the [pilot implementation plan](PILOT-PLAN.md) for delivery status. All 12 original repository tests passed, and the skill synchronization check passed. A separate run exercised project creation, uploads, checks, review, recheck and Excel export in a temporary workspace with synthetic documents. Clean-machine installation, automatic skill selection in a new chat and staff review times still need field testing.

### What works today

- **Guideline approval and rule reuse.** Proposed rules carry a source document and page. Reviewers can filter by status and type, approve or reject proposals, and edit descriptions. The engine selects enabled, confirmed project rules for the document type, including rules marked for all types. Duplicate invoice numbers also produce a built-in warning. [Rule proposal skill](skills/propose-rules/SKILL.md) · [Rule engine](tools/checks.py)
- **Evidence and human review.** Numbered marks connect findings to page regions. Reviewers can see questions, correct values, override outcomes and save a tip. Saving a review preserves the assistant's original reading, recalculates the checks and regenerates a marked PDF. The Excel report includes a review flag and corrected values. [Review handling](app/server.py) · [PDF marks](tools/marks.py) · [Excel report](tools/report.py)
- **Local operation and handover.** The server listens on loopback. Both assistants use copies of one source skill set, checked for drift. Staff can transfer types, rules, fields and tips with a setup export; invoice files and results stay out of that export. Tips can include free text and a source invoice identifier, so staff should preview what they share. [Skill synchronization](tools/sync_skills.py) · [Setup export](tools/project.py)

### What to change before a staff pilot

| Priority | Finding and consequence | Change and acceptance check |
|---|---|---|
| 1. Bind each action to its project and invoice | In the isolated run, a review opened in project A was saved to project B after the selection changed. Both had an invoice with the same ID. The browser sends the invoice ID and the server looks up the current project at save time. Chat commands also read the selection afresh. [Server](app/server.py) · [Check skill](skills/check-invoices/SKILL.md) | Carry explicit project and invoice IDs from selection through rendering, review, recheck and export. Put both in the chat handoff. Test two open projects with the same invoice name and switch projects mid-check. The original invoice must receive the edit or the user must see a clear refusal. |
| 2. Make “passes” meaningful | A synthetic invoice with a valid type, a field and zero applicable rules received **passes** and appeared that way in Excel. The findings list explains that no rules apply, but a reviewer relying on the headline or report can miss this. [Rule engine](tools/checks.py) · [Report](tools/report.py) | Show **No applicable rules** as a distinct outcome on the page and in exports. Show how many rules ran. Test a new project, a type with only proposed rules, and a type whose confirmed rules all pass. |
| 3. Preserve the confirmed decision during a recheck | After a reviewer changed an amount from 100 to 125 and confirmed it, Excel showed 125 and “reviewed.” Rechecking the same invoice moved the review into `previous_review`; the next report showed 100 and “unreviewed.” [Result saving](tools/results.py) · [Excel report](tools/report.py) | Keep the last confirmed version available for reporting. Save the recheck as a new draft, show what changed and let the reviewer accept it. Verify that two consecutive rechecks preserve the confirmed values and their history. |
| 4. Give every uploaded invoice a distinct identity | Uploading `receipt.png` and `receipt.jpg` saved two files but produced one invoice-list entry. The listing uses the normalized filename stem as its key, which also identifies results and marks. [Upload handling](app/server.py) · [Invoice lookup](tools/common.py) | Assign an ID that is unique across formats, retain the original filename for display, and preserve links to existing reviews. Verify that each upload can be opened, checked and exported independently. |
| 5. Make first use work without a developer | A blank project starts with zero document types and fields. The page lets staff edit existing entries but offers no control to create the first type or field. On a fresh launch without a selected project, the empty-state code also replaces the invoice panel containing the upload and list controls. Help says to install Python manually while the setup guide provisions it locally. [Project creation](tools/project.py) · [Website](app/app.js) · [Help](app/index.html) | Provide a starter type and fields or a guided way to create them. Preserve the upload controls across the first project selection, align the setup instructions and test from a fresh folder on staff Windows and Mac machines using ordinary approvals. The reviewer should reach the first marked invoice without editing files or reloading to recover the page. |

## Design and feature audit

### Finding the next task

- **Workspace home.** The project picker, Help button and invoice status labels are worth keeping. Today five tabs have equal prominence, and the upload area stays beside an open invoice. The meeting proposed two main destinations, **Invoices** and **Project setup**, with History and Settings accessible from the header. Open an invoice in a dedicated reading view with **Back to invoices**. Returning should keep the reviewer's place in the list. [Current navigation](app/index.html) · [Layout](app/app.css)
- **Project setup.** The approval list already shows why a rule was proposed and which guideline it came from. Status and document-type filters already exist. The harder question for a new reviewer is “Which rules will apply to my next invoice?” Lead with the guideline and pending decisions, show confirmed rules for the chosen type, and open the detailed editor on demand. When a project has rules but no local guideline, explain whether they were copied, imported or entered manually wherever that information is available. [Setup interface](app/app.js) · [Project creation and import](tools/project.py)
- **From upload to check.** The drop zone accepts several files, but a generic message asks the user to change to chat. “New” currently means any invoice in the project without a saved result, which may cover more than the last upload. Show the filenames and count before a batch check. Give a selected invoice a separate **Check this invoice** action. A prompt containing the project and invoice is a small first step that works with either assistant. Direct submission and an embedded chat were ideas to investigate. Test uploading in chat as well as on the page before choosing a default. [Upload interface](app/index.html) · [Pending invoice selection](tools/pages.py) · [Check skill](skills/check-invoices/SKILL.md)

### Verifying and correcting one invoice

| Reviewer question | Current experience | Proposed change |
|---|---|---|
| Am I checking the right document? | The page names the file and assigned type. The skill records a reason for the classification, but the detail header omits it. A wrong type changes which rules run. | Put project, filename and type together. Show the classification reason and offer a way to question the type. If the document names a conflicting project, pause before evaluating it. |
| Where is the evidence for this finding? | Numbered marks, explanations and open questions are useful. Hovering a finding can switch pages, and page buttons show one page at a time. | Keep findings beside a continuously scrollable document. Clicking or keyboard-selecting a finding should take the reviewer to its mark and keep it selected. Say when no evidence was located. Keep the question and its explanation available during inspection. |
| Did the assistant misread a value or misjudge a rule? | Rule decisions appear above the extracted fields. Each correction input repeats the original value, and “Keep” can mean the same thing as “Mark as passed.” | Let reviewers switch between **Values** and **Rule findings** without losing their page. Show the original reading once with **Edit value**. For a verdict, show the current decision and an explicit **Change decision** action. Before confirmation, make the reviewer’s changes visible. |
| Will this edit affect future invoices? | A value correction, **Change how this is read**, a reusable tip and test-invoice enrollment all appear during review. They affect different records. | Make the scope plain. Correcting a total affects this invoice. Teaching the assistant where totals appear is a separate, optional project change. Keep **Save draft** and **Confirm review** together, and move test enrollment into evaluation tools. |
| Can I ask the assistant to look again? | Staff can ask in chat, but the selected finding and page are not included automatically. A recheck can also displace a confirmed correction in the report. | From a finding, prepare a request that names the project, invoice, rule and page, such as “Check the signature on page 3 again.” Show the proposed change alongside the confirmed result before accepting it. |

These proposals build on the existing reader, review controls and saved classification data. [Invoice interface](app/app.js) · [Check result format](skills/check-invoices/result-format.md) · [Review persistence](app/server.py)

### Exports, collaboration and ownership

| Audience | What exists | What the discussion calls for |
|---|---|---|
| Staff recording an invoice | **Create Excel report** sits below the invoice list. The workbook has fixed Invoices, Findings and Fields sheets. | Put the project report at list level and label it clearly as a whole-project export. If staff enter one invoice at a time, offer a copyable confirmed row in their register's column order. Obtain their actual template before choosing between a row, CSV or workbook. [Report layout](tools/report.py) |
| A partner receiving a flagged invoice | The per-invoice download is below the viewer. The exported PDF contains numbered boxes; the explanations remain in the workspace. | Put **Download marked PDF** in the invoice header. Give a partner the file on its own and ask whether they can identify the problem. A first-page list linking findings to marked pages was proposed. Movable boxes remain an open question for reviewers who encounter misplaced marks. [Marked PDF generation](tools/marks.py) |
| Colleagues sharing what they learned | A setup file transfers rules, types, fields and tips to a new project. It is a snapshot. Staff who subsequently edit separate copies can diverge. | Keep knowledge sharing separate from sending reviewed results. Establish who maintains the shared rules and how colleagues adopt an update. A common Drive folder, a pull at session start and synchronization at session end were discussed. Validate the need for simultaneous editing and the acceptable write permissions first. [Setup transfer](tools/project.py) |
| Staff maintaining the tool after handover | Plain-language Help suggests a next step. History records changes, though details appear as raw data. Test invoices and model effort settings already occupy primary navigation. | Keep Help within reach. Make history readable and let pilot participants choose which activity to export for feedback. Keep evaluation and model tuning available to maintainers. A repair action and a guided way to request workflow changes are later options. The proposed change workflow would explain effects and seek confirmation before touching application files. [Help skill](skills/invoice-help/SKILL.md) · [History and settings](app/app.js) |

### What to learn in the pilot

1. **Watch one invoice go all the way into the register.** Have staff use their usual process, then try a comparable invoice in the workspace. Record review time, time spent locating evidence, retyping and where they expect to upload. Have them find one failed rule, correct one value and explain what **Confirm review** will save.
2. **Test the handoffs.** Ask a colleague to start from a shared setup and a partner to interpret a marked PDF without the workspace. Try a multipage bundle, an ambiguous classification and a request about the wrong project. Test ordinary wording in both assistants. Check whether staff receive scanned guidelines; the current proposal skill requires readable text. [Guideline support](skills/propose-rules/SKILL.md)
3. **Use a week of ordinary work to set the next scope.** After the correctness fixes, collect repeated points of friction and examples staff agree to share. Use those observations to decide on direct chat submission, Drive collaboration, a PDF findings sheet and adjustable marks. Investigate model delegation if usage limits become a practical constraint. Branding and licensing wording remain separate handover decisions.

## File structure audit

At revision `a2f45a1`, Git tracked 62 files. The small Python tools, one source directory for skills, dependency lockfile and one directory per project make the installation understandable. The main structural problem was ownership: six editable example-project files were tracked alongside the application, and Git ignored only selected parts of other projects. An invoice PDF was ignored while a tip or proposal naming that invoice could be added to Git. A disposable installation also demonstrated that saving model settings could remove an independently installed skill and rewrite unrelated Codex settings.

| Location | Who owns it and how it is used |
|---|---|
| `app/`, `tools/`, `tests/` | Application source and tests. The page calls a local Python server. The assistant skills call Python tools for the same project data. Keep review and reporting decisions in shared Python code so both entry points agree. The original single browser script is now split into native modules for [navigation](app/app.js), [invoice review](app/invoice-review.js), [project setup](app/project-setup.js), [history, settings and evaluation](app/workspace-tools.js), and [shared page state and requests](app/workspace.js). These run directly in the browser without a frontend build step. |
| `AGENTS.md`, `CLAUDE.md`, `skills/` | Maintainer-owned instructions. Claude imports the common instructions. Edit skills in `skills/`, synchronize them, then check for drift. The two installed copies let staff use either assistant without creating symbolic links on Windows. |
| `.claude/skills/`, `.agents/skills/`, `.claude/settings.json`, `.codex/config.toml` | Assistant-specific installation files. Synchronization updates this workspace's named skill files and model settings. It preserves unrelated skills and settings. Retiring a shipped skill also requires retiring its two shipped copies. |
| `assistant-settings.json`, `assistant-settings.local.json` | The first supplies the shipped defaults (and preserves preferences from an older install). The website writes staff preferences to the second, which is excluded from Git. Model settings are also applied to the installed assistant configurations. |
| `templates/`, `projects/` | Templates are distributable starting points. The example contains types, fields and proposed rules for staff to assess. Every live project lives separately under the Git-ignored `projects/`, including private rule descriptions, tips and proposals. |
| `pyproject.toml`, `uv.lock`, `.tools/`, `.venv/` | The dependency declarations and lockfile are shipped. The interpreter, package cache and virtual environment can be rebuilt on the destination machine. The desktop launchers use the workspace runtime. |
| `workspace.json` | Local selection for the next task. A project-specific operation carries its own project identifier. Include this file in a backup if you want to reopen the same selection. |

### Inside a live project

- **Originals and project knowledge:** `invoices/` holds source documents and their upload-name metadata. `guidelines/` holds source requirements. The top-level JSON files contain project details, types, fields, rules, reviewer tips and change proposals.
- **Decisions and history:** `results/` contains machine-readable findings and human review records alongside generated marked documents and reports. Rechecks awaiting confirmation are stored with the invoice result. Earlier confirmed versions are kept under `results/archive/`, and new marked PDFs have per-version paths under `results/marked/`. `history.jsonl` records project activity. Back up the whole directory to retain the context behind an exported spreadsheet.
- **Evaluation and working files:** `evaluation/` contains test documents, reviewer-confirmed answers, latest checks and run history. `work/` contains rendered pages, evidence grids and intermediate drafts. A full backup includes both, particularly when someone may resume work in progress.

### Backup, update and recovery

1. Finish any running checks and close the local server. Copy the entire `projects/` directory **including hidden files** to a private backup location. Also copy `workspace.json` and `assistant-settings.local.json` if present. For older installations, preserve `assistant-settings.json` as well. Back up any independently customized skills or assistant configuration separately.
2. For an update from the original layout, install the new release in a separate folder and keep the old folder until verification finishes. The original release tracked files inside the example project. An in-place Git update could remove those files even on a machine where the invoice PDFs remain.
3. Restore the project directory into the fresh installation. Restore the selection and preferences; an older customized `assistant-settings.json` can be copied as `assistant-settings.local.json`. Install the locked dependencies and run `tools/sync_skills.py` using the workspace runtime. Restore independently installed skills as needed.
4. Choose the restored project, open a previously reviewed invoice, check its correction and download the report. Verify the project history and test answers if the team uses them. **Download setup to share** transfers configuration, and **Download project workbook** transfers results. A full recovery uses the project folder.
