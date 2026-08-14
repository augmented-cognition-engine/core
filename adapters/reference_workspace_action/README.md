# ACE reference workspace action adapter

This is a separately buildable example of a trusted ACE action adapter. It implements only the
public `ace.core.action-adapter/v1alpha1` contract and deliberately imports no `core.engine` host
module.

The adapter supports one action: `create_workspace_export`. The host supplies an existing workspace
root. The request names one relative path and bounded UTF-8 content. Preparation is effect-free;
execution creates a new file with exclusive-create semantics. Existing files, symlinks, missing
parent directories, absolute paths, traversal, and paths outside the workspace fail closed.

This package is not included in the `ace-core` wheel and is not dynamically discovered. A host must
install it, construct it, and register its exact artifact identity explicitly. The ACE release
workflow builds it independently and attaches its wheel and source distribution to the matching
GitHub Release; only the Core distribution is sent to PyPI.

Distribution 0.4.1 targets `ace-core>=0.8.0,<1.1`. The executable implementation is unchanged from
0.1.0, so its public capability artifact identity remains 0.1.0 rather than manufacturing a new
implementation identity for dependency metadata alone. Installation grants no execution authority;
the host must still register and authorize the exact adapter and operation.
