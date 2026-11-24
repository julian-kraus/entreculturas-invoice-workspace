import { api, button, copyText, el, notify, projectUrl, state, when } from "./workspace.js";
import { describeHistory, historyRow, loadProjectHistory } from "./workspace-tools.js";

const invoiceSelections = new Map();
const historySelections = new Map();

function downloadLink(text, path, project) {
  return el("a", { class: "ghost-link", href: projectUrl(path, project), text });
}

function workbookButton(text, path, project) {
  const download = button(text, async () => {
    download.disabled = true;
    try {
      const data = await api("POST", path, undefined, project);
      window.location.href = projectUrl(data.url, project);
    } catch (error) { notify(error.message, true); }
    finally { download.disabled = false; }
  });
  return download;
}

function exportMessage(text) {
  return el("p", { class: "muted small", text });
}

function downloadText(text, type, filename) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = el("a", { href: url, download: filename });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function resultLabel(value) {
  const text = String(value ?? "").replaceAll("_", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function reviewLabel(status) {
  if (status === "confirmed") return "Reviewed";
  return status === "draft" ? "Draft saved" : "Awaiting confirmation";
}

function csvCell(value) {
  const text = String(value ?? "");
  // Quote each cell and treat formula-like imported text as a literal in spreadsheets.
  const literal = typeof value !== "number" && /^[\s\u200b]*[=+\-@＝＋－＠]|^[\t\r\n]/u.test(text) ? "'" + text : text;
  return '"' + literal.replaceAll('"', '""') + '"';
}

function resultsCsv(data) {
  const header = ["Project", "Project ID", "File", "Invoice ID", "Invoice type", "Check status", "Review status",
    "Checked at", "Reviewed at", "Rules checked", "Category", "Item ID", "Item", "Outcome or status",
    "Value", "Explanation", "Corrected"];
  const context = [data.project_name, data.project, data.file, data.invoice, data.invoice_type, resultLabel(data.status),
    reviewLabel(data.review_status), data.checked_at, data.reviewed_at, data.rules_checked];
  const rows = [];
  if (!data.rules_checked) rows.push(["Summary", "", "No applicable rules", "", "", "", ""]);
  for (const finding of data.findings) {
    rows.push(["Finding", finding.id, finding.name, resultLabel(finding.outcome), "", finding.reason, ""]);
  }
  for (const field of data.fields) {
    rows.push(["Extracted value", field.id, field.name, resultLabel(field.status), field.value, "", field.corrected ? "Yes" : ""]);
  }
  if (!rows.length) rows.push(["Summary", "", "No findings or extracted values", "", "", "", ""]);
  return "\ufeff" + [header, ...rows.map(row => [...context, ...row])]
    .map(row => row.map(csvCell).join(",")).join("\r\n") + "\r\n";
}

function resultsText(data) {
  const context = [
    `Invoice: ${data.file} (${data.invoice})`,
    `Project: ${data.project_name} (${data.project})`,
    data.invoice_type ? `Invoice type: ${data.invoice_type}` : null,
    `Check result: ${resultLabel(data.status)}`,
    `Review status: ${reviewLabel(data.review_status)}`,
    data.checked_at ? `Checked: ${when(data.checked_at)}` : null,
    data.reviewed_at ? `Review saved: ${when(data.reviewed_at)}` : null,
    `Rules checked: ${data.rules_checked}`,
  ].filter(Boolean);
  const findings = data.findings.map(finding => {
    const title = `• ${finding.name} · ${resultLabel(finding.outcome)}`;
    return finding.reason ? `${title}\n  ${finding.reason.replaceAll("\n", "\n  ")}` : title;
  });
  if (!data.rules_checked) findings.unshift("No applicable rules.");
  const fields = data.fields.map(field =>
    `• ${field.name} · ${field.value ?? "—"} (${[resultLabel(field.status), field.corrected ? "Corrected" : ""].filter(Boolean).join(", ")})`);
  return [context.join("\n"), ["Rule findings", ...findings].join("\n"),
    fields.length ? ["Extracted values", ...fields].join("\n") : null].filter(Boolean).join("\n\n");
}

async function loadInvoiceOptions(container, id, project, isCurrent, { confirmedRow = false, finish } = {}) {
  if (!id) {
    container.replaceChildren();
    return;
  }
  const loading = el("p", { class: "muted small", role: "status", text: "Loading invoice exports…" });
  container.replaceChildren(loading);
  const current = () => isCurrent() && loading.isConnected;
  let data;
  try {
    data = await api("GET", `/api/export/invoice/${encodeURIComponent(id)}`, undefined, project);
  } catch (error) {
    if (current()) loading.textContent = error.message;
    return;
  }
  if (!current()) return;
  if (!data.results) {
    container.replaceChildren(exportMessage("Check this invoice to export its results."));
    return;
  }
  const actions = el("div", { class: "action-row" });
  if (data.marked_pdf_url) {
    const pdf = downloadLink("Download marked PDF", data.marked_pdf_url, project);
    if (finish) pdf.addEventListener("click", finish);
    actions.append(pdf);
  }
  actions.append(
    button("Download CSV", () => {
      downloadText(resultsCsv(data.results), "text/csv;charset=utf-8", `${id}-results.csv`);
      finish?.();
    }),
    button("Copy results", () => {
      finish?.();
      void copyText(resultsText(data.results), "Invoice results copied.");
    }));
  if (confirmedRow && data.confirmed_row) actions.append(button("Copy confirmed row", () => {
    const line = data.confirmed_row.map(value => String(value ?? "").replace(/[\t\r\n]+/g, " ")).join("\t");
    void copyText(line, "Confirmed row copied in workbook column order.");
  }));
  if (confirmedRow && data.register_row) actions.append(button("Copy register row", () => {
    const line = data.register_row.map(value => String(value ?? "").replace(/[\t\r\n]+/g, " ")).join("\t");
    void copyText(line, "Register row copied.");
  }));
  container.replaceChildren(actions);
  if (!data.marked_pdf_url) container.append(exportMessage("This invoice has no marked PDF."));
  if (confirmedRow && !data.confirmed_row) container.append(exportMessage("Confirm the invoice review to copy its spreadsheet row."));
}

export function openInvoiceExport(trigger) {
  const { exportInvoice: id, exportProject: project } = trigger.dataset;
  const sameInvoice = () => state.tab === "invoices" && state.current === project && state.selected === id;
  if (!sameInvoice()) return;
  const options = el("div", { class: "export-options" });
  const title = el("h2", { id: "invoice-export-title", text: "Export invoice results" });
  const filename = state.invoices.find(invoice => invoice.id === id)?.file || id;
  const description = el("div", { id: "invoice-export-description" },
    el("p", { text: filename }), exportMessage(state.reviewDirty
      ? "Exports use the last saved results. Your unsaved edits stay open in the review."
      : "Choose a format for the saved results."));
  const close = button("Close", () => dialog.close());
  close.autofocus = true;
  const dialog = el("dialog", { class: "invoice-export-dialog", "aria-labelledby": title.id,
    "aria-describedby": description.id }, title, description, options, el("div", { class: "row-end" }, close));
  dialog.addEventListener("close", () => {
    dialog.remove();
    if (trigger.isConnected) trigger.focus();
    else if (sameInvoice()) document.querySelector("#invoice-detail [data-export-invoice]")?.focus();
  }, { once: true });
  document.body.append(dialog);
  dialog.showModal();
  void loadInvoiceOptions(options, id, project, () => dialog.open && sameInvoice(), { finish: () => dialog.close() });
}

function invoiceExports(invoices, project) {
  const title = el("h3", { text: "Individual invoice" });
  if (!invoices.length) {
    return { section: el("section", { class: "card" }, title,
      exportMessage("Check an invoice to export its results or confirm its review to copy its spreadsheet row.")) };
  }

  const options = el("div", { class: "export-options" });
  const loadSelected = () => loadInvoiceOptions(options, select ? select.value : invoices[0].id, project,
    () => project === state.current && state.tab === "settings" && state.settingsSub === "export", { confirmedRow: true });
  const displayNames = new Map();
  for (const invoice of invoices) displayNames.set(invoice.file, (displayNames.get(invoice.file) || 0) + 1);
  const select = invoices.length > 1 ? el("select", { id: "export-invoice", onchange: () => {
    invoiceSelections.set(project, select.value);
    void loadSelected();
  } }, el("option", { value: "", "data-placeholder": true, text: "Choose an invoice" }),
  invoices.map(invoice => el("option", { value: invoice.id,
    text: displayNames.get(invoice.file) > 1 ? `${invoice.file} (${invoice.id})` : invoice.file }))) : null;
  if (select) {
    const preferred = invoiceSelections.get(project) ?? state.selected ?? "";
    select.value = invoices.some(invoice => invoice.id === preferred) ? preferred : "";
  }
  const invoiceControl = select ? el("label", { for: "export-invoice", class: "export-invoice-label" }, "Checked invoice", select) :
    el("p", { class: "muted", text: `Checked invoice: ${invoices[0].file}` });
  return {
    section: el("section", { class: "card" }, title, invoiceControl, options),
    loadSelected,
  };
}

function historyExportOptions(entries, project) {
  // Count identical records from the oldest entry so new entries cannot shift an existing selection.
  const occurrences = new Map();
  const keyedEntries = entries.slice().reverse().map(entry => {
    const content = JSON.stringify(entry);
    const occurrence = (occurrences.get(content) || 0) + 1;
    occurrences.set(content, occurrence);
    return { entry, key: `${occurrence}:${content}` };
  }).reverse();
  const remembered = historySelections.get(project) || new Set();
  const selected = new Set(keyedEntries.map(({ key }) => key).filter(key => remembered.has(key)));
  historySelections.set(project, selected);
  const download = button("Download selected entries", () => {
    const text = keyedEntries.filter(({ key }) => selected.has(key)).map(({ entry }) =>
      [`${when(entry.at)} · ${entry.action} · ${entry.who}`, ...describeHistory(entry.detail)].join("\n"));
    downloadText([`Project history · ${project}`, ...text].join("\n\n") + "\n", "text/plain;charset=utf-8", `${project}-history.txt`);
  });
  const updateDownload = () => {
    download.disabled = selected.size === 0;
    download.textContent = selected.size ? `Download selected entries (${selected.size})` : "Download selected entries";
  };
  updateDownload();
  const rows = keyedEntries.map(({ entry, key }) => historyRow(entry,
    el("input", { type: "checkbox", checked: selected.has(key), onchange: event => {
      if (event.target.checked) selected.add(key);
      else selected.delete(key);
      updateDownload();
    } })));
  return el("div", { class: "export-options" },
    exportMessage("Select the entries to include in the text file. Expand Details to see what each entry contains."),
    el("div", { class: "action-row" }, download), el("ul", { class: "history" }, rows));
}

function historyExports(project) {
  const options = el("div");
  const history = el("details", { ontoggle: () => {
    if (history.open) void loadProjectHistory(options, project, entries => historyExportOptions(entries, project));
  } }, el("summary", { text: "Select history entries" }), options);
  return el("section", { class: "card" }, el("h3", { text: "Project history" }), history);
}

export async function loadExports() {
  const panel = document.getElementById("export-body");
  const project = state.current;
  if (!project) {
    panel.replaceChildren(el("p", { class: "empty", text: "Choose or create a project to export its files." }));
    return;
  }

  const loading = el("p", { class: "muted", role: "status", text: "Loading project exports…" });
  panel.replaceChildren(loading);
  let invoices = [];
  let errorMessage;
  try {
    invoices = (await api("GET", "/api/invoices", undefined, project)).filter(invoice => invoice.revision);
  } catch (error) { errorMessage = error.message; }
  if (project !== state.current || state.tab !== "settings" ||
      state.settingsSub !== "export" || !loading.isConnected) return;

  const reportButton = workbookButton("Download project workbook", "/api/report", project);
  reportButton.disabled = !invoices.length;
  const invoiceOptions = errorMessage ? null : invoiceExports(invoices, project);
  panel.replaceChildren(
    el("section", { class: "card" }, el("h3", { text: "Project results" }),
      exportMessage(errorMessage || (invoices.length
        ? "One Excel workbook with the project's checked invoices, findings and extracted values."
        : "Check an invoice to create the project workbook.")),
      el("div", { class: "action-row" }, reportButton)),
    invoiceOptions?.section,
    el("section", { class: "card" }, el("h3", { text: "Project setup" }),
      exportMessage("Download an importable setup file to share or an Excel workbook to read. Both include invoice types, fields, rules and tips."),
      el("div", { class: "action-row" },
        downloadLink("Download setup JSON", "/api/export/setup.json", project),
        downloadLink("Download confirmed rules ZIP", "/api/export/rules.zip", project),
        workbookButton("Download setup workbook", "/api/export/setup.xlsx", project))),
    historyExports(project));
  await invoiceOptions?.loadSelected?.();
}
