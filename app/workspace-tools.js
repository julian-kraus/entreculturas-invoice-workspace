import {
  api, clone, el, notify, state, when
} from "./workspace.js";

// ---------- history ----------
export function describeHistory(value, label = "") {
  if (Array.isArray(value)) {
    return value.flatMap((item) => describeHistory(item, label));
  }
  if (value && typeof value === "object") {
    return Object.entries(value).flatMap(([key, item]) =>
      describeHistory(item, [label, key.replaceAll("_", " ")].filter(Boolean).join(" · ")));
  }
  const text = value === null || value === "" ? "(empty)" : String(value);
  return [label ? `${label}: ${text}` : text];
}

export function historyRow(entry, checkbox) {
  const details = describeHistory(entry.detail || {});
  const title = [el("b", { text: entry.action }), ` · ${when(entry.at)} · ${entry.who}`];
  return el("li", {}, checkbox ? el("label", {}, checkbox, " ", title) : el("span", {}, title),
    details.length ? el("details", {}, el("summary", { text: "Details" }),
      el("ul", {}, details.map((text) => el("li", { text })))) : null);
}

export async function loadProjectHistory(panel, project, render) {
  const loading = el("p", { class: "muted", role: "status", text: "Loading project history…" });
  const subsection = state.settingsSub;
  panel.replaceChildren(loading);
  const current = () => project === state.current && state.tab === "settings" &&
    state.settingsSub === subsection && loading.isConnected;
  let entries;
  try {
    entries = await api("GET", "/api/history?limit=300", undefined, project);
  } catch (error) {
    if (current()) loading.textContent = error.message;
    return;
  }
  if (!current()) return;
  panel.replaceChildren(entries.length
    ? render(entries)
    : el("p", { class: "empty", text: "No activity recorded for this project yet." }));
}

export async function loadHistory() {
  const panel = document.getElementById("history-body");
  const project = state.current;
  if (!project) {
    panel.replaceChildren(el("p", { class: "empty", text: "Choose or create a project to view its history." }));
    return;
  }
  await loadProjectHistory(panel, project, entries =>
    el("ul", { class: "history" }, entries.map(entry => historyRow(entry))));
}

// ---------- assistant settings ----------
const JOB_LABELS = {
  reading: ["Checking invoices", "Reading pages, judging rules, marking evidence. Runs most often, so it decides most of the usage."],
  rules: ["Proposing rules", "Reading funder guidelines. Runs rarely and needs careful reading."],
  other: ["Everything else", "Switching projects, help, questions in the chat."],
};
const MODEL_LABELS = { haiku: "Haiku (fastest, lowest usage)", sonnet: "Sonnet (balanced)", opus: "Opus (most careful, highest usage)" };
const EFFORT_LABELS = { low: "Low", medium: "Medium", high: "High", xhigh: "Extra high", max: "Maximum" };

export async function loadSettings() {
  const panel = document.getElementById("assistant-settings-body");
  const loading = el("p", { class: "muted", role: "status", text: "Loading assistant settings…" });
  panel.replaceChildren(loading);
  const current = () => state.tab === "settings" && state.settingsSub === "assistant" && panel.contains(loading);
  let data;
  try {
    data = await api("GET", "/api/settings");
  } catch (error) {
    if (current()) loading.textContent = error.message;
    return;
  }
  if (!current()) return;

  let saved = JSON.stringify(data.settings);
  const draft = clone(data.settings);
  const dirty = el("span", { class: "dirty", role: "status" });
  const updateDraft = (object, key, value) => {
    object[key] = value;
    state.settingsDirty = JSON.stringify(draft) !== saved;
    dirty.textContent = state.settingsDirty ? "Unsaved changes" : "";
  };
  const select = (options, labels, value, onChange, name) => {
    const node = el("select", { "aria-label": name, onchange: (e) => onChange(e.target.value) },
      options.map((o) => el("option", { value: o, text: labels[o] || o })));
    node.value = value;
    return node;
  };
  const rows = Object.entries(JOB_LABELS).map(([job, [title, help]]) => el("tr", {},
    el("td", {}, el("b", { text: title }), el("div", { class: "small muted", text: help })),
    el("td", {}, select(data.claude_models, MODEL_LABELS, draft.claude[job].model,
      (v) => updateDraft(draft.claude[job], "model", v), `${title} model`)),
    el("td", {}, select(data.efforts, EFFORT_LABELS, draft.claude[job].effort,
      (v) => updateDraft(draft.claude[job], "effort", v), `${title} effort`))));
  const codexModel = el("input", { value: draft.codex.model, placeholder: "Leave empty for the Codex default",
    oninput: (e) => updateDraft(draft.codex, "model", e.target.value.trim()) });
  const save = el("button", { type: "button", class: "primary", text: "Save settings", onclick: async () => {
    const controls = panel.querySelectorAll("input, select, button");
    state.settingsSaving = true;
    controls.forEach(control => { control.disabled = true; });
    save.textContent = "Saving settings…";
    try {
      const response = await api("PUT", "/api/settings", { value: draft });
      saved = JSON.stringify(draft);
      codexModel.value = draft.codex.model;
      state.settingsDirty = false;
      dirty.textContent = "";
      notify(response.changes ? "Settings saved." : "Nothing changed.");
    } catch (error) { notify(error.message, true); }
    finally {
      state.settingsSaving = false;
      controls.forEach(control => { control.disabled = false; });
      save.textContent = "Save settings";
    }
  } });
  panel.replaceChildren(
    el("p", { class: "muted", text: "Choose how much each job may use of your plan. Stronger models and higher effort are more careful but use the limits faster." }),
    el("h3", { text: "Claude Code" }),
    el("div", { class: "table-wrap" }, el("table", { class: "plain" },
      el("thead", {}, el("tr", {}, el("th", { text: "Job" }), el("th", { text: "Model" }), el("th", { text: "Effort" }))),
      el("tbody", {}, rows))),
    el("p", { class: "small muted", text: "Applies from the next request in the chat. If it doesn't, start a new chat." }),
    el("h3", { text: "Codex" }),
    el("p", { class: "small muted", text: "Codex uses one model for the whole workspace. It reads this setting only after you trust this folder in Codex." }),
    el("div", { class: "card" },
      el("div", { class: "grid2" },
        el("label", {}, "Model (as named in the Codex model menu)", codexModel),
        el("label", {}, "Effort", select(data.efforts, EFFORT_LABELS, draft.codex.effort,
          (v) => updateDraft(draft.codex, "effort", v))))),
    el("div", { class: "savebar" }, dirty, save));
}
