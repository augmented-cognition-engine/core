"""ACE extensions — the extension layer.

An *extension* is a domain configuration (personas, frameworks, recipes, instruments,
tools, schema) built on the ACE kernel without forking it. The kernel ships empty
of extension specifics; extensions self-register on load.

Public surface:
- ``Extension``      — the contract an extension implements
- ``Registry``    — the facade an extension registers through
- ``load_extensions``— discover + register all installed/declared extensions
"""

from core.engine.extensions.base import Extension
from core.engine.extensions.conformance import run_task_action_conformance
from core.engine.extensions.invocation import (
    ContextResolution,
    ExtensionActorContext,
    ExtensionArtifactProvenance,
    ExtensionCapabilityManifest,
    ExtensionInvocationEnvelope,
    ExtensionInvocationReceipt,
    ExtensionOutcome,
    ExtensionReference,
    ExtensionTaskPlan,
    RegisteredTaskAction,
    ResolvedContextRecord,
)
from core.engine.extensions.loader import load_extensions, loaded_extensions
from core.engine.extensions.registry import Registry

__all__ = [
    "ContextResolution",
    "Extension",
    "ExtensionActorContext",
    "ExtensionArtifactProvenance",
    "ExtensionCapabilityManifest",
    "ExtensionInvocationEnvelope",
    "ExtensionInvocationReceipt",
    "ExtensionOutcome",
    "ExtensionReference",
    "ExtensionTaskPlan",
    "RegisteredTaskAction",
    "ResolvedContextRecord",
    "Registry",
    "load_extensions",
    "loaded_extensions",
    "run_task_action_conformance",
]
