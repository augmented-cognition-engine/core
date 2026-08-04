"""Strict current-runtime baseline for the frozen TP0 State Engine corpus.

The baseline intentionally evaluates the supported thin MCP contract rather
than private modules or an unconstrained language-model answer.  A case passes
only when the current public runtime can accept the grounded evidence input and
emit machine-checkable State Engine semantics.  Unsupported capability is a
measured failure, never a vacuous success.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import platform
import time
from datetime import datetime, timezone
from enum import StrEnum
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any, Literal, Mapping, Self

from pydantic import Field, field_validator, model_validator

from core.engine.grounded_state.contracts import FrozenContract, canonical_hash
from core.engine.grounded_state.corpus import TemporalReferenceCorpusV1

TP0_RUNTIME_BASELINE_CONFIG_VERSION = "ace.grounded-state.runtime-baseline-config/v1"
TP0_RUNTIME_BASELINE_RESULT_VERSION = "ace.grounded-state.runtime-baseline-result/v1"
TP0_CURRENT_ACE_ADAPTER_VERSION = "ace.grounded-state.current-thin-mcp-adapter/v1"

_SHA256 = frozenset("0123456789abcdef")
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = _REPO_ROOT / "evaluations/fixtures/state_engine_tp0_runtime_baseline_v1.json"
DEFAULT_CORPUS_PATH = _REPO_ROOT / "tests/fixtures/grounded_state/temporal_reference_candidate_v1.json"
DEFAULT_SURFACE_PATH = _REPO_ROOT / "ace_mcp_client/server.py"
DEFAULT_JSON_RESULT_PATH = _REPO_ROOT / "evaluations/results/state_engine_tp0_runtime_baseline_v1.json"
DEFAULT_MARKDOWN_RESULT_PATH = _REPO_ROOT / "evaluations/results/state_engine_tp0_runtime_baseline_v1.md"


def _validate_sha256(value: str) -> str:
    normalized = value.lower()
    if len(normalized) != 64 or any(character not in _SHA256 for character in normalized):
        raise ValueError("value must be a lowercase SHA-256 digest")
    return normalized


class BaselineEnvironmentV1(FrozenContract):
    system: str = Field(min_length=1, max_length=80)
    release: str = Field(min_length=1, max_length=80)
    machine: str = Field(min_length=1, max_length=80)
    logical_cpu_count: int = Field(gt=0)
    python_implementation: str = Field(min_length=1, max_length=80)
    python_version: str = Field(min_length=1, max_length=80)
    ace_version: str = Field(min_length=1, max_length=80)
    source_revision: str = Field(min_length=7, max_length=64)
    execution_mode: Literal["source_checkout"] = "source_checkout"
    public_surface: Literal["thin_mcp_11_tool_contract"] = "thin_mcp_11_tool_contract"
    provider_route: Literal["none"] = "none"
    model: None = None
    database_route: Literal["none"] = "none"


class BaselineBudgetsV1(FrozenContract):
    max_cases: int = Field(gt=0, le=100)
    max_evidence_records_per_case: int = Field(gt=0, le=100)
    max_model_calls: Literal[0] = 0
    max_input_tokens: Literal[0] = 0
    max_output_tokens: Literal[0] = 0
    max_estimated_cost_usd: Literal[0] = 0
    max_database_writes: Literal[0] = 0
    max_wall_clock_seconds: int = Field(gt=0, le=300)


class BaselineSeedsV1(FrozenContract):
    evaluation_seed: int = Field(ge=0)
    model_seed: None = None
    note: str = Field(min_length=1, max_length=1_000)


class BaselineRulesV1(FrozenContract):
    pass_rule: Literal["exact_structured_semantics"] = "exact_structured_semantics"
    unsupported_counts_as_failure: Literal[True] = True
    partial_credit_advances_maturity: Literal[False] = False
    reference_expectations_hidden_from_adapter: Literal[True] = True
    negative_controls_cannot_pass_vacuously: Literal[True] = True
    prose_is_not_structured_state: Literal[True] = True
    no_private_runtime_imports: Literal[True] = True
    required_ingest_fields: tuple[str, ...] = Field(min_length=1, max_length=40)
    required_output_contracts: tuple[str, ...] = Field(min_length=1, max_length=20)

    @field_validator("required_ingest_fields", "required_output_contracts", mode="before")
    @classmethod
    def normalize_values(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise ValueError("baseline rule values must be collections")
        normalized = tuple(sorted(set(value)))
        if any(not isinstance(item, str) or not item.strip() for item in normalized):
            raise ValueError("baseline rule values must be non-empty strings")
        return normalized


class RuntimeBaselineConfigV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.runtime-baseline-config/v1"] = TP0_RUNTIME_BASELINE_CONFIG_VERSION
    baseline_id: str = Field(min_length=1, max_length=160)
    corpus_hash: str
    adapter_source_sha256: str
    public_surface_sha256: str
    adapter_version: Literal["ace.grounded-state.current-thin-mcp-adapter/v1"] = TP0_CURRENT_ACE_ADAPTER_VERSION
    environment: BaselineEnvironmentV1
    budgets: BaselineBudgetsV1
    seeds: BaselineSeedsV1
    rules: BaselineRulesV1
    declared_limitations: tuple[str, ...] = Field(min_length=1, max_length=30)

    @field_validator("corpus_hash", "adapter_source_sha256", "public_surface_sha256")
    @classmethod
    def validate_corpus_hash(cls, value: str) -> str:
        return _validate_sha256(value)

    @field_validator("declared_limitations", mode="before")
    @classmethod
    def normalize_limitations(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise ValueError("declared_limitations must be a collection")
        normalized = tuple(sorted(set(value)))
        if any(not isinstance(item, str) or not item.strip() or len(item) > 2_000 for item in normalized):
            raise ValueError("declared limitations must be bounded non-empty strings")
        return normalized

    def config_hash(self) -> str:
        return canonical_hash(self)


class PublicToolV1(FrozenContract):
    name: str = Field(min_length=1, max_length=120)
    parameters: tuple[str, ...] = Field(max_length=100)
    return_annotation: str | None = Field(default=None, max_length=500)


class PublicSurfaceV1(FrozenContract):
    source_path: str = Field(min_length=1, max_length=500)
    source_sha256: str
    tools: tuple[PublicToolV1, ...] = Field(min_length=1, max_length=100)

    @field_validator("source_sha256")
    @classmethod
    def validate_source_hash(cls, value: str) -> str:
        return _validate_sha256(value)

    @model_validator(mode="after")
    def validate_tools(self) -> Self:
        names = [tool.name for tool in self.tools]
        if names != sorted(names) or len(names) != len(set(names)):
            raise ValueError("public tools must have unique sorted names")
        return self


class BaselineDisposition(StrEnum):
    EXACT_MATCH = "exact_match"
    MISMATCH = "mismatch"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


class RuntimeCaseInputV1(FrozenContract):
    """Inputs visible to the adapter; expected answers are deliberately absent."""

    input_id: str
    product_ids: tuple[str, ...]
    evidence: tuple[dict[str, Any], ...]
    as_of_times: tuple[datetime, ...]


class AdapterObservationV1(FrozenContract):
    disposition: BaselineDisposition
    reason_codes: tuple[str, ...] = Field(min_length=1, max_length=20)
    emitted_beliefs: tuple[dict[str, Any], ...] = Field(default_factory=tuple, max_length=100)
    emitted_relationships: tuple[dict[str, Any], ...] = Field(default_factory=tuple, max_length=100)
    emitted_transition_hypotheses: tuple[dict[str, Any], ...] = Field(default_factory=tuple, max_length=100)
    emitted_rollouts: tuple[dict[str, Any], ...] = Field(default_factory=tuple, max_length=100)
    emitted_record_meanings: tuple[str, ...] = Field(default_factory=tuple, max_length=20)
    model_calls: Literal[0] = 0
    input_tokens: Literal[0] = 0
    output_tokens: Literal[0] = 0
    estimated_cost_usd: Literal[0] = 0
    database_writes: Literal[0] = 0


class RuntimeBaselineCaseResultV1(FrozenContract):
    case_key: str
    case_id: str
    case_hash: str
    adapter_input_hash: str
    disposition: BaselineDisposition
    reason_codes: tuple[str, ...]
    expected_judgments: int = Field(ge=1)
    matched_judgments: int = Field(ge=0)
    prohibited_violations: int = Field(ge=0)
    exact_match: bool
    model_calls: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    database_writes: int = Field(ge=0)

    @field_validator("case_hash", "adapter_input_hash")
    @classmethod
    def validate_hashes(cls, value: str) -> str:
        return _validate_sha256(value)


class RuntimeBaselineSummaryV1(FrozenContract):
    total_cases: int = Field(ge=0)
    exact_matches: int = Field(ge=0)
    mismatches: int = Field(ge=0)
    unsupported: int = Field(ge=0)
    errors: int = Field(ge=0)
    exact_match_rate: float = Field(ge=0, le=1)
    matched_judgments: int = Field(ge=0)
    expected_judgments: int = Field(ge=0)
    model_calls: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    database_writes: int = Field(ge=0)


class RuntimeBaselineResultV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.runtime-baseline-result/v1"] = TP0_RUNTIME_BASELINE_RESULT_VERSION
    baseline_id: str
    executed_at: datetime
    duration_ms: int = Field(ge=0)
    config_hash: str
    corpus_hash: str
    adapter_version: str
    environment_matches_reference: bool
    environment_differences: tuple[str, ...]
    public_surface: PublicSurfaceV1
    cases: tuple[RuntimeBaselineCaseResultV1, ...]
    summary: RuntimeBaselineSummaryV1
    outcome_hash: str
    conclusion: Literal["capability_not_established", "capability_partially_established", "capability_established"]
    declared_limitations: tuple[str, ...]

    @field_validator("executed_at")
    @classmethod
    def validate_executed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("executed_at must include a timezone")
        return value

    @field_validator("config_hash", "corpus_hash", "outcome_hash")
    @classmethod
    def validate_hashes(cls, value: str) -> str:
        return _validate_sha256(value)


def _annotation(node: ast.expr | None) -> str | None:
    return ast.unparse(node) if node is not None else None


def inspect_thin_mcp_surface(path: str | Path) -> PublicSurfaceV1:
    """Parse the supported thin MCP server without importing engine internals."""
    source_path = Path(path)
    source = source_path.read_bytes()
    tree = ast.parse(source, filename=str(source_path))
    tools: list[PublicToolV1] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        tool_name: str | None = None
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if not isinstance(decorator.func, ast.Attribute) or decorator.func.attr != "tool":
                continue
            for keyword in decorator.keywords:
                if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                    tool_name = str(keyword.value.value)
        if tool_name is None:
            continue
        positional = [argument.arg for argument in (*node.args.posonlyargs, *node.args.args)]
        keyword_only = [argument.arg for argument in node.args.kwonlyargs]
        tools.append(
            PublicToolV1(
                name=tool_name,
                parameters=tuple(positional + keyword_only),
                return_annotation=_annotation(node.returns),
            )
        )
    return PublicSurfaceV1(
        source_path=source_path.name,
        source_sha256=hashlib.sha256(source).hexdigest(),
        tools=tuple(sorted(tools, key=lambda tool: tool.name)),
    )


def _current_environment(config: RuntimeBaselineConfigV1) -> BaselineEnvironmentV1:
    reference = config.environment
    try:
        ace_version = package_version("ace-core")
    except PackageNotFoundError:
        ace_version = reference.ace_version
    return BaselineEnvironmentV1(
        system=platform.system(),
        release=platform.release(),
        machine=platform.machine(),
        logical_cpu_count=os.cpu_count() or 1,
        python_implementation=platform.python_implementation(),
        python_version=platform.python_version(),
        ace_version=ace_version,
        source_revision=_source_revision(_REPO_ROOT),
        execution_mode=reference.execution_mode,
        public_surface=reference.public_surface,
        provider_route="none",
        model=None,
        database_route="none",
    )


def _source_revision(root: Path) -> str:
    """Resolve the checked-out revision without invoking git or mutating state."""
    git_dir = root / ".git"
    head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    if not head.startswith("ref: "):
        return head
    ref = head.removeprefix("ref: ")
    loose_ref = git_dir / ref
    if loose_ref.exists():
        return loose_ref.read_text(encoding="utf-8").strip()
    packed_refs = git_dir / "packed-refs"
    if packed_refs.exists():
        for line in packed_refs.read_text(encoding="utf-8").splitlines():
            if not line.startswith(("#", "^")) and line.endswith(f" {ref}"):
                return line.split(" ", 1)[0]
    raise ValueError(f"unable to resolve source revision {ref}")


def _environment_differences(reference: BaselineEnvironmentV1, current: BaselineEnvironmentV1) -> tuple[str, ...]:
    reference_values = reference.model_dump(mode="json")
    current_values = current.model_dump(mode="json")
    return tuple(
        f"{key}: expected {reference_values[key]!r}, observed {current_values[key]!r}"
        for key in sorted(reference_values)
        if reference_values[key] != current_values[key]
    )


class CurrentThinMcpAdapterV1:
    """Observe whether today's supported MCP surface implements State Engine I/O."""

    def __init__(self, config: RuntimeBaselineConfigV1, surface: PublicSurfaceV1):
        self._config = config
        self._surface = surface

    def run(self, case_input: RuntimeCaseInputV1) -> AdapterObservationV1:
        del case_input  # Expectations are not available and the legacy surface cannot accept the input contract.
        tools = {tool.name: tool for tool in self._surface.tools}
        capture_parameters = set(tools.get("ace_capture", PublicToolV1(name="missing", parameters=())).parameters)
        missing_ingest = set(self._config.rules.required_ingest_fields) - capture_parameters
        reason_codes: list[str] = []
        if missing_ingest:
            reason_codes.append("unsupported_grounded_evidence_ingest_contract")
        # The current generic dict/text returns do not declare any of the required
        # machine-checkable State Engine output contracts.
        typed_outputs = {
            annotation
            for tool in self._surface.tools
            if (annotation := tool.return_annotation) is not None and annotation not in {"dict", "str"}
        }
        if not set(self._config.rules.required_output_contracts).issubset(typed_outputs):
            reason_codes.append("unsupported_structured_state_output_contract")
        if not reason_codes:
            # Future public surface changes must add a real adapter.  Structural
            # discovery alone is not allowed to fabricate runtime outputs.
            reason_codes.append("state_engine_adapter_not_implemented")
        return AdapterObservationV1(
            disposition=BaselineDisposition.UNSUPPORTED,
            reason_codes=tuple(sorted(reason_codes)),
        )


