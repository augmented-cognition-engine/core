# engine/scanner/ast_parser.py
"""AST-based file parser using tree-sitter.

Extracts functions, classes, imports, and exports from source files
using proper AST parsing instead of regex.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Languages supported by tree-sitter-language-pack
LANG_MAP: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".rs": "rust",
    ".go": "go",
    ".rb": "ruby",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".cs": "c_sharp",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".php": "php",
    ".swift": "swift",
    ".lua": "lua",
    ".zig": "zig",
    ".ex": "elixir",
    ".exs": "elixir",
    ".elm": "elm",
    ".ml": "ocaml",
    ".hs": "haskell",
    ".r": "r",
    ".R": "r",
    ".sql": "sql",
    ".sh": "bash",
    ".bash": "bash",
}


@dataclass
class FunctionInfo:
    name: str
    line_start: int
    line_end: int
    parameters: str = ""
    return_type: str = ""
    kind: str = "function"  # function | method | class
    class_name: str | None = None


@dataclass
class ClassInfo:
    name: str
    line_start: int
    line_end: int
    methods: list[FunctionInfo] = field(default_factory=list)


@dataclass
class ImportInfo:
    module: str
    name: str | None = None
    alias: str | None = None
    line: int = 0


@dataclass
class ExportInfo:
    name: str
    kind: str = ""  # function, class, variable, default
    line: int = 0


@dataclass
class ParseResult:
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)
    exports: list[ExportInfo] = field(default_factory=list)


def _safe_text(node) -> str:
    """Safely get decoded text from a tree-sitter node."""
    if node is None:
        return ""
    try:
        return node.text.decode()
    except Exception:
        return ""


def _safe_field(node, field_name: str) -> str:
    """Safely get a field's text from a node."""
    child = node.child_by_field_name(field_name)
    return _safe_text(child)


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------


def _parse_python_function(node, class_name: str | None = None) -> FunctionInfo:
    """Extract function info from a Python function_definition node."""
    name = _safe_field(node, "name")
    params = _safe_field(node, "parameters")
    return_type = _safe_field(node, "return_type")

    kind = "method" if class_name else "function"
    full_name = f"{class_name}.{name}" if class_name else name

    return FunctionInfo(
        name=full_name,
        line_start=node.start_point.row + 1,
        line_end=node.end_point.row + 1,
        parameters=params,
        return_type=return_type,
        kind=kind,
        class_name=class_name,
    )


def _parse_python_class(node) -> tuple[ClassInfo, list[FunctionInfo]]:
    """Extract class info and its methods from a Python class_definition node."""
    name = _safe_field(node, "name")
    cls = ClassInfo(
        name=name,
        line_start=node.start_point.row + 1,
        line_end=node.end_point.row + 1,
    )

    methods: list[FunctionInfo] = []
    # Methods are inside body -> block
    body = node.child_by_field_name("body")
    if body:
        for child in body.children:
            if child.type == "function_definition":
                method = _parse_python_function(child, class_name=name)
                methods.append(method)
                cls.methods.append(method)
            elif child.type == "decorated_definition":
                for dchild in child.children:
                    if dchild.type == "function_definition":
                        method = _parse_python_function(dchild, class_name=name)
                        methods.append(method)
                        cls.methods.append(method)

    return cls, methods


def _parse_python_import_from(node) -> list[ImportInfo]:
    """Extract imports from a Python import_from_statement node."""
    module = _safe_field(node, "module_name")
    if not module:
        # Fallback: first dotted_name child after 'from'
        for child in node.named_children:
            if child.type == "dotted_name":
                module = _safe_text(child)
                break
        if not module:
            return []

    imports: list[ImportInfo] = []
    line = node.start_point.row + 1

    # Named children after the module are the imported names
    found_module = False
    for child in node.children:
        if child.type == "import":
            found_module = True
            continue
        if not found_module:
            continue

        if child.type == "dotted_name":
            # Simple import name: from X import Y
            imports.append(
                ImportInfo(
                    module=module,
                    name=_safe_text(child),
                    line=line,
                )
            )
        elif child.type == "aliased_import":
            # from X import Y as Z
            orig_name = None
            alias = None
            for ac in child.children:
                if ac.type == "dotted_name":
                    orig_name = _safe_text(ac)
                elif ac.type == "identifier" and orig_name is not None:
                    alias = _safe_text(ac)
            if orig_name:
                imports.append(
                    ImportInfo(
                        module=module,
                        name=orig_name,
                        alias=alias,
                        line=line,
                    )
                )

    return imports


