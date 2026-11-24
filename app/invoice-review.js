import {
  api, askConfirm, button, confirmLeave, copyText, el, notify, pill, projectUrl, promptButton, state, when
} from "./workspace.js";

const STATUS_LABEL = {
  "passes": "Passes",
  "no applicable rules": "No applicable rules",
  "fails rules": "Fails rules",
  "needs a look": "Needs a look",
  "not checked": "Not checked yet",
};
const OUTCOME_LABEL = { passed: "Passed", failed: "Failed", unclear: "Unclear", not_applicable: "Does not apply" };

let invoiceScope = 0;
let loadedProject = null;
let loadingRequest = null;
let editingCandidate = false;
let inboxStatus = { project: null, count: null };

function updateCheckButtons(project, count) {
  inboxStatus = { project, count };
  document.querySelectorAll("[data-check-request]").forEach(control => {
    if (control.dataset.checkProject !== project) return;
    control.textContent = count ? "Review Inbox before checking" : control.dataset.checkLabel;
  });
  document.querySelectorAll("[data-check-hint]").forEach(hint => {
    if (hint.dataset.checkProject !== project) return;
    hint.textContent = count ? "Handle the Inbox items before checking invoices." :
      "Paste the request into your project chat to start the checks. Invoice pages are processed by the assistant you use in that chat.";
  });
}

document.addEventListener("invoice-inbox-status", event => {
  if (event.detail.project === state.current) updateCheckButtons(event.detail.project, event.detail.count);
});

function guardedCheckButton(label, request, project, scope, style = "ghost") {
  const control = button(label, async () => {
    try {
      const proposals = await api("GET", "/api/proposals", undefined, project);
      if (!control.isConnected || !currentInvoiceScope(project, scope)) return;
      const count = proposals.rules.length + proposals.changes.length;
      updateCheckButtons(project, count);
      if (count) {
        document.getElementById("invoice-detail").dispatchEvent(new CustomEvent("review-inbox"));
        return;
      }
      await copyText(request, "Request copied. Paste it into your project chat to start the checks.");
    } catch (error) { notify(`Could not check the Inbox: ${error.message}`, true); }
  }, style);
  control.dataset.checkRequest = "";
  control.dataset.checkProject = project;
  control.dataset.checkLabel = label;
  if (inboxStatus.project === project && inboxStatus.count) control.textContent = "Review Inbox before checking";
  return control;
}
const reviewResult = () => editingCandidate ? state.detail.candidate.result : state.detail.result;

function currentInvoiceScope(project, scope) {
  return project && project === state.current && scope === invoiceScope && state.tab === "invoices";
}

export function invalidateInvoiceRequests() {
  invoiceScope++;
  loadedProject = null;
  loadingRequest = null;
  state.detailRequest++;
}

export function clearInvoices() {
  invalidateInvoiceRequests();
  loadedProject = null;
  loadingRequest = null;
  Object.assign(state, { invoices: [], selected: null, detail: null, listScroll: 0 });
  displayInvoiceView(false);
  document.getElementById("invoice-detail").replaceChildren();
  document.getElementById("invoice-count").textContent = "";
  document.getElementById("invoice-list").replaceChildren();
  document.getElementById("invoice-rules-status").replaceChildren();
}

export async function loadInvoices({ poll = false } = {}) {
  const project = state.current;
  const scope = invoiceScope;
  if (!currentInvoiceScope(project, scope) || (poll && loadingRequest)) return false;
  const request = {};
  loadingRequest = request;
  const current = () => loadingRequest === request && currentInvoiceScope(project, scope);
  const list = document.getElementById("invoice-list");
  const previous = state.invoices;
  const selected = state.selected;
  if (!poll && loadedProject !== project) {
    list.replaceChildren(el("p", { class: "empty", role: "status", text: "Loading invoices…" }));
  }
  try {
    const invoices = await api("GET", "/api/invoices", undefined, project);
    if (!current()) return false;
    if (loadedProject !== project || JSON.stringify(invoices) !== JSON.stringify(previous)) {
      state.invoices = invoices;
      loadedProject = project;
      renderInvoiceList(project, scope);
    }
    const selectedItem = invoices.find(invoice => invoice.id === selected);
    if (poll && selected && selected === state.selected && state.detail) {
      const changed = selectedItem && (selectedItem.revision !== state.detail.revision ||
        selectedItem.pending_recheck !== (state.detail.candidate?.revision || null));
      if (changed && state.reviewDirty) {
        const detail = document.getElementById("invoice-detail");
        if (!detail.querySelector(".newer-result-notice")) {
          detail.prepend(el("p", { class: "newer-result-notice", role: "status",
            text: "A newer saved version is available. Your edits are still here; review the latest version before saving." }));
        }
      } else if (changed) {
        await selectInvoice(selected, true, project);
      }
    }
    return current();
  } catch (error) {
    if (!current()) return false;
    if (!poll && loadedProject !== project) {
      const retry = button("Try again", () => {
        if (currentInvoiceScope(project, scope)) return loadInvoices();
      });
      list.replaceChildren(el("div", { class: "empty" },
        el("p", { role: "status", text: "Could not load invoices for this project." }), retry));
    } else if (!poll) {
      notify(error.message, true);
    }
    return loadedProject === project;
  } finally {
    if (loadingRequest === request) loadingRequest = null;
  }
}

export function displayInvoiceView(showDetail) {
  document.getElementById("invoice-home").hidden = showDetail;
  document.getElementById("invoice-detail").hidden = !showDetail;
}

