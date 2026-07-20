# engine/scanner/import_parser.py
"""Parse import statements from Python and TypeScript/JavaScript files."""

import os
import re


def parse_python_imports(content: str, file_path: str) -> list[dict]:
    """Parse Python import statements.

    Returns list of dicts: [{module, name, alias}]
    """
    imports = []

    # from X import Y [as Z], ...
    from_pattern = re.compile(
        r"^from\s+([\w.]+)\s+import\s+(.+)",
        re.MULTILINE,
    )
    for match in from_pattern.finditer(content):
        module = match.group(1)
        names_str = match.group(2).strip()
        # Handle trailing comments
        names_str = names_str.split("#")[0].strip()
        # Handle multiline imports with parens — just take what's on this line
        names_str = names_str.strip("()")
        for part in names_str.split(","):
            part = part.strip()
            if not part or part == "\\":
                continue
            # Handle "name as alias"
            alias_match = re.match(r"(\w+)\s+as\s+(\w+)", part)
            if alias_match:
                imports.append(
                    {
                        "module": module,
                        "name": alias_match.group(1),
                        "alias": alias_match.group(2),
                    }
                )
            else:
                name = part.split()[0] if part.split() else part
                if re.match(r"^\w+$", name):
                    imports.append({"module": module, "name": name, "alias": None})

    # import X [as Y]
    import_pattern = re.compile(
        r"^import\s+([\w.]+)(?:\s+as\s+(\w+))?",
        re.MULTILINE,
    )
    for match in import_pattern.finditer(content):
        module = match.group(1)
        alias = match.group(2)
        imports.append({"module": module, "name": None, "alias": alias})

    return imports


def parse_typescript_imports(content: str, file_path: str) -> list[dict]:
    """Parse TypeScript/JavaScript import statements.

    Returns list of dicts: [{module, name, alias}]
    """
    imports = []

    # import ... from "X" or import ... from 'X'
    from_pattern = re.compile(
        r"""import\s+(?:(?:\{[^}]*\}|[\w*]+(?:\s+as\s+\w+)?)\s*,?\s*)*from\s+["']([^"']+)["']""",
        re.MULTILINE,
    )
    for match in from_pattern.finditer(content):
        module = match.group(1)
        imports.append({"module": module, "name": None, "alias": None})

    # import "X" or import 'X' (side-effect imports)
    side_effect_pattern = re.compile(
        r"""^import\s+["']([^"']+)["']\s*;?\s*$""",
        re.MULTILINE,
    )
    for match in side_effect_pattern.finditer(content):
        module = match.group(1)
        imports.append({"module": module, "name": None, "alias": None})

    # require("X") or require('X')
    require_pattern = re.compile(
        r"""require\s*\(\s*["']([^"']+)["']\s*\)""",
    )
    for match in require_pattern.finditer(content):
        module = match.group(1)
        imports.append({"module": module, "name": None, "alias": None})

    return imports


def resolve_import_to_file(
    import_module: str,
    repo_files: dict[str, str],
    file_path: str,
) -> str | None:
    """Try to resolve an import module path to an actual file in the repo.

    Args:
        import_module: The module path from the import statement (e.g., "engine.core.db")
        repo_files: Dict mapping relative paths to their slugified IDs
        file_path: The file containing the import (for relative resolution)

    Returns:
        The relative path of the resolved file, or None if unresolvable.
    """
    # Python-style: dots to slashes
    module_as_path = import_module.replace(".", "/")

    # Try direct file match
    candidates = [
        f"{module_as_path}.py",
        f"{module_as_path}.ts",
        f"{module_as_path}.tsx",
        f"{module_as_path}.js",
        f"{module_as_path}.jsx",
        f"{module_as_path}/__init__.py",
        f"{module_as_path}/index.ts",
        f"{module_as_path}/index.tsx",
        f"{module_as_path}/index.js",
    ]

    for candidate in candidates:
        if candidate in repo_files:
            return candidate

    # TypeScript/JS relative imports: resolve relative to importing file
    if import_module.startswith("."):
        dir_of_file = os.path.dirname(file_path)
        resolved = os.path.normpath(os.path.join(dir_of_file, import_module))
        ts_candidates = [
            f"{resolved}.ts",
            f"{resolved}.tsx",
            f"{resolved}.js",
            f"{resolved}.jsx",
            f"{resolved}/index.ts",
            f"{resolved}/index.tsx",
            f"{resolved}/index.js",
        ]
        for candidate in ts_candidates:
            if candidate in repo_files:
                return candidate

    return None
