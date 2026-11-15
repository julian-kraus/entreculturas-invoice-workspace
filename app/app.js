"use strict";

const state = {
  tab: "invoices",
  current: null,
  projects: [],
  invoices: [],
  selected: null,
  detail: null,
  page: 1,
  reviewDirty: false,
  config: null,
  draft: null,
  setupSub: "rules",
  setupDirty: false,
  typeFilter: "",
  statusFilter: "all",
};

const STATUS_LABEL = {
  "passes": "Passes",
  "fails rules": "Fails rules",
  "needs a look": "Needs a look",
  "not checked": "Not checked yet",
};
const OUTCOME_LABEL = { passed: "Passed", failed: "Failed", unclear: "Unclear", not_applicable: "Does not apply" };
const CHECK_LABEL = {
  visual: "Judged by looking at the document",
  required: "Value must be present",
  date_in_period: "Date inside the project period",
  range: "Number within a range",
  enum: "One of a list of values",
  regex: "Follows a pattern",
};

// ---------- helpers ----------
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key === "value") node.value = value;
    else if (key === "checked") node.checked = Boolean(value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

async function api(method, path, body) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

let noticeTimer = null;
function notify(message, isError = false) {
  const box = document.getElementById("notice");
  box.textContent = message;
  box.className = isError ? "notice error" : "notice";
  box.hidden = false;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => { box.hidden = true; }, isError ? 9000 : 4000);
}

function pill(text, kind) {
  return el("span", { class: `pill ${String(kind || "").replace(/\s+/g, "-")}`, text });
}

function when(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function clone(value) { return JSON.parse(JSON.stringify(value)); }

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error(`Could not read ${file.name}`));
    reader.readAsDataURL(file);
  });
}

function askConfirm(message, yesLabel = "Leave without saving") {
  const dialog = document.getElementById("confirm-dialog");
  document.getElementById("confirm-text").textContent = message;
  document.getElementById("confirm-yes").textContent = yesLabel;
  return new Promise((resolve) => {
    const finish = (answer) => { dialog.close(); resolve(answer); };
    document.getElementById("confirm-yes").onclick = () => finish(true);
    document.getElementById("confirm-no").onclick = () => finish(false);
    dialog.oncancel = () => resolve(false);
    dialog.showModal();
  });
}

async function confirmLeave() {
  if (state.setupDirty || state.reviewDirty) return askConfirm("You have unsaved changes. Leave without saving?");
  return true;
}

// ---------- projects ----------
async function loadState() {
  const data = await api("GET", "/api/state");
  state.current = data.current;
  state.projects = data.projects;
  const select = document.getElementById("project-select");
  select.replaceChildren(
    ...(data.current ? [] : [el("option", { value: "", text: "Choose a project" })]),
    ...data.projects.map((p) => el("option", { value: p.slug, text: `${p.name} (${p.invoices} invoices)` })),
  );
  select.value = data.current || "";
  const copy = document.getElementById("new-project-copy");
  copy.replaceChildren(el("option", { value: "", text: "Nothing, start empty" }),
    ...data.projects.map((p) => el("option", { value: p.slug, text: p.name })));
}

async function switchProject(slug) {
  if (!slug || slug === state.current) return;
  if (!(await confirmLeave())) { document.getElementById("project-select").value = state.current || ""; return; }
  await api("POST", "/api/project/switch", { slug });
  Object.assign(state, { selected: null, detail: null, config: null, draft: null, setupDirty: false, reviewDirty: false });
  await loadState();
  await showTab(state.tab, true);
  notify("Project switched.");
}

// ---------- tabs ----------
async function showTab(tab, force = false) {
  if (!force && tab !== state.tab && !(await confirmLeave())) return;
  if (tab !== state.tab) { state.setupDirty = false; state.reviewDirty = false; }
  state.tab = tab;
  for (const button of document.querySelectorAll(".tabs button")) {
    button.setAttribute("aria-selected", String(button.dataset.tab === tab));
  }
  for (const name of ["invoices", "setup", "tests", "history", "settings"]) {
    document.getElementById(`panel-${name}`).hidden = name !== tab;
  }
  if (tab === "settings") { await loadSettings(); return; }
  if (!state.current) {
    document.getElementById(`panel-${tab}`).replaceChildren(
      el("p", { class: "empty", text: "Choose a project at the top, or create a new one." }));
    return;
  }
  if (tab === "invoices") { await loadInvoices(); if (state.selected) await selectInvoice(state.selected, true); }
  if (tab === "setup") await loadSetup();
  if (tab === "tests") await loadTests();
  if (tab === "history") await loadHistory();
}

// ---------- invoices ----------
async function loadInvoices() {
  state.invoices = await api("GET", "/api/invoices");
  renderInvoiceList();
}

function renderInvoiceList() {
  const list = document.getElementById("invoice-list");
  if (!state.invoices.length) {
    list.replaceChildren(el("li", { class: "muted small", text: "No invoices yet." }));
    return;
  }
  list.replaceChildren(...state.invoices.map((inv) => el("li", {},
    el("button", { type: "button", class: inv.id === state.selected ? "active" : "", onclick: () => selectInvoice(inv.id) },
      el("span", { class: "name", text: inv.file }),
      el("span", { class: "tags" },
        pill(STATUS_LABEL[inv.status] || inv.status, inv.status),
        inv.reviewed ? pill("Reviewed", "passes") : null,
        inv.test_invoice ? pill("Test invoice", "") : null),
    ))));
}