export async function backToList() {
  const project = state.current;
  const scope = invoiceScope;
  if (state.reviewDirty && !(await confirmLeave())) return;
  if (!currentInvoiceScope(project, scope)) return;
  const id = state.selected;
  Object.assign(state, { selected: null, detail: null, reviewDirty: false });
  state.detailRequest++;
  displayInvoiceView(false);
  await loadInvoices();
  if (!currentInvoiceScope(project, scope) || state.selected) return;
  document.querySelector(`[data-invoice-id="${CSS.escape(id)}"]`)?.focus({ preventScroll: true });
  window.scrollTo(0, state.listScroll);
}

function renderInvoiceList(project, scope) {
  const list = document.getElementById("invoice-list");
  const focused = list.contains(document.activeElement) ? document.activeElement.dataset.invoiceId : null;
  if (!state.invoices.length) {
    document.getElementById("invoice-count").textContent = "No invoices yet.";
    list.replaceChildren(el("p", { class: "empty", text: "Add an invoice, then copy the check request into your project chat." }));
    return;
  }
  const groups = [
    { key: "review", name: "Needs review", items: state.invoices.filter(i => i.result_error || i.pending_recheck || (i.has_result && i.review_status !== "confirmed")) },
    { key: "pending", name: "To check", items: state.invoices.filter(i => !i.has_result && !i.result_error) },
    { key: "confirmed", name: "Confirmed", items: state.invoices.filter(i => i.has_result && !i.result_error && !i.pending_recheck && i.review_status === "confirmed") },
  ];
  const summary = `${state.invoices.length} total · ${groups[0].items.length} need review · ${groups[1].items.length} to check`;
  const count = document.getElementById("invoice-count");
  if (count.textContent !== summary) count.textContent = summary;
  const row = inv => {
    let action = "Open invoice";
    if (inv.identity_error) action = "Invoice identity needs attention";
    else if (inv.result_error) action = "Result could not be read";
    else if (inv.pending_recheck) action = inv.candidate_origin === "staff_draft" ? "Continue draft" :
      ["assistant_recheck", "rule_recalculation"].includes(inv.candidate_origin) ? "Compare recheck" : "Review pending change";
    else if (!inv.has_result) action = "Not checked";
    else if (inv.review_status === "draft") action = "Continue review";
    else if (inv.review_status !== "confirmed") action = "Review";
    return el("li", {},
    el("button", { type: "button", "data-invoice-id": inv.id, onclick: () => {
      if (inv.identity_error) {
        notify("These files have the same name and their saved result cannot be identified. Restore the result from a backup before checking them.", true);
        return;
      }
      if (currentInvoiceScope(project, scope)) return selectInvoice(inv.id, false, project);
    } },
      el("span", { class: "name", text: inv.file }),
      el("span", { class: "tags" }, inv.has_result && !inv.result_error ? pill(STATUS_LABEL[inv.status] || inv.status, inv.status) : null,
        inv.pending_recheck && inv.reviewed ? pill("Confirmed result", "reviewed") : null,
        el("span", { class: "muted small", text: action })),
      el("span", { class: "chevron", "aria-hidden": true, text: "›" })));
  };
  list.replaceChildren(...groups.map(group => {
    const copy = group.key === "pending" && group.items.length ? guardedCheckButton(
      group.items.length === 1 ? "Copy check request" : `Copy request for ${group.items.length}`,
      `Check these invoices in project "${project}" only if they are still unchecked: ${group.items.map(invoice => JSON.stringify(invoice.id)).join(", ")}. Use the confirmed rules for that project.`,
      project, scope, "primary") : null;
    return el("section", { class: "invoice-queue", "aria-label": group.name },
      el("div", { class: "section-head" }, el("h3", { text: `${group.name} · ${group.items.length}` }), copy),
      copy ? el("p", { class: "muted small", "data-check-hint": "", "data-check-project": project,
        text: inboxStatus.project === project && inboxStatus.count ? "Handle the Inbox items before checking invoices." :
          "Paste the request into your project chat to start the checks. Invoice pages are processed by the assistant you use in that chat." }) : null,
      group.items.length ? el("ul", { class: "navigation-list invoice-list" }, group.items.map(row)) :
        el("p", { class: "muted small", text: `No invoices ${group.key === "pending" ? "to check" : group.key === "review" ? "need review" : "confirmed yet"}.` }));
  }));
  if (focused) list.querySelector(`[data-invoice-id="${CSS.escape(focused)}"]`)?.focus({ preventScroll: true });
}

function invoiceHeader(filename, ...actions) {
  const listButton = el("button", { type: "button", class: "ghost back-button", onclick: backToList,
    "aria-label": "Back to invoices", title: "Back to invoices", text: "←" });
  return el("header", { class: "invoice-header" },
    el("div", { class: "back-heading" }, listButton,
      el("h2", { class: "page-title", tabindex: "-1", text: filename })),
    actions.length ? el("div", { class: "action-row" }, actions) : null);
}

