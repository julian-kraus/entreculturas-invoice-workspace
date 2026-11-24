# Impendo Invoice Workspace design proposal

**Status — proposed.** This document specifies a future implementation. Start with the invoice review screen, where staff need to read a result, inspect its evidence, correct it and decide whether to confirm it.

## Global tokens

Use CSS custom properties in `:root`. Define typography and spacing in rem so the interface follows the user's font settings. Pixel equivalents below assume a 16px root.

| Type role | Size / line height | Weight | Where to use it |
| --- | --- | --- | --- |
| Workspace title | 32 / 40px, 24 / 32px on narrow screens | 700 | Impendo Invoice Workspace, once per page |
| Page title | 24 / 32px | 700 | Invoices, Settings or the open invoice filename |
| Section heading | 20 / 28px | 600 | Your review, Project history |
| Row title and control label | 16 / 24px | 600 | Rule name, field label, action |
| Body and input | 16 / 24px | 400 | Findings, explanations, editable values |
| Supporting text and status | 14 / 20px | 400 for text, 600 for badges | Dates, page references, review status |

Use `--font-ui: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif` for all roles, including form controls. Use `ui-monospace, Consolas, monospace` only for literal commands or identifiers. Both stacks work offline. Use tabular numerals in columns of amounts. Allow long filenames, translations and labels to wrap.

| Token family | Proposed values | Application |
| --- | --- | --- |
| Space | `--space-1` through `--space-8` = 4, 8, 12, 16, 20, 24, 32, 48px respectively | 4px label to hint, 8px between related controls, 12px between rows, 16px between groups, 24px between sections |
| Inset | Page 24px desktop / 16px narrow, card 16px, compact row 12px, button 8px vertical / 16px horizontal | Reuse space tokens for padding and gap |
| Shape | 6px controls, 8px panels, fully rounded status pills, 1px control outlines | Flat panels, no shadow except elevated dialogs |
| Measure | 80rem shell, 70ch prose, 44px minimum action height | Center the shell, keep help readable, let actions wrap |

| Color roles | Foreground / background | Contrast on specified pair |
| --- | --- | --- |
| Text, secondary text | `#16232F`, `#52626D` on panel `#FCFCFA` | 15.54, 6.15 to 1 |
| Primary action | White on teal `#0A6E85` | 5.86 to 1 |
| Passed | `#196841` on `#D6EEE3` | 5.55 to 1 |
| Failed or error | `#9A3127` on `#F8DFDB` | 5.83 to 1 |
| Unclear or needs attention | `#794900` on `#FBECC8` | 6.48 to 1 |
| Field boundary | `#657780` against panel `#FCFCFA` | 4.54 to 1 |

Keep the canvas at `#F3F5F2`, neutral grouping at `#E7ECEA` and the dark header at `#16232F`. Use spacing and headings to group content. Use a 3px teal focus outline with a 2px offset on light surfaces and white on the header. On page images, use a two-tone white and dark outline so focus stays visible over both paper and printing. Pair colors with text such as “Failed”, “Unclear” and “Corrected”. Show the check outcome and the human review status as separate labels.

## Components

| Component | Contract and examples |
| --- | --- |
| Primary button | Solid teal. One per action group for its main commitment, such as **Confirm review** or **Save settings**. |
| Secondary button | White (`#fff`) fill, dark text and a visible outline on both dark and light surfaces. Use for **Save draft**, **New project** and downloads. Implement file downloads as links with the same visual treatment. |
| Text action | Underlined teal label for low-emphasis actions such as **Copy question** and **Edit value**. Use a button for a command and a link for a destination. |
| Destructive button | Use a red outline for the initiating action and solid dark red for the final **Discard changes** button. Name the consequence and initially focus **Keep editing**. |
| Button states | On hover darken the primary fill to `#085C70` or tint the secondary surface. On press darken further or strengthen the border. On keyboard focus show the shared outline. During a save keep the action in place with “Saving…” and block repeat submission. Explain a disabled action beside it when the reason is unclear. |
| Panel and row | Use one panel for one task, such as the review summary. Space repeated findings and fields apart and put the title, value or decision before its actions. An invoice list row has one named navigation control. Keep each action in an editable row independently focusable. |
| Form | Put a persistent label above the control, then a hint or inline error. Connect messages with `aria-describedby`, set `aria-invalid` on invalid fields and focus the first error on submit. Keep the user's input for correction. Scope ambiguous edits explicitly, e.g. **Value for this invoice** versus **Edit project field instructions**. |

## Interaction contracts

