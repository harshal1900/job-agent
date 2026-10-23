export const ATS_NAMES = ["greenhouse", "lever", "ashby", "workday", "amazon", "microsoft"] as const
export type Ats = (typeof ATS_NAMES)[number]

export type Country = "US" | "CA"
export type Workplace = "remote" | "hybrid" | "onsite"

/** One company job board. `ref` is the stable identifier used in job ids. */
export interface Board {
  ats: Ats
  /** Greenhouse/Lever/Ashby board token, or the Workday tenant. */
  company: string
  /** Display name; falls back to what the API reports, then the token. */
  name?: string
  /** Workday only: data-center host label (`wd5`) and career-site name. */
  host?: string
  site?: string
}

/** A posting after normalisation, independent of the ATS it came from. */
export interface Job {
  /** `<ats>:<boardRef>:<jobRef>`; pass it unchanged to `detail`. */
  id: string
  ats: Ats
  company: string
  title: string
  location: string
  locations: string[]
  country: Country | null
  /** `YYYY-MM-DD`, or null when the source gives none. */
  date: string | null
  /** True when `date` was derived from a relative label ("Posted 3 Days Ago"). */
  dateApproximate: boolean
  url: string
  department: string | null
  employmentType: string | null
  workplace: Workplace | null
  salary: string | null
  /** Plain-text description, or null when not fetched. */
  description: string | null
  /** What `detail` needs to fetch the description (Workday: the posting path). */
  detailRef: string
}

/** Server-side hints a provider may use to narrow what it downloads. */
export interface ListHints {
  /** Alternatives of the user's query; a provider may run one request each. */
  searchTexts: string[]
  countries: Country[]
  /** Most postings a provider downloads per search request (Workday paging). */
  maxPerSearch: number
}

export interface ListResult {
  jobs: Job[]
  /** True when the provider stopped early (page cap) and more jobs exist. */
  truncated: boolean
  /** True when the provider already restricted jobs to `hints.countries`. */
  countryFiltered: boolean
  /** Postings dropped because a required field (id, title, url) was missing. */
  skipped: number
}

export class CliError extends Error {
  constructor(
    message: string,
    public code: string,
  ) {
    super(message)
  }
}
