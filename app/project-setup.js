import {
  api, button, clone, confirmLeave, el, notify, pill, projectUrl, promptButton, state, uploadFiles, when
} from "./workspace.js";

const CHECK_LABEL = {
  visual: "Judged by looking at the document",
  required: "Value must be present",
  date_in_period: "Date inside the project period",
  range: "Number within a range",
  enum: "One of a list of values",
  regex: "Follows a pattern",
};

// ---------- setup ----------
export async function loadSetup() {
  const [config] = await Promise.all([api("GET", "/api/config"), loadProposals()]);
  if (state.tab !== "setup") return;
  state.config = config;
  state.draft = clone(state.config);
  state.setupDirty = false;
  document.getElementById("guidelines-box").replaceChildren(guidelinesView());
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

export function renderSetup() {
  if (!state.draft) return;
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

function guidelinesView() {
  const files = state.config.guidelines || [];
  const picker = el("input", { type: "file", accept: ".pdf,.txt,.md", multiple: true, hidden: true,
    onchange: async e => {
      if (!(await confirmLeave())) return;
      const n = await uploadFiles(e.target.files, "/api/guidelines/upload");
      if (n) { notify(`Added ${n} guideline file(s).`); await loadSetup(); }
    } });
  return el("section", { class: "guidelines" },
    el("h3", { text: "Funder guidelines" }),
    files.length ? el("ul", {}, files.map(name => el("li", { text: name }))) :
      el("p", { class: "muted", text: state.config.rules.length ? "This setup contains rules. Add the source guidelines here so staff can verify them." : "Add the project guidelines, then ask the assistant to propose rules." }),
    el("div", { class: "action-row" }, picker, button("Add guidelines", () => picker.click()),
      files.length ? promptButton("Copy rule proposal request", `Propose invoice rules from the guidelines in project "${state.current}". Include the source file and page for each proposal.`) : null));
}

function rulesView() {
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
    check.addEventListener("change", () => { state.editRule = rule.id; renderSetup(); });
    const severity = bind(rule, "severity", el("select", {}, el("option", { value: "error", text: "Error: fails the invoice" }), el("option", { value: "warning", text: "Warning: needs a look" })));
    severity.value = rule.severity;
    const typeSelect = bind(rule, "type_id", el("select", {}, el("option", { value: "ALL", text: "Every invoice type" }), typeOptions(false)));
    typeSelect.value = rule.type_id;
    typeSelect.addEventListener("change", () => { rule.field = ""; state.editRule = rule.id; renderSetup(); });
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
    return el("details", { class: `rule-card ${rule.status}`, open: rule.id === state.editRule },
      el("summary", {}, el("b", { text: rule.name || rule.id }), " ", pill(rule.status, rule.status)),
      el("div", { class: "card" }, statusButtons,
      el("label", {}, "Name", bind(rule, "name", el("input", { value: rule.name || "" }))),
      el("label", {}, "What the rule requires", bind(rule, "description", el("textarea", { value: rule.description || "" }))),
      el("label", {}, "Where to look (helps the assistant)", bind(rule, "hint", el("textarea", { value: rule.hint || "" }))),
      grid,
      rule.reason ? el("p", { class: "small muted", text: `Why the assistant proposed it: ${rule.reason}` }) : null,
      el("label", {}, "Source (document and page)", bind(rule, "source", el("input", { value: rule.source || "" }))),
      el("label", { style: "display:flex;gap:6px;align-items:center;color:var(--ink)" }, bind(rule, "enabled", el("input", { type: "checkbox", checked: rule.enabled !== false })), "In use")));
  });
  const addButton = el("button", { type: "button", class: "ghost", onclick: () => {
    let n = 1; const ids = new Set(state.draft.rules.map((r) => r.id));
    while (ids.has(`M${String(n).padStart(3, "0")}`)) n += 1;
    state.draft.rules.unshift({ id: `M${String(n).padStart(3, "0")}`, type_id: state.typeFilter || "ALL", name: "New rule", check: "visual",
      field: null, value: "", severity: "error", description: "", hint: "", source: "", status: "proposed", enabled: true });
    state.editRule = state.draft.rules[0].id; state.statusFilter = "all"; markDirty(); renderSetup();
  } }, "Add a rule");
  const counts = ["confirmed", "proposed", "rejected"].map((s) => `${state.draft.rules.filter((r) => r.status === s).length} ${s}`).join(" · ");
  return el("div", {}, el("div", { class: "toolbar" }, filterBar(true), el("span", { class: "muted small", text: counts }), addButton),
    el("p", { class: "small muted", text: "Only confirmed rules are applied when invoices are checked." }),
    el("div", { class: "cards" }, cards.length ? cards : el("p", { class: "muted", text: "No rules match." })), saveBar(["rules"]));
}

