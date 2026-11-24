import {
  api, askConfirm, button, clone, compareLabels, confirmLeave, el, notify, promptButton, radioGroup, state, uploadFiles, uploadSummary, when, startRuleDetection, refreshRuleDetection
} from "./workspace.js";

const CHECK_LABEL = {
  visual: "Judged by looking at the document",
  required: "Value must be present",
  date_in_period: "Date inside the project period",
  range: "Number within a range",
  enum: "One of a list of values",
  regex: "Follows a pattern",
};
const SEVERITIES = [["error", "Error: fails the invoice"], ["warning", "Warning: needs a look"]];
const FIELD_KINDS = { text: "Text", amount: "Amount", date: "Date" };

// ---------- setup ----------
let loadedProject = null;
let setupRequest = 0;
const inboxErrors = new Map();
const openSetupItems = new Set();
let guidelineUploadResults = null;
let pendingDetectionRefresh = null;
let detectionRefreshRunning = false;

function setupNotice(text, failed = false, unapplied = []) {
  const notice = document.getElementById("setup-notice");
  notice.textContent = text;
  if (unapplied.length) notice.append(el("details", {}, el("summary", { text: "Your unapplied edits" }),
    ...unapplied.map(({ expected, edits }) => el("div", {}, el("b", { text: expected.name || expected.target_name || expected.id }),
      el("ul", {}, Object.entries(edits).map(([key, value]) => el("li", { text: `${key}: ${changeText(value)}` })))))));
  notice.classList.toggle("error", failed);
  notice.hidden = !text;
}

export function clearSetup() {
  setupRequest++;
  inboxErrors.clear();
  openSetupItems.clear();
  guidelineUploadResults = null;
  setupNotice("");
  document.getElementById("rule-detection-status")?.remove();
  loadedProject = null;
  pendingDetectionRefresh = null;
  state.draft = null;
  state.editRule = null;
  document.getElementById("inbox-count").textContent = "";
  document.querySelector('[data-sub="inbox"]').hidden = true;
  document.getElementById("setup-body").replaceChildren();
  for (const tab of document.querySelectorAll("[data-sub]")) tab.removeAttribute("aria-current");
}

export async function loadSetup() {
  clearSetup();
  const request = setupRequest;
  const project = state.current;
  const body = document.getElementById("setup-body");
  body.textContent = "Loading project setup…";
  try {
    const config = await api("GET", "/api/config?inbox=1", undefined, project);
    if (request !== setupRequest || state.tab !== "setup") return;
    loadedProject = project;
    state.config = config;
    state.draft = clone(config);
    state.setupDirty = false;
    state.setupSub ??= pendingCount() ? "inbox" : "rules";
    renderSetup();
    void refreshRuleDetection(project);
  } catch (error) {
    if (request !== setupRequest || state.tab !== "setup") return;
    body.replaceChildren(el("p", { text: "Could not load project setup." }),
      button("Try again", () => loadSetup().catch(err => notify(err.message, true))));
    throw error;
  }
}

function pendingCount() {
  return state.config.rules.filter(rule => rule.status === "proposed").length + state.config.pending_changes.length;
}

function markDirty() {
  state.setupDirty = true;
  const flag = document.getElementById("dirty-flag");
  if (flag) {
    flag.textContent = "Unsaved changes";
    for (const action of flag.parentElement.querySelectorAll("button")) action.disabled = false;
  }
}

function bind(object, key, input, onChange = markDirty) {
  input.addEventListener(input.type === "checkbox" ? "change" : "input", () => {
    object[key] = input.type === "checkbox" ? input.checked : input.value;
    onChange?.();
  });
  return input;
}

function typeOptions(withAll, allLabel = "All types") {
  return [withAll ? el("option", { value: "", text: allLabel }) : null,
    ...state.draft.invoice_types.map((t) => el("option", { value: t.id, text: t.name }))];
}

function focusRuleRow(ruleId) {
  const opener = document.querySelector(`[data-edit-rule="${CSS.escape(ruleId)}"]`);
  if (!opener) {
    document.querySelector(`[data-sub="${CSS.escape(state.setupSub)}"]`)?.focus();
    return;
  }
  const disclosure = opener.closest("details");
  if (disclosure) disclosure.open = true;
  opener.focus();
}

function saveBar(part, rule = null) {
  const project = loadedProject;
  const draft = state.draft;
  const actions = el("div", { class: rule ? "action-row rule-save-actions" : "savebar setup-savebar" },
    el("span", { id: "dirty-flag", class: "dirty", role: "status", text: state.setupDirty ? "Unsaved changes" : "" }),
    button(rule && !state.setupDirty ? "Done" : "Discard", async () => {
      if (draft !== state.draft) return;
      if (!(await confirmLeave()) || draft !== state.draft) return;
      state.draft = clone(state.config);
      state.editRule = null;
      state.setupDirty = false;
      renderSetup();
      if (rule) focusRuleRow(rule.id);
    }),
    button("Save changes", async event => {
      if (draft !== state.draft || project !== state.current) return;
      const save = event.currentTarget;
      const panel = save.closest("#panel-setup");
      panel.inert = true;
      try {
        const { changes } = await api("PUT", `/api/config/${part}`, { value: draft[part], expected: state.config[part] }, project);
        if (draft !== state.draft || state.tab !== "setup") return;
        state.setupDirty = false;
        notify(changes ? "Changes saved." : "Nothing changed.");
        await loadSetup();
        if (rule && state.tab === "setup" && loadedProject === project) {
          panel.inert = false;
          focusRuleRow(rule.id);
        }
      } catch (error) { notify(error.message, true); }
      finally { panel.inert = false; }
    }, "primary"));
  for (const action of actions.querySelectorAll("button")) action.disabled = !state.setupDirty;
  if (!rule) return actions;
  actions.querySelector("button").disabled = false;
  return el("div", { class: "savebar setup-savebar rule-editor-header" },
    el("h3", { tabindex: "-1", text: "Edit rule" }), actions);
}