def _parse_python_import(node) -> list[ImportInfo]:
    """Extract imports from a Python import_statement node."""
    imports: list[ImportInfo] = []
    line = node.start_point.row + 1

    for child in node.named_children:
        if child.type == "dotted_name":
            imports.append(
                ImportInfo(
                    module=_safe_text(child),
                    line=line,
                )
            )
        elif child.type == "aliased_import":
            module = None
            alias = None
            for ac in child.children:
                if ac.type == "dotted_name":
                    module = _safe_text(ac)
                elif ac.type == "identifier" and module is not None:
                    alias = _safe_text(ac)
            if module:
                imports.append(
                    ImportInfo(
                        module=module,
                        alias=alias,
                        line=line,
                    )
                )

    return imports


def _parse_python(root) -> ParseResult:
    """Parse a Python AST root node."""
    result = ParseResult()

    for child in root.children:
        if child.type == "function_definition":
            result.functions.append(_parse_python_function(child))
        elif child.type == "decorated_definition":
            for dchild in child.children:
                if dchild.type == "function_definition":
                    result.functions.append(_parse_python_function(dchild))
                elif dchild.type == "class_definition":
                    cls, methods = _parse_python_class(dchild)
                    result.classes.append(cls)
                    result.functions.extend(methods)
        elif child.type == "class_definition":
            cls, methods = _parse_python_class(child)
            result.classes.append(cls)
            result.functions.extend(methods)
        elif child.type == "import_from_statement":
            result.imports.extend(_parse_python_import_from(child))
        elif child.type == "import_statement":
            result.imports.extend(_parse_python_import(child))

    return result


# ---------------------------------------------------------------------------
# TypeScript / JavaScript / TSX
# ---------------------------------------------------------------------------


def _parse_ts_function(node) -> FunctionInfo:
    """Extract function info from a TS function_declaration node."""
    name = _safe_field(node, "name")
    params = _safe_field(node, "parameters")
    return_type = _safe_field(node, "return_type")

    return FunctionInfo(
        name=name,
        line_start=node.start_point.row + 1,
        line_end=node.end_point.row + 1,
        parameters=params,
        return_type=return_type,
        kind="function",
    )


def _parse_ts_method(node, class_name: str) -> FunctionInfo:
    """Extract method info from a TS method_definition node."""
    name = _safe_field(node, "name")
    params = _safe_field(node, "parameters")
    return_type = _safe_field(node, "return_type")
    full_name = f"{class_name}.{name}"

    return FunctionInfo(
        name=full_name,
        line_start=node.start_point.row + 1,
        line_end=node.end_point.row + 1,
        parameters=params,
        return_type=return_type,
        kind="method",
        class_name=class_name,
    )


def _parse_ts_class(node) -> tuple[ClassInfo, list[FunctionInfo]]:
    """Extract class info and methods from a TS class_declaration node."""
    name = _safe_field(node, "name")
    cls = ClassInfo(
        name=name,
        line_start=node.start_point.row + 1,
        line_end=node.end_point.row + 1,
    )

    methods: list[FunctionInfo] = []
    body = node.child_by_field_name("body")
    if body:
        for child in body.children:
            if child.type == "method_definition":
                method = _parse_ts_method(child, class_name=name)
                methods.append(method)
                cls.methods.append(method)

    return cls, methods


