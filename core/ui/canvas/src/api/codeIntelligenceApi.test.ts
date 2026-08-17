// core/ui/canvas/src/api/codeIntelligenceApi.test.ts
//
// Two things are exercised here against one shared fixture:
//
//   * Session continuity for the caller-held snapshot precondition triple
//     (id/digest/generation).
//   * The bounded structural validation of a 200 body, which decides whether a
//     journey may be returned to the UI at all and whether its triple may
//     become the next request's precondition.
//
// The fixture is a genuinely valid backend-shaped journey: the exact contract
// strings on every nested shape, the exact index profile/topology/scanner, one
// closed node/edge projection whose evidence references are the GENUINE
// stable_id("code_anchor", anchor) identities of the anchors it publishes,
// receipts whose totals are the exact sums over their blocks and whose cited
// anchors attest their exact spans, and a handoff whose included paths are the
// exact ordered manifest block paths — i.e. what core/engine/api/code_
// intelligence.py actually emits, minus the server-side semantics no caller
// can recompute. Every invalid case below is a fixture proved valid by an
// accepting test, with one field changed.
//
// Each test imports a fresh module instance (via vi.resetModules + dynamic
// import) so module-memory state never leaks between scenarios, and drives the
// real happy-dom localStorage rather than a mock so "bounded same-origin
// localStorage JSON" is exercised for real.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const STORAGE_KEY = 'ace.code-intelligence.snapshot'
const CONTRACT_ERROR = /does not match its exact contract/

const TARGET_PATH = 'core/engine/mcp/tools.py'
const LOADER_PATH = 'core/engine/extensions/loader.py'
const QUERY = 'What breaks if core.engine.mcp.tools.ace_impact changes, and why does this path exist?'
const INDEX_ID = `code_index:${'0'.repeat(32)}`
const LENS_ID = `atrium_code_lens:${'1'.repeat(32)}`
const MANIFEST_ID = `code_context_manifest:${'2'.repeat(32)}`
const BLOCK_ID = `code_context_block:${'5'.repeat(32)}`
const REPOSITORY_NODE = 'repository:ace:0123456789'
const MODULE_NODE = 'module:core/engine/mcp:1234567890'
const FILE_NODE = 'file:core/engine/mcp/tools.py:2345678901'
const CONTRIBUTOR_NODE = 'contributor:ada@example.com:3456789012'
const TARGET_DIGEST = `sha256:${'e'.repeat(64)}`
const LOADER_DIGEST = `sha256:${'a'.repeat(64)}`
const BLOCK_DIGEST = `sha256:${'f'.repeat(64)}`
const SYMBOL_BODY_DIGEST = `sha256:${'b'.repeat(64)}`
const COMMIT_EVIDENCE = `git:${'c'.repeat(40)}`

// Anchor identities are NOT free-form strings in a fixture: the backend files
// every anchor under stable_id("code_anchor", anchor) — canonical JSON of the
// anchor's exact serialized fields, SHA-256, first 32 hex characters — and the
// module recomputes each one before resolving any reference to it. These four
// are the genuine identities of the four anchors below, produced by the real
// backend contract rather than written by hand:
//
//   .venv/bin/python -c "from core.engine.code_intelligence.contracts import \
//     SourceAnchorV1Alpha1 as A; print(A(path=..., line_start=..., \
//     line_end=..., content_digest=..., derivation=..., confidence=..., \
//     explanation=...).anchor_id)"
//
// Change any field of the matching anchor below and its identity changes with
// it — which is exactly the property the resolution tests rely on.
const TARGET_ANCHOR_ID = 'code_anchor:23d14e1d30ed48836d97cfcb8ac97c97'
const SYMBOL_ANCHOR_ID = 'code_anchor:18d5667657b83b5c8154ffe188143b1f'
const BLOCK_ANCHOR_ID = 'code_anchor:4ea786b72b659c3348fe3a9dc7620ead'
const SYMBOL_SPAN_ANCHOR_ID = 'code_anchor:5fda28163665676815e4fcf5d9f44cef'
// The same derivation over an explanation carrying non-ASCII text, a quote,
// and a tab — the exact characters `ensure_ascii=True` canonical JSON escapes.
const UNICODE_EXPLANATION = 'Naïve span — 😀 explanation with "quotes" and a\ttab.'
const UNICODE_ANCHOR_ID = 'code_anchor:4b9e95b33dd21ca3310d3dcfdde2e5c4'
// The genuine identities of the target anchor carrying a WRONG contract, and
// of the same anchor with no contract field at all. Citing an anchor by the id
// its own altered content derives isolates the contract-literal check: the
// reference resolves, and only the contract value is left to reject.
const WRONG_CONTRACT_ANCHOR_ID = 'code_anchor:6e5077fc171bee0c6b4a65349dd06de4'
const NO_CONTRACT_ANCHOR_ID = 'code_anchor:03e0f6a69518d7dbde7c30a96db66fee'
// An anchor over the manifest block's exact span and digest but a DIFFERENT
// file, so a receipt citing it differs from it in path alone.
const OTHER_PATH_ANCHOR_ID = 'code_anchor:50b59cd013c5ab29c5fbb72592e64afd'
// The same file and digest over a span shifted by one line at each end, so a
// receipt citing either differs from it in that one line alone.
const START_SHIFTED_ANCHOR_ID = 'code_anchor:b08cff9486a89577f2789a9b37bee882'
const END_SHIFTED_ANCHOR_ID = 'code_anchor:4aacb703d9852146a13f5488e6b7fd08'

function precondition(overrides: Partial<{ id: string; digest: string; generation: number }> = {}) {
  return {
    id: overrides.id ?? `code_index_snapshot:${'a'.repeat(32)}`,
    digest: overrides.digest ?? `sha256:${'b'.repeat(64)}`,
    generation: overrides.generation ?? 3,
  }
}

function indexIdentity(overrides: Record<string, unknown> = {}) {
  return {
    contract: 'ace.code-intelligence.repository-index/v1alpha1',
    repository: 'acme/ace',
    revision: 'c'.repeat(40),
    dirty: false,
    working_tree_digest: 'clean',
    scanner_contract: 'core.engine.intelligence.graph-builder/phase1-tree-sitter',
    analysis_profile: 'python-local-static-v1',
    topology: 'single-local-git-repository',
    supported_languages: ['python'],
    observed_languages: ['python', 'typescript'],
    generated_at: '2026-08-14T12:00:00Z',
    ...overrides,
  }
}

