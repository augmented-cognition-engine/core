/// <reference types="vite/client" />
//
// Session continuity: the backend's local index cache is reconstructible
// evidence, not product truth (see AtriumCodeJourneyResponse.index_snapshot_is_
// product_truth). This module holds the caller-side half of that contract — a
// snapshot precondition triple (id, digest, generation) captured from the most
// recent successful journey and echoed on the NEXT request so the backend can
// tell whether its writable cache still matches what this caller last saw.
//
// The triple is continuity evidence only, and losing it does not cost the same
// thing in every case. If the backend's local cache is still empty, the next
// request simply computes a fresh index. But once that cache is nonempty, the
// backend can only trust it against these exact caller-held coordinates — so
// losing the triple makes the NEXT request fail closed with a 409 conflict,
// not a silent re-scan. Nothing here retries or recovers from that conflict or
// deletes the backend cache automatically — that stays a caller decision made
// elsewhere. Held in module memory for this tab session and mirrored into a
// bounded localStorage entry (same-origin by construction) so a page reload
// does not silently strand a warm backend cache behind a conflict it can no
// longer present the precondition for.
//
// An HTTP 200 is not on its own a reason to trust a body: everything this
// module returns is rendered by CodeIntelligenceOS and everything it persists
// becomes the next request's precondition, so one bounded validator runs over
// the parsed payload BEFORE either happens.
import { clearToken, getToken } from './auth'

const BASE = import.meta.env.VITE_API_BASE_URL ?? ''

export type CodeConfidence = 'observed' | 'supported' | 'inferred' | 'unknown'

export type CodeDerivation = 'parser' | 'graph' | 'git' | 'declared' | 'heuristic'

export type CodeArtifactKind =
  | 'repository'
  | 'service'
  | 'module'
  | 'file'
  | 'symbol'
  | 'feature'
  | 'test'
  | 'api'
  | 'ownership'
  | 'contributor'
  | 'adr'
  | 'incident'
  | 'decision'

export interface RepositoryIndexIdentity {
  repository: string
  revision: string
  dirty: boolean
  working_tree_digest: string
  analysis_profile: 'python-local-static-v1'
  topology: 'single-local-git-repository'
  supported_languages: string[]
  observed_languages: string[]
  generated_at: string
}

export interface CodeNode {
  node_id: string
  kind: CodeArtifactKind
  label: string
  path: string | null
  symbol: string | null
  confidence: CodeConfidence
  detail: string | null
}

export interface SourceAnchor {
  path: string
  line_start: number
  line_end: number
  content_digest: string
  derivation: CodeDerivation
  confidence: CodeConfidence
  explanation: string
}

export interface DisconnectedSymbolCandidate {
  symbol_id: string
  path: string
  symbol: string
  line_start: number
  reason: string
  confidence: 'inferred'
  evidence_ref: string
}

export interface CodeImpact {
  target_path: string
  direct_dependents: string[]
  transitive_dependents: string[]
  affected_tests: string[]
  known_coverage_gaps: string[]
  confidence: CodeConfidence
  basis: string
}

export interface AtriumCodeLens {
  contract: 'ace.code-intelligence.atrium-code-lens/v1alpha1'
  index: RepositoryIndexIdentity
  query: string
  target_path: string
  nodes: CodeNode[]
  edges: Array<{
    source: string
    target: string
    relation: string
    derivation: CodeDerivation
    confidence: CodeConfidence
    evidence_refs: string[]
  }>
  impact: CodeImpact
  disconnected_symbols: DisconnectedSymbolCandidate[]
  evidence: SourceAnchor[]
  omissions: string[]
  degraded_reasons: string[]
  read_only: true
  source_authority: false
  reasoning_authority: false
  delivery_authority: false
  effect_authority: false
}

export interface CodeContextManifest {
  contract: 'ace.code-intelligence.context-manifest/v1alpha1'
  index_id: string
  lens_id: string
  blocks: Array<{
    block_id: string
    path: string
    line_start: number
    line_end: number
    body_digest: string
    byte_count: number
    token_estimate: number
    reason: string
    evidence_ref: string
  }>
  total_bytes: number
  total_token_estimate: number
  max_files: number
  max_bytes: number
  omissions: string[]
  degraded_reasons: string[]
  execution_authority: false
}

export interface CodingAgentHandoffReceipt {
  // Declared optional because no screen reads it; the validator still requires
  // the exact literal below, which the backend always emits.
  contract?: 'ace.code-intelligence.coding-agent-handoff/v1alpha1'
  receiver_ref: string
  requested_change: string
  requested_outputs: string[]
  index_id: string
  lens_id: string
  manifest_id: string
  included_paths: string[]
  provider_neutral: true
  grants_source_authority: false
  grants_reasoning_authority: false
  grants_delivery_authority: false
  grants_effect_authority: false
  execution_authority_revalidation_required: true
}

export interface AtriumCodeJourneyResponse {
  contract: 'ace.code-intelligence.atrium-journey-response/v1alpha1'
  lens: AtriumCodeLens
  manifest: CodeContextManifest
  handoff: CodingAgentHandoffReceipt
  scanner_stats: Record<string, number>
  limitations: string[]
  context_bodies_exposed: false
  repository_read_only: true
  product_history_write: false
  local_cache_may_write: true
  index_snapshot_id: string
  index_snapshot_digest: string
  index_generation: number
  index_reopened: boolean
  index_store_provider_free: true
  index_snapshot_is_product_truth: false
}

export interface CodeJourneyInput {
  query: string
  target_path: string
  receiver_ref?: string
}

// --- Session continuity: caller-held snapshot precondition -----------------
// Mirrors the backend's exact validation (core/engine/api/code_intelligence.py):
// snapshot id/digest formats and the [1, MAX_INDEX_GENERATION] integer bound.
const SNAPSHOT_ID_PATTERN = /^code_index_snapshot:[a-f0-9]{32}$/
const SNAPSHOT_DIGEST_PATTERN = /^sha256:[a-f0-9]{64}$/
const MAX_INDEX_GENERATION = 1_000_000_000
const JOURNEY_RESPONSE_CONTRACT = 'ace.code-intelligence.atrium-journey-response/v1alpha1'

