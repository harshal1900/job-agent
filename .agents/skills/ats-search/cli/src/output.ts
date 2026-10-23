import type { Job } from "./types.js"

export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

export function writeWarning(warning: string, code: string): void {
  process.stderr.write(JSON.stringify({ warning, code }) + "\n")
}

function clip(s: string | null | undefined, n: number): string {
  const t = (s ?? "").replace(/\s+/g, " ")
  return t.length > n ? t.slice(0, n - 1) + "…" : t
}

export function renderTable(jobs: Job[]): string {
  if (jobs.length === 0) return "(no matching jobs)\n"
  const rows = jobs.map((j) => [
    clip(j.date ?? "", 10),
    clip(j.company, 18),
    clip(j.title, 48),
    clip(j.location, 34),
    j.ats,
  ])
  const header = ["DATE", "COMPANY", "TITLE", "LOCATION", "ATS"]
  const widths = header.map((h, i) => Math.max(h.length, ...rows.map((r) => r[i].length)))
  const line = (r: string[]) => r.map((c, i) => c.padEnd(widths[i])).join("  ").trimEnd()
  return [line(header), ...rows.map(line)].join("\n") + "\n"
}

export function renderPlain(job: Job): string {
  const fields: [string, string | null][] = [
    ["Title", job.title],
    ["Company", job.company],
    ["Location", job.location || null],
    ["Posted", job.date ? `${job.date}${job.dateApproximate ? " (approximate)" : ""}` : null],
    ["Department", job.department],
    ["Type", job.employmentType],
    ["Workplace", job.workplace],
    ["Salary", job.salary],
    ["URL", job.url],
    ["ID", job.id],
  ]
  const head = fields.filter(([, v]) => v).map(([k, v]) => `${k}: ${v}`).join("\n")
  return `${head}\n\n${job.description ?? "(no description)"}\n`
}
