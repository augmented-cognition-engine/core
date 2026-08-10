# ACE reference workspace action adapter

This is a separately buildable example of a trusted ACE action adapter. It implements only the
public `ace.core.action-adapter/v1alpha1` contract and deliberately imports no `core.engine` host
module.

The adapter supports one action: `create_workspace_export`. The host supplies an existing workspace
root. The request names one relative path and bounded UTF-8 content. Preparation is effect-free;
execution creates a new file with exclusive-create semantics. Existing files, symlinks, missing
parent directories, absolute paths, traversal, and paths outside the workspace fail closed.

This package is not included in the `ace-core` wheel and is not dynamically discovered. A host must
install it, construct it, and register its exact artifact identity explicitly. The ACE 0.5.0
release workflow builds it independently and attaches its wheel and source distribution to the
matching GitHub Release; only the Core distribution is sent to PyPI.

The dependency begins at `ace-core>=0.5.0,<0.6`. Install `ace-core==0.5.0` from PyPI and the adapter
wheel from the public [`v0.5.0` GitHub Release](https://github.com/augmented-cognition-engine/core/releases/tag/v0.5.0).