async function selectInvoice(id, keepPage = false) {
  if (id !== state.selected && state.reviewDirty && !(await askConfirm("Your review is not saved. Leave it?", "Leave without saving"))) return;
  if (id !== state.selected) { state.reviewDirty = false; if (!keepPage) state.page = 1; }
  state.selected = id;
  renderInvoiceList();
  const detail = document.getElementById("invoice-detail");
  detail.replaceChildren(el("p", { class: "empty", text: "Loading…" }));
  try {
    state.detail = await api("GET", `/api/result/${encodeURIComponent(id)}`);
  } catch (error) {
    detail.replaceChildren(el("p", { class: "empty", text: error.message }));
    return;
  }
  if (!state.config) state.config = await api("GET", "/api/config");
  renderDetail();
}

function markNumberFor(label, kind) {
  const mark = (state.detail.marks || []).find((m) => m.label === label && (!kind || m.kind === kind));
  return mark ? mark.number : null;
}

function renderDetail() {
  const { result, pages } = state.detail;
  const invoice = state.invoices.find((i) => i.id === state.selected) || {};
  const container = document.getElementById("invoice-detail");
  const head = el("div", { class: "detail-head" },
    el("h2", { text: invoice.file || state.selected }),
    pill(STATUS_LABEL[result ? result.status : "not checked"] || "", result ? result.status : "not checked"));
  if (!result) {
    container.replaceChildren(head,
      el("p", { text: "This invoice has not been checked yet. Ask in the chat: “Check the new invoices”." }),
      viewer(pages, []));
    return;
  }
  const typeName = (state.config.invoice_types.find((t) => t.id === result.type_id) || {}).name || result.type_id;
  const review = result.review || {};
  const parts = [head,
    el("p", { class: "muted small", text: `Type: ${typeName} · checked ${when(result.checked_at)}${review.status === "confirmed" ? ` · review confirmed ${when(review.at)}` : ""}` }),
    result.summary ? el("p", { text: result.summary }) : null];
  if ((result.questions || []).length) {
    parts.push(el("div", { class: "questions" }, el("b", { text: "Questions from the check" }),
      el("ul", {}, result.questions.map((q) => el("li", { text: q })))));
  }
  const left = el("div", {}, el("h3", { text: "Findings" }), findingsList(result));
  const right = el("div", {}, el("h3", { text: "Invoice" }), el("div", { id: "viewer-slot" }, viewer(pages, state.detail.marks || [])),
    el("p", { class: "small" }, el("a", { href: `/files/projects/${state.current}/results/marked/${state.selected}-marked.pdf?download=1`, text: "Download marked PDF" })));
  parts.push(el("div", { class: "detail-grid" }, left, right),
    el("h3", { text: "Values read from the invoice", style: "margin-top:18px" }), fieldsTable(result), reviewBox(result, invoice));
  container.replaceChildren(...parts);
}

function findingsList(result) {
  const overrides = (result.review || {}).rules || {};
  const items = (result.rule_results || []).map((o) => {
    const number = markNumberFor(o.name, o.outcome);
    const select = el("select", {
      "aria-label": `Your decision for ${o.name}`,
      onchange: (event) => { state.reviewDirty = true; event.target.dataset.changed = "1"; },
      "data-rule": o.rule_id,
    },
    el("option", { value: "", text: "Keep" }),
    el("option", { value: "passed", text: "Mark as passed" }),
    el("option", { value: "failed", text: "Mark as failed" }));
    select.value = overrides[o.rule_id] || "";
    return el("li", { class: `finding ${o.outcome}`,
      onmouseenter: () => highlight(number), onmouseleave: () => highlight(null) },
    el("div", { class: "top" },
      el("span", {}, number ? el("span", { class: "num", text: String(number) }) : null, " ", el("b", { text: o.name })),
      el("span", {}, pill(OUTCOME_LABEL[o.outcome] || o.outcome, o.outcome), o.overridden ? pill("changed by reviewer", "") : null)),
    o.message ? el("p", { text: o.message }) : null,
    o.rule_id === "DUPLICATE_NUMBER" ? null : el("div", { class: "row-end small" }, select));
  });
  return el("ul", { class: "findings" }, items.length ? items : [el("li", { class: "muted", text: "No confirmed rules apply to this invoice type yet." })]);
}

function fieldsTable(result) {
  const fieldsConfig = state.config.fields.filter((f) => f.type_id === result.type_id);
  const corrections = (result.review || {}).fields || {};
  const original = (result.ai_original || result).fields || {};
  const rows = fieldsConfig.map((f) => {
    const read = original[f.name] || {};
    const corrected = Object.prototype.hasOwnProperty.call(corrections, f.name);
    const number = markNumberFor(f.name);
    const input = el("input", {
      value: corrected ? corrections[f.name] ?? "" : read.value ?? "",
      "data-field": f.name, "aria-label": `Correct value for ${f.label}`,
      oninput: (event) => { state.reviewDirty = true; event.target.dataset.changed = "1"; },
    });
    const status = read.status === "uncertain" ? pill("uncertain", "unclear") : read.status === "not_found" ? pill("not found", "") : null;
    const hintBox = el("div", { class: "hint-edit", hidden: true },
      el("label", { class: "small muted" }, "How to find this value on future invoices",
        el("textarea", { value: f.hint || "", "aria-label": `How to find ${f.label}` })),
      el("div", { class: "row-end" }, el("button", { type: "button", class: "primary", onclick: (e) => saveFieldHint(f.id, e.target.closest(".hint-edit").querySelector("textarea").value) }, "Save description")));
    return el("tr", { class: corrected ? "corrected" : "", onmouseenter: () => highlight(number), onmouseleave: () => highlight(null) },
      el("td", {}, number ? el("span", { class: "num", text: String(number) }) : null, " ", f.label, f.required ? " *" : "",
        el("div", {}, el("button", { type: "button", class: "link", onclick: () => { hintBox.hidden = !hintBox.hidden; } }, "Change how this is read"))),
      el("td", {}, el("div", { text: read.value ?? "—" }), status, read.note ? el("div", { class: "muted small", text: read.note }) : null, hintBox),
      el("td", {}, input));
  });
  return el("table", { class: "fields" },
    el("thead", {}, el("tr", {}, el("th", { text: "Field" }), el("th", { text: "Read by the assistant" }), el("th", { text: "Correct value" }))),
    el("tbody", {}, rows));
}

