# engine/scanner/scanner.py
"""Git-first code scanner — builds a knowledge graph from any repository."""

import asyncio
import logging
import os
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from git import Repo
from pydriller import Repository
from surrealdb import RecordID

from core.engine.core.db import parse_rows, pool
from core.engine.core.exceptions import ScannerError
from core.engine.scanner.ast_parser import parse_file
from core.engine.scanner.import_parser import (
    parse_python_imports,
    parse_typescript_imports,
    resolve_import_to_file,
)

logger = logging.getLogger(__name__)


def _validate_repo_path(repo_path: str) -> str:
    """Validate and normalise a repository path before scanning.

    Raises ScannerError if the path doesn't exist or is not a directory.
    Returns the absolute, normalised path so callers don't need to repeat
    the os.path.abspath call.
    """
    normalised = os.path.abspath(repo_path)
    if not os.path.exists(normalised):
        raise ScannerError(f"Repository path does not exist: {normalised!r}")
    if not os.path.isdir(normalised):
        raise ScannerError(f"Repository path is not a directory: {normalised!r}")
    return normalised


# Conventional-commit prefixes that are definitively trivial — skip classification entirely
_TRIVIAL_PREFIXES = re.compile(
    r"^(fix|chore|style|test|docs|ci|build|bump|release|revert|wip|lint|cleanup|typo)\b",
    re.IGNORECASE,
)

# Implementation prefixes: commit record is created, but no decision_type assigned.
# feat/refactor commits are build steps, not intentional design choices.
# Intentional decisions should be captured via ace_capture_decision instead.
_IMPLEMENTATION_PREFIXES = re.compile(
    r"^(feat|feature|refactor|redesign)\b",
    re.IGNORECASE,
)

# Explicit decision-oriented prefixes — assign decision_type directly without LLM
_DECISION_PREFIX_TYPE_MAP = {
    "arch": "architecture",
    "architecture": "architecture",
    "migrate": "direction",
    "migration": "direction",
    "decide": "direction",
    "direction": "direction",
    "convention": "convention",
    "breaking": "trade_off",
}


async def _classify_commit_decision(title: str, description: str, changed_files: list[str]) -> dict | None:
    """Extract decision metadata from a commit message.

    Three tiers:
    1. Trivial prefixes (fix/chore/test/docs…) → None immediately
    2. Implementation prefixes (feat/refactor) → None; record is still created
       by the scanner but without a decision_type.  Intentional decisions belong
       in the `decision` table via ace_capture_decision.
    3. Explicit decision prefixes (arch/migrate/decide…) → fast-path result
    4. Freeform messages with substantive body → LLM with 30s timeout

    Returns None if the commit carries no meaningful decision signal.
    """
    if not title:
        return None

    # Strip conventional-commit scope: "feat(orchestration): ..." → "feat"
    prefix_match = re.match(r"^([a-zA-Z_\-]+)(?:\([^)]*\))?[!:]?\s*", title)
    prefix = prefix_match.group(1).lower() if prefix_match else ""

    # Tier 1: definitely trivial
    if _TRIVIAL_PREFIXES.match(title):
        return None

    # Tier 2: implementation steps — commit record created, no classification
    if _IMPLEMENTATION_PREFIXES.match(title):
        return None

    body = description.strip() if description else ""

    # Tier 3: explicit decision prefix → classify without LLM
    if prefix in _DECISION_PREFIX_TYPE_MAP and (len(title) >= 20 or body):
        body_lines = [ln.strip() for ln in body.splitlines() if ln.strip() and ln.strip() != title]
        rationale = body_lines[0][:200] if body_lines else title
        return {
            "has_decision": True,
            "decision_type": _DECISION_PREFIX_TYPE_MAP[prefix],
            "rationale": rationale,
            "alternatives": [],
        }

    # Tier 4: freeform message — only worth LLM if there's substantive body text
    if len(title) < 30 and not body:
        return None

    try:
        from core.engine.core.config import settings
        from core.engine.core.llm import get_llm

        llm = get_llm()
        result = await asyncio.wait_for(
            llm.complete_json(
                f"""You are classifying a git commit message (no diff is available — message text only).

Commit title: {title}
Commit body: {body[:800] if body else "(none)"}
Files changed: {", ".join(changed_files[:10]) if changed_files else "(unknown)"}

Determine whether this commit records an architectural decision, convention, trade-off, or directional choice.
Base your answer ONLY on the text above.  Do NOT ask for the diff.

Return JSON with these exact keys:
{{
  "has_decision": true or false,
  "decision_type": "architecture" | "convention" | "trade_off" | "direction" | null,
  "rationale": "one sentence extracted from the message" or null,
  "alternatives": ["rejected option"] or []
}}

Set has_decision: false for: formatting, typo fixes, dependency bumps, test additions, CI changes.""",
                model=settings.llm_budget_model,
            ),
            timeout=30.0,
        )
        if not result.get("has_decision"):
            return None
        return result
    except asyncio.TimeoutError:
        logger.warning("Commit decision classification timed out for: %s", title)
        return None
    except Exception:
        logger.warning("Commit decision classification failed", exc_info=True)
        return None


