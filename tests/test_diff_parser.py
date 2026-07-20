# tests/test_diff_parser.py
"""Tests for engine.github.diff_parser — parse unified diffs into structured data."""

import pytest

from core.engine.github.diff_parser import parse_diff
from core.engine.github.models import FileDiff

# ─── Fixtures ────────────────────────────────────────────────────────────────

SIMPLE_MODIFICATION = """\
diff --git a/engine/core/config.py b/engine/core/config.py
index 1a2b3c4..5d6e7f8 100644
--- a/engine/core/config.py
+++ b/engine/core/config.py
@@ -10,7 +10,9 @@ class Settings(BaseSettings):
     debug: bool = False
     log_level: str = "INFO"
-    old_setting: str = "deprecated"
+    new_setting: str = "active"
+    extra_setting: int = 42
     database_url: str = ""
"""

NEW_FILE = """\
diff --git a/engine/github/__init__.py b/engine/github/__init__.py
new file mode 100644
index 0000000..e69de29
--- /dev/null
+++ b/engine/github/__init__.py
@@ -0,0 +1,3 @@
+# engine/github
+"""

DELETED_FILE = """\
diff --git a/engine/old_module.py b/engine/old_module.py
deleted file mode 100644
index abcdef1..0000000
--- a/engine/old_module.py
+++ /dev/null
@@ -1,5 +0,0 @@
-# Old module — no longer needed
-
-def legacy_fn():
-    pass
-
"""

RENAMED_FILE = """\
diff --git a/engine/skills/runner.py b/engine/playbooks/runner.py
similarity index 90%
rename from engine/skills/runner.py
rename to engine/playbooks/runner.py
index 1111111..2222222 100644
--- a/engine/skills/runner.py
+++ b/engine/playbooks/runner.py
@@ -1,4 +1,4 @@
-# engine/skills/runner.py
+# engine/playbooks/runner.py

 def run():
     pass
"""

MULTI_FILE = """\
diff --git a/engine/core/db.py b/engine/core/db.py
index aaa..bbb 100644
--- a/engine/core/db.py
+++ b/engine/core/db.py
@@ -5,3 +5,4 @@ from surrealdb import Surreal

 POOL_SIZE = 5
+TIMEOUT = 30

diff --git a/engine/core/config.py b/engine/core/config.py
index ccc..ddd 100644
--- a/engine/core/config.py
+++ b/engine/core/config.py
@@ -1,3 +1,4 @@
 from pydantic_settings import BaseSettings
+from typing import Optional

 class Settings(BaseSettings):
"""

EMPTY_DIFF = ""

HUNK_CONTENT_DIFF = """\
diff --git a/engine/capture/pipeline.py b/engine/capture/pipeline.py
index abc..def 100644
--- a/engine/capture/pipeline.py
+++ b/engine/capture/pipeline.py
@@ -20,8 +20,10 @@ class CapturePipeline:
     async def run(self, data: dict) -> dict:
         result = await self._process(data)
-        log.debug("done")
+        log.info("capture complete")
+        log.debug("result: %s", result)
         return result

     async def _process(self, data: dict) -> dict:
"""

MULTI_HUNK_DIFF = """\
diff --git a/engine/orchestrator/executor.py b/engine/orchestrator/executor.py
index 111..222 100644
--- a/engine/orchestrator/executor.py
+++ b/engine/orchestrator/executor.py
@@ -5,3 +5,4 @@ import asyncio

 WORKERS = 4
+MAX_RETRIES = 3

@@ -50,4 +51,5 @@ class Executor:
     async def execute(self, task):
         result = await self._run(task)
+        await self._cleanup(task)
         return result
"""


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestSimpleModification:
    def test_returns_one_file(self):
        files = parse_diff(SIMPLE_MODIFICATION)
        assert len(files) == 1

    def test_path(self):
        files = parse_diff(SIMPLE_MODIFICATION)
        assert files[0].path == "engine/core/config.py"

    def test_status_is_modified(self):
        files = parse_diff(SIMPLE_MODIFICATION)
        assert files[0].status == "modified"

    def test_addition_count(self):
        files = parse_diff(SIMPLE_MODIFICATION)
        assert files[0].additions == 2

    def test_deletion_count(self):
        files = parse_diff(SIMPLE_MODIFICATION)
        assert files[0].deletions == 1

    def test_one_hunk(self):
        files = parse_diff(SIMPLE_MODIFICATION)
        assert len(files[0].hunks) == 1

    def test_hunk_positions(self):
        hunk = parse_diff(SIMPLE_MODIFICATION)[0].hunks[0]
        assert hunk.old_start == 10
        assert hunk.old_count == 7
        assert hunk.new_start == 10
        assert hunk.new_count == 9


class TestNewFile:
    def test_status_is_added(self):
        files = parse_diff(NEW_FILE)
        assert files[0].status == "added"

    def test_is_new_property(self):
        files = parse_diff(NEW_FILE)
        assert files[0].is_new is True

    def test_is_deleted_property_false(self):
        files = parse_diff(NEW_FILE)
        assert files[0].is_deleted is False

    def test_path(self):
        files = parse_diff(NEW_FILE)
        assert files[0].path == "engine/github/__init__.py"

    def test_additions_counted(self):
        files = parse_diff(NEW_FILE)
        assert files[0].additions == 2


