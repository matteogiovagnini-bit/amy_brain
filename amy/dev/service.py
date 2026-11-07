"""Servizio Developer: analisi del progetto in sola lettura.

Amy non esegue shell arbitrarie. Questo servizio usa solo comandi Git
predefiniti, senza ``shell=True``, e legge i file con la libreria standard.
L'unica operazione che esegue codice è ``run_tests``: avvia la suite del
progetto con un timeout finito ed è di livello B.
"""

from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..core.errors import AmyError

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    ".build",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "site-packages",
}
TEXT_SUFFIXES = {
    ".py",
    ".swift",
    ".js",
    ".css",
    ".html",
    ".md",
    ".json",
    ".toml",
    ".sh",
    ".yml",
    ".yaml",
    ".txt",
}
MAX_FILE_BYTES = 1_000_000
TODO_RE = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b[:\s]*(.*)", re.IGNORECASE)
RAN_RE = re.compile(r"^Ran (\d+) tests?", re.MULTILINE)


class DevError(AmyError):
    code = "dev_error"


def _project(context: Any) -> Path:
    configured = str(context.config.get("dev.project_dir", "") or "").strip()
    raw = configured or str(Path(__file__).resolve().parents[2])
    project = context.path_guard.resolve(raw, must_exist=True)
    if not project.is_dir():
        raise DevError("La cartella di progetto non è una directory.", detail=str(project))
    return project