// Bounded so a corrupted or hostile localStorage entry cannot grow unbounded
// before it is even parsed.
const MAX_STORED_PRECONDITION_LENGTH = 512

interface SnapshotPrecondition {
  readonly id: string
  readonly digest: string
  readonly generation: number
}

function isValidGeneration(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 1 && value <= MAX_INDEX_GENERATION
}

/** Malformed or incomplete input is rejected as a whole — never partially trusted. */
function isValidPrecondition(value: unknown): value is SnapshotPrecondition {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  return (
    typeof v.id === 'string' &&
    SNAPSHOT_ID_PATTERN.test(v.id) &&
    typeof v.digest === 'string' &&
    SNAPSHOT_DIGEST_PATTERN.test(v.digest) &&
    isValidGeneration(v.generation)
  )
}

function loadStoredPrecondition(): SnapshotPrecondition | null {
  if (typeof window === 'undefined') return null
  let raw: string | null
  try {
    raw = window.localStorage.getItem(SNAPSHOT_STORAGE_KEY)
  } catch {
    return null
  }
  if (typeof raw !== 'string' || raw.length === 0 || raw.length > MAX_STORED_PRECONDITION_LENGTH) return null
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return null
  }
  return isValidPrecondition(parsed) ? parsed : null
}

/** Exported only so tests can pre-seed/inspect the exact storage entry. */
export const SNAPSHOT_STORAGE_KEY = 'ace.code-intelligence.snapshot'

// Module-memory continuity for this tab session, hydrated once from the
// bounded localStorage entry (a page reload restores it; nothing else does).
let snapshotPrecondition: SnapshotPrecondition | null = loadStoredPrecondition()

function persistPrecondition(precondition: SnapshotPrecondition): void {
  snapshotPrecondition = precondition
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(SNAPSHOT_STORAGE_KEY, JSON.stringify(precondition))
  } catch {
    // The stored triple is continuity evidence, not a secret or product
    // truth — a storage failure only costs a future re-scan.
  }
}

// --- Bounded structural validation of one journey response -----------------
// The exact contracts, flags, and shapes the backend exposes
// (core/engine/api/code_intelligence.py and
// core/engine/code_intelligence/contracts.py), narrowed to what
// CodeIntelligenceOS renders plus the continuity and authority invariants the
// screen asserts on the user's behalf.
//
// This is a STRUCTURAL check and nothing more. It establishes that a body has
// the exact shape, contracts, bounds, and flag values the journey contract
// requires, and that every evidence reference resolves to an anchor whose own
// content derives the id it was cited by; it cannot establish that any id,
// digest, anchor, or count was honestly derived from the repository it names.
const LENS_CONTRACT = 'ace.code-intelligence.atrium-code-lens/v1alpha1'
const MANIFEST_CONTRACT = 'ace.code-intelligence.context-manifest/v1alpha1'
const HANDOFF_CONTRACT = 'ace.code-intelligence.coding-agent-handoff/v1alpha1'
const INDEX_CONTRACT = 'ace.code-intelligence.repository-index/v1alpha1'
const SOURCE_ANCHOR_CONTRACT = 'ace.code-intelligence.source-anchor/v1alpha1'
// The exact scanner the phase-1 profile names; a body claiming any other
// scanner is not the profile this screen describes on the user's behalf.
const SCANNER_CONTRACT = 'core.engine.intelligence.graph-builder/phase1-tree-sitter'
const ANALYSIS_PROFILE = 'python-local-static-v1'
const REPOSITORY_TOPOLOGY = 'single-local-git-repository'
// The backend's supported-language tuple is exactly ("python",); a response
// claiming any other analysable language is not this bounded profile.
const SUPPORTED_LANGUAGES = ['python'] as const
const WORKING_TREE_DIGEST_PATTERN = /^(clean|sha256:[a-f0-9]{64})$/
// The one relation whose evidence is a commit rather than a scanned source
// span, and the exact commit form it may name — mirrors _GIT_COMMIT_EVIDENCE
// and AtriumCodeLensV1Alpha1.exact_internal_closure in contracts.py.
const GIT_COMMIT_EVIDENCE_PATTERN = /^git:[0-9a-f]{40}$/
const HISTORICAL_CONTRIBUTOR_RELATION = 'historical_contributor'
const GIT_DERIVATION = 'git'
// The index timestamp is a serialized aware datetime, not free text: an
// RFC 3339 instant with an explicit offset, which is exactly what pydantic
// emits for the aware datetime the journey stamps.
const ISO_DATETIME_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,9})?(?:Z|[+-](\d{2}):(\d{2}))$/
const MAX_DATETIME_CHARS = 40
const SCANNER_STAT_KEYS = ['files', 'functions', 'classes', 'imports'] as const
const CODE_CONFIDENCE_BANDS: readonly string[] = ['observed', 'supported', 'inferred', 'unknown']
const CODE_DERIVATIONS: readonly string[] = ['parser', 'graph', 'git', 'declared', 'heuristic']
const CODE_ARTIFACT_KINDS: readonly string[] = [
  'repository',
  'service',
  'module',
  'file',
  'symbol',
  'feature',
  'test',
  'api',
  'ownership',
  'contributor',
  'adr',
  'incident',
  'decision',
]

