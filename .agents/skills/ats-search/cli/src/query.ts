// Query and filter helpers: the "a OR b" keyword syntax and job predicates.

import { CliError, type Job, type Workplace } from "./types.js"

const MAX_ALTERNATIVES = 5

/** Split `"a b" OR c` into alternatives, each a list of required terms. */
export function parseQuery(query: string | undefined): string[][] {
  if (!query || !query.trim()) return []
  const alternatives = splitOutsideQuotes(query)
  if (alternatives.length > MAX_ALTERNATIVES) {
    throw new CliError(`--query allows at most ${MAX_ALTERNATIVES} OR alternatives, got ${alternatives.length}`, "BAD_ARG")
  }
  return alternatives
    .map((alt) => terms(alt.replace(/^\s*title:/i, "")))
    .filter((t) => t.length > 0)
}

function splitOutsideQuotes(query: string): string[] {
  const out: string[] = []
  let current = ""
  let inQuote = false
  const tokens = query.split(/(\s+)/)
  for (const tok of tokens) {
    if (!inQuote && tok === "OR") {
      out.push(current)
      current = ""
      continue
    }
    const quotes = (tok.match(/"/g) ?? []).length
    if (quotes % 2 === 1) inQuote = !inQuote
    current += tok
  }
  out.push(current)
  return out
}

function terms(alt: string): string[] {
  const out: string[] = []
  const re = /"([^"]+)"|(\S+)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(alt))) out.push((m[1] ?? m[2]).toLowerCase())
  return out
}

/** Does the job's title/department contain every term of any alternative? */
export function matchesQuery(job: Job, alternatives: string[][]): boolean {
  if (alternatives.length === 0) return true
  const hay = `${job.title} ${job.department ?? ""}`.toLowerCase()
  return alternatives.some((alt) => alt.every((term) => hay.includes(term)))
}

export function matchesWorkplace(job: Job, wanted: Workplace[]): boolean {
  if (wanted.length === 0) return true
  if (job.workplace) return wanted.includes(job.workplace)
  return wanted.includes("remote") && /\bremote\b/i.test(job.location)
}

export function matchesLocationText(job: Job, needle: string | undefined): boolean {
  if (!needle) return true
  const n = needle.toLowerCase()
  return job.locations.some((l) => l.toLowerCase().includes(n)) || job.location.toLowerCase().includes(n)
}

export function compareJobs(a: Job, b: Job): number {
  if (a.date && b.date && a.date !== b.date) return a.date < b.date ? 1 : -1
  if (a.date && !b.date) return -1
  if (!a.date && b.date) return 1
  return a.title.localeCompare(b.title) || a.id.localeCompare(b.id)
}