export async function selectInvoice(id, refresh = false, project = state.current) {
  const scope = invoiceScope;
  if (!currentInvoiceScope(project, scope)) return;
  if (id !== state.selected && state.reviewDirty && !(await confirmLeave())) return;
  if (!currentInvoiceScope(project, scope)) return;
  const request = ++state.detailRequest;
  const current = () => request === state.detailRequest && state.selected === id && currentInvoiceScope(project, scope);
  if (!refresh) {
    editingCandidate = false;
    state.listScroll = window.scrollY;
    state.reviewView = "findings";
    state.reviewDirty = false;
    window.scrollTo(0, 0);
  }
  state.selected = id;
  displayInvoiceView(true);
  const detail = document.getElementById("invoice-detail");
  const filename = state.invoices.find(invoice => invoice.id === id)?.file || id;
  if (!refresh || !state.detail) detail.replaceChildren(invoiceHeader(filename), el("p", { class: "empty", role: "status", text: "Loading invoice…" }));
  try {
    const [data, config] = await Promise.all([
      api("GET", `/api/result/${encodeURIComponent(id)}`, undefined, project),
      api("GET", "/api/config", undefined, project),
    ]);
    if (!current() || state.reviewDirty) return;
    state.detail = data;
    state.config = config;
    renderDetail(filename);
  } catch (error) {
    if (current() && !state.reviewDirty) detail.replaceChildren(invoiceHeader(filename), el("p", { class: "empty", role: "alert", text: error.message }));
  }
  if (!refresh && current() && document.activeElement === document.body) detail.querySelector(".page-title").focus({ preventScroll: true });
}

function confirmedValue(result, name) {
  const changes = result.review?.fields || {};
  return Object.hasOwn(changes, name) ? changes[name] : result.fields?.[name]?.value;
}

function candidatePanel(official, candidate, project, invoiceId) {
  const proposed = candidate.result;
  const differences = [];
  const fieldNames = new Set([...Object.keys(official.fields || {}), ...Object.keys(proposed.fields || {}),
    ...Object.keys(official.review?.fields || {}), ...Object.keys(proposed.review?.fields || {})]);
  const fieldLabel = name => state.config.fields.find(f => f.name === name && f.type_id === proposed.type_id)?.label || name;
  const add = (label, oldValue, newValue) => {
    if (String(oldValue ?? "") !== String(newValue ?? "")) differences.push([label, oldValue ?? "—", newValue ?? "—"]);
  };
  add("Invoice type", official.type_id, proposed.type_id);
  add("Status", official.status, proposed.status);
  add("Classification reason", official.type_reason, proposed.type_reason);
  add("Summary", official.summary, proposed.summary);
  add("Questions", JSON.stringify(official.questions || []), JSON.stringify(proposed.questions || []));
  add("Review note", official.review?.note, proposed.review?.note);
  const location = value => value?.page && value?.box ? `Page ${value.page}, box ${JSON.stringify(value.box)}` : "No location";
  for (const name of fieldNames) {
    add(fieldLabel(name), confirmedValue(official, name), confirmedValue(proposed, name));
    add(`${fieldLabel(name)} · evidence`,
      location(official.review?.evidence?.fields?.[name] || official.fields?.[name]),
      location(proposed.review?.evidence?.fields?.[name] || proposed.fields?.[name]));
  }
  const previous = new Map((official.rule_results || []).map(rule => [rule.rule_id, rule]));
  for (const rule of proposed.rule_results || []) {
    const old = previous.get(rule.rule_id);
    add(rule.name, old ? OUTCOME_LABEL[old.outcome] : null, OUTCOME_LABEL[rule.outcome]);
    add(`${rule.name} · reason`, old?.message, rule.message);
    add(`${rule.name} · evidence`,
      location(official.review?.evidence?.rules?.[rule.rule_id] || old?.evidence),
      location(proposed.review?.evidence?.rules?.[rule.rule_id] || rule.evidence));
    previous.delete(rule.rule_id);
  }
  for (const rule of previous.values()) {
    add(rule.name, OUTCOME_LABEL[rule.outcome], null);
    add(`${rule.name} · reason`, rule.message, null);
    add(`${rule.name} · evidence`, location(official.review?.evidence?.rules?.[rule.rule_id] || rule.evidence), null);
  }
  const revision = state.detail.revision;
  const scope = invoiceScope;
  const origin = candidate.origin;
  const title = origin === "staff_draft" ? "Saved review draft" :
    ["assistant_recheck", "rule_recalculation"].includes(origin) ? "Recheck awaiting review" : "Pending change awaiting review";
  const accept = button("Accept and confirm", async () => {
    if (!currentInvoiceScope(project, scope) || state.selected !== invoiceId) return;
    if (state.reviewDirty) { notify("Save or discard your current edits before accepting the recheck.", true); return; }
    if (!(await askConfirm("Replace the confirmed decision with this recheck? The previous confirmation will be kept in the invoice history.", "Accept recheck"))) return;
    if (!currentInvoiceScope(project, scope) || state.selected !== invoiceId) return;
    accept.disabled = true;
    try {
      await api("POST", `/api/result/${encodeURIComponent(invoiceId)}/accept-recheck`, { revision, candidate_revision: candidate.revision }, project);
      if (!currentInvoiceScope(project, scope)) return;
      notify("Recheck accepted. Exports now use the new confirmation.");
      if (state.selected === invoiceId) await selectInvoice(invoiceId, true, project);
      if (currentInvoiceScope(project, scope)) await loadInvoices();
    } catch (error) {
      if (currentInvoiceScope(project, scope)) notify(error.message, true);
    } finally { accept.disabled = false; }
  }, "primary");
  const discard = button("Discard pending change", async () => {
    if (!(await askConfirm("Discard this pending change? The confirmed decision remains available.", "Discard change"))) return;
    if (!currentInvoiceScope(project, scope) || state.selected !== invoiceId) return;
    try {
      await api("POST", `/api/result/${encodeURIComponent(invoiceId)}/discard-candidate`,
        { revision, candidate_revision: candidate.revision }, project);
      editingCandidate = false;
      await selectInvoice(invoiceId, true, project);
      await loadInvoices();
    } catch (error) { notify(error.message, true); }
  });
  const edit = origin === "staff_draft" ? button("Continue draft", () => {
    editingCandidate = true;
    renderDetail(state.invoices.find(invoice => invoice.id === invoiceId)?.file || invoiceId);
  }, "primary") : null;
  return el("section", { class: "candidate-panel" }, el("h3", { text: title }),
    el("p", { text: "Exports continue to use the confirmed decision until you accept this change." }),
    differences.length ? el("div", { class: "table-wrap" }, el("table", { class: "plain" },
      el("thead", {}, el("tr", {}, ["Change", "Confirmed", "Pending"].map(t => el("th", { text: t })))),
      el("tbody", {}, differences.map(row => el("tr", {}, row.map(value => el("td", { text: String(value) }))))))) :
      el("p", { text: "The document type, values, status, rule decisions and reasons match the confirmation." }),
    el("details", {}, el("summary", { text: "Inspect pending evidence and explanations" }),
      proposed.summary ? el("p", { text: proposed.summary }) : null,
      proposed.type_reason ? el("p", { text: proposed.type_reason }) : null,
      (proposed.questions || []).map(q => el("p", { text: q })),
      el("ul", {}, (proposed.rule_results || []).map(r => el("li", { text: `${r.name} · ${OUTCOME_LABEL[r.outcome] || r.outcome}${r.message ? " — " + r.message : ""}` }))),
      !proposed.source_digest ? el("p", { class: "muted small", text: "This older result has no saved document fingerprint, so its evidence pages cannot be verified against the original file." }) : null,
      candidate.pages_error ? el("p", { class: "empty", text: candidate.pages_error }) :
        viewer(candidate.pages || [], candidate.marks || [], "recheck")),
    el("div", { class: "action-row" }, discard, edit, origin === "staff_draft" ? null : accept));
}

