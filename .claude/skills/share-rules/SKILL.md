---
name: share-rules
description: Import a colleague's invoice workspace rules ZIP into a project's Inbox or export confirmed rules for a colleague.
---

# Share rules

Resolve the project once and pin it with INVOICE_PROJECT on every command, as described in AGENTS.md.

When the person supplies a ZIP and asks to add its rules to a project, run `./.tools/uv run tools/share_rules.py import <zip-file>`. The tool checks the ZIP and requires matching invoice types and fields. It adds new rules as proposals to the Inbox, skips duplicates, and leaves existing rules intact. If required types or fields are missing, explain which ones and help the person add them before retrying. Tell them how many rules were added and that they need to review them in Project setup → Inbox.

When asked to export, people can download the confirmed rules ZIP from Settings → Export. Alternatively use `./.tools/uv run tools/share_rules.py export <new-zip-file>`. The ZIP contains rules and type/field context, so ask the person to check what they share.
