// Board references: parsing `--board` specs and job ids, building API URLs.
// Every token that ends up inside a URL path is validated here, so a hostile
// job id or config entry can never redirect a request to another host or path.

import { ATS_NAMES, CliError, type Ats, type Board } from "./types.js"

const TOKEN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/
const WORKDAY_HOST = /^wd\d{1,3}$/
const WORKDAY_SITE = /^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$/

/** Base URLs, overridable per ATS (tests point them at a local server). */
export function apiBase(ats: Ats, board?: Board): string {
  const env = process.env[`ATS_${ats.toUpperCase()}_URL`]?.trim().replace(/\/+$/, "")
  if (env) return env
  switch (ats) {
    case "greenhouse":
      return "https://boards-api.greenhouse.io"
    case "lever":
      return "https://api.lever.co"
    case "ashby":
      return "https://api.ashbyhq.com"
    case "amazon":
      return "https://www.amazon.jobs"
    case "microsoft":
      return "https://apply.careers.microsoft.com"
    case "workday":
      if (!board?.host) throw new CliError("workday board needs a host (wd1, wd5, ...)", "BAD_BOARD")
      return `https://${board.company}.${board.host}.myworkdayjobs.com`
  }
}

export function validateBoard(b: Board): Board {
  if (!ATS_NAMES.includes(b.ats)) throw new CliError(`unknown ats "${b.ats}" (want ${ATS_NAMES.join("|")})`, "BAD_BOARD")
  if (!TOKEN.test(b.company)) throw new CliError(`invalid ${b.ats} board token "${b.company}"`, "BAD_BOARD")
  if (b.ats === "workday") {
    if (!b.host || !WORKDAY_HOST.test(b.host)) throw new CliError(`workday board "${b.company}" needs host like wd5`, "BAD_BOARD")
    if (!b.site || !WORKDAY_SITE.test(b.site)) throw new CliError(`workday board "${b.company}" needs a valid site name`, "BAD_BOARD")
  }
  return b
}

/** Stable board identifier used inside job ids. */
export function boardRef(b: Board): string {
  return b.ats === "workday" ? `${b.company}.${b.host}/${b.site}` : b.company
}

export function parseBoardRef(ats: Ats, ref: string): Board {
  if (ats !== "workday") return validateBoard({ ats, company: ref })
  const m = /^([^./]+)\.(wd\d+)\/(.+)$/.exec(ref)
  if (!m) throw new CliError(`bad workday board "${ref}", want <tenant>.<wdN>/<site>`, "BAD_BOARD")
  return validateBoard({ ats, company: m[1], host: m[2], site: m[3] })
}

/**
 * Parse a `--board` spec: `greenhouse:stripe`, `lever:palantir`, `ashby:ramp`,
 * or `workday:nvidia.wd5/NVIDIAExternalCareerSite`.
 */
export function parseBoardSpec(spec: string): Board {
  const i = spec.indexOf(":")
  if (i <= 0) throw new CliError(`invalid --board "${spec}", want <ats>:<company> (e.g. greenhouse:stripe)`, "BAD_ARG")
  const ats = spec.slice(0, i).toLowerCase() as Ats
  if (!ATS_NAMES.includes(ats)) throw new CliError(`invalid --board "${spec}": unknown ats "${ats}"`, "BAD_ARG")
  return parseBoardRef(ats, spec.slice(i + 1))
}

export interface ParsedId {
  board: Board
  jobRef: string
}

/** Parse `<ats>:<boardRef>:<jobRef>` as emitted in search results. */
export function parseJobId(id: string): ParsedId {
  const first = id.indexOf(":")
  const second = first < 0 ? -1 : id.indexOf(":", first + 1)
  if (first <= 0 || second < 0) throw new CliError(`bad job id "${id}", want <ats>:<board>:<job>`, "BAD_ID")
  const ats = id.slice(0, first) as Ats
  if (!ATS_NAMES.includes(ats)) throw new CliError(`bad job id "${id}": unknown ats`, "BAD_ID")
  const jobRef = id.slice(second + 1)
  if (!jobRef || /[\s?#]/.test(jobRef)) throw new CliError(`bad job id "${id}"`, "BAD_ID")
  try {
    return { board: parseBoardRef(ats, id.slice(first + 1, second)), jobRef }
  } catch (e) {
    throw new CliError(e instanceof Error ? e.message : String(e), "BAD_ID")
  }
}

/**
 * Turn a public posting URL into a job id. Only the ATS hosts themselves are
 * accepted: an employer's own careers page (`stripe.com/jobs?gh_jid=...`) says
 * nothing about which board it came from, so it is rejected rather than guessed.
 */
export function parseJobUrl(raw: string): ParsedId {
  let u: URL
  try {
    u = new URL(raw)
  } catch {
    throw new CliError(`"${raw}" is neither a job id nor a URL`, "BAD_ID")
  }
  if (u.protocol !== "https:") throw new CliError("only https posting URLs are accepted", "BAD_ID")
  const host = u.hostname.toLowerCase()
  const parts = u.pathname.split("/").filter(Boolean)
  const fail = () => new CliError(`cannot map ${host}${u.pathname} to a job; use the id from a search result`, "BAD_ID")

  if (host === "boards.greenhouse.io" || host === "job-boards.greenhouse.io") {
    // /<company>/jobs/<id>
    if (parts.length >= 3 && parts[1] === "jobs" && /^\d+$/.test(parts[2])) {
      return { board: validateBoard({ ats: "greenhouse", company: parts[0] }), jobRef: parts[2] }
    }
    throw fail()
  }
  if (host === "jobs.lever.co") {
    if (parts.length >= 2) return { board: validateBoard({ ats: "lever", company: parts[0] }), jobRef: parts[1] }
    throw fail()
  }
  if (host === "jobs.ashbyhq.com") {
    if (parts.length >= 2) return { board: validateBoard({ ats: "ashby", company: parts[0] }), jobRef: parts[1] }
    throw fail()
  }
  const wd = /^([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com$/.exec(host)
  if (wd) {
    // /[<locale>/]<site>/job/<location>/<slug>
    const jobAt = parts.indexOf("job")
    if (jobAt > 0 && parts.length > jobAt + 1) {
      const site = parts[jobAt - 1]
      return {
        board: validateBoard({ ats: "workday", company: wd[1], host: wd[2], site }),
        jobRef: "/" + parts.slice(jobAt).join("/"),
      }
    }
    throw fail()
  }
  if (host === "www.amazon.jobs" || host === "amazon.jobs") {
    // /<locale>/jobs/<id>/<slug>
    const at = parts.indexOf("jobs")
    if (at >= 0 && /^\d+$/.test(parts[at + 1] ?? "")) return { board: validateBoard({ ats: "amazon", company: "amazon" }), jobRef: parts[at + 1] }
    throw fail()
  }
  if (host === "apply.careers.microsoft.com") {
    // /careers/job/<id>
    const at = parts.indexOf("job")
    if (at >= 0 && /^\d+$/.test(parts[at + 1] ?? "")) return { board: validateBoard({ ats: "microsoft", company: "microsoft" }), jobRef: parts[at + 1] }
    throw fail()
  }
  throw new CliError(`host ${host} is not a supported ATS (greenhouse, lever, ashby, workday, amazon, microsoft)`, "BAD_ID")
}

export function parseIdOrUrl(input: string): ParsedId {
  return /^https?:\/\//i.test(input) ? parseJobUrl(input) : parseJobId(input)
}

export function makeId(board: Board, jobRef: string): string {
  return `${board.ats}:${boardRef(board)}:${jobRef}`
}