function renderDetail(filename) {
  const { candidate } = state.detail;
  const pages = editingCandidate ? candidate.pages : state.detail.pages;
  const pagesError = editingCandidate ? candidate.pages_error : state.detail.pages_error;
  const result = reviewResult();
  const marks = editingCandidate ? candidate.marks : state.detail.marks;
  const id = state.selected, project = state.current;
  const basePrompt = `invoice "${id}" in project "${project}"`;
  const checkRequest = candidate ? null : guardedCheckButton(result ? "Copy recheck request" : "Copy check request",
    result ? `Recheck ${basePrompt} against this project's confirmed rules. The displayed base revision is "${state.detail.revision}". Preserve any pending change.` :
      `Check ${basePrompt} against this project's confirmed rules only if it is still unchecked.`, project, invoiceScope);
  const exportAction = result ? el("button", { type: "button", class: "ghost", text: "Export", "aria-haspopup": "dialog",
    "data-export-invoice": id, "data-export-project": project }) : null;
  const header = invoiceHeader(filename, ...[exportAction, checkRequest].filter(Boolean));
  const container = document.getElementById("invoice-detail");
  if (!result) {
    container.replaceChildren(header, el("p", { text: "Paste the check request into your project chat. The findings will appear here." }), viewer(pages, []));
    return;
  }
  const type = state.config.invoice_types.find(t => t.id === result.type_id)?.name || result.type_id;
  const count = result.rules_checked ?? (result.rule_results || []).filter(r => r.rule_id !== "DUPLICATE_NUMBER").length;
  const description = el("div", { class: "invoice-description" },
    type ? el("p", { class: "invoice-type", text: type }) : null,
    result.type_reason ? el("p", { text: result.type_reason }) : null,
    result.summary ? el("p", { text: result.summary }) : null);
  const questions = result.questions?.length ? [el("section", { class: "questions", "aria-labelledby": "invoice-questions" },
    el("h3", { id: "invoice-questions", text: "Questions from the check" }),
    el("ul", {}, result.questions.map(q => el("li", { text: q }))))] : [];
  const reviewStatus = result.review?.status;
  const reviewLabel = reviewStatus === "confirmed" ? "Reviewed" : reviewStatus === "draft" ? "Draft saved" : "Awaiting confirmation";
  const status = el("div", { class: "tags review-state" },
    pill(STATUS_LABEL[result.status] || result.status, result.status),
    pill(reviewLabel, reviewStatus === "confirmed" ? "reviewed" : ""),
    el("span", { class: "muted small", text: `${count} rule${count === 1 ? "" : "s"} checked` }));
  const readOnly = Boolean(candidate && !editingCandidate);
  const findings = findingsList(result, marks, pages, basePrompt, readOnly);
  const values = fieldsTable(result, marks, pages, readOnly);
  const switchView = name => {
    state.reviewView = name;
    findings.hidden = name !== "findings";
    values.hidden = name !== "values";
    findingsButton.setAttribute("aria-pressed", String(!findings.hidden));
    valuesButton.setAttribute("aria-pressed", String(!values.hidden));
  };
  const findingsButton = button("Rule findings", () => switchView("findings"));
  const valuesButton = button("Extracted values", () => switchView("values"));
  switchView(state.reviewView);
  const review = el("section", { class: "review-detail", "aria-label": "Rule findings and extracted values",
    tabindex: pages?.length ? "0" : undefined },
    el("div", { class: "view-tabs", role: "group", "aria-label": "Review content" }, findingsButton, valuesButton),
    status, findings, values);
  if (result.status === "no applicable rules") {
    status.append(button("Review rules", () => {
      document.getElementById("invoice-detail").dispatchEvent(new CustomEvent("review-rules",
        { bubbles: true, detail: { typeId: result.type_id } }));
    }));
  }
  const returnToCard = mark => {
    const selector = `[data-evidence-mark="${mark.number}"]`;
    const list = state.reviewView === "findings" ? findings : values;
    const control = list.querySelector(selector) || review.querySelector(selector);
    if (!control) return;
    if (!list.contains(control)) switchView(findings.contains(control) ? "findings" : "values");
    control.focus({ preventScroll: true });
    control.scrollIntoView({ block: "nearest", inline: "nearest" });
  };
  container.replaceChildren(header, description, ...questions,
    ...(!result.source_digest ? [el("p", { class: "muted small", text: "This older result has no saved document fingerprint, so its evidence pages cannot be verified against the original file." })] : []),
    ...(candidate && !editingCandidate ? [candidatePanel(result, candidate, project, id)] : []),
    el("div", { class: pages?.length ? "detail-grid has-pages" : "detail-grid" },
      review, pagesError ? el("p", { class: "empty", text: pagesError }) : viewer(pages, marks, "invoice", returnToCard)), !candidate || editingCandidate ? reviewBox(result) : null);
}

