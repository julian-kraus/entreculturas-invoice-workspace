# Invoice workflow plan

**Status — proposal.** Invoice checks run in the existing project chat. The website copies requests and displays saved work. Guideline detection remains a separate background Codex run that the website already supports. Website-started invoice checks, chat submission and invoice job tracking are outside this plan.

## Current experience

Invoices currently shows one list and offers to copy a batch request for invoices without a check timestamp. Staff paste the request in chat. The assistant checks the documents and saves each result to the pinned project. The page polls while Invoices is visible. Invoice detail already supports findings, evidence, value corrections, review, recheck comparison and exports. Project setup already defaults to standard invoice fields and offers guideline detection, an Inbox and configuration. [Invoice list and detail](../app/invoice-review.js) · [Batch request](../app/app.js) · [Project creation](../app/index.html)

## Invoice home

```text
Invoices                                              [Add invoices]

3 proposed rules                                      [Review proposed rules]

Needs review · 2
  Invoice C.pdf          Fails rules · Review                                ›
  Invoice D.pdf          Passes · Continue review                            ›

To check · 2                                          [Copy request for 2]
Paste the request into your project chat to start the checks.
  Invoice A.pdf          Not checked                                         ›
  Invoice B.pdf          Not checked                                         ›

Confirmed · 1
  Invoice E.pdf          Passes · Confirmed                                   ›
```

- Show the queues in this order and keep each invoice in one queue. Each row has one navigation target, with the display filename, saved outcome and next action available together. A pending change belongs in Needs review, with the current confirmed outcome labelled separately when one exists.
- With a selected project and zero invoices, lead with **Add invoices** and the paste step. With zero projects, keep **New project** or project selection as the entry point. Keep partial upload results and **Retry failed files** separate from the saved invoice list, scoped to the project where the upload started.
- Collapse empty queues to a concise count or message. Keep a stable order within each queue using the existing file order and invoice IDs. Preserve the focused row or its successor when polling updates the list. After a successful confirmation or acceptance, return to the list with the moved row visible and focused. A successful draft save stays in detail. Keep Back and the unsaved-edit guard.

## Saved-state contract

Derive both list placement and request eligibility from one server-side result check. Treat a valid legacy result without a timestamp as checked. Keep an unreadable result out of copied batches and show a load error for that invoice without hiding the other rows. Keep legacy revision hashing and existing list fields. Add explicit `has_result`, `review_status` and candidate provenance fields to the list response, with the candidate revision still separate from the base revision. Keep the CLI pending list and project counts consistent with the website. [List API](../app/server.py) · [Result state](../tools/results.py) · [CLI pending list](../tools/pages.py) · [Project counts](../tools/project.py)

| Saved state, in priority order | Queue | Action |
| --- | --- | --- |
| A pending candidate exists | Needs review | **Continue draft**, **Compare recheck** or **Review pending change**, according to saved provenance. |
| No saved result | To check | **Copy check request** for this invoice or its displayed batch. |
| A result has no confirmed review | Needs review | **Continue review** for a saved draft, otherwise **Review**. Missing legacy review status is awaiting confirmation. |
| Confirmed review with no pending candidate | Confirmed | **Open invoice**. |

Keep the saved outcome distinct from review status. **No applicable rules** means the saved check found zero enabled, confirmed rules for the chosen type or all types. Keep extracted values and any separate duplicate-number finding available. Put the contextual **Review rules** link in detail, with a route to the relevant type and all-types rules or proposed rules. Keep **Review proposed rules** as a project action based on actual pending rule proposals, even if the last detection run found none. Before an invoice is classified, speak only about project-wide rule availability. [Rule evaluation](../tools/checks.py) · [Project setup](../app/project-setup.js)

## Chat handoff and refresh

