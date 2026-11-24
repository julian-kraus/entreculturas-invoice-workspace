"""The workspace page: a small local web server for reviewing invoices and editing the setup.

It only listens on this computer (127.0.0.1). It never calls an AI: checking invoices and
proposing rules happen in the chat. Everything is saved in projects/<project>/.

Usage:
  ./.tools/uv run app/server.py [--port 8790]
"""

from __future__ import annotations

import argparse
import base64
import binascii
import errno
import json
import mimetypes
import os
import tempfile
import webbrowser
from copy import deepcopy
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import results as result_store  # noqa: E402
from common import (  # noqa: E402
    INVOICE_SUFFIXES, PROJECTS, WorkspaceError, check_id, selected_project, existing_project, invoice_display_name, invoice_files, list_projects,
    load_config, load_json, log, now_iso, project_dir, read_history, result_path, save_json,
    set_current_project, set_dirs, storage_slug, work_dir,
)
from evaluate import add as add_test_invoice, score, truth_dir  # noqa: E402
from marks import marks_for  # noqa: E402
from pages import render  # noqa: E402
from project import create, export_setup, import_setup, project_summary  # noqa: E402
from proposals import decide as decide_proposal, pending as pending_proposals  # noqa: E402
from report import build as build_report, build_setup  # noqa: E402
from sync_skills import CLAUDE_MODELS, EFFORTS, SETTINGS_FILE, load_settings, sync, validate  # noqa: E402

APP = Path(__file__).resolve().parent
MAX_BODY = 40 * 1024 * 1024
CONFIG_PARTS = {
    "project": ("project.json", dict),
    "invoice_types": ("invoice_types.json", list),
    "fields": ("fields.json", list),
    "rules": ("rules.json", list),
    "learnings": ("learnings.json", list),
}
GUIDELINE_SUFFIXES = {".pdf", ".txt", ".md"}


def describe_changes(before, after) -> dict:
    """A short, readable before/after for the history, item by item."""
    if isinstance(before, dict) or isinstance(after, dict):
        before, after = before or {}, after or {}
        keys = sorted(set(before) | set(after))
        return {"changed": [{"what": k, "before": before.get(k), "after": after.get(k)}
                            for k in keys if before.get(k) != after.get(k)]}
    old = {item.get("id"): item for item in before or [] if isinstance(item, dict)}
    new = {item.get("id"): item for item in after or [] if isinstance(item, dict)}
    changes = []
    for item_id in sorted(set(old) | set(new), key=str):
        a, b = old.get(item_id), new.get(item_id)
        if a == b:
            continue
        if a is None:
            changes.append({"what": item_id, "change": "added", "after": b})
        elif b is None:
            changes.append({"what": item_id, "change": "removed", "before": a})
        else:
            keys = sorted(set(a) | set(b))
            changes.append({"what": item_id, "change": "edited",
                            "before": {k: a.get(k) for k in keys if a.get(k) != b.get(k)},
                            "after": {k: b.get(k) for k in keys if a.get(k) != b.get(k)}})
    return {"changed": changes}


def invoice_list(slug: str) -> list[dict]:
    tested = {p.stem for p in truth_dir(slug).glob("*.json")}
    items = []
    for invoice_id, path in invoice_files(slug).items():
        stored = load_json(result_path(slug, invoice_id))
        result = result_store.record_for_display(stored) if stored else None
        review = (result or {}).get("review") or {}
        items.append({
            "id": invoice_id, "file": invoice_display_name(slug, invoice_id, source=path),
            "revision": result_store.revision(result) if result else None,
            "pending_recheck": ((stored or {}).get("pending_recheck") or {}).get("revision"),
            "status": (result or {}).get("status", "not checked"),
            "checked_at": (result or {}).get("checked_at"),
            "summary": (result or {}).get("summary", ""),
            "reviewed": review.get("status") == "confirmed",
            "test_invoice": invoice_id in tested,
        })
    return items


def page_images(slug: str, invoice_id: str) -> list[str]:
    folder = work_dir(slug, invoice_id)
    pages = sorted((p for p in folder.glob("page-*.png") if p.stem.count("-") == 1),
                   key=lambda p: int(p.stem.split("-")[1])) if folder.exists() else []
    if not pages:
        render(slug, invoice_id, "invoices")
        pages = sorted((p for p in folder.glob("page-*.png") if p.stem.count("-") == 1),
                       key=lambda p: int(p.stem.split("-")[1]))
    return [file_url(p, slug) for p in pages]


def file_url(path: Path | str, slug: str, *, download: bool = False) -> str:
    relative = (ROOT / path).resolve().relative_to(ROOT.resolve()).as_posix()
    query = {"project": slug}
    if download:
        query["download"] = "1"
    return "/files/" + quote(relative) + "?" + urlencode(query)