export function renderSetup() {
  if (!state.draft || loadedProject !== state.current) return;
  if (!state.setupDirty && pendingDetectionRefresh === loadedProject) {
    queueMicrotask(() => reconcileDetection());
  }
  const count = pendingCount();
  const inboxTab = document.querySelector('[data-sub="inbox"]');
  inboxTab.hidden = count === 0;
  if (!count && state.setupSub === "inbox") state.setupSub = "rules";
  for (const tab of document.querySelectorAll("[data-sub]")) {
    if (tab.dataset.sub === state.setupSub) tab.setAttribute("aria-current", "page");
    else tab.removeAttribute("aria-current");
  }
  document.getElementById("inbox-count").textContent = `(${count})`;
  const views = { inbox: inboxView, rules: rulesView, types: typesView,
    fields: fieldsView, learnings: learningsView, project: projectView };
  const editing = state.editRule && state.draft.rules.find(rule => rule.id === state.editRule);
  document.getElementById("setup-body").replaceChildren(editing ? ruleEditor(editing) : views[state.setupSub]());
}

function filterBar() {
  const type = el("select", { "aria-label": "Invoice type", onchange: e => {
    for (const item of document.querySelectorAll("#setup-body details[data-remember-key]")) {
      if (item.open) openSetupItems.add(item.dataset.rememberKey);
      else openSetupItems.delete(item.dataset.rememberKey);
    }
    state.typeFilter = e.target.value;
    renderSetup();
    document.querySelector('#setup-body select[aria-label="Invoice type"]')?.focus();
  } }, typeOptions(true));
  type.value = state.typeFilter;
  return el("label", {}, "Invoice type ", type);
}

function guidelinesView() {
  const project = loadedProject;
  const files = state.config.guidelines || [];
  async function addGuidelines(selected, previous = []) {
    const results = await uploadFiles(selected, "/api/guidelines/upload", project);
    if (!results.length || project !== loadedProject || state.tab !== "setup") return;
    const section = document.querySelector("#setup-body .guidelines");
    if (results.some(result => !result.error)) {
      try {
        const config = await api("GET", "/api/config", undefined, project);
        if (project !== loadedProject || state.tab !== "setup") return;
        state.config.guidelines = config.guidelines;
        section?.replaceWith(guidelinesView());
      } catch (error) { notify(error.message, true); }
    }
    if (results.some(result => !result.error)) await startRuleDetection(project);
    const allResults = [...previous, ...results];
    guidelineUploadResults = uploadSummary(allResults,
      failed => addGuidelines(failed, allResults.filter(result => !result.error)));
    guidelineUploadResults.addEventListener("click", event => {
      if (event.target.textContent === "Dismiss") guidelineUploadResults = null;
    });
    document.querySelector("#setup-body .guideline-upload-results")?.replaceChildren(guidelineUploadResults);
  }
  const picker = el("input", { type: "file", accept: ".pdf,.txt,.md", multiple: true, hidden: true,
    onchange: async e => {
      try {
        await addGuidelines(picker.files);
      } catch (error) { notify(error.message, true); }
      finally { picker.value = ""; }
    } });
  return el("section", { class: "guidelines" },
    el("h3", { text: "Funder guidelines" }),
    el("p", { class: "muted small", text: "Added guidelines are sent to Codex using your signed-in plan to detect proposed rules." }),
    el("div", { class: "guideline-upload-results" }, guidelineUploadResults),
    files.length ? el("ul", {}, files.map(name => el("li", { text: name }))) :
      el("p", { class: "muted", text: state.config.rules.length ? "This setup contains rules. Add the source guidelines here so staff can verify them." : "Add the project guidelines, then ask the assistant to propose rules." }),
    el("div", { class: "action-row" }, picker, button("Add guidelines", () => picker.click()),
      files.length ? promptButton("Copy rule proposal request", `Propose invoice rules from the guidelines in project "${project}". Include the source file and page for each proposal.`) : null));
}