async function saveFieldHint(fieldId, hint) {
  try {
    const config = await api("GET", "/api/config");
    const field = config.fields.find((f) => f.id === fieldId);
    if (!field) throw new Error("This field no longer exists.");
    field.hint = hint.trim();
    await api("PUT", "/api/config/fields", { value: config.fields });
    state.config = config;
    notify("Saved. The next check uses the new description. Run the test invoices to see whether it helps.");
  } catch (error) { notify(error.message, true); }
}

function reviewBox(result, invoice) {
  const tip = el("textarea", { id: "review-tip", placeholder: "Optional tip for next time, e.g. “In this office the amount is handwritten below the table.”", oninput: () => { state.reviewDirty = true; } });
  const aside = el("input", { type: "checkbox", id: "test-aside" });
  const confirmed = (result.review || {}).status === "confirmed";
  return el("div", { class: "review-box" },
    el("h3", { text: "Your review" }),
    el("p", { class: "small muted", text: "Correct any value or decision above, then confirm. Corrections are saved with the history, and the rules are applied again." }),
    tip,
    el("div", { class: "row-end" },
      el("button", { type: "button", class: "ghost", onclick: () => submitReview("draft") }, "Save draft"),
      el("button", { type: "button", class: "primary", onclick: () => submitReview("confirmed") }, "Confirm review")),
    el("div", { class: "row-end small" },
      invoice.test_invoice ? el("span", { class: "muted", text: "This is a test invoice." }) : [
        el("label", {}, aside, " keep aside (never used to make changes)"),
        el("button", { type: "button", class: "ghost", disabled: !confirmed, title: confirmed ? "" : "Confirm the review first",
          onclick: () => addTestInvoice(aside.checked) }, "Add to test invoices")]));
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
  const body = { ...collectReview(), status, learning: (document.getElementById("review-tip") || {}).value || "" };
  try {
    await api("POST", `/api/result/${encodeURIComponent(state.selected)}/review`, body);
    state.reviewDirty = false;
    notify(status === "confirmed" ? "Review confirmed and saved." : "Draft saved.");
    await loadInvoices();
    await selectInvoice(state.selected, true);
  } catch (error) { notify(error.message, true); }
}

async function addTestInvoice(aside) {
  try {
    await api("POST", `/api/evaluation/add/${encodeURIComponent(state.selected)}`, { aside });
    notify("Added to the test invoices.");
    await loadInvoices();
    renderDetail();
  } catch (error) { notify(error.message, true); }
}

function viewer(pages, marks) {
  if (!pages.length) return el("p", { class: "muted", text: "No page images." });
  if (state.page > pages.length) state.page = 1;
  const nav = el("div", { class: "page-nav" },
    pages.length > 1 ? pages.map((_, i) => el("button", { type: "button", class: i + 1 === state.page ? "primary" : "ghost",
      onclick: () => { state.page = i + 1; renderViewer(); } }, `Page ${i + 1}`)) : null);
  const frame = el("div", { class: "viewer" }, el("img", { src: pages[state.page - 1], alt: `Page ${state.page} of the invoice` }));
  for (const mark of marks.filter((m) => m.page === state.page)) {
    const [x0, y0, x1, y1] = mark.box;
    frame.append(el("div", { class: `mark ${mark.kind}`, "data-number": String(mark.number),
      style: `left:${x0 * 100}%;top:${y0 * 100}%;width:${(x1 - x0) * 100}%;height:${(y1 - y0) * 100}%` },
    el("span", { text: String(mark.number) })));
  }
  return el("div", {}, nav, frame);
}

function renderViewer() {
  const slot = document.getElementById("viewer-slot");
  if (slot) slot.replaceChildren(viewer(state.detail.pages, state.detail.marks || []));
}

function highlight(number) {
  if (number !== null) {
    const mark = (state.detail.marks || []).find((m) => m.number === number);
    if (mark && mark.page !== state.page) { state.page = mark.page; renderViewer(); }
  }
  for (const mark of document.querySelectorAll(".mark")) {
    mark.classList.toggle("hilite", number !== null && mark.dataset.number === String(number));
  }
}

async function uploadFiles(files, endpoint) {
  let added = 0;
  for (const file of files) {
    try {
      const data = await readFileAsDataUrl(file);
      await api("POST", endpoint, { name: file.name, data });
      added += 1;
    } catch (error) { notify(`${file.name}: ${error.message}`, true); }
  }
  return added;
}

// ---------- setup ----------
async function loadSetup() {
  await loadProposals();
  state.config = await api("GET", "/api/config");
  state.draft = clone(state.config);
  state.setupDirty = false;
  renderSetup();
}

function markDirty() {
  state.setupDirty = true;
  const flag = document.getElementById("dirty-flag");
  if (flag) flag.textContent = "Unsaved changes";
}

