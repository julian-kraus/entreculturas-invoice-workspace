---
name: switch-project
description: Show the projects in this workspace, switch to another one, or create a new one. Use when someone names a project, asks which projects exist, or wants to start a new project.
---

# Switch project

Work from the repository root.

- List projects: `./.tools/uv run tools/project.py list`. Say which one is selected and how many invoices each has.
- Switch: `./.tools/uv run tools/project.py switch "<name or part of it>"`. If several match, ask which one.
- Create: `./.tools/uv run tools/project.py create "<name>"`. To start from another project's invoice types and rules, add `--copy-rules-from <project>`. Copied rules start as proposed, so tell the person to confirm them on the workspace page.

After switching or creating, confirm the selected project in one sentence. The workspace page shows the same selection after a refresh.
