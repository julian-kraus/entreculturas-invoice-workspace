---
name: open-workspace
description: Start the invoice workspace page so the person can review invoices, edit rules and descriptions, and see test results. Use when someone asks to open the workspace, the page, or the review screen.
---

# Open the workspace page

1. Check whether it already runs: open `http://localhost:8790/api/state`. If it answers, skip to step 3.
2. Start it from the repository root as a background process: `./.tools/uv run app/server.py`. It keeps running until stopped.
   - In the Claude desktop app, the preview named "workspace" starts it and shows it beside the chat.
   - If background processes stop when your command ends, ask the person to double-click `start-workspace` (Windows: `start-workspace.bat`, Mac: `start-workspace.command`) instead.
3. Tell the person the page is at http://localhost:8790 and, if the app has a browser panel, open it there.
