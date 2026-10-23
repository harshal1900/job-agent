// Test harness: a local mock of the four ATS APIs plus a CLI runner. Providers
// honour ATS_<NAME>_URL, so the real CLI runs unmodified against the mock.

import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"

export const fixture = (name: string) => JSON.parse(readFileSync(new URL(`./fixtures/${name}`, import.meta.url), "utf8"))

export interface Recorded {
  method: string
  path: string
  search: string
  body: any
}

export interface Mock {
  url: string
  requests: Recorded[]
  /** Replace a handler: return a Response to override, or undefined to fall through. */
  override: (fn: ((req: Recorded) => Response | undefined) | null) => void
  stop: () => void
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })

export function startMock(): Mock {
  const requests: Recorded[] = []
  let overrideFn: ((req: Recorded) => Response | undefined) | null = null
  const server = Bun.serve({
    port: 0,
    async fetch(req) {
      const u = new URL(req.url)
      const text = await req.text()
      const rec: Recorded = { method: req.method, path: u.pathname, search: u.search, body: text ? JSON.parse(text) : null }
      requests.push(rec)
      const forced = overrideFn?.(rec)
      if (forced) return forced

      const p = u.pathname
      if (p === "/greenhouse/v1/boards/acme/jobs") return json(fixture("greenhouse-list.json"))
      const gh = /^\/greenhouse\/v1\/boards\/acme\/jobs\/(\d+)$/.exec(p)
      if (gh) {
        const base = fixture("greenhouse-detail.json")
        return json({ ...base, id: Number(gh[1]) })
      }
      if (p === "/lever/v0/postings/acme") return json(fixture("lever-list.json"))
      const lv = /^\/lever\/v0\/postings\/acme\/([0-9a-f-]+)$/.exec(p)
      if (lv) {
        const hit = fixture("lever-list.json").find((x: any) => x.id === lv[1])
        return hit ? json(hit) : json({ ok: false }, 404)
      }
      if (p === "/ashby/posting-api/job-board/acme") return json(fixture("ashby-list.json"))
      if (p === "/workday/wday/cxs/acme/Site/jobs" && req.method === "POST") {
        const list = fixture("workday-list.json")
        const offset = rec.body?.offset ?? 0
        const limit = rec.body?.limit ?? 20
        // Mimic Workday: `total` only on the first page, 400 above 20 per page.
        if (limit > 20) return json({ errorCode: "HTTP_400" }, 400)
        const postings = list.jobPostings.slice(offset, offset + limit)
        return json({ total: offset === 0 ? list.jobPostings.length : 0, jobPostings: postings, facets: fixtureFacets() })
      }
      if (p.startsWith("/workday/wday/cxs/acme/Site/job/")) return json(fixture("workday-detail.json"))
      if (p === "/amazon/en/search.json") {
        const q = new URLSearchParams(u.search)
        const all = fixture("amazon-list.json")
        const want = q.getAll("country[]")
        const base = q.get("base_query") ?? ""
        const jobs = all.jobs.filter((j: any) => (!want.length || want.includes(j.country_code) || !j.country_code) && (!base || /^\d+$/.test(base) ? !base || j.id_icims === base : true))
        return json({ ...all, jobs })
      }
      if (p === "/microsoft/api/pcsx/search") {
        const all = fixture("microsoft-list.json")
        const country = new URLSearchParams(u.search).get("location")
        const keep = all.data.positions.filter((x: any) => !x.standardizedLocations || x.standardizedLocations.some((l: string) => l.endsWith(country === "Canada" ? ", CA" : ", US")))
        const start = Number(new URLSearchParams(u.search).get("start") ?? 0)
        return json({ status: 200, data: { count: keep.length, positions: start === 0 ? keep : [] } })
      }
      if (p === "/microsoft/api/pcsx/position_details") return json(fixture("microsoft-detail.json"))
      return json({ error: "not found" }, 404)
    },
  })
  return {
    url: `http://localhost:${server.port}`,
    requests,
    override: (fn) => {
      overrideFn = fn
    },
    stop: () => server.stop(true),
  }
}

function fixtureFacets() {
  return fixture("workday-facets-adobe.json")
}

export interface RunResult {
  code: number
  stdout: string
  stderr: string
  json: any
  errJson: any
}

export async function runCli(args: string[], env: Record<string, string> = {}): Promise<RunResult> {
  const proc = Bun.spawn(["bun", "run", fileURLToPath(new URL("../src/cli.ts", import.meta.url)), ...args], {
    env: { ...process.env, ...env },
    stdout: "pipe",
    stderr: "pipe",
  })
  const [stdout, stderr] = await Promise.all([new Response(proc.stdout).text(), new Response(proc.stderr).text()])
  const code = await proc.exited
  const parse = (s: string) => {
    try {
      return JSON.parse(s)
    } catch {
      return undefined
    }
  }
  // The final JSON line is the command's own error; earlier lines are per-board warnings.
  const firstErrLine = stderr.split("\n").filter((l) => l.trim().startsWith("{")).pop()
  return { code, stdout, stderr, json: parse(stdout), errJson: firstErrLine ? parse(firstErrLine) : undefined }
}

export function mockEnv(m: Mock): Record<string, string> {
  return {
    ATS_GREENHOUSE_URL: `${m.url}/greenhouse`,
    ATS_LEVER_URL: `${m.url}/lever`,
    ATS_ASHBY_URL: `${m.url}/ashby`,
    ATS_WORKDAY_URL: `${m.url}/workday`,
    ATS_AMAZON_URL: `${m.url}/amazon`,
    ATS_MICROSOFT_URL: `${m.url}/microsoft`,
    ATS_MICROSOFT_DELAY_MS: "0",
  }
}

export const EMPTY_COMPANIES = fileURLToPath(new URL("./fixtures/empty-companies.json", import.meta.url))

export const ACME = ["--board", "greenhouse:acme", "--board", "lever:acme", "--board", "ashby:acme", "--board", "workday:acme.wd5/Site", "--companies", EMPTY_COMPANIES]
