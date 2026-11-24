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

export async function loadInvoices() {
  const invoices = await api("GET", "/api/invoices");
  state.invoices = invoices;
  renderInvoiceList();
}

export function displayInvoiceView(showDetail) {
  document.getElementById("invoice-home").hidden = showDetail;
  document.getElementById("invoice-detail").hidden = !showDetail;
}

export async function backToList() {
  if (state.reviewDirty && !(await confirmLeave())) return;
  const id = state.selected;
  Object.assign(state, { selected: null, detail: null, reviewDirty: false });
  state.detailRequest++;
  displayInvoiceView(false);
  await loadInvoices();
  document.querySelector(`[data-invoice-id="${CSS.escape(id)}"]`)?.focus({ preventScroll: true });
  window.scrollTo(0, state.listScroll);
}

export function renderInvoiceList() {
  const pending = state.invoices.filter(i => !i.checked_at);
  document.getElementById("invoice-count").textContent = `${state.invoices.length} total · ${pending.length} awaiting a check`;
  document.getElementById("report-btn").disabled = !state.invoices.some(i => i.checked_at);
  document.getElementById("pending-batch").hidden = !pending.length;
  document.getElementById("pending-summary").textContent = `Check ${pending.length} pending invoice${pending.length === 1 ? "" : "s"}`;
  document.getElementById("pending-files").replaceChildren(...pending.map(i => el("li", { text: i.file })));
  const list = document.getElementById("invoice-list");
  if (!state.invoices.length) {
    list.replaceChildren(el("li", { class: "empty", text: "Add your first invoice to start a check." }));
    return;
  }
  list.replaceChildren(...state.invoices.map(inv => el("li", {},
    el("button", { type: "button", "data-invoice-id": inv.id, onclick: () => selectInvoice(inv.id) },
      el("span", { class: "name", text: inv.file }),
      el("span", { class: "tags" }, pill(STATUS_LABEL[inv.status] || inv.status, inv.status),
        inv.reviewed ? pill("Reviewed", "reviewed") : null,
        inv.pending_recheck ? pill("Recheck awaiting review", "unclear") : null),
      el("span", { class: "chevron", "aria-hidden": true, text: "›" })))));
}

export async function selectInvoice(id, refresh = false) {
  if (id !== state.selected && state.reviewDirty && !(await confirmLeave())) return;
  const request = ++state.detailRequest;
  const current = () => request === state.detailRequest && state.selected === id && state.tab === "invoices";
  if (!refresh) {
    state.listScroll = window.scrollY;
    state.reviewView = "findings";
    state.reviewDirty = false;
    window.scrollTo(0, 0);
  }
  state.selected = id;
  displayInvoiceView(true);
  const detail = document.getElementById("invoice-detail");
  if (!refresh || !state.detail) detail.replaceChildren(button("Back to invoices", backToList), el("p", { class: "empty", text: "Loading invoice…" }));
  try {
    const [data, config] = await Promise.all([api("GET", `/api/result/${encodeURIComponent(id)}`), api("GET", "/api/config")]);
    if (!current() || state.reviewDirty) return;
    state.detail = data;
    state.config = config;
    renderDetail();
  } catch (error) {
    if (current()) detail.replaceChildren(button("Back to invoices", backToList), el("p", { class: "empty", text: error.message }));
  }
}

function confirmedValue(result, name) {
  const changes = result.review?.fields || {};
  return Object.hasOwn(changes, name) ? changes[name] : result.fields?.[name]?.value;
}