# Directories to skip during scan
SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".eggs",
    "egg-info",
    ".next",
    ".nuxt",
    "coverage",
    ".coverage",
    ".claude",  # Claude Code worktrees + memory — not application code
    "claude-repo",  # external repo clone — not the platform's own source
}

# Binary/non-text extensions to skip
BINARY_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".so",
    ".o",
    ".a",
    ".dylib",
    ".dll",
    ".exe",
    ".bin",
    ".dat",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".svg",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".mp3",
    ".mp4",
    ".wav",
    ".avi",
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    ".rar",
    ".7z",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".jar",
    ".class",
    ".wasm",
    ".lock",
}

# Extension to language mapping
LANG_MAP = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".sql": "sql",
    ".surql": "surql",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".xml": "xml",
    ".md": "markdown",
    ".rst": "restructuredtext",
    ".vue": "vue",
    ".svelte": "svelte",
    ".lua": "lua",
    ".r": "r",
    ".R": "r",
    ".dart": "dart",
    ".zig": "zig",
    ".nim": "nim",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hs": "haskell",
    ".ml": "ocaml",
    ".clj": "clojure",
    ".tf": "terraform",
    ".proto": "protobuf",
    ".graphql": "graphql",
    ".gql": "graphql",
    "Makefile": "make",
    "Dockerfile": "docker",
    ".dockerfile": "docker",
}


def _slug(path: str) -> str:
    """Convert a file path to a safe SurrealDB record ID component.

    "engine/core/db.py" -> "engine_core_db_py"
    """
    slug = re.sub(r"[^a-zA-Z0-9]", "_", path)
    # Collapse multiple underscores
    slug = re.sub(r"_+", "_", slug)
    # Strip leading/trailing underscores
    slug = slug.strip("_")
    return slug.lower()


def _detect_language(path: str) -> str:
    """Detect programming language from file extension or name."""
    name = os.path.basename(path)
    if name in LANG_MAP:
        return LANG_MAP[name]
    _, ext = os.path.splitext(path)
    return LANG_MAP.get(ext, "")


def _count_lines(full_path: str) -> int:
    """Count lines in a file. Returns 0 if unreadable."""
    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def _is_hidden(name: str) -> bool:
    """Check if a file/directory name is hidden (starts with .)."""
    return name.startswith(".") and name not in {".", ".."}


def _should_skip_dir(name: str) -> bool:
    """Check if a directory should be skipped."""
    return name in SKIP_DIRS or _is_hidden(name)


