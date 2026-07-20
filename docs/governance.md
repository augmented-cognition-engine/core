# Governance and support

ACE is an open-source project created and led by Edwin Amirian, with QueryLabs as its founding
sponsor. The lead maintainer is responsible for product direction, stable contracts, security
releases, and maintainer appointments.

Issues and pull requests receive best-effort community support; the developer preview has no
service-level agreement. Security reports follow [`SECURITY.md`](../SECURITY.md), and community
participation follows the [`CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md).

Small, reversible changes use normal review. Changes to public contracts, persistence schemas,
security boundaries, licensing, or project direction should begin with a proposal that explains
the problem, alternatives, compatibility impact, evidence, and rollback.

During 0.1.x, ACE aims to keep the thin eleven-tool MCP contract, CLI golden path, extension
entry-point group, and documented stable registry calls compatible. Experimental surfaces may
change in a minor release; migration notes will be provided when practical.

Maintainers are added after sustained contributions and sound review judgment. Contributions are
accepted under Apache-2.0 as described in [`CONTRIBUTING.md`](../CONTRIBUTING.md). Contributors
retain copyright in their contributions and license them to the project under Apache-2.0.
