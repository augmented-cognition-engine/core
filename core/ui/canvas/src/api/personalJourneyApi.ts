/**
 * Personal journey surfaces: authorize a local folder, then walk the Builder's
 * exact proposal/approval steps (PI13 WS2/WS3).
 *
 * Every call here is one explicit owner decision. Nothing is batched, nothing is
 * inferred, and no approval is ever sent on the owner's behalf: the server keeps
 * source scope, concept model, and intelligence model as separate exact
 * dispositions, and this client preserves that separation rather than smoothing
 * it into a single "set up my intelligence" action.
 */
import { clearToken, getToken } from './auth'

const BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const BUILDS = `${BASE}/v1/intelligence/builds`

/** A failure that carries the server's own exact reason, never a generic one. */
export class PersonalJourneyApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'PersonalJourneyApiError'
    this.status = status
  }
}

/**
 * The server owns every identity, digest, and receipt in these payloads, so the
 * client passes exact material through rather than re-deriving or reshaping it.
 * Narrowing these to hand-written mirrors of the server contracts would invite
 * exactly the drift the exact-material rules exist to prevent.
 */
export type ExactServerMaterial = Record<string, unknown>

export interface LocalSourceConnectPreviewInput {
  readonly profile_id: string
  readonly profile_digest: string
  readonly source_group_id: string
  /** Shown to the owner before any read happens. */
  readonly authorized_root: string
  readonly mapping_scopes: ReadonlyArray<{ readonly mapping_id: string; readonly include: readonly string[] }>
  readonly exclude: readonly string[]
}

export interface LocalSourceConnectAuthorizeInput {
  readonly preview: ExactServerMaterial
  /** Consent is explicit and positive; the server rejects anything else. */
  readonly authorized: true
  readonly authorized_at: string
}

async function send(path: string, body: unknown, failure: string): Promise<ExactServerMaterial> {
  const post = async (token: string) =>
    fetch(`${BUILDS}${path}`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    })

  let token = await getToken()
  let response = await post(token)
  if (response.status === 401) {
    clearToken()
    token = await getToken()
    response = await post(token)
  }
  if (!response.ok) {
    let detail = `${failure} (${response.status}).`
    try {
      const parsed = (await response.json()) as { detail?: unknown }
      if (typeof parsed.detail === 'string') detail = parsed.detail
    } catch {
      // Keep the bounded status-only message for non-JSON failures.
    }
    throw new PersonalJourneyApiError(response.status, detail)
  }
  return (await response.json()) as ExactServerMaterial
}

/** Side-effect-free: shows the exact scope and read-only mode before any read. */
export async function previewLocalSourceConnect(
  input: LocalSourceConnectPreviewInput,
): Promise<ExactServerMaterial> {
  return send('/connect/preview', input, 'ACE could not preview this exact local source scope')
}

/** The first call that reads anything, and only after explicit consent. */
export async function authorizeLocalSourceConnect(
  input: LocalSourceConnectAuthorizeInput,
): Promise<ExactServerMaterial> {
  return send('/connect/authorize', input, 'ACE could not authorize this exact local source read')
}

export async function proposeBuilderSourceScope(input: ExactServerMaterial): Promise<ExactServerMaterial> {
  return send('/builder/source/propose', input, 'ACE could not propose this exact source scope')
}

/**
 * One explicit source-scope approval followed by connect. The server performs
 * them in that order using the receipt it just minted; there is deliberately no
 * approval-only shortcut on this surface.
 */
export async function approveConnectBuilderSourceScope(input: ExactServerMaterial): Promise<ExactServerMaterial> {
  return send('/builder/source/approve-connect', input, 'ACE could not approve and connect this exact source scope')
}

export async function proposeBuilderConceptModel(input: ExactServerMaterial): Promise<ExactServerMaterial> {
  return send('/builder/concept/propose', input, 'ACE could not propose this exact concept model')
}

export async function approveBuilderConceptModel(input: ExactServerMaterial): Promise<ExactServerMaterial> {
  return send('/builder/concept/approve', input, 'ACE could not approve this exact concept model')
}

export async function proposeBuilderIntelligenceModel(input: ExactServerMaterial): Promise<ExactServerMaterial> {
  return send('/builder/intelligence/propose', input, 'ACE could not propose this exact intelligence model')
}

export async function approveBuilderIntelligenceModel(input: ExactServerMaterial): Promise<ExactServerMaterial> {
  return send('/builder/intelligence/approve', input, 'ACE could not approve this exact intelligence model')
}

/** No separate Brief approval exists, and this client must not invent one. */
export async function prepareBuilderFirstBrief(input: ExactServerMaterial): Promise<ExactServerMaterial> {
  return send('/builder/first-brief/prepare', input, 'ACE could not prepare this exact first Brief')
}
