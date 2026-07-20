// @ts-nocheck — globalTeardown runs in Node.js; no @types/node in this project
import jtbdTeardown from './jtbd/teardown'
import jtbd2Teardown from './jtbd2/teardown2'

export default async function globalTeardown(): Promise<void> {
  // Reverse order — last seeded, first torn down.
  await jtbd2Teardown()
  await jtbdTeardown()
}
