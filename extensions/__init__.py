"""Extensions namespace.

Vertical specializations on top of ACE core. Each extension is a Python
package that registers itself with the engine via the
``ace.extensions`` entry point in pyproject.toml. See ``extensions/README.md``
for the contract every extension follows.

Built-in extensions:
  - ``extensions.reference`` — canonical worked example a contributor copies
                                to start their own domain extension

Private extensions may be installed alongside; the kernel discovers them
through the same entry point and never needs to name them.
"""
