"""PI13 WS0 deterministic structured provider, reachable only through production binding.

The WS0 journey gate must exercise the Builder strategies and the governed
first-Brief reasoning exactly the way an installed ACE does: the runtime
selects its provider through ``get_llm()``. This module therefore never
injects a provider object; it serves the OpenAI chat-completions wire shape
on a loopback port so the gate can point ``OPENAI_COMPAT_BASE_URL`` at it and
let ``OpenAICompatProvider`` -- the production adapter -- carry every call.

Responses are pure, deterministic functions of the prompt: every citation,
identifier, and support reference is copied from the trusted context the host
placed in the prompt, so the stub can never introduce material the host did not
already admit. It performs no network access and holds no state.
"""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

STUB_MODEL_ID = "pi13-ws0-deterministic-stub"
BRIEF_DRAFT_CONTRACT = "ace.intelligence.brief-synthesis-draft/v1alpha1"
_EXCLUSION = "No source credentials, connector configuration, monitoring policy, or activation authority."
_SLUG_CLEAN = re.compile(r"[^a-z0-9]+")


def attribute_id_for_field(field_path: str) -> str:
    """Deterministic, slug-safe attribute id for one JSON-pointer field path."""

    cleaned = _SLUG_CLEAN.sub("_", field_path.lower()).strip("_")
    return f"field_{cleaned}" if cleaned else "field_root"


