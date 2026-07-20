// @ts-nocheck — globalSetup/teardown run in Node.js; no @types/node in this project
import { type Page } from '@playwright/test'
import * as fs from 'fs'
import * as path from 'path'
import { fileURLToPath } from 'url'

// ---------------------------------------------------------------------------
// State types
// ---------------------------------------------------------------------------

export interface Jtbd2State {
  skip?: boolean
  jtbd6: { sessionId: string }
  jtbd7: { sessionId: string }
  jtbd8: { sessionId1: string; sessionId2: string }
  jtbd9: { sessionId: string; decisionId1: string; decisionId2: string }
  jtbd10: { sessionId: string; decisionId: string }
  allSessionIds: string[]
  allDecisionIds: string[]
}

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
export const STATE_PATH = path.resolve(__dirname, 'state2.json')
const SCREENSHOTS_DIR = path.resolve(__dirname, 'screenshots')

// ---------------------------------------------------------------------------
// Payloads
// ---------------------------------------------------------------------------

export const TRADE_OFF_PAYLOAD_2 = {
  framework_kind: 'trade_off_matrix',
  options: [
    { name: 'Kafka', description: 'Distributed log; durable replay; high throughput' },
    { name: 'Redis Streams', description: 'Low latency; simpler ops; less durability' },
  ],
  axes: [
    { name: 'throughput', weight: 0.6 },
    { name: 'operational_cost', weight: 0.4 },
  ],
  scores: {
    Kafka: { throughput: 9, operational_cost: 4 },
    'Redis Streams': { throughput: 7, operational_cost: 9 },
  },
  recommendation: 'Kafka — throughput and replay are non-negotiable for the event bus.',
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export function loadState(): Jtbd2State {
  return JSON.parse(fs.readFileSync(STATE_PATH, 'utf8')) as Jtbd2State
}

export function saveState(state: Jtbd2State): void {
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