function evidenceHeading(card, name, mark, page, pages) {
  if (!Number.isInteger(page) || !pages?.[page - 1]) {
    return el("div", { class: "evidence-heading" }, el("b", { text: name }),
      el("span", { class: "evidence-location", text: "No evidence marked" }));
  }
  const targetId = mark ? `invoice-mark-${mark.number}` : `invoice-page-${page}`;
  const control = button(name, () => {
    const detail = card.closest(".invoice-detail");
    const target = document.getElementById(targetId);
    if (!detail || !target) return;
    detail.querySelector(".evidence-title[aria-pressed=true]")?.setAttribute("aria-pressed", "false");
    detail.querySelector(".document-viewer .hilite")?.classList.remove("hilite");
    control.setAttribute("aria-pressed", "true");
    target.classList.add("hilite");
    target.scrollIntoView({ block: "center", inline: "nearest" });
  }, "evidence-title");
  control.setAttribute("aria-label", `${name}, go to page ${page}${mark ? `, mark ${mark.number}` : ""}`);
  control.setAttribute("aria-controls", targetId);
  control.setAttribute("aria-pressed", "false");
  if (mark) control.dataset.evidenceMark = mark.number;
  card.classList.add("evidence-card");
  card.addEventListener("click", event => {
    if (event.defaultPrevented || event.target.closest("a, button, label, input, select, textarea, summary, [contenteditable]")) return;
    const selection = window.getSelection();
    if (selection && !selection.isCollapsed && selection.containsNode(card, true)) return;
    control.focus({ preventScroll: true });
    control.click();
  });
  return el("div", { class: "evidence-heading" }, control,
    el("span", { class: "evidence-location", text: `Page ${page}${mark ? ` · #${mark.number}` : ""}` }));
}

function editEvidence(group, key, name, location, pages) {
  const edit = button("Move mark", () => {
    const saved = reviewResult().review?.evidence?.[group]?.[key] || location;
    const originalPage = saved?.page || 1;
    const originalBox = saved?.box ? [...saved.box] : null;
    let box = originalBox ? [...originalBox] : null;
    let zoom = 1;
    let gesture = null;
    const dialog = el("dialog", { class: "mark-editor", "aria-label": `Move mark for ${name}` },
      el("h2", { text: `Move mark for ${name}` }),
      el("p", { class: "small muted", text: "Drag on the page to draw a box. Drag inside the box to move it, or drag a corner to resize it." }));
    const page = el("select", { "aria-label": "Evidence page" },
      pages.map((_, i) => el("option", { value: String(i + 1), text: `Page ${i + 1}` })));
    page.value = String(originalPage);
    const canvas = el("div", { class: "mark-editor-canvas" });
    const image = el("img", { alt: "Document page for selecting evidence", draggable: false });
    const rectangle = el("div", { class: "mark-editor-selection", hidden: true, "aria-hidden": "true" });
    for (const corner of ["nw", "ne", "sw", "se"]) {
      rectangle.append(el("span", { class: `mark-editor-handle ${corner}`, "data-corner": corner }));
    }
    canvas.append(image, rectangle);
    const viewport = el("div", { class: "mark-editor-viewport", tabindex: "0", "aria-label": "Document page. Scroll to view the page." }, canvas);
    const message = el("p", { class: "dialog-error", role: "status" });
    const coordinates = ["Left", "Top", "Right", "Bottom"].map(label =>
      el("input", { type: "number", min: "0", max: "100", step: "0.1", "aria-label": `${label} percentage` }));
    const syncInputs = () => coordinates.forEach((input, i) => {
      input.value = box ? String(Math.round(box[i] * 1000) / 10) : "";
    });
    function renderBox() {
      rectangle.hidden = !box;
      if (box) Object.assign(rectangle.style, { left: `${box[0] * 100}%`, top: `${box[1] * 100}%`,
        width: `${(box[2] - box[0]) * 100}%`, height: `${(box[3] - box[1]) * 100}%` });
    }
    function loadPage() {
      image.src = projectUrl(pages[Number(page.value) - 1]);
      box = Number(page.value) === originalPage && originalBox ? [...originalBox] : null;
      syncInputs();
      renderBox();
      viewport.scrollTop = 0;
      message.textContent = "";
    }
    page.addEventListener("change", loadPage);
    function point(event) {
      const rect = image.getBoundingClientRect();
      return [Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)),
        Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height))];
    }
    canvas.addEventListener("pointerdown", event => {
      if (event.button !== 0) return;
      event.preventDefault();
      const corner = event.target.dataset.corner;
      const start = point(event);
      gesture = { start, initial: box ? [...box] : null, mode: corner || (event.target === rectangle ? "move" : "draw") };
      if (gesture.mode === "draw") box = [start[0], start[1], start[0], start[1]];
      canvas.setPointerCapture(event.pointerId);
      renderBox();
    });
    canvas.addEventListener("pointermove", event => {
      if (!gesture) return;
      const end = point(event);
      const { start, initial, mode } = gesture;
      if (mode === "draw") box = [Math.min(start[0], end[0]), Math.min(start[1], end[1]), Math.max(start[0], end[0]), Math.max(start[1], end[1])];
      else if (mode === "move") {
        const dx = Math.max(-initial[0], Math.min(1 - initial[2], end[0] - start[0]));
        const dy = Math.max(-initial[1], Math.min(1 - initial[3], end[1] - start[1]));
        box = [initial[0] + dx, initial[1] + dy, initial[2] + dx, initial[3] + dy];
      } else {
        const oppositeX = mode.includes("w") ? initial[2] : initial[0];
        const oppositeY = mode.includes("n") ? initial[3] : initial[1];
        box = [Math.min(end[0], oppositeX), Math.min(end[1], oppositeY), Math.max(end[0], oppositeX), Math.max(end[1], oppositeY)];
      }
      syncInputs();
      renderBox();
    });
    const endGesture = () => { gesture = null; };
    canvas.addEventListener("pointerup", endGesture);
    canvas.addEventListener("pointercancel", endGesture);
    coordinates.forEach(input => input.addEventListener("input", () => {
      box = coordinates.every(item => item.value !== "") ? coordinates.map(item => Number(item.value) / 100) : null;
      renderBox();
    }));
    const zoomLabel = el("span", { text: "100%" });
    const changeZoom = amount => {
      zoom = Math.max(1, Math.min(3, zoom + amount));
      canvas.style.width = `${zoom * 100}%`;
      zoomLabel.textContent = `${Math.round(zoom * 100)}%`;
    };
    const toolbar = el("div", { class: "mark-editor-toolbar" },
      el("label", {}, "Page", page),
      el("div", { class: "mark-editor-zoom", role: "group", "aria-label": "Page zoom" },
        button("−", () => changeZoom(-0.5)), zoomLabel, button("+", () => changeZoom(0.5))));
    const precise = el("details", { class: "mark-editor-precise" },
      el("summary", { text: "Adjust coordinates" }),
      el("p", { class: "small muted", text: "Enter the box edges as percentages of the page. Use the arrow keys for fine adjustments." }),
      el("div", { class: "grid2" }, coordinates.map((input, i) =>
        el("label", {}, `${["Left", "Top", "Right", "Bottom"][i]} (%)`, input))));
    const actions = el("div", { class: "mark-editor-actions" },
      button("Cancel", () => dialog.close()),
      button("Use this location", () => {
        if (!box || box.some(v => !Number.isFinite(v) || v < 0 || v > 1) || box[2] - box[0] < .002 || box[3] - box[1] < .002) {
          message.textContent = "Draw a box around the evidence, or enter all four valid coordinates.";
          return;
        }
        const review = reviewResult().review ||= {};
        const evidence = review.evidence ||= { fields: {}, rules: {} };
        (evidence[group] ||= {})[key] = { page: Number(page.value), box: [...box] };
        state.reviewDirty = true;
        dialog.close();
        notify("Location changed. Save or confirm your review to apply it.");
      }, "primary"));
    dialog.append(toolbar, viewport, precise, message, actions);
    dialog.addEventListener("close", () => { dialog.remove(); edit.focus(); }, { once: true });
    document.getElementById("invoice-detail").append(dialog);
    loadPage();
    dialog.showModal();
  }, "link");
  return edit;
}