window.addEventListener("rule-detection", async event => {
  const { project, status, message } = event.detail;
  if (project !== loadedProject || state.tab !== "setup") return;
  let box = document.getElementById("rule-detection-status");
  if (status === "idle" || message) {
    if (!box) {
      box = el("div", { id: "rule-detection-status", class: "setup-notice", role: "status", "aria-live": "polite" });
      document.getElementById("setup-notice").after(box);
    }
    box.classList.toggle("error", status === "failed");
    if (status === "idle") {
      const hasGuidelines = (state.config.guidelines || []).length > 0;
      box.replaceChildren(el("p", { text: hasGuidelines
        ? "Check the added guidelines for rules using Codex."
        : "Add guidelines to check them for rules." }));
      if (hasGuidelines) {
        const start = button("Check rules from guidelines", async () => {
          if (project !== loadedProject || project !== state.current || state.tab !== "setup") return;
          start.disabled = true;
          await startRuleDetection(project);
        });
        box.append(start);
      } else {
        box.append(button("Add guidelines", () => document.querySelector('[data-sub="project"]')?.click()));
      }
    } else {
      box.replaceChildren(el("p", { text: message }));
    }
    if (status === "failed") box.append(button("Retry rule detection", () => startRuleDetection(project)));
    if (status === "completed" && event.detail.count > 0) {
      box.append(button("Open Inbox", () => document.querySelector('[data-sub="inbox"]')?.click()));
    }
  } else {
    box?.remove();
  }
  if (status === "completed") {
    pendingDetectionRefresh = project;
    await reconcileDetection();
  }
});

async function reconcileDetection() {
  const project = pendingDetectionRefresh;
  if (!project || detectionRefreshRunning || project !== loadedProject || state.tab !== "setup" || state.setupDirty || state.inboxBusy || state.editRule) return;
  detectionRefreshRunning = true;
  try {
    const config = await api("GET", "/api/config?inbox=1", undefined, project);
    if (project !== loadedProject || state.tab !== "setup" || state.setupDirty || state.inboxBusy || state.editRule) return;
    pendingDetectionRefresh = null;
    state.config.rules = config.rules;
    state.config.pending_changes = config.pending_changes;
    state.draft.rules = clone(config.rules);
    state.draft.pending_changes = clone(config.pending_changes);
    if (state.setupSub === "inbox" && !state.editRule) {
      const active = document.activeElement;
      const body = document.getElementById("setup-body");
      const focusWasInside = body.contains(active);
      const focusName = focusWasInside ? active.getAttribute("aria-label") : null;
      const selectionStart = focusWasInside && typeof active.selectionStart === "number" ? active.selectionStart : null;
      const selectionEnd = selectionStart === null ? null : active.selectionEnd;
      renderSetup();
      if (focusWasInside) {
        const match = focusName && [...body.querySelectorAll("[aria-label]")].find(node => node.getAttribute("aria-label") === focusName);
        const target = match || document.querySelector('[data-sub="inbox"]');
        target?.focus({ preventScroll: true });
        if (selectionStart !== null && match?.setSelectionRange) match.setSelectionRange(selectionStart, selectionEnd);
      }
    } else {
      document.querySelector('[data-sub="inbox"]').hidden = !pendingCount();
      document.getElementById("inbox-count").textContent = `(${pendingCount()})`;
    }
  } catch (error) {
    if (project === loadedProject) notify(error.message, true);
  } finally {
    detectionRefreshRunning = false;
    if (pendingDetectionRefresh && pendingDetectionRefresh !== project && pendingDetectionRefresh === loadedProject)
      queueMicrotask(() => reconcileDetection());
  }
}

function ruleInputs(rule, onChange, inbox = false) {
  const input = (key, control) => {
    control.dataset.ruleKey = key;
    return bind(rule, key, control, onChange);
  };
  function checkSettings() {
    const check = input("check", el("select", {}, Object.entries(CHECK_LABEL).map(([v, t]) => el("option", { value: v, text: t }))));
    check.value = rule.check;
    const severity = radioGroup(`rule-severity-${rule.id}`, "If it fails", SEVERITIES, rule.severity || "error", value => {
      rule.severity = value;
      onChange?.();
    });
    const type = input("type_id", el("select", {}, el("option", { value: "ALL", text: "Every invoice type" }), typeOptions(false)));
    type.value = rule.type_id;
    const fields = el("div", { class: "grid2" });
    function showCheckFields() {
      fields.replaceChildren();
      fields.hidden = rule.check === "visual";
      if (fields.hidden) return;
      const options = state.draft.fields.filter(f => rule.type_id === "ALL" || f.type_id === rule.type_id);
      const field = input("field", el("select", { required: true }, el("option", { value: "", "data-placeholder": true, text: "Choose a field" }),
        options.map(f => el("option", { value: f.name, text: `${f.label} (${f.name})` }))));
      field.value = rule.field || "";
      fields.append(el("label", {}, "Field", field));
      const label = { range: "Range (min,max)", enum: "Allowed values (comma separated)", regex: "Pattern" }[rule.check];
      if (label) fields.append(el("label", {}, label, input("value", el("input", { value: rule.value || "" }))));
    }
    check.addEventListener("change", () => {
      showCheckFields();
      if (inbox) settings.querySelector("summary").textContent = `Check settings · ${CHECK_LABEL[rule.check]}`;
    });
    type.addEventListener("change", () => { rule.field = ""; showCheckFields(); onChange?.(); });
    showCheckFields();
    return el("div", { class: "rule-check-settings" },
      el("div", { class: "grid2" }, el("label", {}, "Invoice type", type), el("label", {}, "How it is checked", check), severity),
      fields, el("label", { class: "inline-control" }, input("enabled", el("input", { type: "checkbox", checked: rule.enabled !== false })), "In use"));
  }
  const settings = inbox ? el("details", { class: "rule-check-disclosure" }, el("summary", {
    text: `Check settings · ${CHECK_LABEL[rule.check] || rule.check || "Visual check"}` })) : checkSettings();
  if (inbox) settings.addEventListener("toggle", () => {
    if (settings.open && settings.childElementCount === 1) settings.append(checkSettings());
  });
  return el("div", { class: "card rule-inputs" },
    el("label", {}, "Name", input("name", el("input", { required: true, value: rule.name || "" }))),
    el("label", {}, "What the rule requires", input("description", el("textarea", { value: rule.description || "" }))),
    el("label", {}, "Where to look", input("hint", el("textarea", { value: rule.hint || "" }))),
    el("label", {}, "Source (document and page)", input("source", el("input", { value: rule.source || "" }))), settings);
}