function bind(object, key, input, transform = (v) => v) {
  input.addEventListener(input.type === "checkbox" ? "change" : "input", () => {
    object[key] = transform(input.type === "checkbox" ? input.checked : input.value);
    markDirty();
  });
  return input;
}

function typeOptions(withAll, allLabel = "All types") {
  return [withAll ? el("option", { value: "", text: allLabel }) : null,
    ...state.draft.invoice_types.map((t) => el("option", { value: t.id, text: t.name }))];
}

function saveBar(parts) {
  return el("div", { class: "savebar" },
    el("span", { id: "dirty-flag", class: "dirty", text: state.setupDirty ? "Unsaved changes" : "" }),
    el("button", { type: "button", class: "ghost", onclick: async () => { if (await confirmLeave()) await loadSetup(); } }, "Discard"),
    el("button", { type: "button", class: "primary", onclick: () => saveSetup(parts) }, "Save changes"));
}

async function saveSetup(parts) {
  try {
    let changes = 0;
    for (const part of parts) {
      const response = await api("PUT", `/api/config/${part}`, { value: state.draft[part] });
      changes += response.changes;
    }
    state.setupDirty = false;
    notify(changes ? `Saved ${changes} change${changes === 1 ? "" : "s"}. They are in the history.` : "Nothing changed.");
    await loadSetup();
  } catch (error) { notify(error.message, true); }
}

function renderSetup() {
  for (const button of document.querySelectorAll(".subtabs button")) {
    button.classList.toggle("active", button.dataset.sub === state.setupSub);
  }
  const body = document.getElementById("setup-body");
  const views = { rules: rulesView, types: typesView, fields: fieldsView, learnings: learningsView, project: projectView };
  body.replaceChildren(views[state.setupSub]());
}

function filterBar(withStatus) {
  const type = el("select", { "aria-label": "Invoice type", onchange: (e) => { state.typeFilter = e.target.value; renderSetup(); } }, typeOptions(true));
  type.value = state.typeFilter;
  const parts = [el("label", {}, "Invoice type ", type)];
  if (withStatus) {
    const status = el("select", { "aria-label": "Status", onchange: (e) => { state.statusFilter = e.target.value; renderSetup(); } },
      el("option", { value: "all", text: "All" }), el("option", { value: "confirmed", text: "Confirmed" }),
      el("option", { value: "proposed", text: "Proposed" }), el("option", { value: "rejected", text: "Rejected" }));
    status.value = state.statusFilter;
    parts.push(el("label", {}, "Status ", status));
  }
  return el("div", { class: "toolbar" }, parts);
}

function rulesView() {
  const guidelinesInput = el("input", { type: "file", accept: ".pdf,.txt,.md", multiple: true, hidden: true,
    onchange: async (e) => { const n = await uploadFiles(e.target.files, "/api/guidelines/upload"); if (n) { notify(`Added ${n} guideline file(s). Ask in the chat: “Propose rules from the guidelines”.`); await loadSetup(); } } });
  const guidelines = el("div", { class: "guidelines" },
    el("h3", { text: "Funder guidelines" }),
    state.draft.guidelines.length ? el("p", { class: "small", text: state.draft.guidelines.join(" · ") }) : el("p", { class: "small muted", text: "No guidelines added yet." }),
    el("div", { class: "row-end" }, el("span", { class: "small muted", text: "After adding, ask in the chat: “Propose rules from the guidelines”." }),
      el("label", { class: "ghost", style: "border:1px solid var(--line);border-radius:6px;padding:6px 12px;cursor:pointer" }, guidelinesInput, "Add guidelines")));
  const fieldNames = (typeId) => state.draft.fields.filter((f) => typeId === "ALL" || f.type_id === typeId);
  const rules = state.draft.rules.filter((r) =>
    (!state.typeFilter || r.type_id === state.typeFilter || r.type_id === "ALL") &&
    (state.statusFilter === "all" || r.status === state.statusFilter));
  const cards = rules.map((rule) => {
    const statusButtons = el("div", { class: "status-buttons", role: "group", "aria-label": "Status" },
      ["confirmed", "proposed", "rejected"].map((s) => el("button", { type: "button", class: rule.status === s ? "on" : "",
        onclick: () => { rule.status = s; markDirty(); renderSetup(); } }, { confirmed: "Confirmed", proposed: "Proposed", rejected: "Rejected" }[s])));
    const check = bind(rule, "check", el("select", {}, Object.entries(CHECK_LABEL).map(([v, t]) => el("option", { value: v, text: t }))));
    check.value = rule.check;
    check.addEventListener("change", () => renderSetup());
    const severity = bind(rule, "severity", el("select", {}, el("option", { value: "error", text: "Error: fails the invoice" }), el("option", { value: "warning", text: "Warning: needs a look" })));
    severity.value = rule.severity;
    const typeSelect = bind(rule, "type_id", el("select", {}, el("option", { value: "ALL", text: "Every invoice type" }), typeOptions(false)));
    typeSelect.value = rule.type_id;
    const grid = el("div", { class: "grid2" },
      el("label", {}, "Invoice type", typeSelect),
      el("label", {}, "How it is checked", check),
      el("label", {}, "If it fails", severity));
    if (rule.check !== "visual") {
      const field = bind(rule, "field", el("select", {}, el("option", { value: "", text: "Choose a field" }),
        fieldNames(rule.type_id).map((f) => el("option", { value: f.name, text: `${f.label} (${f.name})` }))));
      field.value = rule.field || "";
      grid.append(el("label", {}, "Field", field));
      if (["range", "enum", "regex"].includes(rule.check)) {
        grid.append(el("label", {}, { range: "Range (min,max)", enum: "Allowed values (comma separated)", regex: "Pattern" }[rule.check],
          bind(rule, "value", el("input", { value: rule.value || "" }))));
      }
    }
    return el("div", { class: `card ${rule.status}` },
      el("div", { class: "head" }, el("span", {}, el("b", { text: rule.name || rule.id }), " ", el("span", { class: "muted small", text: rule.id })), statusButtons),
      el("label", {}, "Name", bind(rule, "name", el("input", { value: rule.name || "" }))),
      el("label", {}, "What the rule requires", bind(rule, "description", el("textarea", { value: rule.description || "" }))),
      el("label", {}, "Where to look (helps the assistant)", bind(rule, "hint", el("textarea", { value: rule.hint || "" }))),
      grid,
      rule.reason ? el("p", { class: "small muted", text: `Why the assistant proposed it: ${rule.reason}` }) : null,
      el("label", {}, "Source (document and page)", bind(rule, "source", el("input", { value: rule.source || "" }))),
      el("label", { style: "display:flex;gap:6px;align-items:center;color:var(--ink)" }, bind(rule, "enabled", el("input", { type: "checkbox", checked: rule.enabled !== false })), "In use"));
  });
  const addButton = el("button", { type: "button", class: "ghost", onclick: () => {
    let n = 1; const ids = new Set(state.draft.rules.map((r) => r.id));
    while (ids.has(`M${String(n).padStart(3, "0")}`)) n += 1;
    state.draft.rules.unshift({ id: `M${String(n).padStart(3, "0")}`, type_id: state.typeFilter || "ALL", name: "New rule", check: "visual",
      field: null, value: "", severity: "error", description: "", hint: "", source: "", status: "proposed", enabled: true });
    state.statusFilter = "all"; markDirty(); renderSetup();
  } }, "Add a rule");
  const counts = ["confirmed", "proposed", "rejected"].map((s) => `${state.draft.rules.filter((r) => r.status === s).length} ${s}`).join(" · ");
  return el("div", {}, guidelines, el("div", { class: "toolbar" }, filterBar(true), el("span", { class: "muted small", text: counts }), addButton),
    el("p", { class: "small muted", text: "Only confirmed rules are applied when invoices are checked." }),
    el("div", { class: "cards" }, cards.length ? cards : el("p", { class: "muted", text: "No rules match." })), saveBar(["rules"]));
}

