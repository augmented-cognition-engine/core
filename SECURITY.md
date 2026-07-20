# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in ACE, please **do not file a public GitHub issue**. Public disclosure before a fix is shipped puts adopters at risk.

Before sending logs, screenshots, configuration, fixtures, or graph exports, redact API keys,
bearer tokens, repository secrets, database credentials, provider credentials, proprietary code,
client names, and private graph contents. Replace values with descriptive placeholders; never
paste an `.env` file.

## Private reporting route

Use the repository's **Security → Report a vulnerability** route when it is available.

If that private route is unavailable, open a minimal public issue titled **Security contact
request**. Do not include vulnerability details, logs, reproduction steps, client information, or
other sensitive material in the issue. A maintainer will establish a private channel before asking
for the report.

Include in the private report:

- A description of the vulnerability and its potential impact
- Steps to reproduce (proof-of-concept code if applicable)
- Affected components (kernel, reference UI, a specific extension)
- Your suggested remediation if you have one
- Whether you'd like public credit when the fix ships

## Response

- **Best-effort acknowledgement and assessment** — the developer preview has no response SLA
- **Fix or mitigation** timing depends on severity — critical vulnerabilities are prioritized over feature work
- **Coordinated disclosure** — we'll coordinate with you on a public-disclosure timeline, typically aligned with the fix's release

## Scope

This policy covers:

- The ACE kernel (`core/engine/`)
- Atrium (`core/ui/canvas/`), where the issue is in repository-owned code
- The reference extension (`extensions/reference/`)
- The thin MCP package (`ace_mcp_client/`)

Private and third-party extensions are owned by their respective maintainers; security issues in those should be reported to those owners.

## What's in scope as a vulnerability

- Authentication or authorization bypass
- Injection vulnerabilities (SQL, command, prompt injection in the LLM pipeline)
- Data exposure beyond intended boundaries (cross-extension, cross-tenant, cross-session)
- Denial of service against the engine or shared infrastructure
- Supply chain risks (dependency compromise, build-time injection)
- Information leakage through error messages or telemetry

## Out of scope

- Issues in third-party dependencies — please report those upstream
- Issues that require physical access or already-compromised credentials
- Social engineering or phishing
- Theoretical issues without a demonstrated impact path
