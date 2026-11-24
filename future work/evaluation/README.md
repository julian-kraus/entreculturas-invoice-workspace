# Evaluating invoice checks

This idea is deferred beyond the local pilot. The question for a project team is whether changing its rules, field descriptions or assistant settings helps the assistant catch more real problems on invoices the team has already reviewed.

## Building a reference set

A reviewer selected an invoice after confirming its review. The workspace copied the source document and saved its assigned type, final values for the fields configured for that type, and rule outcomes the reviewer had accepted or corrected to *passed* or *failed*. Missing values counted as empty. Each case recorded the reviewer’s name and when the case was added. A reviewer could keep a case aside for an independent check, with the remaining cases available for improving descriptions.

## Rechecking and scoring

Adding a case seeded its first comparison with the assistant’s original reading before reviewer corrections. For a fresh run, the assistant cleared the latest readings, read every test invoice in the selected project using the ordinary invoice-checking workflow and current confirmed rules, and saved its predictions separately. The skill instructed the assistant to read the invoice without consulting the stored answers. Scoring compared those predictions with the saved answers and listed any invoices still awaiting a reading.

| Measure | What the team could learn |
| --- | --- |
| Invoice type | How often the assigned type matched the reviewed case. A wrong type could also cause relevant rules to be skipped. |
| Field values | How many configured fields matched, with expected and observed values for each difference. Amounts used a tolerance of less than 0.01, dates were parsed when possible, and text comparison normalized case, accents and whitespace. |
| Rule outcomes | An unclear or absent prediction counted as **unclear**. For the remaining predictions, a **missed problem** meant the assistant predicted *passed* or *not applicable* for a rule the reviewer marked failed. A **false alarm** meant it failed a rule the reviewer marked passed. The scorer counted agreement as a match and also counted a *not applicable* prediction as a match when the reviewer had marked the rule passed. Missed problems had highest priority for investigation. |

## Using the results

The workspace stored timestamped runs, summarized the main and held-aside groups separately, and showed per-invoice differences and earlier scores. Staff could compare runs after a change. The improvement skill could use repeated discrepancies to propose clearer descriptions for human approval.

Two details matter if this returns. The old improvement workflow exposed differences for both groups, so genuinely independent cases would need to stay out of tuning feedback. Runs also lacked snapshots of the rules and assistant settings. Recording those alongside case counts and unchecked invoices would help staff interpret a change in score.

Older installations may retain private files under `projects/<project>/evaluation/`. Its `invoices/`, `truth/`, `latest/` and `runs/` folders held case documents, confirmed answers, predictions and score history respectively. These belong with the local project backup.
