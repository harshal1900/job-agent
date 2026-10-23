#!/usr/bin/env bun
// ats-search: search the public job boards of the companies you watch on
// Greenhouse, Lever, Ashby and Workday, filtered to the US and Canada.
// Zero runtime dependencies; reads are anonymous.

import { parseBoardSpec } from "./boards.js"
import { loadConfig } from "./config.js"
import { runCompanies } from "./commands/companies.js"
import { runDetail } from "./commands/detail.js"
import { collectJobs, hydrate, toResult, type SearchOpts } from "./commands/search.js"
import { renderTable, writeError } from "./output.js"
import { parseQuery } from "./query.js"
import { ATS_NAMES, CliError, type Ats, type Board, type Country, type Workplace } from "./types.js"

// Flags that never take a value. Declaring them keeps `--no-description foo`
// from swallowing `foo` as the flag's value.
const BOOLEAN_FLAGS = new Set(["no-description", "include-unspecified-location", "check", "help", "h"])
const REPEATABLE = new Set(["board"])
const ALIAS: Record<string, string> = { q: "query", n: "limit" }

const KNOWN: Record<string, Set<string>> = {
  search: new Set([
    "query", "ats", "company", "country", "location", "remote", "jobage", "limit", "offset", "page", "format",
    "board", "companies", "max-per-board", "no-description", "include-unspecified-location", "help", "h",
  ]),
  detail: new Set(["format", "help", "h"]),
  companies: new Set(["ats", "board", "companies", "check", "help", "h"]),
}

interface Flags {
  _: string[]
  [k: string]: string | boolean | string[]
}

export function parseFlags(argv: string[]): Flags {
  const flags: Flags = { _: [] }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (!a.startsWith("-") || a === "-") {
      flags._.push(a)
      continue
    }
    const name = a.replace(/^-+/, "")
    const eq = name.indexOf("=")
    const rawKey = eq >= 0 ? name.slice(0, eq) : name
    const key = ALIAS[rawKey] ?? rawKey
    let value: string | boolean = true
    if (eq >= 0) value = name.slice(eq + 1)
    else if (!BOOLEAN_FLAGS.has(key) && argv[i + 1] !== undefined && !argv[i + 1].startsWith("-")) value = argv[++i]
    if (REPEATABLE.has(key)) {
      const acc = Array.isArray(flags[key]) ? (flags[key] as string[]) : []
      acc.push(typeof value === "string" ? value : "")
      flags[key] = acc
    } else {
      flags[key] = value
    }
  }
  return flags
}

const HELP = `ats-search — search company job boards on Greenhouse, Lever, Ashby and Workday (US & Canada)

USAGE
  bun run src/cli.ts search [-q "<keywords>"] [filters] [--format json|table|plain]
  bun run src/cli.ts detail <job-id|posting-url> [--format json|plain]
  bun run src/cli.ts companies [--check]

WATCHLIST
  Boards come from config/target_companies.json (repo root). Override with
  --companies <file> or ATS_COMPANIES, and add ad-hoc boards with --board
  (repeatable): greenhouse:stripe  lever:palantir  ashby:ramp
                workday:nvidia.wd5/NVIDIAExternalCareerSite

SEARCH FLAGS
  --query, -q <text>          Words that must appear in the title or department.
                              "a OR b" matches either (uppercase OR, max 5);
                              "quoted phrase" matches the phrase.
  --country <us|ca|us,ca>     Default us,ca. Inferred from the location text.
  --location <text>           Only locations containing this text (e.g. Seattle).
  --remote <mode>             remote | hybrid | onsite (comma = OR; bare = remote).
  --jobage <days>             Posted within N days (jobs with no date are dropped).
  --ats <list>                Restrict to greenhouse,lever,ashby,workday.
  --company <text>            Only boards whose token or name contains this (comma = OR).
  --limit, -n <n>             Results to return. Default 25.
  --page <n>                  1-indexed page of --limit results. Default 1.
  --offset <n>                Skip the first n results instead of using --page.
  --include-unspecified-location
                              Keep jobs whose location is just "Remote" or blank.
  --max-per-board <n>         Workday only: postings downloaded per query and board
                              (min 20, default 100). Raise it for big tenants.
  --no-description            Skip fetching descriptions (faster discovery pass).
  --format <fmt>              json (default) | table | plain.

Reads are anonymous. See SKILL.md for output fields, limits and caveats.
`