// Every rendered collection and string is bounded, so a single oversized or
// unbounded 200 cannot be walked, stored, or laid out at repository scale.
const MAX_INPUT_CHARS = 500 // the backend's own query/target_path bound
const MAX_IDENTIFIER_CHARS = 256
const MAX_LABEL_CHARS = 512
const MAX_PATH_CHARS = 1_024
const MAX_TEXT_CHARS = 4_000
const MAX_LINE = 1_000_000
const MAX_COUNT = 1_000_000_000
const MAX_NODES = 256
const MAX_EDGES = 1_024
const MAX_EVIDENCE_ANCHORS = 256
const MAX_DISCONNECTED_SYMBOLS = 128
const MAX_EVIDENCE_REFS = 32
const MAX_IMPACT_PATHS = 512
const MAX_CONTEXT_BLOCKS = 64
const MAX_REQUESTED_OUTPUTS = 32
const MAX_LIMITATIONS = 32
const MAX_DEGRADED_REASONS = 24
const MAX_OBSERVED_LANGUAGES = 64
// Mirrors LENS_MAX_OMISSIONS* / CONTEXT_MANIFEST_MAX_OMISSIONS* in contracts.py.
const LENS_MAX_OMISSIONS = 24
const LENS_MAX_OMISSION_CHARS = 320
const LENS_MAX_OMISSIONS_TOTAL_CHARS = 3_200
const MANIFEST_MAX_OMISSIONS = 16
const MANIFEST_MAX_OMISSION_CHARS = 160
const MANIFEST_MAX_OMISSIONS_TOTAL_CHARS = 1_200

// Bounds for the recursive forbidden-key scan below. The parsed response is
// acyclic JSON, but nothing about that bounds its depth or object/array
// count on its own — a hostile or malformed body could nest arbitrarily
// deep or wide, so the scan itself must stay deterministic regardless.
const MAX_SCAN_DEPTH = 12
const MAX_SCAN_NODES = 4_096

// The journey exposes receipts, digests, and spans — never source bodies. A
// structure carrying a body-shaped field is rejected rather than rendered.
const BODY_BEARING_KEYS = [
  'body',
  'before_body',
  'after_body',
  'symbol_body',
  'source_body',
  'content',
  'text',
  'snippet',
] as const

// One short, non-echoing failure: an untrusted body is never quoted back into
// the UI, and no check reveals which part of it failed.
const JOURNEY_CONTRACT_ERROR = 'Code Intelligence returned a response that does not match its exact contract.'

type Unknown = Record<string, unknown>

function isRecord(value: unknown): value is Unknown {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isText(value: unknown, maxChars: number): value is string {
  return typeof value === 'string' && value.length >= 1 && value.length <= maxChars
}

function isNullableText(value: unknown, maxChars: number): boolean {
  return value === null || isText(value, maxChars)
}

function isBoundedInt(value: unknown, min: number, max: number): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= min && value <= max
}

function isOrderedLineSpan(start: unknown, end: unknown): boolean {
  if (!isBoundedInt(start, 1, MAX_LINE) || !isBoundedInt(end, 1, MAX_LINE)) return false
  return end >= start
}

function isMember(value: unknown, allowed: readonly string[]): boolean {
  return typeof value === 'string' && allowed.includes(value)
}

function isDigest(value: unknown): boolean {
  return typeof value === 'string' && SNAPSHOT_DIGEST_PATTERN.test(value)
}

/** Bounded in length, exact in shape, and an instant that actually exists.
 *  Each component is range-checked rather than left to Date.parse, which
 *  silently rolls an impossible calendar date such as "2026-02-30T00:00:00Z"
 *  forward into a real one. */
function isIsoDateTime(value: unknown): boolean {
  if (!isText(value, MAX_DATETIME_CHARS)) return false
  const parts = ISO_DATETIME_PATTERN.exec(value)
  if (parts === null) return false
  const [year, month, day, hour, minute, second] = parts.slice(1, 7).map(Number)
  // Absent for a "Z" instant, which is the same as a zero offset.
  const offsetHour = parts[7] === undefined ? 0 : Number(parts[7])
  const offsetMinute = parts[8] === undefined ? 0 : Number(parts[8])
  if (hour > 23 || minute > 59 || second > 59 || offsetHour > 23 || offsetMinute > 59) return false
  const stamped = new Date(Date.UTC(year, month - 1, day))
  if (stamped.getUTCFullYear() !== year || stamped.getUTCMonth() !== month - 1 || stamped.getUTCDate() !== day) {
    return false
  }
  return Number.isFinite(Date.parse(value))
}

function isTextList(value: unknown, maxItems: number, maxChars: number): value is string[] {
  return Array.isArray(value) && value.length <= maxItems && value.every((item) => isText(item, maxChars))
}

/** Bounded per item, per entry length, and in total, exactly as the backend bounds it. */
function isOmissionList(value: unknown, maxItems: number, maxChars: number, maxTotalChars: number): boolean {
  if (!isTextList(value, maxItems, maxChars)) return false
  if (new Set(value).size !== value.length) return false
  return value.reduce((total, item) => total + item.length, 0) <= maxTotalChars
}

function isRecordList(value: unknown, maxItems: number, check: (item: Unknown) => boolean): value is Unknown[] {
  return Array.isArray(value) && value.length <= maxItems && value.every((item) => isRecord(item) && check(item))
}

function carriesBody(record: Unknown): boolean {
  return BODY_BEARING_KEYS.some((key) => key in record)
}

function hasOnlyKeys(record: Unknown, allowed: readonly string[]): boolean {
  return Object.keys(record).every((key) => allowed.includes(key))
}

/** Walks the ENTIRE parsed response — every object and array, at any depth —
 *  before any structural check below reads a single declared field. The
 *  per-shape checks only ever look at the keys their own contract declares,
 *  so a body-bearing key hiding on an undeclared, nested, or array-wrapped
 *  path (an extra property no allow-list names) would otherwise pass
 *  unnoticed. Bounded so the walk itself cannot be turned into an unbounded
 *  traversal: exceeding the depth or object/array node budget is itself a
 *  rejection, exactly like finding a forbidden key. */
function hasForbiddenContentAnywhere(root: unknown): boolean {
  let nodes = 0
  function walk(value: unknown, depth: number): boolean {
    if (!Array.isArray(value) && !isRecord(value)) return false
    if (depth > MAX_SCAN_DEPTH) return true
    nodes += 1
    if (nodes > MAX_SCAN_NODES) return true
    if (isRecord(value) && carriesBody(value)) return true
    const children = Array.isArray(value) ? value : Object.values(value)
    return children.some((child) => walk(child, depth + 1))
  }
  return walk(root, 0)
}

