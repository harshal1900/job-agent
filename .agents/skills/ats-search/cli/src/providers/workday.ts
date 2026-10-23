// Workday career sites. There is no published API, but every Workday careers
// page is a single-page app over a JSON "CXS" endpoint that is open to anonymous
// readers:
//   POST {base}/wday/cxs/{tenant}/{site}/jobs   list/search (20 per page max)
//   GET  {base}/wday/cxs/{tenant}/{site}{path}  one posting with description
// Being unofficial it can change without notice; failures name the board so one
// breaking tenant never takes down the rest of a run.

import { apiBase, makeId } from "../boards.js"
import { requestJson } from "../http.js"
import { inferCountry } from "../geo.js"
import { htmlToText, toIsoDate, uniq } from "../text.js"
import type { Board, Country, Job, ListHints, ListResult, Workplace } from "../types.js"

const PAGE = 20 // Workday rejects larger pages with HTTP 400

interface WdPosting {
  title: string
  externalPath: string
  locationsText?: string
  postedOn?: string
}

interface WdFacetValue {
  descriptor?: string
  id?: string
  facetParameter?: string
  values?: WdFacetValue[]
}

interface WdFacet {
  facetParameter: string
  values?: WdFacetValue[]
}

interface WdList {
  total?: number
  jobPostings?: WdPosting[]
  facets?: WdFacet[]
}

interface WdDetail {
  jobPostingInfo?: {
    title?: string
    jobDescription?: string
    location?: string
    additionalLocations?: string[]
    startDate?: string
    jobReqId?: string
    timeType?: string
    remoteType?: string
    externalUrl?: string
    country?: { descriptor?: string }
  }
}

const SAFE_PATH = /^\/job\/[A-Za-z0-9_%.~()'-]+(\/[A-Za-z0-9_%.~()'-]+)*$/

export function isSafeWorkdayPath(path: string): boolean {
  return SAFE_PATH.test(path) && !path.split("/").some((s) => s === "." || s === "..")
}

function cxs(board: Board): string {
  return `${apiBase("workday", board)}/wday/cxs/${board.company}/${board.site}`
}

/** "Posted 3 Days Ago" → days; null for "30+ days" or unparseable labels. */
export function postedDays(label: string | undefined): number | null {
  if (!label) return null
  if (/today/i.test(label)) return 0
  if (/yesterday/i.test(label)) return 1
  const m = /(\d+)(\+)?\s*days?/i.exec(label)
  if (!m || m[2]) return null
  return Number(m[1])
}

function dateDaysAgo(days: number, now = new Date()): string {
  const t = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()) - days * 86_400_000
  return new Date(t).toISOString().slice(0, 10)
}

const COUNTRY_NAME = /^(united states( of america)?|usa?|canada)$/i

function countryFromName(name: string): Country | null {
  if (/^canada$/i.test(name)) return "CA"
  if (/^(united states( of america)?|usa?)$/i.test(name)) return "US"
  return null
}

/**
 * Choose the one location facet that narrows a tenant to the wanted countries.
 * Tenants differ: some expose a country facet, others only per-site entries
 * ("US, AL, Madison"), so country-level values are preferred and per-site
 * values matched through the location parser are the fallback. Workday ANDs
 * different facet parameters, so exactly one parameter is ever returned.
 */
export function pickCountryFacet(facets: WdFacet[], wanted: Country[]): Record<string, string[]> | null {
  const groups: { param: string; values: WdFacetValue[] }[] = []
  for (const f of facets) {
    const nested = (f.values ?? []).filter((v) => Array.isArray(v.values))
    if (nested.length) {
      for (const g of nested) if (g.facetParameter) groups.push({ param: g.facetParameter, values: g.values ?? [] })
    } else if (/location/i.test(f.facetParameter)) {
      groups.push({ param: f.facetParameter, values: f.values ?? [] })
    }
  }
  const rank = (p: string) => (/country|hierarchy1/i.test(p) ? 0 : 1)
  groups.sort((a, b) => rank(a.param) - rank(b.param))
  for (const g of groups) {
    if (!/location/i.test(g.param)) continue
    const ids = g.values
      .filter((v) => v.id && v.descriptor)
      .filter((v) => {
        const c = COUNTRY_NAME.test(v.descriptor!) ? countryFromName(v.descriptor!) : inferCountry(v.descriptor)
        return c !== null && wanted.includes(c)
      })
      .map((v) => v.id!)
    if (ids.length) return { [g.param]: ids }
  }
  return null
}

function workplaceOf(text: string | undefined): Workplace | null {
  if (!text) return null
  if (/\bremote\b/i.test(text)) return "remote"
  if (/\bhybrid\b|\bflex/i.test(text)) return "hybrid"
  return null
}