def load_runtime_baseline_config(path: str | Path) -> RuntimeBaselineConfigV1:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("runtime baseline config must be a JSON object")
    return RuntimeBaselineConfigV1.model_validate(payload)


def load_temporal_corpus(path: str | Path) -> TemporalReferenceCorpusV1:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("temporal reference corpus must be a JSON object")
    return TemporalReferenceCorpusV1.model_validate(payload)


def run_current_ace_baseline(
    config: RuntimeBaselineConfigV1,
    corpus: TemporalReferenceCorpusV1,
    surface: PublicSurfaceV1,
    *,
    executed_at: datetime | None = None,
) -> RuntimeBaselineResultV1:
    """Execute the strict baseline without network, provider, database, or writes."""
    started = time.monotonic()
    if corpus.corpus_hash() != config.corpus_hash:
        raise ValueError("baseline config corpus_hash does not match the supplied corpus")
    adapter_source_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if adapter_source_hash != config.adapter_source_sha256:
        raise ValueError("baseline adapter source does not match the frozen configuration")
    if surface.source_sha256 != config.public_surface_sha256:
        raise ValueError("current public surface does not match the frozen configuration")
    if len(corpus.cases) > config.budgets.max_cases:
        raise ValueError("corpus exceeds the frozen case budget")
    if any(len(case.evidence) > config.budgets.max_evidence_records_per_case for case in corpus.cases):
        raise ValueError("corpus case exceeds the frozen evidence-record budget")

    current_environment = _current_environment(config)
    environment_differences = _environment_differences(config.environment, current_environment)
    adapter = CurrentThinMcpAdapterV1(config, surface)
    case_results: list[RuntimeBaselineCaseResultV1] = []
    for case in corpus.cases:
        adapter_input = RuntimeCaseInputV1(
            input_id=case.case_id(),
            product_ids=case.product_ids,
            evidence=tuple(item.model_dump(mode="json") for item in case.evidence),
            as_of_times=case.as_of_times,
        )
        observation = adapter.run(adapter_input)
        # Current ACE emits no typed State Engine judgments.  Avoidance of a
        # prohibited edge earns no credit when the positive contract is absent.
        matched_judgments = 0
        exact_match = False
        case_results.append(
            RuntimeBaselineCaseResultV1(
                case_key=case.case_key,
                case_id=case.case_id(),
                case_hash=case.case_hash(),
                adapter_input_hash=canonical_hash(adapter_input),
                disposition=observation.disposition,
                reason_codes=observation.reason_codes,
                expected_judgments=len(case.expected.judgment_hashes()),
                matched_judgments=matched_judgments,
                prohibited_violations=0,
                exact_match=exact_match,
                model_calls=observation.model_calls,
                input_tokens=observation.input_tokens,
                output_tokens=observation.output_tokens,
                estimated_cost_usd=observation.estimated_cost_usd,
                database_writes=observation.database_writes,
            )
        )

    dispositions = [result.disposition for result in case_results]
    summary = RuntimeBaselineSummaryV1(
        total_cases=len(case_results),
        exact_matches=sum(result.exact_match for result in case_results),
        mismatches=dispositions.count(BaselineDisposition.MISMATCH),
        unsupported=dispositions.count(BaselineDisposition.UNSUPPORTED),
        errors=dispositions.count(BaselineDisposition.ERROR),
        exact_match_rate=(sum(result.exact_match for result in case_results) / len(case_results)),
        matched_judgments=sum(result.matched_judgments for result in case_results),
        expected_judgments=sum(result.expected_judgments for result in case_results),
        model_calls=sum(result.model_calls for result in case_results),
        input_tokens=sum(result.input_tokens for result in case_results),
        output_tokens=sum(result.output_tokens for result in case_results),
        estimated_cost_usd=sum(result.estimated_cost_usd for result in case_results),
        database_writes=sum(result.database_writes for result in case_results),
    )
    if summary.exact_matches == summary.total_cases:
        conclusion = "capability_established"
    elif summary.exact_matches:
        conclusion = "capability_partially_established"
    else:
        conclusion = "capability_not_established"
    outcome_hash = canonical_hash(
        {
            "config_hash": config.config_hash(),
            "corpus_hash": corpus.corpus_hash(),
            "surface": surface.model_dump(mode="json"),
            "cases": [result.model_dump(mode="json") for result in case_results],
            "summary": summary.model_dump(mode="json"),
            "conclusion": conclusion,
        }
    )
    duration_ms = round((time.monotonic() - started) * 1_000)
    if duration_ms > config.budgets.max_wall_clock_seconds * 1_000:
        raise RuntimeError("runtime baseline exceeded the frozen wall-clock budget")
    return RuntimeBaselineResultV1(
        baseline_id=config.baseline_id,
        executed_at=executed_at or datetime.now(timezone.utc),
        duration_ms=duration_ms,
        config_hash=config.config_hash(),
        corpus_hash=corpus.corpus_hash(),
        adapter_version=config.adapter_version,
        environment_matches_reference=not environment_differences,
        environment_differences=environment_differences,
        public_surface=surface,
        cases=tuple(case_results),
        summary=summary,
        outcome_hash=outcome_hash,
        conclusion=conclusion,
        declared_limitations=config.declared_limitations,
    )