function candidatePanel(official, candidate, project, invoiceId) {
  const proposed = candidate.result;
  const differences = [];
  const fieldNames = new Set([...Object.keys(official.fields || {}), ...Object.keys(proposed.fields || {}), ...Object.keys(official.review?.fields || {})]);
  const fieldLabel = name => state.config.fields.find(f => f.name === name && f.type_id === proposed.type_id)?.label || name;
  const add = (label, oldValue, newValue) => {
    if (String(oldValue ?? "") !== String(newValue ?? "")) differences.push([label, oldValue ?? "—", newValue ?? "—"]);
  };
  add("Invoice type", official.type_id, proposed.type_id);
  add("Status", official.status, proposed.status);
  for (const name of fieldNames) add(fieldLabel(name), confirmedValue(official, name), confirmedValue(proposed, name));
  const previous = new Map((official.rule_results || []).map(rule => [rule.rule_id, rule]));
  for (const rule of proposed.rule_results || []) {
    const old = previous.get(rule.rule_id);
    add(rule.name, old ? OUTCOME_LABEL[old.outcome] : null, OUTCOME_LABEL[rule.outcome]);
    previous.delete(rule.rule_id);
  }
  for (const rule of previous.values()) add(rule.name, OUTCOME_LABEL[rule.outcome], null);
  const revision = state.detail.revision;
  const accept = button("Accept and confirm recheck", async () => {
    if (state.reviewDirty) { notify("Save or discard your current edits before accepting the recheck.", true); return; }
    if (!(await askConfirm("Replace the confirmed decision with this recheck? The previous confirmation will be kept in the invoice history.", "Accept recheck"))) return;
    accept.disabled = true;
    try {
      await api("POST", `/api/result/${encodeURIComponent(invoiceId)}/accept-recheck`, { revision, candidate_revision: candidate.revision }, project);
      notify("Recheck accepted. Exports now use the new confirmation.");
      if (state.selected === invoiceId) await selectInvoice(invoiceId, true);
      await loadInvoices();
    } catch (error) { notify(error.message, true); } finally { accept.disabled = false; }
  }, "primary");
  return el("section", { class: "candidate-panel" }, el("h3", { text: "Recheck awaiting review" }),
    el("p", { text: "Exports continue to use the confirmed decision until you accept this recheck." }),
    differences.length ? el("div", { class: "table-wrap" }, el("table", { class: "plain" },
      el("thead", {}, el("tr", {}, ["Change", "Confirmed", "Recheck"].map(t => el("th", { text: t })))),
      el("tbody", {}, differences.map(row => el("tr", {}, row.map(value => el("td", { text: String(value) }))))))) :
      el("p", { text: "The document type, values, status and rule decisions match the confirmation." }),
    el("details", {}, el("summary", { text: "Inspect recheck evidence and explanations" }),
      proposed.summary ? el("p", { text: proposed.summary }) : null,
      proposed.type_reason ? el("p", { text: proposed.type_reason }) : null,
      (proposed.questions || []).map(q => el("p", { text: q })),
      el("ul", {}, (proposed.rule_results || []).map(r => el("li", { text: `${r.name} · ${OUTCOME_LABEL[r.outcome] || r.outcome}${r.message ? " — " + r.message : ""}` }))),
      viewer(state.detail.pages, candidate.marks || [], "recheck")),
    accept);
}

function renderDetail() {
  const { result, pages, marks, candidate, confirmed_row } = state.detail;
  const id = state.selected, project = state.current;
  const invoice = state.invoices.find(i => i.id === id);
  const projectName = state.projects.find(p => p.slug === project)?.name || project;
  const basePrompt = `invoice "${id}" in project "${project}"`;
  const actions = el("div", { class: "action-row" },
    promptButton(result ? "Copy recheck request" : "Copy check request",
      `${result ? "Recheck" : "Check"} ${basePrompt} against this project's confirmed rules.`));
  if (result) {
    const marked = state.detail.marked_pdf_url;
    if (marked) actions.append(el("a", { class: "ghost-link", href: projectUrl(marked, project), text: "Download marked PDF" }));
    if (confirmed_row) actions.append(button("Copy confirmed row", () => {
      const line = confirmed_row.map(v => String(v ?? "").replace(/[\t\r\n]+/g, " ")).join("\t");
      copyText(line, "Confirmed row copied in workbook column order.");
    }));
  }
  const header = el("header", { class: "invoice-header" },
    button("‹ Back to invoices", backToList, "link"), el("p", { class: "project-name", text: projectName }),
    el("h1", { text: invoice?.file || id }), actions);
  const container = document.getElementById("invoice-detail");
  if (!result) {
    container.replaceChildren(header, el("p", { text: "Paste the check request into your project chat. The findings will appear here." }), viewer(pages, []));
    return;
  }
  const type = state.config.invoice_types.find(t => t.id === result.type_id)?.name || result.type_id;
  const count = result.rules_checked ?? (result.rule_results || []).filter(r => r.rule_id !== "DUPLICATE_NUMBER").length;
  const summary = el("section", { class: "review-summary" },
    el("div", { class: "tags" }, pill(STATUS_LABEL[result.status] || result.status, result.status),
      pill(result.review?.status === "confirmed" ? "Reviewed" : "Awaiting confirmation", ""),
      el("span", { class: "muted", text: `${count} rule${count === 1 ? "" : "s"} checked` })),
    el("p", {}, el("b", { text: type }), result.type_reason ? ` · ${result.type_reason}` : ""),
    result.summary ? el("p", { text: result.summary }) : null,
    result.questions?.length ? el("div", { class: "questions" }, el("b", { text: "Questions from the check" }),
      el("ul", {}, result.questions.map(q => el("li", { text: q })))) : null);
  const findings = findingsList(result, marks, basePrompt);
  const values = fieldsTable(result, marks);
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
  const review = el("div", { class: "review-detail" },
    el("div", { class: "view-tabs", role: "group", "aria-label": "Review content" }, findingsButton, valuesButton),
    findings, values, reviewBox(result));
  container.replaceChildren(header, summary,
    ...(candidate ? [candidatePanel(result, candidate, project, id)] : []),
    el("div", { class: "detail-grid" }, review, viewer(pages, marks)));
}

