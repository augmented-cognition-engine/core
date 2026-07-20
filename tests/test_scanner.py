# tests/test_scanner.py
"""Tests for the git-first code scanner."""

import os
import textwrap
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.scanner.ast_parser import ParseResult, parse_file
from core.engine.scanner.import_parser import (
    parse_python_imports,
    parse_typescript_imports,
    resolve_import_to_file,
)
from core.engine.scanner.scanner import _slug, _walk_repo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_git_repo(tmp_path, files: dict[str, str] | None = None, commits: list[dict] | None = None):
    """Create a small git repo in tmp_path with given files and commits.

    Args:
        tmp_path: Path object for temp directory
        files: Dict of {relative_path: content}
        commits: List of dicts [{files: {path: content}, message: str, author: str}]
    """
    from git import Actor, Repo

    repo = Repo.init(tmp_path)

    if files is None:
        files = {}

    if commits is None:
        # Default: create all files in a single commit
        commits = [{"files": files, "message": "Initial commit", "author": "Test Author"}]

    for commit_spec in commits:
        for rel_path, content in commit_spec.get("files", {}).items():
            full = tmp_path / rel_path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content)
            repo.index.add([rel_path])

        author = Actor(commit_spec.get("author", "Test Author"), "test@example.com")
        repo.index.commit(
            commit_spec.get("message", "test commit"),
            author=author,
            committer=author,
        )

    return repo


# ---------------------------------------------------------------------------
# Unit tests: _slug
# ---------------------------------------------------------------------------


class TestSlugGeneration:
    def test_basic_path(self):
        assert _slug("engine/core/db.py") == "engine_core_db_py"

    def test_nested_path(self):
        assert _slug("src/components/Header.tsx") == "src_components_header_tsx"

    def test_root_file(self):
        assert _slug("README.md") == "readme_md"

    def test_special_characters(self):
        assert _slug("my-file.test.py") == "my_file_test_py"

    def test_leading_dot(self):
        assert _slug(".gitignore") == "gitignore"

    def test_empty_string(self):
        assert _slug("") == ""


# ---------------------------------------------------------------------------
# Unit tests: AST parser (tree-sitter)
# ---------------------------------------------------------------------------


class TestParsePythonFunctions:
    def test_standalone_function(self):
        code = b"def greet(name: str) -> str:\n    return f'Hello, {name}'\n"
        result = parse_file(code, "python")
        assert len(result.functions) == 1
        func = result.functions[0]
        assert func.name == "greet"
        assert func.kind == "function"
        assert "(name: str)" in func.parameters
        assert "str" in func.return_type
        assert func.line_start == 1
        assert func.line_end == 2

    def test_async_function(self):
        code = b"async def fetch(url: str) -> None:\n    pass\n"
        result = parse_file(code, "python")
        assert len(result.functions) == 1
        assert result.functions[0].name == "fetch"

    def test_multiple_functions(self):
        code = b"def foo(): pass\ndef bar(): pass\ndef baz(): pass\n"
        result = parse_file(code, "python")
        assert len(result.functions) == 3
        names = [f.name for f in result.functions]
        assert "foo" in names
        assert "bar" in names
        assert "baz" in names

    def test_decorated_function(self):
        code = b"@app.route('/api')\ndef handler():\n    pass\n"
        result = parse_file(code, "python")
        assert len(result.functions) == 1
        assert result.functions[0].name == "handler"


class TestParsePythonClasses:
    def test_class_with_methods(self):
        code = textwrap.dedent("""\
            class UserService:
                def __init__(self, db):
                    self.db = db

                def get_user(self, user_id: int) -> dict:
                    pass
        """).encode()
        result = parse_file(code, "python")
        assert len(result.classes) == 1
        assert result.classes[0].name == "UserService"
        assert result.classes[0].line_start == 1

        # Methods should appear as functions with class prefix
        method_names = [f.name for f in result.functions]
        assert "UserService.__init__" in method_names
        assert "UserService.get_user" in method_names
        for f in result.functions:
            assert f.kind == "method"
            assert f.class_name == "UserService"

    def test_empty_class(self):
        code = b"class Empty:\n    pass\n"
        result = parse_file(code, "python")
        assert len(result.classes) == 1
        assert result.classes[0].name == "Empty"
        assert len(result.classes[0].methods) == 0

    def test_decorated_class(self):
        code = b"@dataclass\nclass Config:\n    host: str = 'localhost'\n"
        result = parse_file(code, "python")
        assert len(result.classes) == 1
        assert result.classes[0].name == "Config"