function findingCard(rule, review, mark, page, pages, basePrompt, readOnly = false) {
  const card = el("li", { class: `finding ${rule.outcome}` });
  const decision = el("div", { class: "finding-outcome" });
  card.append(evidenceHeading(card, rule.name, mark, page, pages), decision);
  const key = rule.rule_id;
  if (readOnly) {
    decision.append(pill(OUTCOME_LABEL[rule.outcome] || rule.outcome, rule.outcome));
    if (rule.message) card.append(el("p", { text: rule.message }));
    if (rule.review_reason && rule.ai_message && rule.ai_message !== rule.message) {
      card.append(el("p", { class: "small muted", text: `Assistant: ${rule.ai_message}` }));
    }
  } else if (key === "DUPLICATE_NUMBER") {
    decision.append(pill(OUTCOME_LABEL[rule.outcome] || rule.outcome, rule.outcome));
    if (rule.message) card.append(el("p", { text: rule.message }));
  } else {
    const automatic = rule.check_outcome || rule.ai_outcome || rule.outcome;
    const assistant = rule.ai_outcome || automatic;
    const aiMessage = rule.ai_message ?? rule.message;
    const options = Object.entries(OUTCOME_LABEL).map(([value, text]) => el("option", { value, text }));
    const select = el("select", { value: rule.outcome, "data-rule": key,
      "aria-label": `Decision for ${rule.name}` }, options);
    // Preserve an explicit legacy choice, even when it matches today's automatic result.
    select.dataset.override = review.rules?.[key] || "";
    decision.append(select);
    card.append(el("p", { class: "finding-original", text:
      `Assistant selected ${OUTCOME_LABEL[assistant] || assistant}${aiMessage ? " · " + aiMessage : ""}` }));
    if (automatic !== assistant || (rule.check_message != null && rule.check_message !== aiMessage)) {
      card.append(el("p", { text: `Current check: ${OUTCOME_LABEL[automatic] || automatic}${rule.check_message ? " · " + rule.check_message : ""}` }));
    }
    const reason = el("textarea", { rows: 2, "data-reason": key, "aria-label": `Your reason for ${rule.name}`,
      value: review.rule_reasons?.[key] || "", placeholder: "Explain your decision for this invoice." });
    const label = el("label", { class: "finding-reason" }, "Your reason", reason);
    const edit = button("Edit reason", () => {
      label.hidden = false;
      edit.hidden = true;
      reason.focus();
    }, "link");
    const reset = button("Reset finding", () => {
      select.value = automatic;
      select.dataset.override = "";
      reason.value = "";
      state.reviewDirty = true;
      update();
      select.focus();
    }, "link");
    reset.dataset.resetFinding = key;
    const update = () => {
      card.classList.remove(...Object.keys(OUTCOME_LABEL));
      card.classList.add(select.value);
      select.className = `finding-decision ${select.value}`;
      const changed = Boolean(select.dataset.override || reason.value);
      const required = select.dataset.override && new Set([automatic, select.value]).size === 2 &&
        [automatic, select.value].every(value => value === "passed" || value === "failed");
      label.firstChild.textContent = required ? "Your reason (required)" : "Your reason";
      reason.required = Boolean(required);
      label.hidden = !changed;
      edit.hidden = changed;
      reset.hidden = !changed;
    };
    select.addEventListener("change", () => {
      select.dataset.override = select.value === automatic ? "" : select.value;
      state.reviewDirty = true;
      update();
    });
    reason.addEventListener("input", () => {
      state.reviewDirty = true;
      reset.hidden = !reason.value && !select.dataset.override;
    });
    update();
    card.append(label, el("div", { class: "action-row small" }, edit, reset));
  }
  card.append(el("div", { class: "action-row small" },
    !readOnly && pages?.length ? editEvidence("rules", key, rule.name, rule.evidence, pages) : null,
    promptButton("Copy question", `Explain the finding "${rule.name}" (rule "${key}") for ${basePrompt}${mark ? ` at mark ${mark.number} on page ${mark.page}` : ""}. Verify the evidence and explain any uncertainty.`)));
  return card;
}