export function normalizeWorkdayListing(board: Board, p: WdPosting, forcedCountry: Country | null, now = new Date()): Job {
  const location = (p.locationsText ?? "").trim()
  const days = postedDays(p.postedOn)
  const inferred = inferCountry(location)
  return {
    id: makeId(board, p.externalPath),
    ats: "workday",
    company: board.name ?? board.company,
    title: p.title.trim(),
    location,
    locations: location ? [location] : [],
    country: inferred ?? forcedCountry,
    date: days === null ? null : dateDaysAgo(days, now),
    dateApproximate: days !== null,
    url: `${apiBase("workday", board)}/${board.site}${p.externalPath}`,
    department: null,
    employmentType: null,
    workplace: workplaceOf(location),
    salary: null,
    description: null,
    detailRef: p.externalPath,
  }
}

async function postList(board: Board, body: unknown): Promise<WdList> {
  const label = `workday:${board.company}`
  const res = await requestJson<WdList>(`${cxs(board)}/jobs`, { method: "POST", body, label })
  if (!res) throw new Error(`${label}: career site not found (check tenant, wdN host and site name)`)
  if (!Array.isArray(res.jobPostings)) throw new Error(`${label}: unexpected response shape (Workday may have changed its API)`)
  return res
}

export async function listWorkday(board: Board, hints: ListHints): Promise<ListResult> {
  const maxPerSearch = hints.maxPerSearch
  let applied: Record<string, string[]> = {}
  let countryFiltered = false
  let forcedCountry: Country | null = null

  if (hints.countries.length) {
    // One cheap request to read the tenant's location facets.
    const probe = await postList(board, { appliedFacets: {}, limit: 1, offset: 0, searchText: "" })
    const picked = pickCountryFacet(probe.facets ?? [], hints.countries)
    if (picked) {
      applied = picked
      countryFiltered = true
      forcedCountry = hints.countries.length === 1 ? hints.countries[0] : null
    }
  }

  const byPath = new Map<string, Job>()
  let truncated = false
  let skipped = 0
  const queries = hints.searchTexts.length ? hints.searchTexts : [""]
  for (const searchText of queries) {
    let offset = 0
    let total = Infinity
    while (offset < total && offset < maxPerSearch) {
      const page = await postList(board, { appliedFacets: applied, limit: PAGE, offset, searchText })
      // Workday reports `total` on the first page only; later pages say 0.
      if (offset === 0) total = page.total && page.total > 0 ? page.total : Infinity
      for (const p of page.jobPostings!) {
        // Workday occasionally lists a withdrawn posting with no title; skip it
        // rather than failing the whole tenant.
        if (typeof p?.title !== "string" || !p.title.trim() || typeof p.externalPath !== "string" || !isSafeWorkdayPath(p.externalPath)) {
          skipped++
          continue
        }
        if (!byPath.has(p.externalPath)) byPath.set(p.externalPath, normalizeWorkdayListing(board, p, forcedCountry))
      }
      if (page.jobPostings!.length < PAGE) break
      offset += PAGE
    }
    if (offset < total && offset >= maxPerSearch) truncated = true
  }
  return { jobs: [...byPath.values()], truncated, countryFiltered, skipped }
}

export async function fetchWorkdayDetail(board: Board, jobRef: string): Promise<Job | null> {
  if (!isSafeWorkdayPath(jobRef)) return null
  const res = await requestJson<WdDetail>(`${cxs(board)}${jobRef}`, { label: `workday:${board.company}` })
  const info = res?.jobPostingInfo
  if (!info || !info.title) return null
  const locations = uniq([info.location ?? "", ...(info.additionalLocations ?? [])])
  const countryName = info.country?.descriptor ?? ""
  const country = countryFromName(countryName) ?? inferCountry(info.location)
  return {
    id: makeId(board, jobRef),
    ats: "workday",
    company: board.name ?? board.company,
    title: info.title.trim(),
    location: locations.join(" | "),
    locations,
    country,
    date: toIsoDate(info.startDate),
    dateApproximate: false,
    url: info.externalUrl && info.externalUrl.startsWith("https://") ? info.externalUrl : `${apiBase("workday", board)}/${board.site}${jobRef}`,
    department: null,
    employmentType: info.timeType?.trim() || null,
    workplace: workplaceOf(info.remoteType) ?? workplaceOf(info.location),
    salary: null,
    description: htmlToText(info.jobDescription) || null,
    detailRef: jobRef,
  }
}

/** Cheap liveness check for `companies --check`: total postings on the site. */
export async function probeWorkday(board: Board): Promise<number> {
  const page = await postList(board, { appliedFacets: {}, limit: 1, offset: 0, searchText: "" })
  return page.total ?? page.jobPostings!.length
}