class TestParsePythonImportsAST:
    def test_from_import(self):
        code = b"from engine.core.db import pool, parse_rows\n"
        result = parse_file(code, "python")
        assert len(result.imports) == 2
        modules = [i.module for i in result.imports]
        assert all(m == "engine.core.db" for m in modules)
        names = [i.name for i in result.imports]
        assert "pool" in names
        assert "parse_rows" in names

    def test_plain_import(self):
        code = b"import os\n"
        result = parse_file(code, "python")
        assert len(result.imports) == 1
        assert result.imports[0].module == "os"

    def test_aliased_import(self):
        code = b"import numpy as np\n"
        result = parse_file(code, "python")
        assert len(result.imports) == 1
        assert result.imports[0].module == "numpy"
        assert result.imports[0].alias == "np"

    def test_from_import_with_alias(self):
        code = b"from os.path import join as pjoin\n"
        result = parse_file(code, "python")
        assert any(i.name == "join" and i.alias == "pjoin" for i in result.imports)

    def test_multiple_imports(self):
        code = b"import os\nimport sys\nfrom pathlib import Path\nfrom engine.core.db import pool\n"
        result = parse_file(code, "python")
        assert len(result.imports) == 4


class TestParseTypescriptImportsAST:
    def test_named_import(self):
        code = b'import { useState } from "react";\n'
        result = parse_file(code, "typescript")
        assert len(result.imports) >= 1
        assert any(i.module == "react" for i in result.imports)

    def test_default_import(self):
        code = b"import React from 'react';\n"
        result = parse_file(code, "typescript")
        assert any(i.module == "react" for i in result.imports)

    def test_side_effect_import(self):
        code = b"import './styles.css';\n"
        result = parse_file(code, "typescript")
        assert any(i.module == "./styles.css" for i in result.imports)

    def test_relative_import(self):
        code = b'import { helper } from "../utils/helper";\n'
        result = parse_file(code, "typescript")
        assert any(i.module == "../utils/helper" for i in result.imports)

    def test_typescript_functions(self):
        code = b"export function greet(name: string): string { return name; }\n"
        result = parse_file(code, "typescript")
        assert len(result.functions) >= 1
        assert any(f.name == "greet" for f in result.functions)

    def test_typescript_class(self):
        code = textwrap.dedent("""\
            class UserService {
                getName(): string {
                    return 'test';
                }
            }
        """).encode()
        result = parse_file(code, "typescript")
        assert len(result.classes) == 1
        assert result.classes[0].name == "UserService"
        assert any(f.name == "UserService.getName" for f in result.functions)

    def test_typescript_arrow_function(self):
        code = b"const helper = (x: number): number => x * 2;\n"
        result = parse_file(code, "typescript")
        assert any(f.name == "helper" for f in result.functions)

    def test_typescript_exports(self):
        code = b"export function greet(): void {}\nexport const x = 1;\n"
        result = parse_file(code, "typescript")
        assert len(result.exports) >= 1
        assert any(e.name == "greet" for e in result.exports)


class TestParseUnsupportedLanguage:
    def test_returns_empty_result(self):
        result = parse_file(b"SELECT * FROM table;", "sql")
        assert isinstance(result, ParseResult)
        assert len(result.functions) == 0
        assert len(result.classes) == 0
        assert len(result.imports) == 0

    def test_empty_content(self):
        result = parse_file(b"", "python")
        assert isinstance(result, ParseResult)
        assert len(result.functions) == 0

    def test_unknown_language(self):
        result = parse_file(b"hello world", "brainfuck")
        assert isinstance(result, ParseResult)
        assert len(result.functions) == 0


# ---------------------------------------------------------------------------
# Unit tests: import parser — Python (regex fallback)
# ---------------------------------------------------------------------------


class TestParsePythonImports:
    def test_from_import(self):
        code = "from engine.core.db import pool, parse_rows"
        imports = parse_python_imports(code, "test.py")
        modules = [i["module"] for i in imports]
        assert "engine.core.db" in modules
        names = [i["name"] for i in imports]
        assert "pool" in names
        assert "parse_rows" in names

    def test_plain_import(self):
        code = "import os"
        imports = parse_python_imports(code, "test.py")
        assert len(imports) == 1
        assert imports[0]["module"] == "os"

    def test_import_with_alias(self):
        code = "import numpy as np"
        imports = parse_python_imports(code, "test.py")
        assert len(imports) == 1
        assert imports[0]["module"] == "numpy"
        assert imports[0]["alias"] == "np"

    def test_from_import_with_alias(self):
        code = "from os.path import join as pjoin"
        imports = parse_python_imports(code, "test.py")
        assert any(i["name"] == "join" and i["alias"] == "pjoin" for i in imports)

    def test_multiple_imports(self):
        code = textwrap.dedent("""\
            import os
            import sys
            from pathlib import Path
            from core.engine.core.db import pool
        """)
        imports = parse_python_imports(code, "test.py")
        assert len(imports) == 4

    def test_ignores_comments(self):
        code = "# import os\nfrom sys import argv"
        imports = parse_python_imports(code, "test.py")
        modules = [i["module"] for i in imports]
        assert "sys" in modules
        # The comment line should not produce an import with module "os"
        # (it starts with "# import" which won't match "^import")

    def test_empty_file(self):
        assert parse_python_imports("", "test.py") == []


