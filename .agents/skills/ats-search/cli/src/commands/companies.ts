import { PROVIDERS } from "../providers/index.js"
import { mapPool } from "../http.js"
import { boardRef } from "../boards.js"
import type { Board } from "../types.js"

export interface CompaniesOpts {
  boards: Board[]
  check: boolean
}

export async function runCompanies(opts: CompaniesOpts): Promise<number> {
  const rows = await mapPool(opts.boards, 6, async (b) => {
    const base = { ats: b.ats, company: b.company, name: b.name ?? null, board: boardRef(b) }
    if (!opts.check) return base
    try {
      const jobs = await PROVIDERS[b.ats].probe(b)
      return { ...base, status: "ok", jobs }
    } catch (e) {
      return { ...base, status: "error", error: e instanceof Error ? e.message : String(e) }
    }
  })
  process.stdout.write(JSON.stringify({ count: rows.length, boards: rows }, null, 2) + "\n")
  return opts.check && rows.some((r) => "status" in r && r.status !== "ok") ? 1 : 0
}
