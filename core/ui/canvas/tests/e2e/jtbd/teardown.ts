// @ts-nocheck — globalTeardown runs in Node.js; no @types/node in this project
import * as fs from 'fs'
import * as path from 'path'
import { fileURLToPath } from 'url'
import { type JtbdState, loadState } from './fixtures'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const BACKEND = process.env.VITE_API_BASE_URL ?? 'http://localhost:3000'
const API_KEY = process.env.ACE_API_KEY ?? 'ace2026'
const STATE_PATH = path.resolve(__dirname, 'state.json')

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
  let state: JtbdState
  try {
    state = loadState()
  } catch {
    console.log('[JTBD teardown] No state.json found — nothing to clean up.')
    return
  }

  if (state.skip) {
    console.log('[JTBD teardown] skip=true — no records seeded, nothing to delete.')
    if (fs.existsSync(STATE_PATH)) fs.unlinkSync(STATE_PATH)
    return
  }

  const errors: string[] = []

  // Delete decisions first (sessions cascade artifacts/events, not decisions)
  for (const id of state.allDecisionIds) {
    const status = await del(`${BACKEND}/canvas/decisions/${id}`)
    if (status !== 204) {
      errors.push(`DELETE /canvas/decisions/${id} → ${status} (expected 204)`)
    }
  }

  // Delete sessions (cascades canvas_artifact + canvas_event rows)
  for (const id of state.allSessionIds) {
    const status = await del(`${BACKEND}/canvas/sessions/${id}`)
    if (status !== 204) {
      errors.push(`DELETE /canvas/sessions/${id} → ${status} (expected 204)`)
    }
  }

  // Verify session erasure (decisions have no GET endpoint, DELETE status is sufficient)
  for (const id of state.allSessionIds) {
    const status = await getStatus(`${BACKEND}/canvas/sessions/${id}`)
    if (status !== 404) {
      errors.push(`Verification failed: GET /canvas/sessions/${id} → ${status} (expected 404)`)
    }
  }

  if (errors.length > 0) {
    console.error('[JTBD teardown] Cleanup errors:')
    for (const e of errors) console.error(' ', e)
    console.error('[JTBD teardown] Manual cleanup needed for the above IDs.')
    process.exit(1)
  }

  if (fs.existsSync(STATE_PATH)) fs.unlinkSync(STATE_PATH)
  console.log('[JTBD teardown] All seeded records deleted and verified.')
}
