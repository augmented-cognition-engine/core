from __future__ import annotations

import pytest

from scripts.verify_e1_package_matrix import _same_minor_release_line


def test_patch_predecessor_is_same_release_line() -> None:
    assert _same_minor_release_line("0.3.1", "0.3.0") is True


def test_minor_predecessor_is_not_same_release_line() -> None:
    assert _same_minor_release_line("0.3.0", "0.2.0") is False


@pytest.mark.parametrize("n1", ["0.3.1", "0.3.2"])
def test_release_line_requires_an_older_n1(n1: str) -> None:
    with pytest.raises(ValueError, match="N-1 must be older"):
        _same_minor_release_line("0.3.1", n1)


@pytest.mark.parametrize("version", ["0.3", "v0.3.1", "0.3.x"])
def test_release_line_rejects_non_package_versions(version: str) -> None:
    with pytest.raises(ValueError, match="requires X.Y.Z versions"):
        _same_minor_release_line(version, "0.3.0")
