# engine/scanner/frontend_scanner.py
"""Frontend impact scanner — maps ALL cross-file dependencies in React/TS/CSS codebases.

Creates graph edges for:
- imports: file A imports from file B
- uses_token: file uses CSS variable defined in tokens file
- uses_component: file renders a component from another file
- depends_on: file uses a store/context from another file

These edges enable impact analysis: "if I change tokens.css, what components break?"
"""

import logging
import re
from pathlib import Path

from core.engine.core.db import parse_rows, pool

logger = logging.getLogger(__name__)

# CSS variable pattern: var(--anything)
CSS_VAR_PATTERN = re.compile(r"var\(--([a-zA-Z0-9_-]+)\)")

# TypeScript import pattern: import { X } from "path" or import X from "path"
TS_IMPORT_PATTERN = re.compile(r"""import\s+(?:{[^}]+}|\w+|\*\s+as\s+\w+)\s+from\s+['"]([^'"]+)['"]""")

# Dynamic import: import("path") or require("path")
DYNAMIC_IMPORT_PATTERN = re.compile(r"""(?:import|require)\s*\(\s*['"]([^'"]+)['"]\s*\)""")

# React component usage: <ComponentName or <Component.Sub
COMPONENT_USAGE_PATTERN = re.compile(r"<([A-Z][a-zA-Z0-9]+(?:\.[A-Z][a-zA-Z0-9]+)?)")

# Hook usage: useXxx()
HOOK_USAGE_PATTERN = re.compile(r"\b(use[A-Z][a-zA-Z0-9]+)\s*\(")

# CSS @import
CSS_IMPORT_PATTERN = re.compile(r"""@import\s+['"]([^'"]+)['"]""")


def _resolve_import_path(import_path: str, source_file: str, base_dir: str) -> str | None:
    """Resolve a TypeScript import path to a file path relative to base_dir.

    Handles:
    - @/ alias → src/
    - Relative paths (./foo, ../foo)
    - Extension inference (.tsx, .ts, /index.tsx, /index.ts)
    """
    base = Path(base_dir)
    source = Path(source_file)

    # Skip node_modules
    if not import_path.startswith(".") and not import_path.startswith("@/"):
        return None

    # Resolve @/ alias
    if import_path.startswith("@/"):
        resolved = base / "src" / import_path[2:]
    else:
        resolved = source.parent / import_path

    # Try extensions
    for ext in ["", ".tsx", ".ts", ".jsx", ".js", ".css", "/index.tsx", "/index.ts"]:
        candidate = resolved.with_suffix(ext) if ext.startswith(".") else Path(str(resolved) + ext)
        if candidate.exists():
            try:
                return str(candidate.relative_to(base.parent))  # relative to repo root (e.g., portal/src/...)
            except ValueError:
                return str(candidate)

    return None


def scan_css_variables(tokens_file: str) -> dict[str, list[int]]:
    """Extract all CSS variable definitions from a file.

    Returns: {variable_name: [line_numbers]}
    """
    variables: dict[str, list[int]] = {}
    try:
        content = Path(tokens_file).read_text()
        for i, line in enumerate(content.split("\n"), 1):
            # Match --variable-name: value
            match = re.findall(r"--([\w-]+)\s*:", line)
            for var_name in match:
                variables.setdefault(var_name, []).append(i)
    except Exception:
        pass
    return variables


def scan_file_dependencies(file_path: str, base_dir: str) -> dict:
    """Scan a single file for all dependency types.

    Returns: {
        imports: [resolved_paths],
        css_vars_used: [var_names],
        components_used: [ComponentNames],
        hooks_used: [hookNames],
        css_imports: [resolved_paths],
    }
    """
    result: dict = {
        "imports": [],
        "css_vars_used": [],
        "components_used": [],
        "hooks_used": [],
        "css_imports": [],
    }

    try:
        content = Path(file_path).read_text()
    except Exception:
        return result

    # TypeScript imports
    for match in TS_IMPORT_PATTERN.finditer(content):
        import_path = match.group(1)
        resolved = _resolve_import_path(import_path, file_path, base_dir)
        if resolved:
            result["imports"].append(resolved)

    # Dynamic imports
    for match in DYNAMIC_IMPORT_PATTERN.finditer(content):
        import_path = match.group(1)
        resolved = _resolve_import_path(import_path, file_path, base_dir)
        if resolved:
            result["imports"].append(resolved)

    # CSS variable usage
    for match in CSS_VAR_PATTERN.finditer(content):
        var_name = match.group(1)
        if var_name not in result["css_vars_used"]:
            result["css_vars_used"].append(var_name)

    # Component usage in JSX
    for match in COMPONENT_USAGE_PATTERN.finditer(content):
        component = match.group(1)
        # Skip HTML elements and common React elements
        if component not in ("Fragment", "Suspense", "StrictMode", "Provider"):
            if component not in result["components_used"]:
                result["components_used"].append(component)

    # Hook usage
    for match in HOOK_USAGE_PATTERN.finditer(content):
        hook = match.group(1)
        if hook not in (
            "useState",
            "useEffect",
            "useCallback",
            "useMemo",
            "useRef",
            "useContext",
            "useReducer",
            "useLayoutEffect",
            "useId",
        ):
            if hook not in result["hooks_used"]:
                result["hooks_used"].append(hook)

    # CSS @import
    for match in CSS_IMPORT_PATTERN.finditer(content):
        import_path = match.group(1)
        resolved = _resolve_import_path(import_path, file_path, base_dir)
        if resolved:
            result["css_imports"].append(resolved)

    return result


