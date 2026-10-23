// Microsoft Careers (apply.careers.microsoft.com), an Eightfold "PCSX" site:
//   GET {base}/api/pcsx/search?domain=microsoft.com&query=..&location=..&start=..
//   GET {base}/api/pcsx/position_details?position_id=..&domain=microsoft.com
// The search returns 10 postings per page and no description; the detail call has
// it. The service rejects the default client and rate-limits quickly, so requests
// send browser-like headers and pages are spaced out. Unofficial: failures name
// the board so one breaking source never takes down the rest of a run.

import { apiBase, makeId } from "../boards.js"
import { requestJson } from "../http.js"
import { inferCountry, primaryCountry } from "../geo.js"
import { htmlToText, toIsoDate, uniq } from "../text.js"
import type { Board, Country, Job, ListHints, ListResult, Workplace } from "../types.js"

const PAGE = 10
const PUBLIC_BASE = "https://apply.careers.microsoft.com" // posting links stay real even when the API base is overridden
const delayEnv = Number(process.env.ATS_MICROSOFT_DELAY_MS ?? "")
const PAGE_DELAY_MS = Number.isFinite(delayEnv) && process.env.ATS_MICROSOFT_DELAY_MS ? delayEnv : 1200
const COUNTRY_NAME: Record<Country, string> = { US: "United States", CA: "Canada" }
const HEADERS = {
  "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
  Referer: "https://apply.careers.microsoft.com/careers",
}

interface MsPosition {
  id?: number | string
  displayJobId?: string
  name?: string
  standardizedLocations?: string[]
  locations?: string[]
  postedTs?: number
  department?: string
  workLocationOption?: string
  positionUrl?: string
  publicUrl?: string
  jobDescription?: string
  efcustomTextEmploymentType?: string[]
}

interface MsSearch {
  data?: { count?: number; positions?: MsPosition[] }
}

interface MsDetail {
  data?: MsPosition
}

function workplaceOf(w: string | undefined): Workplace | null {
  switch ((w ?? "").toLowerCase()) {
    case "remote":
      return "remote"
    case "hybrid":
      return "hybrid"
    case "onsite":
    case "on-site":
      return "onsite"
    default:
      return null
  }
}

const isValidMs = (p: MsPosition): boolean => !!p && p.id !== undefined && /^\d+$/.test(String(p.id)) && typeof p.name === "string" && p.name.trim() !== ""

export function normalizeMicrosoft(board: Board, p: MsPosition): Job {
  const locations = uniq(p.standardizedLocations?.length ? p.standardizedLocations : (p.locations ?? []))
  const id = String(p.id)
  return {
    id: makeId(board, id),
    ats: "microsoft",
    company: board.name ?? "Microsoft",
    title: (p.name as string).trim(),
    location: locations.join(" | "),
    locations,
    country: primaryCountry(locations) ?? inferCountry(p.locations?.[0]),
    date: typeof p.postedTs === "number" ? toIsoDate(p.postedTs * 1000) : null,
    dateApproximate: false,
    url: `${PUBLIC_BASE}/careers/job/${id}`,
    department: p.department?.trim() || null,
    employmentType: p.efcustomTextEmploymentType?.[0]?.trim() || null,
    workplace: workplaceOf(p.workLocationOption),
    salary: null,
    description: p.jobDescription ? htmlToText(p.jobDescription) || null : null,
    detailRef: id,
  }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

function searchUrl(board: Board, query: string, location: string, start: number): string {
  const q = new URLSearchParams({ domain: "microsoft.com", query, location, start: String(start), sort_by: "timestamp" })
  return `${apiBase("microsoft", board)}/api/pcsx/search?${q}`
}

export async function listMicrosoft(board: Board, hints: ListHints): Promise<ListResult> {
  const label = `microsoft:${board.company}`
  const countries = hints.countries.length ? hints.countries : (["US", "CA"] as Country[])
  const texts = hints.searchTexts.length ? hints.searchTexts : [""]
  const byId = new Map<string, Job>()
  let truncated = false
  let skipped = 0
  let first = true
  for (const text of texts) {
    for (const country of countries) {
      for (let start = 0; start < hints.maxPerSearch; start += PAGE) {
        if (!first) await sleep(PAGE_DELAY_MS)
        first = false
        const body = await requestJson<MsSearch>(searchUrl(board, text, COUNTRY_NAME[country], start), { label, headers: HEADERS })
        const positions = body?.data?.positions
        if (!body || !Array.isArray(positions)) throw new Error(`${label}: unexpected response shape`)
        for (const p of positions) {
          if (!isValidMs(p)) {
            skipped++
            continue
          }
          const job = normalizeMicrosoft(board, p)
          byId.set(job.id, job)
        }
        const total = body.data?.count ?? 0
        if (positions.length < PAGE || start + PAGE >= total) break
        if (start + PAGE >= hints.maxPerSearch) truncated = true
      }
    }
  }
  return { jobs: [...byId.values()], truncated, countryFiltered: true, skipped }
}

export async function fetchMicrosoftDetail(board: Board, jobRef: string): Promise<Job | null> {
  if (!/^\d{1,20}$/.test(jobRef)) return null
  const q = new URLSearchParams({ position_id: jobRef, domain: "microsoft.com", hl: "en" })
  const body = await requestJson<MsDetail>(`${apiBase("microsoft", board)}/api/pcsx/position_details?${q}`, { label: `microsoft:${board.company}`, headers: HEADERS })
  return body?.data && isValidMs(body.data) ? normalizeMicrosoft(board, body.data) : null
}

export async function probeMicrosoft(board: Board): Promise<number> {
  const body = await requestJson<MsSearch>(searchUrl(board, "", "United States", 0), { label: `microsoft:${board.company}`, headers: HEADERS })
  if (!body?.data || typeof body.data.count !== "number") throw new Error(`microsoft:${board.company}: unexpected response shape`)
  return body.data.count
}