function fail(message: string, code = "BAD_ARG"): never {
  throw new CliError(message, code)
}

function str(flags: Flags, name: string): string | undefined {
  const v = flags[name]
  if (v === undefined) return undefined
  if (typeof v !== "string" || !v.trim()) fail(`--${name} requires a non-empty value`)
  return v.trim()
}

function intFlag(flags: Flags, name: string, min: number, fallback: number): number {
  const raw = str(flags, name)
  if (raw === undefined) return fallback
  const n = Number(raw)
  if (!Number.isInteger(n) || n < min) fail(`--${name} must be a whole number of at least ${min}, got "${raw}"`)
  return n
}

function list(raw: string | undefined): string[] {
  return (raw ?? "").split(",").map((s) => s.trim()).filter(Boolean)
}

function parseCountries(raw: string | undefined): Country[] {
  if (raw === undefined) return ["US", "CA"]
  const out = new Set<Country>()
  for (const item of list(raw)) {
    const c = item.toUpperCase()
    if (c === "US" || c === "USA") out.add("US")
    else if (c === "CA" || c === "CAN" || c === "CANADA") out.add("CA")
    else fail(`--country must be us, ca or us,ca, got "${item}"`)
  }
  if (out.size === 0) fail("--country requires at least one of us, ca")
  return [...out]
}

function parseWorkplace(flags: Flags): Workplace[] {
  const v = flags.remote
  if (v === undefined) return []
  if (v === true) return ["remote"]
  const out = new Set<Workplace>()
  for (const item of list(typeof v === "string" ? v : "")) {
    const t = item.toLowerCase()
    if (t === "remote") out.add("remote")
    else if (t === "hybrid") out.add("hybrid")
    else if (t === "onsite" || t === "on-site") out.add("onsite")
    else fail(`--remote must be one of remote|hybrid|onsite, got "${item}"`)
  }
  if (out.size === 0) fail(`--remote must be one of remote|hybrid|onsite`)
  return [...out]
}

function resolveBoards(flags: Flags): Board[] {
  const companiesFlag = str(flags, "companies") ?? (process.env.ATS_COMPANIES?.trim() || undefined)
  let boards = loadConfig(companiesFlag, companiesFlag !== undefined)
  const extra = (Array.isArray(flags.board) ? flags.board : []).map((spec) => parseBoardSpec(spec))
  if (extra.length) {
    const keys = new Set(boards.map((b) => `${b.ats}:${b.company}:${b.site ?? ""}`.toLowerCase()))
    for (const b of extra) if (!keys.has(`${b.ats}:${b.company}:${b.site ?? ""}`.toLowerCase())) boards.push(b)
  }
  const atsFilter = list(str(flags, "ats"))
  if (atsFilter.length) {
    for (const a of atsFilter) if (!ATS_NAMES.includes(a.toLowerCase() as Ats)) fail(`--ats must be a list of ${ATS_NAMES.join("|")}, got "${a}"`)
    const wanted = new Set(atsFilter.map((a) => a.toLowerCase()))
    boards = boards.filter((b) => wanted.has(b.ats))
  }
  const companyFilter = list(str(flags, "company")).map((c) => c.toLowerCase())
  if (companyFilter.length) {
    boards = boards.filter((b) => companyFilter.some((c) => b.company.toLowerCase().includes(c) || (b.name ?? "").toLowerCase().includes(c)))
  }
  if (boards.length === 0) {
    fail(
      "no boards to search: add companies to config/target_companies.json, pass --board <ats>:<company>, or loosen --ats/--company",
      "NO_BOARDS",
    )
  }
  return boards
}