function typesView() {
  const cards = state.draft.invoice_types.map((t) => el("div", { class: "card" },
    el("div", { class: "head" }, el("b", { text: t.name }), el("span", { class: "muted small", text: t.id })),
    el("div", { class: "grid2" },
      el("label", {}, "Name", bind(t, "name", el("input", { value: t.name || "" }))),
      el("label", {}, "Budget line", bind(t, "budget_line", el("input", { value: t.budget_line || "" })))),
    el("label", {}, "What this invoice type is (used to recognise it)", bind(t, "description", el("textarea", { value: t.description || "" }))),
    el("label", {}, "What to look for on these documents", bind(t, "what_to_look_for", el("textarea", { value: t.what_to_look_for || "", rows: 5 }))),
    el("label", { style: "display:flex;gap:6px;align-items:center;color:var(--ink)" }, bind(t, "enabled", el("input", { type: "checkbox", checked: t.enabled !== false })), "In use")));
  return el("div", {}, el("p", { class: "small muted", text: "These descriptions tell the assistant how to recognise each invoice type and what to look for. Edit them in your own words." }),
    el("div", { class: "cards" }, cards), saveBar(["invoice_types"]));
}

function fieldsView() {
  const fields = state.draft.fields.filter((f) => !state.typeFilter || f.type_id === state.typeFilter);
  const cards = fields.map((f) => {
    const kind = bind(f, "kind", el("select", {}, el("option", { value: "text", text: "Text" }), el("option", { value: "amount", text: "Amount" }), el("option", { value: "date", text: "Date" })));
    kind.value = f.kind || "text";
    return el("div", { class: "card" },
      el("div", { class: "head" }, el("b", { text: f.label }), el("span", { class: "muted small", text: `${f.type_id} · ${f.name}` })),
      el("div", { class: "grid2" },
        el("label", {}, "Label", bind(f, "label", el("input", { value: f.label || "" }))),
        el("label", {}, "Kind of value", kind),
        el("label", { style: "display:flex;gap:6px;align-items:center;color:var(--ink)" }, bind(f, "required", el("input", { type: "checkbox", checked: f.required })), "Usually on every document")),
      el("label", {}, "How to find it", bind(f, "hint", el("textarea", { value: f.hint || "" }))));
  });
  return el("div", {}, filterBar(false), el("p", { class: "small muted", text: "The values the assistant reads from each invoice type." }),
    el("div", { class: "cards" }, cards.length ? cards : el("p", { class: "muted", text: "No fields for this type." })), saveBar(["fields"]));
}

function learningsView() {
  const items = state.draft.learnings.map((l) => el("div", { class: "card" },
    el("div", { class: "head" }, el("span", { class: "muted small", text: `${l.id} · from ${l.source_invoice || "manual"} · ${when(l.created)}` })),
    el("label", {}, "Tip", bind(l, "text", el("textarea", { value: l.text || "" }))),
    el("label", { style: "display:flex;gap:6px;align-items:center;color:var(--ink)" }, bind(l, "active", el("input", { type: "checkbox", checked: l.active !== false })), "In use")));
  return el("div", {}, el("p", { class: "small muted", text: "Tips saved with reviews. The assistant follows the tips that are in use. Remove or switch off any that cause problems." }),
    el("div", { class: "cards" }, items.length ? items : el("p", { class: "muted", text: "No tips yet. Add one when you confirm a review." })), saveBar(["learnings"]));
}

