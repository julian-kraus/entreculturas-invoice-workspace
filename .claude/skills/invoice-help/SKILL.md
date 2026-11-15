---
name: invoice-help
description: Explain what this invoice workspace can do and suggest the next step for the selected project. Use when someone asks for help, what they can do, how it works, or seems unsure what to do next.
---

# Help

Run `python tools/project.py list` (use `python3` if `python` is not found) and answer in plain words, short:

1. Which project is selected, and how many invoices it has, checked and not yet checked.
2. What they can ask you in the chat:
   - "Check the new invoices" (check-invoices)
   - "Propose rules from the guidelines" (propose-rules)
   - "Run the test invoices" (run-evaluation)
   - "Suggest improvements" (suggest-improvements): proposes clearer descriptions from corrections
   - "Switch to project …" or "Start a new project" (switch-project)
   - "Open the workspace" (open-workspace)
3. What they do on the workspace page: add invoices and guidelines, approve or reject what you proposed (top of Rules and types), edit invoice type descriptions, review findings and correct values, add reviewed invoices as test invoices, see the history and create the Excel report.
4. One suggested next step based on the project's state, for example confirming proposed rules before the first check, or reviewing invoices that need a look.