/** The target-file anchor (TARGET_ANCHOR_ID) unless overridden. */
function anchor(overrides: Record<string, unknown> = {}) {
  return {
    contract: 'ace.code-intelligence.source-anchor/v1alpha1',
    path: TARGET_PATH,
    line_start: 1,
    line_end: 80,
    content_digest: TARGET_DIGEST,
    derivation: 'parser',
    confidence: 'observed',
    explanation: 'Exact target file in the scanned repository revision.',
    ...overrides,
  }
}

/** The lexically scanned candidate span behind the disconnected symbol
 *  (SYMBOL_ANCHOR_ID). */
function loaderAnchor(overrides: Record<string, unknown> = {}) {
  return anchor({
    path: LOADER_PATH,
    line_start: 12,
    line_end: 24,
    content_digest: LOADER_DIGEST,
    confidence: 'supported',
    explanation: 'Lexically scanned candidate symbol span.',
    ...overrides,
  })
}

/** The anchor over the exact bounded span the manifest block reports
 *  (BLOCK_ANCHOR_ID). */
function blockAnchor(overrides: Record<string, unknown> = {}) {
  return anchor({
    line_start: 1,
    line_end: 40,
    content_digest: BLOCK_DIGEST,
    explanation: 'Exact bounded source excerpt selected for the coding-agent handoff.',
    ...overrides,
  })
}

/** The anchor over the exact named-symbol span a symbol block reports
 *  (SYMBOL_SPAN_ANCHOR_ID). */
function symbolSpanAnchor(overrides: Record<string, unknown> = {}) {
  return anchor({
    line_start: 12,
    line_end: 28,
    content_digest: SYMBOL_BODY_DIGEST,
    explanation: 'Exact bounded source excerpt selected for the coding-agent handoff.',
    ...overrides,
  })
}

function lens(overrides: Record<string, unknown> = {}) {
  return {
    contract: 'ace.code-intelligence.atrium-code-lens/v1alpha1',
    index: indexIdentity(),
    query: QUERY,
    target_path: TARGET_PATH,
    nodes: [
      {
        node_id: REPOSITORY_NODE,
        kind: 'repository',
        label: 'acme/ace',
        path: null,
        symbol: null,
        derivation: 'git',
        confidence: 'observed',
        evidence_refs: [],
        detail: 'revision cccccccccccc (clean)',
      },
      {
        node_id: MODULE_NODE,
        kind: 'module',
        label: 'core/engine/mcp',
        path: 'core/engine/mcp',
        symbol: null,
        derivation: 'parser',
        confidence: 'observed',
        evidence_refs: [],
        detail: null,
      },
      {
        node_id: FILE_NODE,
        kind: 'api',
        label: 'tools.py',
        path: TARGET_PATH,
        symbol: null,
        derivation: 'parser',
        confidence: 'observed',
        evidence_refs: [TARGET_ANCHOR_ID],
        detail: null,
      },
      {
        node_id: CONTRIBUTOR_NODE,
        kind: 'contributor',
        label: 'ada@example.com',
        path: null,
        symbol: null,
        derivation: 'git',
        confidence: 'observed',
        evidence_refs: [],
        detail: 'Historical Git contributor; not current ownership authority.',
      },
    ],
    edges: [
      {
        source: REPOSITORY_NODE,
        target: MODULE_NODE,
        relation: 'contains',
        derivation: 'parser',
        confidence: 'observed',
        evidence_refs: [],
      },
      {
        source: MODULE_NODE,
        target: FILE_NODE,
        relation: 'contains',
        derivation: 'parser',
        confidence: 'observed',
        evidence_refs: [TARGET_ANCHOR_ID],
      },
      // The one relation whose evidence is a commit rather than a scanned
      // source span, exactly as journey.py emits it.
      {
        source: CONTRIBUTOR_NODE,
        target: FILE_NODE,
        relation: 'historical_contributor',
        derivation: 'git',
        confidence: 'observed',
        evidence_refs: [COMMIT_EVIDENCE],
      },
    ],
    impact: {
      target_path: TARGET_PATH,
      direct_dependents: ['core/engine/mcp/server.py'],
      transitive_dependents: ['core/engine/api/main.py'],
      affected_tests: ['tests/test_mcp_graph_tools.py'],
      known_coverage_gaps: ['Runtime dispatch is not observed by the static profile.'],
      confidence: 'supported',
      basis: 'Static import graph over the exact indexed revision.',
    },
    disconnected_symbols: [
      {
        symbol_id: `symbol:${LOADER_PATH}:plugin_entrypoint`,
        path: LOADER_PATH,
        symbol: 'plugin_entrypoint',
        line_start: 12,
        reason: 'No static inbound edge; may still be a CLI, plugin, framework, or reflective entrypoint.',
        confidence: 'inferred',
        evidence_ref: SYMBOL_ANCHOR_ID,
      },
    ],
    // Exactly the anchors this lens's own claims cite: the target file, the
    // disconnected candidate's span, and the span the manifest block reports.
    evidence: [anchor(), loaderAnchor(), blockAnchor()],
    omissions: ['Static reachability does not prove runtime reachability or safe deletion.'],
    degraded_reasons: [],
    read_only: true,
    source_authority: false,
    reasoning_authority: false,
    delivery_authority: false,
    effect_authority: false,
    ...overrides,
  }
}

function contextBlock(overrides: Record<string, unknown> = {}) {
  return {
    block_id: BLOCK_ID,
    path: TARGET_PATH,
    line_start: 1,
    line_end: 40,
    body_digest: BLOCK_DIGEST,
    byte_count: 1_180,
    token_estimate: 295,
    reason: 'Exact target file head for the requested change.',
    evidence_ref: BLOCK_ANCHOR_ID,
    symbol: null,
    symbol_line_start: null,
    symbol_line_end: null,
    symbol_body_digest: null,
    ...overrides,
  }
}

/** The same receipt for a named symbol: the optional tuple is complete, its
 *  span sits inside the block, and its evidence is the anchor over that exact
 *  symbol span rather than over the block body. */
function symbolBlock(overrides: Record<string, unknown> = {}) {
  return contextBlock({
    evidence_ref: SYMBOL_SPAN_ANCHOR_ID,
    reason: 'named target symbol:ace_impact',
    symbol: 'ace_impact',
    symbol_line_start: 12,
    symbol_line_end: 28,
    symbol_body_digest: SYMBOL_BODY_DIGEST,
    ...overrides,
  })
}

