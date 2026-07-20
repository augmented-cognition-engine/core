// @ts-nocheck — globalSetup runs in Node.js; no @types/node in this project
// Dispatcher: chains every per-suite setup so each numbered fixture suite
// (jtbd, jtbd2, ...) can keep its self-contained setup.ts without needing
// to edit playwright.config.ts each time a new suite is added.
import jtbdSetup from './jtbd/setup'
import jtbd2Setup from './jtbd2/setup2'

export default async function globalSetup(): Promise<void> {
  await jtbdSetup()
  await jtbd2Setup()
}