// --- extra=forbid parity: exact allowed key sets per already-validated shape
// Every backend model behind ace.code-intelligence is a FrozenContract with
// extra="forbid" (core/engine/code_intelligence/contracts.py and
// core/engine/api/code_intelligence.py): unknown fields never reach the
// caller from an honest backend. A shape this validator has already checked
// structurally must carry no additional key either — an arbitrary harmless-
// looking extra property must reject exactly like a body-bearing one. Some
// backend contracts declare fields this screen never renders (e.g. a node's
// derivation/evidence_refs, an anchor's or index's own contract literal, a
// context block's optional symbol span) — those stay in the allowed set
// below because the backend genuinely emits them; nothing outside this list
// is trusted through.
const JOURNEY_RESPONSE_KEYS = [
  'contract',
  'lens',
  'manifest',
  'handoff',
  'scanner_stats',
  'limitations',
  'context_bodies_exposed',
  'repository_read_only',
  'product_history_write',
  'local_cache_may_write',
  'index_snapshot_id',
  'index_snapshot_digest',
  'index_generation',
  'index_reopened',
  'index_store_provider_free',
  'index_snapshot_is_product_truth',
] as const

const INDEX_IDENTITY_KEYS = [
  'contract',
  'repository',
  'revision',
  'dirty',
  'working_tree_digest',
  'scanner_contract',
  'analysis_profile',
  'topology',
  'supported_languages',
  'observed_languages',
  'generated_at',
] as const

const LENS_KEYS = [
  'contract',
  'index',
  'query',
  'target_path',
  'nodes',
  'edges',
  'impact',
  'disconnected_symbols',
  'evidence',
  'omissions',
  'degraded_reasons',
  'read_only',
  'source_authority',
  'reasoning_authority',
  'delivery_authority',
  'effect_authority',
] as const

const NODE_KEYS = [
  'node_id',
  'kind',
  'label',
  'path',
  'symbol',
  'derivation',
  'confidence',
  'evidence_refs',
  'detail',
] as const

const EDGE_KEYS = ['source', 'target', 'relation', 'derivation', 'confidence', 'evidence_refs'] as const

const IMPACT_KEYS = [
  'target_path',
  'direct_dependents',
  'transitive_dependents',
  'affected_tests',
  'known_coverage_gaps',
  'confidence',
  'basis',
] as const

const ANCHOR_KEYS = [
  'contract',
  'path',
  'line_start',
  'line_end',
  'content_digest',
  'derivation',
  'confidence',
  'explanation',
] as const

const DISCONNECTED_SYMBOL_KEYS = [
  'symbol_id',
  'path',
  'symbol',
  'line_start',
  'reason',
  'confidence',
  'evidence_ref',
] as const

const MANIFEST_KEYS = [
  'contract',
  'index_id',
  'lens_id',
  'blocks',
  'total_bytes',
  'total_token_estimate',
  'max_files',
  'max_bytes',
  'omissions',
  'degraded_reasons',
  'execution_authority',
] as const

const BLOCK_RECEIPT_KEYS = [
  'block_id',
  'path',
  'line_start',
  'line_end',
  'body_digest',
  'byte_count',
  'token_estimate',
  'reason',
  'evidence_ref',
  'symbol',
  'symbol_line_start',
  'symbol_line_end',
  'symbol_body_digest',
] as const

const HANDOFF_KEYS = [
  'contract',
  'receiver_ref',
  'requested_change',
  'requested_outputs',
  'index_id',
  'lens_id',
  'manifest_id',
  'included_paths',
  'provider_neutral',
  'grants_source_authority',
  'grants_reasoning_authority',
  'grants_delivery_authority',
  'grants_effect_authority',
  'execution_authority_revalidation_required',
] as const

function isValidIndexIdentity(value: unknown): boolean {
  if (!isRecord(value)) return false
  return (
    hasOnlyKeys(value, INDEX_IDENTITY_KEYS) &&
    value.contract === INDEX_CONTRACT &&
    value.scanner_contract === SCANNER_CONTRACT &&
    isText(value.repository, MAX_LABEL_CHARS) &&
    isText(value.revision, MAX_IDENTIFIER_CHARS) &&
    typeof value.dirty === 'boolean' &&
    typeof value.working_tree_digest === 'string' &&
    WORKING_TREE_DIGEST_PATTERN.test(value.working_tree_digest) &&
    value.analysis_profile === ANALYSIS_PROFILE &&
    value.topology === REPOSITORY_TOPOLOGY &&
    Array.isArray(value.supported_languages) &&
    value.supported_languages.length === SUPPORTED_LANGUAGES.length &&
    value.supported_languages.every((item, position) => item === SUPPORTED_LANGUAGES[position]) &&
    isTextList(value.observed_languages, MAX_OBSERVED_LANGUAGES, MAX_LABEL_CHARS) &&
    isIsoDateTime(value.generated_at)
  )
}

function isValidNode(item: Unknown): boolean {
  return (
    hasOnlyKeys(item, NODE_KEYS) &&
    !carriesBody(item) &&
    isText(item.node_id, MAX_IDENTIFIER_CHARS) &&
    isMember(item.kind, CODE_ARTIFACT_KINDS) &&
    isText(item.label, MAX_LABEL_CHARS) &&
    isNullableText(item.path, MAX_PATH_CHARS) &&
    isNullableText(item.symbol, MAX_LABEL_CHARS) &&
    isMember(item.derivation, CODE_DERIVATIONS) &&
    isMember(item.confidence, CODE_CONFIDENCE_BANDS) &&
    isTextList(item.evidence_refs, MAX_EVIDENCE_REFS, MAX_IDENTIFIER_CHARS) &&
    isNullableText(item.detail, MAX_TEXT_CHARS)
  )
}