function evidenceControl(mark) {
  if (!mark) return el("span", { class: "small muted", text: "No evidence marked" });
  const link = button(`Show mark ${mark.number} · page ${mark.page}`, () => {
    const target = document.getElementById(`invoice-mark-${mark.number}`);
    if (!target) return;
    for (const box of document.querySelectorAll(".mark.hilite")) box.classList.remove("hilite");
    target.classList.add("hilite");
    target.scrollIntoView({ block: "center", inline: "nearest" });
    document.querySelectorAll(".evidence-select[aria-pressed=true]").forEach(b => b.setAttribute("aria-pressed", "false"));
    link.setAttribute("aria-pressed", "true");
  }, "evidence-select");
  link.setAttribute("aria-pressed", "false");
  return link;
}

function editControl(label, input, caption) {
  const wrapper = el("div", { class: "inline-edit" });
  const control = button(label, () => {
    editor.hidden = !editor.hidden;
    control.setAttribute("aria-expanded", String(!editor.hidden));
    if (!editor.hidden) input.focus();
  }, "link");
  const editor = el("label", { hidden: true }, caption, input);
  control.setAttribute("aria-expanded", "false");
  wrapper.append(control, editor);
  return wrapper;
}

function findingsList(result, marks, basePrompt) {
  const overrides = result.review?.rules || {};
  const items = (result.rule_results || []).map(r => {
    const mark = marks.find(m => m.label === r.name && m.kind === r.outcome && (!r.evidence?.box || (m.page === r.evidence.page && m.box.join() === r.evidence.box.join())));
    const select = el("select", { "aria-label": `Decision for ${r.name}`, "data-rule": r.rule_id, onchange: () => { state.reviewDirty = true; } },
      el("option", { value: "", text: `Use assistant decision (${OUTCOME_LABEL[r.ai_outcome || r.outcome] || r.outcome})` }),
      el("option", { value: "passed", text: "Passed" }), el("option", { value: "failed", text: "Failed" }));
    select.value = overrides[r.rule_id] || "";
    return el("li", { class: `finding ${r.outcome}` },
      el("div", { class: "top" }, el("b", { text: r.name }), pill(OUTCOME_LABEL[r.outcome] || r.outcome, r.outcome)),
      r.message ? el("p", { text: r.message }) : null,
      r.overridden ? el("p", { class: "small", text: "Changed by reviewer" }) : null,
      el("div", { class: "action-row small" }, evidenceControl(mark),
        promptButton("Copy question", `Explain the finding "${r.name}" (rule "${r.rule_id}") for ${basePrompt}${mark ? ` at mark ${mark.number} on page ${mark.page}` : ""}. Verify the evidence and explain any uncertainty.`)),
      r.rule_id === "DUPLICATE_NUMBER" ? null : editControl("Change decision", select, "Decision for this invoice"));
  });
  return el("ul", { class: "findings" }, items.length ? items : [el("li", { class: "empty", text: "No confirmed rules apply to this document type." })]);
}

