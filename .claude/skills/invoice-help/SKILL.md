---
name: invoice-help
description: Explain what this invoice workspace can do and suggest the next step for the selected project. Use when someone asks for help, what they can do, how it works, or seems unsure what to do next.
---

# Help

Run `./.tools/uv run tools/project.py list` and answer in plain words, short:

1. Which project is selected, and how many invoices it has, checked and not yet checked.
2. What they can ask you in the chat:
   - "Check the new invoices" (check-invoices)
   - "Propose rules from the guidelines" (propose-rules)
   - "Suggest improvements" (suggest-improvements): proposes clearer descriptions from corrections
   - "Add these invoice files" or "Add these guidelines" (add-files)
   - "Import these shared rules" (share-rules)
   - "Switch to project …" or "Start a new project" (switch-project)
   - "Open the workspace" (open-workspace)
3. The page can copy a request for one invoice, the displayed batch, or a specific finding. Ask the person to paste it into this project chat. The page is also where they add invoices, upload guidelines when creating a project or under **Project setup → Project details**, review proposals in **Project setup → Inbox**, change descriptions, and review findings and values. Guideline detection sends readable guideline text, invoice type and field definitions, and existing rules to Codex using the signed-in plan. Invoice pages are processed through the assistant used in chat. Scanned guidelines need OCR or a text-readable version. Each editable rule finding shows an outcome selector and the original assistant decision. Changing the outcome opens Your reason. Edit reason lets staff add their explanation to the existing decision. Reset finding clears the invoice-specific edits to that finding. On a checked invoice, **Export** offers its marked PDF, CSV and copyable saved results. **Settings → Export** also offers project and setup workbooks, a confirmed spreadsheet row, setup JSON, a confirmed-rules ZIP and selected history entries. Open **Help** in the main navigation for workspace guidance. Use **Settings → History** for project activity and **Settings → Assistant settings** to change models.
4. One suggested next step based on the project's state, for example confirming proposed rules before the first check, or reviewing invoices that need a look.