function isValidEdge(item: Unknown): boolean {
  return (
    hasOnlyKeys(item, EDGE_KEYS) &&
    isText(item.source, MAX_IDENTIFIER_CHARS) &&
    isText(item.target, MAX_IDENTIFIER_CHARS) &&
    isText(item.relation, MAX_LABEL_CHARS) &&
    isMember(item.derivation, CODE_DERIVATIONS) &&
    isMember(item.confidence, CODE_CONFIDENCE_BANDS) &&
    isTextList(item.evidence_refs, MAX_EVIDENCE_REFS, MAX_IDENTIFIER_CHARS)
  )
}

function isValidAnchor(item: Unknown): boolean {
  return (
    hasOnlyKeys(item, ANCHOR_KEYS) &&
    !carriesBody(item) &&
    item.contract === SOURCE_ANCHOR_CONTRACT &&
    isText(item.path, MAX_PATH_CHARS) &&
    isOrderedLineSpan(item.line_start, item.line_end) &&
    isDigest(item.content_digest) &&
    isMember(item.derivation, CODE_DERIVATIONS) &&
    isMember(item.confidence, CODE_CONFIDENCE_BANDS) &&
    isText(item.explanation, MAX_TEXT_CHARS)
  )
}

function isValidDisconnectedSymbol(item: Unknown): boolean {
  return (
    hasOnlyKeys(item, DISCONNECTED_SYMBOL_KEYS) &&
    !carriesBody(item) &&
    isText(item.symbol_id, MAX_IDENTIFIER_CHARS) &&
    isText(item.path, MAX_PATH_CHARS) &&
    isText(item.symbol, MAX_LABEL_CHARS) &&
    isBoundedInt(item.line_start, 1, MAX_LINE) &&
    isText(item.reason, MAX_TEXT_CHARS) &&
    item.confidence === 'inferred' &&
    isText(item.evidence_ref, MAX_IDENTIFIER_CHARS)
  )
}

function isValidImpact(value: unknown, targetPath: string): boolean {
  if (!isRecord(value)) return false
  return (
    hasOnlyKeys(value, IMPACT_KEYS) &&
    value.target_path === targetPath &&
    isTextList(value.direct_dependents, MAX_IMPACT_PATHS, MAX_PATH_CHARS) &&
    isTextList(value.transitive_dependents, MAX_IMPACT_PATHS, MAX_PATH_CHARS) &&
    isTextList(value.affected_tests, MAX_IMPACT_PATHS, MAX_PATH_CHARS) &&
    isTextList(value.known_coverage_gaps, MAX_IMPACT_PATHS, MAX_TEXT_CHARS) &&
    isMember(value.confidence, CODE_CONFIDENCE_BANDS) &&
    isText(value.basis, MAX_TEXT_CHARS)
  )
}

// --- Anchor identity: the caller's own derivation of every evidence ref -----
// A lens names its evidence by id, and every node, disconnected candidate,
// edge, and context receipt cites those ids. The backend derives each one as
// stable_id("code_anchor", anchor) — canonical JSON over the anchor's exact
// serialized fields, SHA-256, first 32 hex characters (contracts.py). Nothing
// in the response body proves an id belongs to the anchor it is filed under,
// so this module recomputes every id from the anchor itself and resolves every
// reference against the recomputed set. An id that was not derived from an
// anchor actually present in this lens resolves to nothing and the body is
// rejected as a whole.
//
// This binds ids to anchor CONTENT and nothing further: it cannot establish
// that any anchor describes a real source span in the repository it names.
const ANCHOR_ID_PREFIX = 'code_anchor'
const ANCHOR_ID_HEX_CHARS = 32
// Every anchor field is already bounded above, so its canonical form is
// bounded too; the explicit ceiling keeps the serializer itself bounded rather
// than relying on those checks having run first.
const MAX_CANONICAL_JSON_CHARS = 65_536

const CANONICAL_ESCAPES: Readonly<Record<string, string>> = {
  '"': '\\"',
  '\\': '\\\\',
  '\b': '\\b',
  '\f': '\\f',
  '\n': '\\n',
  '\r': '\\r',
  '\t': '\\t',
}

/** Python's `json.dumps(..., ensure_ascii=True)` string form, exactly: the
 *  short escapes, control characters as \u00xx, and every non-ASCII character
 *  (including DEL and each half of a surrogate pair) as lowercase \uxxxx. */
function canonicalString(value: string): string {
  let out = '"'
  for (let index = 0; index < value.length; index += 1) {
    const char = value[index]
    const escape = CANONICAL_ESCAPES[char]
    if (escape !== undefined) {
      out += escape
      continue
    }
    const code = value.charCodeAt(index)
    out += code < 0x20 || code > 0x7e ? `\\u${code.toString(16).padStart(4, '0')}` : char
  }
  return `${out}"`
}

/** Canonical JSON matching json.dumps(sort_keys=True, separators=(",", ":"),
 *  ensure_ascii=True) for the bounded JSON an anchor is made of. Anything the
 *  backend cannot have produced — a non-integer or non-finite number, an
 *  undefined value, a structure deeper than the bounded scan allows — yields
 *  null, which fails the whole body rather than hashing a guess.
 *
 *  Keys are sorted with the default comparator, which orders the ASCII field
 *  names of these contracts exactly as Python's codepoint sort does; a record
 *  reaching here has already been checked against its exact key allow-list. */
function canonicalJson(value: unknown, depth = 0): string | null {
  if (depth > MAX_SCAN_DEPTH) return null
  if (value === null) return 'null'
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'string') return canonicalString(value)
  if (typeof value === 'number') return Number.isSafeInteger(value) ? String(value) : null
  if (Array.isArray(value)) {
    const items: string[] = []
    for (const item of value) {
      const encoded = canonicalJson(item, depth + 1)
      if (encoded === null) return null
      items.push(encoded)
    }
    return `[${items.join(',')}]`
  }
  if (!isRecord(value)) return null
  const members: string[] = []
  for (const key of Object.keys(value).sort()) {
    const encoded = canonicalJson(value[key], depth + 1)
    if (encoded === null) return null
    members.push(`${canonicalString(key)}:${encoded}`)
  }
  return `{${members.join(',')}}`
}