1. The batch and individual actions copy the project slug, exact invoice IDs and intent. Initial-check requests explicitly ask to check the listed invoices **only if they are still unchecked** and to use that project's confirmed rules. A batch is a snapshot of the displayed To check queue. New files enter the next batch. Copy success says “Request copied. Paste it into your project chat to start the checks.” If the clipboard fails, give users the existing selectable-text dialog.
2. The assistant pins the project for every operation, verifies eligibility for each ID before reading, and repeats the check at save time. A repeated or stale batch skips invoices already checked, reports unavailable IDs and keeps going with the rest. An interrupted check leaves the invoice in To check. Chat reports which invoices were saved, skipped or failed, with a next action for retry. If imported or edited setup has no enabled invoice types, route staff to Invoice types so they can enable or add one. Persisted results appear independently as they are saved. Adding files in chat checks only the successfully added IDs when the person also requested a check.
3. **Copy recheck request** prepares an explicit recheck for one invoice. Include the displayed base revision in the copied request. Chat verifies that revision and the absence of a candidate before reading and again when saving. If the invoice changed or already has a pending candidate, direct staff to the saved work. Direct chat rechecks obtain their starting revision from the same scoped tool. A question about an existing finding continues to explain evidence without starting another check.
4. Copying only changes the inline feedback. The website can show a saved result or candidate, and an actual upload, clipboard or refresh error. Refresh on return to the Invoices tab and when the browser becomes visible, alongside periodic visible-tab polling. Guard all async work by project and view generation, including switching away and back to the same slug. [Chat checking skill](../skills/check-invoices/SKILL.md) · [Chat ingestion skill](../skills/add-files/SKILL.md) · [Copy and polling](../app/app.js)
5. Compare incoming base and candidate revisions against the **open detail's** snapshot. If either changed while the review is dirty, keep the edits and show that a newer saved version exists. A conflicting save preserves the form and explains that the reviewer must inspect the latest version before applying changes. Reload or discard requires a deliberate action. Polling and a successful copy should leave keyboard focus where it is. [Existing refresh guards](../app/invoice-review.js)

## Protect pending work before publishing queue labels

Today a staff draft on a confirmed invoice, an assistant recheck and a rules recalculation all use `pending_recheck`. A new stage can replace a previous candidate. An assistant save can also replace an unconfirmed staff draft. The current candidate panel treats every candidate as a recheck, compares only selected fields and findings, and offers no draft editor or discard action. [Result mutations](../tools/results.py) · [Rules recalculation](../tools/checks.py) · [Candidate panel](../app/invoice-review.js)

### State changes and compatibility

Serialize each commit with the existing cross-process project lock. Check the expected base revision and candidate revision or explicitly expected absence **inside** the lock before changing anything. Distinguish “expect no candidate” from an omitted token. For old callers, accept omitted expectations only for operations with a safe precondition enforced inside the lock, such as an initial save when no result exists. Update the current chat, web and recalculation entry points together. Share a specific conflict type across the CLI and browser routes so clients can report the conflict without retrying a write against newer revisions. [Lock](../tools/review_lock.py) · [Review API](../app/server.py)

| Operation | Required behavior |
| --- | --- |
| Initial check | Save only if the invoice still exists in the pinned project and has no saved result. A parallel check that gets there second leaves the winner intact. |
| Explicit assistant recheck | Use the identified base revision and require no pending candidate. Stage when the base is confirmed. An awaiting-review result with no saved staff draft can be replaced after the version check. If there is a saved staff draft, ask staff to finish it before rechecking, including when the draft is the base result. |
| Rules recalculation | Use the same result guard and block if a candidate exists. Preserve any staff corrections on the base. Stage recalculation of a confirmed invoice and record its distinct origin even if its UI uses **Compare recheck**. For `--all`, surface per-invoice conflicts and continue with unaffected records. |
| Staff review save | Save against the exact base or staff draft being edited. Offer **Edit confirmed review** when there is no candidate. Saving its draft creates a staff candidate. Editing that candidate requires its exact revision and loads its values, outcomes, reasons, notes and evidence. Direct base saves or confirmations cannot bypass a pending candidate. |
| Candidate confirm or discard | Require the exact base and candidate revisions and explicit staff action. Compare with the prior confirmation, including evidence locations and differences in questions or explanations. Confirm the version the reviewer inspected, or discard the candidate while preserving its snapshot and audit trail. |
| Legacy candidate | Preserve fields, revision, artifact and review state as stored and label **Review pending change**. Offer inspection, confirmation and explicit discard with the same guards. Only a new deliberate staff draft receives staff-draft provenance. |