def _is_git_untracked_dir(repo_path: str, name: str) -> bool:
    """True if `name/` has NO git-tracked files (untracked WIP/cruft). Non-fatal: a non-git repo or
    any git error returns False (assume tracked → do NOT skip), so we never drop a legit dir."""
    try:
        out = subprocess.run(
            ["git", "-C", repo_path, "ls-files", "--", name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return out.returncode == 0 and not out.stdout.strip()
    except Exception:
        return False


def _is_stale_generation_dir(repo_path: str, dirpath: str, name: str) -> bool:
    """A root-level dir that duplicates a `core/<name>` tree AND is git-untracked is a stale
    pre-restructure generation (e.g. an untracked `engine/` left beside the canonical `core/engine/`).
    Skip it so the scanner never indexes two generations into one graph. The untracked check keeps
    this safe on EXTERNAL repos (a generic scanner): a repo whose canonical source genuinely is a
    tracked `foo/` beside a tracked `core/foo/` is never dropped. Root-level only: `core/engine`
    itself (dirpath != repo root) is never skipped."""
    if os.path.abspath(dirpath) != os.path.abspath(repo_path):
        return False
    if not os.path.isdir(os.path.join(repo_path, "core", name)):
        return False
    if not _is_git_untracked_dir(repo_path, name):
        return False
    logger.info("scanner: skipping stale untracked generation dir %r (core/%s is the canonical tree)", name, name)
    return True


def _should_skip_file(path: str) -> bool:
    """Check if a file should be skipped (binary, too large, etc.)."""
    _, ext = os.path.splitext(path)
    if ext in BINARY_EXTENSIONS:
        return True
    return False


def _walk_repo(repo_path: str) -> list[dict]:
    """Walk the repository and collect file metadata.

    Returns list of dicts: [{path, name, extension, language, size_bytes, line_count, full_path}]
    """
    files = []
    repo_path = os.path.abspath(repo_path)

    for dirpath, dirnames, filenames in os.walk(repo_path):
        # Filter out directories we want to skip (modifying in place affects walk).
        # Also drop stale pre-restructure generations (a root `engine/` beside `core/engine/`).
        dirnames[:] = [
            d for d in dirnames if not _should_skip_dir(d) and not _is_stale_generation_dir(repo_path, dirpath, d)
        ]

        for filename in filenames:
            if _is_hidden(filename):
                continue

            full_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(full_path, repo_path)

            if _should_skip_file(rel_path):
                continue

            _, ext = os.path.splitext(filename)
            size = 0
            try:
                size = os.path.getsize(full_path)
            except OSError:
                continue

            files.append(
                {
                    "path": rel_path,
                    "name": filename,
                    "extension": ext,
                    "language": _detect_language(rel_path),
                    "size_bytes": size,
                    "line_count": _count_lines(full_path),
                    "full_path": full_path,
                }
            )

    return files


def _get_changed_files_since(repo_path: str, since: object) -> set[str]:
    """Return paths (relative to repo root) of files changed since *since*.

    Covers both committed changes (``git log --since``) and any staged/unstaged
    working-tree changes (``git diff --name-only HEAD``).  Returns an empty set
    on any error so callers fall back to a full scan.
    """
    try:
        if hasattr(since, "isoformat"):
            # Ensure timezone-aware so git --since interprets correctly (not local time)
            if hasattr(since, "tzinfo") and since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
            ts = since.isoformat()
        else:
            ts = str(since)

        log_out = subprocess.run(
            ["git", "log", f"--since={ts}", "--name-only", "--pretty=format:"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout
        changed = {line.strip() for line in log_out.splitlines() if line.strip()}

        diff_out = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
        changed.update(line.strip() for line in diff_out.splitlines() if line.strip())

        return changed
    except Exception as exc:
        logger.warning("_get_changed_files_since failed, falling back to full scan: %s", exc)
        return set()


async def scan_repo(repo_path: str, graph_id: str = "default") -> dict:
    """Scan a git repository and build the knowledge graph.

    Returns: {files_created, imports_created, decisions_created, users_created,
              related_edges_created, graph_id}
    """
    repo_path = _validate_repo_path(repo_path)
    repo = Repo(repo_path)
    repo_name = os.path.basename(repo_path)

    stats = {
        "files_created": 0,
        "functions_created": 0,
        "imports_created": 0,
        "decisions_created": 0,
        "users_created": 0,
        "related_edges_created": 0,
        "graph_id": graph_id,
    }

    import time as _time

    logger.info("scan_repo started: %s (graph_id=%s)", repo_path, graph_id)
    _t0 = _time.monotonic()

    async with pool.connection() as db:
        # ------------------------------------------------------------------
        # Step 1: Upsert graph record (idempotent — rescans update, not duplicate)
        # Capture old scanned_at BEFORE the upsert so incremental scan can use it.
        # ------------------------------------------------------------------
        _prev = parse_rows(await db.query("SELECT scan_completed_at FROM $rid", {"rid": RecordID("graph", graph_id)}))
        # Use scan_completed_at (written at end of scan) — not scanned_at (written at start).
        # This ensures incremental detection only activates after a full successful scan.
        _last_scan_at = _prev[0].get("scan_completed_at") if _prev else None

        if graph_id.startswith("competitor_"):
            _mode = "competitor"
        elif graph_id == "default":
            _mode = "permanent"
        else:
            _mode = "temporary"

        await db.query(
            """
            UPSERT $rid SET
                graph_id   = $id,
                name       = $name,
                repo_path  = $path,
                mode       = $mode,
                scanned_at = time::now()
            """,
            {
                "rid": RecordID("graph", graph_id),
                "id": graph_id,
                "name": repo_name,
                "path": repo_path,
                "mode": _mode,
            },
        )

        # ------------------------------------------------------------------
        # Step 2: Scan directory tree -> file nodes (batched)
        # ------------------------------------------------------------------
        logger.info("Step 2: walking repo (%.1fs elapsed)", _time.monotonic() - _t0)
        file_list = await asyncio.to_thread(_walk_repo, repo_path)
        logger.info("Step 2: found %d files (%.1fs elapsed)", len(file_list), _time.monotonic() - _t0)

        # Build full lookup first (needed for import resolution regardless of scope)
        repo_files: dict[str, str] = {}
        for f in file_list:
            repo_files[f["path"]] = _slug(f["path"])

        # Incremental: only process files changed since last scan
        if _last_scan_at:
            _changed = _get_changed_files_since(repo_path, _last_scan_at)
            if _changed:
                process_files = [f for f in file_list if f["path"] in _changed]
                logger.info(
                    "Incremental scan for %s: %d changed files (of %d total)",
                    repo_path,
                    len(process_files),
                    len(file_list),
                )
            else:
                logger.info("Incremental scan for %s: no changes since %s", repo_path, _last_scan_at)
                async with pool.connection() as _noop_db:
                    await _noop_db.query(
                        "UPDATE $rid SET scan_completed_at = time::now()",
                        {"rid": RecordID("graph", graph_id)},
                    )
                return stats
        else:
            process_files = file_list

        _BATCH = 50

        _file_coros = [
            db.query(
                """
                UPSERT $id SET
                    path = $path,
                    name = $name,
                    extension = $ext,
                    language = $lang,
                    size_bytes = $size,
                    line_count = $lines,
                    graph_id = $gid
                """,
                {
                    "id": RecordID("graph_file", repo_files[f["path"]]),
                    "path": f["path"],
                    "name": f["name"],
                    "ext": f["extension"],
                    "lang": f["language"],
                    "size": f["size_bytes"],
                    "lines": f["line_count"],
                    "gid": graph_id,
                },
            )
            for f in process_files
        ]
        for i in range(0, len(_file_coros), _BATCH):
            _results = await asyncio.gather(*_file_coros[i : i + _BATCH], return_exceptions=True)
            stats["files_created"] += sum(1 for r in _results if not isinstance(r, Exception))

        # ------------------------------------------------------------------
        # Step 3: AST parsing -> function nodes + import edges (batched)
        # Parse all files first (sync/CPU in thread), then fire DB writes concurrently.
        # ------------------------------------------------------------------
        logger.info("Step 3: AST parsing %d files (%.1fs elapsed)", len(process_files), _time.monotonic() - _t0)

        def _parse_all() -> tuple[list[tuple], list[tuple[str, str]]]:
            """Parse every file's AST + imports synchronously in a thread.

            Returns (results, skipped) — skipped entries are (path, error_summary)
            so the caller can log them. Previously the parse-failure path was
            silently dropped: `len(_parsed_files)` reported only successful files
            and there was no signal that some files were missing from the graph.
            decision:ur72ghj9p0ql01fo76j6 — make skips visible.
            """
            results = []
            skipped: list[tuple[str, str]] = []
            for f in process_files:
                try:
                    content_bytes = open(f["full_path"], "rb").read()
                    parsed = parse_file(content_bytes, f["language"])
                    results.append((f, parsed, content_bytes))
                except Exception as exc:
                    skipped.append((f.get("path", f.get("full_path", "<unknown>")), f"{type(exc).__name__}: {exc}"))
            return results, skipped

        _parsed_files, _skipped_files = await asyncio.to_thread(_parse_all)
        if _skipped_files:
            # Log skipped files at WARNING — they're not in the graph and the
            # operator should be able to diagnose why without code-diving.
            logger.warning(
                "Step 3: %d file(s) skipped during parse — first 5: %s",
                len(_skipped_files),
                _skipped_files[:5],
            )
        logger.info(
            "Step 3: parsed %d files, skipped %d (%.1fs elapsed)",
            len(_parsed_files),
            len(_skipped_files),
            _time.monotonic() - _t0,
        )

        _func_coros: list = []
        _import_coros: list = []

        for f, parsed, content_bytes in _parsed_files:
            try:
                language = f["language"]
                file_rid = RecordID("graph_file", repo_files[f["path"]])

                for func in parsed.functions:
                    func_slug = _slug(f"{f['path']}_{func.name}")
                    _func_coros.append(
                        db.query(
                            """
                            UPSERT $id SET
                                name = $name,
                                file = $file,
                                line_start = $ls,
                                line_end = $le,
                                kind = $kind,
                                parameters = $params,
                                return_type = $ret,
                                graph_id = $gid
                            """,
                            {
                                "id": RecordID("graph_function", func_slug),
                                "name": func.name,
                                "file": file_rid,
                                "ls": func.line_start,
                                "le": func.line_end,
                                "kind": func.kind,
                                "params": func.parameters or None,
                                "ret": func.return_type or None,
                                "gid": graph_id,
                            },
                        )
                    )

                for cls in parsed.classes:
                    cls_slug = _slug(f"{f['path']}_{cls.name}")
                    _func_coros.append(
                        db.query(
                            """
                            UPSERT $id SET
                                name = $name,
                                file = $file,
                                line_start = $ls,
                                line_end = $le,
                                kind = 'class',
                                graph_id = $gid
                            """,
                            {
                                "id": RecordID("graph_function", cls_slug),
                                "name": cls.name,
                                "file": file_rid,
                                "ls": cls.line_start,
                                "le": cls.line_end,
                                "gid": graph_id,
                            },
                        )
                    )

                if parsed.imports:
                    for imp in parsed.imports:
                        resolved = resolve_import_to_file(imp.module, repo_files, f["path"])
                        if resolved and resolved in repo_files:
                            _import_coros.append(
                                db.query(
                                    """
                                    RELATE $from -> imports -> $to SET
                                        import_name = $name,
                                        source = 'scanner'
                                    """,
                                    {
                                        "from": file_rid,
                                        "to": RecordID("graph_file", repo_files[resolved]),
                                        "name": imp.name or imp.module,
                                    },
                                )
                            )
                elif language in ("python", "typescript", "javascript"):
                    # Fallback: regex parser for files where tree-sitter returned no imports
                    try:
                        content_str = content_bytes.decode("utf-8", errors="replace")
                        regex_imports = (
                            parse_python_imports(content_str, f["path"])
                            if language == "python"
                            else parse_typescript_imports(content_str, f["path"])
                        )
                        for imp in regex_imports:
                            resolved = resolve_import_to_file(imp["module"], repo_files, f["path"])
                            if resolved and resolved in repo_files:
                                _import_coros.append(
                                    db.query(
                                        """
                                        RELATE $from -> imports -> $to SET
                                            import_name = $name,
                                            source = 'scanner'
                                        """,
                                        {
                                            "from": file_rid,
                                            "to": RecordID("graph_file", repo_files[resolved]),
                                            "name": imp.get("name") or imp["module"],
                                        },
                                    )
                                )
                    except Exception:
                        pass

            except Exception as exc:
                logger.debug("Failed to parse %s: %s", f["path"], exc)

        for i in range(0, len(_func_coros), _BATCH):
            _results = await asyncio.gather(*_func_coros[i : i + _BATCH], return_exceptions=True)
            stats["functions_created"] += sum(1 for r in _results if not isinstance(r, Exception))

        for i in range(0, len(_import_coros), _BATCH):
            _results = await asyncio.gather(*_import_coros[i : i + _BATCH], return_exceptions=True)
            stats["imports_created"] += sum(1 for r in _results if not isinstance(r, Exception))

        # ------------------------------------------------------------------
        # Step 4: Git log via PyDriller -> decision + user nodes
        # ------------------------------------------------------------------
        user_commits: dict[str, int] = Counter()
        # Track which files each commit touches for co-change analysis (step 6)
        commit_files: list[list[str]] = []
        # Track change frequency and ownership for step 5
        file_change_count: dict[str, int] = Counter()
        file_authors: dict[str, Counter] = defaultdict(Counter)

        logger.info("Step 4: loading git history via PyDriller (%.1fs elapsed)", _time.monotonic() - _t0)
        since_date = datetime.now(tz=timezone.utc) - timedelta(days=180)

        def _load_commits() -> list:
            raw = list(Repository(repo_path, since=since_date, num_workers=1).traverse_commits())
            return raw[-500:] if len(raw) > 500 else raw

        try:
            pd_commits = await asyncio.to_thread(_load_commits)
        except Exception as exc:
            logger.warning("PyDriller failed, falling back to GitPython: %s", exc)
            pd_commits = []

        logger.info("Step 4: processing %d commits (%.1fs elapsed)", len(pd_commits), _time.monotonic() - _t0)
        for commit in pd_commits:
            try:
                # --- User node (upsert by author name) ---
                author_name = commit.author.name or "Unknown"
                author_email = commit.author.email or ""
                user_slug = _slug(author_name)
                user_commits[author_name] += 1

                ts = commit.author_date.isoformat() if commit.author_date else datetime.now(tz=timezone.utc).isoformat()

                await db.query(
                    """
                    UPSERT $id SET
                        name = $name,
                        email = $email,
                        source = 'git',
                        commit_count += 1,
                        last_active = <datetime>$ts,
                        graph_id = $gid
                    """,
                    {
                        "id": RecordID("graph_user", user_slug),
                        "name": author_name,
                        "email": author_email,
                        "ts": ts,
                        "gid": graph_id,
                    },
                )

                # --- Decision node from commit ---
                msg_lines = commit.msg.strip().split("\n")
                title = msg_lines[0][:200] if msg_lines else "No message"
                description = "\n".join(msg_lines[1:]).strip() if len(msg_lines) > 1 else ""
                commit_hex = commit.hash[:12]
                decision_slug = f"commit_{commit_hex}"

                # Collect changed file paths (no_metric=True so no complexity/methods)
                changed_paths: list[str] = []
                for mod_file in commit.modified_files:
                    path = mod_file.new_path or mod_file.old_path
                    if path:
                        changed_paths.append(path)

                await db.query(
                    """
                    CREATE $id SET
                        title = $title,
                        description = $desc,
                        source_commit = $sha,
                        timestamp = <datetime>$ts,
                        files_changed = $nfiles,
                        graph_id = $gid
                    """,
                    {
                        "id": RecordID("graph_decision", decision_slug),
                        "title": title,
                        "desc": description,
                        "sha": commit.hash,
                        "ts": ts,
                        "nfiles": len(changed_paths),
                        "gid": graph_id,
                    },
                )
                stats["decisions_created"] += 1

                # --- produced edge: user -> decision ---
                await db.query(
                    """
                    RELATE $from -> produced -> $to SET
                        source = 'scanner'
                    """,
                    {
                        "from": RecordID("graph_user", user_slug),
                        "to": RecordID("graph_decision", decision_slug),
                    },
                )

                # --- improves edges: decision -> files changed ---
                commit_files.append(changed_paths)

                for changed_path in changed_paths:
                    if changed_path in repo_files:
                        file_slug = repo_files[changed_path]
                        try:
                            await db.query(
                                """
                                RELATE $from -> improves -> $to SET
                                    source = 'scanner'
                                """,
                                {
                                    "from": RecordID("graph_decision", decision_slug),
                                    "to": RecordID("graph_file", file_slug),
                                },
                            )
                        except Exception:
                            pass

                    # Accumulate for step 5
                    file_change_count[changed_path] += 1
                    file_authors[changed_path][author_name] += 1

                # --- semantic classification of commit decision ---
                classification = await _classify_commit_decision(
                    title=commit.msg.split("\n")[0],
                    description=commit.msg,
                    changed_files=[f.filename for f in commit.modified_files],
                )
                if classification:
                    try:
                        await db.query(
                            """
                            UPDATE <record>$decision_id SET
                                decision_type = $dtype,
                                alternatives = $alts,
                                tags = array::union(tags, ['auto-classified'])
                            """,
                            {
                                "decision_id": RecordID("graph_decision", decision_slug),
                                "dtype": classification.get("decision_type"),
                                "alts": classification.get("alternatives", []),
                            },
                        )
                    except Exception:
                        logger.warning("Failed to update graph_decision with classification", exc_info=True)

                # --- affected edges: decision -> capability (via realizes) ---
                try:
                    from core.engine.graph.edge_writer import create_edge as _create_edge

                    file_slugs = [repo_files[p] for p in changed_paths if p in repo_files]
                    if file_slugs:
                        cap_result = await db.query(
                            """SELECT out AS capability
                               FROM realizes
                               WHERE in IN $file_ids
                               GROUP BY capability""",
                            {"file_ids": [RecordID("graph_file", s) for s in file_slugs]},
                        )
                        from core.engine.core.db import parse_rows as _parse_rows

                        for row in _parse_rows(cap_result):
                            cap_id = row.get("capability")
                            if cap_id:
                                await _create_edge(
                                    "affected",
                                    str(RecordID("graph_decision", decision_slug)),
                                    str(cap_id),
                                )
                except Exception:
                    pass  # best-effort

            except Exception as exc:
                logger.debug(
                    "Failed to process commit %s: %s",
                    getattr(commit, "hash", "?"),
                    exc,
                )

        # GitPython fallback if PyDriller yielded nothing
        if not pd_commits:
            try:
                gp_commits = list(repo.iter_commits(max_count=500))
            except Exception:
                gp_commits = []

            for commit in gp_commits:
                try:
                    author_name = commit.author.name or "Unknown"
                    author_email = commit.author.email or ""
                    user_slug = _slug(author_name)
                    user_commits[author_name] += 1

                    await db.query(
                        """
                        UPSERT $id SET
                            name = $name,
                            email = $email,
                            source = 'git',
                            commit_count += 1,
                            last_active = <datetime>$ts,
                            graph_id = $gid
                        """,
                        {
                            "id": RecordID("graph_user", user_slug),
                            "name": author_name,
                            "email": author_email,
                            "ts": commit.authored_datetime.isoformat(),
                            "gid": graph_id,
                        },
                    )

                    msg_lines = commit.message.strip().split("\n")
                    title = msg_lines[0][:200] if msg_lines else "No message"
                    description = "\n".join(msg_lines[1:]).strip() if len(msg_lines) > 1 else ""
                    commit_hex = commit.hexsha[:12]
                    decision_slug = f"commit_{commit_hex}"

                    await db.query(
                        """
                        CREATE $id SET
                            title = $title,
                            description = $desc,
                            source_commit = $sha,
                            timestamp = <datetime>$ts,
                            graph_id = $gid
                        """,
                        {
                            "id": RecordID("graph_decision", decision_slug),
                            "title": title,
                            "desc": description,
                            "sha": commit.hexsha,
                            "ts": commit.authored_datetime.isoformat(),
                            "gid": graph_id,
                        },
                    )
                    stats["decisions_created"] += 1

                    await db.query(
                        """
                        RELATE $from -> produced -> $to SET
                            source = 'scanner'
                        """,
                        {
                            "from": RecordID("graph_user", user_slug),
                            "to": RecordID("graph_decision", decision_slug),
                        },
                    )

                    changed_files_gp = list(commit.stats.files.keys())
                    commit_files.append(changed_files_gp)

                    for changed_path in changed_files_gp:
                        if changed_path in repo_files:
                            file_slug = repo_files[changed_path]
                            try:
                                await db.query(
                                    """
                                    RELATE $from -> improves -> $to SET
                                        source = 'scanner'
                                    """,
                                    {
                                        "from": RecordID("graph_decision", decision_slug),
                                        "to": RecordID("graph_file", file_slug),
                                    },
                                )
                            except Exception:
                                pass

                        file_change_count[changed_path] += 1
                        file_authors[changed_path][author_name] += 1

                except Exception as exc:
                    logger.debug(
                        "Failed to process commit %s: %s",
                        getattr(commit, "hexsha", "?"),
                        exc,
                    )

        # Count unique users
        stats["users_created"] = len(user_commits)

        # ------------------------------------------------------------------
        # Step 5: Change frequency + ownership (accumulated in step 4)
        # ------------------------------------------------------------------
        for rel_path, count in file_change_count.items():
            if rel_path not in repo_files:
                continue
            file_slug = repo_files[rel_path]
            top_author = file_authors[rel_path].most_common(1)
            owner = top_author[0][0] if top_author else None
            try:
                await db.query(
                    """
                    UPDATE <record>$id SET
                        change_frequency = $freq,
                        ownership = $owner
                    """,
                    {
                        "id": RecordID("graph_file", file_slug),
                        "freq": count,
                        "owner": owner,
                    },
                )
            except Exception as exc:
                logger.debug("Failed to update change frequency for %s: %s", rel_path, exc)

        # ------------------------------------------------------------------
        # Step 6: Co-change analysis -> related_to edges
        # ------------------------------------------------------------------
        co_change: Counter = Counter()
        for files_in_commit in commit_files:
            # Only process commits that touch a reasonable number of files
            if len(files_in_commit) > 50:
                continue
            # Only consider files that exist in our repo_files
            known = [f for f in files_in_commit if f in repo_files]
            for i, f1 in enumerate(known):
                for f2 in known[i + 1 :]:
                    pair = tuple(sorted([f1, f2]))
                    co_change[pair] += 1

        for (f1, f2), count in co_change.items():
            if count < 3:
                continue
            slug1 = repo_files[f1]
            slug2 = repo_files[f2]
            strength = min(1.0, count / 20.0)  # Normalize: 20+ co-changes = 1.0
            try:
                await db.query(
                    """
                    RELATE $from -> related_to -> $to SET
                        strength = $strength,
                        source = 'scanner',
                        confidence = $confidence
                    """,
                    {
                        "from": RecordID("graph_file", slug1),
                        "to": RecordID("graph_file", slug2),
                        "strength": strength,
                        "confidence": min(0.9, count / 10.0),
                    },
                )
                stats["related_edges_created"] += 1
            except Exception as exc:
                logger.debug("Failed to create related_to edge %s <-> %s: %s", f1, f2, exc)

        # ------------------------------------------------------------------
        # Step 7: Update graph with counts
        # ------------------------------------------------------------------
        total_nodes = (
            stats["files_created"] + stats["functions_created"] + stats["decisions_created"] + stats["users_created"]
        )
        total_edges = stats["imports_created"] + stats["related_edges_created"]

        await db.query(
            """
            UPDATE $rid SET
                node_count         = $nodes,
                edge_count         = $edges,
                scan_completed_at  = time::now()
            """,
            {
                "rid": RecordID("graph", graph_id),
                "nodes": total_nodes,
                "edges": total_edges,
            },
        )

    logger.info(
        "Scan complete for %s (graph_id=%s): %d files, %d functions, %d imports, "
        "%d decisions, %d users, %d related edges",
        repo_path,
        graph_id,
        stats["files_created"],
        stats["functions_created"],
        stats["imports_created"],
        stats["decisions_created"],
        stats["users_created"],
        stats["related_edges_created"],
    )

    # Post-scan hook: update product map (skip for external/competitor graphs —
    # capability mapping uses ACE's own realizes edges, not the scanned repo's)
    if not graph_id.startswith("competitor_"):
        try:
            from core.engine.product.capability_mapper import CapabilityMapper

            mapper = CapabilityMapper(pool)
            # Bootstrap realizes edges if none exist yet (first scan) OR if the
            # existing edges are stale (all referenced files missing on disk).
            # decision:fepcr57v26jh9qyk9jfy — audit found the only 4 realizes
            # edges all point at deleted portal files; without this re-trigger
            # the scanner would never re-bootstrap and the capability→code
            # graph stays collapsed permanently.
            async with pool.connection() as _db:
                _r = await _db.query("SELECT count() AS c FROM realizes GROUP ALL")
                _rows = parse_rows(_r)
                _edge_count = _rows[0].get("c", 0) if _rows else 0
                # decision:fepcr57v26jh9qyk9jfy — v061 renamed capability.org → product.
                # Prior code queried `SELECT org` and tried to read `.get("product")` from
                # the result (always missing → fallback to "product:platform"). Use the
                # correct field name; fall back only if no capability rows exist.
                _org_rows = parse_rows(await _db.query("SELECT product FROM capability LIMIT 1"))
                _org_id = str(_org_rows[0].get("product", "product:platform")) if _org_rows else "product:platform"

                # Stale-edge detection: if every existing realizes edge points at a
                # file that no longer exists in graph_file, treat as needing re-bootstrap.
                _stale_bootstrap = False
                if _edge_count > 0:
                    _stale_check = parse_rows(
                        await _db.query(
                            "SELECT in.path AS path FROM realizes",
                        )
                    )
                    _live_paths = {f["path"] for f in process_files}
                    _stale_count = sum(1 for row in _stale_check if (row.get("path") or "") not in _live_paths)
                    if _stale_check and _stale_count == len(_stale_check):
                        _stale_bootstrap = True
                        logger.warning(
                            "All %d realizes edges point at files not in current scan — "
                            "re-bootstrapping capability mapping",
                            len(_stale_check),
                        )
            if _edge_count == 0 or _stale_bootstrap:
                bootstrap_result = await mapper.map_files_to_capabilities(_org_id)
                logger.info("Bootstrap capability mapping: %s", bootstrap_result)
            else:
                new_files = [{"id": repo_files[f["path"]], "path": f["path"]} for f in process_files]
                if new_files:
                    map_result = await mapper.incremental_map(new_files, _org_id)
                    logger.info("Capability mapping: %s", map_result)
        except Exception as e:
            logger.warning("Post-scan capability mapping failed (non-fatal): %s", e)

    # Step 8: Embed files (semantic search)
    try:
        from core.engine.scanner.embed_hook import embed_files

        embed_result = await embed_files(repo_path, graph_id)
        stats["files_embedded"] = embed_result.get("embedded", 0)
    except Exception as exc:
        logger.warning("Embedding step failed (non-blocking): %s", exc)
        stats["files_embedded"] = 0

    return stats