def _parse_ts_arrow_function(node) -> FunctionInfo | None:
    """Try to extract a named arrow function from a lexical_declaration or variable_declarator."""
    # lexical_declaration -> variable_declarator -> name + value(arrow_function)
    for child in node.children:
        if child.type == "variable_declarator":
            name_node = child.child_by_field_name("name")
            value_node = child.child_by_field_name("value")
            if name_node and value_node and value_node.type == "arrow_function":
                params = _safe_field(value_node, "parameters")
                return_type = _safe_field(value_node, "return_type")
                return FunctionInfo(
                    name=_safe_text(name_node),
                    line_start=node.start_point.row + 1,
                    line_end=node.end_point.row + 1,
                    parameters=params,
                    return_type=return_type,
                    kind="function",
                )
    return None


def _parse_ts_import(node) -> list[ImportInfo]:
    """Extract imports from a TS import_statement node."""
    source_node = node.child_by_field_name("source")
    if not source_node:
        # Fallback: find the string child
        for child in node.children:
            if child.type == "string":
                source_node = child
                break

    if not source_node:
        return []

    module = _safe_text(source_node).strip("'\"")
    line = node.start_point.row + 1

    # Extract named imports from import_clause
    names: list[str] = []
    for child in node.children:
        if child.type == "import_clause":
            _extract_ts_import_names(child, names)

    if names:
        return [ImportInfo(module=module, name=n, line=line) for n in names]
    else:
        return [ImportInfo(module=module, line=line)]


def _extract_ts_import_names(node, names: list[str]) -> None:
    """Recursively extract imported names from an import_clause."""
    if node.type == "identifier":
        names.append(_safe_text(node))
    elif node.type == "import_specifier":
        name_node = node.child_by_field_name("name")
        if name_node:
            names.append(_safe_text(name_node))
    else:
        for child in node.children:
            _extract_ts_import_names(child, names)


def _parse_ts_export(node) -> tuple[list[ExportInfo], list[FunctionInfo], list[ClassInfo]]:
    """Parse a TS export_statement. Returns exports, functions, and classes found."""
    exports: list[ExportInfo] = []
    functions: list[FunctionInfo] = []
    classes: list[ClassInfo] = []
    line = node.start_point.row + 1

    is_default = any(c.type == "default" for c in node.children)

    for child in node.children:
        if child.type == "function_declaration":
            func = _parse_ts_function(child)
            functions.append(func)
            exports.append(
                ExportInfo(
                    name=func.name,
                    kind="default" if is_default else "function",
                    line=line,
                )
            )
        elif child.type == "class_declaration":
            cls, methods = _parse_ts_class(child)
            classes.append(cls)
            functions.extend(methods)
            exports.append(
                ExportInfo(
                    name=cls.name,
                    kind="default" if is_default else "class",
                    line=line,
                )
            )
        elif child.type == "lexical_declaration":
            arrow = _parse_ts_arrow_function(child)
            if arrow:
                functions.append(arrow)
                exports.append(
                    ExportInfo(
                        name=arrow.name,
                        kind="function",
                        line=line,
                    )
                )
            else:
                # Exported variable
                for vc in child.children:
                    if vc.type == "variable_declarator":
                        vname = _safe_field(vc, "name")
                        if vname:
                            exports.append(
                                ExportInfo(
                                    name=vname,
                                    kind="variable",
                                    line=line,
                                )
                            )
        elif child.type == "interface_declaration":
            iname = _safe_field(child, "name")
            if iname:
                exports.append(
                    ExportInfo(
                        name=iname,
                        kind="interface",
                        line=line,
                    )
                )
        elif child.type == "type_alias_declaration":
            tname = _safe_field(child, "name")
            if tname:
                exports.append(
                    ExportInfo(
                        name=tname,
                        kind="type",
                        line=line,
                    )
                )
        elif child.type == "identifier":
            # export default SomeName;
            exports.append(
                ExportInfo(
                    name=_safe_text(child),
                    kind="default",
                    line=line,
                )
            )

    return exports, functions, classes


