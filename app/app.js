import {
  api, clone, confirmLeave, copyText, el, hasUnsavedChanges, notify, setSelectOptions, state, uploadFiles, uploadSummary, startRuleDetection, refreshRuleDetection
} from "./workspace.js";
import {
  backToList, clearInvoices, displayInvoiceView, invalidateInvoiceRequests, loadInvoices, selectInvoice
} from "./invoice-review.js";
import {
  clearSetup, loadSetup, renderSetup
} from "./project-setup.js";
import {
  loadHistory, loadSettings
} from "./workspace-tools.js";
import { loadExports, openInvoiceExport } from "./workspace-exports.js";
import { loadInvoiceRulesStatus } from "./invoice-rules-status.js";

async function openInvoiceRules(kind, typeId = "") {
  await showTab("setup");
  if (state.tab !== "setup") return;
  if (kind === "inbox" && document.querySelector('[data-sub="inbox"]').hidden) {
    notify("The Inbox has already been handled.");
    kind = "rules";
  }
  state.setupSub = kind;
  state.typeFilter = typeId || "";
  renderSetup();
  document.querySelector(`[data-sub="${kind}"]`)?.focus();
}

function updateStartingSetup() {
  const source = document.querySelector('[name="starting-setup"]:checked').value;
  const file = document.getElementById("new-project-file");
  document.getElementById("copy-project-label").hidden = source !== "copy";
  document.getElementById("import-project-label").hidden = source !== "import";
  document.getElementById("new-project-copy").required = source === "copy";
  file.required = source === "import";
}

// ---------- projects ----------
async function loadState(selected) {
  const data = await api("GET", "/api/state");
  state.current = selected === undefined ? data.current : selected;
  state.projects = data.projects;
  const select = document.getElementById("project-select");
  setSelectOptions(select,
    ...(state.current ? [] : [el("option", { value: "", "data-placeholder": true, text: "Choose a project" })]),
    ...data.projects.map((p) => el("option", { value: p.slug, text: `${p.name} (${p.invoices} invoices)` })),
  );
  select.value = state.current || "";
  const copy = document.getElementById("new-project-copy");
  setSelectOptions(copy, ...data.projects.map((p) => el("option", { value: p.slug, text: p.name })));
  document.getElementById("copy-project-choice").hidden = !data.projects.length;
  if (!data.projects.length && document.querySelector('[name="starting-setup"]:checked').value === "copy") {
    document.querySelector('[name="starting-setup"][value="standard"]').checked = true;
  }
  updateStartingSetup();

}

async function activateProject(slug, tab) {
  document.getElementById("invoice-upload-results").replaceChildren();
  Object.assign(state, { current: slug, config: null, setupSub: null, typeFilter: "",
    setupDirty: false, reviewDirty: false, settingsDirty: false });
  clearInvoices();
  clearSetup();
  const select = document.getElementById("project-select");
  if (![...select.options].some(option => option.value === slug)) {
    setSelectOptions(select, ...select.options, new Option(slug, slug));
  }
  select.value = slug;
  try { await loadState(slug); }
  finally { await showTab(tab, true); }
}

async function whileSwitchingProject(action) {
  const surfaces = document.querySelectorAll("main, .topbar, .tabs");
  surfaces.forEach(surface => { surface.inert = true; });
  try { await action(); }
  finally { surfaces.forEach(surface => { surface.inert = false; }); }
}

async function switchProject(slug) {
  if (!slug || slug === state.current) return;
  document.getElementById("project-select").value = state.current || "";
  if (!(await confirmLeave())) return;
  await whileSwitchingProject(async () => {
    await api("POST", "/api/project/switch", { slug });
    await activateProject(slug, state.tab);
    notify("Project switched.");
  });
}

// ---------- tabs ----------
async function showTab(tab, force = false) {
  if (!force && tab === state.tab) {
    if (tab === "invoices" && state.selected) await backToList();
    return;
  }
  if (!force && !(await confirmLeave())) return;
  if (tab !== state.tab) {
    if (state.tab === "invoices") invalidateInvoiceRequests();
    state.setupDirty = false;
    state.reviewDirty = false;
    state.settingsDirty = false;
  }
  state.tab = tab;
  for (const button of document.querySelectorAll("[data-tab]")) {
    const active = button.dataset.tab === tab;
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
    document.getElementById(button.getAttribute("aria-controls")).hidden = !active;
  }
  const noProject = !state.current && (tab === "invoices" || tab === "setup");
  document.getElementById("no-project").hidden = !noProject;
  if (noProject) { document.getElementById(`panel-${tab}`).hidden = true; return; }
  if (tab === "settings") { await showSettingsSub(state.settingsSub, true); return; }
  if (tab === "invoices") {
    displayInvoiceView(Boolean(state.selected));
    if (await loadInvoices() && state.selected) await selectInvoice(state.selected, true);
    void loadInvoiceRulesStatus(state.current, openInvoiceRules);
  }
  if (tab === "setup") await loadSetup();
}

