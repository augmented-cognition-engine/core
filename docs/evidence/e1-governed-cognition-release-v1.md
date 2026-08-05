# E1 governed-cognition release evidence v1

Status: **passed**

Date: 2026-08-05

## Outcome

E1 passes for the exact ace-core 0.3.0 artifact set. ACE now has one canonical governed-cognition
model for the lifecycle:

```text
teach → propose → inspect → approve → use → measure → revise or retire
```

Stable cognition identity, immutable revisions, scoped active heads, proposals, human review,
selection/use receipts, and effectiveness observations remain distinct. Models may propose but
cannot approve, activate, roll back, expire, disable, supersede, retire, or grant execution
authority. The public thin MCP surface remains exactly eleven tools.

The pass supports explicitly trusted installed Python extensions running in process. It does not
claim sandboxing for hostile Python, distributed approval, exactly-once external effects, Level-2
resource-body loading, or beneficial real-world impact from usage alone.

## Immutable release binding

| Evidence | Exact identity |
|---|---|
| GitHub Release | [`v0.3.0`](https://github.com/augmented-cognition-engine/core/releases/tag/v0.3.0) |
| Release commit | `673870817a0d4a5e05af7f4149330acbb1012c80` |
| Reviewed Git tree | `3ee0ec3fa6c88ecd9f932d08788f7c54d9dd730e` |
| Reviewed candidate | `c56a5b2f8291faca557d1b345b51574911375d62`; identical Git tree |
| Candidate CI | [run 31017998433](https://github.com/augmented-cognition-engine/core/actions/runs/31017998433), all jobs passed |
| Trusted publication | [run 31018989609](https://github.com/augmented-cognition-engine/core/actions/runs/31018989609), passed |
| PyPI project | [`ace-core==0.3.0`](https://pypi.org/project/ace-core/0.3.0/) |
| Exact release matrix receipt SHA-256 | `1a1a2efa46eaf57ac3f36ce51b1eadb1843f692f4e9a842051a48afccfac7775` |
| Publication receipt | [public machine-readable record](https://github.com/augmented-cognition-engine/core/pull/44#issuecomment-5193688535), SHA-256 `68dad95a6344cd7c763644282eb0cb4910093b9d68eb33cef1bb6e69fbbf02c2` |

The complete matrix at the immutable release commit passed current-Core/N-1-reference adaptation,
N-1-Core/current-reference refusal before mutation, both independent-consumer wheel/source-mix
directions, naked-kernel boot, and package exclusions.

The published wheel SHA-256 is
`c60e49c97a5e5cb4eb8615f03720d88b1c2020f67f4d5ef9f9dffbd8ad2d1dbd`; the source-distribution
SHA-256 is `a9ab2a589adb983a85dc81c154c73aba79c0ecaba0985697547d518e9385c1c6`.
Both downloaded PyPI files byte-match their exact-release matrix artifacts. A fresh public-index
environment verified package/thin-client version 0.3.0, schema head 171, all eleven MCP tools, and
zero extensions under the naked configuration.

The pre-merge candidate matrix used the candidate commit timestamp and therefore produced different
archive hashes after the identical tree was squash-merged. Registry verification caught this before
closeout. The matrix was rerun in full at the tagged release commit; a member-by-member comparison
proved identical payloads and timestamp-only archive differences. The correction is retained in the
[publication review addendum](https://github.com/augmented-cognition-engine/core/pull/44#issuecomment-5193671117).

## Independent security review

A fresh Anthropic Claude Fable 5 invocation outside the implementation workstream received the
frozen 51-file surface and release receipts. It ran with read-only `Read`, `Glob`, and `Grep`, no
session persistence, no author-review record, and no web or command execution. It independently
accepted all 14 required boundaries and found no critical, high, or medium issue.

| Record | Identity |
|---|---|
| Independent review | [Claude Fable 5 review](https://github.com/augmented-cognition-engine/core/pull/44#issuecomment-5194025297) |
| Reviewer | Anthropic `claude-fable-5`, Claude Code 2.1.216 |
| Review-record SHA-256 | `6f450e0acf09bca8f914c435118651362aa0c2cbb64e0184e1491d9a187d543c` |
| Provenance-receipt SHA-256 | `7e82290de30883d2182105cf0d7437b1456d04e9cdd5b0a7d5525cd94822c016` |
| Security-bundle semantic SHA-256 | `c74cb5778c83c4b0cbabd97ac3a8dd9a0ecdcc76d99fb3231588395fa288ce1c` |
| Security-bundle file SHA-256 | `04ce1757e73032092075ff8437bd5d019d4319d498d555e7be400caacd2180c3` |
| Release-owner acceptance | [authenticated countersignature](https://github.com/augmented-cognition-engine/core/pull/44#issuecomment-5194052374) |

The review is independent AI assurance. It is not a human penetration test, professional security
audit, or certification. That limitation is part of the accepted evidence and must not be removed
from downstream claims.

The release owner accepted five low and two informational findings:

| ID | Accepted residual | Review deadline / containment |
|---|---|---|
| F1 | Durable generation checking relies on the v169 unique activation-generation index as its atomic race backstop | Next minor or 2026-11-05; verify index, reconcile from receipts, and use documented rollback |
| F2 | Selection/use receipt persistence is fail-open to task projection when the audit store fails | 2026-11-05; monitor, retain task projections, restore store, rerun when durable evidence is required |
| F3 | Some trusted registration surfaces lack ceilings and compatible partial registration has no rollback | Next minor; trusted packages only, disable loading on unexpected partial state, add ceilings/reporting |
| F4 | The restart e2e source is hashed but its execution receipt is external to the generated security-bundle gate | Next bundle; retain CI/deployment receipts and embed immutable executed evidence |
| F5 | A same-product legacy optimizer lookup has a narrow record-type-confusion surface | Next minor; disable affected facade if abused and pin the table |
| F6 | Human authority is credential-derived rather than proof of personhood | 2026-11-05; never expose owner API credentials to agents and rotate on suspicion |
| F7 | Manually configured JWT secrets have no enforced minimum entropy | Before production; use the setup-generated 64-hex-character or equivalent secret and rotate weak material |

Follow-up hardening is tracked in
[issue #49](https://github.com/augmented-cognition-engine/core/issues/49). These accepted items do
not expand the supported boundary and become a new gate if their containment fails or their expiry
passes without review.

## Deployment inventory

The operator discovered one configured/running upgraded deployment:
`local-compose-infra-surrealdb-1`. At schema 171, its dry-run and persisted/read-verified inventory
covered all 1,151 legacy rows with identical receipt-set SHA-256
`ba6a2b0f231beca56ac95b9f221681fb739d558be0a9fa50a5484feef9b87f36`.
All 1,151 dispositions were read back. The retained receipt-file SHA-256 values are:

- dry run: `b675c7a7a8827f4e78f1f23fd03da129834b572e748473e56d26d5d36c3a436e`;
- persisted/read-verified:
  `3f47d6bad768969b5114a686dc3712aa8c2253d576a29acbd791a1c1a5dbe1e0`.

No legacy history was deleted. Unknown or offline deployments are not claimed. Any later-discovered
deployment must complete and retain the same one-for-one inventory before legacy deletion.

## Final decision

**E1 passed.** The canonical implementation, repository gates, exact published artifact matrix,
fresh public install, real upgraded-deployment inventory, independent AI security acceptance, and
release-owner countersignature are complete for ace-core 0.3.0.

The decision is fail-closed to the exact hashes above. A changed artifact, widened execution or
authority boundary, untrusted extension claim, expired residual without review, or failed
containment requires new evidence and can reopen the gate.
