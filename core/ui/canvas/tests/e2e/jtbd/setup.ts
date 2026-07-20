// @ts-nocheck — globalSetup runs in Node.js; no @types/node in this project
import {
  type JtbdState,
  saveState,
  TRADE_OFF_PAYLOAD,
  DESIGN_OPTIONS_PAYLOAD,
  CODE_ARCH_PAYLOAD,
} from './fixtures'

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
    console.warn('[JTBD setup] Backend not reachable — skipping seed, tests will be skipped.')
    saveState({ skip: true } as JtbdState)
    return
  }

  // -------------------------------------------------------------------------
  // JTBD-1: DB selection — trade-off matrix artifact + decision
  // -------------------------------------------------------------------------
  const sess1 = (await post(`${BACKEND}/canvas/sessions`, {
    project_id: PRODUCT_ID,
    title: '[JTBD] DB selection — SurrealDB vs PostgreSQL',
  })) as { id: string }

  const art1 = (await post(`${BACKEND}/canvas/sessions/${sess1.id}/artifacts`, {
    shape_kind: 'framework_artifact',
    tldraw_shape_id: 'shape:jtbd1_fw',
    payload: TRADE_OFF_PAYLOAD,
    x: 100,
    y: 100,
    author: 'ai',
  })) as { id: string }

  const dec1 = (await post(`${BACKEND}/canvas/sessions/${sess1.id}/decision`, {
    title: 'Use SurrealDB',
    rationale: 'Graph traversal removes join overhead; single binary simplifies ops.',
    framework_kind: 'trade_off_matrix',
    cited_artifact_ids: [art1.id],
  })) as { decision_id: string }

  // -------------------------------------------------------------------------
  // JTBD-2: Streaming transport — design options artifact + decision
  // -------------------------------------------------------------------------
  const sess2 = (await post(`${BACKEND}/canvas/sessions`, {
    project_id: PRODUCT_ID,
    title: '[JTBD] Streaming transport for canvas events',
  })) as { id: string }

  const art2 = (await post(`${BACKEND}/canvas/sessions/${sess2.id}/artifacts`, {
    shape_kind: 'framework_artifact',
    tldraw_shape_id: 'shape:jtbd2_fw',
    payload: DESIGN_OPTIONS_PAYLOAD,
    x: 100,
    y: 100,
    author: 'ai',
  })) as { id: string }

  const dec2 = (await post(`${BACKEND}/canvas/sessions/${sess2.id}/decision`, {
    title: 'Use SSE',
    rationale: 'ACE canvas is server-push only; SSE simplicity wins over WebSocket complexity.',
    framework_kind: 'design_options',
    cited_artifact_ids: [art2.id],
  })) as { decision_id: string }

  // -------------------------------------------------------------------------
  // JTBD-3: Orientation session — no artifact, one decision for context
  // -------------------------------------------------------------------------
  const sess3 = (await post(`${BACKEND}/canvas/sessions`, {
    project_id: PRODUCT_ID,
    title: '[JTBD] Auth middleware rewrite — orientation',
  })) as { id: string }

  const dec3 = (await post(`${BACKEND}/canvas/sessions/${sess3.id}/decision`, {
    title: 'Extract auth into standalone service',
    rationale:
      'Current middleware couples auth with request routing; extraction enables independent scaling.',
    framework_kind: 'trade_off_matrix',
    cited_artifact_ids: [],
  })) as { decision_id: string }

  // -------------------------------------------------------------------------
  // JTBD-4: Close the loop — decision without what_it_led_to initially
  // -------------------------------------------------------------------------
  const sess4 = (await post(`${BACKEND}/canvas/sessions`, {
    project_id: PRODUCT_ID,
    title: '[JTBD] Auth middleware rewrite — close loop',
  })) as { id: string }

  const dec4 = (await post(`${BACKEND}/canvas/sessions/${sess4.id}/decision`, {
    title: 'Extract auth into standalone service',
    rationale:
      'Current middleware couples auth with request routing; extraction enables independent scaling.',
    framework_kind: 'trade_off_matrix',
    cited_artifact_ids: [],
  })) as { decision_id: string }

  // -------------------------------------------------------------------------
  // JTBD-5: Canvas pipeline refactor — code architecture artifact, no decision
  // -------------------------------------------------------------------------
  const sess5 = (await post(`${BACKEND}/canvas/sessions`, {
    project_id: PRODUCT_ID,
    title: '[JTBD] Canvas pipeline refactor — blast radius',
  })) as { id: string }

  await post(`${BACKEND}/canvas/sessions/${sess5.id}/artifacts`, {
    shape_kind: 'framework_artifact',
    tldraw_shape_id: 'shape:jtbd5_fw',
    payload: CODE_ARCH_PAYLOAD,
    x: 100,
    y: 100,
    author: 'ai',
  })

  // -------------------------------------------------------------------------
  // Write state
  // -------------------------------------------------------------------------
  const state: JtbdState = {
    jtbd1: { sessionId: sess1.id, decisionId: dec1.decision_id },
    jtbd2: { sessionId: sess2.id, decisionId: dec2.decision_id },
    jtbd3: { sessionId: sess3.id },
    jtbd4: { sessionId: sess4.id, decisionId: dec4.decision_id },
    jtbd5: { sessionId: sess5.id },
    allDecisionIds: [dec1.decision_id, dec2.decision_id, dec3.decision_id, dec4.decision_id],
    allSessionIds: [sess1.id, sess2.id, sess3.id, sess4.id, sess5.id],
  }

  saveState(state)
  console.log('[JTBD setup] Seeded 5 sessions, 4 decisions, 3 artifacts.')
}
