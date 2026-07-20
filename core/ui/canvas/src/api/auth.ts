// frontend/src/api/auth.ts
// Exchanges VITE_API_KEY for a short-lived JWT on demand. Cached in memory;
// re-fetched on 401. No localStorage — token is scoped to this tab session.

const API_KEY = import.meta.env.VITE_API_KEY ?? ''

let _token: string | null = null
let _inflight: Promise<string> | null = null

async function fetchToken(): Promise<string> {
  const res = await fetch('/auth/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
    body: JSON.stringify({ api_key: API_KEY }),
    signal: AbortSignal.timeout(5000),
  })
  if (!res.ok) throw new Error(`auth/token → ${res.status}`)
  const data = await res.json()
  return data.token as string
}

export async function getToken(): Promise<string> {
  if (_token) return _token
  if (_inflight) return _inflight
  _inflight = fetchToken().then((t) => {
    _token = t
    _inflight = null
    return t
  }).catch((e) => {
    _inflight = null
    throw e
  })
  return _inflight
}

export function clearToken() {
  _token = null
}