def save_settings(body: dict) -> dict:
    """Save which model and effort each job uses, and write them into the Claude Code and Codex files."""
    before = load_settings()
    wanted = body.get("value")
    if not isinstance(wanted, dict):
        raise WorkspaceError("Expected the assistant settings.")
    settings = deepcopy(before)
    for provider, value in wanted.items():
        if provider not in settings or not isinstance(value, dict):
            raise WorkspaceError("Unknown assistant settings.")
        groups = [(settings["codex"], value)] if provider == "codex" else [
            (settings["claude"].get(job), options) for job, options in value.items()
        ]
        for target, options in groups:
            if (target is None or not isinstance(options, dict) or not options.keys() <= target.keys()
                    or any(not isinstance(v, str) for v in options.values())):
                raise WorkspaceError("Invalid model or effort setting.")
            target.update(options)
    problems = validate(settings)
    if problems:
        raise WorkspaceError(" ".join(problems))
    # Sync parses all configuration and constructs every destination before writing.
    sync(settings)
    save_json(SETTINGS_FILE, settings)
    changes = describe_changes(
        {f"Claude {job}": f"{v['model']}, {v['effort']}" for job, v in before["claude"].items()}
        | {"Codex": f"{before['codex']['model'] or 'default'}, {before['codex']['effort']}"},
        {f"Claude {job}": f"{v['model']}, {v['effort']}" for job, v in settings["claude"].items()}
        | {"Codex": f"{settings['codex']['model'] or 'default'}, {settings['codex']['effort']}"})
    try:
        if changes["changed"]:
            log(selected_project(), body.get("by") or "staff", "assistant settings changed", changes)
    except WorkspaceError:
        pass
    return {"settings": settings, "changes": len(changes["changed"])}


def set_rule_status(slug: str, rule_id: str, status: str, who: str) -> dict:
    if status not in ("confirmed", "proposed", "rejected"):
        raise WorkspaceError("Unknown status.")
    path = project_dir(slug) / "rules.json"
    rules = load_json(path, [])
    rule = next((r for r in rules if r.get("id") == rule_id), None)
    if rule is None:
        raise WorkspaceError("This rule no longer exists.")
    before = rule.get("status")
    rule["status"] = status
    save_json(path, rules)
    log(slug, who, "rules edited", {"changed": [{"what": rule_id, "change": "edited",
                                                  "before": {"status": before}, "after": {"status": status}}]})
    return rule


def save_upload(folder: Path, body: dict, allowed: set[str], slug: str | None = None) -> dict:
    name = Path(str(body.get("name", "")).replace("\\", "/")).name
    suffix = Path(name).suffix.lower()
    if suffix not in allowed:
        raise WorkspaceError(f"Files of type '{suffix or 'unknown'}' can't be added here.")
    try:
        data = base64.b64decode(str(body.get("data", "")).split(",")[-1], validate=True)
    except (ValueError, binascii.Error) as error:
        raise WorkspaceError("The uploaded file could not be read.") from error
    if not data:
        raise WorkspaceError("The file is empty.")
    folder.mkdir(parents=True, exist_ok=True)
    taken = set(invoice_files(slug)) if slug else set()
    if slug:
        _, records = set_dirs(slug, "invoices")
        taken.update(p.stem for p in records.glob("*.json"))
    stem = storage_slug(Path(name).stem)
    # The reservation is shared across file formats and server processes. The
    # original filename is kept here while the stored filename is safe to use on Windows.
    names = folder / ".upload-names"
    names.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=folder, prefix=".upload-", delete=False) as temp:
        staged = Path(temp.name)
    try:
        staged.write_bytes(data)
        for index in range(1, 10000):
            tail = "" if index == 1 else f"-{index}"
            key = stem[:80 - len(tail)] + tail
            target = folder / (key + suffix)
            if key in taken or target.exists():
                continue
            reservation = names / f"{key}.json"
            try:
                marker = reservation.open("x", encoding="utf-8")
            except FileExistsError:
                continue
            try:
                with marker:
                    json.dump({"file": target.name, "original": name}, marker, ensure_ascii=False)
                os.replace(staged, target)
            except BaseException:
                reservation.unlink(missing_ok=True)
                raise
            return {"id": key, "file": name, "stored_file": target.name}
        raise WorkspaceError("Too many files with this name.")
    finally:
        staged.unlink(missing_ok=True)


