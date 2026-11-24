import {
  api, clone, confirmLeave, copyText, el, notify, projectUrl, state, uploadFiles
} from "./workspace.js";
import {
  backToList, displayInvoiceView, loadInvoices, renderInvoiceList, selectInvoice
} from "./invoice-review.js";
import {
  loadSetup, renderSetup
} from "./project-setup.js";
import {
  loadHistory, loadSettings, loadTests
} from "./workspace-tools.js";

// ---------- projects ----------
async function loadState(selected) {
  const data = await api("GET", "/api/state");
  state.current = selected === undefined ? data.current : selected;
  state.projects = data.projects;
  const select = document.getElementById("project-select");
  select.replaceChildren(
    ...(state.current ? [] : [el("option", { value: "", text: "Choose a project" })]),
    ...data.projects.map((p) => el("option", { value: p.slug, text: `${p.name} (${p.invoices} invoices)` })),
  );
  select.value = state.current || "";
  const copy = document.getElementById("new-project-copy");
  copy.replaceChildren(el("option", { value: "", text: "Standard invoice fields" }),
    ...data.projects.map((p) => el("option", { value: p.slug, text: p.name })));
}

async function activateProject(slug, tab) {
  Object.assign(state, { current: slug, invoices: [], selected: null, detail: null, config: null,
    draft: null, setupSub: "rules", typeFilter: "", statusFilter: "confirmed", editRule: null,
    setupDirty: false, reviewDirty: false });
  state.detailRequest++;
  await loadState(slug);
  await showTab(tab, true);
}

async function whileSwitchingProject(action) {
  const surfaces = document.querySelectorAll("main, .topbar, .tabs");
  surfaces.forEach(surface => { surface.inert = true; });
  try { await action(); }
  finally { surfaces.forEach(surface => { surface.inert = false; }); }
}

async function switchProject(slug) {
  if (!slug || slug === state.current) return;
  if (!(await confirmLeave())) { document.getElementById("project-select").value = state.current || ""; return; }
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
  if (tab !== state.tab) { state.setupDirty = false; state.reviewDirty = false; }
  state.tab = tab;
  for (const button of document.querySelectorAll("[data-tab]")) {
    if (button.dataset.tab === tab) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  for (const name of ["invoices", "setup", "tests", "history", "settings"]) {
    document.getElementById(`panel-${name}`).hidden = name !== tab;
  }
  const noProject = !state.current && tab !== "settings";
  document.getElementById("no-project").hidden = !noProject;
  if (noProject) { document.getElementById(`panel-${tab}`).hidden = true; return; }
  if (tab === "settings") { await loadSettings(); return; }
  if (tab === "invoices") {
    displayInvoiceView(Boolean(state.selected));
    await loadInvoices();
    if (state.selected) await selectInvoice(state.selected, true);
  }
  if (tab === "setup") await loadSetup();
  if (tab === "tests") await loadTests();
  if (tab === "history") await loadHistory();
}

// ---------- start ----------
function wire() {
  document.getElementById("invoice-detail").addEventListener("click", async (event) => {
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
      const form = event.currentTarget;
      const submit = form.querySelector("[type=submit]");
      submit.disabled = true;
      try {
        await whileSwitchingProject(async () => {
          let created;
          if (file) {
            let setup;
            try { setup = JSON.parse(await file.text()); } catch { throw new Error("The setup file could not be read."); }
            created = await api("POST", "/api/project/import", { name, setup });
          } else {
            created = await api("POST", "/api/project/create", { name, copy_rules_from: document.getElementById("new-project-copy").value });
          }
          dialog.close();
          form.reset();
          await activateProject(created.current, "setup");
        });
      } finally { submit.disabled = false; }
      notify("Project created. Add guidelines or review the rules.");
    } catch (error) { notify(error.message, true); }
  });
  const drop = document.getElementById("invoice-drop");
  const input = document.getElementById("invoice-upload");
  drop.addEventListener("click", () => input.click());
  document.getElementById("pending-copy").addEventListener("click", () => {
    const ids = state.invoices.filter(i => !i.checked_at).map(i => i.id);
    if (ids.length) copyText(`Check these invoices in project "${state.current}": ${ids.map(id => JSON.stringify(id)).join(", ")}. Use the confirmed rules for that project.`, "Batch request copied. Paste it into your project chat.");
  });
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
      window.location.href = projectUrl(data.url);
    } catch (error) { notify(error.message, true); }
  });
  window.addEventListener("beforeunload", (e) => { if (state.setupDirty || state.reviewDirty) e.preventDefault(); });
}

async function afterInvoiceUpload(count) {
  if (!count) return;
  notify(`Added ${count} invoice(s). Open an invoice or copy the batch request.`);
  await loadInvoices();
}

async function poll() {
  if (document.hidden || !state.current || state.tab !== "invoices") return;
  try {
    const selected = state.selected;
    const previous = state.invoices;
    const next = await api("GET", "/api/invoices");
    if (state.tab !== "invoices" || JSON.stringify(next) === JSON.stringify(previous)) return;
    state.invoices = next;
    renderInvoiceList();
    const selectedItem = list => list.find(i => i.id === selected);
    if (selected && selected === state.selected && !state.reviewDirty &&
        JSON.stringify(selectedItem(next)) !== JSON.stringify(selectedItem(previous))) await selectInvoice(selected, true);
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
