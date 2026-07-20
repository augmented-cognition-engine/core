# tests/test_intelligence_detector.py
"""Tests for language detection."""

import os
import tempfile

from core.engine.intelligence.detector import detect_languages
from core.engine.intelligence.servers import SUPPORTED_LANGUAGES, get_server_config


def test_detect_python_project():
    with tempfile.TemporaryDirectory() as d:
        for name in ["app.py", "models.py", "utils.py", "test.py"]:
            open(os.path.join(d, name), "w").close()
        open(os.path.join(d, "readme.md"), "w").close()
        langs = detect_languages(d)
        assert langs[0].name == "python"
        assert langs[0].file_count == 4


def test_detect_mixed_project():
    with tempfile.TemporaryDirectory() as d:
        for name in ["app.py", "models.py"]:
            open(os.path.join(d, name), "w").close()
        for name in ["index.ts", "App.tsx", "utils.ts"]:
            open(os.path.join(d, name), "w").close()
        langs = detect_languages(d)
        names = [lang.name for lang in langs]
        assert "python" in names
        assert "typescript" in names


def test_detect_skips_hidden_dirs():
    with tempfile.TemporaryDirectory() as d:
        hidden = os.path.join(d, ".git")
        os.makedirs(hidden)
        open(os.path.join(hidden, "config.py"), "w").close()
        open(os.path.join(d, "main.py"), "w").close()
        langs = detect_languages(d)
        assert langs[0].file_count == 1  # only main.py


def test_detect_skips_node_modules():
    with tempfile.TemporaryDirectory() as d:
        nm = os.path.join(d, "node_modules", "pkg")
        os.makedirs(nm)
        open(os.path.join(nm, "index.js"), "w").close()
        open(os.path.join(d, "app.ts"), "w").close()
        langs = detect_languages(d)
        total_files = sum(lang.file_count for lang in langs)
        assert total_files == 1


def test_detect_empty_dir():
    with tempfile.TemporaryDirectory() as d:
        langs = detect_languages(d)
        assert langs == []


def test_server_config_python():
    cfg = get_server_config("python")
    assert cfg is not None
    assert cfg["name"] == "pyright"


def test_server_config_typescript():
    cfg = get_server_config("typescript")
    assert cfg is not None
    assert "typescript" in cfg["name"].lower()


def test_supported_languages():
    assert "python" in SUPPORTED_LANGUAGES
    assert "typescript" in SUPPORTED_LANGUAGES