/** Null whenever a digest cannot be computed — including a runtime with no Web
 *  Crypto at all. An id that cannot be derived is never assumed to match: the
 *  journey fails closed rather than trusting the ids the body supplied. */
async function sha256Hex(text: string): Promise<string | null> {
  const subtle = globalThis.crypto?.subtle
  if (subtle === undefined) return null
  try {
    const digest = await subtle.digest('SHA-256', new TextEncoder().encode(text))
    return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('')
  } catch {
    return null
  }
}

async function anchorIdentity(anchor: Unknown): Promise<string | null> {
  const canonical = canonicalJson(anchor)
  if (canonical === null || canonical.length > MAX_CANONICAL_JSON_CHARS) return null
  const digest = await sha256Hex(canonical)
  if (digest === null) return null
  return `${ANCHOR_ID_PREFIX}:${digest.slice(0, ANCHOR_ID_HEX_CHARS)}`
}

/** The lens's evidence keyed by the identity each anchor actually derives to.
 *  Two anchors deriving to one id would be one anchor published twice, which
 *  the backend's own dedupe makes impossible — so it is rejected here too. */
async function anchorsByIdentity(evidence: Unknown[]): Promise<Map<string, Unknown> | null> {
  const identities = await Promise.all(evidence.map((anchor) => anchorIdentity(anchor)))
  const anchors = new Map<string, Unknown>()
  identities.forEach((identity, at) => {
    if (identity !== null) anchors.set(identity, evidence[at])
  })
  return anchors.size === evidence.length ? anchors : null
}

/** Collision-free key for one edge's (source, target, relation) identity:
 *  length-prefixed, so no separator inside a value can forge a duplicate or
 *  disguise one. */
function edgeIdentity(edge: Unknown): string {
  const source = edge.source as string
  const target = edge.target as string
  return `${source.length}:${source}|${target.length}:${target}|${edge.relation as string}`
}

/** An edge evidence ref resolves to a published anchor, or — for the single
 *  historical Git contributor relation, whose evidence is a commit rather than
 *  a scanned span — to an exact commit reference. Nothing else. */
function resolvesEdgeEvidence(edge: Unknown, reference: string, anchorIds: ReadonlySet<string>): boolean {
  if (anchorIds.has(reference)) return true
  return (
    edge.derivation === GIT_DERIVATION &&
    edge.relation === HISTORICAL_CONTRIBUTOR_RELATION &&
    GIT_COMMIT_EVIDENCE_PATTERN.test(reference)
  )
}

/** Each node, edge, and candidate is named once, every edge stays inside the
 *  exact projection, and every claim's evidence resolves to evidence this lens
 *  actually published. */
function isExactGraphClosure(lens: Unknown, anchorIds: ReadonlySet<string>): boolean {
  const nodes = lens.nodes as Unknown[]
  const edges = lens.edges as Unknown[]
  const disconnected = lens.disconnected_symbols as Unknown[]
  const nodeIds = new Set(nodes.map((node) => node.node_id as string))
  if (nodeIds.size !== nodes.length) return false
  if (new Set(edges.map(edgeIdentity)).size !== edges.length) return false
  if (new Set(disconnected.map((item) => item.symbol_id as string)).size !== disconnected.length) return false
  if (!edges.every((edge) => nodeIds.has(edge.source as string) && nodeIds.has(edge.target as string))) return false
  if (!nodes.every((node) => (node.evidence_refs as string[]).every((ref) => anchorIds.has(ref)))) return false
  if (!disconnected.every((item) => anchorIds.has(item.evidence_ref as string))) return false
  return edges.every((edge) =>
    (edge.evidence_refs as string[]).every((ref) => resolvesEdgeEvidence(edge, ref, anchorIds)),
  )
}

function hasSymbolIdentity(receipt: Unknown): boolean {
  return receipt.symbol !== null && receipt.symbol !== undefined
}

/** Every context receipt cites an anchor this lens published, over the exact
 *  span and digest the receipt itself declares: the named symbol's span when
 *  the receipt names one, and the block's own bounded span when it does not.
 *  This is what keeps a receipt from citing some other anchor's authority for
 *  a span nobody anchored (journey.py plans blocks before the lens is frozen
 *  precisely so the anchor exists). */
function isExactReceiptClosure(receipts: Unknown[], anchors: ReadonlyMap<string, Unknown>): boolean {
  return receipts.every((receipt) => {
    const anchor = anchors.get(receipt.evidence_ref as string)
    if (anchor === undefined) return false
    const symbolic = hasSymbolIdentity(receipt)
    return (
      anchor.path === receipt.path &&
      anchor.line_start === (symbolic ? receipt.symbol_line_start : receipt.line_start) &&
      anchor.line_end === (symbolic ? receipt.symbol_line_end : receipt.line_end) &&
      anchor.content_digest === (symbolic ? receipt.symbol_body_digest : receipt.body_digest)
    )
  })
}

/** Shape only: the exact closure over node, edge, candidate, and evidence
 *  identity needs each anchor's derived id and is checked in
 *  isExactGraphClosure once those ids have been recomputed. */
function isValidLens(value: unknown): boolean {
  if (!isRecord(value)) return false
  if (!hasOnlyKeys(value, LENS_KEYS)) return false
  if (value.contract !== LENS_CONTRACT) return false
  if (!isValidIndexIdentity(value.index)) return false
  if (!isText(value.query, MAX_INPUT_CHARS) || !isText(value.target_path, MAX_INPUT_CHARS)) return false
  if (!isRecordList(value.nodes, MAX_NODES, isValidNode)) return false
  if (!isRecordList(value.edges, MAX_EDGES, isValidEdge)) return false
  if (!isValidImpact(value.impact, value.target_path)) return false
  if (!isRecordList(value.disconnected_symbols, MAX_DISCONNECTED_SYMBOLS, isValidDisconnectedSymbol)) return false
  if (!isRecordList(value.evidence, MAX_EVIDENCE_ANCHORS, isValidAnchor)) return false
  if (!isOmissionList(value.omissions, LENS_MAX_OMISSIONS, LENS_MAX_OMISSION_CHARS, LENS_MAX_OMISSIONS_TOTAL_CHARS)) {
    return false
  }
  if (!isTextList(value.degraded_reasons, MAX_DEGRADED_REASONS, MAX_TEXT_CHARS)) return false
  return (
    value.read_only === true &&
    value.source_authority === false &&
    value.reasoning_authority === false &&
    value.delivery_authority === false &&
    value.effect_authority === false
  )
}

