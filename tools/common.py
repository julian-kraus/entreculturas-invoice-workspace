"""Shared paths, file helpers and the activity log for the invoice workspace."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT / "projects"
WORKSPACE_FILE = ROOT / "workspace.json"
PDFIUM_LOCK = Lock()

INVOICE_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,80}$")


class WorkspaceError(Exception):
    """A problem the person or the assistant can fix, explained in plain words."""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:80] or "item"


def storage_slug(text: str) -> str:
    """Choose a portable name for new files without renaming existing IDs."""
    value = slugify(text)
    if re.fullmatch(r"con|prn|aux|nul|(?:com|lpt)[1-9]", value):
        return value + "-document"
    return value


def check_id(value: str, what: str = "id") -> str:
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise WorkspaceError(f"'{value}' is not a valid {what}.")
    return value


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".write-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def list_projects() -> list[dict]:
    projects = []
    if not PROJECTS.exists():
        return projects
    for folder in sorted(PROJECTS.iterdir()):
        info = folder / "project.json"
        if folder.is_dir() and info.exists():
            data = load_json(info, {})
            projects.append({"slug": folder.name, "name": data.get("name", folder.name)})
    return projects


def existing_project(slug: str) -> str:
    if not (project_dir(slug) / "project.json").is_file():
        raise WorkspaceError(f"There is no project called '{slug}'.")
    return slug


def current_project() -> str:
    if "INVOICE_PROJECT" in os.environ:
        return existing_project(os.environ["INVOICE_PROJECT"])
    return selected_project()


def selected_project() -> str:
    slug = (load_json(WORKSPACE_FILE, {}) or {}).get("current_project")
    if not slug:
        raise WorkspaceError("No project is selected. Choose one on the workspace page or ask to switch project.")
    return existing_project(slug)


def set_current_project(slug: str) -> None:
    existing_project(slug)
    data = load_json(WORKSPACE_FILE, {}) or {}
    data["current_project"] = slug
    save_json(WORKSPACE_FILE, data)


def project_dir(slug: str) -> Path:
    return PROJECTS / check_id(slug, "project")


def invoice_files(slug: str) -> dict[str, Path]:
    base = project_dir(slug)
    folder = base / "invoices"
    results = base / "results"
    if not folder.exists():
        return {}
    groups: dict[str, list[Path]] = {}
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() in INVOICE_SUFFIXES and path.is_file():
            groups.setdefault(slugify(path.stem), []).append(path)

    files = {}
    reserved = set(groups)
    for stem, paths in groups.items():
        recorded = load_json(folder / ".upload-names" / f"{stem}.json", {}) or {}
        preferred = recorded.get("file")
        if len(paths) > 1 and not preferred:
            try:
                previous = load_json(results / f"{stem}.json", {}) or {}
            except (ValueError, OSError):
                previous = {}
            preferred = previous.get("file") if isinstance(previous, dict) else None
        owner = next((p for p in paths if p.name == preferred), paths[-1])
        for path in paths:
            key = stem
            if path != owner:
                # Older versions indexed by stem alone. Keep their original entry
                # and give every shadowed file a repeatable, filename-based ID.
                digest = hashlib.sha256(path.name.encode()).hexdigest()
                key = f"{stem[:57]}-{digest[:20]}"
                while key in reserved or key in files:
                    digest = hashlib.sha256(digest.encode()).hexdigest()
                    key = f"{stem[:57]}-{digest[:20]}"
            files[key] = path
    return files



def ambiguous_invoice_ids(slug: str) -> set[str]:
    """Find legacy same-stem invoices whose unreadable result cannot identify its source."""
    base = project_dir(slug)
    files = invoice_files(slug)
    groups: dict[str, list[tuple[str, Path]]] = {}
    for invoice_id, path in files.items():
        groups.setdefault(slugify(path.stem), []).append((invoice_id, path))
    ambiguous = set()
    for stem, entries in groups.items():
        if len(entries) < 2:
            continue
        recorded = load_json(base / "invoices" / ".upload-names" / f"{stem}.json", {}) or {}
        if isinstance(recorded, dict) and recorded.get("file") in {path.name for _, path in entries}:
            continue
        result = base / "results" / f"{stem}.json"
        if not result.exists():
            continue
        try:
            value = load_json(result)
        except (ValueError, OSError):
            value = None
        if not isinstance(value, dict) or value.get("file") not in {path.name for _, path in entries}:
            ambiguous.update(invoice_id for invoice_id, _ in entries)
    return ambiguous


def invoice_display_name(slug: str, invoice_id: str, *, source: Path | None = None) -> str:
    source = source or invoice_path(slug, invoice_id)
    folder = project_dir(slug) / "invoices"
    meta = load_json(folder / ".upload-names" / f"{check_id(invoice_id, 'invoice')}.json", {}) or {}
    return meta.get("original", source.name) if meta.get("file") == source.name else source.name


def invoice_path(slug: str, invoice_id: str) -> Path:
    files = invoice_files(slug)
    if invoice_id not in files:
        raise WorkspaceError(f"No invoice '{invoice_id}' in this project.")
    return files[invoice_id]


def result_path(slug: str, invoice_id: str) -> Path:
    return project_dir(slug) / "results" / f"{check_id(invoice_id, 'invoice')}.json"


def work_dir(slug: str, invoice_id: str) -> Path:
    return project_dir(slug) / "work" / "invoices" / check_id(invoice_id, "invoice")


def load_config(slug: str) -> dict:
    base = project_dir(slug)
    return {
        "project": load_json(base / "project.json", {}),
        "invoice_types": load_json(base / "invoice_types.json", []),
        "fields": load_json(base / "fields.json", []),
        "rules": load_json(base / "rules.json", []),
        "learnings": load_json(base / "learnings.json", []),
    }


def log(slug: str, who: str, action: str, detail: dict | None = None) -> None:
    entry = {"at": now_iso(), "who": who, "action": action, "detail": detail or {}}
    path = project_dir(slug) / "history.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_history(slug: str, limit: int = 200) -> list[dict]:
    path = project_dir(slug) / "history.jsonl"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    entries = []
    for line in lines[-limit:]:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(entries))


def rel(path: Path) -> str:
    """A path relative to the workspace folder when possible, for messages and links."""
    try:
        return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))