class TestDeletedFile:
    def test_status_is_deleted(self):
        files = parse_diff(DELETED_FILE)
        assert files[0].status == "deleted"

    def test_is_deleted_property(self):
        files = parse_diff(DELETED_FILE)
        assert files[0].is_deleted is True

    def test_deletions_counted(self):
        files = parse_diff(DELETED_FILE)
        assert files[0].deletions == 5

    def test_zero_additions(self):
        files = parse_diff(DELETED_FILE)
        assert files[0].additions == 0


class TestRenamedFile:
    def test_status_is_renamed(self):
        files = parse_diff(RENAMED_FILE)
        assert files[0].status == "renamed"

    def test_new_path(self):
        files = parse_diff(RENAMED_FILE)
        assert files[0].path == "engine/playbooks/runner.py"

    def test_old_path(self):
        files = parse_diff(RENAMED_FILE)
        assert files[0].old_path == "engine/skills/runner.py"

    def test_has_hunk(self):
        files = parse_diff(RENAMED_FILE)
        assert len(files[0].hunks) == 1


class TestMultiFileDiff:
    def test_returns_two_files(self):
        files = parse_diff(MULTI_FILE)
        assert len(files) == 2

    def test_paths(self):
        files = parse_diff(MULTI_FILE)
        paths = [f.path for f in files]
        assert "engine/core/db.py" in paths
        assert "engine/core/config.py" in paths

    def test_each_file_has_one_hunk(self):
        files = parse_diff(MULTI_FILE)
        for f in files:
            assert len(f.hunks) == 1

    def test_addition_counts(self):
        files = parse_diff(MULTI_FILE)
        by_path = {f.path: f for f in files}
        assert by_path["engine/core/db.py"].additions == 1
        assert by_path["engine/core/config.py"].additions == 1


class TestEmptyDiff:
    def test_empty_string_returns_empty_list(self):
        assert parse_diff("") == []

    def test_whitespace_only_returns_empty_list(self):
        assert parse_diff("   \n\n  ") == []

    def test_none_like_diff(self):
        # Ensure robustness — caller passes empty string not None
        result = parse_diff("")
        assert isinstance(result, list)
        assert len(result) == 0


class TestHunkAddedRemovedLines:
    def test_added_lines_content(self):
        files = parse_diff(HUNK_CONTENT_DIFF)
        hunk = files[0].hunks[0]
        added = hunk.added_lines
        assert len(added) == 2
        # Lines preserve indentation but have the +/- prefix stripped
        assert any('log.info("capture complete")' in line for line in added)
        assert any('log.debug("result: %s", result)' in line for line in added)

    def test_removed_lines_content(self):
        files = parse_diff(HUNK_CONTENT_DIFF)
        hunk = files[0].hunks[0]
        removed = hunk.removed_lines
        assert len(removed) == 1
        assert any('log.debug("done")' in line for line in removed)

    def test_added_lines_strip_prefix(self):
        files = parse_diff(HUNK_CONTENT_DIFF)
        for line in files[0].hunks[0].added_lines:
            assert not line.startswith("+")

    def test_removed_lines_strip_prefix(self):
        files = parse_diff(HUNK_CONTENT_DIFF)
        for line in files[0].hunks[0].removed_lines:
            assert not line.startswith("-")


class TestMultiHunk:
    def test_two_hunks_parsed(self):
        files = parse_diff(MULTI_HUNK_DIFF)
        assert len(files[0].hunks) == 2

    def test_first_hunk_position(self):
        hunk = parse_diff(MULTI_HUNK_DIFF)[0].hunks[0]
        assert hunk.old_start == 5
        assert hunk.new_start == 5

    def test_second_hunk_position(self):
        hunk = parse_diff(MULTI_HUNK_DIFF)[0].hunks[1]
        assert hunk.old_start == 50
        assert hunk.new_start == 51

    def test_total_additions(self):
        files = parse_diff(MULTI_HUNK_DIFF)
        assert files[0].additions == 2


class TestFileLanguageDetection:
    @pytest.mark.parametrize(
        "path,expected_lang",
        [
            ("src/main.py", "python"),
            ("app/index.js", "javascript"),
            ("app/index.ts", "typescript"),
            ("app/Component.tsx", "typescript"),
            ("app/Component.jsx", "javascript"),
            ("src/main.rs", "rust"),
            ("cmd/main.go", "go"),
            ("App.java", "java"),
            ("app.rb", "ruby"),
            ("main.cpp", "cpp"),
            ("main.c", "c"),
            ("App.cs", "csharp"),
            ("index.php", "php"),
            ("App.swift", "swift"),
            ("App.kt", "kotlin"),
            ("README.md", "unknown"),
            ("data.json", "unknown"),
            ("Makefile", "unknown"),
        ],
    )
    def test_language_detection(self, path, expected_lang):
        fd = FileDiff(path=path)
        assert fd.language == expected_lang
