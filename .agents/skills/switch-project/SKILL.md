---
name: switch-project
description: Show the projects in this workspace, switch to another one, or create a new one. Use when someone names a project, asks which projects exist, or wants to start a new project.
---

# Switch project

Work from the repository root.

- List projects: `./.tools/uv run tools/project.py list`. Say which one is selected and how many invoices each has.
- Switch: `./.tools/uv run tools/project.py switch "<name or part of it>"`. If several match, ask which one.
- Create: `./.tools/uv run tools/project.py create "<name>"`. To use the bundled Template project, add `--template`. It includes AEXCID invoice types, fields to extract and proposed rules. To copy a local project's types, fields and rules, add `--copy-rules-from <project>`. Previously confirmed rules from a local project become proposed in the copy. Ask the person to review the proposals in Project setup → Inbox.

After switching or creating, confirm the selected project in one sentence. The workspace page shows the same selection after a refresh.
