# B1C independent action adapter work packet (v1)

Status: **active candidate for ACE 0.5.0; does not complete T1 or B1**

Date: 2026-08-10

## Outcome

Prove that the B1 public action contract can carry one real, bounded effect through a separately
installable trusted adapter without putting a product tool, dynamic discovery, or Domain Pack code
inside the Core wheel.

## Frozen boundary

The reference distribution is `ace-reference-workspace-action`. It depends only on the public
`ace.core.action-adapter/v1alpha1` contract and implements one action:
`create_workspace_export`.

The application supplies an existing non-symlink workspace root and explicitly constructs and
registers the adapter by its complete immutable artifact identity. The request contains exactly a
canonical relative path and bounded UTF-8 content. Preparation resolves the target and produces an
effect-free plan. Execution creates one previously absent file with exclusive-create semantics.

The adapter:

- cannot overwrite, append, delete, rename, execute commands, access the network, discover a
  workspace, or select another capability;
- refuses absolute paths, traversal, missing or symlinked parent directories, existing targets,
  duplicate JSON keys, extra parameters, and content over 128,000 UTF-8 bytes;
- opens each parent relative to an already approved directory descriptor with no-follow semantics,
  then exclusively creates the final file with mode `0600`; and
- reports a confirmed effect only after the complete content is written and synchronized.

If the target changes before creation, the adapter returns `failed/effect_none`. If an error occurs
after exclusive creation, it escapes to Core, which records the effect as unknown rather than
inventing success or safe retry.

## Packaging and trust

This repository carries the adapter source as a separately buildable reference distribution under
`adapters/reference_workspace_action/`; the root `ace-core` package configuration does not include
its import package. The adapter imports `ace.core` only. It does not import `core.engine`,
`ace.intelligence`, an extension loader, or host persistence.

This is trusted in-process code, not inert Domain Pack configuration and not safe execution of
untrusted plugins. Core performs no dynamic package discovery. Installation alone grants no
authority: a host must construct the adapter, register the exact identity, bind it to a governed
operation, and supply Core's authorizer and immutable store.

## Acceptance

- adapter conformance covers effect-free preparation, exact create, changed-target refusal,
  symlink-swap refusal, traversal and absolute-path refusal, and public-import boundaries;
- ordinary Core tests execute that separately rooted conformance suite and prove exact explicit
  host registration;
- Core and adapter wheels build independently; the adapter package is absent from the Core wheel;
- a clean environment installs both wheels and creates the expected file from outside the source
  tree; and
- focused verification, full non-e2e regression, naked-kernel checks, lint, formatting, package
  inspection, and documentation integrity pass.

## Non-claims and next boundary

B1C does not provide arbitrary filesystem writes, dynamic discovery, an HTTP action API,
cross-process locking, distributed exactly-once effects, compensation, remote/container execution,
safe untrusted code, or a released artifact. It does not make adapter effects a Domain Pack
capability and does not complete T1 or B1.

The next B1 packet must make action inspection, human review, repair, and promotion explicit. T1
still requires its portability and topology closeout before ACE 0.5.0 can pass.