function addDefinitionForm(kind) {
  const addingField = kind === "field";
  const label = addingField ? "field" : "invoice type";
  if (addingField && !state.draft.invoice_types.length) return el("p", { text: "Add an invoice type before defining its fields." });
  const name = el("input", { required: true, maxlength: "80" });
  const type = addingField ? el("select", {}, typeOptions(false)) : null;
  if (type && state.typeFilter) type.value = state.typeFilter;
  const form = el("form", { class: "definition-form" }, el("label", {}, "Name", name),
    type ? el("label", {}, "Invoice type", type) : null,
    el("button", { type: "submit", class: "ghost", text: `Add ${label}` }));
  form.addEventListener("submit", event => {
    event.preventDefault();
    const title = name.value.trim();
    if (!title) { name.focus(); return; }
    const items = addingField ? state.draft.fields : state.draft.invoice_types;
    const base = title.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || kind;
    const taken = new Set(items.map(i => addingField ? i.name : i.id));
    let technical = addingField ? base : base.toUpperCase();
    let count = 1;
    while (taken.has(technical)) technical = `${addingField ? base : base.toUpperCase()}_${++count}`;
    if (addingField) {
      let index = items.length + 1;
      while (items.some(i => i.id === `F${index}`)) index++;
      items.unshift({ id: `F${index}`, type_id: type.value, name: technical, label: title, kind: "text", required: false, hint: "" });
      state.typeFilter = type.value;
    } else items.unshift({ id: technical, name: title, enabled: true, budget_line: "", description: "", what_to_look_for: "" });
    markDirty(); renderSetup();
  });
  return el("details", { class: "add-definition" }, el("summary", { text: `Add ${label}` }), form);
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
  return el("div", {}, addDefinitionForm("type"), el("p", { class: "small muted", text: "These descriptions tell the assistant how to recognise each invoice type and what to look for. Edit them in your own words." }),
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
      el("label", {}, "How to find it", bind(f, "hint", el("textarea", { id: `hint-${f.id}`, value: f.hint || "" }))));
  });
  return el("div", {}, addDefinitionForm("field"), filterBar(false), el("p", { class: "small muted", text: "The values the assistant reads from each invoice type." }),
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
    if (!(await confirmLeave())) return;
    try {
      await api("POST", `/api/proposals/${encodeURIComponent(id)}`, { approve });
      notify(approve ? "Approved and applied. It is in the history." : "Rejected.");
      await loadSetup();
    } catch (error) { notify(error.message, true); }
  };
  const decideRule = async (id, status) => {
    if (!(await confirmLeave())) return;
    try {
      await api("POST", `/api/rules/${encodeURIComponent(id)}/status`, { status });
      notify(status === "confirmed" ? "Rule confirmed. It applies from the next check." : "Rule rejected.");
      await loadSetup();
    } catch (error) { notify(error.message, true); }
  };
  const exportBar = el("div", { class: "row-end small" },
    el("a", { href: projectUrl("/api/export/setup.json"), class: "ghost-link", text: "Download setup to share" }),
    el("button", { type: "button", class: "ghost", onclick: async () => {
      try { const d = await api("POST", "/api/export/setup.xlsx"); window.location.href = projectUrl(d.url); } catch (e) { notify(e.message, true); }
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