async def scan_frontend(portal_dir: str, graph_id: str = "default") -> dict:
    """Scan all frontend files and create/update graph edges.

    Returns scan statistics.
    """
    portal_path = Path(portal_dir)
    src_dir = portal_path / "src"

    if not src_dir.exists():
        return {"error": f"src directory not found at {src_dir}"}

    # Collect all scannable files
    extensions = {".tsx", ".ts", ".jsx", ".js", ".css"}
    files = []
    for ext in extensions:
        files.extend(src_dir.rglob(f"*{ext}"))

    # Scan tokens file for CSS variable definitions
    tokens_file = src_dir / "styles" / "tokens.css"
    defined_vars = scan_css_variables(str(tokens_file)) if tokens_file.exists() else {}

    stats: dict = {
        "files_scanned": 0,
        "import_edges": 0,
        "token_edges": 0,
        "hook_edges": 0,
        "total_css_vars": len(defined_vars),
        "components_found": set(),
        "hooks_found": set(),
    }

    # Map of component name → file path (for component usage edges)
    component_map: dict[str, str] = {}
    for f in files:
        if f.suffix in (".tsx", ".jsx"):
            stem = f.stem
            if stem[0].isupper():
                component_map[stem] = str(f)

    # Map of hook name → file path
    hook_map: dict[str, str] = {}
    for f in files:
        content = f.read_text(errors="ignore")
        # Find exported hooks: export function useXxx or export const useXxx
        for match in re.finditer(r"export\s+(?:function|const)\s+(use[A-Z]\w+)", content):
            hook_name = match.group(1)
            hook_map[hook_name] = str(f)

    async with pool.connection() as db:
        # Get existing graph_file nodes for portal
        file_nodes = parse_rows(
            await db.query(
                "SELECT id, path FROM graph_file WHERE graph_id = $gid AND path CONTAINS 'portal/'",
                {"gid": graph_id},
            )
        )
        path_to_id = {n["path"]: str(n["id"]) for n in file_nodes}

        tokens_rel_path = "portal/src/styles/tokens.css"

        for f in files:
            try:
                rel_path = f"portal/{f.relative_to(portal_path)}"
            except ValueError:
                continue

            deps = scan_file_dependencies(str(f), str(portal_path))
            stats["files_scanned"] += 1

            source_id = path_to_id.get(rel_path)
            if not source_id:
                continue

            # Create import edges
            for imp in deps["imports"]:
                target_id = path_to_id.get(imp)
                if target_id and target_id != source_id:
                    try:
                        await db.query(
                            "CREATE frontend_dep SET source = $source, target = $target, graph_id = $gid, dep_type = 'import', source_path = $sp, target_path = $tp",
                            {"source": source_id, "target": target_id, "gid": graph_id, "sp": rel_path, "tp": imp},
                        )
                        stats["import_edges"] += 1
                    except Exception as e:
                        logger.debug("Import edge failed: %s", e)

            # Create token usage edges
            for var_name in deps["css_vars_used"]:
                if var_name in defined_vars:
                    tokens_id = path_to_id.get(tokens_rel_path)
                    if tokens_id and source_id:
                        try:
                            await db.query(
                                "CREATE frontend_dep SET source = $source, target = $target, graph_id = $gid, dep_type = 'uses_token', token_name = $tok, source_path = $sp, target_path = $tp",
                                {
                                    "source": source_id,
                                    "target": tokens_id,
                                    "gid": graph_id,
                                    "tok": var_name,
                                    "sp": rel_path,
                                    "tp": tokens_rel_path,
                                },
                            )
                            stats["token_edges"] += 1
                        except Exception as e:
                            logger.debug("Token edge failed: %s", e)

            # Create hook/store dependency edges
            for hook in deps["hooks_used"]:
                hook_file = hook_map.get(hook)
                if hook_file:
                    try:
                        hook_rel = f"portal/{Path(hook_file).relative_to(portal_path)}"
                    except ValueError:
                        continue
                    target_id = path_to_id.get(hook_rel)
                    if target_id and target_id != source_id:
                        try:
                            await db.query(
                                "CREATE frontend_dep SET source = $source, target = $target, graph_id = $gid, dep_type = 'uses_hook', hook_name = $hook, source_path = $sp, target_path = $tp",
                                {
                                    "source": source_id,
                                    "target": target_id,
                                    "gid": graph_id,
                                    "hook": hook,
                                    "sp": rel_path,
                                    "tp": hook_rel,
                                },
                            )
                            stats["hook_edges"] += 1
                        except Exception:
                            pass

            stats["components_found"].update(deps["components_used"])
            stats["hooks_found"].update(deps["hooks_used"])

    stats["components_found"] = len(stats["components_found"])
    stats["hooks_found"] = len(stats["hooks_found"])

    return stats
