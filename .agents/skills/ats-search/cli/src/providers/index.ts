import type { Ats, Board, Job, ListHints, ListResult } from "../types.js"
import { fetchAshbyDetail, listAshby } from "./ashby.js"
import { fetchGreenhouseDetail, listGreenhouse } from "./greenhouse.js"
import { fetchLeverDetail, listLever } from "./lever.js"
import { fetchWorkdayDetail, listWorkday, probeWorkday } from "./workday.js"

interface Provider {
  list(board: Board, hints: ListHints): Promise<ListResult>
  detail(board: Board, jobRef: string): Promise<Job | null>
  /** True when `list` already returns descriptions, so no hydration is needed. */
  listHasDescriptions: boolean
  /** Number of postings on the board; throws when the board cannot be read. */
  probe(board: Board): Promise<number>
}

const viaList = (list: Provider["list"]) => async (board: Board) => (await list(board, { searchTexts: [], countries: [], maxPerSearch: 20 })).jobs.length

export const PROVIDERS: Record<Ats, Provider> = {
  greenhouse: { list: listGreenhouse, detail: fetchGreenhouseDetail, listHasDescriptions: false, probe: viaList(listGreenhouse) },
  lever: { list: listLever, detail: fetchLeverDetail, listHasDescriptions: true, probe: viaList(listLever) },
  ashby: { list: listAshby, detail: fetchAshbyDetail, listHasDescriptions: true, probe: viaList(listAshby) },
  workday: { list: listWorkday, detail: fetchWorkdayDetail, listHasDescriptions: false, probe: probeWorkday },
}
