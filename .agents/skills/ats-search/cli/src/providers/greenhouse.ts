// Greenhouse Job Board API: https://developers.greenhouse.io/job-board.html
// One request lists every job on a board; `content=true` adds full descriptions,
// which is heavy (hundreds of KB for large boards), so listing omits it and the
// description is fetched per posting only for results that survive filtering.

import { apiBase, makeId } from "../boards.js"
import { requestJson } from "../http.js"
import { htmlToText, toIsoDate, uniq } from "../text.js"
import { inferCountry, primaryCountry } from "../geo.js"
import type { Board, Job, ListHints, ListResult, Workplace } from "../types.js"

interface GhJob {
  id: number
  title: string
  absolute_url: string
  company_name?: string
  location?: { name?: string } | null
  first_published?: string | null
  updated_at?: string | null
  content?: string
  departments?: { name?: string }[]
  offices?: { name?: string; location?: string | null }[]
  metadata?: { name?: string; value?: unknown }[] | null
  pay_input_ranges?: { min_cents: number; max_cents: number; currency_type?: string; title?: string }[] | null
}

function money(cents: number, currency: string): string {
  const amount = (cents / 100).toLocaleString("en-US", { maximumFractionDigits: 0 })
  const symbol = currency === "USD" ? "$" : currency === "CAD" ? "CA$" : `${currency} `
  return `${symbol}${amount}`
}

function salaryOf(ranges: GhJob["pay_input_ranges"]): string | null {
  if (!ranges?.length) return null
  return ranges
    .filter((r) => Number.isFinite(r.min_cents) && Number.isFinite(r.max_cents))
    .map((r) => `${money(r.min_cents, r.currency_type ?? "USD")} – ${money(r.max_cents, r.currency_type ?? "USD")}`)
    .join("; ") || null
}

function workplaceOf(location: string): Workplace | null {
  return /\bremote\b/i.test(location) ? "remote" : null
}

/**
 * Some boards keep the real geography outside `location.name`: Cloudflare's
 * `location.name` is "Hybrid" while a custom "Job Posting Location" field holds
 * "Austin, US". Pick up custom fields whose name mentions a location, plus offices.
 */
function extraLocations(j: GhJob): string[] {
  const fromMeta = (j.metadata ?? [])
    .filter((m) => /location/i.test(m.name ?? ""))
    .flatMap((m) => (Array.isArray(m.value) ? m.value : [m.value]))
    .filter((v): v is string => typeof v === "string")
  const fromOffices = (j.offices ?? []).flatMap((o) => [o.location ?? "", o.name ?? ""])
  return [...fromMeta, ...fromOffices]
}

const isValidGh = (j: GhJob): boolean =>
  !!j && typeof j.id === "number" && typeof j.title === "string" && j.title.trim() !== "" && typeof j.absolute_url === "string"

export function normalizeGreenhouse(board: Board, j: GhJob, withContent: boolean): Job {
  const name = (j.location?.name ?? "").trim()
  const candidates = uniq([name, ...extraLocations(j)])
  // Show the first candidate that actually names a place; "Hybrid" or "N/A" is not one.
  const location = candidates.find((c) => inferCountry(c) !== null) ?? name
  const locations = candidates
  const date = toIsoDate(j.first_published ?? j.updated_at)
  return {
    id: makeId(board, String(j.id)),
    ats: "greenhouse",
    company: board.name ?? j.company_name ?? board.company,
    title: j.title.trim(),
    location,
    locations,
    country: primaryCountry(locations),
    date,
    dateApproximate: false,
    url: j.absolute_url,
    department: j.departments?.[0]?.name?.trim() || null,
    employmentType: null,
    workplace: workplaceOf(location),
    salary: salaryOf(j.pay_input_ranges),
    description: withContent && j.content !== undefined ? htmlToText(j.content, { escaped: true }) : null,
    detailRef: String(j.id),
  }
}

export async function listGreenhouse(board: Board, _hints: ListHints): Promise<ListResult> {
  const label = `greenhouse:${board.company}`
  const body = await requestJson<{ jobs?: GhJob[] }>(`${apiBase("greenhouse")}/v1/boards/${board.company}/jobs`, { label })
  if (!body) throw new Error(`${label}: board not found (check the board token)`)
  const valid = (body.jobs ?? []).filter(isValidGh)
  const jobs = valid.map((j) => normalizeGreenhouse(board, j, false))
  return { jobs, truncated: false, countryFiltered: false, skipped: (body.jobs ?? []).length - valid.length }
}

export async function fetchGreenhouseDetail(board: Board, jobRef: string): Promise<Job | null> {
  const label = `greenhouse:${board.company}`
  if (!/^\d+$/.test(jobRef)) return null
  const j = await requestJson<GhJob>(`${apiBase("greenhouse")}/v1/boards/${board.company}/jobs/${jobRef}?pay_transparency=true`, { label })
  return j ? normalizeGreenhouse(board, j, true) : null
}