function projectView() {
  const p = state.draft.project;
  return el("div", { class: "card" },
    el("label", {}, "Project name", bind(p, "name", el("input", { value: p.name || "" }))),
    el("label", {}, "Funder", bind(p, "funder", el("input", { value: p.funder || "" }))),
    el("div", { class: "grid2" },
      el("label", {}, "Project start", bind(p, "period_start", el("input", { type: "date", value: p.period_start || "" }))),
      el("label", {}, "Project end", bind(p, "period_end", el("input", { type: "date", value: p.period_end || "" }))),
      el("label", {}, "Main currency", bind(p, "currency", el("input", { value: p.currency || "" })))),
    saveBar(["project"]));
}

// ---------- tests ----------
async function loadTests() {
  const panel = document.getElementById("panel-tests");
  const data = await api("GET", "/api/evaluation");
  const run = data.latest_run;
  const parts = [el("h2", { text: "Test invoices" }),
    el("p", { class: "muted", text: "Invoices your team already checked, with the right answers saved. To measure the current setup, ask in the chat: “Run the test invoices”." }),
    el("p", { class: "small", text: `${data.test_invoices.length} test invoice(s), ${data.test_invoices.filter((t) => t.aside).length} kept aside.` })];
  if (!data.test_invoices.length) {
    parts.push(el("p", { class: "empty", text: "No test invoices yet. Review an invoice, confirm it, then choose “Add to test invoices”." }));
    panel.replaceChildren(...parts);
    return;
  }
  parts.push(el("div", { class: "row-end" }, el("button", { type: "button", class: "ghost", onclick: async () => {
    try { await api("POST", "/api/evaluation/score"); notify("Scored with the latest results."); await loadTests(); } catch (e) { notify(e.message, true); }
  } }, "Score the latest results")));
  if (run) {
    const t = run.groups.main.totals;
    parts.push(el("p", { class: "small muted", text: `Latest score: ${when(run.at)}${run.not_checked_yet.length ? ` · not checked yet: ${run.not_checked_yet.join(", ")}` : ""}` }),
      el("div", { class: "score" },
        el("div", {}, el("b", { text: String(t.matched) }), "rule results right"),
        el("div", {}, el("b", { text: String(t.missed) }), "problems missed"),
        el("div", {}, el("b", { text: String(t.false_alarm) }), "false alarms"),
        el("div", {}, el("b", { text: String(t.unclear) }), "unclear"),
        el("div", {}, el("b", { text: `${run.groups.main.fields_right}/${run.groups.main.fields_total}` }), "values read right")),
      el("h3", { text: "Per rule" }),
      el("div", { class: "table-wrap" }, el("table", { class: "plain" },
        el("thead", {}, el("tr", {}, ["Rule", "Right", "Missed", "False alarms", "Unclear"].map((h) => el("th", { text: h })))),
        el("tbody", {}, run.groups.main.rules.map((r) => el("tr", {}, el("td", { text: r.name }),
          el("td", { class: "num", text: String(r.matched) }), el("td", { class: "num", text: String(r.missed) }),
          el("td", { class: "num", text: String(r.false_alarm) }), el("td", { class: "num", text: String(r.unclear) })))))),
      el("h3", { text: "Differences per invoice", style: "margin-top:16px" }),
      el("div", { class: "cards" }, run.invoices.map((inv) => el("div", { class: "card" },
        el("div", { class: "head" }, el("b", { text: inv.invoice }), inv.aside ? pill("kept aside", "") : null,
          inv.type_correct ? null : pill("wrong invoice type", "failed")),
        inv.wrong_fields.length || inv.rule_notes.length ? el("ul", {},
          inv.wrong_fields.map((w) => el("li", { text: `${w.field}: expected “${w.expected ?? "empty"}”, got “${w.got ?? "empty"}”` })),
          inv.rule_notes.map((n) => el("li", { text: `${n.name}: expected ${n.expected}, got ${n.got} (${n.kind.replace("_", " ")})` })))
          : el("p", { class: "small muted", text: "Everything matches." })))));
    if (run.groups.aside.invoices) {
      const a = run.groups.aside.totals;
      parts.push(el("p", { class: "small", text: `Kept aside: ${a.matched} right, ${a.missed} missed, ${a.false_alarm} false alarms, ${a.unclear} unclear.` }));
    }
    if (data.runs.length > 1) {
      parts.push(el("h3", { text: "Earlier scores", style: "margin-top:16px" }), el("div", { class: "table-wrap" }, el("table", { class: "plain" },
        el("thead", {}, el("tr", {}, ["When", "Right", "Missed", "False alarms", "Unclear"].map((h) => el("th", { text: h })))),
        el("tbody", {}, data.runs.map((r) => el("tr", {}, el("td", { text: when(r.at) }),
          ["matched", "missed", "false_alarm", "unclear"].map((k) => el("td", { class: "num", text: String(r.groups.main.totals[k]) }))))))));
    }
  }
  parts.push(el("h3", { text: "Test invoices", style: "margin-top:16px" }),
    el("ul", {}, data.test_invoices.map((t) => el("li", { text: `${t.invoice}${t.aside ? " (kept aside)" : ""}, confirmed ${when(t.confirmed_at)}` }))));
  panel.replaceChildren(...parts);
}