# ---------------------------------------------------------------------------
# Unit tests: import parser — TypeScript
# ---------------------------------------------------------------------------


class TestParseTypescriptImports:
    def test_named_import(self):
        code = 'import { useState } from "react";'
        imports = parse_typescript_imports(code, "test.ts")
        assert len(imports) == 1
        assert imports[0]["module"] == "react"

    def test_default_import(self):
        code = "import React from 'react';"
        imports = parse_typescript_imports(code, "test.ts")
        assert len(imports) == 1
        assert imports[0]["module"] == "react"

    def test_side_effect_import(self):
        code = 'import "./styles.css";'
        imports = parse_typescript_imports(code, "test.ts")
        assert any(i["module"] == "./styles.css" for i in imports)

    def test_relative_import(self):
        code = 'import { helper } from "../utils/helper";'
        imports = parse_typescript_imports(code, "test.ts")
        assert any(i["module"] == "../utils/helper" for i in imports)

    def test_require(self):
        code = 'const fs = require("fs");'
        imports = parse_typescript_imports(code, "test.ts")
        assert any(i["module"] == "fs" for i in imports)

    def test_empty_file(self):
        assert parse_typescript_imports("", "test.ts") == []


# ---------------------------------------------------------------------------
# Unit tests: import resolution
# ---------------------------------------------------------------------------


class TestResolveImport:
    def test_python_module_to_file(self):
        repo_files = {
            "core/engine/core/db.py": "engine_core_db_py",
            "core/engine/core/__init__.py": "engine_core___init___py",
        }
        result = resolve_import_to_file("core.engine.core.db", repo_files, "core/engine/api/main.py")
        assert result == "core/engine/core/db.py"

    def test_python_package_init(self):
        repo_files = {
            "core/engine/core/__init__.py": "engine_core___init___py",
        }
        result = resolve_import_to_file("core.engine.core", repo_files, "core/engine/api/main.py")
        assert result == "core/engine/core/__init__.py"

    def test_unresolvable_import(self):
        repo_files = {"core/engine/core/db.py": "engine_core_db_py"}
        result = resolve_import_to_file("numpy", repo_files, "test.py")
        assert result is None

    def test_ts_relative_import(self):
        repo_files = {
            "src/utils/helper.ts": "src_utils_helper_ts",
        }
        result = resolve_import_to_file("./utils/helper", repo_files, "src/app.ts")
        assert result == "src/utils/helper.ts"


# ---------------------------------------------------------------------------
# Unit tests: file walking
# ---------------------------------------------------------------------------


class TestWalkRepo:
    def test_finds_files(self, tmp_path):
        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "lib").mkdir()
        (tmp_path / "lib" / "util.py").write_text("x = 1")

        files = _walk_repo(str(tmp_path))
        paths = [f["path"] for f in files]
        assert "main.py" in paths
        assert os.path.join("lib", "util.py") in paths

    def test_skips_git_dir(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("[core]")
        (tmp_path / "main.py").write_text("print('hello')")

        files = _walk_repo(str(tmp_path))
        paths = [f["path"] for f in files]
        assert "main.py" in paths
        assert not any(".git" in p for p in paths)

    def test_skips_node_modules(self, tmp_path):
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "react.js").write_text("export default {}")
        (tmp_path / "index.js").write_text("import React from 'react'")

        files = _walk_repo(str(tmp_path))
        paths = [f["path"] for f in files]
        assert "index.js" in paths
        assert not any("node_modules" in p for p in paths)

    def test_skips_binary_files(self, tmp_path):
        (tmp_path / "image.png").write_bytes(b"\x89PNG")
        (tmp_path / "main.py").write_text("print('hello')")

        files = _walk_repo(str(tmp_path))
        paths = [f["path"] for f in files]
        assert "main.py" in paths
        assert "image.png" not in paths

    def test_detects_language(self, tmp_path):
        (tmp_path / "app.py").write_text("pass")
        (tmp_path / "index.ts").write_text("export {}")

        files = _walk_repo(str(tmp_path))
        langs = {f["path"]: f["language"] for f in files}
        assert langs["app.py"] == "python"
        assert langs["index.ts"] == "typescript"

    def test_counts_lines(self, tmp_path):
        (tmp_path / "three_lines.py").write_text("a\nb\nc\n")

        files = _walk_repo(str(tmp_path))
        f = next(f for f in files if f["name"] == "three_lines.py")
        assert f["line_count"] == 3


