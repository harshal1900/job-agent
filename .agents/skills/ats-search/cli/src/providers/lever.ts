// Lever Postings API (github lever/postings-api)
// One request lists every posting with its description included.

import { apiBase, makeId } from "../boards.js"
import { requestJson } from "../http.js"
import { primaryCountry } from "../geo.js"
import { toIsoDate, uniq } from "../text.js"
import type { Board, Job, ListHints, ListResult, Workplace } from "../types.js"

interface LeverPosting {
  id: string
  text: string
  hostedUrl: string
  createdAt?: number
  workplaceType?: string
  country?: string
  categories?: { commitment?: string; location?: string; team?: string; department?: string; allLocations?: string[] }
  descriptionPlain?: string
  additionalPlain?: string
  lists?: { text: string; content: string }[]
  salaryRange?: { min?: number; max?: number; currency?: string; interval?: string } | null
}

function workplaceOf(w: string | undefined): Workplace | null {
  switch ((w ?? "").toLowerCase()) {
    case "remote":
      return "remote"
    case "hybrid":
      return "hybrid"
    case "on-site":
    case "onsite":
      return "onsite"
    default:
      return null
  }
}

function salaryOf(r: LeverPosting["salaryRange"]): string | null {
  if (!r || r.min === undefined || r.max === undefined) return null
  const fmt = (n: number) => n.toLocaleString("en-US", { maximumFractionDigits: 0 })
  return `${r.currency ?? "USD"} ${fmt(r.min)} – ${fmt(r.max)}${r.interval ? ` ${r.interval.replace(/^per-/, "per ")}` : ""}`
}

function descriptionOf(p: LeverPosting): string {
  // `lists` carry the requirement bullets as HTML fragments.
  const lists = (p.lists ?? [])
    .map((l) => `${l.text}\n${l.content.replace(/<li[^>]*>/gi, "- ").replace(/<\/li>/gi, "\n").replace(/<[^>]+>/g, "").trim()}`)
    .join("\n\n")
  return [p.descriptionPlain, lists, p.additionalPlain].filter((s) => s && s.trim()).join("\n\n").trim()
}

const isValidLever = (p: LeverPosting): boolean =>
  !!p && typeof p.id === "string" && typeof p.text === "string" && p.text.trim() !== "" && typeof p.hostedUrl === "string"

export function normalizeLever(board: Board, p: LeverPosting): Job {
  const all = uniq([p.categories?.location ?? "", ...(p.categories?.allLocations ?? [])])
  const location = all.join(" | ")
  const countryHint = p.country === "US" || p.country === "CA" ? p.country : null
  return {
    id: makeId(board, p.id),
    ats: "lever",
    company: board.name ?? board.company,
    title: p.text.trim(),
    location,
    locations: all,
    country: countryHint ?? primaryCountry(all),
    date: toIsoDate(p.createdAt),
    dateApproximate: false,
    url: p.hostedUrl,
    department: p.categories?.team?.trim() || p.categories?.department?.trim() || null,
    employmentType: p.categories?.commitment?.trim() || null,
    workplace: workplaceOf(p.workplaceType),
    salary: salaryOf(p.salaryRange),
    description: descriptionOf(p) || null,
    detailRef: p.id,
  }
}

export async function listLever(board: Board, _hints: ListHints): Promise<ListResult> {
  const label = `lever:${board.company}`
  const body = await requestJson<LeverPosting[]>(`${apiBase("lever")}/v0/postings/${board.company}?mode=json`, { label })
  if (!body) throw new Error(`${label}: board not found (check the board token)`)
  if (!Array.isArray(body)) throw new Error(`${label}: unexpected response shape`)
  const valid = body.filter(isValidLever)
  return { jobs: valid.map((p) => normalizeLever(board, p)), truncated: false, countryFiltered: false, skipped: body.length - valid.length }
}

export async function fetchLeverDetail(board: Board, jobRef: string): Promise<Job | null> {
  if (!/^[0-9a-f-]{8,64}$/i.test(jobRef)) return null
  const p = await requestJson<LeverPosting>(`${apiBase("lever")}/v0/postings/${board.company}/${jobRef}`, { label: `lever:${board.company}` })
  return p && p.id ? normalizeLever(board, p) : null
}
