// @ts-nocheck — globalSetup runs in Node.js; no @types/node in this project
import { type Jtbd2State, saveState, TRADE_OFF_PAYLOAD_2 } from './fixtures2'

const BACKEND = process.env.VITE_API_BASE_URL ?? 'http://localhost:3000'
const API_KEY = process.env.ACE_API_KEY ?? 'ace2026'
const PRODUCT_ID = 'product:platform'

function headers(): Record<string, string> {
  return { 'Content-Type': 'application/json', 'X-API-Key': API_KEY }
}

async function post(url: string, body: unknown): Promise<unknown> {
  const r = await fetch(url, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify(body),
  })
  if (!r.ok) {
    const text = await r.text()
    throw new Error(`POST ${url} → ${r.status}: ${text}`)
  }
  return r.json()
}

async function ping(): Promise<boolean> {
  try {
    const r = await fetch(`${BACKEND}/canvas/sessions?limit=1`, {
      headers: { 'X-API-Key': API_KEY },
    })
    return r.ok
  } catch {
    return false
  }
}

export default async function globalSetup(): Promise<void> {
  if (!(await ping())) {
    console.warn('[JTBD2 setup] Backend not reachable — skipping seed, tests will be skipped.')
    saveState({ skip: true } as Jtbd2State)
    return
  }

  // -------------------------------------------------------------------------
  // JTBD-6: Sticky notes — AI sticky + user sticky on same canvas
  // -------------------------------------------------------------------------
  const sess6 = (await post(`${BACKEND}/canvas/sessions`, {
    project_id: PRODUCT_ID,
    title: '[JTBD2] Event bus decision — brainstorm',
  })) as { id: string }

  await post(`${BACKEND}/canvas/sessions/${sess6.id}/artifacts`, {
    shape_kind: 'sticky',
    tldraw_shape_id: 'shape:jtbd6_ai_sticky',
    payload: { text: 'Kafka gives us replay — crucial for audit trail and catch-up consumers.' },
    x: 100,
    y: 100,
    author: 'ai',
  })

  await post(`${BACKEND}/canvas/sessions/${sess6.id}/artifacts`, {
    shape_kind: 'sticky',
    tldraw_shape_id: 'shape:jtbd6_user_sticky',
    payload: { text: 'Redis Streams might be enough given our current scale.' },
    x: 320,
    y: 100,
    author: 'human',
  })

  // -------------------------------------------------------------------------
  // JTBD-7: Matrix card content — Kafka vs Redis trade-off matrix
  // -------------------------------------------------------------------------
  const sess7 = (await post(`${BACKEND}/canvas/sessions`, {
    project_id: PRODUCT_ID,
    title: '[JTBD2] Event bus selection — trade-off matrix',
  })) as { id: string }

  await post(`${BACKEND}/canvas/sessions/${sess7.id}/artifacts`, {
    shape_kind: 'framework_artifact',
    tldraw_shape_id: 'shape:jtbd7_fw',
    payload: TRADE_OFF_PAYLOAD_2,
    x: 100,
    y: 100,
    author: 'ai',
  })

  // -------------------------------------------------------------------------
  // JTBD-8: Topic cluster expansion — 2 auth sessions in same cluster
  // -------------------------------------------------------------------------
  const sess8a = (await post(`${BACKEND}/canvas/sessions`, {
    project_id: PRODUCT_ID,
    title: '[JTBD2] Auth token refresh strategy',
  })) as { id: string }

  const sess8b = (await post(`${BACKEND}/canvas/sessions`, {
    project_id: PRODUCT_ID,
    title: '[JTBD2] Auth middleware extraction plan',
  })) as { id: string }

  // -------------------------------------------------------------------------
  // JTBD-9: Decision count badge — 2 decisions in one session
  // -------------------------------------------------------------------------
  const sess9 = (await post(`${BACKEND}/canvas/sessions`, {
    project_id: PRODUCT_ID,
    title: '[JTBD2] Auth service — two decisions',
  })) as { id: string }

  const dec9a = (await post(`${BACKEND}/canvas/sessions/${sess9.id}/decision`, {
    title: 'Use JWT with 15-minute expiry',
    rationale: 'Short expiry limits exposure window; refresh token in HttpOnly cookie prevents XSS theft.',
    framework_kind: 'trade_off_matrix',
    cited_artifact_ids: [],
  })) as { decision_id: string }

  const dec9b = (await post(`${BACKEND}/canvas/sessions/${sess9.id}/decision`, {
    title: 'Store refresh tokens in Redis',
    rationale: 'Enables immediate invalidation on logout; Redis TTL matches token lifetime automatically.',
    framework_kind: 'trade_off_matrix',
    cited_artifact_ids: [],
  })) as { decision_id: string }

  // -------------------------------------------------------------------------
  // JTBD-10: Decision rationale on expand — single decision with rich rationale
  // -------------------------------------------------------------------------
  const sess10 = (await post(`${BACKEND}/canvas/sessions`, {
    project_id: PRODUCT_ID,
    title: '[JTBD2] Auth — rationale expand check',
  })) as { id: string }

  const dec10 = (await post(`${BACKEND}/canvas/sessions/${sess10.id}/decision`, {
    title: 'Adopt short-lived JWT + Redis refresh',
    rationale:
      'HttpOnly cookie prevents XSS theft; Redis enables immediate invalidation on logout; 15-minute window limits blast radius on token leak.',
    framework_kind: 'trade_off_matrix',
    cited_artifact_ids: [],
  })) as { decision_id: string }

  // -------------------------------------------------------------------------
  // Write state
  // -------------------------------------------------------------------------
  const state: Jtbd2State = {
    jtbd6: { sessionId: sess6.id },
    jtbd7: { sessionId: sess7.id },
    jtbd8: { sessionId1: sess8a.id, sessionId2: sess8b.id },
    jtbd9: { sessionId: sess9.id, decisionId1: dec9a.decision_id, decisionId2: dec9b.decision_id },
    jtbd10: { sessionId: sess10.id, decisionId: dec10.decision_id },
    allSessionIds: [sess6.id, sess7.id, sess8a.id, sess8b.id, sess9.id, sess10.id],
    allDecisionIds: [dec9a.decision_id, dec9b.decision_id, dec10.decision_id],
  }

  saveState(state)
  console.log('[JTBD2 setup] Seeded 6 sessions, 3 decisions, 3 artifacts.')
}
