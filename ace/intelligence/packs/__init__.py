"""Pure Domain Pack compilation and activation preparation."""

from ace.intelligence.packs.activation import (
    compile_overlay,
    prepare_activation_revision,
    prepare_domain_activation,
)
from ace.intelligence.packs.bundle_activation import (
    SolutionBundleResolutionError,
    preview_solution_bundle_activation,
    resolve_solution_bundle,
)
from ace.intelligence.packs.compiler import (
    CompiledPackResultV1,
    PackCompilationError,
    compile_pack,
    compile_pack_document,
    compile_pack_document_with_report,
    negotiate_pack_compatibility,
    validate_compiled_pack_set,
)
from ace.intelligence.packs.diagnostics import (
    PackCompatibilityResultV1,
    PackCompatibilityStatus,
    StablePackCompilationResultV1,
)
from ace.intelligence.packs.runtime import (
    PreparedActivationBinding,
    PreparedActivationBindingError,
    ResolvedSourceMappingPolicy,
    bind_prepared_activation,
    resolve_source_mapping_policy,
    resolve_source_mapping_rule,
)

__all__ = [
    "PackCompilationError",
    "CompiledPackResultV1",
    "PackCompatibilityResultV1",
    "PackCompatibilityStatus",
    "StablePackCompilationResultV1",
    "PreparedActivationBinding",
    "PreparedActivationBindingError",
    "ResolvedSourceMappingPolicy",
    "bind_prepared_activation",
    "compile_overlay",
    "compile_pack",
    "compile_pack_document",
    "compile_pack_document_with_report",
    "prepare_activation_revision",
    "prepare_domain_activation",
    "negotiate_pack_compatibility",
    "validate_compiled_pack_set",
    "resolve_source_mapping_rule",
    "resolve_source_mapping_policy",
    "preview_solution_bundle_activation",
    "SolutionBundleResolutionError",
    "resolve_solution_bundle",
]
