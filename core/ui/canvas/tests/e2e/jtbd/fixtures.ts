// @ts-nocheck — globalSetup/teardown run in Node.js; no @types/node in this project
import { type Page } from '@playwright/test'
import * as fs from 'fs'
import * as path from 'path'
import { fileURLToPath } from 'url'

// ---------------------------------------------------------------------------
// State types
// ---------------------------------------------------------------------------

export interface JtbdState {
  skip?: boolean
  jtbd1: { sessionId: string; decisionId: string }
  jtbd2: { sessionId: string; decisionId: string }
  jtbd3: { sessionId: string }
  jtbd4: { sessionId: string; decisionId: string }
  jtbd5: { sessionId: string }
  allDecisionIds: string[]
  allSessionIds: string[]
}

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const STATE_PATH = path.resolve(__dirname, 'state.json')
const SCREENSHOTS_DIR = path.resolve(__dirname, 'screenshots')

// ---------------------------------------------------------------------------
// Artifact payloads — mirrors Python test_e2e_jtbd.py constants
// ---------------------------------------------------------------------------

export const TRADE_OFF_PAYLOAD = {
  framework_kind: 'trade_off_matrix',
  options: [
    { name: 'SurrealDB', description: 'Native graph traversal; single binary' },
    { name: 'PostgreSQL', description: 'Mature ecosystem; strong team familiarity' },
  ],
  axes: [
    { name: 'graph_support', weight: 0.55 },
    { name: 'operational_simplicity', weight: 0.45 },
  ],
  scores: {
    SurrealDB: { graph_support: 9, operational_simplicity: 7 },
    PostgreSQL: { graph_support: 5, operational_simplicity: 9 },
  },
  recommendation: 'SurrealDB — graph traversal removes join overhead on insight-specialty edges.',
}

export const DESIGN_OPTIONS_PAYLOAD = {
  framework_kind: 'design_options',
  title: 'Streaming transport for canvas events',
  question: 'SSE vs WebSocket vs long-poll for canvas event delivery?',
  options: [
    {
      name: 'SSE',
      scores: { simplicity: 9, browser_support: 8, bidirectionality: 3 },
      note: 'Unidirectional; trivial to proxy; no library needed',
    },
    {
      name: 'WebSocket',
      scores: { simplicity: 6, browser_support: 8, bidirectionality: 9 },
      note: 'Full duplex; needed if client sends high-freq events',
    },
    {
      name: 'Long-poll',
      scores: { simplicity: 7, browser_support: 10, bidirectionality: 4 },
      note: 'Works everywhere; high server overhead at scale',
    },
  ],
  axes: [
    { name: 'simplicity', weight: 0.4 },
    { name: 'browser_support', weight: 0.25 },
    { name: 'bidirectionality', weight: 0.35 },
  ],
  recommendation: 'SSE — ACE canvas is server-push only; simplicity wins.',
}

export const CODE_ARCH_PAYLOAD = {
  framework_kind: 'code_architecture',
  title: 'Canvas orchestration pipeline',
  module: 'engine/canvas/orchestrated_renderer.py',
  nodes: [
    { id: 'n1', label: 'orchestrated_renderer', type: 'core' },
    { id: 'n2', label: 'canvas_engagement', type: 'core' },
    { id: 'n3', label: 'engagement.py', type: 'core' },
    { id: 'n4', label: 'canvas API', type: 'consumer' },
  ],
  edges: [
    { from: 'n4', to: 'n1', label: 'calls render_via_orchestration' },
    { from: 'n1', to: 'n2', label: 'delegates engagement' },
    { from: 'n2', to: 'n3', label: 'calls _execute_single_spin' },
  ],
  blast_radius: {
    score: 0.72,
    affected_files: 7,
    risk: 'medium',
  },
  recommendation:
    'Extract spin execution into a canvas-specific adapter to decouple max_tokens from the shared engagement path.',
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export function loadState(): JtbdState {
  return JSON.parse(fs.readFileSync(STATE_PATH, 'utf8')) as JtbdState
}

export function saveState(state: JtbdState): void {
  fs.writeFileSync(STATE_PATH, JSON.stringify(state, null, 2))
}

export async function waitForCanvas(page: Page, timeout = 20000): Promise<void> {
  await page.waitForSelector('.tl-container', { timeout })
}

export async function screenshot(page: Page, name: string): Promise<string> {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true })
  const filePath = path.join(SCREENSHOTS_DIR, `${name}.png`)
  await page.screenshot({ path: filePath, fullPage: false })
  return filePath
}
