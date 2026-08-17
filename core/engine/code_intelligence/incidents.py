"""Fail-closed public incident-to-code projection for Code Intelligence.

The v1 packet admits one independently verified public fixture.  It consumes a
host-supplied, provider-neutral source envelope and emits only the exact
incident/code relation declared by the report.  Repeated error text, generic
failure stores, and historical commits are never promoted into code edges.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any, Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, ValidationError, field_validator, model_validator

from core.engine.code_intelligence.contracts import FrozenContract, stable_id

_SYMBOL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,199}$")
_MAX_SECTION_CHARS = 20_000
_MAX_CODE_SPAN = 200

_REPORT_COMMIT = "083c62168e470e466e9d701fb48242eef254d7b5"
_REPORT_REPOSITORY = "https://github.com/keep-network/tbtc-website"
_REPORT_PATH = "src/pages/news/2020-05-21-details-of-the-tbtc-deposit-pause-on-may-18-2020.md"
_REPORT_BLOB = "693535acb820c7b8347c4e1bf3bccc81414b01c8"
_REPORT_DIGEST = "sha256:9f105c2a56cae01b16e27625dee1b6c2d32a5f9dae71225bb0c0fb4a659a6a72"
_REPORT_BYTE_COUNT = 20_336
_REPORT_URI = f"{_REPORT_REPOSITORY}/blob/{_REPORT_COMMIT}/{_REPORT_PATH}"
_REPORT_RAW_URI = f"https://raw.githubusercontent.com/keep-network/tbtc-website/{_REPORT_COMMIT}/{_REPORT_PATH}"
_REPORT_PUBLISHED_URI = "https://tbtc.network/news/2020-05-21-details-of-the-tbtc-deposit-pause-on-may-18-2020/"
_INCIDENT_TITLE = "Details of the tBTC Deposit Pause on May 18, 2020"
_TIMELINE_DIGEST = "sha256:31bfd48a08b7535c7726f04b4ff6af4fcb1ec5d113b5462f6774607692881d1c"
_DECLARATION_DIGEST = "sha256:7f15b01d687ad196081b48c75d6e2ec4028bfc615b8744d5a563d2945e0bd450"
_CODE_REVISION = "9651d53a443b3d2470e13ee1db0ecae60be8b246"
_CODE_REPOSITORY = "https://github.com/keep-network/tbtc"
_CODE_PATH = "solidity/contracts/deposit/DepositRedemption.sol"
_CODE_SYMBOL = "redemptionTransactionChecks"
_CODE_BLOB = "e7e16d77c32fd23437320cede83c07db75e6f5e8"
_CODE_DIGEST = "sha256:22ce6fd7f78e97423a495273bbea89d7d185b12318b3dd0da6449b38acbaf330"
_CODE_BYTE_COUNT = 17_849
_CODE_URI = f"{_CODE_REPOSITORY}/blob/{_CODE_REVISION}/{_CODE_PATH}#L326-L355"
_CODE_RAW_URI = f"https://raw.githubusercontent.com/keep-network/tbtc/{_CODE_REVISION}/{_CODE_PATH}"
_CODE_EXCERPT_DIGEST = "sha256:8dcc8a65e144e04de894826c9b7777430570265f175198a0b687d6652c50d172"
_SOURCE_DEFINITION_REF = "source_definition:code-intelligence-tbtc-incident-v1"
_SOURCE_LOCATOR = f"git-blob:{_REPORT_BLOB}"
_ACQUISITION_RECEIPT_REF = "acquisition_receipt:tbtc-incident-fixture-v1"
_FIXTURE_PAYLOAD_DIGEST = "sha256:7eb299306cd8d25f3be927b117cdfc83ecdb75cb4b338e95856874072bc7b52f"
_FIXTURE_ACQUISITION_DIGEST = "sha256:bcdb5d18066859e0d79c20e4cc1c41acc8849c74f7e3574100e93076e8d48c35"
_NON_PROJECTED_HISTORICAL_REVISION = "71361a51c220536d82681f1ab77ed640836329ce"
_NON_PROJECTED_HISTORICAL_REASON = (
    "The report discusses this historical change separately; this fixture does not bind it to the affected "
    "snapshot coordinate and emits no historical-change relation."
)
_TIMELINE_OMISSION_DETAIL = (
    "The timeline repeats the runtime error text but declares no immutable repository coordinate; "
    "lexical similarity emits no code relation."
)
_EXPECTED_CLOCKS = (
    ("sortition_pool_created", "2020-03-15T15:52:00+00:00", 23),
    ("redemption_first_failed", "2020-05-18T02:29:00+00:00", 29),
    ("relay_caught_up", "2020-05-18T03:07:00+00:00", 29),
    ("redemption_error_observed", "2020-05-18T03:13:00+00:00", 31),
    ("finding_corroborated", "2020-05-18T05:02:00+00:00", 35),
    ("emergency_pause_triggered", "2020-05-18T05:18:00+00:00", 37),
    ("pause_transaction_completed", "2020-05-18T05:45:00+00:00", 37),
    ("hosted_pages_redirected", "2020-05-18T14:11:00+00:00", 39),
)


class IncidentProjectionError(ValueError):
    """The source cannot produce the bounded incident projection."""


def _text_digest(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _aware_utc(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _exact_https(value: str, *, name: str) -> str:
    if len(value) > 2_048 or any(character.isspace() or ord(character) < 0x20 for character in value):
        raise ValueError(f"{name} must be a bounded exact HTTPS URI")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{name} must be a bounded exact HTTPS URI")
    return value


def _repository_path(value: str) -> str:
    if not value or len(value) > 1_000 or "\\" in value or "\x00" in value:
        raise ValueError("repository path must use bounded canonical POSIX spelling")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts) or str(path) != value:
        raise ValueError("repository path traversal or alias is not allowed")
    return value


class IncidentSourceEnvelopeV1Alpha1(FrozenContract):
    """Code-owned view of one canonical host source snapshot."""

    contract: Literal["ace.code-intelligence.incident-source-envelope/v1alpha1"] = (
        "ace.code-intelligence.incident-source-envelope/v1alpha1"
    )
    source_definition_ref: str
    source_snapshot_ref: str
    source_snapshot_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    source_type_ref: Literal["code-intelligence.public-incident-fixture"]
    source_uri: str
    captured_payload_json: str = Field(min_length=1, max_length=200_000)
    captured_payload_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    source_published_at: datetime
    event_effective_at: datetime
    observed_at: datetime
    ingested_at: datetime
    locator: str
    acquisition_mode: Literal["prepared_fixture"]
    acquisition_receipt_ref: str
    acquisition_receipt_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    provider_neutral: Literal[True] = True
    source_authority: Literal[False] = False
    reasoning_authority: Literal[False] = False
    change_authority: Literal[False] = False
    approval_authority: Literal[False] = False
    delivery_authority: Literal[False] = False
    execution_authority: Literal[False] = False
    effect_authority: Literal[False] = False

    @field_validator("source_uri")
    @classmethod
    def exact_source_uri(cls, value: str) -> str:
        return _exact_https(value, name="source_uri")

    @model_validator(mode="after")
    def exact_payload_and_times(self) -> Self:
        try:
            canonical_payload = json.dumps(
                json.loads(self.captured_payload_json),
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError("incident source payload must be canonical finite JSON") from exc
        if self.captured_payload_json != canonical_payload:
            raise ValueError("incident source payload must use Core canonical JSON spelling")
        if _text_digest(self.captured_payload_json) != self.captured_payload_digest:
            raise ValueError("incident source payload digest differs from exact payload")
        published = _aware_utc(self.source_published_at, name="source_published_at")
        effective = _aware_utc(self.event_effective_at, name="event_effective_at")
        observed = _aware_utc(self.observed_at, name="observed_at")
        ingested = _aware_utc(self.ingested_at, name="ingested_at")
        if published > observed or effective > observed or observed > ingested:
            raise ValueError("incident source clocks are not causally ordered")
        object.__setattr__(self, "source_published_at", published)
        object.__setattr__(self, "event_effective_at", effective)
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "ingested_at", ingested)
        expected_receipt_digest = _text_digest(
            json.dumps(
                {"mode": "prepared_fixture", "payload": self.captured_payload_digest},
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        if (
            self.source_definition_ref != _SOURCE_DEFINITION_REF
            or self.source_uri != _REPORT_URI
            or published.isoformat() != "2020-05-21T17:02:51.487000+00:00"
            or effective.isoformat() != "2020-03-15T15:52:00+00:00"
            or self.locator != _SOURCE_LOCATOR
            or self.acquisition_mode != "prepared_fixture"
            or self.acquisition_receipt_ref != _ACQUISITION_RECEIPT_REF
            or self.acquisition_receipt_digest != expected_receipt_digest
        ):
            raise ValueError("incident source provenance differs from the frozen prepared-fixture seam")

        snapshot_material = {
            "contract": "ace.core.canonical-source-snapshot/v1alpha1",
            "source_definition_ref": self.source_definition_ref,
            "source_type_ref": self.source_type_ref,
            "source_uri": self.source_uri,
            "captured_payload_json": self.captured_payload_json,
            "captured_payload_digest": self.captured_payload_digest,
            "source_published_at": self.source_published_at.isoformat().replace("+00:00", "Z"),
            "event_effective_at": self.event_effective_at.isoformat().replace("+00:00", "Z"),
            "observed_at": self.observed_at.isoformat().replace("+00:00", "Z"),
            "ingested_at": self.ingested_at.isoformat().replace("+00:00", "Z"),
            "locator": self.locator,
            "acquisition_mode": self.acquisition_mode,
            "acquisition_receipt_ref": self.acquisition_receipt_ref,
            "acquisition_receipt_digest": self.acquisition_receipt_digest,
        }
        snapshot_digest = _text_digest(
            json.dumps(
                snapshot_material,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        expected_snapshot_ref = f"source_snapshot:{snapshot_digest.removeprefix('sha256:')[:32]}"
        if self.source_snapshot_digest != snapshot_digest or self.source_snapshot_ref != expected_snapshot_ref:
            raise ValueError("incident source snapshot identity differs from exact canonical material")
        return self


class IncidentReportSourceV1Alpha1(FrozenContract):
    repository_url: str
    repository_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    repository_path: str
    git_blob_sha: str = Field(pattern=r"^[a-f0-9]{40}$")
    content_sha256: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    byte_count: int = Field(ge=1, le=1_000_000)
    raw_url: str
    immutable_url: str
    published_url: str
    published_at: datetime

    @field_validator("repository_url", "immutable_url", "published_url", "raw_url")
    @classmethod
    def exact_urls(cls, value: str, info) -> str:
        return _exact_https(value, name=info.field_name)

    @field_validator("repository_path")
    @classmethod
    def canonical_path(cls, value: str) -> str:
        return _repository_path(value)

    @model_validator(mode="after")
    def exact_immutable_coordinate(self) -> Self:
        expected = f"{self.repository_url}/blob/{self.repository_commit}/{self.repository_path}"
        if self.immutable_url != expected:
            raise ValueError("report immutable URL differs from revision/path coordinate")
        object.__setattr__(self, "published_at", _aware_utc(self.published_at, name="published_at"))
        return self


class IncidentLicenseAnchorV1Alpha1(FrozenContract):
    scope: Literal["report", "code"]
    spdx_id: Literal["MIT"]
    immutable_url: str
    raw_url: str
    git_blob_sha: str = Field(pattern=r"^[a-f0-9]{40}$")
    byte_count: int = Field(ge=1, le=100_000)
    content_sha256: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    copyright_notice: Literal["Copyright (c) 2020 Keep SEZC."]

    @field_validator("immutable_url", "raw_url")
    @classmethod
    def exact_url(cls, value: str) -> str:
        return _exact_https(value, name="license immutable_url")

    @property
    def anchor_id(self) -> str:
        return stable_id("code_incident_license", self)


class IncidentClockV1Alpha1(FrozenContract):
    label: str = Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")
    occurred_at: datetime
    source_line: int = Field(ge=1, le=10_000)

    @field_validator("occurred_at")
    @classmethod
    def aware_clock(cls, value: datetime) -> datetime:
        return _aware_utc(value, name="occurred_at")


class IncidentCodeCoordinateV1Alpha1(FrozenContract):
    relation: Literal["affected_code_snapshot"]
    repository_url: str
    revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    path: str
    symbol: str
    line_start: int = Field(ge=1, le=100_000)
    line_end: int = Field(ge=1, le=100_000)
    immutable_url: str
    git_blob_sha: str = Field(pattern=r"^[a-f0-9]{40}$")
    file_sha256: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    byte_count: int = Field(ge=1, le=1_000_000)
    raw_url: str
    excerpt: str = Field(min_length=1, max_length=_MAX_SECTION_CHARS)
    excerpt_sha256: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")

    @field_validator("repository_url", "immutable_url", "raw_url")
    @classmethod
    def exact_urls(cls, value: str, info) -> str:
        return _exact_https(value, name=info.field_name)

    @field_validator("path")
    @classmethod
    def canonical_path(cls, value: str) -> str:
        return _repository_path(value)

    @field_validator("symbol")
    @classmethod
    def bounded_symbol(cls, value: str) -> str:
        if not _SYMBOL.fullmatch(value):
            raise ValueError("code symbol must use bounded identifier spelling")
        return value

    @model_validator(mode="after")
    def exact_coordinate_and_excerpt(self) -> Self:
        if self.line_end < self.line_start or self.line_end - self.line_start + 1 > _MAX_CODE_SPAN:
            raise ValueError("code coordinate exceeds ordered line bounds")
        if len(self.excerpt.splitlines()) != self.line_end - self.line_start + 1:
            raise ValueError("code excerpt line count differs from coordinate")
        if _text_digest(self.excerpt) != self.excerpt_sha256:
            raise ValueError("code excerpt digest differs from exact excerpt")
        expected = f"{self.repository_url}/blob/{self.revision}/{self.path}#L{self.line_start}-L{self.line_end}"
        if self.immutable_url != expected:
            raise ValueError("code immutable URL differs from exact coordinate")
        return self

    @property
    def coordinate_id(self) -> str:
        return stable_id("code_incident_coordinate", self.model_dump(exclude={"excerpt"}))


class IncidentFixtureSectionV1Alpha1(FrozenContract):
    section_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,79}$")
    kind: Literal["timeline_only", "source_declared_code_coordinate"]
    source_line_start: int = Field(ge=1, le=10_000)
    source_line_end: int = Field(ge=1, le=10_000)
    excerpt: str = Field(min_length=1, max_length=_MAX_SECTION_CHARS)
    excerpt_sha256: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    code_coordinate: IncidentCodeCoordinateV1Alpha1 | None

    @model_validator(mode="after")
    def exact_section(self) -> Self:
        if self.source_line_end < self.source_line_start or self.source_line_end - self.source_line_start > 500:
            raise ValueError("incident section exceeds ordered source bounds")
        if len(self.excerpt.splitlines()) != self.source_line_end - self.source_line_start + 1:
            raise ValueError("incident excerpt line count differs from source bounds")
        if _text_digest(self.excerpt) != self.excerpt_sha256:
            raise ValueError("incident excerpt digest differs from exact excerpt")
        if self.kind == "timeline_only" and self.code_coordinate is not None:
            raise ValueError("timeline-only evidence cannot declare a code coordinate")
        if self.kind == "source_declared_code_coordinate" and self.code_coordinate is None:
            raise ValueError("declared-code section requires an exact code coordinate")
        return self

    @property
    def evidence_id(self) -> str:
        return stable_id(
            "code_incident_evidence",
            self.model_dump(exclude={"excerpt", "code_coordinate"}),
        )


class NonProjectedIncidentContextV1Alpha1(FrozenContract):
    revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    immutable_url: str
    report_label: Literal["How The Code Landed"]
    projected: Literal[False]
    reason: str = Field(min_length=1, max_length=1_000)

    @field_validator("immutable_url")
    @classmethod
    def exact_url(cls, value: str) -> str:
        return _exact_https(value, name="non-projected context URL")


class PublicIncidentFixtureV1Alpha1(FrozenContract):
    contract: Literal["ace.code-intelligence.public-incident-fixture/v1alpha1"]
    fixture_key: Literal["keep-tbtc-deposit-pause-2020"]
    source_kind: Literal["incident_postmortem"]
    title: str = Field(min_length=1, max_length=300)
    report: IncidentReportSourceV1Alpha1
    licenses: tuple[IncidentLicenseAnchorV1Alpha1, ...] = Field(min_length=2, max_length=2)
    clocks: tuple[IncidentClockV1Alpha1, ...] = Field(min_length=1, max_length=16)
    sections: tuple[IncidentFixtureSectionV1Alpha1, ...] = Field(min_length=2, max_length=8)
    non_projected_context: NonProjectedIncidentContextV1Alpha1

    @model_validator(mode="after")
    def unique_fixture_material(self) -> Self:
        if len({item.scope for item in self.licenses}) != len(self.licenses):
            raise ValueError("incident fixture repeats a license scope")
        if len({item.label for item in self.clocks}) != len(self.clocks):
            raise ValueError("incident fixture repeats a clock label")
        if len({item.section_id for item in self.sections}) != len(self.sections):
            raise ValueError("incident fixture repeats a section id")
        coordinates = [item.code_coordinate for item in self.sections if item.code_coordinate is not None]
        if len({item.coordinate_id for item in coordinates}) != len(coordinates):
            raise ValueError("incident fixture repeats a code coordinate")
        return self


class IncidentProjectionEvidenceV1Alpha1(FrozenContract):
    evidence_id: str
    kind: Literal["report_section", "code_coordinate"]
    immutable_uri: str
    content_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    artifact_digest: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    source_snapshot_ref: str
    source_snapshot_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")


class IncidentProjectionRecordV1Alpha1(FrozenContract):
    incident_id: str
    fixture_key: str
    title: str
    report_uri: str
    report_commit: str
    report_blob_sha: str
    report_content_digest: str
    clocks: tuple[IncidentClockV1Alpha1, ...]


class IncidentCodeRelationV1Alpha1(FrozenContract):
    relation_id: str
    source_incident_id: str
    target_coordinate_id: str
    relation: Literal["affected_code_snapshot"]
    evidence_refs: tuple[str, str]
    derivation: Literal["source_declared"] = "source_declared"
    confidence: Literal["observed"] = "observed"
    lexical_match_is_causality: Literal[False] = False
    introduced_by_claimed: Literal[False] = False
    root_cause_claimed: Literal[False] = False


class IncidentProjectionOmissionV1Alpha1(FrozenContract):
    section_id: str
    reason: Literal[
        "no_source_declared_code_coordinate",
        "historical_change_not_conflated_with_affected_snapshot",
    ]
    detail: str
    evidence_ref: str | None = None


class IncidentToCodeProjectionV1Alpha1(FrozenContract):
    contract: Literal["ace.code-intelligence.incident-to-code-projection/v1alpha1"] = (
        "ace.code-intelligence.incident-to-code-projection/v1alpha1"
    )
    incident: IncidentProjectionRecordV1Alpha1
    code_coordinates: tuple[IncidentCodeCoordinateV1Alpha1, ...] = Field(min_length=1, max_length=1)
    relations: tuple[IncidentCodeRelationV1Alpha1, ...] = Field(min_length=1, max_length=1)
    evidence: tuple[IncidentProjectionEvidenceV1Alpha1, ...] = Field(min_length=3, max_length=3)
    license_anchors: tuple[IncidentLicenseAnchorV1Alpha1, ...] = Field(min_length=2, max_length=2)
    omissions: tuple[IncidentProjectionOmissionV1Alpha1, ...] = Field(min_length=2, max_length=2)
    source_snapshot_ref: str
    source_snapshot_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    acquisition_receipt_ref: str
    acquisition_receipt_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    source_acquisition_mode: Literal["prepared_fixture"]
    live_external_fetch_claimed: Literal[False] = False
    governed_adapter_delivery_claimed: Literal[False] = False
    source_snapshot_revalidation_required: Literal[True] = True
    self_authenticates_source_snapshot: Literal[False] = False
    provider_neutral: Literal[True] = True
    read_only: Literal[True] = True
    source_authority: Literal[False] = False
    reasoning_authority: Literal[False] = False
    change_authority: Literal[False] = False
    approval_authority: Literal[False] = False
    delivery_authority: Literal[False] = False
    execution_authority: Literal[False] = False
    effect_authority: Literal[False] = False

    @model_validator(mode="after")
    def exact_closed_projection_graph(self) -> Self:
        coordinate = self.code_coordinates[0]
        relation = self.relations[0]
        evidence = {item.evidence_id: item for item in self.evidence}
        if len(evidence) != 3:
            raise ValueError("incident projection evidence identities must be unique")
        if len({item.coordinate_id for item in self.code_coordinates}) != 1:
            raise ValueError("incident projection coordinate identities must be unique")
        if len({item.relation_id for item in self.relations}) != 1:
            raise ValueError("incident projection relation identities must be unique")
        if len({item.anchor_id for item in self.license_anchors}) != 2:
            raise ValueError("incident projection license identities must be unique")
        if len({(item.section_id, item.reason) for item in self.omissions}) != 2:
            raise ValueError("incident projection omission identities must be unique")
        if self.source_snapshot_ref != f"source_snapshot:{self.source_snapshot_digest[7:39]}":
            raise ValueError("incident projection source snapshot ref does not match its digest prefix")
        if (
            self.acquisition_receipt_ref != _ACQUISITION_RECEIPT_REF
            or self.acquisition_receipt_digest != _FIXTURE_ACQUISITION_DIGEST
        ):
            raise ValueError("incident projection acquisition receipt differs from the frozen prepared fixture")

        if (
            self.incident.fixture_key != "keep-tbtc-deposit-pause-2020"
            or self.incident.title != _INCIDENT_TITLE
            or self.incident.report_uri != _REPORT_URI
            or self.incident.report_commit != _REPORT_COMMIT
            or self.incident.report_blob_sha != _REPORT_BLOB
            or self.incident.report_content_digest != _REPORT_DIGEST
            or tuple((item.label, item.occurred_at.isoformat(), item.source_line) for item in self.incident.clocks)
            != _EXPECTED_CLOCKS
        ):
            raise ValueError("incident projection record differs from the frozen qualified source")
        if tuple(
            (
                item.scope,
                item.spdx_id,
                item.immutable_url,
                item.raw_url,
                item.git_blob_sha,
                item.byte_count,
                item.content_sha256,
                item.copyright_notice,
            )
            for item in self.license_anchors
        ) != (
            (
                "report",
                "MIT",
                f"{_REPORT_REPOSITORY}/blob/{_REPORT_COMMIT}/LICENSE",
                f"https://raw.githubusercontent.com/keep-network/tbtc-website/{_REPORT_COMMIT}/LICENSE",
                "4ed19fdb338ca18942ed904d47e5c377103e45eb",
                1_054,
                "sha256:be587dab2304aa7efbf8807c30107fbe74f17a772a563233b2d9fd1fb05503fd",
                "Copyright (c) 2020 Keep SEZC.",
            ),
            (
                "code",
                "MIT",
                f"{_CODE_REPOSITORY}/blob/{_CODE_REVISION}/LICENSE",
                f"https://raw.githubusercontent.com/keep-network/tbtc/{_CODE_REVISION}/LICENSE",
                "80a1ed24975b0263f29157a7bc788d9e30ab2adf",
                1_053,
                "sha256:59f67a2ea030f1fcbfd4f5ffd0aae8b65f66954e5aa0fdd5b745c4ac9eba6fb9",
                "Copyright (c) 2020 Keep SEZC.",
            ),
        ):
            raise ValueError("incident projection license anchors differ from the frozen source")
        coordinate_material = (
            coordinate.relation,
            coordinate.repository_url,
            coordinate.revision,
            coordinate.path,
            coordinate.symbol,
            coordinate.line_start,
            coordinate.line_end,
            coordinate.immutable_url,
            coordinate.git_blob_sha,
            coordinate.file_sha256,
            coordinate.byte_count,
            coordinate.raw_url,
            coordinate.excerpt_sha256,
        )
        if coordinate_material != (
            "affected_code_snapshot",
            _CODE_REPOSITORY,
            _CODE_REVISION,
            _CODE_PATH,
            _CODE_SYMBOL,
            326,
            355,
            _CODE_URI,
            _CODE_BLOB,
            _CODE_DIGEST,
            _CODE_BYTE_COUNT,
            _CODE_RAW_URI,
            _CODE_EXCERPT_DIGEST,
        ):
            raise ValueError("incident projection coordinate differs from the frozen qualified source")

        expected_incident_id = stable_id(
            "code_incident",
            {
                "fixture_key": self.incident.fixture_key,
                "report_commit": self.incident.report_commit,
                "report_digest": self.incident.report_content_digest,
            },
        )
        if self.incident.incident_id != expected_incident_id:
            raise ValueError("incident projection incident identity is not content-derived")
        if relation.source_incident_id != self.incident.incident_id:
            raise ValueError("incident projection relation source does not resolve")
        if relation.target_coordinate_id != coordinate.coordinate_id:
            raise ValueError("incident projection relation target does not resolve")
        if len(set(relation.evidence_refs)) != 2 or any(ref not in evidence for ref in relation.evidence_refs):
            raise ValueError("incident projection relation evidence does not resolve uniquely")
        expected_relation_id = stable_id(
            "code_incident_relation",
            {
                "source": self.incident.incident_id,
                "target": coordinate.coordinate_id,
                "relation": relation.relation,
                "evidence": relation.evidence_refs,
            },
        )
        if relation.relation_id != expected_relation_id:
            raise ValueError("incident projection relation identity is not content-derived")

        positive_evidence_id = stable_id(
            "code_incident_evidence",
            {
                "section_id": "technical-issue-code-coordinate",
                "kind": "source_declared_code_coordinate",
                "source_line_start": 45,
                "source_line_end": 45,
                "excerpt_sha256": _DECLARATION_DIGEST,
            },
        )
        timeline_evidence_id = stable_id(
            "code_incident_evidence",
            {
                "section_id": "incident-timeline",
                "kind": "timeline_only",
                "source_line_start": 21,
                "source_line_end": 39,
                "excerpt_sha256": _TIMELINE_DIGEST,
            },
        )
        code_evidence_id = stable_id("code_incident_evidence", coordinate.model_dump(exclude={"excerpt"}))
        expected_evidence = {
            positive_evidence_id: ("report_section", f"{_REPORT_URI}#L45", _DECLARATION_DIGEST, None, 45, 45),
            code_evidence_id: ("code_coordinate", _CODE_URI, _CODE_EXCERPT_DIGEST, _CODE_DIGEST, 326, 355),
            timeline_evidence_id: (
                "report_section",
                f"{_REPORT_URI}#L21-L39",
                _TIMELINE_DIGEST,
                None,
                21,
                39,
            ),
        }
        actual_evidence = {
            item.evidence_id: (
                item.kind,
                item.immutable_uri,
                item.content_digest,
                item.artifact_digest,
                item.line_start,
                item.line_end,
            )
            for item in self.evidence
        }
        if actual_evidence != expected_evidence:
            raise ValueError("incident projection evidence differs from exact source spans")
        if relation.evidence_refs != (positive_evidence_id, code_evidence_id):
            raise ValueError("incident projection relation evidence order differs from the declaration and code span")
        if any(
            item.source_snapshot_ref != self.source_snapshot_ref
            or item.source_snapshot_digest != self.source_snapshot_digest
            for item in self.evidence
        ):
            raise ValueError("incident projection evidence is cross-wired to another source snapshot")
        omission_refs = tuple(item.evidence_ref for item in self.omissions if item.evidence_ref is not None)
        if omission_refs != (timeline_evidence_id,):
            raise ValueError("incident projection omission evidence does not resolve exactly once")
        if tuple((item.section_id, item.reason, item.detail, item.evidence_ref) for item in self.omissions) != (
            (
                "incident-timeline",
                "no_source_declared_code_coordinate",
                _TIMELINE_OMISSION_DETAIL,
                timeline_evidence_id,
            ),
            (
                "How The Code Landed",
                "historical_change_not_conflated_with_affected_snapshot",
                _NON_PROJECTED_HISTORICAL_REASON,
                None,
            ),
        ):
            raise ValueError("incident projection omissions differ from the frozen non-projections")
        return self

    @property
    def projection_id(self) -> str:
        return stable_id("code_incident_projection", self)


def _parse_payload(payload: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise IncidentProjectionError("incident source payload is not valid JSON") from exc
    if not isinstance(value, dict):
        raise IncidentProjectionError("incident source payload must be one object")
    return value


def _require_qualified_fixture(fixture: PublicIncidentFixtureV1Alpha1) -> None:
    if fixture.title != _INCIDENT_TITLE:
        raise IncidentProjectionError("incident title is not the frozen source title")
    report = fixture.report
    expected_report = (
        _REPORT_REPOSITORY,
        _REPORT_COMMIT,
        _REPORT_PATH,
        _REPORT_BLOB,
        _REPORT_DIGEST,
        _REPORT_BYTE_COUNT,
        _REPORT_RAW_URI,
        _REPORT_URI,
        _REPORT_PUBLISHED_URI,
    )
    actual_report = (
        report.repository_url,
        report.repository_commit,
        report.repository_path,
        report.git_blob_sha,
        report.content_sha256,
        report.byte_count,
        report.raw_url,
        report.immutable_url,
        report.published_url,
    )
    if actual_report != expected_report:
        raise IncidentProjectionError("incident report revision, path, blob, URI, or digest is not qualified")
    if report.published_at.isoformat() != "2020-05-21T17:02:51.487000+00:00":
        raise IncidentProjectionError("incident report publication clock is not qualified")

    if tuple(
        (
            item.scope,
            item.spdx_id,
            item.immutable_url,
            item.raw_url,
            item.git_blob_sha,
            item.byte_count,
            item.content_sha256,
            item.copyright_notice,
        )
        for item in fixture.licenses
    ) != (
        (
            "report",
            "MIT",
            f"https://github.com/keep-network/tbtc-website/blob/{_REPORT_COMMIT}/LICENSE",
            f"https://raw.githubusercontent.com/keep-network/tbtc-website/{_REPORT_COMMIT}/LICENSE",
            "4ed19fdb338ca18942ed904d47e5c377103e45eb",
            1_054,
            "sha256:be587dab2304aa7efbf8807c30107fbe74f17a772a563233b2d9fd1fb05503fd",
            "Copyright (c) 2020 Keep SEZC.",
        ),
        (
            "code",
            "MIT",
            f"https://github.com/keep-network/tbtc/blob/{_CODE_REVISION}/LICENSE",
            f"https://raw.githubusercontent.com/keep-network/tbtc/{_CODE_REVISION}/LICENSE",
            "80a1ed24975b0263f29157a7bc788d9e30ab2adf",
            1_053,
            "sha256:59f67a2ea030f1fcbfd4f5ffd0aae8b65f66954e5aa0fdd5b745c4ac9eba6fb9",
            "Copyright (c) 2020 Keep SEZC.",
        ),
    ):
        raise IncidentProjectionError("incident fixture license anchors are not qualified")

    actual_clocks = tuple((item.label, item.occurred_at.isoformat(), item.source_line) for item in fixture.clocks)
    if actual_clocks != _EXPECTED_CLOCKS:
        raise IncidentProjectionError("incident fixture clocks differ from verified UTC source clocks")

    sections = {item.section_id: item for item in fixture.sections}
    if set(sections) != {"incident-timeline", "technical-issue-code-coordinate"}:
        raise IncidentProjectionError("incident fixture sections conflict with the bounded acceptance source")
    timeline = sections["incident-timeline"]
    positive = sections["technical-issue-code-coordinate"]
    if (
        timeline.kind,
        timeline.source_line_start,
        timeline.source_line_end,
        timeline.excerpt_sha256,
        timeline.code_coordinate,
    ) != (
        "timeline_only",
        21,
        39,
        _TIMELINE_DIGEST,
        None,
    ):
        raise IncidentProjectionError("timeline-only negative section is not the verified source span")
    coordinate = positive.code_coordinate
    assert coordinate is not None
    expected_coordinate = (
        "affected_code_snapshot",
        _CODE_REPOSITORY,
        _CODE_REVISION,
        _CODE_PATH,
        _CODE_SYMBOL,
        326,
        355,
        _CODE_BLOB,
        _CODE_DIGEST,
        _CODE_BYTE_COUNT,
        _CODE_RAW_URI,
        _CODE_URI,
        _CODE_EXCERPT_DIGEST,
    )
    actual_coordinate = (
        coordinate.relation,
        coordinate.repository_url,
        coordinate.revision,
        coordinate.path,
        coordinate.symbol,
        coordinate.line_start,
        coordinate.line_end,
        coordinate.git_blob_sha,
        coordinate.file_sha256,
        coordinate.byte_count,
        coordinate.raw_url,
        coordinate.immutable_url,
        coordinate.excerpt_sha256,
    )
    if (positive.kind, positive.source_line_start, positive.source_line_end, positive.excerpt_sha256) != (
        "source_declared_code_coordinate",
        45,
        45,
        _DECLARATION_DIGEST,
    ) or actual_coordinate != expected_coordinate:
        raise IncidentProjectionError("source-declared code coordinate is not the verified affected snapshot")

    context = fixture.non_projected_context
    if (
        context.revision != _NON_PROJECTED_HISTORICAL_REVISION
        or context.immutable_url != f"{_CODE_REPOSITORY}/commit/{_NON_PROJECTED_HISTORICAL_REVISION}"
        or context.report_label != "How The Code Landed"
        or context.projected is not False
        or context.reason != _NON_PROJECTED_HISTORICAL_REASON
    ):
        raise IncidentProjectionError("historical change exclusion is not the verified non-projection")


def project_public_incident_to_code(
    source: IncidentSourceEnvelopeV1Alpha1,
) -> IncidentToCodeProjectionV1Alpha1:
    """Project the one qualified public incident without inference or authority."""

    try:
        source = IncidentSourceEnvelopeV1Alpha1.model_validate(source.model_dump(mode="json"))
        fixture = PublicIncidentFixtureV1Alpha1.model_validate(_parse_payload(source.captured_payload_json))
    except (AttributeError, TypeError, ValidationError, ValueError) as exc:
        if isinstance(exc, IncidentProjectionError):
            raise
        raise IncidentProjectionError(f"incident fixture failed closed: {exc}") from exc
    _require_qualified_fixture(fixture)
    if source.source_uri != fixture.report.immutable_url:
        raise IncidentProjectionError("host source URI differs from the qualified report")
    if source.source_published_at != fixture.report.published_at:
        raise IncidentProjectionError("host publication clock differs from the qualified report")

    timeline = next(item for item in fixture.sections if item.section_id == "incident-timeline")
    positive = next(item for item in fixture.sections if item.section_id == "technical-issue-code-coordinate")
    coordinate = positive.code_coordinate
    assert coordinate is not None

    incident_id = stable_id(
        "code_incident",
        {
            "fixture_key": fixture.fixture_key,
            "report_commit": fixture.report.repository_commit,
            "report_digest": fixture.report.content_sha256,
        },
    )
    positive_evidence = IncidentProjectionEvidenceV1Alpha1(
        evidence_id=positive.evidence_id,
        kind="report_section",
        immutable_uri=f"{fixture.report.immutable_url}#L{positive.source_line_start}",
        content_digest=positive.excerpt_sha256,
        line_start=positive.source_line_start,
        line_end=positive.source_line_end,
        source_snapshot_ref=source.source_snapshot_ref,
        source_snapshot_digest=source.source_snapshot_digest,
    )
    code_evidence = IncidentProjectionEvidenceV1Alpha1(
        evidence_id=stable_id("code_incident_evidence", coordinate.model_dump(exclude={"excerpt"})),
        kind="code_coordinate",
        immutable_uri=coordinate.immutable_url,
        content_digest=coordinate.excerpt_sha256,
        artifact_digest=coordinate.file_sha256,
        line_start=coordinate.line_start,
        line_end=coordinate.line_end,
        source_snapshot_ref=source.source_snapshot_ref,
        source_snapshot_digest=source.source_snapshot_digest,
    )
    timeline_evidence = IncidentProjectionEvidenceV1Alpha1(
        evidence_id=timeline.evidence_id,
        kind="report_section",
        immutable_uri=f"{fixture.report.immutable_url}#L{timeline.source_line_start}-L{timeline.source_line_end}",
        content_digest=timeline.excerpt_sha256,
        line_start=timeline.source_line_start,
        line_end=timeline.source_line_end,
        source_snapshot_ref=source.source_snapshot_ref,
        source_snapshot_digest=source.source_snapshot_digest,
    )
    relation = IncidentCodeRelationV1Alpha1(
        relation_id=stable_id(
            "code_incident_relation",
            {
                "source": incident_id,
                "target": coordinate.coordinate_id,
                "relation": coordinate.relation,
                "evidence": (positive_evidence.evidence_id, code_evidence.evidence_id),
            },
        ),
        source_incident_id=incident_id,
        target_coordinate_id=coordinate.coordinate_id,
        relation=coordinate.relation,
        evidence_refs=(positive_evidence.evidence_id, code_evidence.evidence_id),
    )
    return IncidentToCodeProjectionV1Alpha1(
        incident=IncidentProjectionRecordV1Alpha1(
            incident_id=incident_id,
            fixture_key=fixture.fixture_key,
            title=fixture.title,
            report_uri=fixture.report.immutable_url,
            report_commit=fixture.report.repository_commit,
            report_blob_sha=fixture.report.git_blob_sha,
            report_content_digest=fixture.report.content_sha256,
            clocks=fixture.clocks,
        ),
        code_coordinates=(coordinate,),
        relations=(relation,),
        evidence=(positive_evidence, code_evidence, timeline_evidence),
        license_anchors=fixture.licenses,
        omissions=(
            IncidentProjectionOmissionV1Alpha1(
                section_id=timeline.section_id,
                reason="no_source_declared_code_coordinate",
                detail=_TIMELINE_OMISSION_DETAIL,
                evidence_ref=timeline_evidence.evidence_id,
            ),
            IncidentProjectionOmissionV1Alpha1(
                section_id=fixture.non_projected_context.report_label,
                reason="historical_change_not_conflated_with_affected_snapshot",
                detail=fixture.non_projected_context.reason,
            ),
        ),
        source_snapshot_ref=source.source_snapshot_ref,
        source_snapshot_digest=source.source_snapshot_digest,
        acquisition_receipt_ref=source.acquisition_receipt_ref,
        acquisition_receipt_digest=source.acquisition_receipt_digest,
        source_acquisition_mode=source.acquisition_mode,
    )


def validate_incident_projection_against_source(
    projection: IncidentToCodeProjectionV1Alpha1,
    source: IncidentSourceEnvelopeV1Alpha1,
) -> IncidentToCodeProjectionV1Alpha1:
    """Revalidate a serialized projection against its strict canonical source envelope."""

    try:
        projection = IncidentToCodeProjectionV1Alpha1.model_validate(projection.model_dump(mode="json"))
        source = IncidentSourceEnvelopeV1Alpha1.model_validate(source.model_dump(mode="json"))
    except (AttributeError, TypeError, ValidationError, ValueError) as exc:
        raise IncidentProjectionError(f"incident projection/source revalidation failed closed: {exc}") from exc
    if (
        projection.source_snapshot_ref != source.source_snapshot_ref
        or projection.source_snapshot_digest != source.source_snapshot_digest
        or projection.acquisition_receipt_ref != source.acquisition_receipt_ref
        or projection.acquisition_receipt_digest != source.acquisition_receipt_digest
        or source.captured_payload_digest != _FIXTURE_PAYLOAD_DIGEST
    ):
        raise IncidentProjectionError("incident projection provenance does not match the canonical source envelope")
    return projection


__all__ = [
    "IncidentProjectionError",
    "IncidentSourceEnvelopeV1Alpha1",
    "IncidentToCodeProjectionV1Alpha1",
    "PublicIncidentFixtureV1Alpha1",
    "project_public_incident_to_code",
    "validate_incident_projection_against_source",
]