function manifest(overrides: Record<string, unknown> = {}) {
  return {
    contract: 'ace.code-intelligence.context-manifest/v1alpha1',
    index_id: INDEX_ID,
    lens_id: LENS_ID,
    blocks: [contextBlock()],
    total_bytes: 1_180,
    total_token_estimate: 295,
    max_files: 8,
    max_bytes: 24_000,
    omissions: ['Only the bounded head of the target file entered the manifest.'],
    degraded_reasons: [],
    execution_authority: false,
    ...overrides,
  }
}

function handoff(overrides: Record<string, unknown> = {}) {
  return {
    contract: 'ace.code-intelligence.coding-agent-handoff/v1alpha1',
    receiver_ref: 'coding-agent:provider-neutral',
    requested_change: QUERY,
    requested_outputs: ['analysis', 'change_proposal'],
    index_id: INDEX_ID,
    lens_id: LENS_ID,
    manifest_id: MANIFEST_ID,
    included_paths: [TARGET_PATH],
    provider_neutral: true,
    grants_source_authority: false,
    grants_reasoning_authority: false,
    grants_delivery_authority: false,
    grants_effect_authority: false,
    execution_authority_revalidation_required: true,
    ...overrides,
  }
}

function journeyResponse(overrides: Record<string, unknown> = {}) {
  return {
    contract: 'ace.code-intelligence.atrium-journey-response/v1alpha1',
    lens: lens(),
    manifest: manifest(),
    handoff: handoff(),
    scanner_stats: { files: 2_497, functions: 8_213, classes: 964, imports: 12_045 },
    limitations: ['Python static profile only; runtime behaviour is not observed.'],
    context_bodies_exposed: false,
    repository_read_only: true,
    product_history_write: false,
    local_cache_may_write: true,
    index_snapshot_id: `code_index_snapshot:${'c'.repeat(32)}`,
    index_snapshot_digest: `sha256:${'d'.repeat(64)}`,
    index_generation: 1,
    index_reopened: false,
    index_store_provider_free: true,
    index_snapshot_is_product_truth: false,
    ...overrides,
  }
}

/** The fixture with exactly one lens field replaced. */
function withLens(overrides: Record<string, unknown>) {
  return journeyResponse({ lens: lens(overrides) })
}

function withIndex(overrides: Record<string, unknown>) {
  return withLens({ index: indexIdentity(overrides) })
}

/** The fixture with exactly one node field replaced, the rest of the exact
 *  projection — and therefore its closure — left intact, so only the changed
 *  field can be what rejects. */
function withNode(at: number, overrides: Record<string, unknown>) {
  return withLens({ nodes: lens().nodes.map((node, index) => (index === at ? { ...node, ...overrides } : node)) })
}

/** The target file anchor with no contract field at all, rather than one
 *  present but undefined — what an omitted field actually looks like on the
 *  wire, and what its derived identity is computed over. */
function anchorWithoutContract() {
  const bare: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(anchor())) {
    if (key !== 'contract') bare[key] = value
  }
  return bare
}

/** The fixture with its target anchor replaced, cited by the identity that
 *  replacement's own content derives. Every reference still resolves, so the
 *  anchor's own fields are all that is left to reject. */
function withTargetAnchor(variant: unknown, identity: string) {
  return withLens({
    evidence: [variant, loaderAnchor(), blockAnchor()],
    nodes: lens().nodes.map((node, at) => (at === 2 ? { ...node, evidence_refs: [identity] } : node)),
    edges: lens().edges.map((edge, at) => (at === 1 ? { ...edge, evidence_refs: [identity] } : edge)),
  })
}

function withManifest(overrides: Record<string, unknown>) {
  return journeyResponse({ manifest: manifest(overrides) })
}

function withHandoff(overrides: Record<string, unknown>) {
  return journeyResponse({ handoff: handoff(overrides) })
}

/** The fixture publishing BOTH the block-body anchor and the symbol-span
 *  anchor, so a receipt can cite either and only the exact one holds. Byte and
 *  token counts never change here, so the manifest totals still hold. */
function withBlocks(blocks: unknown[]) {
  return journeyResponse({
    lens: lens({
      evidence: [
        anchor(),
        loaderAnchor(),
        blockAnchor(),
        symbolSpanAnchor(),
        otherPathAnchor(),
        startShiftedAnchor(),
        endShiftedAnchor(),
      ],
    }),
    manifest: manifest({ blocks }),
  })
}

/** The manifest block's exact span and digest over another file entirely
 *  (OTHER_PATH_ANCHOR_ID). */
function otherPathAnchor(overrides: Record<string, unknown> = {}) {
  return blockAnchor({ path: LOADER_PATH, ...overrides })
}

/** The block's exact file and digest over a span one line off at the start
 *  (START_SHIFTED_ANCHOR_ID) and at the end (END_SHIFTED_ANCHOR_ID). */
function startShiftedAnchor() {
  return blockAnchor({ line_start: 2 })
}

function endShiftedAnchor() {
  return blockAnchor({ line_end: 41 })
}

/** The anchor whose explanation carries the exact characters canonical
 *  `ensure_ascii=True` JSON has to escape (UNICODE_ANCHOR_ID). */
function unicodeAnchor(overrides: Record<string, unknown> = {}) {
  return symbolSpanAnchor({ explanation: UNICODE_EXPLANATION, ...overrides })
}

/** The fixture with a fourth published anchor whose identity only derives
 *  correctly if non-ASCII text, quotes, and tabs are escaped exactly as the
 *  backend's canonical JSON escapes them — cited by the target file node. */
function withUnicodeAnchor(overrides: Record<string, unknown> = {}) {
  const nodes = lens().nodes
  return withLens({
    evidence: [anchor(), loaderAnchor(), blockAnchor(), unicodeAnchor(overrides)],
    nodes: [
      ...nodes.slice(0, 2),
      { ...nodes[2], evidence_refs: [TARGET_ANCHOR_ID, UNICODE_ANCHOR_ID] },
      ...nodes.slice(3),
    ],
  })
}

/** A JSON array nested `depth` levels deep — for probing the bounded
 *  recursive scan's maximum traversal depth without adding any key. */
function deepArray(depth: number): unknown {
  let value: unknown = []
  for (let i = 0; i < depth; i += 1) value = [value]
  return value
}

function okResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body }
}

function unauthorizedResponse() {
  return { ok: false, status: 401, json: async () => ({ detail: 'expired' }) }
}

async function freshApi(tokens: string[] = ['token-1']) {
  vi.resetModules()
  vi.doMock('./auth', () => {
    let calls = 0
    return {
      getToken: vi.fn(async () => tokens[Math.min(calls++, tokens.length - 1)]),
      clearToken: vi.fn(),
    }
  })
  const auth = await import('./auth')
  const api = await import('./codeIntelligenceApi')
  return { api, auth }
}