Mutations publish the revision-specific marked PDF before the atomic result JSON pointer. That pointer is the commit point. Generate a fresh PDF with confirmed status at acceptance from the candidate the reviewer saw and archive the previous confirmation, including its artifact reference. The current acceptance function reuses the candidate PDF, whose cover may say draft or awaiting confirmation. Preserve prior versions and every PDF a committed record references. The standalone marks command currently redraws the published PDF in place. Send standalone redraws to a separate output instead. Store operation IDs and pending history or project-tip changes durably so a retry or later mutation can reconcile those changes once per operation. A reported pre-commit failure leaves the existing result, pending candidate and effective exports intact. A lost response or post-commit failure lets the client reload the committed state and distinguish it from an uncommitted save. [Atomic JSON writer](../tools/common.py) · [PDF cover and rendering](../tools/marks.py) · [Publication and archive](../tools/results.py)

Keep long-running chat reading outside the project lock. Give each attempt its own draft and grid files. Make the shared page cache safe to read during concurrent rendering so the browser and PDF generator see complete pages. Check at save that the invoice source and relevant configuration used for classification, extraction and rule judgment still match. If the project configuration changed during reading, ask the assistant to reload and rerun that invoice. This avoids evaluating newer rules against stale visual judgments. [Page rendering](../tools/pages.py) · [Grid workflow](../skills/check-invoices/SKILL.md) · [Project configuration view](../tools/project.py)

## Rules and project setup

- Keep separately visible actions for guidelines and invoices. Keep standard fields selected by default and put the template, project copy and setup import under **More starting options**. Guidelines stay optional at creation and can be added later under Project details. A project can proceed to invoices immediately.
- Website guideline uploads already start detection. Surface project-scoped reading, completion and failure, plus **Review proposed rules** when there are pending proposals. Preserve manual **Check rules from guidelines** for files added outside the website flow, including files added after a previous run, and Retry for failures and interruption. Use the existing detection endpoint and its follow-up runs when website uploads add guidelines during detection. Send the start request for the captured project after a successful upload even if the user navigated away. Completion with zero proposals says so. Keep pending changes to descriptions accessible through Inbox. A refresh must preserve local setup edits and avoid publishing a stale rules count after a project switch. [Detection backend](../tools/detect_rules.py) · [Project setup](../app/project-setup.js)
- Link proposal sources to an available project file and identify the page. For imported or legacy text citations without a matching file, show the citation and its availability. A source citation helps staff find the evidence. Staff still verify that it supports the interpretation before confirming. If pages lack readable text, request a text-layer PDF or text version. Keep the chat fallback for readable guidelines and other applicable failures. Correct scanned-page advice in the detection error, CLI, Help and skills. [Guideline extraction](../tools/guidelines.py) · [Chat proposals](../skills/propose-rules/SKILL.md)
- Share validation and duplicate handling for automatic and chat proposals under the project lock. Check pending and confirmed rules as well as proposals within the same batch. Keep existing rejections unless staff deliberately reopen the rule. Make duplicates and rejected matches visible as skipped rather than silently dropping possible revised interpretations. Keep source, check method and severity visible for review. Automatic detection can keep creating visual checks with error severity. Chat's supported structured checks remain available and validated against the chosen fields. [Proposal validation](../tools/rules.py) · [Automatic proposal handling](../tools/detect_rules.py)
- Align setup, Help, README and assistant instructions about data and accounts. The website stores project files locally. When guideline detection runs, it sends readable guideline text, invoice type and field definitions, and existing rules to Codex under the signed-in plan. Invoice chat processes invoice pages through the assistant the staff member is using. Explain this where they add guidelines or start a check. [README](../README.md) · [Assistant instructions](../AGENTS.md) · [Detection payload](../tools/detect_rules.py)

## Review and exports

Keep the filename header, two independently scrollable findings and evidence panes, sticky Findings and Extracted values switch, page and mark navigation, editable decisions and reasons, and full-width confirmation section. Desktop panes currently have different widths. Keep the review and document legible at desktop and stack them with bounded scrolling on narrow screens. Check 320px overflow, keyboard operation and screen-reader names. Focus the filename on opening a row. Announce grouped result arrivals, copied requests and errors without stealing focus. [Review layout](../app/app.css) · [Detail controls](../app/invoice-review.js)