/** A receipt's optional named symbol is one indivisible tuple: identity, both
 *  span ends, and the span's own digest, or none of them. When present it must
 *  be an ordered span contained in the block the receipt describes — a symbol
 *  reaching outside its own block is not a bounded excerpt of it. */
function hasValidSymbolTuple(item: Unknown): boolean {
  const supplied = [item.symbol, item.symbol_line_start, item.symbol_line_end, item.symbol_body_digest].filter(
    (field) => field !== null && field !== undefined,
  )
  if (supplied.length === 0) return true
  if (supplied.length !== 4) return false
  return (
    isText(item.symbol, MAX_LABEL_CHARS) &&
    isOrderedLineSpan(item.symbol_line_start, item.symbol_line_end) &&
    isDigest(item.symbol_body_digest) &&
    (item.symbol_line_start as number) >= (item.line_start as number) &&
    (item.symbol_line_end as number) <= (item.line_end as number)
  )
}

function isValidBlockReceipt(item: Unknown): boolean {
  return (
    hasOnlyKeys(item, BLOCK_RECEIPT_KEYS) &&
    !carriesBody(item) &&
    isText(item.block_id, MAX_IDENTIFIER_CHARS) &&
    isText(item.path, MAX_PATH_CHARS) &&
    isOrderedLineSpan(item.line_start, item.line_end) &&
    isDigest(item.body_digest) &&
    isBoundedInt(item.byte_count, 0, MAX_COUNT) &&
    isBoundedInt(item.token_estimate, 0, MAX_COUNT) &&
    isText(item.reason, MAX_TEXT_CHARS) &&
    isText(item.evidence_ref, MAX_IDENTIFIER_CHARS) &&
    // Last, so the containment comparison below is made against a block span
    // already known to be an ordered pair of bounded integers.
    hasValidSymbolTuple(item)
  )
}

function isValidManifest(value: unknown): boolean {
  if (!isRecord(value)) return false
  if (!hasOnlyKeys(value, MANIFEST_KEYS)) return false
  if (value.contract !== MANIFEST_CONTRACT) return false
  if (!isText(value.index_id, MAX_IDENTIFIER_CHARS) || !isText(value.lens_id, MAX_IDENTIFIER_CHARS)) return false
  if (!isRecordList(value.blocks, MAX_CONTEXT_BLOCKS, isValidBlockReceipt)) return false
  const blocks = value.blocks
  if (new Set(blocks.map((block) => block.block_id as string)).size !== blocks.length) return false
  if (!isBoundedInt(value.total_bytes, 0, MAX_COUNT) || !isBoundedInt(value.total_token_estimate, 0, MAX_COUNT)) {
    return false
  }
  if (!isBoundedInt(value.max_files, 0, MAX_COUNT) || !isBoundedInt(value.max_bytes, 0, MAX_COUNT)) return false
  // The declared totals and bounds are the ones the screen shows, so they must
  // be the exact sums over the exact receipts, inside the declared budget.
  const totalBytes = blocks.reduce((total, block) => total + (block.byte_count as number), 0)
  const totalTokens = blocks.reduce((total, block) => total + (block.token_estimate as number), 0)
  if (totalBytes !== value.total_bytes || totalTokens !== value.total_token_estimate) return false
  if (blocks.length > value.max_files || totalBytes > value.max_bytes) return false
  if (
    !isOmissionList(
      value.omissions,
      MANIFEST_MAX_OMISSIONS,
      MANIFEST_MAX_OMISSION_CHARS,
      MANIFEST_MAX_OMISSIONS_TOTAL_CHARS,
    )
  ) {
    return false
  }
  if (!isTextList(value.degraded_reasons, MAX_DEGRADED_REASONS, MAX_TEXT_CHARS)) return false
  return value.execution_authority === false
}

function isValidHandoff(value: unknown): boolean {
  if (!isRecord(value)) return false
  if (!hasOnlyKeys(value, HANDOFF_KEYS)) return false
  if (value.contract !== HANDOFF_CONTRACT) return false
  return (
    isText(value.receiver_ref, MAX_IDENTIFIER_CHARS) &&
    isText(value.requested_change, MAX_INPUT_CHARS) &&
    isTextList(value.requested_outputs, MAX_REQUESTED_OUTPUTS, MAX_LABEL_CHARS) &&
    isText(value.index_id, MAX_IDENTIFIER_CHARS) &&
    isText(value.lens_id, MAX_IDENTIFIER_CHARS) &&
    isText(value.manifest_id, MAX_IDENTIFIER_CHARS) &&
    isTextList(value.included_paths, MAX_CONTEXT_BLOCKS, MAX_PATH_CHARS) &&
    value.provider_neutral === true &&
    value.grants_source_authority === false &&
    value.grants_reasoning_authority === false &&
    value.grants_delivery_authority === false &&
    value.grants_effect_authority === false &&
    value.execution_authority_revalidation_required === true
  )
}

/** Lens, manifest, and receipt must name one index, one lens, and one path set. */
function isOneExactChain(lens: Unknown, manifest: Unknown, handoff: Unknown): boolean {
  if (handoff.index_id !== manifest.index_id || handoff.lens_id !== manifest.lens_id) return false
  if (handoff.requested_change !== lens.query) return false
  const blockPaths = (manifest.blocks as Unknown[]).map((block) => block.path as string)
  const includedPaths = handoff.included_paths as string[]
  return includedPaths.length === blockPaths.length && includedPaths.every((path, at) => path === blockPaths[at])
}