function ruleEditor(rule) {
  const bar = saveBar("rules", rule);
  const original = state.config.rules.find(saved => saved.id === rule.id);
  const inputs = ["name", "description", "hint", "type_id", "check", "severity", "field", "value", "source", "enabled"];
  const value = (entry, key) => key === "enabled" ? entry.enabled !== false : String(entry[key] ?? "");
  function updateActions() {
    state.setupDirty = inputs.some(key => value(rule, key) !== value(original, key));
    bar.querySelector(".dirty").textContent = state.setupDirty ? "Unsaved changes" : "";
    bar.querySelector("button").textContent = state.setupDirty ? "Discard" : "Done";
    bar.querySelector(".primary").disabled = !state.setupDirty;
    if (!state.setupDirty && pendingDetectionRefresh === loadedProject) queueMicrotask(() => reconcileDetection());
  }
  return el("div", {}, bar, ruleInputs(rule, updateActions));
}

function typeName(type) {
  if (type === "ALL") return "All invoice types";
  return state.draft.invoice_types.find(t => t.id === type)?.name || type;
}

function matchesType(type) {
  return !state.typeFilter || type === state.typeFilter || type === "ALL";
}

function entryPart(kind) { return kind === "rule" ? "rules" : "pending_changes"; }
function entryKey(kind, id) { return `${kind}/${id}`; }

function inboxDirty() {
  return ["rules", "pending_changes"].some(part => JSON.stringify(state.draft[part]) !== JSON.stringify(state.config[part]));
}

function inboxEdited() {
  state.setupDirty = inboxDirty();
  if (!state.setupDirty && pendingDetectionRefresh === loadedProject) queueMicrotask(() => reconcileDetection());
}

function replaceEntry(part, id, item) {
  for (const config of [state.config, state.draft]) {
    const index = config[part].findIndex(row => row.id === id);
    if (index >= 0) config[part].splice(index, 1, ...(item ? [clone(item)] : []));
  }
}

function decisionApplied(kind, item) {
  const part = entryPart(kind);
  if (kind === "rule") { replaceEntry(part, item.id, item); return; }
  replaceEntry(part, item.id, null);
  if (item.status !== "approved") return;
  const targetPart = { field: "fields", invoice_type: "invoice_types", rule: "rules" }[item.kind];
  const saved = state.config[targetPart].find(row => row.id === item.target);
  const draft = state.draft[targetPart].find(row => row.id === item.target);
  if (!saved || !draft) return;
  for (const [key, value] of Object.entries(item.reviewed_after || item.after)) {
    if (JSON.stringify(draft[key]) === JSON.stringify(saved[key])) draft[key] = value;
    saved[key] = value;
  }
}

function decisionRequest(kind, item, approve) {
  const expected = state.config[entryPart(kind)].find(original => original.id === item.id);
  const edits = {};
  if (approve) {
    const original = kind === "rule" ? expected : expected.after;
    const proposed = kind === "rule" ? item : item.after;
    for (const [key, value] of Object.entries(proposed)) {
      if (JSON.stringify(value) === JSON.stringify(original[key])) continue;
      const typed = kind === "change" && original[key] !== null && ["object", "number"].includes(typeof original[key]);
      if (typed && typeof value === "string") {
        try { edits[key] = JSON.parse(value); }
        catch { throw new Error(`Enter a valid value for ${key} on ${item.target_name || item.name}.`); }
      } else edits[key] = value;
    }
  }
  return { kind, expected, edits };
}

function validateInboxRows(entries) {
  for (const { kind, item } of entries) {
    const key = entryKey(kind, item.id);
    const row = document.querySelector(`[data-inbox-key="${CSS.escape(key)}"]`);
    if (!row) return false;
    const original = state.config[entryPart(kind)].find(saved => saved.id === item.id);
    if (kind === "rule") {
      if (item.name !== original.name && !item.name?.trim()) {
        const name = row.querySelector('[data-rule-key="name"]');
        name.focus();
        setupNotice("Enter a name before confirming this rule.", true);
        return false;
      }
      if (["check", "type_id", "field"].some(k => item[k] !== original[k]) && item.check !== "visual" && !item.field) {
        const settings = row.querySelector(".rule-check-disclosure");
        settings.open = true;
        settings.dispatchEvent(new Event("toggle"));
        const field = settings.querySelector('[data-rule-key="field"]');
        field.focus();
        field.reportValidity();
        setupNotice("Choose a field for this rule before confirming.", true);
        return false;
      }
    } else {
      const invalid = row.querySelector("input:invalid, textarea:invalid, select:invalid");
      if (invalid) { invalid.focus(); invalid.reportValidity(); return false; }
    }
  }
  return true;
}