function requestBodyOf(call: unknown[]): Record<string, unknown> {
  const init = call[1] as RequestInit
  return JSON.parse(init.body as string) as Record<string, unknown>
}

beforeEach(() => {
  window.localStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.doUnmock('./auth')
})

describe('code intelligence journey: session continuity', () => {
  it('sends no snapshot precondition on the first request', async () => {
    const { api } = await freshApi()
    const fetchMock = vi.fn().mockResolvedValue(okResponse(journeyResponse()))
    vi.stubGlobal('fetch', fetchMock)

    await api.inspectCodeJourney({ query: 'q', target_path: 't' })

    const body = requestBodyOf(fetchMock.mock.calls[0])
    expect(body.expected_snapshot_id).toBeUndefined()
    expect(body.expected_snapshot_digest).toBeUndefined()
    expect(body.expected_snapshot_generation).toBeUndefined()
  })

  it('sends the exact triple from a prior success on the next request', async () => {
    const { api } = await freshApi()
    const first = journeyResponse({
      index_snapshot_id: `code_index_snapshot:${'1'.repeat(32)}`,
      index_snapshot_digest: `sha256:${'2'.repeat(64)}`,
      index_generation: 5,
    })
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(okResponse(first))
      .mockResolvedValueOnce(okResponse(journeyResponse()))
    vi.stubGlobal('fetch', fetchMock)

    await api.inspectCodeJourney({ query: 'q', target_path: 't' })
    await api.inspectCodeJourney({ query: 'q2', target_path: 't2' })

    const second = requestBodyOf(fetchMock.mock.calls[1])
    expect(second.expected_snapshot_id).toBe(first.index_snapshot_id)
    expect(second.expected_snapshot_digest).toBe(first.index_snapshot_digest)
    expect(second.expected_snapshot_generation).toBe(first.index_generation)
  })

  it('a refreshed session restores the triple from bounded localStorage', async () => {
    const stored = precondition()
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(stored))
    const { api } = await freshApi()
    const fetchMock = vi.fn().mockResolvedValue(okResponse(journeyResponse()))
    vi.stubGlobal('fetch', fetchMock)

    await api.inspectCodeJourney({ query: 'q', target_path: 't' })

    const body = requestBodyOf(fetchMock.mock.calls[0])
    expect(body.expected_snapshot_id).toBe(stored.id)
    expect(body.expected_snapshot_digest).toBe(stored.digest)
    expect(body.expected_snapshot_generation).toBe(stored.generation)
  })

  it('retries a 401 with the identical precondition, unchanged by the refresh', async () => {
    const stored = precondition()
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(stored))
    const { api, auth } = await freshApi(['token-1', 'token-2'])
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(unauthorizedResponse())
      .mockResolvedValueOnce(okResponse(journeyResponse()))
    vi.stubGlobal('fetch', fetchMock)

    await api.inspectCodeJourney({ query: 'q', target_path: 't' })

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(auth.clearToken).toHaveBeenCalledTimes(1)
    const firstBody = requestBodyOf(fetchMock.mock.calls[0])
    const secondBody = requestBodyOf(fetchMock.mock.calls[1])
    expect(secondBody.expected_snapshot_id).toBe(firstBody.expected_snapshot_id)
    expect(secondBody.expected_snapshot_digest).toBe(firstBody.expected_snapshot_digest)
    expect(secondBody.expected_snapshot_generation).toBe(firstBody.expected_snapshot_generation)
    expect(secondBody.expected_snapshot_id).toBe(stored.id)
  })

  it.each([
    ['invalid JSON', 'not-json'],
    ['missing digest', JSON.stringify({ id: precondition().id, generation: 1 })],
    ['bad id format', JSON.stringify(precondition({ id: 'nope' }))],
    ['bad digest format', JSON.stringify(precondition({ digest: 'nope' }))],
    ['generation zero', JSON.stringify(precondition({ generation: 0 }))],
    ['generation not an integer', JSON.stringify({ ...precondition(), generation: 1.5 })],
    ['oversized entry', JSON.stringify(precondition({ id: `code_index_snapshot:${'a'.repeat(32)}${'x'.repeat(600)}` }))],
  ])('malformed storage (%s) is ignored as a whole', async (_label, raw) => {
    window.localStorage.setItem(STORAGE_KEY, raw)
    const { api } = await freshApi()
    const fetchMock = vi.fn().mockResolvedValue(okResponse(journeyResponse()))
    vi.stubGlobal('fetch', fetchMock)

    await api.inspectCodeJourney({ query: 'q', target_path: 't' })

    const body = requestBodyOf(fetchMock.mock.calls[0])
    expect(body.expected_snapshot_id).toBeUndefined()
    expect(body.expected_snapshot_digest).toBeUndefined()
    expect(body.expected_snapshot_generation).toBeUndefined()
  })
})