async function main(): Promise<number> {
  const flags = parseFlags(process.argv.slice(2))
  const cmd = flags._[0]
  if (!cmd || flags.help || flags.h) {
    process.stdout.write(HELP)
    return cmd ? 0 : 1
  }
  const known = KNOWN[cmd]
  if (!known) fail(`Unknown command "${cmd}"`, "BAD_CMD")
  for (const key of Object.keys(flags)) {
    if (key === "_" || known.has(key)) continue
    fail(
      `unknown flag --${key} for '${cmd}' - flags are never silently ignored, because a discarded filter changes what the search returns; see --help`,
      "UNKNOWN_FLAG",
    )
  }

  if (cmd === "companies") {
    return runCompanies({ boards: resolveBoards(flags), check: flags.check === true })
  }

  if (cmd === "detail") {
    const id = flags._[1]
    if (!id) fail("detail requires a <job-id|posting-url>", "NO_ID")
    const format = str(flags, "format") ?? "json"
    if (format !== "json" && format !== "plain") fail(`--format must be one of json|plain, got "${format}"`)
    return runDetail({ id, format })
  }

  const format = str(flags, "format") ?? "json"
  if (format !== "json" && format !== "table" && format !== "plain") fail(`--format must be one of json|table|plain, got "${format}"`)
  const opts: SearchOpts = {
    boards: [], // resolved below, after every cheaper argument check
    query: str(flags, "query"),
    countries: parseCountries(str(flags, "country")),
    location: str(flags, "location"),
    workplace: parseWorkplace(flags),
    jobage: flags.jobage === undefined ? undefined : intFlag(flags, "jobage", 1, 1),
    limit: intFlag(flags, "limit", 1, 25),
    offset: 0,
    includeUnspecifiedLocation: flags["include-unspecified-location"] === true,
    includeDescription: flags["no-description"] !== true,
    maxPerBoard: intFlag(flags, "max-per-board", 20, 100),
    format,
  }
  parseQuery(opts.query) // reject a malformed query before touching the network
  if (flags.offset !== undefined && flags.page !== undefined) fail("use either --offset or --page, not both")
  opts.offset = flags.page !== undefined ? (intFlag(flags, "page", 1, 1) - 1) * opts.limit : intFlag(flags, "offset", 0, 0)
  opts.boards = resolveBoards(flags)

  const outcome = await collectJobs(opts)
  if (outcome.boardsSearched === 0) {
    fail(`every board failed: ${outcome.failures.map((f) => f.board).join(", ")}`, "ALL_BOARDS_FAILED")
  }
  const page = outcome.jobs.slice(opts.offset, opts.offset + opts.limit)
  let detailFailures: typeof outcome.failures = []
  if (opts.includeDescription && opts.format === "json") detailFailures = await hydrate(page, outcome.boardOf)

  if (opts.format === "table") {
    process.stdout.write(renderTable(page))
  } else if (opts.format === "plain") {
    process.stdout.write(page.map((j) => `${j.title} — ${j.company} — ${j.location || "n/a"} — ${j.url}`).join("\n") + (page.length ? "\n" : ""))
  } else {
    process.stdout.write(
      JSON.stringify(
        {
          meta: {
            count: page.length,
            total_matches: outcome.totalMatches,
            page: Math.floor(opts.offset / opts.limit) + 1,
            offset: opts.offset,
            boards_searched: outcome.boardsSearched,
            boards_failed: outcome.failures.map((f) => ({ board: f.board, error: f.error })),
            detail_failures: detailFailures.length,
            truncated_boards: outcome.truncatedBoards,
            dropped_outside_countries: outcome.droppedOutsideCountries,
            dropped_unknown_date: outcome.droppedUnknownDate,
            skipped_malformed: outcome.skippedMalformed,
            countries: opts.countries,
          },
          results: page.map((j) => toResult(j, opts.includeDescription)),
        },
        null,
        2,
      ) + "\n",
    )
  }
  return 0
}

// Only run when executed directly, so tests can import parseFlags.
if (import.meta.main) {
  main()
    .then((code) => {
      // Not process.exit(): on a pipe it can cut off stdout mid-write (a large
      // JSON result was truncated at 64 KB). Setting the exit code lets the
      // event loop drain stdout and then end the process.
      process.exitCode = code
    })
    .catch((e) => {
      if (e instanceof CliError) writeError(e.message, e.code)
      else writeError(e instanceof Error ? e.message : String(e), "INTERNAL_ERROR")
      process.exitCode = 1
    })
}
