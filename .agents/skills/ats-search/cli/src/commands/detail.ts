import { parseIdOrUrl } from "../boards.js"
import { PROVIDERS } from "../providers/index.js"
import { renderPlain, writeError } from "../output.js"
import { toResult } from "./search.js"

export interface DetailOpts {
  id: string
  format: "json" | "plain"
}

export async function runDetail(opts: DetailOpts): Promise<number> {
  const { board, jobRef } = parseIdOrUrl(opts.id)
  const job = await PROVIDERS[board.ats].detail(board, jobRef)
  if (!job) {
    writeError(`posting not found on ${board.ats}:${board.company} (it may be closed)`, "NOT_FOUND")
    return 1
  }
  process.stdout.write(opts.format === "plain" ? renderPlain(job) : JSON.stringify(toResult(job, true), null, 2) + "\n")
  return 0
}