async function decideInbox(entries, approve, batch, trigger) {
  const project = loadedProject;
  const draft = state.draft;
  if (state.inboxBusy || !trigger.isConnected || project !== state.current || state.tab !== "setup") return;
  const list = document.querySelector(".setup-list");
  const index = [...list.children].indexOf(trigger.closest("article"));
  if (approve && !validateInboxRows(entries)) return;
  if (batch) {
    const rules = entries.filter(entry => entry.kind === "rule").length;
    const changes = entries.length - rules;
    const scope = state.typeFilter ? `the ${typeName(state.typeFilter)} filter` : "all invoice types";
    if (!(await askConfirm(`Confirm ${rules} proposed rule${rules === 1 ? "" : "s"} and apply ${changes} change${changes === 1 ? "" : "s"} shown for ${scope}? This includes your edits.`, `Confirm all (${entries.length})`))) return;
  }
  if (draft !== state.draft || !trigger.isConnected || state.inboxBusy) return;
  const panel = document.getElementById("panel-setup");
  state.inboxBusy = true;
  panel.inert = true;
  try {
    const items = entries.map(({ kind, item }) => decisionRequest(kind, item, approve));
    const { results } = await api("POST", "/api/inbox/decide", { approve, items }, project);
    if (draft !== state.draft || project !== loadedProject) return;
    const errors = [];
    const unapplied = [];
    for (const [position, result] of results.entries()) {
      const key = entryKey(result.kind, result.id);
      inboxErrors.delete(key);
      if (result.error) {
        errors.push(result);
        if (result.current?.status === (result.kind === "rule" ? "proposed" : "pending")) inboxErrors.set(key, result);
        else {
          if (Object.keys(items[position].edits).length) unapplied.push(items[position]);
          if (result.current) decisionApplied(result.kind, result.current);
          else replaceEntry(entryPart(result.kind), result.id, null);
        }
      } else decisionApplied(result.kind, result.item);
    }
    const done = results.length - errors.length;
    const single = entries[0].kind === "rule" ? (approve ? "Rule confirmed." : "Rule rejected.") :
      (approve ? "Change approved and applied." : "Change rejected.");
    const message = batch ? `Confirmed ${done} of ${entries.length} items.` : done ? single : "";
    let failure = "";
    if (errors.length) {
      const first = errors[0];
      failure = `${errors.length > 1 ? `${errors.length} items need attention. ` : ""}${first.current?.name || first.current?.target_name || first.id}: ${first.error}`;
    }
    inboxEdited();
    renderSetup();
    panel.inert = false;
    const rows = document.querySelectorAll(".setup-item-heading");
    (rows[Math.min(Math.max(0, index), rows.length - 1)] || document.querySelector(`[data-sub="${state.setupSub}"]`)).focus({ preventScroll: true });
    setupNotice([message, failure].filter(Boolean).join(" "), Boolean(failure), unapplied);
  } catch (error) { setupNotice(error.message, true); }
  finally {
    panel.inert = false;
    state.inboxBusy = false;
    if (!state.setupDirty && pendingDetectionRefresh === loadedProject) queueMicrotask(() => reconcileDetection());
  }
}

function decisionButtons(item, kind) {
  const decide = (approve, e) => decideInbox([{ kind, item }], approve, false, e.currentTarget);
  return el("div", { class: "action-row", role: "group", "aria-label": item.name || item.target_name || item.id },
    button("Reject", e => decide(false, e)), button(kind === "rule" ? "Confirm" : "Approve", e => decide(true, e), "primary"));
}

function rowError(kind, id) {
  const key = entryKey(kind, id);
  const error = inboxErrors.get(key);
  if (!error) return null;
  const original = state.config[entryPart(kind)].find(row => row.id === id);
  const stale = JSON.stringify(original) !== JSON.stringify(error.current);
  return el("div", { class: "inbox-error" }, el("p", { text: error.error }),
    stale ? button("Review latest version", async () => {
      const draft = state.draft;
      if (!(await askConfirm("Replace this item’s draft with its latest version?", "Use latest version")) || draft !== state.draft) return;
      replaceEntry(entryPart(kind), id, error.current);
      inboxErrors.delete(key);
      inboxEdited();
      renderSetup();
    }) : null);
}

function rememberedDetails(key, ...children) {
  const details = el("details", { open: openSetupItems.has(key), "data-remember-key": key }, ...children);
  details.addEventListener("toggle", () => {
    if (!details.isConnected) return;
    if (details.open) openSetupItems.add(key);
    else openSetupItems.delete(key);
  });
  return details;
}

function setupRow(title, meta, details, actions, key) {
  const metadata = el("span", { class: "row-meta", text: meta });
  if (actions) {
    return el("article", { class: "setup-row inbox-item", "data-inbox-key": key },
      el("div", { class: "setup-item" },
        el("div", { class: "setup-item-title" }, el("h4", { class: "setup-item-heading", tabindex: "-1", text: title }), metadata),
        details), actions);
  }
  return el("div", { class: "setup-row" },
    rememberedDetails(key, el("summary", {}, el("strong", { text: title }), metadata), details));
}

