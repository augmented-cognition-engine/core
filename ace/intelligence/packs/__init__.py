"""Pure Domain Pack compilation and activation preparation."""

from ace.intelligence.packs.activation import (
    compile_overlay,
    prepare_activation_revision,
    prepare_domain_activation,
)
from ace.intelligence.packs.compiler import PackCompilationError, compile_pack, compile_pack_document
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
    "PreparedActivationBinding",
    "PreparedActivationBindingError",
    "ResolvedSourceMappingPolicy",
    "bind_prepared_activation",
    "compile_overlay",
    "compile_pack",
    "compile_pack_document",
    "prepare_activation_revision",
    "prepare_domain_activation",
    "resolve_source_mapping_rule",
    "resolve_source_mapping_policy",
]