def render_runtime_baseline_markdown(result: RuntimeBaselineResultV1) -> str:
    summary = result.summary
    lines = [
        "# ACE State Engine TP0 current-runtime baseline v1",
        "",
        f"- Baseline: `{result.baseline_id}`",
        f"- Executed: `{result.executed_at.isoformat()}`",
        f"- Corpus hash: `{result.corpus_hash}`",
        f"- Configuration hash: `{result.config_hash}`",
        f"- Public-surface hash: `{result.public_surface.source_sha256}`",
        f"- Outcome hash: `{result.outcome_hash}`",
        f"- Reference environment matched: **{'yes' if result.environment_matches_reference else 'no'}**",
        f"- Conclusion: **{result.conclusion}**",
        "",
        "## Result",
        "",
        "| Measure | Result |",
        "|---|---:|",
        f"| Cases | {summary.total_cases} |",
        f"| Exact structured matches | {summary.exact_matches} |",
        f"| Unsupported | {summary.unsupported} |",
        f"| Mismatches | {summary.mismatches} |",
        f"| Errors | {summary.errors} |",
        f"| Matched judgments | {summary.matched_judgments} / {summary.expected_judgments} |",
        f"| Model calls | {summary.model_calls} |",
        f"| Tokens | {summary.input_tokens + summary.output_tokens} |",
        f"| Estimated cost USD | {summary.estimated_cost_usd:.2f} |",
        f"| Database writes | {summary.database_writes} |",
        "",
        "Current ACE exposes the supported thin 11-tool MCP contract, but that contract cannot accept the",
        "frozen grounded-evidence shape or emit typed belief state, relationships, transition hypotheses,",
        "or consequence rollouts. All 40 cases therefore remain unsupported. Unsupported cases count as",
        "failures; negative controls receive no vacuous credit.",
        "",
        "## Public surface",
        "",
        "| Tool | Parameters | Return |",
        "|---|---|---|",
    ]
    for tool in result.public_surface.tools:
        lines.append(f"| `{tool.name}` | `{', '.join(tool.parameters)}` | `{tool.return_annotation or 'untyped'}` |")
    lines.extend(["", "## Declared limitations", ""])
    lines.extend(f"- {limitation}" for limitation in result.declared_limitations)
    if result.environment_differences:
        lines.extend(["", "## Environment differences", ""])
        lines.extend(f"- {difference}" for difference in result.environment_differences)
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This is an architecture capability baseline, not an LLM quality comparison and not evidence",
            "that TP1 or TP2 is complete. It establishes the honest zero point before a grounded-state",
            "ingestion/query surface exists.",
            "",
        ]
    )
    return "\n".join(lines)


def write_runtime_baseline_results(
    result: RuntimeBaselineResultV1,
    json_path: str | Path,
    markdown_path: str | Path,
) -> None:
    json_output = Path(json_path)
    markdown_output = Path(markdown_path)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(
        json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_output.write_text(render_runtime_baseline_markdown(result), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the frozen TP0 current-ACE runtime baseline")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_PATH)
    parser.add_argument("--surface", type=Path, default=DEFAULT_SURFACE_PATH)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON_RESULT_PATH)
    parser.add_argument("--markdown-out", type=Path, default=DEFAULT_MARKDOWN_RESULT_PATH)
    args = parser.parse_args()

    config = load_runtime_baseline_config(args.config)
    corpus = load_temporal_corpus(args.corpus)
    surface = inspect_thin_mcp_surface(args.surface)
    result = run_current_ace_baseline(config, corpus, surface)
    write_runtime_baseline_results(result, args.json_out, args.markdown_out)
    print(json.dumps(result.summary.model_dump(mode="json"), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