function ruleRow(rule) {
  if (rule.status === "proposed") {
    const original = state.config.rules.find(item => item.id === rule.id);
    const details = el("div", { class: "setup-row-details" },
      rule.reason ? el("p", { text: rule.reason }) : null, ruleInputs(rule, inboxEdited, true), rowError("rule", rule.id));
    return setupRow(original.name || original.id, `New rule · ${typeName(original.type_id)}`, details, decisionButtons(rule, "rule"), entryKey("rule", rule.id));
  }
  const edit = button("Edit rule", () => {
    state.editRule = rule.id;
    renderSetup();
    document.querySelector(".rule-editor-header h3").focus();
  });
  edit.dataset.editRule = rule.id;
  const details = el("div", { class: "setup-row-details" },
    el("p", { text: rule.description || "No description provided." }),
    rule.source ? el("p", { text: `Source: ${rule.source}` }) : null,
    rule.reason ? el("p", { text: `Reason: ${rule.reason}` }) : null,
    rule.hint ? el("p", { text: `Where to look: ${rule.hint}` }) : null,
    el("p", { class: "muted small", text: [CHECK_LABEL[rule.check], rule.field, rule.value,
      rule.severity === "warning" ? "Warning" : "Error"].filter(Boolean).join(" · ") }),
    edit);
  const meta = [typeName(rule.type_id), rule.enabled === false ? "Off" : ""].filter(Boolean).join(" · ");
  return setupRow(rule.name || rule.id, meta, details, null, `rule:${rule.id}`);
}

function rulesView() {
  const rules = state.draft.rules.filter(rule => rule.status === "confirmed");
  const visible = rules.filter(rule => matchesType(rule.type_id));
  return el("div", {}, el("div", { class: "setup-list-head" }, el("h3", { text: "Confirmed rules" }),
    el("div", { class: "action-row" }, rules.length ? filterBar() : null, addButton("rules"))),
    visible.length ? el("div", { class: "setup-list" }, visible.map(ruleRow))
      : el("p", { class: "muted", text: rules.length ? "No confirmed rules for this invoice type." : "No confirmed rules yet." }));
}

const ADD_LABELS = { invoice_types: "Add invoice type", fields: "Add field", rules: "Add a rule" };

function addButton(part) {
  const project = loadedProject;
  const draft = state.draft;
  const unavailable = part === "fields" && !draft.invoice_types.length;
  const add = el("button", { type: "button", class: "ghost", disabled: unavailable, "data-add": part, "aria-haspopup": "dialog",
    onclick: event => {
      if (draft === state.draft && project === loadedProject && project === state.current) openAddDialog(part, event.currentTarget);
    }, text: ADD_LABELS[part] });
  return unavailable ? el("div", { class: "action-row" }, add,
    el("span", { class: "muted", text: "Add an invoice type before defining its fields." })) : add;
}

function newItem(part) {
  if (part === "rules") {
    let number = 1;
    const ids = new Set(state.draft.rules.map(rule => rule.id));
    while (ids.has(`M${String(number).padStart(3, "0")}`)) number++;
    return { id: `M${String(number).padStart(3, "0")}`, type_id: state.typeFilter || "ALL", name: "", check: "visual",
      field: null, value: "", severity: "error", description: "", hint: "", source: "", status: "proposed", enabled: true };
  }
  if (part === "invoice_types") return { name: "", enabled: true, budget_line: "", description: "", what_to_look_for: "" };
  return { type_id: state.typeFilter || "", name: "", label: "", kind: "text", required: false, hint: "" };
}

function assignDefinitionId(item, part, existing) {
  const field = part === "fields";
  const name = field ? item.label : item.name;
  const base = name.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || (field ? "field" : "type");
  const prefix = field ? base : base.toUpperCase();
  const taken = new Set(existing.map(i => field ? i.name : i.id));
  let technical = prefix;
  let suffix = 1;
  while (taken.has(technical)) technical = `${prefix}_${++suffix}`;
  if (field) {
    let n = existing.length + 1;
    while (existing.some(i => i.id === `F${n}`)) n++;
    item.id = `F${n}`;
    item.name = technical;
  } else item.id = technical;
}

function newItemInputs(part, item) {
  if (part === "rules") return ruleInputs(item, null);
  const field = part === "fields";
  const name = el("label", {}, "Name", bind(item, field ? "label" : "name", el("input", { required: true, maxlength: "80" }), null));
  if (!field) return el("div", { class: "card" }, name,
    el("label", {}, "Budget line", bind(item, "budget_line", el("input"), null)),
    el("label", {}, "What this invoice type is", bind(item, "description", el("textarea"), null)),
    el("label", {}, "What to look for on these documents", bind(item, "what_to_look_for", el("textarea"), null)));
  const types = state.draft.invoice_types;
  let typeControl;
  if (types.length === 1) {
    item.type_id = types[0].id;
    typeControl = el("span", { class: "muted", text: `Invoice type: ${types[0].name}` });
  } else {
    const select = bind(item, "type_id", el("select", {}, typeOptions(false)), null);
    if (item.type_id) select.value = item.type_id;
    item.type_id = select.value;
    typeControl = el("label", {}, "Invoice type", select);
  }
  return el("div", { class: "card" }, name, typeControl,
    radioGroup("new-field-kind", "Kind of value", Object.entries(FIELD_KINDS), item.kind, value => { item.kind = value; }),
    el("label", { class: "inline-control" }, bind(item, "required", el("input", { type: "checkbox" }), null), "Usually on every document"),
    el("label", {}, "How to find it", bind(item, "hint", el("textarea"), null)));
}

