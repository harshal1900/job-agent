// Amazon Jobs (amazon.jobs). The careers site is a single-page app over a public
// JSON search endpoint that returns every field, description included:
//   GET {base}/en/search.json?base_query=..&country[]=USA&result_limit=100&offset=..
// Unofficial, so it can change without notice; a failure names the board.

import { apiBase, makeId } from "../boards.js"
import { requestJson } from "../http.js"
import { primaryCountry } from "../geo.js"
import { htmlToText, uniq } from "../text.js"
import type { Board, Country, Job, ListHints, ListResult } from "../types.js"

const PAGE = 100
const PUBLIC_BASE = "https://www.amazon.jobs" // posting links stay real even when the API base is overridden
const COUNTRY_CODE: Record<Country, string> = { US: "USA", CA: "CAN" }
const MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]

interface AmazonJob {
  id_icims?: string
  title?: string
  job_path?: string
  location?: string
  normalized_location?: string
  locations?: string[]
  country_code?: string
  posted_date?: string
  job_category?: string
  job_schedule_type?: string
  description?: string
  basic_qualifications?: string
  preferred_qualifications?: string
}

interface AmazonList {
  hits?: number
  jobs?: AmazonJob[]
}

/** "October 23, 2026" -> "2026-10-23"; null for anything else. */
export function amazonDate(text: string | undefined): string | null {
  const m = /^([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})$/.exec((text ?? "").trim())
  const month = m ? MONTHS.indexOf(m[1].toLowerCase()) : -1
  if (!m || month < 0) return null
  return `${m[3]}-${String(month + 1).padStart(2, "0")}-${m[2].padStart(2, "0")}`
}

function cityList(j: AmazonJob): string[] {
  const parsed: string[] = []
  for (const raw of j.locations ?? []) {
    try {
      const o = JSON.parse(raw) as { city?: string; normalizedStateName?: string; normalizedCountryCode?: string }
      const text = [o.city, o.normalizedStateName, o.normalizedCountryCode].filter(Boolean).join(", ")
      if (text) parsed.push(text)
    } catch {
      /* a malformed location entry is skipped; normalized_location still applies */
    }
  }
  return uniq(parsed.length ? parsed : [j.normalized_location ?? j.location ?? ""])
}

const isValidAmazon = (j: AmazonJob): boolean =>
  !!j && typeof j.id_icims === "string" && /^\d+$/.test(j.id_icims) && typeof j.title === "string" && j.title.trim() !== "" && typeof j.job_path === "string"

export function normalizeAmazon(board: Board, j: AmazonJob): Job {
  const locations = cityList(j)
  const description = [j.description, j.basic_qualifications && `Basic qualifications\n${j.basic_qualifications}`, j.preferred_qualifications && `Preferred qualifications\n${j.preferred_qualifications}`]
    .filter(Boolean)
    .map((h) => htmlToText(h as string))
    .join("\n\n")
    .trim()
  const code = j.country_code === "USA" ? "US" : j.country_code === "CAN" ? "CA" : null
  return {
    id: makeId(board, j.id_icims as string),
    ats: "amazon",
    company: board.name ?? "Amazon",
    title: (j.title as string).trim(),
    location: locations.join(" | "),
    locations,
    country: code ?? primaryCountry(locations),
    date: amazonDate(j.posted_date),
    dateApproximate: false,
    url: `${PUBLIC_BASE}${j.job_path}`,
    department: j.job_category?.trim() || null,
    employmentType: j.job_schedule_type?.trim() || null,
    workplace: null,
    salary: null,
    description: description || null,
    detailRef: j.id_icims as string,
  }
}

function searchUrl(board: Board, params: [string, string][]): string {
  const q = new URLSearchParams()
  for (const [k, v] of params) q.append(k, v)
  return `${apiBase("amazon", board)}/en/search.json?${q}`
}

export async function listAmazon(board: Board, hints: ListHints): Promise<ListResult> {
  const label = `amazon:${board.company}`
  const countries = (hints.countries.length ? hints.countries : (["US", "CA"] as Country[])).map((c) => ["country[]", COUNTRY_CODE[c]] as [string, string])
  const texts = hints.searchTexts.length ? hints.searchTexts : [""]
  const byId = new Map<string, Job>()
  let truncated = false
  let skipped = 0
  for (const text of texts) {
    for (let offset = 0; offset < hints.maxPerSearch; offset += PAGE) {
      const limit = Math.min(PAGE, hints.maxPerSearch - offset)
      const body = await requestJson<AmazonList>(
        searchUrl(board, [["base_query", text], ...countries, ["sort", "recent"], ["result_limit", String(limit)], ["offset", String(offset)]]),
        { label },
      )
      if (!body || !Array.isArray(body.jobs)) throw new Error(`${label}: unexpected response shape`)
      for (const j of body.jobs) {
        if (!isValidAmazon(j)) {
          skipped++
          continue
        }
        const job = normalizeAmazon(board, j)
        byId.set(job.id, job)
      }
      const more = (body.hits ?? 0) > offset + body.jobs.length && body.jobs.length === limit
      if (!more) break
      if (offset + PAGE >= hints.maxPerSearch) truncated = true
    }
  }
  return { jobs: [...byId.values()], truncated, countryFiltered: true, skipped }
}

export async function fetchAmazonDetail(board: Board, jobRef: string): Promise<Job | null> {
  if (!/^\d{1,12}$/.test(jobRef)) return null
  const body = await requestJson<AmazonList>(searchUrl(board, [["base_query", jobRef], ["result_limit", "5"]]), { label: `amazon:${board.company}` })
  const hit = body?.jobs?.find((j) => j.id_icims === jobRef)
  return hit && isValidAmazon(hit) ? normalizeAmazon(board, hit) : null
}

export async function probeAmazon(board: Board): Promise<number> {
  const body = await requestJson<AmazonList>(searchUrl(board, [["result_limit", "1"]]), { label: `amazon:${board.company}` })
  if (!body || typeof body.hits !== "number") throw new Error(`amazon:${board.company}: unexpected response shape`)
  return body.hits
}