function isValidScannerStats(value: unknown): boolean {
  if (!isRecord(value)) return false
  if (Object.keys(value).length !== SCANNER_STAT_KEYS.length) return false
  return SCANNER_STAT_KEYS.every((key) => isBoundedInt(value[key], 0, MAX_COUNT))
}

function isValidSnapshotCoordinates(value: Unknown): boolean {
  return (
    typeof value.index_snapshot_id === 'string' &&
    SNAPSHOT_ID_PATTERN.test(value.index_snapshot_id) &&
    isDigest(value.index_snapshot_digest) &&
    isValidGeneration(value.index_generation) &&
    typeof value.index_reopened === 'boolean'
  )
}

/** Asynchronous only because deriving an anchor identity means hashing, and
 *  the browser's SHA-256 is asynchronous; every check is otherwise bounded and
 *  synchronous, and the answer is still all-or-none. */
async function isValidJourneyResponse(value: unknown): Promise<boolean> {
  if (!isRecord(value)) return false
  // Runs over the WHOLE parsed body, before any field below is read, so a
  // body-bearing key hiding anywhere — top level, nested, nested inside an
  // otherwise-unvalidated extra object — is caught before it can be.
  if (hasForbiddenContentAnywhere(value)) return false
  if (!hasOnlyKeys(value, JOURNEY_RESPONSE_KEYS)) return false
  if (value.contract !== JOURNEY_RESPONSE_CONTRACT) return false
  if (!isValidLens(value.lens) || !isValidManifest(value.manifest) || !isValidHandoff(value.handoff)) return false
  if (!isOneExactChain(value.lens as Unknown, value.manifest as Unknown, value.handoff as Unknown)) return false
  if (!isValidScannerStats(value.scanner_stats)) return false
  if (!isTextList(value.limitations, MAX_LIMITATIONS, MAX_TEXT_CHARS)) return false
  // The exposure, read-only, history, cache, and product-truth boundaries the
  // screen states on the user's behalf are contract constants, not variables.
  if (value.context_bodies_exposed !== false) return false
  if (value.repository_read_only !== true) return false
  if (value.product_history_write !== false) return false
  if (value.local_cache_may_write !== true) return false
  if (value.index_store_provider_free !== true) return false
  if (value.index_snapshot_is_product_truth !== false) return false
  if (!isValidSnapshotCoordinates(value)) return false
  // Last, over shapes already known to be exact: every evidence reference in
  // the lens and in every context receipt must resolve to an anchor whose own
  // content derives the id it was cited by.
  const lens = value.lens as Unknown
  const anchors = await anchorsByIdentity(lens.evidence as Unknown[])
  if (anchors === null) return false
  if (!isExactGraphClosure(lens, new Set(anchors.keys()))) return false
  return isExactReceiptClosure((value.manifest as Unknown).blocks as Unknown[], anchors)
}

// A displayed error is bounded the same way a displayed body is: short, fixed
// maximum length, no control characters. Neither a hostile nor a merely
// oversized backend/network error detail is ever echoed unbounded into the UI.
const MAX_ERROR_DETAIL_CHARS = 200
const FALLBACK_ERROR_DETAIL = 'Code Intelligence is unavailable.'

/** Strips C0/DEL control characters and bounds length. A codepoint filter
 *  rather than a control-char regex class, which this file's toolchain has
 *  shown itself prone to mis-transcribing. */
export function sanitizeErrorDetail(raw: string): string {
  let stripped = ''
  for (let i = 0; i < raw.length; i += 1) {
    const code = raw.charCodeAt(i)
    if (code > 31 && code !== 127) stripped += raw[i]
  }
  stripped = stripped.trim()
  if (stripped.length === 0) return FALLBACK_ERROR_DETAIL
  return stripped.length > MAX_ERROR_DETAIL_CHARS ? `${stripped.slice(0, MAX_ERROR_DETAIL_CHARS)}…` : stripped
}

async function responseError(response: Response): Promise<Error> {
  let detail = `Code Intelligence is unavailable (${response.status}).`
  try {
    const body = (await response.json()) as { detail?: string }
    if (typeof body.detail === 'string') detail = sanitizeErrorDetail(body.detail)
  } catch {
    // Preserve the bounded status-only message for a non-JSON response.
  }
  return new Error(detail)
}

/** A body that is not even JSON fails the same way any other invalid body does. */
async function journeyPayload(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    return null
  }
}

function journeyRequestBody(
  input: CodeJourneyInput,
  precondition: SnapshotPrecondition | null,
): CodeJourneyInput & Record<string, unknown> {
  if (precondition === null) return { ...input }
  return {
    ...input,
    expected_snapshot_id: precondition.id,
    expected_snapshot_digest: precondition.digest,
    expected_snapshot_generation: precondition.generation,
  }
}

async function postJourney(
  token: string,
  input: CodeJourneyInput,
  precondition: SnapshotPrecondition | null,
): Promise<Response> {
  return fetch(`${BASE}/v1/code-intelligence/journey`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(journeyRequestBody(input, precondition)),
  })
}

export async function inspectCodeJourney(input: CodeJourneyInput): Promise<AtriumCodeJourneyResponse> {
  // Captured once so a 401 retry presents the identical precondition — no
  // recovery logic runs between the two attempts, only a token refresh.
  const precondition = snapshotPrecondition
  let token = await getToken()
  let response = await postJourney(token, input, precondition)
  if (response.status === 401) {
    clearToken()
    token = await getToken()
    response = await postJourney(token, input, precondition)
  }
  if (!response.ok) throw await responseError(response)
  const parsed = await journeyPayload(response)
  // All-or-none, before anything is rendered and before anything is stored: a
  // body that fails any check reaches neither the UI nor the next request's
  // precondition, which stays exactly what the last valid journey left.
  if (!(await isValidJourneyResponse(parsed))) throw new Error(JOURNEY_CONTRACT_ERROR)
  const journey = parsed as AtriumCodeJourneyResponse
  persistPrecondition({
    id: journey.index_snapshot_id,
    digest: journey.index_snapshot_digest,
    generation: journey.index_generation,
  })
  return journey
}
