from __future__ import annotations

import json
import tomllib
from pathlib import Path

from evaluations.state_engine_product_journey import (
    acceptance_hash,
    file_sha256,
    load_product_journey_config,
    product_journey_config_hash,
    validate_product_journey_result,
)

ROOT = Path(__file__).parents[1]
RESULT = ROOT / "evaluations/results/state_engine_product_journey_v1.json"


def test_frozen_product_journey_fixture_and_extension_package() -> None:
    config = load_product_journey_config()
    extension = config["extension"]
    package = tomllib.loads((ROOT / "examples/ace_ext_fjord_operations/pyproject.toml").read_text(encoding="utf-8"))

    assert config["fixture_status"] == "frozen_before_execution"
    assert len(product_journey_config_hash()) == 64
    assert file_sha256(ROOT / extension["corpus_path"]) == extension["corpus_sha256"]
    assert package["project"]["name"] == extension["distribution"]
    assert package["project"]["version"] == extension["extension_version"]
    assert package["project"]["entry-points"]["ace.extensions"][extension["entry_point"]] == extension["module_spec"]


def test_frozen_corpus_separates_source_and_ace_times() -> None:
    config = load_product_journey_config()
    corpus = json.loads((ROOT / config["extension"]["corpus_path"]).read_text(encoding="utf-8"))
    timed = corpus["records"][0]["record"]

    assert corpus["license"].startswith("CC0-1.0")
    assert "fictional" in corpus["license"]
    assert (
        len(
            {
                timed["temporal"]["occurred_at"],
                timed["published_at"],
                timed["ingested_at"],
                timed["extracted_at"],
            }
        )
        == 4
    )
    assert "Ignore prior instructions" in timed["content"]


def test_product_journey_keeps_the_thin_public_boundary() -> None:
    config = load_product_journey_config()
    tools = config["acceptance"]["thin_mcp_tools"]

    assert len(tools) == len(set(tools)) == 11
    assert all("state" not in name and "engine" not in name for name in tools)


def test_committed_product_journey_receipt_is_self_validating() -> None:
    result = json.loads(RESULT.read_text(encoding="utf-8"))

    validate_product_journey_result(result)
    assert result["acceptance_hash"] == acceptance_hash(result)
    assert result["fixture"]["config_sha256"] == product_journey_config_hash()
