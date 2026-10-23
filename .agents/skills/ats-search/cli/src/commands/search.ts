import { PROVIDERS } from "../providers/index.js"
import { countriesOf, inCountries } from "../geo.js"
import { mapPool } from "../http.js"
import { compareJobs, matchesLocationText, matchesQuery, matchesWorkplace, parseQuery } from "../query.js"
import { ageInDays } from "../text.js"
import { CliError, type Board, type Country, type Job, type Workplace } from "../types.js"
import { writeWarning } from "../output.js"

export interface SearchOpts {
  boards: Board[]
  query?: string
  countries: Country[]
  location?: string
  workplace: Workplace[]
  jobage?: number
  limit: number
  offset: number
  includeUnspecifiedLocation: boolean
  includeDescription: boolean
  maxPerBoard: number
  format: "json" | "table" | "plain"
}

export interface BoardFailure {
  board: string
  error: string
}

export interface SearchOutcome {
  jobs: Job[]
  boardOf: Map<string, Board>
  totalMatches: number
  boardsSearched: number
  failures: BoardFailure[]
  truncatedBoards: string[]
  droppedOutsideCountries: number
  droppedUnknownDate: number
  skippedMalformed: number
}

const BOARD_CONCURRENCY = 6
const DETAIL_CONCURRENCY = 6

function label(b: Board): string {
  return b.ats === "workday" ? `workday:${b.company}` : `${b.ats}:${b.company}`
}

/** The plain output object for one job: the field contract /scrape consumes. */
export function toResult(job: Job, includeDescription: boolean): Record<string, unknown> {
  const result: Record<string, unknown> = {
    id: job.id,
    ats: job.ats,
    title: job.title,
    company: job.company,
    location: job.location || null,
    date: job.date,
    url: job.url,
    country: job.country,
    countries: [...new Set([...(job.country ? [job.country] : []), ...countriesOf(job.locations)])].sort(),
    department: job.department,
    employment_type: job.employmentType,
    workplace: job.workplace,
    salary: job.salary,
    date_approximate: job.dateApproximate,
  }
  if (includeDescription) result.description = job.description
  return result
}

export async function collectJobs(opts: SearchOpts): Promise<SearchOutcome> {
  const alternatives = parseQuery(opts.query)
  const hints = { searchTexts: alternatives.map((a) => a.join(" ")), countries: opts.countries, maxPerSearch: opts.maxPerBoard }
  const failures: BoardFailure[] = []
  const truncatedBoards: string[] = []
  const matched: Job[] = []
  const boardOf = new Map<string, Board>()
  let droppedOutsideCountries = 0
  let droppedUnknownDate = 0
  let skippedMalformed = 0

  await mapPool(opts.boards, BOARD_CONCURRENCY, async (board) => {
    let res
    try {
      res = await PROVIDERS[board.ats].list(board, hints)
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e)
      failures.push({ board: label(board), error })
      writeWarning(error, e instanceof CliError ? e.code : "BOARD_FAILED")
      return
    }
    if (res.truncated) truncatedBoards.push(label(board))
    skippedMalformed += res.skipped
    for (const job of res.jobs) {
      if (!matchesQuery(job, alternatives)) continue
      if (!matchesWorkplace(job, opts.workplace)) continue
      if (!matchesLocationText(job, opts.location)) continue
      if (opts.countries.length) {
        const named = countriesOf(job.locations)
        const wanted = inCountries(job.locations, opts.countries) || (job.country !== null && opts.countries.includes(job.country))
        // A board the server already narrowed is trusted when the location text says
        // nothing ("3 Locations"), but not against text that names another country.
        const known = res.countryFiltered ? wanted || named.size === 0 : wanted
        if (!known) {
          // "Remote" or a blank location says nothing about the country.
          const unspecified = job.locations.every((l) => /^(remote|anywhere|global|worldwide|distributed)?\W*$/i.test(l))
          if (!(unspecified && opts.includeUnspecifiedLocation)) {
            droppedOutsideCountries++
            continue
          }
        }
      }
      if (opts.jobage !== undefined) {
        const age = ageInDays(job.date)
        if (age === null) {
          droppedUnknownDate++
          continue
        }
        if (age > opts.jobage) continue
      }
      matched.push(job)
      boardOf.set(job.id, board)
    }
  })

  matched.sort(compareJobs)
  return {
    jobs: matched,
    boardOf,
    totalMatches: matched.length,
    boardsSearched: opts.boards.length - failures.length,
    failures,
    truncatedBoards: truncatedBoards.sort(),
    droppedOutsideCountries,
    droppedUnknownDate,
    skippedMalformed,
  }
}

/** Fetch descriptions for the jobs the list endpoint did not include them for. */
export async function hydrate(jobs: Job[], boardOf: Map<string, Board>): Promise<BoardFailure[]> {
  const failures: BoardFailure[] = []
  await mapPool(jobs, DETAIL_CONCURRENCY, async (job, i) => {
    const board = boardOf.get(job.id)
    if (!board || job.description !== null || PROVIDERS[job.ats].listHasDescriptions) return
    try {
      const detail = await PROVIDERS[job.ats].detail(board, job.detailRef)
      if (!detail) return
      jobs[i] = {
        ...job,
        description: detail.description,
        // Workday lists "2 Locations" and a relative date; the posting has the real ones.
        ...(job.ats === "workday"
          ? {
              location: detail.location || job.location,
              locations: detail.locations.length ? detail.locations : job.locations,
              country: detail.country ?? job.country,
              date: detail.date ?? job.date,
              dateApproximate: detail.date ? false : job.dateApproximate,
              employmentType: detail.employmentType ?? job.employmentType,
              workplace: detail.workplace ?? job.workplace,
            }
          : { salary: detail.salary ?? job.salary }),
      }
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e)
      failures.push({ board: label(board), error })
      writeWarning(error, e instanceof CliError ? e.code : "DETAIL_FAILED")
    }
  })
  return failures
}