async function showSettingsSub(sub, force = false) {
  const previous = state.settingsSub;
  if (!force && (sub === previous || !(await confirmLeave()))) return;
  if (sub !== previous) state.settingsDirty = false;
  state.settingsSub = sub;
  for (const button of document.querySelectorAll("[data-settings-sub]")) {
    if (button.dataset.settingsSub === sub) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  for (const panel of document.querySelectorAll("[data-settings-panel]")) {
    panel.hidden = panel.dataset.settingsPanel !== sub;
  }
  if (sub === "assistant") await loadSettings();
  if (sub === "history") await loadHistory();
  if (sub === "export") await loadExports();
}

// ---------- start ----------
function wire() {
  document.getElementById("invoice-detail").addEventListener("review-inbox", () => {
    openInvoiceRules("inbox").catch(error => notify(error.message, true));
  });
  document.getElementById("invoice-detail").addEventListener("review-rules", event => {
    openInvoiceRules("rules", event.detail.typeId).catch(error => notify(error.message, true));
  });
  document.getElementById("invoice-detail").addEventListener("click", async (event) => {
    const exportAction = event.target.closest("[data-export-invoice]");
    if (exportAction) { openInvoiceExport(exportAction); return; }
    const action = event.target.closest("[data-edit-field]");
    if (!action) return;
    try {
      await showTab("setup");
      if (state.tab !== "setup") return;
      state.setupSub = "fields";
      state.typeFilter = action.dataset.type;
      renderSetup();
      document.getElementById(`hint-${action.dataset.editField}`)?.focus();
    } catch (error) { notify(error.message, true); }
  });
  document.getElementById("project-select").addEventListener("change", (e) => switchProject(e.target.value).catch((err) => notify(err.message, true)));
  for (const button of document.querySelectorAll("[data-tab]")) {
    button.addEventListener("click", () => showTab(button.dataset.tab).catch((err) => notify(err.message, true)));
  }
  for (const button of document.querySelectorAll("[data-sub]")) {
    button.addEventListener("click", async () => {
      if (state.setupDirty && !(await confirmLeave())) return;
      if (state.setupDirty) { state.draft = clone(state.config); state.setupDirty = false; }
      state.editRule = null;
      state.setupSub = button.dataset.sub;
      if (state.draft) renderSetup();
      else { try { await loadSetup(); } catch (error) { notify(error.message, true); } }
    });
  }
  for (const button of document.querySelectorAll("[data-settings-sub]")) {
    button.addEventListener("click", () => showSettingsSub(button.dataset.settingsSub).catch((err) => notify(err.message, true)));
  }
  const dialog = document.getElementById("new-project-dialog");
  const projectForm = document.getElementById("new-project-form");
  const projectInputs = document.getElementById("new-project-inputs");
  const projectResult = document.getElementById("new-project-result");
  const projectCancel = document.getElementById("new-project-cancel");
  const projectSubmit = projectForm.querySelector("[type=submit]");
  const projectTitle = document.getElementById("new-project-title");
  const projectPropose = document.getElementById("new-project-propose");
  function resetProjectDialog() {
    projectForm.reset();
    projectInputs.hidden = false;
    projectInputs.inert = false;
    projectResult.hidden = true;
    projectResult.replaceChildren();
    projectCancel.textContent = "Cancel";
    projectTitle.textContent = "New project";
    projectPropose.hidden = true;
    projectPropose.onclick = null;
    projectSubmit.hidden = false;
    updateStartingSetup();
  }
  let projectBusy = false;
  dialog.addEventListener("cancel", event => { if (projectBusy) event.preventDefault(); });
  dialog.addEventListener("close", resetProjectDialog);
  window.addEventListener("rule-detection", event => {
    const { project, status, message } = event.detail;
    const box = document.getElementById("new-project-detection");
    if (!box || project !== state.current) return;
    box.replaceChildren(el("p", { text: message || "" }));
    if (status === "failed") box.append(el("button", { type: "button", class: "ghost",
      onclick: () => startRuleDetection(project), text: "Retry rule detection" }));
  });
  document.getElementById("new-project-btn").addEventListener("click", async () => { if (await confirmLeave()) dialog.showModal(); });
  document.getElementById("new-project-cancel").addEventListener("click", () => dialog.close());
  document.querySelectorAll('[name="starting-setup"]').forEach(option =>
    option.addEventListener("change", updateStartingSetup));
  document.getElementById("new-project-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const source = document.querySelector('[name="starting-setup"]:checked').value;
      const file = source === "import" ? document.getElementById("new-project-file").files[0] : null;
      const name = document.getElementById("new-project-name").value;
      const guidelines = [...document.getElementById("new-project-guidelines").files];
      const submit = projectSubmit;
      submit.disabled = true;
      projectBusy = true;
      projectCancel.disabled = true;
      try {
        await whileSwitchingProject(async () => {
          let created;
          if (file) {
            let setup;
            try { setup = JSON.parse(await file.text()); } catch { throw new Error("The setup file could not be read."); }
            created = await api("POST", "/api/project/import", { name, setup });
          } else {
            const startingSetup = source === "template" ? { template: true } :
              { copy_rules_from: source === "copy" ? document.getElementById("new-project-copy").value : "" };
            created = await api("POST", "/api/project/create", { name, ...startingSetup });
          }
          const project = created.current;
          projectInputs.hidden = true;
          projectInputs.inert = true;
          projectSubmit.hidden = true;
          projectCancel.textContent = "Done";
          projectTitle.textContent = "Project created";
          projectResult.hidden = false;
          projectResult.replaceChildren(el("p", { role: "status", text: "Project created. Adding guidelines…" }));
          try {
            await activateProject(project, "setup");
          } catch (error) {
            notify(`Project created, but the workspace could not refresh: ${error.message}`, true);
          }
          async function addGuidelines(files, previous = []) {
            projectBusy = true;
            projectCancel.disabled = true;
            let results;
            try {
              results = await uploadFiles(files, "/api/guidelines/upload", project);
            } finally {
              projectBusy = false;
              projectCancel.disabled = false;
            }
            const combined = [...previous, ...results];
            const failed = combined.filter(result => result.error);
            const added = combined.length - failed.length;
            const message = !combined.length ? "You can add guidelines later in Project details." :
              failed.length ? `${added} guideline${added === 1 ? "" : "s"} added · ${failed.length} failed` :
                `${added} guideline${added === 1 ? "" : "s"} added`;
            projectResult.replaceChildren(el("p", { class: "project-result-summary", text: message }));
            if (combined.length) {
              projectResult.append(el("ul", { class: "project-result-files" }, combined.map(result =>
                el("li", { text: result.error ? `${result.file.name} — ${result.error}` : result.file.name }))));
            }
            if (failed.length) {
              projectResult.append(el("button", { type: "button", class: "ghost", text: "Retry failed files", onclick: async event => {
                event.currentTarget.disabled = true;
                await addGuidelines(failed.map(result => result.file), combined.filter(result => !result.error));
                (projectResult.querySelector("button") || (!projectPropose.hidden && projectPropose) || projectCancel).focus();
              } }));
            }
            projectPropose.hidden = !added;
            projectPropose.textContent = "Copy chat request";
            if (results.some(result => !result.error)) await startRuleDetection(project);
            if (added) {
              const request = `Propose invoice rules from the guidelines in project "${project}". Include the source file and page for each proposal.`;
              projectResult.append(el("p", { class: "muted", text: "Rule detection runs in the background using Codex." }),
                el("div", { id: "new-project-detection", role: "status", "aria-live": "polite" }));
              projectPropose.onclick = () => copyText(request, "Request copied. Paste it into your project chat.");
              await refreshRuleDetection(project);
              if (state.current === project && state.tab === "setup") {
                try { await loadSetup(); } catch (error) { notify(error.message, true); }
              }
            }
          }
          await addGuidelines(guidelines);
          projectCancel.focus();
        });
      } finally {
        submit.disabled = false;
        projectBusy = false;
        projectCancel.disabled = false;
      }

    } catch (error) { notify(error.message, true); }
  });
  const drop = document.getElementById("invoice-drop");
  const input = document.getElementById("invoice-upload");
  drop.addEventListener("click", () => input.click());
  input.addEventListener("change", async () => {
    await addInvoices(input.files);
    input.value = "";
  });
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", async (e) => {
    e.preventDefault(); drop.classList.remove("over");
    await addInvoices(e.dataTransfer.files);
  });
  window.addEventListener("beforeunload", (e) => { if (hasUnsavedChanges()) e.preventDefault(); });
}

async function addInvoices(files, previous = []) {
  const project = state.current;
  const results = await uploadFiles(files, "/api/invoices/upload", project);
  if (!results.length || state.current !== project) return;
  const allResults = [...previous, ...results];
  const feedback = document.getElementById("invoice-upload-results");
  if (allResults.some(result => result.error)) {
    feedback.replaceChildren(uploadSummary(allResults,
      failed => addInvoices(failed, allResults.filter(result => !result.error))));
  } else {
    feedback.replaceChildren();
    notify(`${allResults.length} invoice${allResults.length === 1 ? "" : "s"} added.`);
  }
  if (results.some(result => !result.error)) await loadInvoices();
}

async function poll() {
  if (document.hidden || !state.current || state.tab !== "invoices") return;
  await Promise.all([loadInvoices({ poll: true }), loadInvoiceRulesStatus(state.current, openInvoiceRules)]);
}

document.addEventListener("visibilitychange", () => { if (!document.hidden) void poll(); });

(async () => {
  wire();
  try {
    await loadState();
    await showTab("invoices", true);
  } catch (error) { notify(error.message, true); }
  setInterval(poll, 6000);
})();
