// Ashby public job-board API: https://developers.ashbyhq.com/docs/public-job-posting-api
// One request lists every listed posting with its description and (optionally)
// compensation included.

import { apiBase, makeId } from "../boards.js"
import { requestJson } from "../http.js"
import { primaryCountry } from "../geo.js"
import { htmlToText, toIsoDate, uniq } from "../text.js"
import type { Board, Job, ListHints, ListResult, Workplace } from "../types.js"

interface AshbyJob {
  id: string
  title: string
  department?: string
  team?: string
  employmentType?: string
  location?: string
  secondaryLocations?: { location?: string; address?: { postalAddress?: { addressCountry?: string } } }[]
  address?: { postalAddress?: { addressCountry?: string } }
  publishedAt?: string
  isListed?: boolean
  isRemote?: boolean
  workplaceType?: string
  jobUrl: string
  descriptionHtml?: string
  descriptionPlain?: string
  compensation?: { compensationTierSummary?: string; scrapeableCompensationSalarySummary?: string } | null
}

function workplaceOf(j: AshbyJob): Workplace | null {
  switch ((j.workplaceType ?? "").toLowerCase()) {
    case "remote":
      return "remote"
    case "hybrid":
      return "hybrid"
    case "onsite":
    case "on-site":
      return "onsite"
  }
  return j.isRemote ? "remote" : null
}

const isValidAshby = (j: AshbyJob): boolean =>
  !!j && typeof j.id === "string" && typeof j.title === "string" && j.title.trim() !== "" && typeof j.jobUrl === "string"

export function normalizeAshby(board: Board, j: AshbyJob): Job {
  const locations = uniq([j.location ?? "", ...(j.secondaryLocations ?? []).map((s) => s.location ?? "")])
  const description = j.descriptionPlain?.trim() || htmlToText(j.descriptionHtml)
  return {
    id: makeId(board, j.id),
    ats: "ashby",
    company: board.name ?? board.company,
    title: j.title.trim(),
    location: locations.join(" | "),
    locations,
    country: primaryCountry(locations),
    date: toIsoDate(j.publishedAt),
    dateApproximate: false,
    url: j.jobUrl,
    department: j.team?.trim() || j.department?.trim() || null,
    employmentType: j.employmentType?.trim() || null,
    workplace: workplaceOf(j),
    salary: j.compensation?.scrapeableCompensationSalarySummary?.trim() || j.compensation?.compensationTierSummary?.trim() || null,
    description: description || null,
    detailRef: j.id,
  }
}

export async function listAshby(board: Board, _hints: ListHints): Promise<ListResult> {
  const label = `ashby:${board.company}`
  const body = await requestJson<{ jobs?: AshbyJob[] }>(
    `${apiBase("ashby")}/posting-api/job-board/${board.company}?includeCompensation=true`,
    { label },
  )
  if (!body) throw new Error(`${label}: board not found (check the board token)`)
  const listed = (body.jobs ?? []).filter((j) => j?.isListed !== false)
  const valid = listed.filter(isValidAshby)
  return { jobs: valid.map((j) => normalizeAshby(board, j)), truncated: false, countryFiltered: false, skipped: listed.length - valid.length }
}

/** Ashby has no single-posting endpoint; look the id up in the board listing. */
export async function fetchAshbyDetail(board: Board, jobRef: string): Promise<Job | null> {
  const body = await requestJson<{ jobs?: AshbyJob[] }>(
    `${apiBase("ashby")}/posting-api/job-board/${board.company}?includeCompensation=true`,
    { label: `ashby:${board.company}` },
  )
  const hit = body?.jobs?.find((j) => j.id === jobRef)
  return hit ? normalizeAshby(board, hit) : null
}
