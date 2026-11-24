---
name: add-files
description: Add invoice documents or funder guidelines supplied in chat to a project.
---

# Add files from chat

Resolve the project once and pin it with INVOICE_PROJECT on every command, as described in AGENTS.md. Use file paths provided in chat. If the project is ambiguous, ask which project the files belong to.

For invoices run `./.tools/uv run tools/add_files.py invoice <file> [<file> ...]`. For funder guidelines use `./.tools/uv run tools/add_files.py guideline <file> [<file> ...]`. Report the project, added files and any failures, and point to the workspace page for review. If the person asks to check newly added invoices, continue with the check-invoices skill using only successfully added invoice IDs in that project. If they ask to propose rules, continue using the propose-rules skill with the same project.
