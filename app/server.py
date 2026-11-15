"""The workspace page: a small local web server for reviewing invoices and editing the setup.

It only listens on this computer (127.0.0.1). It never calls an AI: checking invoices and
proposing rules happen in the chat. Everything is saved in projects/<project>/.

Usage:
  ./.tools/uv run app/server.py [--port 8790]
"""

from __future__ import annotations

import argparse
import base64
import errno
import json
import mimetypes
import sys
from copy import deepcopy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from checks import run as run_checks  # noqa: E402
from common import (  # noqa: E402
    INVOICE_SUFFIXES, PROJECTS, WorkspaceError, check_id, current_project, invoice_files, list_projects,
    load_config, load_json, log, now_iso, project_dir, read_history, result_path, save_json,
    set_current_project, set_dirs, slugify, work_dir,
)
from evaluate import add as add_test_invoice, score, truth_dir  # noqa: E402
from marks import draw, marks_for  # noqa: E402
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
        result = load_json(result_path(slug, invoice_id))
        review = (result or {}).get("review") or {}
        items.append({
            "id": invoice_id, "file": path.name,
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
    return ["/files/" + str(p.relative_to(ROOT)) for p in pages]


def save_review(slug: str, invoice_id: str, body: dict) -> dict:
    path = result_path(slug, invoice_id)
    result = load_json(path)
    if not result:
        raise WorkspaceError("This invoice has not been checked yet.")
    if "ai_original" not in result:
        original = deepcopy(result)
        original.pop("review", None)
        result["ai_original"] = original
    config = load_config(slug)
    known_fields = {f["name"] for f in config["fields"] if f["type_id"] == result.get("type_id")}
    corrections = {k: v for k, v in (body.get("fields") or {}).items() if k in known_fields}
    rule_ids = {o["rule_id"] for o in result.get("rule_results", [])}
    overrides = {k: v for k, v in (body.get("rules") or {}).items() if k in rule_ids and v in ("passed", "failed")}
    status = "confirmed" if body.get("status") == "confirmed" else "draft"
    before = deepcopy(result.get("review") or {})
    result["review"] = {"fields": corrections, "rules": overrides, "status": status,
                        "by": body.get("by") or "staff", "at": now_iso(), "note": body.get("note", "")}
    save_json(path, result)
    checked = run_checks(slug, invoice_id)
    draw(slug, invoice_id, "invoices")
    log(slug, result["review"]["by"], "review saved", {
        "invoice": invoice_id, "status": status,
        "corrected fields": {k: {"assistant read": (result["ai_original"].get("fields", {}).get(k) or {}).get("value"),
                                 "reviewer": v} for k, v in corrections.items()},
        "changed rule outcomes": overrides, "before": before.get("status")})
    tip = (body.get("learning") or "").strip()
    if tip:
        learnings = load_json(project_dir(slug) / "learnings.json", [])
        learnings.append({"id": f"L{len(learnings) + 1:03d}", "text": tip, "type_id": result.get("type_id"),
                          "source_invoice": invoice_id, "created": now_iso(), "active": True})
        save_json(project_dir(slug) / "learnings.json", learnings)
        log(slug, result["review"]["by"], "learning saved", {"text": tip, "invoice": invoice_id})
    return checked


def save_settings(body: dict) -> dict:
    """Save which model and effort each job uses, and write them into the Claude Code and Codex files."""
    before = load_settings()
    wanted = body.get("value")
    if not isinstance(wanted, dict):
        raise WorkspaceError("Expected the assistant settings.")
    save_json(SETTINGS_FILE, wanted)
    settings = load_settings()
    problems = validate(settings)
    if problems:
        save_json(SETTINGS_FILE, before)
        raise WorkspaceError(" ".join(problems))
    save_json(SETTINGS_FILE, settings)
    sync(settings)
    changes = describe_changes(
        {f"Claude {job}": f"{v['model']}, {v['effort']}" for job, v in before["claude"].items()}
        | {"Codex": f"{before['codex']['model'] or 'default'}, {before['codex']['effort']}"},
        {f"Claude {job}": f"{v['model']}, {v['effort']}" for job, v in settings["claude"].items()}
        | {"Codex": f"{settings['codex']['model'] or 'default'}, {settings['codex']['effort']}"})
    try:
        if changes["changed"]:
            log(current_project(), body.get("by") or "staff", "assistant settings changed", changes)
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


def save_upload(folder: Path, body: dict, allowed: set[str]) -> str:
    name = Path(str(body.get("name", ""))).name
    suffix = Path(name).suffix.lower()
    if suffix not in allowed:
        raise WorkspaceError(f"Files of type '{suffix or 'unknown'}' can't be added here.")
    data = base64.b64decode(str(body.get("data", "")).split(",")[-1], validate=False)
    if not data:
        raise WorkspaceError("The file is empty.")
    folder.mkdir(parents=True, exist_ok=True)
    stem, target = slugify(Path(name).stem), None
    for index in range(1, 1000):
        candidate = folder / (f"{stem}{suffix}" if index == 1 else f"{stem}-{index}{suffix}")
        if not candidate.exists():
            target = candidate
            break
    if target is None:
        raise WorkspaceError("Too many files with this name.")
    target.write_bytes(data)
    return target.name


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
        if path in ("/app.js", "/app.css"):
            return self.send_file(APP / path.lstrip("/"))
        if path.startswith("/files/"):
            target = (ROOT / path[len("/files/"):]).resolve()
            if not target.is_relative_to(PROJECTS.resolve()):
                return self.send_json({"error": "Not allowed."}, HTTPStatus.FORBIDDEN)
            return self.send_file(target, download="download" in query)
        if path == "/api/state":
            try:
                current = current_project()
            except WorkspaceError:
                current = None
            return self.send_json({"current": current,
                                   "projects": [project_summary(p["slug"]) for p in list_projects()]})
        if path == "/api/settings":
            return self.send_json({"settings": load_settings(), "claude_models": list(CLAUDE_MODELS),
                                   "efforts": list(EFFORTS)})
        slug = current_project()
        if path == "/api/config":
            config = load_config(slug)
            config["guidelines"] = sorted(p.name for p in (project_dir(slug) / "guidelines").glob("*") if p.is_file())
            return self.send_json(config)
        if path == "/api/invoices":
            return self.send_json(invoice_list(slug))
        if path.startswith("/api/result/"):
            invoice_id = check_id(path.rsplit("/", 1)[1], "invoice")
            result = load_json(result_path(slug, invoice_id))
            return self.send_json({"result": result, "pages": page_images(slug, invoice_id),
                                   "marks": marks_for(result) if result else []})
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
        slug = current_project()
        if path.startswith("/api/proposals/"):
            proposal_id = path.rsplit("/", 1)[1]
            return self.send_json(decide_proposal(slug, proposal_id, bool(body.get("approve")), body.get("by") or "staff"))
        if path.startswith("/api/rules/") and path.endswith("/status"):
            return self.send_json(set_rule_status(slug, path.split("/")[3], str(body.get("status", "")), body.get("by") or "staff"))
        if path == "/api/export/setup.xlsx":
            report = build_setup(slug)
            return self.send_json({"report": report, "url": "/files/" + report + "?download=1"})
        if path == "/api/invoices/upload":
            folder, _ = set_dirs(slug, "invoices")
            name = save_upload(folder, body, INVOICE_SUFFIXES)
            log(slug, "staff", "invoice added", {"file": name})
            return self.send_json({"file": name})
        if path == "/api/guidelines/upload":
            name = save_upload(project_dir(slug) / "guidelines", body, GUIDELINE_SUFFIXES)
            log(slug, "staff", "guideline added", {"file": name})
            return self.send_json({"file": name})
        if path.startswith("/api/result/") and path.endswith("/review"):
            invoice_id = check_id(path.split("/")[3], "invoice")
            return self.send_json({"result": save_review(slug, invoice_id, body)})
        if path.startswith("/api/evaluation/add/"):
            invoice_id = check_id(path.rsplit("/", 1)[1], "invoice")
            return self.send_json(add_test_invoice(slug, invoice_id, bool(body.get("aside"))))
        if path == "/api/evaluation/score":
            return self.send_json(score(slug, who="staff"))
        if path == "/api/report":
            report = build_report(slug, who="staff")
            return self.send_json({"report": report, "url": "/files/" + report + "?download=1"})
        return self.send_json({"error": "Not found."}, HTTPStatus.NOT_FOUND)

    def _put(self):
        path = unquote(urlparse(self.path).path)
        if path == "/api/settings":
            return self.send_json(save_settings(self.read_body()))
        slug = current_project()
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
    args = parser.parse_args()
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as error:
        if error.errno == errno.EADDRINUSE:
            print(f"The workspace is already running at http://localhost:{args.port}")
            return 0
        raise
    print(f"Invoice workspace running at http://localhost:{args.port}  (stop with Ctrl+C)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
