# Code Intelligence external-agent round trip v1

Date: 2026-08-15 (America/Los_Angeles)

Disposition: **accepted for one bounded, observed external Codex CLI round trip**

This packet closes the first genuine external-agent journey for the 1.1 Code Intelligence
candidate. ACE minted a new provider-neutral handoff from a fresh three-file Python repository;
`codex exec` consumed the bounded prompt, changed only `pkg/service.py`, and returned the strict
provider-neutral `CodingAgentReturn`. ACE then independently bound the exact changed bytes, ran the
fixture behavior, appended generation two, reopened it in a provider/rescan-forbidden fresh Python
process, and reread immutable generation one.

The exact machine trust root is
[code-intelligence-external-agent-round-trip-v1.json](code-intelligence-external-agent-round-trip-v1.json).
The full deterministic evidence archive is stored as
[base64](artifacts/code-intelligence-external-agent-round-trip-v1.tar.gz.b64) so its bytes can be
reviewed in source control. Decode that file to a `.tar.gz` before passing it to
`replay_external_agent_archive` together with the separately checked-in archive digest, byte count,
and replay expectation.

## Observed external event

The controller invoked `codex exec` version `0.147.0-alpha.6.5` with model `gpt-5.6-sol`, ephemeral
mode, `workspace-write`, ignored user configuration and repository rules, JSON events, the exact
return schema, and an explicit disposable repository working directory. No approval or sandbox
bypass, extra write directory, MCP, plugin, commit, stage, push, or network instruction was used.

The run started at `2026-08-15T05:08:35.217716Z`, acknowledged its first literal
`thread.started` event at `05:08:35.483501Z`, and completed successfully at `05:08:56.282537Z`.
Its session was `01a003d2-65d2-7ca1-8e6b-9031f8a573d5`; the exact ten-event transcript is 2,781
bytes with SHA-256 `4d31d7bb9cff974a1c1de33011fdb4e1fcd3651895a63b97af788d241dcc99e9`.
The trace contains one exact `update` event for the resolved disposable
`pkg/service.py`, the bounded Python assertion, and a UTC timestamp command. The validator parses
the trace rather than trusting summary booleans. This is observed boundedness, not cryptographic
filesystem-read isolation or cryptographic proof that a particular process caused the bytes.

The validator also reconstructs the prompt marker as the exact initial handoff, the supplied schema
as the exact return schema for that journey, the raw and normalized output as the accepted return,
and the repository diff as the exact change-set bytes. The accepted identities are:

- controller `external-agent-controller:8dad0f44237b1c13dbb362dd5f4ed061`;
- delivery `external_agent_delivery:e22312ac85804b5efa3076cd109f385e`;
- return `coding_agent_return:d6351f449db0871672bb7b68eb3be074`;
- change set `external_code_change_set:090703fe0ae12fffe4f5ab590f791a4c`;
- verification `external_code_verification:b721d34ec50661808604e1baaadd3ee1`;
- living update `code_living_update:44181381c8ed3375702a55ddfa02edd6`; and
- complete run `external_agent_acceptance:f1ce09e12ced8edc62f23ec7e6ed6d64`.

The successful Codex event itself was not rerun or relabeled when the durable envelope was
hardened. Its acceptance, delivery, return, timestamps, and transcript IDs remain byte-identical.
Only the outer archive was deterministically repackaged with full initial, updated, historical, and
post-restart contracts and a separately pairable replay expectation.

## Exact change and independent behavior

The repository remained on revision `d5d91413fb6b33346f40c73edab61b469c187f90`; its Git index was
unchanged, with no staged or untracked path. The observed interval changed one 136-byte regular
file from SHA-256 `c0eca19cf8cac8d0b15e026f54978a170b0e147a0202ca2a7f88f1002ff16ab2`
to `47f80352745bf6ae10dab910c91e611d02e3bbb47ee20b4cd23b186b7ec9b9de`.
The deterministic 175-byte patch has SHA-256
`c00200ef4b5a4808815d044795d3a496403a9f32f1142ec686f034bf8c65b38f`; the independent
281-byte Git diff has SHA-256
`773f0770e6d8f0cd4d662f007c1a985439cdd96e7f01bd364fe6c990e7d7f45e`.

ACE did not accept the agent's verification statement as proof. A separate local subprocess ran
`transform(1) == 3` and observed exit code zero. The receipt keeps
`self_authenticates_command_execution=false` and `verifier_replay_required=true`; stored output
digests are not execution authority.

Generation two `code_index_snapshot:563aca8b984af41321be6da79e0531b0` names generation one
`code_index_snapshot:00296c5968d818a90aa0674883aadb42` and its exact digest as parent. A fresh
Python process reopened generation two with full and incremental scanning and provider import or
invocation forbidden. It regenerated index `code_index:16febce8dfa0435ef16b1cb5d996e710`,
lens `atrium_code_lens:6e3c0bb05f4bcd0741dbedc87cc64bee`, and the exact post-change
`transform` block `code_context_block:065bf938b9129b7bb85a846321d5fc2e`. Generation one remained
readable and byte-identical.

