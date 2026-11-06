"""Strumenti per file e cartelle, confinati nelle radici autorizzate."""

from __future__ import annotations

import difflib
import fnmatch
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

from ..core.errors import PermissionDeniedError, ToolValidationError
from ..security.risk import RiskLevel
from .base import FunctionTool, ToolContext, ToolResult, ToolSpec


def _backup_path(original: Path, backup_dir: str) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target_dir = Path(backup_dir).expanduser() / stamp
    target_dir.mkdir(parents=True, exist_ok=True)
    candidate = target_dir / original.name
    if candidate.exists():
        candidate = target_dir / ("%s-%s%s" % (original.stem, uuid.uuid4().hex[:6], original.suffix))
    return candidate


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return "%.1f %s" % (value, unit) if unit != "B" else "%d B" % int(value)
        value /= 1024
    return "%d B" % size


def _entry_info(path: Path) -> Dict[str, Any]:
    try:
        stat = path.stat()
        return {
            "name": path.name,
            "path": str(path),
            "tipo": "cartella" if path.is_dir() else "file",
            "dimensione": stat.st_size,
            "modificato": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
        }
    except OSError:
        return {"name": path.name, "path": str(path), "tipo": "sconosciuto"}


def _list_files(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    path = context.path_guard.resolve(str(args.get("path", "~")), must_exist=True)
    if not path.is_dir():
        raise ToolValidationError("Il percorso indicato non è una cartella.")
    limit = int(args.get("max_entries", 100))
    recursive = bool(args.get("recursive", False))
    entries: List[Dict[str, Any]] = []

    if recursive:
        for root, dirnames, filenames in os.walk(str(path), followlinks=False):
            dirnames[:] = [name for name in dirnames if not name.startswith(".")]
            for name in dirnames + filenames:
                if name.startswith(".") or len(entries) >= limit:
                    continue
                entries.append(_entry_info(Path(root) / name))
            if len(entries) >= limit:
                break
    else:
        for entry in sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
            if entry.name.startswith("."):
                continue
            entries.append(_entry_info(entry))
            if len(entries) >= limit:
                break

    return ToolResult.success(
        {"path": str(path), "voci": entries, "mostrate": len(entries), "limite": limit},
        "Trovate %d voci in %s." % (len(entries), path),
    )


def _search_files(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    query = str(args["query"]).strip()
    if not query:
        raise ToolValidationError("La ricerca non può essere vuota.")
    limit = int(args.get("max_results", 30))
    roots = (
        [context.path_guard.resolve(str(args["path"]), must_exist=True)]
        if args.get("path")
        else list(context.path_guard.roots)
    )
    matches: List[Dict[str, Any]] = []
    seen = 0
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        for current, dirnames, filenames in os.walk(str(root), followlinks=False):
            dirnames[:] = [name for name in dirnames if not name.startswith(".")]
            for name in filenames + dirnames:
                seen += 1
                if seen > 50000 or len(matches) >= limit:
                    break
                if name.startswith("."):
                    continue
                if fnmatch.fnmatch(name.lower(), "*%s*" % query.lower()):
                    matches.append(_entry_info(Path(current) / name))
            if len(matches) >= limit or seen > 50000:
                break
        if len(matches) >= limit:
            break
    return ToolResult.success(
        {"query": query, "risultati": matches, "esaminati": seen},
        "Trovati %d risultati per «%s»." % (len(matches), query),
    )


def _read_file(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    path = context.path_guard.resolve(str(args["path"]), must_exist=True)
    if path.is_dir():
        raise ToolValidationError("Il percorso è una cartella, non un file.")
    size = path.stat().st_size
    context.path_guard.check_size(size)
    raw = path.read_bytes()
    if b"\x00" in raw[:4096]:
        raise ToolValidationError("Il file sembra binario e non viene letto come testo.")
    try:
        content = raw.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        content = raw.decode("utf-8", errors="replace")
        encoding = "utf-8 (con sostituzioni)"
    max_chars = int(args.get("max_chars", 20000))
    truncated = len(content) > max_chars
    if truncated:
        content = content[:max_chars]
    return ToolResult.success(
        {
            "path": str(path),
            "content": content,
            "encoding": encoding,
            "bytes": size,
            "troncato": truncated,
        },
        "Letto %s (%s)." % (path.name, _human_size(size)),
    )


def _write_file(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    path = context.path_guard.resolve(str(args["path"]))
    if path.exists() and path.is_dir():
        raise ToolValidationError("Il percorso è una cartella.")
    content = str(args["content"])
    encoded = content.encode("utf-8")
    context.path_guard.check_size(len(encoded))
    if not path.parent.exists():
        if not args.get("create_parents", False):
            raise ToolValidationError("La cartella di destinazione non esiste.")
        path.parent.mkdir(parents=True, exist_ok=True)

    backup = None
    if path.exists() and args.get("backup", True):
        backup_path = _backup_path(path, context.config.get("security.backup_dir"))
        shutil.copy2(str(path), str(backup_path))
        backup = str(backup_path)

    tmp = path.with_name(".%s.amy-tmp-%s" % (path.name, uuid.uuid4().hex[:8]))
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(tmp), str(path))
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass

    return ToolResult.success(
        {
            "path": str(path),
            "bytes": len(encoded),
            "backup": backup,
            "creato": backup is None,
        },
        "File scritto: %s%s" % (path, " (backup: %s)" % backup if backup else ""),
    )


def _mkdir(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    path = context.path_guard.resolve(str(args["path"]))
    if path.exists():
        if path.is_dir():
            return ToolResult.success({"path": str(path), "created": False}, "La cartella esiste già.")
        raise ToolValidationError("Esiste già un file con questo nome.")
    path.mkdir(parents=bool(args.get("parents", True)), exist_ok=False)
    return ToolResult.success({"path": str(path), "created": True}, "Cartella creata: %s" % path)


def _diff_files(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    first = context.path_guard.resolve(str(args["path_a"]), must_exist=True)
    second = context.path_guard.resolve(str(args["path_b"]), must_exist=True)
    context.path_guard.check_size(first.stat().st_size)
    context.path_guard.check_size(second.stat().st_size)
    try:
        a_lines = first.read_text(encoding="utf-8").splitlines(keepends=True)
        b_lines = second.read_text(encoding="utf-8").splitlines(keepends=True)
    except UnicodeDecodeError as exc:
        raise ToolValidationError("Confronto non disponibile per file non testuali.") from exc
    diff = "".join(
        difflib.unified_diff(
            a_lines,
            b_lines,
            fromfile=str(first),
            tofile=str(second),
            n=3,
        )
    )
    truncated = len(diff) > 20000
    return ToolResult.success(
        {"diff": diff[:20000], "troncato": truncated, "identici": not bool(diff)},
        "I file sono identici." if not diff else "Differenze trovate.",
    )


class _MoveTool(FunctionTool):
    def risk_for(self, args: Dict[str, Any]) -> RiskLevel:
        source = Path(str(args.get("source", ""))).expanduser()
        destination = Path(str(args.get("destination", ""))).expanduser()
        try:
            target = destination / source.name if destination.is_dir() else destination
            if target.exists():
                return RiskLevel.C
        except OSError:
            pass
        return RiskLevel.B


def _move(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    source = context.path_guard.resolve(str(args["source"]), must_exist=True)
    destination = context.path_guard.resolve(str(args["destination"]))
    target = destination / source.name if destination.is_dir() else destination
    if not Path(str(destination)).exists() and not target.parent.exists():
        raise ToolValidationError("La cartella di destinazione non esiste.")
    if target.exists() and not args.get("overwrite", False):
        raise ToolValidationError(
            "La destinazione esiste già. Per sostituirla serve una conferma specifica (livello C)."
        )
    backup = None
    if target.exists():
        backup_path = _backup_path(target, context.config.get("security.backup_dir"))
        shutil.copy2(str(target), str(backup_path))
        backup = str(backup_path)
        if target.is_dir():
            shutil.rmtree(str(target))
        else:
            target.unlink()
    shutil.move(str(source), str(target))
    return ToolResult.success(
        {"source": str(source), "destination": str(target), "backup": backup},
        "Spostato in %s.%s" % (target, " Backup del file sostituito: %s" % backup if backup else ""),
    )


def _trash(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    path = context.path_guard.resolve(str(args["path"]), must_exist=True)
    if path.is_dir() and not args.get("recursive", False):
        raise ToolValidationError("Per spostare una cartella serve recursive=true e conferma esplicita.")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    trash_dir = Path(context.config.get("security.backup_dir")).expanduser() / "trash" / stamp
    trash_dir.mkdir(parents=True, exist_ok=True)
    target = trash_dir / path.name
    if target.exists():
        target = trash_dir / ("%s-%s%s" % (path.stem, uuid.uuid4().hex[:6], path.suffix))
    shutil.move(str(path), str(target))
    return ToolResult.success(
        {
            "original": str(path),
            "trash": str(target),
            "recuperabile": True,
        },
        "Elemento spostato nel cestino di Amy: %s" % target,
    )


LIST_FILES = ToolSpec(
    name="files.list",
    description="Elenca file e cartelle in una cartella autorizzata.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "maxLength": 1000},
            "recursive": {"type": "boolean"},
            "max_entries": {"type": "integer", "minimum": 1, "maximum": 500},
        },
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Lettura dell'elenco di una cartella autorizzata.",
    tags=("file",),
)

SEARCH_FILES = ToolSpec(
    name="files.search",
    description="Cerca file per nome nelle cartelle autorizzate.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 100},
            "path": {"type": "string", "maxLength": 1000},
            "max_results": {"type": "integer", "minimum": 1, "maximum": 100},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Ricerca per nome in cartelle autorizzate.",
    tags=("file", "ricerca"),
)

READ_FILE = ToolSpec(
    name="files.read",
    description="Legge un file di testo autorizzato, con limite di dimensione.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "minLength": 1, "maxLength": 1000},
            "max_chars": {"type": "integer", "minimum": 100, "maximum": 100000},
        },
        "required": ["path"],
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Lettura di un file nelle cartelle autorizzate.",
    tags=("file", "lettura"),
)

WRITE_FILE = ToolSpec(
    name="files.write",
    description="Scrive o sostituisce un file di testo, creando un backup se esiste già.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "minLength": 1, "maxLength": 1000},
            "content": {"type": "string", "maxLength": 500000},
            "create_parents": {"type": "boolean"},
            "backup": {"type": "boolean"},
        },
        "required": ["path", "content"],
        "additionalProperties": False,
    },
    risk=RiskLevel.B,
    reason="Modifica del contenuto di un file.",
    consequences="Il contenuto precedente viene sostituito; viene creato un backup automatico se il file esiste.",
    undo="Ripristina il backup indicato nel risultato.",
    tags=("file", "scrittura"),
)

MKDIR = ToolSpec(
    name="files.mkdir",
    description="Crea una cartella nelle aree autorizzate.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "minLength": 1, "maxLength": 1000},
            "parents": {"type": "boolean"},
        },
        "required": ["path"],
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Creazione di una nuova cartella, operazione reversibile.",
    tags=("file",),
)

DIFF_FILES = ToolSpec(
    name="files.diff",
    description="Confronta due file di testo e restituisce le differenze in formato unificato.",
    parameters={
        "type": "object",
        "properties": {
            "path_a": {"type": "string", "minLength": 1, "maxLength": 1000},
            "path_b": {"type": "string", "minLength": 1, "maxLength": 1000},
        },
        "required": ["path_a", "path_b"],
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Confronto in sola lettura tra due file.",
    tags=("file", "sviluppo"),
)

MOVE = ToolSpec(
    name="files.move",
    description="Sposta un file o una cartella. Se la destinazione esiste, richiede conferma di livello C.",
    parameters={
        "type": "object",
        "properties": {
            "source": {"type": "string", "minLength": 1, "maxLength": 1000},
            "destination": {"type": "string", "minLength": 1, "maxLength": 1000},
            "overwrite": {"type": "boolean"},
        },
        "required": ["source", "destination"],
        "additionalProperties": False,
    },
    risk=RiskLevel.B,
    reason="Spostamento di un elemento tra cartelle autorizzate.",
    consequences="L'elemento cambia percorso; se la destinazione esiste viene sostituita solo con conferma.",
    undo="Spostalo di nuovo nella posizione originale.",
    tags=("file",),
)

TRASH = ToolSpec(
    name="files.trash",
    description="Sposta un file o una cartella nel cestino di Amy, in modo recuperabile. Non cancella definitivamente.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "minLength": 1, "maxLength": 1000},
            "recursive": {"type": "boolean"},
        },
        "required": ["path"],
        "additionalProperties": False,
    },
    risk=RiskLevel.C,
    reason="Rimozione di dati dal loro percorso originale.",
    consequences="L'elemento viene spostato in ~/.amy/backups/trash e può essere recuperato manualmente.",
    undo="Riporta il file dal percorso 'trash' indicato nel risultato.",
    tags=("file", "distruttivo"),
)


def _open_file(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    path = context.path_guard.resolve(str(args["path"]), must_exist=True)
    if path.is_dir():
        raise ToolValidationError("Il percorso è una cartella, non un file.")
    try:
        process = subprocess.run(["open", str(path)], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ToolValidationError("Apertura del file non riuscita.", detail=str(exc)) from exc
    if process.returncode != 0:
        raise ToolValidationError(
            "Apertura del file non riuscita.",
            detail=(process.stderr or "")[:300],
        )
    return ToolResult.success(
        {"path": str(path), "name": path.name, "opened": True},
        "Aperto %s con l'applicazione predefinita." % path.name,
    )


def _grep_files(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    query = str(args.get("query", "") or "").strip()
    if not query:
        raise ToolValidationError("La ricerca è vuota.")
    root = context.path_guard.resolve(str(args.get("path", "~")), must_exist=True)
    max_results = max(1, min(int(args.get("max_results", 20)), 100))
    max_files = max(1, min(int(args.get("max_files", 500)), 2000))
    case_sensitive = bool(args.get("case_sensitive", False))
    needle = query if case_sensitive else query.lower()
    skip = {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__"}

    if root.is_file():
        candidates = [root]
    else:
        candidates = []
        for dirpath, dirnames, filenames in os.walk(str(root), followlinks=False):
            dirnames[:] = [name for name in dirnames if name not in skip]
            for name in filenames:
                candidates.append(Path(dirpath) / name)

    results: List[Dict[str, Any]] = []
    scanned = 0
    for path in candidates:
        if len(results) >= max_results or scanned >= max_files:
            break
        try:
            if path.is_symlink() or not path.is_file():
                continue
            if path.stat().st_size > context.path_guard.max_file_bytes:
                continue
            data = path.read_bytes()
        except OSError:
            continue
        if b"\x00" in data[:4096]:
            continue
        scanned += 1
        text = data.decode("utf-8", errors="ignore")
        for number, line in enumerate(text.splitlines(), start=1):
            haystack = line if case_sensitive else line.lower()
            if needle in haystack:
                results.append({"path": str(path), "line": number, "text": line.strip()[:300]})
                if len(results) >= max_results:
                    break
    return ToolResult.success(
        {
            "query": query,
            "path": str(root),
            "results": results,
            "scanned_files": scanned,
            "truncated": len(results) >= max_results,
        },
        "Trovate %d righe in %d file." % (len(results), scanned),
    )


OPEN_FILE = ToolSpec(
    name="files.open",
    description="Apre un file con l'applicazione predefinita di macOS.",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string", "minLength": 1, "maxLength": 1000}},
        "required": ["path"],
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Apertura di un file già presente nelle aree autorizzate.",
    consequences="Il file viene aperto con l'app predefinita; eventuali macro dipendono dall'app.",
    tags=("file", "apertura"),
)

GREP_FILES = ToolSpec(
    name="files.grep",
    description=(
        "Cerca una parola o frase dentro i documenti di testo (non PDF o Word) "
        "in una cartella autorizzata e restituisce file, riga e estratto."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 200},
            "path": {"type": "string", "maxLength": 1000},
            "max_results": {"type": "integer", "minimum": 1, "maximum": 100},
            "max_files": {"type": "integer", "minimum": 1, "maximum": 2000},
            "case_sensitive": {"type": "boolean"},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Ricerca di testo in file già autorizzati, senza modificarli.",
    consequences="Nessuna modifica: i file vengono solo letti.",
    timeout_s=30.0,
    tags=("file", "ricerca", "documenti"),
)

def register(registry) -> None:
    registry.register(FunctionTool(LIST_FILES, _list_files))
    registry.register(FunctionTool(SEARCH_FILES, _search_files))
    registry.register(FunctionTool(READ_FILE, _read_file))
    registry.register(FunctionTool(OPEN_FILE, _open_file))
    registry.register(FunctionTool(GREP_FILES, _grep_files))
    registry.register(FunctionTool(WRITE_FILE, _write_file))
    registry.register(FunctionTool(MKDIR, _mkdir))
    registry.register(FunctionTool(DIFF_FILES, _diff_files))
    registry.register(_MoveTool(MOVE, _move))
    registry.register(FunctionTool(TRASH, _trash))
