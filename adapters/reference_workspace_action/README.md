# ACE reference workspace action adapter

This is a separately buildable example of a trusted ACE action adapter. It implements only the
public `ace.core.action-adapter/v1alpha1` contract and deliberately imports no `core.engine` host
module.

The adapter supports one action: `create_workspace_export`. The host supplies an existing workspace
root. The request names one relative path and bounded UTF-8 content. Preparation is effect-free;
execution creates a new file with exclusive-create semantics. Existing files, symlinks, missing
parent directories, absolute paths, traversal, and paths outside the workspace fail closed.

This package is not included in the `ace-core` wheel and is not dynamically discovered. A host must
install it, construct it, and register its exact artifact identity explicitly.

The dependency begins at `ace-core>=0.5.0`; until that release exists, candidate conformance installs
the locally built Core wheel first and installs this wheel without dependency resolution.