function openAddDialog(part, trigger) {
  const project = loadedProject;
  const draft = state.draft;
  const expected = state.config[part];
  const item = newItem(part);
  const errorText = el("p", { class: "dialog-error", role: "alert", hidden: true });
  const submit = el("button", { type: "submit", class: "primary", text: "Add" });
  const form = el("form", {}, el("h2", { id: "add-item-title", text: ADD_LABELS[part] }), newItemInputs(part, item),
    errorText, el("div", { class: "row-end" }, button("Cancel", () => dialog.close()), submit));
  const dialog = el("dialog", { class: "wide add-item-dialog", "aria-labelledby": "add-item-title" }, form);
  dialog.addEventListener("cancel", event => { if (submit.disabled) event.preventDefault(); });
  dialog.addEventListener("close", () => {
    dialog.remove();
    if (state.tab === "setup" && project === loadedProject) {
      (trigger.isConnected ? trigger : document.querySelector(`[data-add="${part}"]`))?.focus();
    }
  }, { once: true });
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (submit.disabled || project !== state.current || draft !== state.draft) return;
    const nameKey = part === "fields" ? "label" : "name";
    item[nameKey] = item[nameKey].trim();
    if (!item[nameKey]) {
      const input = form.querySelector("input");
      input.value = "";
      input.reportValidity();
      return;
    }
    if (part !== "rules") assignDefinitionId(item, part, draft[part]);
    const value = [item, ...expected];
    submit.disabled = true;
    form.inert = true;
    errorText.hidden = true;
    try {
      await api("PUT", `/api/config/${part}`, { value, expected }, project);
      if (project === loadedProject && draft === state.draft) {
        // Add only this record to the saved baseline and retain other edits in the draft.
        state.config[part] = value;
        draft[part].unshift(clone(item));
        if (part === "fields") state.typeFilter = item.type_id;
        renderSetup();
        notify(part === "rules" ? "Rule added to the Inbox." : part === "fields" ? "Field added." : "Invoice type added.");
      }
      dialog.close();
    } catch (error) {
      errorText.textContent = error.message;
      errorText.hidden = false;
    } finally {
      form.inert = false;
      submit.disabled = false;
      if (dialog.open) submit.focus();
    }
  });
  document.body.append(dialog);
  dialog.showModal();
  form.querySelector("input").focus();
}

function typesView() {
  const types = [...state.draft.invoice_types].sort((a, b) => compareLabels(a.name, b.name));
  const cards = types.map((t) => el("div", { class: "card" },
    el("div", { class: "head" }, el("b", { text: t.name }), el("span", { class: "muted small", text: t.id })),
    el("div", { class: "grid2" },
      el("label", {}, "Name", bind(t, "name", el("input", { value: t.name || "" }))),
      el("label", {}, "Budget line", bind(t, "budget_line", el("input", { value: t.budget_line || "" })))),
    el("label", {}, "What this invoice type is (used to recognise it)", bind(t, "description", el("textarea", { value: t.description || "" }))),
    el("label", {}, "What to look for on these documents", bind(t, "what_to_look_for", el("textarea", { value: t.what_to_look_for || "", rows: 5 }))),
    el("label", { style: "display:flex;gap:6px;align-items:center;color:var(--ink)" }, bind(t, "enabled", el("input", { type: "checkbox", checked: t.enabled !== false })), "In use")));
  return el("div", {}, saveBar("invoice_types"), addButton("invoice_types"), el("p", { class: "small muted", text: "These descriptions tell the assistant how to recognise each invoice type and what to look for. Edit them in your own words." }),
    el("div", { class: "cards" }, cards));
}

function fieldsView() {
  const fields = state.draft.fields.filter((f) => !state.typeFilter || f.type_id === state.typeFilter);
  const cards = fields.map((f) => {
    const selected = f.kind || "text";
    const summary = el("summary", { text: `Kind of value: ${FIELD_KINDS[selected] || selected}` });
    const kind = radioGroup(`field-kind-${f.id}`, "Kind of value", Object.entries(FIELD_KINDS), selected, value => {
      f.kind = value;
      summary.textContent = `Kind of value: ${FIELD_KINDS[value]}`;
      markDirty();
    });
    return el("div", { class: "card" },
      el("div", { class: "head" }, el("b", { text: f.label }), el("span", { class: "muted small", text: `${f.type_id} · ${f.name}` })),
      el("div", { class: "grid2" },
        el("label", {}, "Label", bind(f, "label", el("input", { value: f.label || "" }))),
        Object.assign(rememberedDetails(`field:${f.id}`, summary, kind), { className: "field-kind" }),
        el("label", { style: "display:flex;gap:6px;align-items:center;color:var(--ink)" }, bind(f, "required", el("input", { type: "checkbox", checked: f.required })), "Usually on every document")),
      el("label", {}, "How to find it", bind(f, "hint", el("textarea", { id: `hint-${f.id}`, value: f.hint || "" }))));
  });
  return el("div", {},
    el("div", { class: "fields-toolbar" },
      el("div", { class: "fields-toolbar-controls" }, addButton("fields"), filterBar()),
      saveBar("fields")),
    el("p", { class: "small muted", text: "The values the assistant reads from each invoice type." }),
    el("div", { class: "cards" }, cards.length ? cards : el("p", { class: "muted", text: "No fields for this type." })));
}

