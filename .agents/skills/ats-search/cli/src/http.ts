// HTTP layer shared by every provider: timeouts, bounded retries with
// Retry-After support, and JSON decoding that surfaces failures instead of
// swallowing them. Zero dependencies — plain fetch.

import { CliError } from "./types.js"

// Identifies this tool to the ATS operators without naming a contact URL: /apply
// learns which hosts a portal serves by reading host literals in cli/src, so a
// URL here would misclassify unrelated links as an installed job board.
const UA = "Mozilla/5.0 (compatible; ats-search-cli/1.0)"

/** The most one request sleeps across all of its retries. */
export const RETRY_BUDGET_MS = 20_000
const MAX_RETRIES = 4
const TIMEOUT_MS = Number(process.env.ATS_TIMEOUT_MS) > 0 ? Number(process.env.ATS_TIMEOUT_MS) : 20_000

export function retryAfterMs(header: string | null, now = Date.now()): number | null {
  if (!header) return null
  const value = header.trim()
  if (/^\d+$/.test(value)) return Number(value) * 1000
  const date = Date.parse(value)
  if (Number.isNaN(date)) return null
  return Math.max(date - now, 0)
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms))
}

export interface RequestOpts {
  method?: "GET" | "POST"
  body?: unknown
  /** Label used in error messages, e.g. "greenhouse:stripe". */
  label: string
}

/**
 * Request a JSON document. Returns null on 404 (board or posting not found).
 * Retries 429/5xx with jittered exponential backoff inside RETRY_BUDGET_MS;
 * a network failure fails fast so one dead board never stalls a whole run.
 */
export async function requestJson<T>(url: string, opts: RequestOpts): Promise<T | null> {
  let delay = 400
  let waited = 0
  let networkRetried = false
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    let response: Response
    try {
      response = await fetch(url, {
        method: opts.method ?? "GET",
        headers: {
          "User-Agent": UA,
          Accept: "application/json",
          ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}),
        },
        body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
        redirect: "follow",
        signal: AbortSignal.timeout(TIMEOUT_MS),
      })
    } catch (e) {
      // A timeout or reset is usually transient; retry once, then fail the board.
      if (!networkRetried) {
        networkRetried = true
        await sleep(500)
        attempt--
        continue
      }
      throw new CliError(
        `${opts.label}: could not reach ${new URL(url).host} (${e instanceof Error ? e.message : String(e)})`,
        "NETWORK",
      )
    }

    if (response.status === 429 || response.status >= 500) {
      if (attempt === MAX_RETRIES) {
        throw new CliError(`${opts.label}: request failed with ${response.status} ${response.statusText}`, "HTTP_ERROR")
      }
      const wait = Math.max(delay + Math.floor(Math.random() * 250), retryAfterMs(response.headers.get("Retry-After")) ?? 0)
      if (waited + wait > RETRY_BUDGET_MS) {
        throw new CliError(
          `${opts.label}: ${response.status} and the server asked to retry in ${Math.ceil(wait / 1000)}s, past the ${RETRY_BUDGET_MS / 1000}s retry budget`,
          "RATE_LIMITED",
        )
      }
      await sleep(wait)
      waited += wait
      delay = Math.min(delay * 2, 6000)
      continue
    }
    if (response.status === 404) return null
    if (!response.ok) {
      throw new CliError(`${opts.label}: request failed with ${response.status} ${response.statusText}`, "HTTP_ERROR")
    }
    try {
      return (await response.json()) as T
    } catch {
      throw new CliError(`${opts.label}: response was not valid JSON`, "BAD_RESPONSE")
    }
  }
  throw new CliError(`${opts.label}: request failed after retries`, "HTTP_ERROR")
}

/** Run `fn` over `items` with at most `limit` in flight; preserves input order. */
export async function mapPool<T, R>(items: T[], limit: number, fn: (item: T, index: number) => Promise<R>): Promise<R[]> {
  const results = new Array<R>(items.length)
  let next = 0
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (true) {
      const i = next++
      if (i >= items.length) return
      results[i] = await fn(items[i], i)
    }
  })
  await Promise.all(workers)
  return results
}