function findingsList(result, marks, pages, basePrompt, readOnly = false) {
  const items = (result.rule_results || []).map(rule => {
    const mark = marks.find(m => m.label === rule.name && m.kind === rule.outcome && (!rule.evidence?.box || (m.page === rule.evidence.page && m.box.join() === rule.evidence.box.join())));
    const page = mark?.page ?? rule.evidence?.page ?? result.visual?.[rule.rule_id]?.page;
    return findingCard(rule, result.review || {}, mark, page, pages, basePrompt, readOnly);
  });
  return el("ul", { class: "findings" }, items.length ? items : [el("li", { class: "empty", text: "No confirmed rules apply to this document type." })]);
}

function valueEditor(field, input, type) {
  const editor = el("label", { hidden: true }, "Value for this invoice", input);
  const edit = button("Edit", () => {
    const title = `Edit ${field.label}`;
    const dialog = el("dialog", { class: "value-edit-dialog", "aria-label": title }, el("h2", { text: title }));
    const correct = button("Correct this invoice’s value", () => {
      dialog.close();
      editor.hidden = false;
      input.focus();
    });
    correct.autofocus = true;
    const instructions = field.id ? el("button", { type: "button", class: "ghost", text: "Edit instructions for future invoices",
      "data-edit-field": field.id, "data-type": type, onclick: () => dialog.close() }) : null;
    dialog.append(el("div", { class: "value-edit-options" }, correct, instructions,
      button("Cancel", () => dialog.close(), "link")));
    dialog.addEventListener("close", () => dialog.remove(), { once: true });
    document.getElementById("invoice-detail").append(dialog);
    edit.focus({ preventScroll: true });
    dialog.showModal();
  }, "link");
  edit.setAttribute("aria-label", `Edit ${field.label}`);
  edit.setAttribute("aria-haspopup", "dialog");
  return el("div", { class: "inline-edit" }, edit, editor);
}

function fieldsTable(result, marks, pages, readOnly = false) {
  const original = (result.ai_original || result).fields || {};
  const previous = result.review?.fields || {};
  const configured = state.config.fields.filter(f => f.type_id === result.type_id);
  const byName = new Map(configured.map(f => [f.name, f]));
  for (const name of Object.keys(original)) if (!byName.has(name)) byName.set(name, { name, label: name });
  const items = [...byName.values()].map(f => {
    const read = original[f.name] || {};
    const corrected = Object.hasOwn(previous, f.name);
    const value = corrected ? previous[f.name] : read.value;
    const located = result.review?.evidence?.fields?.[f.name] || read;
    const mark = marks.find(m => m.label === f.name) || marks.find(m => located.box && m.page === located.page && m.box.join() === located.box.join());
    const input = el("input", { value: value ?? "", "data-field": f.name, "aria-label": `Correct value for ${f.label}`,
      oninput: event => { state.reviewDirty = true; event.target.dataset.changed = "1"; } });
    const card = el("li", { class: "value-card" },
      corrected ? pill("Corrected", "reviewed") : null,
      el("p", { class: "field-value", text: value ?? "No value found" }),
      corrected ? el("p", { class: "small muted", text: `Originally read: ${read.value ?? "No value found"}` }) : null,
      read.status === "uncertain" ? pill("Uncertain", "unclear") : null,
      read.note ? el("p", { class: "small", text: read.note }) : null,
      !readOnly ? valueEditor(f, input, result.type_id) : null,
      !readOnly && pages?.length ? editEvidence("fields", f.name, f.label, (result.review?.evidence?.fields || {})[f.name] || read, pages) : null);
    card.prepend(evidenceHeading(card, f.label, mark, mark?.page ?? located.page, pages));
    return card;
  });
  return el("ul", { class: "findings" }, items.length ? items : [el("li", { class: "empty", text: "No fields configured for this type." })]);
}

