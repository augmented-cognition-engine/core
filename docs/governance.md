# Governance and support

ACE is an open-source project created and led by Edwin Amirian, with QueryLabs as its founding
sponsor. The lead maintainer is responsible for product direction, stable contracts, security
releases, and maintainer appointments.

Issues and pull requests receive best-effort community support; the open-source project has no
service-level agreement. Security reports follow [`SECURITY.md`](../SECURITY.md), and community
participation follows the [`CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md).

Small, reversible changes use normal review. Changes to public contracts, persistence schemas,
security boundaries, licensing, or project direction should begin with a proposal that explains
the problem, alternatives, compatibility impact, evidence, and rollback.

During the 1.0 compatibility line, ACE keeps the thin eleven-tool MCP contract, documented CLI and
Intelligence Builder journey, public `ace.*` contract families, extension entry-point group, and
documented stable registry calls compatible. Incompatible public-contract changes require a new
contract identity plus migration and deprecation guidance. Experimental surfaces remain explicitly
labeled and may change outside that stable boundary.

Code Intelligence improvement follows the
[three-loop governance contract](design/governed-code-improvement-loop-v1.md). Completing current
work, proposing a reusable architecture change, and changing future agent or procedure behavior
require separate evidence and authority. ACE operating on its own repository never grants it
approval, merge, release, deployment, policy, or promotion authority.

Maintainers are added after sustained contributions and sound review judgment. Contributions are
accepted under Apache-2.0 as described in [`CONTRIBUTING.md`](../CONTRIBUTING.md). Contributors
retain copyright in their contributions and license them to the project under Apache-2.0.