def extract_prompt(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Recover the canonical JSON prompt the host placed in the last user message."""

    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        if not isinstance(content, str):
            continue
        start = content.find("{")
        if start < 0:
            continue
        parsed, _ = json.JSONDecoder().raw_decode(content[start:])
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("no JSON prompt found in chat messages")


# --- Builder strategy stages -------------------------------------------------


def _concept_response(parsed: dict[str, Any]) -> dict[str, Any]:
    source_profile = parsed["trusted_context"]["source_profile"]
    citations: list[dict[str, str]] = []
    by_field: dict[str, list[str]] = {}
    value_kinds: dict[str, str] = {}
    for sample_index, sample in enumerate(source_profile["samples"]):
        for field in sample["fields"]:
            citation_id = f"concept_{sample_index}_{attribute_id_for_field(field['field_path'])}"
            citations.append(
                {
                    "citation_id": citation_id,
                    "source_sample_id": sample["sample_id"],
                    "field_path": field["field_path"],
                }
            )
            by_field.setdefault(field["field_path"], []).append(citation_id)
            value_kinds.setdefault(field["field_path"], field.get("value_kind", "string"))
    attributes = [
        {
            "attribute_id": attribute_id_for_field(field_path),
            "display_name": field_path.strip("/").replace("/", " ").replace("_", " ").title() or "Root",
            "value_kind": value_kinds[field_path] if value_kinds[field_path] != "unknown" else "string",
            "required": False,
            "citation_ids": citation_ids,
            "confidence": 0.9,
        }
        for field_path, citation_ids in sorted(by_field.items())
    ]
    return {
        "citations": citations,
        "entity_types": [
            {
                "type_id": "note",
                "display_name": "Note",
                "definition": "One admitted local source unit whose captured fields can be compared over time.",
                "aliases": ["source unit"],
                "attributes": attributes,
                "citation_ids": [item["citation_id"] for item in citations],
                "confidence": 0.9,
            }
        ],
        "relationship_types": [],
        "terminology": [],
        "exclusions": [_EXCLUSION],
        "conflicts": [],
        "unknowns": [],
        "confidence": 0.9,
    }


def _intelligence_response(parsed: dict[str, Any]) -> dict[str, Any]:
    context = parsed["trusted_context"]
    observations = context["observations"]["observations"]
    entity_type = context["concept_model"]["entity_types"][0]
    declared = {item["attribute_id"] for item in entity_type["attributes"]}
    citations: list[dict[str, str]] = []
    by_attribute: dict[str, list[str]] = {}
    baseline_values: dict[str, tuple[str, str]] = {}
    for observation_index, observation in enumerate(observations):
        attributes = json.loads(observation["attributes"]["value_json"])
        for key in sorted(attributes):
            field_path = f"/{key}"
            attribute_id = attribute_id_for_field(field_path)
            if attribute_id not in declared:
                continue
            citation_id = f"obs_{observation_index}_{attribute_id}"
            citations.append(
                {"citation_id": citation_id, "observation_id": observation["observation_id"], "field_path": field_path}
            )
            by_attribute.setdefault(attribute_id, []).append(citation_id)
            baseline_values.setdefault(
                attribute_id,
                (json.dumps(attributes[key], sort_keys=True, separators=(",", ":")), observation["as_of"]),
            )
    if not citations:
        raise ValueError("no admitted observation field matches a declared concept attribute")
    target_ids = [f"watch_{attribute_id}" for attribute_id in sorted(by_attribute)]
    all_citation_ids = [item["citation_id"] for item in citations]
    watch_targets = [
        {
            "target_id": f"watch_{attribute_id}",
            "target_kind": "attribute",
            "entity_type_id": entity_type["type_id"],
            "member_id": attribute_id,
            "citation_ids": citation_ids,
        }
        for attribute_id, citation_ids in sorted(by_attribute.items())
    ]
    baselines = [
        {
            "baseline_id": f"baseline_{attribute_id}",
            "target_id": f"watch_{attribute_id}",
            "value": {"value_json": baseline_values[attribute_id][0]},
            "as_of": baseline_values[attribute_id][1],
            "citation_ids": by_attribute[attribute_id],
        }
        for attribute_id in sorted(by_attribute)
    ]
    detectors = [
        {
            "detector_id": f"detector_{attribute_id}",
            "target_id": f"watch_{attribute_id}",
            "strategy": "categorical_transition",
            "configuration": {"value_json": json.dumps({"field": attribute_id}, separators=(",", ":"))},
            "citation_ids": by_attribute[attribute_id],
        }
        for attribute_id in sorted(by_attribute)
    ]
    materiality_rules = [
        {
            "rule_id": f"materiality_{attribute_id}",
            "detector_id": f"detector_{attribute_id}",
            "minimum_change": 1.0,
            "minimum_confidence": 0.5,
            "rationale": "Any transition of an admitted source field is material to the owner's orientation.",
            "citation_ids": by_attribute[attribute_id],
        }
        for attribute_id in sorted(by_attribute)
    ]
    statements = []
    for index, classification in enumerate(("observation", "claim", "inference", "disagreement", "unknown")):
        statements.append(
            {
                "statement_id": f"statement_{classification}",
                "classification": classification,
                "statement": f"A bounded {classification} statement over the admitted local source evidence.",
                "citation_ids": (
                    all_citation_ids
                    if classification == "disagreement"
                    else [all_citation_ids[index % len(all_citation_ids)]]
                ),
                "confidence": 0.9,
            }
        )
    return {
        "citations": citations,
        "watch_targets": watch_targets,
        "baselines": baselines,
        "detectors": detectors,
        "materiality_rules": materiality_rules,
        "audiences": [
            {
                "audience_id": "local_owner",
                "display_name": "Local Owner",
                "purpose": "The local Intelligence owner reviewing their own admitted material.",
            }
        ],
        "routes": [
            {
                "route_id": "owner_daily",
                "audience_ids": ["local_owner"],
                "target_ids": target_ids,
                "cadence": "daily",
                "minimum_confidence": 0.5,
            }
        ],
        "suppression_grouping_rules": [
            {
                "rule_id": "group_owner_updates",
                "target_ids": target_ids,
                "suppress_below_confidence": 0.3,
                "rationale": "Group related field updates and suppress only explicitly low-confidence items.",
            }
        ],
        "epistemic_statements": statements,
        "conflicts": [],
        "unknowns": ["No unknowns beyond the bounded admitted evidence closure."],
        "exclusions": [_EXCLUSION],
        "confidence": 0.9,
    }


_ITEM_KIND_BY_CLASSIFICATION = {
    "observation": "current_state",
    "claim": "signal",
    "inference": "shift",
    "disagreement": "disagreement",
    "unknown": "unknown",
}


def _briefing_response(parsed: dict[str, Any]) -> dict[str, Any]:
    intelligence_model = parsed["trusted_context"]["intelligence_model"]
    materiality_rule_id = intelligence_model["materiality_rules"][0]["rule_id"]
    items = []
    for statement in intelligence_model["epistemic_statements"]:
        classification = statement["classification"]
        item_kind = _ITEM_KIND_BY_CLASSIFICATION[classification]
        item = {
            "item_id": f"item_{classification}",
            "item_kind": item_kind,
            "title": f"A bounded {classification} item over admitted evidence.",
            "summary": f"The admitted evidence supports this {classification} item.",
            "why_it_matters": "Confirms the bounded orientation the owner requested.",
            "epistemic_classification": classification,
            "statement_ids": [statement["statement_id"]],
            "citation_ids": list(statement["citation_ids"]),
            "counterevidence_citation_ids": [],
            "confidence": 0.9,
            "uncertainty": "None beyond the cited admitted evidence.",
        }
        if item_kind in {"signal", "shift"}:
            item["materiality_rule_id"] = materiality_rule_id
        items.append(item)
    return {
        "title": "First Brief",
        "executive_summary": "A bounded first Brief over the exact admitted local source evidence.",
        "items": items,
        "freshness_statement": "As of the exact admitted evidence timestamps.",
    }


# --- Governed first-Brief reasoning stage -------------------------------------


def _brief_draft_response(parsed: dict[str, Any]) -> dict[str, Any]:
    instructions = parsed["trusted_instructions"]
    boundary = instructions["corpus_boundary"]
    observation_ids = list(boundary["observation_ids"])
    snapshot_ids = list(boundary["entity_snapshot_ids"])
    sections_required = list(instructions["required_sections"])
    persona_ids = [item["persona_id"] for item in instructions["personas"]]
    if not observation_ids:
        raise ValueError("the corpus boundary names no admitted observations")

    def cited(statement: str, refs: list[str]) -> dict[str, Any]:
        return {"statement": statement, "grounding_kind": "cited", "support_refs": refs, "confidence": 0.9}

    def inferred(statement: str, refs: list[str]) -> dict[str, Any]:
        return {
            "statement": statement,
            "grounding_kind": "inference",
            "support_refs": refs,
            "confidence": 0.6,
            "uncertainty": "An orientation inference over the admitted corpus; no source states it directly.",
        }

    claims_by_section: dict[str, list[dict[str, Any]]] = {}
    for section_id in sections_required:
        claims_by_section[section_id] = []
    first, *rest = sections_required
    claims_by_section[first].extend(
        cited(f"The admitted corpus contains the source unit recorded as {observation_id}.", [observation_id])
        for observation_id in observation_ids
    )
    if rest:
        claims_by_section[rest[0]].append(
            cited("What currently matters is exactly the material these admitted source units state.", observation_ids)
        )
    last = sections_required[-1]
    basis = snapshot_ids or observation_ids
    claims_by_section[last].append(
        inferred("Open questions remain about how these admitted entities relate beyond their captured fields.", basis)
    )
    for section_id, claims in claims_by_section.items():
        if not claims:
            claims.append(cited(f"Section {section_id} reflects the admitted corpus as captured.", observation_ids))
    return {
        "referenced_context_ids": [item["context_id"] for item in parsed.get("context_items", [])],
        "structured_result": {
            "contract": BRIEF_DRAFT_CONTRACT,
            "brief_type": instructions["brief_type"],
            "persona_ids": persona_ids,
            "sections": [
                {"section_id": section_id, "claims": claims} for section_id, claims in claims_by_section.items()
            ],
            "recommendation_claim_id": None,
        },
    }


def respond(parsed: dict[str, Any]) -> dict[str, Any]:
    """Dispatch one host prompt to its deterministic structured response."""

    stage = parsed.get("stage")
    if stage == "concept_model_proposal":
        return _concept_response(parsed)
    if stage == "intelligence_model_proposal":
        return _intelligence_response(parsed)
    if stage == "first_briefing_preview":
        return _briefing_response(parsed)
    instructions = parsed.get("trusted_instructions")
    if isinstance(instructions, dict) and instructions.get("output_contract") == BRIEF_DRAFT_CONTRACT:
        return _brief_draft_response(parsed)
    raise ValueError(f"unsupported prompt stage: {stage!r}")


# --- OpenAI chat-completions wire shape ----------------------------------------


def _chat_completion(payload: dict[str, Any]) -> dict[str, Any]:
    parsed = extract_prompt(payload.get("messages") or [])
    content = json.dumps(respond(parsed), separators=(",", ":"), sort_keys=True)
    prompt_chars = sum(len(str(message.get("content", ""))) for message in payload.get("messages") or [])
    return {
        "id": "chatcmpl-pi13-ws0-stub",
        "object": "chat.completion",
        "model": STUB_MODEL_ID,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": max(1, prompt_chars // 4),
            "completion_tokens": max(1, len(content) // 4),
            "total_tokens": max(1, prompt_chars // 4) + max(1, len(content) // 4),
        },
    }


class _Handler(BaseHTTPRequestHandler):
    server_version = "pi13-ws0-stub/1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - BaseHTTPRequestHandler signature
        return

    def _send(self, status: int, body: dict[str, Any]) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler naming
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._send(404, {"error": {"message": "unsupported path"}})
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            self._send(200, _chat_completion(payload))
        except Exception as exc:  # noqa: BLE001 - surfaced as a provider error, never silently 200
            self._send(400, {"error": {"message": f"{type(exc).__name__}: {exc}"}})


class StubProviderServer:
    """Loopback OpenAI-compatible server; ``base_url`` is ready for OPENAI_COMPAT_BASE_URL."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self._server = ThreadingHTTPServer((host, port), _Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, name="pi13-ws0-stub", daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/v1"

    def start(self) -> "StubProviderServer":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()


__all__ = [
    "BRIEF_DRAFT_CONTRACT",
    "STUB_MODEL_ID",
    "StubProviderServer",
    "attribute_id_for_field",
    "extract_prompt",
    "respond",
]