def _parse_typescript(root) -> ParseResult:
    """Parse a TypeScript/JavaScript/TSX AST root node."""
    result = ParseResult()

    for child in root.children:
        if child.type == "function_declaration":
            result.functions.append(_parse_ts_function(child))
        elif child.type == "class_declaration":
            cls, methods = _parse_ts_class(child)
            result.classes.append(cls)
            result.functions.extend(methods)
        elif child.type == "import_statement":
            result.imports.extend(_parse_ts_import(child))
        elif child.type == "export_statement":
            exports, funcs, classes = _parse_ts_export(child)
            result.exports.extend(exports)
            result.functions.extend(funcs)
            for cls in classes:
                result.classes.append(cls)
                # Methods already added via funcs
        elif child.type == "lexical_declaration":
            # Top-level const arrow functions (not exported)
            arrow = _parse_ts_arrow_function(child)
            if arrow:
                result.functions.append(arrow)
        elif child.type == "interface_declaration":
            # Non-exported interface — track as export for completeness
            iname = _safe_field(child, "name")
            if iname:
                result.exports.append(
                    ExportInfo(
                        name=iname,
                        kind="interface",
                        line=child.start_point.row + 1,
                    )
                )

    return result


# ---------------------------------------------------------------------------
# Java
# ---------------------------------------------------------------------------


def _parse_java_method(node, class_name: str | None = None) -> FunctionInfo | None:
    """Extract method info from a Java method_declaration node."""
    name = _safe_field(node, "name")
    if not name:
        return None

    params = _safe_field(node, "parameters")
    kind = "method" if class_name else "function"
    full_name = f"{class_name}.{name}" if class_name else name

    return FunctionInfo(
        name=full_name,
        line_start=node.start_point.row + 1,
        line_end=node.end_point.row + 1,
        parameters=params,
        kind=kind,
        class_name=class_name,
    )


def _parse_java_class(node) -> tuple[ClassInfo | None, list[FunctionInfo]]:
    """Extract class info and methods from a Java class_declaration node.

    Handles class_declaration only. interface_declaration, enum_declaration,
    and record_declaration are out of scope (return None, []).
    """
    name = _safe_field(node, "name")
    if not name:
        return None, []

    cls = ClassInfo(
        name=name,
        line_start=node.start_point.row + 1,
        line_end=node.end_point.row + 1,
    )

    methods: list[FunctionInfo] = []

    # Find class_body and extract methods
    for child in node.children:
        if child.type == "class_body":
            for body_child in child.children:
                if body_child.type == "method_declaration":
                    method = _parse_java_method(body_child, class_name=name)
                    if method:
                        methods.append(method)
                        cls.methods.append(method)

    return cls, methods


def _parse_java(root) -> ParseResult:
    """Parse a Java AST root node.

    Handles top-level class_declaration only.
    interface_declaration, enum_declaration, and record_declaration are skipped.
    """
    result = ParseResult()

    for child in root.children:
        if child.type == "class_declaration":
            cls, methods = _parse_java_class(child)
            if cls:
                result.classes.append(cls)
                result.functions.extend(methods)

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_file(content: bytes, language: str) -> ParseResult:
    """Parse a file with tree-sitter.

    Args:
        content: Raw file bytes.
        language: Language name (from LANG_MAP values).

    Returns:
        ParseResult with functions, classes, imports, and exports.
        Returns empty ParseResult for unsupported languages.
    """
    if language not in LANG_MAP.values():
        return ParseResult()

    try:
        import tree_sitter_language_pack as tslp
    except ImportError:
        logger.warning("tree-sitter-language-pack not installed, returning empty parse result")
        return ParseResult()

    try:
        parser = tslp.get_parser(language)
        tree = parser.parse(content)
        root = tree.root_node
    except Exception as exc:
        logger.debug("tree-sitter parse failed for %s: %s", language, exc)
        return ParseResult()

    if language == "python":
        result = _parse_python(root)
    elif language in ("typescript", "javascript", "tsx"):
        result = _parse_typescript(root)
    elif language == "java":
        result = _parse_java(root)
    else:
        # Language supported by tree-sitter but we don't have a walker yet
        return ParseResult()

    logger.debug(
        "parse_file: language=%s functions=%d classes=%d imports=%d",
        language,
        len(result.functions),
        len(result.classes),
        len(result.imports),
    )
    return result


def get_language_for_extension(ext: str) -> str | None:
    """Get the tree-sitter language name for a file extension.

    Returns None if the extension is not supported.
    """
    return LANG_MAP.get(ext)