Keep marked PDF, CSV and copyable results in invoice detail and the existing export tools under Settings. Label invoice exports with the saved review status. While a confirmed result has a pending change, invoice PDF, CSV, text and workbook exports use the saved confirmation. The project workbook currently includes saved unconfirmed rows, with review status in its Invoices sheet. Preserve existing workbook and register behavior and describe it accurately. Individual **Copy confirmed row** and **Copy register row** require confirmation. A review needs no export to finish. [Export controls](../app/workspace-exports.js) · [Workbook and register](../tools/report.py)

## Implementation sequence

| Phase | Deliverable and release check |
| --- | --- |
| 1. Protect writes | Define expected-state inputs and candidate provenance. Update all writers, status/read tooling, isolated chat scratch files, approval/discard and archival publication. Make the existing browser actions, copy requests, CLI and synchronized chat instructions use the new contract in the same release. Cover separate-process races, legacy records, stale tabs and failures before and after the commit point. |
| 2. Organize review | Add the list-state fields, queues and focus behavior. Connect candidate actions to the same scoped endpoints. Keep dirty reviews during polling. Verify evidence, review and export parity using old and new records. |
| 3. Clarify the handoff | Update scoped batch and individual request copy, skip/recheck treatment, visibility refresh and Help. Exercise the copy/paste loop and partial results in a disposable project. |
| 4. Simplify rule discovery | Update project creation, project-scoped rule CTA and detection status, source navigation, duplicate behavior and account wording. Exercise blank, failed, interrupted and follow-up detection states. |
| 5. Pilot | Observe a staff member with a standard project and an existing AEXCID project as they add files, check through chat, review a partial batch, correct evidence or a value, confirm, handle a pending change and export to their real register. |

## Acceptance checks

- **First use and repeated use** — Create a standard project with no guidelines, add one or several files, retry a partial upload and copy singular and plural requests. Test the selectable fallback. Paste a batch in chat, save one result, switch away and return. The saved invoice appears in Needs review while the others stay in To check. A repeat paste skips the saved invoice. A newly added file stays outside the copied batch. Website actions issue no invoice-check or chat-submission request.
- **Queue and focus** — A result without `checked_at`, an awaiting review, a saved draft, a confirmation and each candidate origin appear in exactly one correct queue. Test a legacy candidate with no origin and a project with proposed-only or disabled rules. Confirm, return with the correct row visible and focused, and add another invoice. Exercise keyboard operation, 320px layout and independent evidence scroll.
- **Concurrent edits** — Start two initial checks of the same invoice. Start a draft and a recheck in both orders and concurrently in separate processes. Repeat with recalculation and two stale tabs. An unseen or mismatched revision leaves the newest saved work intact. Resuming a known draft restores its saved edits. A stale accept or discard cannot affect a newer candidate. Test two simultaneous chat attempts against a multipage invoice and a browser opening its evidence, and change rule configuration while chat is reading.
- **Publication and retries** — Simulate render and write failures, a lost response after commit and a project-tip retry. Keep the previous confirmation, candidate, PDF and history consistent. An explicit acceptance changes all effective exports to the reviewed revision, with confirmed status on the PDF, and maintains the earlier confirmation in the archive. Discard leaves the official result and exports unchanged and retains the discarded snapshot. A standalone redraw leaves previously published PDFs byte-for-byte intact.
- **Scoping and refresh** — Use projects with the same invoice ID, switch while uploads, polling or detail requests are in flight, and switch back. A stale patch, copied request or retry cannot target the wrong project. An arrival during dirty review stays visible after further polls while unsaved edits and focus are preserved. Switching or reloading after canceling the dirty guard keeps the editor in place.
- **Rules and accounts** — Run success with proposals, success with none, a readable fallback, a scanned or mixed guideline, an interrupted run and an upload while detection is active. Confirm source routing and real pending counts after accepting or rejecting proposals. Repeating automatic and chat proposals cannot add the same pending or confirmed rule. Check that account and data-transfer wording matches actual calls.
- **Repository verification** — Run `./.tools/uv run --locked pytest -q tests` and `./.tools/uv run --locked tools/sync_skills.py --check`. Use synthetic or disposable project data for API and browser tests, and preserve the existing user projects.