- **Navigation.** Place “Impendo Invoice Workspace” above the labeled project selector. The primary destinations are **Invoices**, **Project setup**, **Settings** and **Help**, in that order. Settings uses the same subsection navigation as Project setup for **Export**, **History** and **Assistant settings**. **Settings → Export** includes project downloads, individual invoice results and confirmed row copies. Keep native navigation buttons keyboard reachable and mark the active destination with `aria-current="page"` and a filled background. Hide inactive panels. Keep focus on a section switcher when it changes the adjacent panel. Keep focus on the selected Settings subsection control. Focus the heading when opening an invoice, then restore focus to the invoice list row on return.
- **Invoice detail.** Use the same white arrow to the left of the filename, with the accessible name **Back to invoices**. Put **Export** and **Copy recheck request** alongside the heading as secondary actions for checked invoices. Show the invoice type, classification reason and check summary beneath the title. Give any questions their own section. Keep the check outcome, human review status and rule count immediately above the findings. Place **Your review** in a full-width row below the findings and evidence viewer.
- **Invoice exports.** Show one secondary **Export** button for a checked invoice. Its named dialog offers **Download marked PDF**, **Download CSV** and **Copy results** for the open invoice. Use the saved finding outcomes, explanations and extracted values. An unaccepted recheck leaves confirmed exports in place. Keep the current review and unsaved edits open, and return focus to **Export** when the dialog closes.
- **Finding decisions.** Put a named native outcome selector in each editable finding header. Pair Passed, Failed, Unclear and Does not apply with their status colors. Show the original assistant outcome and explanation below it. Changing the outcome opens **Your reason**. **Edit reason** supports a reason-only change. **Reset finding** restores the automatic result and clears the reviewer explanation. Keep automatic duplicate-number warnings read-only.
- **Selection and disclosure.** Use labeled, mutually exclusive pressed buttons for Rule findings / Extracted values. Keep a visible selected indicator distinct from keyboard focus. Use native details/summary for optional information. An Edit button exposes its labeled input, sets `aria-expanded` and focuses the field. Collapsing the editor retains its value. A named modal dialog returns focus to its opener on dismissal. Escape cancels and keeps the draft.
- **Project changes.** Capture the requested project, guard unsaved edits and disable controls bound to the previous project during the switch. Commit the selector, data and actionable panel together after successful loading. On failure restore the previous selection and panel, or offer Retry in a non-editable error panel if the previous state cannot be restored. Bind every mutation to the project and invoice shown when its action began.
- **Drafts and async work.** Distinguish Unsaved changes, Saving, Draft saved and Confirmed. Capture a draft version at submission. Only acknowledge that version, preserve later edits and ignore stale results after navigation. Polling should patch changed content and preserve input, caret, selection and focus. Keep a save error and Retry next to the action. On a revision conflict retain the draft and offer to compare it with the latest saved result before resubmission.
- **Uploads.** Pair the drop target with a keyboard-operable file picker and visible accepted types. List each file's outcome. For a partial success, show e.g. “2 added, 1 failed”, the failed filename and cause, plus Retry for that file. Keep failed rows until resolved or dismissed. Announce the summary once via a status region. For an empty list offer Add invoices. For a failed load offer Retry.
- **Invoice evidence.** Show the recorded page and mark number in the card header, for example **Page 2 · #3**. Selecting the card or activating its title scrolls to the evidence. The numbered mark returns to the card. Show the page by itself when only its location is recorded, and show **No evidence marked** when neither is available. Keep edit controls independent and preserve edits while inspecting pages. Keep a proposed recheck separate from the confirmed result until the reviewer accepts it.
- **Responsive layout.** Place review and evidence side by side on wide screens and stack them on narrow screens. Use equal-height panes with independent scrolling in either layout. Below 40rem use the narrow title and page inset, wrap action rows and keep project controls full-width as needed. At 320px viewport width, labels and controls must fit without horizontal page scrolling. Respect reduced-motion preferences when scrolling to evidence.

## Adoption order

1. In [app.css](../../app/app.css), inventory duplicate selectors and introduce tokens behind the existing classes. Consolidate primary, ghost, link, card and field styles in cascade order. Apply the same tokens to the static controls in [index.html](../../app/index.html) and the generated elements.
2. In [workspace.js](../../app/workspace.js), keep the existing `button()`, `pill()`, `askConfirm()`, `notify()` and `uploadFiles()` entry points. Map ghost to secondary, give destructive actions their own variant and return per-file upload results. Keep transient copy confirmations in the shared status region and actionable errors in the affected panel.
3. Implement project transition and focus handling in [app.js](../../app/app.js). Apply the draft guard and evidence behavior in [invoice-review.js](../../app/invoice-review.js), then align [project-setup.js](../../app/project-setup.js) and [workspace-tools.js](../../app/workspace-tools.js). Verify by keyboard at desktop and 320px width. Exercise a failed switch, an edit during save, a mixed upload and a round trip from a finding to its mark.