// ---------- history ----------
async function loadHistory() {
  const panel = document.getElementById("panel-history");
  const entries = await api("GET", "/api/history?limit=300");
  panel.replaceChildren(el("h2", { text: "History" }),
    el("p", { class: "muted", text: "Everything that changed in this project, newest first. Corrections and edits keep the before and after." }),
    entries.length ? el("ul", { class: "history" }, entries.map((e) => el("li", {},
      el("span", { class: "when", text: when(e.at) }), el("b", { text: e.action }), " ", el("span", { class: "muted", text: `by ${e.who}` }),
      e.detail && Object.keys(e.detail).length ? el("details", {}, el("summary", { class: "small", text: "Details" }),
        el("pre", { text: JSON.stringify(e.detail, null, 2) })) : null)))
      : el("p", { class: "empty", text: "Nothing has happened yet." }));
}

// ---------- proposals ----------
function changeText(value) {
  if (value === null || value === undefined || value === "") return "(empty)";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

async function loadProposals() {
  const box = document.getElementById("proposals-box");
  const data = await api("GET", "/api/proposals");
  const count = data.changes.length + data.rules.length;
  const decideChange = async (id, approve) => {
    try {
      await api("POST", `/api/proposals/${encodeURIComponent(id)}`, { approve });
      notify(approve ? "Approved and applied. It is in the history." : "Rejected.");
      await loadSetup();
    } catch (error) { notify(error.message, true); }
  };
  const decideRule = async (id, status) => {
    try {
      await api("POST", `/api/rules/${encodeURIComponent(id)}/status`, { status });
      notify(status === "confirmed" ? "Rule confirmed. It applies from the next check." : "Rule rejected.");
      await loadSetup();
    } catch (error) { notify(error.message, true); }
  };
  const exportBar = el("div", { class: "row-end small" },
    el("a", { href: "/api/export/setup.json", class: "ghost-link", text: "Download setup to share" }),
    el("button", { type: "button", class: "ghost", onclick: async () => {
      try { const d = await api("POST", "/api/export/setup.xlsx"); window.location.href = d.url; } catch (e) { notify(e.message, true); }
    } }, "Download as Excel"));
  const items = [
    ...data.changes.map((c) => el("div", { class: "proposal" },
      el("div", { class: "head" }, el("b", { text: `Change ${c.kind.replace("_", " ")}: ${c.target_name}` }), pill("change", "proposed")),
      el("p", { class: "small", text: c.reason }),
      el("div", { class: "diff" }, Object.keys(c.after).map((k) => el("div", {},
        el("span", { class: "muted small", text: k.replace("_", " ") }),
        el("div", { class: "before", text: changeText(c.before[k]) }),
        el("div", { class: "after", text: changeText(c.after[k]) })))),
      c.evidence.length ? el("p", { class: "small muted", text: `Based on: ${c.evidence.join(", ")}` }) : null,
      el("div", { class: "row-end" },
        el("button", { type: "button", class: "ghost", onclick: () => decideChange(c.id, false) }, "Reject"),
        el("button", { type: "button", class: "primary", onclick: () => decideChange(c.id, true) }, "Approve")))),
    ...data.rules.map((r) => el("div", { class: "proposal" },
      el("div", { class: "head" }, el("b", { text: `New rule: ${r.name}` }), pill("new rule", "proposed")),
      el("p", { class: "small", text: r.description }),
      r.hint ? el("p", { class: "small muted", text: `Where to look: ${r.hint}` }) : null,
      el("p", { class: "small muted", text: `Source: ${r.source}${r.reason ? ` · ${r.reason}` : ""}` }),
      el("div", { class: "row-end" },
        el("button", { type: "button", class: "ghost", onclick: () => decideRule(r.id, "rejected") }, "Reject"),
        el("button", { type: "button", class: "primary", onclick: () => decideRule(r.id, "confirmed") }, "Approve")))),
  ];
  box.replaceChildren(el("section", { class: "inbox" },
    el("div", { class: "head" }, el("h2", { text: count ? `Waiting for your approval (${count})` : "Nothing waiting for approval" }), exportBar),
    count ? el("div", { class: "proposals" }, items)
      : el("p", { class: "small muted", text: "When the assistant proposes new rules or clearer descriptions, they appear here first." })));
}

// ---------- assistant settings ----------
const JOB_LABELS = {
  reading: ["Checking invoices", "Reading pages, judging rules, marking evidence. Runs most often, so it decides most of the usage."],
  rules: ["Proposing rules", "Reading funder guidelines. Runs rarely and needs careful reading."],
  other: ["Everything else", "Switching projects, help, questions in the chat."],
};
const MODEL_LABELS = { haiku: "Haiku (fastest, lowest usage)", sonnet: "Sonnet (balanced)", opus: "Opus (most careful, highest usage)" };
const EFFORT_LABELS = { low: "Low", medium: "Medium", high: "High", xhigh: "Extra high", max: "Maximum" };

async function loadSettings() {
  const panel = document.getElementById("panel-settings");
  const data = await api("GET", "/api/settings");
  const draft = clone(data.settings);
  const select = (options, labels, value, onChange) => {
    const node = el("select", { onchange: (e) => onChange(e.target.value) }, options.map((o) => el("option", { value: o, text: labels[o] || o })));
    node.value = value;
    return node;
  };
  const rows = Object.entries(JOB_LABELS).map(([job, [title, help]]) => el("tr", {},
    el("td", {}, el("b", { text: title }), el("div", { class: "small muted", text: help })),
    el("td", {}, select(data.claude_models, MODEL_LABELS, draft.claude[job].model, (v) => { draft.claude[job].model = v; })),
    el("td", {}, select(data.efforts, EFFORT_LABELS, draft.claude[job].effort, (v) => { draft.claude[job].effort = v; }))));
  const codexModel = el("input", { value: draft.codex.model, placeholder: "Leave empty for the Codex default", oninput: (e) => { draft.codex.model = e.target.value.trim(); } });
  panel.replaceChildren(
    el("h2", { text: "Assistant settings" }),
    el("p", { class: "muted", text: "Choose how much each job may use of your plan. Stronger models and higher effort are more careful but use the limits faster. Run the test invoices after a change to see whether results got worse." }),
    el("h3", { text: "Claude Code" }),
    el("div", { class: "table-wrap" }, el("table", { class: "plain" },
      el("thead", {}, el("tr", {}, el("th", { text: "Job" }), el("th", { text: "Model" }), el("th", { text: "Effort" }))),
      el("tbody", {}, rows))),
    el("p", { class: "small muted", text: "Applies from the next request in the chat. If it doesn't, start a new chat." }),
    el("h3", { text: "Codex", style: "margin-top:16px" }),
    el("p", { class: "small muted", text: "Codex uses one model for the whole workspace. It reads this setting only after you trust this folder in Codex." }),
    el("div", { class: "card" },
      el("div", { class: "grid2" },
        el("label", {}, "Model (as named in the Codex model menu)", codexModel),
        el("label", {}, "Effort", select(data.efforts, EFFORT_LABELS, draft.codex.effort, (v) => { draft.codex.effort = v; })))),
    el("div", { class: "savebar" }, el("button", { type: "button", class: "primary", onclick: async () => {
      try {
        const response = await api("PUT", "/api/settings", { value: draft });
        notify(response.changes ? "Settings saved. They are in the history." : "Nothing changed.");
        await loadSettings();
      } catch (error) { notify(error.message, true); }
    } }, "Save settings")));
}

// ---------- start ----------
function wire() {
  document.getElementById("project-select").addEventListener("change", (e) => switchProject(e.target.value).catch((err) => notify(err.message, true)));
  for (const button of document.querySelectorAll(".tabs button")) {
    button.addEventListener("click", () => showTab(button.dataset.tab).catch((err) => notify(err.message, true)));
  }
  for (const button of document.querySelectorAll(".subtabs button")) {
    button.addEventListener("click", async () => {
      if (state.setupDirty && !(await confirmLeave())) return;
      if (state.setupDirty) { state.draft = clone(state.config); state.setupDirty = false; }
      state.setupSub = button.dataset.sub; renderSetup();
    });
  }
  const helpDialog = document.getElementById("help-dialog");
  document.getElementById("help-btn").addEventListener("click", () => helpDialog.showModal());
  document.getElementById("help-close").addEventListener("click", () => helpDialog.close());
  const dialog = document.getElementById("new-project-dialog");
  document.getElementById("new-project-btn").addEventListener("click", async () => { if (await confirmLeave()) dialog.showModal(); });
  document.getElementById("new-project-cancel").addEventListener("click", () => dialog.close());
  document.getElementById("new-project-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const file = document.getElementById("new-project-file").files[0];
      const name = document.getElementById("new-project-name").value;
      if (file) {
        let setup;
        try { setup = JSON.parse(await file.text()); } catch { throw new Error("The setup file could not be read."); }
        await api("POST", "/api/project/import", { name, setup });
      } else {
        await api("POST", "/api/project/create", { name, copy_rules_from: document.getElementById("new-project-copy").value });
      }
      dialog.close();
      Object.assign(state, { selected: null, detail: null, config: null, draft: null, setupDirty: false, reviewDirty: false });
      await loadState();
      await showTab("setup", true);
      notify("Project created. Add guidelines or confirm the copied rules.");
    } catch (error) { notify(error.message, true); }
  });
  const drop = document.getElementById("invoice-drop");
  const input = document.getElementById("invoice-upload");
  input.addEventListener("change", async () => { await afterInvoiceUpload(await uploadFiles(input.files, "/api/invoices/upload")); input.value = ""; });
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", async (e) => {
    e.preventDefault(); drop.classList.remove("over");
    await afterInvoiceUpload(await uploadFiles(e.dataTransfer.files, "/api/invoices/upload"));
  });
  document.getElementById("report-btn").addEventListener("click", async () => {
    try {
      const data = await api("POST", "/api/report");
      notify("Report created.");
      window.location.href = data.url;
    } catch (error) { notify(error.message, true); }
  });
  window.addEventListener("beforeunload", (e) => { if (state.setupDirty || state.reviewDirty) e.preventDefault(); });
}

async function afterInvoiceUpload(count) {
  if (!count) return;
  notify(`Added ${count} invoice(s). Ask in the chat: “Check the new invoices”.`);
  await loadState();
  await loadInvoices();
}

async function poll() {
  if (document.hidden || !state.current || state.tab !== "invoices") return;
  try {
    const before = JSON.stringify(state.invoices);
    await loadInvoices();
    if (state.selected && !state.reviewDirty && before !== JSON.stringify(state.invoices)) await selectInvoice(state.selected, true);
  } catch { /* the next poll tries again */ }
}

(async () => {
  wire();
  try {
    await loadState();
    await showTab("invoices", true);
  } catch (error) { notify(error.message, true); }
  setInterval(poll, 6000);
})();
