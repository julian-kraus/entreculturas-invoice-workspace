export const state = {
  tab: "invoices",
  current: null,
  projects: [],
  invoices: [],
  selected: null,
  detail: null,
  detailRequest: 0,
  listScroll: 0,
  reviewView: "findings",
  reviewDirty: false,
  config: null,
  draft: null,
  setupSub: null,
  setupDirty: false,
  inboxBusy: false,
  settingsSub: "export",
  settingsDirty: false,
  settingsSaving: false,
  typeFilter: "",
  editRule: null,
};

// ---------- helpers ----------
const labelCollator = new Intl.Collator(undefined, { sensitivity: "base", numeric: true });

export function compareLabels(left, right) {
  return labelCollator.compare(left, right);
}

function sortSelectOptions(select) {
  const selected = select.selectedOptions[0];
  const options = [...select.options].sort((a, b) => {
    const promptFirst = Number(b.hasAttribute("data-placeholder")) - Number(a.hasAttribute("data-placeholder"));
    return promptFirst || compareLabels(a.label, b.label);
  });
  select.replaceChildren(...options);
  select.selectedIndex = selected ? options.indexOf(selected) : -1;
}

export function setSelectOptions(select, ...options) {
  const previous = select.value;
  select.replaceChildren(...options);
  if ([...select.options].some(option => option.value === previous)) select.value = previous;
  sortSelectOptions(select);
}

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key === "value") {
      if (tag !== "select") node.value = value;
    }
    else if (key === "checked") node.checked = Boolean(value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  if (tag === "select") {
    sortSelectOptions(node);
    if (attrs.value != null && attrs.value !== false) node.value = attrs.value;
  }
  return node;
}

export function projectUrl(path, project = state.current) {
  const url = new URL(path, window.location.origin);
  if (project) url.searchParams.set("project", project);
  return url.pathname + url.search;
}

const globalRoutes = new Set(["/api/state", "/api/settings", "/api/project/create", "/api/project/switch", "/api/project/import"]);

export async function api(method, path, body, project = state.current) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const global = globalRoutes.has(path);
  if (!global && !project) throw new Error("Choose a project first.");
  if (!global && project !== state.current) throw new Error("The project changed. Open the record again.");
  const response = await fetch(global ? path : projectUrl(path, project), options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  if (!global && project !== state.current) throw new Error("The project changed. Open the record again.");
  return data;
}

let noticeTimer = null;
export function notify(message, isError = false) {
  const box = document.getElementById("notice");
  box.textContent = message;
  box.className = isError ? "notice error" : "notice";
  box.hidden = false;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => { box.hidden = true; }, isError ? 9000 : 4000);
}

export function pill(text, kind) {
  return el("span", { class: `pill ${String(kind || "").replace(/\s+/g, "-")}`, text });
}

export function when(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function clone(value) { return JSON.parse(JSON.stringify(value)); }

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error(`Could not read ${file.name}`));
    reader.readAsDataURL(file);
  });
}

export function askConfirm(message, yesLabel = "Leave without saving") {
  const dialog = document.getElementById("confirm-dialog");
  document.getElementById("confirm-text").textContent = message;
  document.getElementById("confirm-no").textContent = yesLabel === "Leave without saving" ? "Stay" : "Cancel";
  document.getElementById("confirm-yes").textContent = yesLabel;
  return new Promise((resolve) => {
    const finish = (answer) => { dialog.close(); resolve(answer); };
    document.getElementById("confirm-yes").onclick = () => finish(true);
    document.getElementById("confirm-no").onclick = () => finish(false);
    dialog.oncancel = () => resolve(false);
    dialog.showModal();
  });
}

export function hasUnsavedChanges() {
  return state.setupDirty || state.inboxBusy || state.reviewDirty || state.settingsDirty;
}

export async function confirmLeave() {
  if (state.inboxBusy) return false;
  if (state.settingsSaving) {
    notify("Settings are being saved.");
    return false;
  }
  if (hasUnsavedChanges()) return askConfirm("You have unsaved changes. Leave without saving?");
  return true;
}

export async function copyText(text, message) {
  try {
    await navigator.clipboard.writeText(text);
    notify(message);
  } catch {
    const value = el("textarea", { value: text, readOnly: true, "aria-label": "Text to copy", rows: 6 });
    const dialog = el("dialog", { class: "wide", "aria-labelledby": "copy-dialog-title" }, el("h2", { id: "copy-dialog-title", text: "Copy text" }), value,
      button("Close", () => dialog.close()));
    dialog.addEventListener("close", () => dialog.remove(), { once: true });
    document.body.append(dialog);
    dialog.showModal();
    value.focus();
    value.select();
  }
}

export function button(text, onclick, style = "ghost") {
  return el("button", { type: "button", class: style, onclick, text });
}

export function radioGroup(name, label, choices, selected, onSelect) {
  return el("fieldset", { class: "choice-group" }, el("legend", { text: label }),
    choices.map(([value, text]) => el("label", {},
      el("input", { type: "radio", name, value, checked: selected === value, onchange: () => onSelect(value) }), text)));
}

export function promptButton(label, request) {
  return button(label, () => copyText(request, "Request copied. Paste it into your project chat."));
}

export async function uploadFiles(files, endpoint, project = state.current) {
  const results = [];
  for (const file of files) {
    try {
      const data = await readFileAsDataUrl(file);
      if (state.current !== project) throw new Error("The selected project changed.");
      await api("POST", endpoint, { name: file.name, data }, project);
      results.push({ file, error: null });
    } catch (error) { results.push({ file, error: error.message }); }
  }
  return results;
}

export function uploadSummary(results, retry) {
  const failed = results.filter(result => result.error);
  const added = results.length - failed.length;
  const panel = el("section", { class: "card upload-results", role: "status" },
    el("p", { text: `${added} added, ${failed.length} failed.` }),
    el("ul", {}, results.map(result => el("li", { text: `${result.file.name} — ${result.error || "Added"}` }))));
  if (failed.length) panel.append(button("Retry failed files", async event => {
    event.currentTarget.disabled = true;
    await retry(failed.map(result => result.file));
  }));
  panel.append(button("Dismiss", () => panel.remove()));
  return panel;
}

// Detection jobs remain scoped to their project while the user navigates.
const detectionJobs = new Map();
const detectionPending = new Set();

function announceDetection(project, result) {
  detectionJobs.set(project, result);
  window.dispatchEvent(new CustomEvent("rule-detection", { detail: { project, ...result } }));
}

export async function refreshRuleDetection(project) {
  if (!project || state.current !== project) return;
  try {
    const result = await api("GET", "/api/rule-detection/status", undefined, project);
    announceDetection(project, result);
    if (result.status === "running" && !detectionPending.has(project)) {
      detectionPending.add(project);
      setTimeout(async () => {
        detectionPending.delete(project);
        if (state.current === project) await refreshRuleDetection(project);
      }, 3000);
    }
  } catch (error) {
    if (state.current === project) announceDetection(project, { status: "failed", message: error.message });
  }
}

export async function startRuleDetection(project) {
  if (!project || state.current !== project) return;
  try {
    const result = await api("POST", "/api/rule-detection/start", {}, project);
    announceDetection(project, result);
    await refreshRuleDetection(project);
  } catch (error) {
    if (state.current === project) {
      await refreshRuleDetection(project);
      if (detectionJobs.get(project)?.status !== "running")
        announceDetection(project, { status: "failed", message: error.message });
    }
  }
}
