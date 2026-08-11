# ACE reference workspace action adapter

This is a separately buildable example of a trusted ACE action adapter. It implements only the
public `ace.core.action-adapter/v1alpha1` contract and deliberately imports no `core.engine` host
module.

The adapter supports one action: `create_workspace_export`. The host supplies an existing workspace
root. The request names one relative path and bounded UTF-8 content. Preparation is effect-free;
execution creates a new file with exclusive-create semantics. Existing files, symlinks, missing
parent directories, absolute paths, traversal, and paths outside the workspace fail closed.

This package is not included in the `ace-core` wheel and is not dynamically discovered. A host must
install it, construct it, and register its exact artifact identity explicitly. The ACE 0.6.0
release-candidate workflow builds it independently and would attach its wheel and source
distribution to a separately authorized matching GitHub Release; only the Core distribution would
be sent to PyPI.

Distribution 0.2.0 targets `ace-core>=0.6.0,<0.7`. The executable implementation is unchanged from
0.1.0, so its public capability artifact identity remains 0.1.0 rather than manufacturing a new
implementation identity for dependency metadata alone. The 0.2.0 archives remain unpublished
candidate artifacts until the separate release gate passes.