class Handler(BaseHTTPRequestHandler):
    server_version = "InvoiceWorkspace/1"

    def log_message(self, fmt, *args):  # keep the terminal quiet
        return

    # -- responses ---------------------------------------------------------
    def send_json(self, data, status=HTTPStatus.OK):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path, download: bool = False):
        if not path.is_file():
            return self.send_json({"error": "File not found."}, HTTPStatus.NOT_FOUND)
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.end_headers()
        self.wfile.write(data)

    def read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise WorkspaceError("The file is too large (40 MB at most).")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw or b"{}")
        except json.JSONDecodeError as error:
            raise WorkspaceError("The request was not valid JSON.") from error
        if not isinstance(data, dict):
            raise WorkspaceError("The request must be a JSON object.")
        return data

    def guard(self, action):
        try:
            action()
        except WorkspaceError as error:
            self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except Exception as error:  # report unexpected failures to the page instead of hanging
            self.send_json({"error": f"Something went wrong: {error}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def scoped_project(self, *, required: bool = False) -> str:
        query = parse_qs(urlparse(self.path).query, keep_blank_values=True)
        values = query.get("project")
        if values is None and not required:
            return selected_project()
        if not values or len(values) != 1 or not values[0]:
            raise WorkspaceError("Select the project for this action and try again.")
        return existing_project(values[0])

    # -- routing -----------------------------------------------------------
    def do_GET(self):
        self.guard(self._get)

    def do_POST(self):
        self.guard(self._post)

    def do_PUT(self):
        self.guard(self._put)

    def _get(self):
        url = urlparse(self.path)
        path = unquote(url.path)
        query = parse_qs(url.query)
        if path in ("/", "/index.html"):
            return self.send_file(APP / "index.html")
        if path in ("/app.js", "/app.css", "/workspace.js", "/invoice-review.js", "/project-setup.js", "/workspace-tools.js"):
            return self.send_file(APP / path.lstrip("/"))
        if path.startswith("/files/"):
            target = (ROOT / path[len("/files/"):]).resolve()
            if not target.is_relative_to(PROJECTS.resolve()):
                return self.send_json({"error": "Not allowed."}, HTTPStatus.FORBIDDEN)
            if "project" in query and not target.is_relative_to(project_dir(self.scoped_project()).resolve()):
                return self.send_json({"error": "File belongs to another project."}, HTTPStatus.FORBIDDEN)
            return self.send_file(target, download="download" in query)
        if path == "/api/state":
            try:
                current = selected_project()
            except WorkspaceError:
                current = None
            return self.send_json({"current": current,
                                   "projects": [project_summary(p["slug"]) for p in list_projects()]})
        if path == "/api/settings":
            return self.send_json({"settings": load_settings(), "claude_models": list(CLAUDE_MODELS),
                                   "efforts": list(EFFORTS)})
        slug = self.scoped_project()
        if path == "/api/config":
            config = load_config(slug)
            config["guidelines"] = sorted(p.name for p in (project_dir(slug) / "guidelines").glob("*") if p.is_file())
            return self.send_json(config)
        if path == "/api/invoices":
            return self.send_json(invoice_list(slug))
        if path.startswith("/api/result/"):
            invoice_id = check_id(path.rsplit("/", 1)[1], "invoice")
            detail = result_store.detail_state(slug, invoice_id)
            result = detail["result"]
            candidate = detail.get("candidate")
            if candidate:
                candidate["marks"] = marks_for(candidate["result"])
            pdf = detail.get("marked_pdf")
            url = file_url(pdf, slug, download=True) if pdf else None
            return self.send_json({**detail, "marked_pdf": url, "marked_pdf_url": url,
                                   "pages": page_images(slug, invoice_id), "marks": marks_for(result) if result else []})
        if path == "/api/evaluation":
            truths = [load_json(p) for p in sorted(truth_dir(slug).glob("*.json"))]
            runs_dir = project_dir(slug) / "evaluation" / "runs"
            runs = sorted(runs_dir.glob("*.json"), reverse=True) if runs_dir.exists() else []
            return self.send_json({"test_invoices": truths, "latest_run": load_json(runs[0]) if runs else None,
                                   "runs": [load_json(r) for r in runs[:10]]})
        if path == "/api/proposals":
            rules = [r for r in load_config(slug)["rules"] if r.get("status") == "proposed" and r.get("proposed_by") == "assistant"]
            return self.send_json({"changes": pending_proposals(slug), "rules": rules})
        if path == "/api/export/setup.json":
            data = json.dumps(export_setup(slug), ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{slug}-setup.json"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            log(slug, "staff", "setup exported", {"format": "json"})
            return None
        if path == "/api/history":
            limit = int((query.get("limit") or ["200"])[0])
            return self.send_json(read_history(slug, max(1, min(limit, 1000))))
        return self.send_json({"error": "Not found."}, HTTPStatus.NOT_FOUND)

    def _post(self):
        path = unquote(urlparse(self.path).path)
        body = self.read_body()
        if path == "/api/project/switch":
            set_current_project(check_id(str(body.get("slug", "")), "project"))
            log(body["slug"], "staff", "project selected", {})
            return self.send_json({"current": body["slug"]})
        if path == "/api/project/create":
            name = str(body.get("name", "")).strip()
            if not name:
                raise WorkspaceError("Give the project a name.")
            copy_from = body.get("copy_rules_from") or None
            slug = create(name, check_id(copy_from, "project") if copy_from else None)
            set_current_project(slug)
            return self.send_json({"current": slug})
        if path == "/api/project/import":
            name = str(body.get("name", "")).strip()
            if not name:
                raise WorkspaceError("Give the project a name.")
            slug = import_setup(name, body.get("setup"))
            set_current_project(slug)
            return self.send_json({"current": slug})
        slug = self.scoped_project(required=True)
        if path.startswith("/api/proposals/"):
            proposal_id = path.rsplit("/", 1)[1]
            return self.send_json(decide_proposal(slug, proposal_id, bool(body.get("approve")), body.get("by") or "staff"))
        if path.startswith("/api/rules/") and path.endswith("/status"):
            return self.send_json(set_rule_status(slug, path.split("/")[3], str(body.get("status", "")), body.get("by") or "staff"))
        if path == "/api/export/setup.xlsx":
            report = build_setup(slug)
            return self.send_json({"report": report, "url": file_url(report, slug, download=True)})
        if path == "/api/invoices/upload":
            folder, _ = set_dirs(slug, "invoices")
            upload = save_upload(folder, body, INVOICE_SUFFIXES, slug)
            log(slug, "staff", "invoice added", upload)
            return self.send_json(upload)
        if path == "/api/guidelines/upload":
            upload = save_upload(project_dir(slug) / "guidelines", body, GUIDELINE_SUFFIXES)
            log(slug, "staff", "guideline added", {"file": upload["stored_file"]})
            return self.send_json({"file": upload["stored_file"]})
        if path.startswith("/api/result/") and path.endswith("/review"):
            invoice_id = check_id(path.split("/")[3], "invoice")
            return self.send_json({"result": result_store.save_review(slug, invoice_id, body)})
        if path.startswith("/api/result/") and path.endswith("/accept-recheck"):
            invoice_id = check_id(path.split("/")[3], "invoice")
            return self.send_json({"result": result_store.accept_recheck(slug, invoice_id, body)})
        if path.startswith("/api/evaluation/add/"):
            invoice_id = check_id(path.rsplit("/", 1)[1], "invoice")
            return self.send_json(add_test_invoice(slug, invoice_id, bool(body.get("aside"))))
        if path == "/api/evaluation/score":
            return self.send_json(score(slug, who="staff"))
        if path == "/api/report":
            report = build_report(slug, who="staff")
            return self.send_json({"report": report, "url": file_url(report, slug, download=True)})
        return self.send_json({"error": "Not found."}, HTTPStatus.NOT_FOUND)

    def _put(self):
        path = unquote(urlparse(self.path).path)
        if path == "/api/settings":
            return self.send_json(save_settings(self.read_body()))
        slug = self.scoped_project(required=True)
        if not path.startswith("/api/config/"):
            return self.send_json({"error": "Not found."}, HTTPStatus.NOT_FOUND)
        part = path.rsplit("/", 1)[1]
        if part not in CONFIG_PARTS:
            raise WorkspaceError(f"Unknown part '{part}'.")
        filename, kind = CONFIG_PARTS[part]
        body = self.read_body()
        value = body.get("value")
        if not isinstance(value, kind):
            raise WorkspaceError(f"Expected a {'list' if kind is list else 'set of values'} for {part}.")
        if kind is list:
            ids = [item.get("id") for item in value if isinstance(item, dict)]
            if len(ids) != len(value) or any(not i for i in ids) or len(set(ids)) != len(ids):
                raise WorkspaceError("Every item needs its own id.")
        file = project_dir(slug) / filename
        before = load_json(file, [] if kind is list else {})
        save_json(file, value)
        changes = describe_changes(before, value)
        if changes["changed"]:
            log(slug, body.get("by") or "staff", f"{part.replace('_', ' ')} edited", changes)
        return self.send_json({"saved": part, "changes": len(changes["changed"])})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--open-browser", action="store_true", help="Open the page in your default browser.")
    args = parser.parse_args()
    url = f"http://localhost:{args.port}"
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as error:
        if error.errno == errno.EADDRINUSE:
            try:
                with urlopen(url + "/api/state", timeout=2) as response:
                    is_workspace = (response.headers.get("Server", "").startswith(Handler.server_version)
                                    and "projects" in json.load(response))
            except (URLError, ValueError, OSError):
                is_workspace = False
            if not is_workspace:
                print(f"Another application is using port {args.port}.", file=sys.stderr)
                return 1
            if args.open_browser:
                webbrowser.open(url)
            print(f"The workspace is already running at {url}")
            return 0
        raise
    if args.open_browser:
        webbrowser.open(url)
    print(f"Invoice workspace running at {url}  (stop with Ctrl+C)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