function fieldsTable(result, marks) {
  const original = (result.ai_original || result).fields || {};
  const previous = result.review?.fields || {};
  const configured = state.config.fields.filter(f => f.type_id === result.type_id);
  const byName = new Map(configured.map(f => [f.name, f]));
  for (const name of Object.keys(original)) if (!byName.has(name)) byName.set(name, { name, label: name });
  const items = [...byName.values()].map(f => {
    const read = original[f.name] || {};
    const corrected = Object.hasOwn(previous, f.name);
    const value = corrected ? previous[f.name] : read.value;
    const mark = marks.find(m => m.label === f.name) || marks.find(m => read.box && m.page === read.page && m.box.join() === read.box.join());
    const input = el("input", { value: value ?? "", "data-field": f.name, "aria-label": `Correct value for ${f.label}`,
      oninput: event => { state.reviewDirty = true; event.target.dataset.changed = "1"; } });
    return el("li", { class: "value-card" },
      el("div", { class: "top" }, el("b", { text: f.label }), corrected ? pill("Corrected", "reviewed") : null),
      el("p", { class: "field-value", text: value ?? "No value found" }),
      corrected ? el("p", { class: "small muted", text: `Originally read: ${read.value ?? "No value found"}` }) : null,
      read.status === "uncertain" ? pill("Uncertain", "unclear") : null,
      read.note ? el("p", { class: "small", text: read.note }) : null,
      evidenceControl(mark), editControl("Edit value", input, "Value for this invoice"),
      f.id ? el("button", { type: "button", class: "link", text: "Edit project field instructions",
        "data-edit-field": f.id, "data-type": result.type_id }) : null);
  });
  return el("ul", { class: "findings" }, items.length ? items : [el("li", { class: "empty", text: "No fields configured for this type." })]);
}

function reviewBox(result) {
  const tip = el("textarea", { id: "review-tip", rows: 2, placeholder: "Where should the assistant look next time?",
    oninput: () => { state.reviewDirty = true; } });
  return el("section", { class: "review-box" }, el("h3", { text: "Your review" }),
    el("p", { class: "small", text: "Edits apply to this invoice. Confirm to use your decision in the register." }),
    el("details", {}, el("summary", { text: "Add a project tip for future checks" }), el("label", {}, "This tip will be saved when you save the review.", tip)),
    el("div", { class: "action-row" }, result.review?.status === "confirmed" ? null : button("Save draft", () => submitReview("draft")),
      button("Confirm review", () => submitReview("confirmed"), "primary")));
}

function viewer(pages, marks, prefix = "invoice") {
  if (!pages?.length) return el("p", { class: "empty", text: "No page images available." });
  const frames = pages.map((src, i) => {
    const frame = el("div", { class: "viewer" }, el("img", { src: projectUrl(src), alt: `Invoice page ${i + 1}` }));
    for (const mark of (marks || []).filter(m => m.page === i + 1)) {
      const [left, top, right, bottom] = mark.box;
      frame.append(el("div", { id: `${prefix}-mark-${mark.number}`, class: `mark ${mark.kind}`,
        style: `left:${left*100}%;top:${top*100}%;width:${(right-left)*100}%;height:${(bottom-top)*100}%` },
        el("span", { text: String(mark.number) })));
    }
    return el("figure", {}, el("figcaption", { text: `Page ${i+1} of ${pages.length}` }), frame);
  });
  return el("section", { class: "document-viewer", tabindex: "0", "aria-label": "Invoice evidence pages" }, frames);
}

function collectReview() {
  const result = state.detail.result;
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
    if (select.value) rules[select.dataset.rule] = select.value;
  }
  return { fields, rules };
}

async function submitReview(status) {
  const id = state.selected;
  const project = state.current;
  const body = { ...collectReview(), status, revision: state.detail.revision, learning: document.getElementById("review-tip").value };
  if (status === "confirmed") {
    const changes = [...Object.entries(body.fields).map(([key, value]) => `${key} → ${value ?? "empty"}`), ...Object.entries(body.rules).map(([key, value]) => `${key} → ${value}`)];
    const note = changes.length ? ` Corrections: ${changes.join(", ")}.` : "";
    if (!(await askConfirm(`Confirm the review for ${id} in project ${project}?${note}${body.learning ? " The tip will also be saved for future checks." : ""}`, "Confirm review"))) return;
  }
  try {
    await api("POST", `/api/result/${encodeURIComponent(id)}/review`, body, project);
    if (state.selected !== id || state.current !== project) return;
    state.reviewDirty = false;
    notify(status === "confirmed" ? "Review confirmed and saved." : "Draft saved.");
    await loadInvoices();
    await selectInvoice(id, true);
  } catch (error) { notify(error.message, true); }
}
