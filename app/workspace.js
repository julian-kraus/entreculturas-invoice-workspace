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
  setupSub: "rules",
  setupDirty: false,
  typeFilter: "",
  statusFilter: "confirmed",
};

// ---------- helpers ----------
export function el(tag, attrs = {}, ...children) {
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

export async function confirmLeave() {
  if (state.setupDirty || state.reviewDirty) return askConfirm("You have unsaved changes. Leave without saving?");
  return true;
}

export async function copyText(text, message) {
  try {
    await navigator.clipboard.writeText(text);
    notify(message);
  } catch {
    const value = el("textarea", { value: text, readOnly: true, "aria-label": "Text to copy", rows: 6 });
    const dialog = el("dialog", { class: "wide" }, el("h2", { text: "Copy text" }), value,
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

export function promptButton(label, request) {
  return button(label, () => copyText(request, "Request copied. Paste it into your project chat."));
}

export async function uploadFiles(files, endpoint) {
  let added = 0;
  const project = state.current;
  for (const file of files) {
    try {
      const data = await readFileAsDataUrl(file);
      if (state.current !== project) break;
      await api("POST", endpoint, { name: file.name, data }, project);
      added += 1;
    } catch (error) { notify(`${file.name}: ${error.message}`, true); }
  }
  return added;
}