## Durable replay and adversarial gates

The decoded deterministic archive is 15,412 bytes, contains 20 sorted regular members, and has
SHA-256 `85bd1c232d03f6517d31fa5f8a73b80a1d6c3049997bcd32ededc67b9ba6d585`.
Its base64 source-control form is 20,553 bytes with SHA-256
`4bffc5caebb26170d9348515b1c1ec4e2d85d55fc85046d72d6290c3577d6437`.
The archive freezes `logs/codex-invocation.json`, the exact Codex `exec` argv, CLI version, and
model observed for this run; replay derives the executable, `exec`, `--ephemeral`,
`--sandbox workspace-write`, `--ignore-user-config`, `--ignore-rules`, model, `--json`, the exact
`--output-schema` and `--output-last-message` paths, the exact `-C` repository working directory,
and the absence of any additional write directory or approval/sandbox bypass flag from that frozen
member, rather than trusting the delivery receipt's own literals. The machine receipt lists every
member's exact byte count and digest. Replay regenerates the archive byte-for-byte, validates all
raw sections and full contracts, and requires the checked-in trust root outside the archive; an
internally coherent archive and manifest cannot authenticate themselves. The archive digest, byte
count, and replay expectation must be supplied together or not at all — replay only reports
`accepted: true` when all three are paired; any unpaired subset is rejected before replay even
begins, and an archive replayed with none of the three reports `accepted: false` while still
reporting structural validation.

The transcript validator parses the exact frozen ten-event Codex lifecycle rather than searching
arbitrary nested keys: one `thread.started` session, one `turn.started`, a matched `file_change`
`item.started`/`item.completed` pair naming the sole target update, two matched
`command_execution` pairs for the exact known allowed commands (the bounded `transform(1) == 3`
check and the UTC timestamp command, each completed with exit code zero and the date command's
output in the observed safe shape), one completed `agent_message` parsed as the exact
coding-agent return matching `exchange/codex-return.json` and the accepted return, and one
`turn.completed`. It rejects a wrong event type, a command string hidden in an arbitrary note
object, a missing completion, a crossed item ID, a duplicate thread, a started-only write, a
nonzero or non-completed command, an absolute outside-repository read such as `cat /etc/passwd`,
and any extra event. Every textual archive member is
scanned for recognized credential and private-key shapes (PEM private keys, `sk-`/`ghp_`/`AKIA`
tokens, and labeled key/token/secret/password assignments); this is a pattern match against known
secret shapes, not proof that no secret is present. The archive replay requires the closed, exact
20-member inventory and rejects any extra, missing, or unrecognized member, and cross-links every
evidentiary member — the live handoff, return receipt, before/after bodies, patch, change-set
receipt, verification receipt, stdout, stderr, invocation, transcript, prompt, schema, output,
normalized return, repository diff, replay expectation, and manifest — back to the single accepted
run.

The focused gate passed 36 tests and Ruff passed. The widened Code Intelligence, continuity,
incremental, graph, and MCP gate passed 197 tests. Adversarial cases reject coherent snapshot and
dependent-ID recomputation, workspace-root relabeling, pre-`thread.started` events, a second
`thread.started` later in an otherwise valid transcript, an absolute outside-repository read
command, crossed write paths or kinds, crossed prompt/schema/output/return/invocation/diff bytes,
crossed or bypass-flagged Codex invocation argv, traversal, symlink, duplicate and extra archive
members, a changed before-body member paired with an unexpected secret-like member, unpaired
trust-root fields, harness-mutation relabeling, authority-positive contracts, an event count other
than the exact ten-event lifecycle, an agent message not bound to its return, a hidden command or
cmd execution marker, a browser, MCP, or web-search marker including case and qualified-name
variants, a non-strict Codex invocation, a partial rather than all-or-none trust-root acceptance,
and an archive member set that is not an exact closure. The recognized credential and private-key
pattern scan across the 20 frozen archive members found zero matches; this is calibrated as a
pattern match against known secret shapes, not proof that no secret is present.

## Authority and scope

Source, reasoning, change, approval, delivery, execution, and effect authority are all false. The
external process produced candidate bytes; the controller observed delivery and independently
validated the result. Neither observation grants Codex or ACE authority over source, reasoning,
approval, delivery, execution, or downstream effects.

This proves one Python path in one disposable local Git repository containing three files. Codex is
the observed adapter, while the handoff and return remain provider-neutral. It does not prove
universal language or topology support, production delivery, publication, installed-wheel behavior,
deployed effect, backup, rollback, recovery, or issue #194 closeout.