def _git(project: Path, args: List[str], *, timeout: float = 15.0) -> str:
    binary = shutil.which("git")
    if not binary:
        raise DevError(
            "Git non è installato o non è nel PATH.",
            detail="Serve Git per lo stato e il diff del progetto.",
        )
    try:
        completed = subprocess.run(
            [binary, "--no-pager"] + args,
            cwd=str(project),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise DevError("Git ha superato il tempo massimo.", detail=str(args)) from exc
    except OSError as exc:
        raise DevError("Impossibile avviare Git.", detail=str(exc)) from exc
    if completed.returncode != 0:
        raise DevError(
            "Comando Git non riuscito.",
            detail=(completed.stderr or completed.stdout or "")[:500],
        )
    return completed.stdout


def _ensure_repo(project: Path) -> None:
    try:
        inside = _git(project, ["rev-parse", "--is-inside-work-tree"]).strip()
    except DevError as exc:
        raise DevError(
            "La cartella non è un repository Git.",
            detail="%s — %s" % (project, exc.detail),
        ) from exc
    if inside != "true":
        raise DevError("La cartella non è un repository Git.", detail=str(project))


def _relative(project: Path, value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise DevError(
            "Il percorso deve essere relativo al progetto e non può uscire dalla cartella.",
            detail=raw,
        )
    resolved = (project / candidate).resolve()
    try:
        return str(resolved.relative_to(project))
    except ValueError as exc:
        raise DevError(
            "Il percorso è fuori dalla cartella del progetto.",
            detail=str(resolved),
        ) from exc


def status(context: Any) -> Dict[str, Any]:
    project = _project(context)
    _ensure_repo(project)
    branch = _git(project, ["rev-parse", "--abbrev-ref", "HEAD"]).strip() or "HEAD"
    changes = _git(project, ["status", "--short"]).splitlines()
    modified = [line for line in changes if not line.startswith("??")]
    untracked = [line for line in changes if line.startswith("??")]
    last = _git(project, ["log", "-1", "--format=%h%x09%ci%x09%s"]).strip()
    commit = {"hash": "", "date": "", "subject": ""}
    if last:
        parts = last.split("\t")
        if len(parts) >= 3:
            commit = {"hash": parts[0], "date": parts[1], "subject": "\t".join(parts[2:])}
    dependencies = {}
    for name in ("pyproject.toml", "requirements.txt", "Pipfile", "package.json", "poetry.lock"):
        path = project / name
        dependencies[name] = path.is_file()
    return {
        "project": str(project),
        "branch": branch,
        "clean": not changes,
        "modified": len(modified),
        "untracked": len(untracked),
        "changes": changes[:50],
        "changes_truncated": len(changes) > 50,
        "last_commit": commit,
        "dependencies": dependencies,
        "verified": True,
    }


def diff(
    context: Any,
    *,
    staged: bool = False,
    path: str = "",
    stat_only: bool = False,
) -> Dict[str, Any]:
    project = _project(context)
    _ensure_repo(project)
    rel = _relative(project, path)
    base = ["diff"]
    if staged:
        base.append("--cached")
    pathspec = ["--", rel] if rel else []
    stat = _git(project, base + ["--stat"] + pathspec)
    full = "" if stat_only else _git(project, base + ["--unified=3"] + pathspec)
    limit = max(500, min(int(context.config.get("dev.max_output_chars", 6000)), 40000))
    truncated = len(stat) > limit or len(full) > limit
    return {
        "project": str(project),
        "staged": bool(staged),
        "path": rel,
        "stat": stat[:limit],
        "diff": full[:limit],
        "truncated": truncated,
        "empty": not stat.strip() and not full.strip(),
        "verified": True,
    }


def _walk_files(target: Path, limit: int) -> Tuple[List[Path], bool]:
    if target.is_file():
        return [target], False
    files: List[Path] = []
    truncated = False
    for root, dirs, names in os.walk(str(target), followlinks=False):
        dirs[:] = sorted(name for name in dirs if name not in SKIP_DIRS and not name.startswith(".git"))
        for name in sorted(names):
            if name.startswith("."):
                continue
            files.append(Path(root) / name)
            if len(files) >= limit:
                return files, True
    return files, truncated


def analyze(context: Any, *, path: str = "", limit: int = 1000) -> Dict[str, Any]:
    project = _project(context)
    rel = _relative(project, path)
    target = project / rel if rel else project
    if not target.exists():
        raise DevError("Il percorso da analizzare non esiste.", detail=str(target))
    limit = max(1, min(int(limit), 5000))
    files, truncated = _walk_files(target, limit)
    by_extension: Counter = Counter()
    largest: List[Dict[str, Any]] = []
    todos: List[Dict[str, Any]] = []
    syntax_errors: List[Dict[str, Any]] = []
    total_lines = 0
    scanned = 0
    skipped_large = 0
    for item in files:
        try:
            size = item.stat().st_size
            relative = str(item.resolve().relative_to(project))
        except (OSError, ValueError):
            continue
        if size > MAX_FILE_BYTES:
            skipped_large += 1
            continue
        scanned += 1
        suffix = item.suffix.lower() or "(senza estensione)"
        by_extension[suffix] += 1
        largest.append({"path": relative, "bytes": size})
        if item.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            content = item.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lines = content.count("\n") + (1 if content else 0)
        total_lines += lines
        for match in TODO_RE.finditer(content):
            if len(todos) >= 20:
                break
            line_no = content.count("\n", 0, match.start()) + 1
            todos.append(
                {
                    "path": relative,
                    "line": line_no,
                    "kind": match.group(1).upper(),
                    "text": (match.group(2) or "").strip()[:160],
                }
            )
        if item.suffix.lower() == ".py":
            try:
                ast.parse(content, filename=relative)
            except SyntaxError as exc:
                if len(syntax_errors) < 10:
                    syntax_errors.append(
                        {
                            "path": relative,
                            "line": exc.lineno or 0,
                            "error": str(exc.msg or "errore di sintassi")[:200],
                        }
                    )
    largest.sort(key=lambda row: row["bytes"], reverse=True)
    return {
        "project": str(project),
        "target": rel or ".",
        "files": scanned,
        "skipped_large": skipped_large,
        "lines": total_lines,
        "by_extension": dict(by_extension.most_common()),
        "largest": largest[:5],
        "todos": todos,
        "syntax_errors": syntax_errors,
        "truncated": truncated,
        "verified": True,
    }


def run_tests(context: Any) -> Dict[str, Any]:
    project = _project(context)
    tests_dir = project / "tests"
    if not tests_dir.is_dir():
        raise DevError(
            "Nessuna cartella tests nel progetto.",
            detail=str(project),
        )
    try:
        timeout = float(context.config.get("dev.test_timeout_s", 300))
    except (TypeError, ValueError):
        timeout = 300.0
    timeout = max(30.0, min(timeout, 900.0))
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests"]
    if (tests_dir / "__init__.py").is_file():
        # Con un package tests/ il top-level resta la radice del progetto, così
        # gli import ``tests.helpers`` funzionano come nella suite reale.
        command.extend(["-t", "."])
    try:
        completed = subprocess.run(
            command,
            cwd=str(project),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        timed_out = False
        code = completed.returncode
        raw = (completed.stdout or "") + (completed.stderr or "")
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        code = -1
        raw = "La suite ha superato il tempo massimo di %.0f secondi.\n" % timeout
        if exc.stdout:
            raw += str(exc.stdout)
        if exc.stderr:
            raw += str(exc.stderr)
    except OSError as exc:
        raise DevError("Impossibile avviare la suite.", detail=str(exc)) from exc
    limit = max(500, min(int(context.config.get("dev.max_output_chars", 6000)), 40000))
    match = RAN_RE.search(raw)
    ran = int(match.group(1)) if match else 0
    return {
        "project": str(project),
        "ok": (not timed_out) and code == 0,
        "exit_code": code,
        "tests": ran,
        "timed_out": timed_out,
        "timeout_s": timeout,
        "command": " ".join(command),
        "output": raw[:limit],
        "truncated": len(raw) > limit,
        "verified": not timed_out,
    }
