// @ts-nocheck — globalTeardown runs in Node.js; no @types/node in this project
import * as fs from 'fs'
import { type Jtbd2State, loadState, STATE_PATH } from './fixtures2'

const BACKEND = process.env.VITE_API_BASE_URL ?? 'http://localhost:3000'
const API_KEY = process.env.ACE_API_KEY ?? 'ace2026'

function authHeader(): Record<string, string> {
  return { 'X-API-Key': API_KEY }
}

async function del(url: string): Promise<number> {
  const r = await fetch(url, { method: 'DELETE', headers: authHeader() })
  return r.status
}

async function getStatus(url: string): Promise<number> {
  const r = await fetch(url, { headers: authHeader() })
  return r.status
}

export default async function globalTeardown(): Promise<void> {
  let state: Jtbd2State
  try {
    state = loadState()
  } catch {
    console.log('[JTBD2 teardown] No state2.json found — nothing to clean up.')
    return
  }

  if (state.skip) {
    console.log('[JTBD2 teardown] skip=true — no records seeded, nothing to delete.')
    if (fs.existsSync(STATE_PATH)) fs.unlinkSync(STATE_PATH)
    return
  }

  const errors: string[] = []

  for (const id of state.allDecisionIds) {
    const status = await del(`${BACKEND}/canvas/decisions/${id}`)
    if (status !== 204) {
      errors.push(`DELETE /canvas/decisions/${id} → ${status} (expected 204)`)
    }
  }

  for (const id of state.allSessionIds) {
    const status = await del(`${BACKEND}/canvas/sessions/${id}`)
    if (status !== 204) {
      errors.push(`DELETE /canvas/sessions/${id} → ${status} (expected 204)`)
    }
  }

  for (const id of state.allSessionIds) {
    const status = await getStatus(`${BACKEND}/canvas/sessions/${id}`)
    if (status !== 404) {
      errors.push(`Verification failed: GET /canvas/sessions/${id} → ${status} (expected 404)`)
    }
  }

  if (errors.length > 0) {
    console.error('[JTBD2 teardown] Cleanup errors:')
    for (const e of errors) console.error(' ', e)
    process.exit(1)
  }

  if (fs.existsSync(STATE_PATH)) fs.unlinkSync(STATE_PATH)
  console.log('[JTBD2 teardown] All seeded records deleted and verified.')
}