describe('code intelligence journey: bounded response validation', () => {
  it('returns the exact validated journey and stores its triple', async () => {
    const { api } = await freshApi()
    const valid = journeyResponse()
    const fetchMock = vi.fn().mockResolvedValue(okResponse(valid))
    vi.stubGlobal('fetch', fetchMock)

    const result = await api.inspectCodeJourney({ query: QUERY, target_path: TARGET_PATH })

    expect(result).toEqual(valid)
    expect(result.lens.impact.affected_tests).toEqual(['tests/test_mcp_graph_tools.py'])
    expect(result.manifest.blocks).toHaveLength(1)
    expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY) as string)).toEqual({
      id: valid.index_snapshot_id,
      digest: valid.index_snapshot_digest,
      generation: valid.index_generation,
    })
  })

  it('rejects with one short message that does not echo the rejected body', async () => {
    const { api } = await freshApi()
    const fetchMock = vi.fn().mockResolvedValue(
      okResponse(journeyResponse({ contract: 'ace.code-intelligence.attacker-supplied-contract/v9' })),
    )
    vi.stubGlobal('fetch', fetchMock)

    const reason = await api
      .inspectCodeJourney({ query: QUERY, target_path: TARGET_PATH })
      .then(() => null)
      .catch((error: Error) => error)

    expect(reason).toBeInstanceOf(Error)
    const message = (reason as Error).message
    expect(message).toMatch(CONTRACT_ERROR)
    expect(message.length).toBeLessThanOrEqual(120)
    expect(message).not.toContain('attacker-supplied')
    expect(message).not.toContain(TARGET_PATH)
    expect(message).not.toContain(String(journeyResponse().index_snapshot_id))
  })

  it('rejects a 200 whose body is not JSON at all', async () => {
    const { api } = await freshApi()
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => {
        throw new SyntaxError('Unexpected token')
      },
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.inspectCodeJourney({ query: QUERY, target_path: TARGET_PATH })).rejects.toThrow(CONTRACT_ERROR)
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it.each([
    ['a non-object payload', []],
    ['wrong journey contract', journeyResponse({ contract: 'ace.code-intelligence.not-this/v1alpha1' })],
    ['an empty lens stub', journeyResponse({ lens: {} })],
    ['an empty manifest stub', journeyResponse({ manifest: {} })],
    ['an empty handoff stub', journeyResponse({ handoff: {} })],
    ['wrong lens contract', withLens({ contract: 'ace.code-intelligence.atrium-code-lens/v2' })],
    ['wrong manifest contract', withManifest({ contract: 'ace.code-intelligence.context-manifest/v2' })],
    ['wrong handoff contract', withHandoff({ contract: 'ace.code-intelligence.coding-agent-handoff/v2' })],
    ['missing handoff contract', journeyResponse({ handoff: { ...handoff(), contract: undefined } })],
  ])('rejects a 200 with %s', async (_label, invalid) => {
    await expectRejectedAndUnrecorded(invalid)
  })

  it.each([
    ['a node missing its identity', withNode(0, { node_id: undefined })],
    ['a node with an unknown artifact kind', withNode(0, { kind: 'wormhole' })],
    ['a node with an unknown confidence band', withNode(0, { confidence: 'certain' })],
    ['a repeated node identity', withLens({ nodes: [lens().nodes[0], lens().nodes[0]], edges: [] })],
    [
      'an edge naming a node outside the projection',
      withLens({ edges: [{ ...lens().edges[0], target: 'file:absent:9999999999' }] }),
    ],
    ['an edge with an unknown derivation', withLens({ edges: [{ ...lens().edges[0], derivation: 'vibes' }] })],
    ['an anchor with a reversed line span', withLens({ evidence: [anchor({ line_start: 80, line_end: 1 })] })],
    ['an anchor with a malformed content digest', withLens({ evidence: [anchor({ content_digest: 'sha256:short' })] })],
    ['an anchor missing its explanation', withLens({ evidence: [anchor({ explanation: '' })] })],
    ['impact describing a different target path', withLens({ impact: { ...lens().impact, target_path: 'other.py' } })],
    [
      'impact dependents that are not strings',
      withLens({ impact: { ...lens().impact, direct_dependents: [{ path: 'x.py' }] } }),
    ],
    [
      'a disconnected symbol claiming a non-inferred confidence',
      withLens({
        disconnected_symbols: [{ ...lens().disconnected_symbols[0], confidence: 'observed' }],
      }),
    ],
    [
      'lens omissions over the item bound',
      withLens({ omissions: Array.from({ length: 25 }, (_, index) => `omission ${index}`) }),
    ],
    ['a lens omission over the character bound', withLens({ omissions: ['x'.repeat(321)] })],
    ['duplicated lens omissions', withLens({ omissions: ['repeated omission', 'repeated omission'] })],
    [
      'manifest omissions over the item bound',
      withManifest({ omissions: Array.from({ length: 17 }, (_, index) => `omission ${index}`) }),
    ],
    ['a manifest omission over the character bound', withManifest({ omissions: ['x'.repeat(161)] })],
    ['manifest totals differing from its blocks', withManifest({ total_bytes: 999_999 })],
    ['manifest token totals differing from its blocks', withManifest({ total_token_estimate: 1 })],
    ['manifest blocks over the declared file bound', withManifest({ max_files: 0 })],
    ['manifest bytes over the declared byte bound', withManifest({ max_bytes: 4 })],
    ['a manifest block with a malformed body digest', withManifest({ blocks: [contextBlock({ body_digest: 'x' })] })],
    ['a repeated manifest block identity', withManifest({ blocks: [contextBlock(), contextBlock()] })],
    ['scanner stats missing a key', journeyResponse({ scanner_stats: { files: 1, functions: 2, classes: 3 } })],
    [
      'scanner stats with a non-integer value',
      journeyResponse({ scanner_stats: { files: 1.5, functions: 2, classes: 3, imports: 4 } }),
    ],
    ['limitations that are not strings', journeyResponse({ limitations: [{ note: 'nope' }] })],
  ])('rejects a 200 with %s', async (_label, invalid) => {
    await expectRejectedAndUnrecorded(invalid)
  })

  it.each([
    [
      'a manifest block carrying a source body',
      withManifest({ blocks: [contextBlock({ body: 'def ace_impact():\n    return 1' })] }),
    ],
    ['an evidence anchor carrying a source body', withLens({ evidence: [anchor({ body: 'import os' })] })],
    ['a node carrying a source body', withLens({ nodes: [{ ...lens().nodes[0], body: 'class Tools:' }] })],
    [
      'a disconnected symbol carrying a source body',
      withLens({ disconnected_symbols: [{ ...lens().disconnected_symbols[0], snippet: 'def plugin_entrypoint():' }] }),
    ],
    ['context bodies declared exposed', journeyResponse({ context_bodies_exposed: true })],
  ])('rejects a body-bearing 200 with %s', async (_label, invalid) => {
    await expectRejectedAndUnrecorded(invalid)
  })

  // The bounded recursive scan (hasForbiddenContentAnywhere) exists precisely
  // because a body-bearing key can hide anywhere in the parsed response, not
  // only on the exact records the structural checks above already inspect —
  // including at the top level and nested inside an otherwise-unvalidated
  // object no allow-list names.
  it.each([
    ['top-level source_body', journeyResponse({ source_body: 'leaked top-level body' })],
    ['lens.body', withLens({ body: 'leaked lens body' })],
    ['edge.content', withLens({ edges: [{ ...lens().edges[0], content: 'import os' }] })],
    ['impact.snippet', withLens({ impact: { ...lens().impact, snippet: 'leaked snippet' } })],
    ['handoff.body', withHandoff({ body: 'leaked handoff body' })],
    [
      'a nested unknown object carrying content/text several levels deep',
      withLens({
        nodes: [{ ...lens().nodes[0], meta: { detail: { text: 'leaked nested text' } } }],
      }),
    ],
  ])('rejects a 200 with a body-bearing key anywhere in the response (%s)', async (_label, invalid) => {
    await expectRejectedAndUnrecorded(invalid)
  })

  it('rejects a 200 whose nesting exceeds the bounded scan depth', async () => {
    await expectRejectedAndUnrecorded(journeyResponse({ limitations: deepArray(40) }))
  })

  it('rejects a 200 whose object/array count exceeds the bounded scan node budget', async () => {
    await expectRejectedAndUnrecorded(journeyResponse({ limitations: Array.from({ length: 5_000 }, () => []) }))
  })

  // extra=forbid parity: every backend model behind this response is a
  // FrozenContract with extra="forbid" (core/engine/code_intelligence/
  // contracts.py, core/engine/api/code_intelligence.py). An arbitrary,
  // otherwise-harmless-looking extra property must reject exactly like a
  // body-bearing one, at the top level and on every already-validated
  // nested shape.
  it.each([
    ['the top-level response', journeyResponse({ extra_field: 'harmless' })],
    ['the index identity', withIndex({ extra_field: 'harmless' })],
    ['the lens', withLens({ extra_field: 'harmless' })],
    ['a node', withLens({ nodes: [{ ...lens().nodes[0], extra_field: 'harmless' }] })],
    ['an edge', withLens({ edges: [{ ...lens().edges[0], extra_field: 'harmless' }] })],
    ['impact', withLens({ impact: { ...lens().impact, extra_field: 'harmless' } })],
    ['an evidence anchor', withLens({ evidence: [anchor({ extra_field: 'harmless' })] })],
    [
      'a disconnected symbol candidate',
      withLens({ disconnected_symbols: [{ ...lens().disconnected_symbols[0], extra_field: 'harmless' }] }),
    ],
    ['the manifest', withManifest({ extra_field: 'harmless' })],
    ['a manifest block receipt', withManifest({ blocks: [contextBlock({ extra_field: 'harmless' })] })],
    ['the handoff', withHandoff({ extra_field: 'harmless' })],
  ])('rejects a 200 with a harmless extra property on %s', async (_label, invalid) => {
    await expectRejectedAndUnrecorded(invalid)
  })

  it.each([
    ['lens read_only false', withLens({ read_only: false })],
    ['lens source_authority true', withLens({ source_authority: true })],
    ['lens reasoning_authority true', withLens({ reasoning_authority: true })],
    ['lens delivery_authority true', withLens({ delivery_authority: true })],
    ['lens effect_authority true', withLens({ effect_authority: true })],
    ['manifest execution_authority true', withManifest({ execution_authority: true })],
    ['handoff grants_source_authority true', withHandoff({ grants_source_authority: true })],
    ['handoff grants_reasoning_authority true', withHandoff({ grants_reasoning_authority: true })],
    ['handoff grants_delivery_authority true', withHandoff({ grants_delivery_authority: true })],
    ['handoff grants_effect_authority true', withHandoff({ grants_effect_authority: true })],
    [
      'handoff execution revalidation not required',
      withHandoff({ execution_authority_revalidation_required: false }),
    ],
  ])('rejects a 200 claiming %s', async (_label, invalid) => {
    await expectRejectedAndUnrecorded(invalid)
  })

  it.each([
    ['handoff provider_neutral false', withHandoff({ provider_neutral: false })],
    ['index store not provider free', journeyResponse({ index_store_provider_free: false })],
    ['repository_read_only false', journeyResponse({ repository_read_only: false })],
    ['product_history_write true', journeyResponse({ product_history_write: true })],
    ['local_cache_may_write false', journeyResponse({ local_cache_may_write: false })],
    ['index_snapshot_is_product_truth true', journeyResponse({ index_snapshot_is_product_truth: true })],
    ['an analysis profile other than python-local-static-v1', withIndex({ analysis_profile: 'python-local-static-v2' })],
    ['a topology other than a single local git repository', withIndex({ topology: 'multi-remote-repository' })],
    ['supported languages beyond python', withIndex({ supported_languages: ['python', 'typescript'] })],
    ['no supported language at all', withIndex({ supported_languages: [] })],
    ['a working tree digest that is neither clean nor sha256', withIndex({ working_tree_digest: 'probably-clean' })],
    ['observed languages that are not strings', withIndex({ observed_languages: [42] })],
  ])('rejects a 200 declaring %s', async (_label, invalid) => {
    await expectRejectedAndUnrecorded(invalid)
  })

  it.each([
    ['a handoff naming a different index', withHandoff({ index_id: `code_index:${'9'.repeat(32)}` })],
    ['a handoff naming a different lens', withHandoff({ lens_id: `atrium_code_lens:${'9'.repeat(32)}` })],
    ['a handoff requesting a change the lens did not examine', withHandoff({ requested_change: 'something else' })],
    ['included paths differing from the manifest blocks', withHandoff({ included_paths: ['core/engine/api/main.py'] })],
    ['included paths beyond the manifest blocks', withHandoff({ included_paths: [TARGET_PATH, 'extra.py'] })],
  ])('rejects a 200 with %s', async (_label, invalid) => {
    await expectRejectedAndUnrecorded(invalid)
  })

  it.each([
    ['a malformed snapshot id', journeyResponse({ index_snapshot_id: 'not-an-id' })],
    ['an uppercase snapshot id', journeyResponse({ index_snapshot_id: `code_index_snapshot:${'A'.repeat(32)}` })],
    ['a malformed snapshot digest', journeyResponse({ index_snapshot_digest: 'not-a-digest' })],
    ['a truncated snapshot digest', journeyResponse({ index_snapshot_digest: `sha256:${'d'.repeat(63)}` })],
    ['generation zero', journeyResponse({ index_generation: 0 })],
    ['generation above the bound', journeyResponse({ index_generation: 1_000_000_001 })],
    ['a non-integer generation', journeyResponse({ index_generation: 1.5 })],
    ['a non-boolean reopened flag', journeyResponse({ index_reopened: 'no' })],
  ])('rejects a 200 with %s', async (_label, invalid) => {
    await expectRejectedAndUnrecorded(invalid)
  })

  // --- Exact nested contracts and required fields -------------------------
  it.each([
    ['a wrong repository index contract', withIndex({ contract: 'ace.code-intelligence.repository-index/v2' })],
    ['no repository index contract at all', withIndex({ contract: undefined })],
    ['a wrong scanner contract', withIndex({ scanner_contract: 'core.engine.intelligence.graph-builder/phase2' })],
    ['no scanner contract at all', withIndex({ scanner_contract: undefined })],
    ['a generated_at that is not a datetime', withIndex({ generated_at: 'yesterday' })],
    ['a generated_at with no timezone offset', withIndex({ generated_at: '2026-08-14T12:00:00' })],
    ['a generated_at naming a date that does not exist', withIndex({ generated_at: '2026-02-30T12:00:00Z' })],
    ['a generated_at naming an hour that does not exist', withIndex({ generated_at: '2026-08-14T25:00:00Z' })],
    ['a generated_at naming a minute that does not exist', withIndex({ generated_at: '2026-08-14T12:61:00Z' })],
    ['a generated_at naming a second that does not exist', withIndex({ generated_at: '2026-08-14T12:00:61Z' })],
    ['a generated_at with an offset that does not exist', withIndex({ generated_at: '2026-08-14T12:00:00+25:00' })],
    ['a generated_at that is not a string', withIndex({ generated_at: 1_760_000_000 })],
    ['a generated_at past the bounded length', withIndex({ generated_at: `2026-08-14T12:00:00.${'0'.repeat(64)}Z` })],
  ])('rejects a 200 declaring %s', async (_label, invalid) => {
    await expectRejectedAndUnrecorded(invalid)
  })

  it.each([
    [
      'a wrong source anchor contract',
      withTargetAnchor(
        anchor({ contract: 'ace.code-intelligence.source-anchor/v2' }),
        WRONG_CONTRACT_ANCHOR_ID,
      ),
    ],
    ['no source anchor contract at all', withTargetAnchor(anchorWithoutContract(), NO_CONTRACT_ANCHOR_ID)],
  ])('rejects a 200 with %s', async (_label, invalid) => {
    await expectRejectedAndUnrecorded(invalid)
  })

  it.each([
    ['a node with no derivation', withNode(0, { derivation: undefined })],
    ['a node with an unknown derivation', withNode(0, { derivation: 'vibes' })],
    ['a node with no evidence reference list', withNode(0, { evidence_refs: undefined })],
    ['a node whose evidence references are not strings', withNode(2, { evidence_refs: [{ ref: TARGET_ANCHOR_ID }] })],
    [
      'a node with more evidence references than the bound allows',
      withNode(2, { evidence_refs: Array.from({ length: 33 }, () => TARGET_ANCHOR_ID) }),
    ],
  ])('rejects a 200 with %s', async (_label, invalid) => {
    await expectRejectedAndUnrecorded(invalid)
  })

  // --- Derived anchor identity -------------------------------------------
  // Every evidence reference must resolve to an anchor whose own content
  // derives the exact id it was cited by (stable_id("code_anchor", anchor)).
  it('resolves an anchor identity derived from escaped non-ASCII anchor content', async () => {
    await expectAccepted(withUnicodeAnchor())
  })

  it('rejects a reference to an anchor whose content no longer derives that identity', async () => {
    await expectRejectedAndUnrecorded(withUnicodeAnchor({ explanation: 'Naive span - plain ASCII explanation.' }))
  })

  it.each([
    ['a node citing an anchor identity nothing derives', withNode(2, { evidence_refs: [`code_anchor:${'0'.repeat(32)}`] })],
    ['a node citing an anchor this lens never published', withNode(2, { evidence_refs: [SYMBOL_SPAN_ANCHOR_ID] })],
    [
      'an anchor whose content was changed under the identity it is cited by',
      withLens({ evidence: [anchor({ line_end: 79 }), loaderAnchor(), blockAnchor()] }),
    ],
    [
      'a disconnected symbol citing an anchor identity nothing derives',
      withLens({ disconnected_symbols: [{ ...lens().disconnected_symbols[0], evidence_ref: `code_anchor:${'0'.repeat(32)}` }] }),
    ],
    [
      'a disconnected symbol citing an anchor this lens never published',
      withLens({ disconnected_symbols: [{ ...lens().disconnected_symbols[0], evidence_ref: SYMBOL_SPAN_ANCHOR_ID }] }),
    ],
    [
      'the same anchor published twice under one identity',
      withLens({ evidence: [anchor(), anchor(), loaderAnchor(), blockAnchor()] }),
    ],
  ])('rejects a 200 with %s', async (_label, invalid) => {
    await expectRejectedAndUnrecorded(invalid)
  })

  // An identity that cannot be derived is never assumed to match: a runtime
  // without Web Crypto fails the journey closed rather than trusting the
  // evidence references the body supplied for itself.
  it('rejects an otherwise valid 200 in a runtime with no Web Crypto to derive identities with', async () => {
    const { api } = await freshApi()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(journeyResponse())))
    vi.stubGlobal('crypto', {})

    await expect(api.inspectCodeJourney({ query: QUERY, target_path: TARGET_PATH })).rejects.toThrow(CONTRACT_ERROR)
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  // --- Exact graph closure ------------------------------------------------
  it.each([
    ['a repeated edge triple', withLens({ edges: [...lens().edges, lens().edges[0]] })],
    [
      'a repeated disconnected symbol identity',
      withLens({ disconnected_symbols: [lens().disconnected_symbols[0], lens().disconnected_symbols[0]] }),
    ],
    [
      'an edge citing an anchor identity nothing derives',
      withLens({ edges: [lens().edges[0], { ...lens().edges[1], evidence_refs: [`code_anchor:${'0'.repeat(32)}`] }, lens().edges[2]] }),
    ],
    [
      'a commit reference on an edge that is not a historical contributor edge',
      withLens({ edges: [lens().edges[0], { ...lens().edges[1], evidence_refs: [COMMIT_EVIDENCE] }, lens().edges[2]] }),
    ],
    [
      'a commit reference on a historical contributor edge not derived from Git',
      withLens({ edges: [...lens().edges.slice(0, 2), { ...lens().edges[2], derivation: 'graph' }] }),
    ],
    [
      'a commit reference on a Git edge naming another relation',
      withLens({ edges: [...lens().edges.slice(0, 2), { ...lens().edges[2], relation: 'touched' }] }),
    ],
    [
      'a malformed commit reference on the historical contributor edge',
      withLens({ edges: [...lens().edges.slice(0, 2), { ...lens().edges[2], evidence_refs: [`git:${'c'.repeat(39)}`] }] }),
    ],
    [
      'an uppercase commit reference on the historical contributor edge',
      withLens({ edges: [...lens().edges.slice(0, 2), { ...lens().edges[2], evidence_refs: [`git:${'C'.repeat(40)}`] }] }),
    ],
  ])('rejects a 200 with %s', async (_label, invalid) => {
    await expectRejectedAndUnrecorded(invalid)
  })

  // --- Exact handoff block receipt closure --------------------------------
  it('returns a journey whose context receipt reports a named symbol span', async () => {
    await expectAccepted(withBlocks([symbolBlock()]))
  })

  it('returns a journey whose context receipt reports only its own block span', async () => {
    await expectAccepted(withBlocks([contextBlock()]))
  })

  it.each([
    // These three keep a receipt whose block span, digest, and cited anchor all
    // still agree exactly, so the incomplete symbol tuple is the only thing
    // left to reject.
    ['a symbol span with no identity or digest', withBlocks([contextBlock({ symbol_line_start: 12, symbol_line_end: 28 })])],
    ['a symbol digest with no identity or span', withBlocks([contextBlock({ symbol_body_digest: SYMBOL_BODY_DIGEST })])],
    ['one end of a symbol span and nothing else', withBlocks([contextBlock({ symbol_line_end: 28 })])],
    ['a symbol identity with no span or digest', withBlocks([symbolBlock({ symbol_line_start: null, symbol_line_end: null, symbol_body_digest: null })])],
    ['a symbol span with no symbol identity', withBlocks([symbolBlock({ symbol: null })])],
    ['a symbol span missing one end', withBlocks([symbolBlock({ symbol_line_end: null })])],
    ['a symbol span with no digest', withBlocks([symbolBlock({ symbol_body_digest: null })])],
    ['a reversed symbol span', withBlocks([symbolBlock({ symbol_line_start: 28, symbol_line_end: 12 })])],
    ['a symbol span reaching outside its own block', withBlocks([symbolBlock({ symbol_line_end: 44 })])],
    ['a symbol span starting before its own block', withBlocks([symbolBlock({ line_start: 13, symbol_line_start: 12 })])],
    ['a non-integer symbol line', withBlocks([symbolBlock({ symbol_line_start: 12.5 })])],
    ['a symbol line below the first line of a file', withBlocks([symbolBlock({ symbol_line_start: 0 })])],
    ['a malformed symbol body digest', withBlocks([symbolBlock({ symbol_body_digest: 'sha256:short' })])],
    ['a symbol identity that is not a string', withBlocks([symbolBlock({ symbol: 12 })])],
  ])('rejects a 200 with a context receipt declaring %s', async (_label, invalid) => {
    await expectRejectedAndUnrecorded(invalid)
  })

  it.each([
    [
      'an evidence reference nothing derives',
      withBlocks([contextBlock({ evidence_ref: `code_anchor:${'0'.repeat(32)}` })]),
    ],
    ['an anchor over a different path, span, and digest', withBlocks([contextBlock({ evidence_ref: SYMBOL_ANCHOR_ID })])],
    // Same span, same digest, different file: path alone is what rejects.
    ['an anchor over the same span and digest in another file', withBlocks([contextBlock({ evidence_ref: OTHER_PATH_ANCHOR_ID })])],
    // Same file, same digest, one line off: the span alone is what rejects.
    ['an anchor starting one line into the block it attests', withBlocks([contextBlock({ evidence_ref: START_SHIFTED_ANCHOR_ID })])],
    ['an anchor ending one line past the block it attests', withBlocks([contextBlock({ evidence_ref: END_SHIFTED_ANCHOR_ID })])],
    ['an anchor over a different span and digest', withBlocks([contextBlock({ evidence_ref: TARGET_ANCHOR_ID })])],
    [
      'the block-body anchor rather than the anchor over its named symbol span',
      withBlocks([symbolBlock({ evidence_ref: BLOCK_ANCHOR_ID })]),
    ],
    [
      'a symbol span anchor while reporting no symbol at all',
      withBlocks([contextBlock({ evidence_ref: SYMBOL_SPAN_ANCHOR_ID })]),
    ],
    [
      'a body digest the cited anchor does not attest',
      withBlocks([contextBlock({ body_digest: `sha256:${'9'.repeat(64)}` })]),
    ],
    [
      'a symbol body digest the cited anchor does not attest',
      withBlocks([symbolBlock({ symbol_body_digest: `sha256:${'9'.repeat(64)}` })]),
    ],
  ])('rejects a 200 whose context receipt cites %s', async (_label, invalid) => {
    await expectRejectedAndUnrecorded(invalid)
  })

  it('leaves an already valid triple as the next request precondition after an invalid response', async () => {
    const { api } = await freshApi()
    const first = journeyResponse({
      index_snapshot_id: `code_index_snapshot:${'1'.repeat(32)}`,
      index_snapshot_digest: `sha256:${'2'.repeat(64)}`,
      index_generation: 5,
    })
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(okResponse(first))
      .mockResolvedValueOnce(okResponse(journeyResponse({ index_generation: 0 })))
      .mockResolvedValueOnce(okResponse(journeyResponse()))
    vi.stubGlobal('fetch', fetchMock)

    await api.inspectCodeJourney({ query: 'q', target_path: 't' })
    const stored = window.localStorage.getItem(STORAGE_KEY)

    await expect(api.inspectCodeJourney({ query: 'q2', target_path: 't2' })).rejects.toThrow(CONTRACT_ERROR)
    // Neither the mirrored entry nor module memory moved.
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe(stored)

    await api.inspectCodeJourney({ query: 'q3', target_path: 't3' })
    const third = requestBodyOf(fetchMock.mock.calls[2])
    expect(third.expected_snapshot_id).toBe(first.index_snapshot_id)
    expect(third.expected_snapshot_digest).toBe(first.index_snapshot_digest)
    expect(third.expected_snapshot_generation).toBe(first.index_generation)
  })
})

