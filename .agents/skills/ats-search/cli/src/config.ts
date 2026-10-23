// The watchlist of company boards: config/target_companies.json at the repo
// root, overridable with --companies or ATS_COMPANIES, extended by --board.

import { existsSync, readFileSync } from "node:fs"
import { resolve } from "node:path"
import { validateBoard } from "./boards.js"
import { ATS_NAMES, CliError, type Ats, type Board } from "./types.js"

export function defaultConfigPath(): string {
  // src/ -> cli/ -> ats-search/ -> skills/ -> .agents/ -> repo root
  return resolve(import.meta.dir, "../../../../../config/target_companies.json")
}

interface RawBoard {
  ats?: unknown
  company?: unknown
  name?: unknown
  host?: unknown
  site?: unknown
}

export function parseConfig(text: string, source: string): Board[] {
  let doc: unknown
  try {
    doc = JSON.parse(text)
  } catch (e) {
    throw new CliError(`${source}: invalid JSON (${e instanceof Error ? e.message : String(e)})`, "BAD_CONFIG")
  }
  const list = (doc as { boards?: unknown })?.boards
  if (!Array.isArray(list)) throw new CliError(`${source}: expected {"boards": [...]}`, "BAD_CONFIG")
  const seen = new Set<string>()
  const boards: Board[] = []
  list.forEach((raw: RawBoard, i: number) => {
    const where = `${source} boards[${i}]`
    if (typeof raw?.ats !== "string" || !ATS_NAMES.includes(raw.ats as Ats)) {
      throw new CliError(`${where}: "ats" must be one of ${ATS_NAMES.join("|")}`, "BAD_CONFIG")
    }
    if (typeof raw.company !== "string") throw new CliError(`${where}: "company" must be a string`, "BAD_CONFIG")
    const board: Board = { ats: raw.ats as Ats, company: raw.company }
    if (typeof raw.name === "string" && raw.name.trim()) board.name = raw.name.trim()
    if (typeof raw.host === "string") board.host = raw.host
    if (typeof raw.site === "string") board.site = raw.site
    try {
      validateBoard(board)
    } catch (e) {
      throw new CliError(`${where}: ${e instanceof Error ? e.message : String(e)}`, "BAD_CONFIG")
    }
    const key = `${board.ats}:${board.company}:${board.site ?? ""}`.toLowerCase()
    if (seen.has(key)) return // a duplicate entry is harmless; keep the first
    seen.add(key)
    boards.push(board)
  })
  return boards
}

export function loadConfig(path: string | undefined, explicit: boolean): Board[] {
  const file = path ?? defaultConfigPath()
  if (!existsSync(file)) {
    if (explicit) throw new CliError(`companies file not found: ${file}`, "BAD_CONFIG")
    return []
  }
  return parseConfig(readFileSync(file, "utf8"), file)
}