function learningsView() {
  const items = state.draft.learnings.map((l) => el("div", { class: "card" },
    el("div", { class: "head" }, el("span", { class: "muted small", text: `${l.id} · from ${l.source_invoice || "manual"} · ${when(l.created)}` })),
    el("label", {}, "Tip", bind(l, "text", el("textarea", { value: l.text || "" }))),
    el("label", { style: "display:flex;gap:6px;align-items:center;color:var(--ink)" }, bind(l, "active", el("input", { type: "checkbox", checked: l.active !== false })), "In use")));
  return el("div", {}, saveBar("learnings"), el("p", { class: "small muted", text: "Tips saved with reviews. The assistant follows the tips that are in use. Remove or switch off any that cause problems." }),
    el("div", { class: "cards" }, items.length ? items : el("p", { class: "muted", text: "No tips yet. Add one when you confirm a review." })));
}

function projectView() {
  const p = state.draft.project;
  return el("div", {}, saveBar("project"), el("div", { class: "card" },
    el("label", {}, "Project name", bind(p, "name", el("input", { value: p.name || "" }))),
    el("label", {}, "Funder", bind(p, "funder", el("input", { value: p.funder || "" }))),
    el("div", { class: "grid2" },
      el("label", {}, "Project start", bind(p, "period_start", el("input", { type: "date", value: p.period_start || "" }))),
      el("label", {}, "Project end", bind(p, "period_end", el("input", { type: "date", value: p.period_end || "" }))),
      el("label", {}, "Main currency", bind(p, "currency", el("input", { value: p.currency || "" }))))),
    guidelinesView());
}

// ---------- proposals ----------
function changeText(value) {
  if (value === null || value === undefined || value === "") return "(empty)";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

function proposedInput(change, key, original) {
  const current = change.after[key];
  const label = `Proposed ${key.replaceAll("_", " ")}`;
  if (key === "required" && typeof original === "boolean") {
    return el("label", { class: "inline-control" }, bind(change.after, key, el("input", { type: "checkbox", checked: current }), inboxEdited), label);
  }
  const choices = key === "kind" ? Object.entries(FIELD_KINDS) : key === "severity" ? SEVERITIES : null;
  let input;
  if (choices) {
    input = el("select", {}, choices.map(([v, t]) => el("option", { value: v, text: t })));
    input.value = current;
  } else {
    const value = current !== null && typeof current === "object" ? JSON.stringify(current) : current ?? "";
    input = el(typeof original === "number" ? "input" : "textarea", { value, ...(typeof original === "number" ? { type: "number", step: "any" } : {}) });
  }
  return el("label", {}, label, bind(change.after, key, input, inboxEdited));
}

function changeRow(change) {
  const original = state.config.pending_changes.find(row => row.id === change.id);
  const details = el("div", { class: "setup-row-details" }, el("p", { text: change.reason }),
    el("div", { class: "diff card" }, Object.keys(change.after).map(key => el("div", {},
      el("div", { class: "before", text: `Current ${key.replaceAll("_", " ")}: ${changeText(change.before[key])}` }),
      proposedInput(change, key, original.after[key])))),
    change.evidence?.length ? el("p", { class: "muted small", text: `Based on: ${change.evidence.join(", ")}` }) : null, rowError("change", change.id));
  return setupRow(change.target_name || change.target, `Change to ${change.kind.replace("_", " ")}`, details, decisionButtons(change, "change"), entryKey("change", change.id));
}

function changeType(change) {
  if (change.kind === "invoice_type") return change.target;
  const items = change.kind === "rule" ? state.config.rules : state.config.fields;
  return items.find(item => item.id === change.target)?.type_id;
}

function inboxView() {
  const changes = state.draft.pending_changes.filter(change => matchesType(changeType(change)));
  const visible = new Set(state.config.rules.filter(rule => rule.status === "proposed" && matchesType(rule.type_id)).map(rule => rule.id));
  const rules = state.draft.rules.filter(rule => visible.has(rule.id));
  const entries = [...rules.map(item => ({ kind: "rule", item })), ...changes.map(item => ({ kind: "change", item }))];
  const count = pendingCount();
  return el("div", {}, el("div", { class: "setup-list-head" }, el("h3", { text: "Awaiting review" }),
    el("div", { class: "action-row" }, count ? filterBar() : null, entries.length ? button(`Confirm all (${entries.length})`,
      e => decideInbox(entries, true, true, e.currentTarget), "primary") : null)),
    changes.length || rules.length ? el("div", { class: "setup-list" }, ...changes.map(changeRow), ...rules.map(ruleRow))
      : el("p", { class: "muted", text: count ? "Nothing to review for this invoice type." : "You're all caught up." }));
}