/**
 * One valid 200 must be returned exactly as it arrived. Every mutation case
 * above starts from a fixture proved valid by one of these, so a rejection can
 * only come from the single field that was changed.
 */
async function expectAccepted(valid: unknown) {
  const { api } = await freshApi()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(valid)))

  await expect(api.inspectCodeJourney({ query: QUERY, target_path: TARGET_PATH })).resolves.toEqual(valid)
}

/**
 * One invalid 200 must reject, write nothing, and leave the next request in the
 * precondition-free state a caller with no valid journey is in.
 */
async function expectRejectedAndUnrecorded(invalid: unknown) {
  const { api } = await freshApi()
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(okResponse(invalid))
    .mockResolvedValueOnce(okResponse(journeyResponse()))
  vi.stubGlobal('fetch', fetchMock)

  await expect(api.inspectCodeJourney({ query: QUERY, target_path: TARGET_PATH })).rejects.toThrow(CONTRACT_ERROR)
  expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull()

  await api.inspectCodeJourney({ query: 'q2', target_path: 't2' })
  const second = requestBodyOf(fetchMock.mock.calls[1])
  expect(second.expected_snapshot_id).toBeUndefined()
  expect(second.expected_snapshot_digest).toBeUndefined()
  expect(second.expected_snapshot_generation).toBeUndefined()
}
