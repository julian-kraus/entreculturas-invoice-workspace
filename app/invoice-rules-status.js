import { api, button, el, startRuleDetection, state } from "./workspace.js";

let requestNumber = 0;
let previousDisplay = "";

// Viewing this summary only reads status. It never starts detection.
export async function loadInvoiceRulesStatus(project, openRules) {
  const request = ++requestNumber;
  const panel = document.getElementById("invoice-rules-status");
  if (!panel || !project || state.current !== project || state.tab !== "invoices") return;
  try {
    const [proposals, detection] = await Promise.all([
      api("GET", "/api/proposals", undefined, project),
      api("GET", "/api/rule-detection/status", undefined, project),
    ]);
    if (request !== requestNumber || state.current !== project || state.tab !== "invoices") return;
    const count = proposals.rules.length + proposals.changes.length;
    document.dispatchEvent(new CustomEvent("invoice-inbox-status", { detail: { project, count } }));
    const display = JSON.stringify([project, count, detection.status, detection.message]);
    const hasVisibleStatus = count > 0 || detection.status === "running" || detection.status === "failed";
    if (panel.dataset.display === display && previousDisplay === display &&
        (panel.childNodes.length || !hasVisibleStatus)) return;
    previousDisplay = display;
    panel.dataset.display = display;
    const contents = [];
    if (detection.status === "running") {
      contents.push(el("p", { text: detection.message || "Checking guidelines for rules…" }));
    } else if (detection.status === "failed") {
      contents.push(el("p", { text: detection.message || "Rule detection could not complete." }),
        button("Retry rule detection", () => startRuleDetection(project)));
    }
    if (count) {
      contents.push(el("p", { text: `${count} proposed ${count === 1 ? "rule or change" : "rules or changes"} await review. Handle all Inbox items before checking invoices.` }),
        button("Review proposed rules", () => openRules("inbox")));
    }
    panel.replaceChildren(...contents);
    panel.hidden = !contents.length;
  } catch (error) {
    if (request !== requestNumber || state.current !== project || state.tab !== "invoices") return;
    panel.dataset.display = "";
    panel.hidden = false;
    panel.replaceChildren(el("p", { text: `Could not load rule status: ${error.message}` }),
      button("Try again", () => loadInvoiceRulesStatus(project, openRules)));
  }
}