# ---------------------------------------------------------------------------
# Integration tests: full scan (mocked DB)
# ---------------------------------------------------------------------------


class TestScanRepo:
    @pytest.fixture
    def mock_db(self):
        """Mock database connection that records all queries."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[])
        return db

    @pytest.fixture
    def mock_pool(self, mock_db):
        """Mock pool that yields the mock db."""
        from contextlib import asynccontextmanager

        mock_p = MagicMock()

        @asynccontextmanager
        async def _conn():
            yield mock_db

        mock_p.connection = _conn
        return mock_p

    @pytest.mark.asyncio
    async def test_scan_creates_file_nodes(self, tmp_path, mock_pool, mock_db):
        """Scan a 3-file repo, verify file node creation queries."""
        _make_git_repo(
            tmp_path,
            {
                "main.py": "print('hello')",
                "lib/util.py": "def helper(): pass",
                "README.md": "# Readme",
            },
        )

        with patch("core.engine.scanner.scanner.pool", mock_pool):
            from core.engine.scanner.scanner import scan_repo

            result = await scan_repo(str(tmp_path), graph_id="test_files")

        assert result["files_created"] == 3
        assert result["graph_id"] == "test_files"

        # Verify UPSERT queries were issued for graph_file
        calls = [str(c) for c in mock_db.query.call_args_list]
        create_file_calls = [c for c in calls if "graph_file" in c and "UPSERT" in c]
        assert len(create_file_calls) >= 3

    @pytest.mark.asyncio
    async def test_scan_creates_import_edges(self, tmp_path, mock_pool, mock_db):
        """Files with imports get RELATE edges."""
        _make_git_repo(
            tmp_path,
            {
                "main.py": "from lib.util import helper\nhelper()",
                "lib/__init__.py": "",
                "lib/util.py": "def helper(): pass",
            },
        )

        with patch("core.engine.scanner.scanner.pool", mock_pool):
            from core.engine.scanner.scanner import scan_repo

            result = await scan_repo(str(tmp_path), graph_id="test_imports")

        assert result["imports_created"] >= 1

        # Verify RELATE ... -> imports -> ... queries
        calls = [str(c) for c in mock_db.query.call_args_list]
        import_calls = [c for c in calls if "imports" in c and "RELATE" in c]
        assert len(import_calls) >= 1

    @pytest.mark.asyncio
    async def test_scan_creates_decision_nodes(self, tmp_path, mock_pool, mock_db):
        """Commits become decision nodes."""
        _make_git_repo(
            tmp_path,
            commits=[
                {
                    "files": {"main.py": "v1"},
                    "message": "feat: initial version",
                    "author": "Alice",
                },
                {
                    "files": {"main.py": "v2"},
                    "message": "fix: bug in main",
                    "author": "Bob",
                },
            ],
        )

        with patch("core.engine.scanner.scanner.pool", mock_pool):
            from core.engine.scanner.scanner import scan_repo

            result = await scan_repo(str(tmp_path), graph_id="test_decisions")

        assert result["decisions_created"] == 2

    @pytest.mark.asyncio
    async def test_scan_creates_user_nodes(self, tmp_path, mock_pool, mock_db):
        """Committers become user nodes."""
        _make_git_repo(
            tmp_path,
            commits=[
                {
                    "files": {"main.py": "v1"},
                    "message": "first",
                    "author": "Alice",
                },
                {
                    "files": {"main.py": "v2"},
                    "message": "second",
                    "author": "Bob",
                },
                {
                    "files": {"main.py": "v3"},
                    "message": "third",
                    "author": "Alice",
                },
            ],
        )

        with patch("core.engine.scanner.scanner.pool", mock_pool):
            from core.engine.scanner.scanner import scan_repo

            result = await scan_repo(str(tmp_path), graph_id="test_users")

        assert result["users_created"] == 2  # Alice and Bob

    @pytest.mark.asyncio
    async def test_scan_handles_empty_repo(self, tmp_path, mock_pool, mock_db):
        """Scan should handle a repo with only the initial commit gracefully."""
        _make_git_repo(tmp_path, {"README.md": "# Empty"})

        with patch("core.engine.scanner.scanner.pool", mock_pool):
            from core.engine.scanner.scanner import scan_repo

            result = await scan_repo(str(tmp_path), graph_id="test_empty")

        assert result["files_created"] >= 1
        assert result["decisions_created"] >= 1
