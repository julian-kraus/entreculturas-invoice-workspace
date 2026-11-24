import {
  api, button, clone, el, notify, pill, state, when
} from "./workspace.js";

// ---------- tests ----------
export async function loadTests() {
  const panel = document.getElementById("panel-tests");
  const [data, invoices] = await Promise.all([api("GET", "/api/evaluation"), api("GET", "/api/invoices")]);
  const run = data.latest_run;
  const parts = [el("h2", { text: "Test invoices" }),
    el("p", { class: "muted", text: "Invoices your team already checked, with the right answers saved. To measure the current setup, ask in the chat: “Run the test invoices”." }),
    el("p", { class: "small", text: `${data.test_invoices.length} test invoice(s), ${data.test_invoices.filter((t) => t.aside).length} kept aside.` })];
  const eligible = invoices.filter(invoice => invoice.reviewed && !invoice.test_invoice);
  if (eligible.length) {
    const choice = el("select", { "aria-label": "Confirmed invoice" }, eligible.map(i => el("option", { value: i.id, text: i.file })));
    const aside = el("input", { type: "checkbox" });
    parts.push(el("div", { class: "toolbar" }, choice, el("label", {}, aside, " Keep aside for independent evaluation"),
      button("Add to test invoices", async () => {
        try { await api("POST", `/api/evaluation/add/${encodeURIComponent(choice.value)}`, { aside: aside.checked }); await loadTests(); }
        catch (error) { notify(error.message, true); }
      })));
  }
  if (!data.test_invoices.length) {
    parts.push(el("p", { class: "empty", text: "No test invoices yet. Confirm a reviewed invoice to add it here." }));
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
function describeHistory(value, label = "") {
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

export async function loadHistory() {
  const panel = document.getElementById("panel-history");
  const project = state.current;
  const entries = await api("GET", "/api/history?limit=300");
  if (project !== state.current) return;
  const selected = new Set();
  const save = el("button", { type: "button", class: "ghost", disabled: true, text: "Download selected entries",
    onclick: () => {
      const paragraphs = entries.flatMap((entry, index) => selected.has(index)
        ? [[`${when(entry.at)} · ${entry.action} · ${entry.who}`, ...describeHistory(entry.detail)].join("\n")]
        : []);
      const file = new Blob([[`Project history · ${project}`, ...paragraphs].join("\n\n") + "\n"], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(file);
      const link = el("a", { href: url, download: `${project}-history.txt` });
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } });
  const rows = entries.map((entry, index) => {
    const details = describeHistory(entry.detail || {});
    const checkbox = el("input", { type: "checkbox", onchange: (event) => {
      if (event.target.checked) selected.add(index);
      else selected.delete(index);
      save.disabled = selected.size === 0;
      save.textContent = selected.size ? `Download selected entries (${selected.size})` : "Download selected entries";
    } });
    return el("li", {}, el("label", {}, checkbox, " ", el("b", { text: entry.action }),
      ` · ${when(entry.at)} · ${entry.who}`), details.length ? el("details", {},
      el("summary", { text: "Details" }), el("ul", {}, details.map((text) => el("li", { text })))) : null);
  });
  panel.replaceChildren(el("h2", { text: "Project history" }), entries.length
    ? el("div", {}, el("p", { class: "muted", text: "Select the entries to include in a feedback file. Expand Details to see what each entry contains." }),
      save, el("ul", { class: "history" }, rows))
    : el("p", { class: "empty", text: "No activity recorded for this project yet." }));
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