function reviewBox(result) {
  const tip = el("textarea", { id: "review-tip", rows: 2, placeholder: "Where should the assistant look next time?",
    oninput: () => { state.reviewDirty = true; } });
  return el("section", { class: "review-box" }, el("h3", { text: "Your review" }),
    el("p", { class: "small", text: "Edits apply to this invoice. Confirm to use your decision in the register." }),
    el("details", {}, el("summary", { text: "Add a project tip for future checks" }), el("label", {}, "This tip will be saved when you save the review.", tip)),
    el("div", { class: "action-row" }, button("Save draft", () => submitReview("draft")),
      button("Confirm review", () => submitReview("confirmed"), "primary")));
}

function viewer(pages, marks, prefix = "invoice", onMark) {
  if (!pages?.length) return el("p", { class: "empty", text: "No page images available." });
  const frames = pages.map((src, i) => {
    const frame = el("div", { class: "viewer" }, el("img", { src: projectUrl(src), alt: `Invoice page ${i + 1}` }));
    for (const mark of (marks || []).filter(m => m.page === i + 1)) {
      const [left, top, right, bottom] = mark.box;
      const label = String(mark.number);
      const number = onMark ? button(label, () => onMark(mark), "mark-number") : el("span", { class: "mark-number", text: label });
      if (onMark) number.setAttribute("aria-label", `Return to the review card for mark ${label} on page ${mark.page}`);
      frame.append(el("div", { id: `${prefix}-mark-${mark.number}`, class: `mark ${mark.kind}`,
        style: `left:${left*100}%;top:${top*100}%;width:${(right-left)*100}%;height:${(bottom-top)*100}%` },
        number));
    }
    return el("figure", { id: `${prefix}-page-${i + 1}` }, el("figcaption", { text: `Page ${i+1} of ${pages.length}` }), frame);
  });
  return el("section", { class: "document-viewer", tabindex: "0", "aria-label": "Invoice evidence pages" }, frames);
}

function collectReview() {
  const result = reviewResult();
  const original = (result.ai_original || result).fields || {};
  const fields = { ...((result.review || {}).fields || {}) };
  for (const input of document.querySelectorAll("#invoice-detail input[data-field]")) {
    const name = input.dataset.field;
    const value = input.value.trim();
    const aiValue = original[name] ? (original[name].value ?? "") : "";
    if (input.dataset.changed || Object.prototype.hasOwnProperty.call(fields, name)) {
      if (String(value) === String(aiValue)) delete fields[name];
      else fields[name] = value === "" ? null : value;
    }
  }
  const rules = {};
  for (const select of document.querySelectorAll("#invoice-detail select[data-rule]")) {
    if (select.dataset.override) rules[select.dataset.rule] = select.dataset.override;
  }
  const rule_reasons = {};
  for (const input of document.querySelectorAll("#invoice-detail textarea[data-reason]")) {
    if (input.value.trim()) rule_reasons[input.dataset.reason] = input.value.trim();
  }
  return { fields, rules, rule_reasons, evidence: result.review?.evidence || {}, note: result.review?.note || "" };
}

async function submitReview(status) {
  const id = state.selected;
  const project = state.current;
  const scope = invoiceScope;
  const tip = document.getElementById("review-tip");
  const current = () => currentInvoiceScope(project, scope) && state.selected === id && tip.isConnected;
  const body = { ...collectReview(), status, revision: state.detail.revision, learning: tip.value };
  if (editingCandidate) body.candidate_revision = state.detail.candidate.revision;
  if (status === "confirmed") {
    const changes = Object.entries(body.fields).map(([key, value]) => `${key} → ${value ?? "empty"}`);
    for (const rule of reviewResult().rule_results || []) {
      const decision = body.rules[rule.rule_id], reason = body.rule_reasons[rule.rule_id];
      if (decision || reason) changes.push(`${rule.name} → ${OUTCOME_LABEL[decision || rule.check_outcome || rule.outcome]}${reason ? " · " + reason : ""}`);
    }
    const note = changes.length ? ` Corrections: ${changes.join(", ")}.` : "";
    if (!(await askConfirm(`Confirm the review for ${id} in project ${project}?${note}${body.learning ? " The tip will also be saved for future checks." : ""}`, "Confirm review"))) return;
  }
  if (!current()) return;
  // Keep the submitted values stable while the server publishes the result and PDF.
  const controls = [...document.querySelectorAll(
    "#invoice-detail select[data-rule], #invoice-detail [data-reason], #invoice-detail [data-reset-finding], #invoice-detail [data-field], #review-tip, #invoice-detail .review-box button")];
  if (controls.some(control => control.disabled)) return;
  // Evidence controls can also change the review. Keep the entire pane stable
  // until the submitted version has been published.
  const reviewPane = document.querySelector("#invoice-detail .review-detail");
  const wasInert = reviewPane?.inert;
  if (reviewPane) reviewPane.inert = true;
  controls.forEach(control => { control.disabled = true; });
  state.reviewDirty = true;
  try {
    await api("POST", `/api/result/${encodeURIComponent(id)}/review`, body, project);
    if (!current()) return;
    state.reviewDirty = false;
    notify(status === "confirmed" ? "Review confirmed and saved." : "Draft saved.");
    editingCandidate = false;
    await loadInvoices();
    if (current() && status === "confirmed") await backToList();
    else if (current()) await selectInvoice(id, true, project);
  } catch (error) {
    if (current()) notify(error.message, true);
  } finally {
    if (reviewPane) reviewPane.inert = wasInert;
    controls.forEach(control => { control.disabled = false; });
  }
}
