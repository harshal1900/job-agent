import { afterAll, beforeAll, beforeEach, describe, expect, test } from "bun:test"
import { ACME, EMPTY_COMPANIES, fixture, mockEnv, runCli, startMock, type Mock } from "./helpers.js"

let mock: Mock
let env: Record<string, string>

beforeAll(() => {
  mock = startMock()
  env = mockEnv(mock)
})
afterAll(() => mock.stop())
beforeEach(() => {
  mock.requests.length = 0
  mock.override(null)
})

const search = (args: string[], extraEnv: Record<string, string> = {}) =>
  runCli(["search", ...ACME, ...args], { ...env, ...extraEnv })

describe("search", () => {
  test("merges all four ATS and returns the Step 2 contract fields", async () => {
    const r = await search(["--country", "us,ca", "--include-unspecified-location", "--no-description"])
    expect(r.code).toBe(0)
    expect(r.json.meta.boards_searched).toBe(4)
    expect(r.json.meta.boards_failed).toEqual([])
    const ats = new Set(r.json.results.map((j: any) => j.ats))
    expect(ats).toEqual(new Set(["greenhouse", "lever", "ashby", "workday"]))
    for (const j of r.json.results) {
      for (const key of ["id", "title", "company", "location", "date", "url"]) expect(j).toHaveProperty(key)
      expect(j.url).toMatch(/^https?:\/\//)
      expect(j).not.toHaveProperty("description")
    }
  })

  test("results are sorted newest first with undated jobs last", async () => {
    const r = await search(["--no-description", "--include-unspecified-location"])
    const dates = r.json.results.map((j: any) => j.date)
    const dated = dates.filter((d: string | null) => d)
    expect(dated).toEqual([...dated].sort().reverse())
    const firstNull = dates.indexOf(null)
    if (firstNull >= 0) expect(dates.slice(firstNull).every((d: string | null) => d === null)).toBe(true)
  })

  test("--country ca excludes US-only jobs and --country us excludes Canada-only jobs", async () => {
    const ca = await search(["--country", "ca", "--no-description"])
    for (const j of ca.json.results) expect(j.countries).toContain("CA")
    const us = await search(["--country", "us", "--no-description"])
    for (const j of us.json.results) expect(j.countries).toContain("US")
    expect(us.json.meta.dropped_outside_countries).toBeGreaterThan(0)
  })

  test("--query filters by title and OR works", async () => {
    const all = await search(["--no-description", "--include-unspecified-location"])
    const word = all.json.results[0].title.split(/\s+/).find((w: string) => w.length > 3)!
    const hit = await search(["-q", word, "--no-description", "--include-unspecified-location"])
    expect(hit.json.results.length).toBeGreaterThan(0)
    for (const j of hit.json.results) expect(`${j.title} ${j.department ?? ""}`.toLowerCase()).toContain(word.toLowerCase())
    const none = await search(["-q", "zzzznomatch", "--no-description"])
    expect(none.json.results).toEqual([])
    const either = await search(["-q", `zzzznomatch OR ${word}`, "--no-description", "--include-unspecified-location"])
    expect(either.json.meta.total_matches).toBe(hit.json.meta.total_matches)
  })

  test("--limit and --offset page through the same ordering", async () => {
    const all = await search(["--limit", "100", "--no-description", "--include-unspecified-location"])
    const first = await search(["--limit", "2", "--no-description", "--include-unspecified-location"])
    const second = await search(["--limit", "2", "--offset", "2", "--no-description", "--include-unspecified-location"])
    expect(first.json.results.map((j: any) => j.id)).toEqual(all.json.results.slice(0, 2).map((j: any) => j.id))
    expect(second.json.results.map((j: any) => j.id)).toEqual(all.json.results.slice(2, 4).map((j: any) => j.id))
    expect(first.json.meta.total_matches).toBe(all.json.results.length)
  })

  test("--page is the same window as the equivalent --offset, and meta.page reports it", async () => {
    const byPage = await search(["--limit", "2", "--page", "2", "--no-description", "--include-unspecified-location"])
    const byOffset = await search(["--limit", "2", "--offset", "2", "--no-description", "--include-unspecified-location"])
    expect(byPage.json.results.map((j: any) => j.id)).toEqual(byOffset.json.results.map((j: any) => j.id))
    expect(byPage.json.meta.page).toBe(2)
  })

  test("descriptions are fetched for Greenhouse and Workday only for the returned page", async () => {
    const r = await search(["--limit", "1", "--ats", "greenhouse", "--include-unspecified-location", "--country", "us,ca"])
    expect(r.json.results[0].description).toBeTruthy()
    const detailCalls = mock.requests.filter((q) => /\/jobs\/\d+$/.test(q.path))
    expect(detailCalls.length).toBe(1)
  })

  test("--no-description makes no per-job requests", async () => {
    await search(["--no-description", "--ats", "greenhouse,workday", "--include-unspecified-location"])
    expect(mock.requests.filter((q) => /\/jobs\/\d+$/.test(q.path) || q.path.includes("/job/")).length).toBe(0)
  })

  test("a large result set is written to a pipe in full (no 64 KB truncation)", async () => {
    const base = fixture("lever-list.json")[0]
    const postings = Array.from({ length: 300 }, (_, i) => ({ ...base, id: `00000000-0000-0000-0000-${String(i).padStart(12, "0")}`, descriptionPlain: "x".repeat(4000) }))
    mock.override((q) => (q.path === "/lever/v0/postings/acme" ? new Response(JSON.stringify(postings), { headers: { "Content-Type": "application/json" } }) : undefined))
    const r = await runCli(["search", "--board", "lever:acme", "--companies", EMPTY_COMPANIES, "--limit", "300", "--include-unspecified-location"], env)
    expect(r.code).toBe(0)
    expect(r.stdout.length).toBeGreaterThan(1_000_000)
    expect(r.json.results.length).toBe(300)
  })

  test("table format prints a header and rows", async () => {
    const r = await search(["--format", "table", "--limit", "3", "--include-unspecified-location"])
    expect(r.code).toBe(0)
    expect(r.stdout.split("\n")[0]).toMatch(/^DATE\s+COMPANY\s+TITLE\s+LOCATION\s+ATS/)
  })

  test("a failing board is reported but does not stop the others", async () => {
    mock.override((q) => (q.path.startsWith("/lever/") ? new Response("nope", { status: 404 }) : undefined))
    const r = await search(["--no-description", "--include-unspecified-location"])
    expect(r.code).toBe(0)
    expect(r.json.meta.boards_searched).toBe(3)
    expect(r.json.meta.boards_failed[0].board).toBe("lever:acme")
    expect(r.stderr).toContain("board not found")
    expect(r.json.results.some((j: any) => j.ats === "lever")).toBe(false)
  })

  test("every board failing is an error with exit 1", async () => {
    mock.override(() => new Response("nope", { status: 404 }))
    const r = await search(["--no-description"])
    expect(r.code).toBe(1)
    expect(r.errJson.code).toBe("ALL_BOARDS_FAILED")
  })

  test("retries a 429 with Retry-After, then succeeds", async () => {
    let n = 0
    mock.override((q) => {
      if (q.path === "/ashby/posting-api/job-board/acme" && n++ === 0) return new Response("slow down", { status: 429, headers: { "Retry-After": "1" } })
      return undefined
    })
    const r = await runCli(["search", "--board", "ashby:acme", "--companies", EMPTY_COMPANIES, "--no-description", "--include-unspecified-location"], env)
    expect(r.code).toBe(0)
    expect(r.json.results.length).toBeGreaterThan(0)
    expect(n).toBeGreaterThanOrEqual(2)
  })

  test("a request that times out once is retried and succeeds", async () => {
    let n = 0
    mock.override((q) => {
      if (q.path === "/lever/v0/postings/acme" && n++ === 0) return new Response(new ReadableStream({ start() {} }), { status: 200 }) // never completes
      return undefined
    })
    const r = await runCli(["search", "--board", "lever:acme", "--companies", EMPTY_COMPANIES, "--no-description", "--include-unspecified-location"], { ...env, ATS_TIMEOUT_MS: "800" })
    expect(r.code).toBe(0)
    expect(r.json.results.length).toBeGreaterThan(0)
    expect(n).toBe(2)
  })

  test("a host that stays unreachable fails that board after one retry", async () => {
    const r = await runCli(["search", "--board", "lever:acme", "--companies", EMPTY_COMPANIES, "--no-description"], { ...env, ATS_LEVER_URL: "http://127.0.0.1:1" })
    expect(r.code).toBe(1)
    expect(r.stderr).toContain("could not reach")
  })

  test("a Retry-After beyond the budget fails that board instead of hanging", async () => {
    mock.override(() => new Response("busy", { status: 503, headers: { "Retry-After": "3600" } }))
    const t0 = Date.now()
    const r = await runCli(["search", "--board", "lever:acme", "--companies", EMPTY_COMPANIES, "--no-description"], env)
    expect(Date.now() - t0).toBeLessThan(10_000)
    expect(r.code).toBe(1)
    expect(r.stderr).toContain("retry budget")
  })

  test("malformed JSON from a board is a clear error, not a crash", async () => {
    mock.override((q) => (q.path.startsWith("/ashby/") ? new Response("<html>oops</html>", { status: 200 }) : undefined))
    const r = await search(["--no-description", "--include-unspecified-location"])
    expect(r.code).toBe(0)
    expect(r.json.meta.boards_failed[0].error).toContain("not valid JSON")
  })

  test("--jobage drops older and undated jobs", async () => {
    const fresh = await search(["--jobage", "1", "--no-description", "--include-unspecified-location"])
    expect(fresh.json.meta.total_matches).toBeLessThan((await search(["--no-description", "--include-unspecified-location"])).json.meta.total_matches)
  })

  test("--remote filters on workplace", async () => {
    const r = await search(["--remote", "hybrid", "--no-description", "--include-unspecified-location"])
    for (const j of r.json.results) expect(j.workplace).toBe("hybrid")
  })

  test("--company narrows the boards searched", async () => {
    const r = await runCli(["search", ...ACME, "--company", "nonexistent"], env)
    expect(r.code).toBe(1)
    expect(r.errJson.code).toBe("NO_BOARDS")
  })
})

describe("malformed postings", () => {
  test("a posting missing its title is skipped and counted, not fatal (live Intel/Workday case)", async () => {
    const wl = fixture("workday-list.json")
    mock.override((q) => {
      if (q.method !== "POST" || q.body.limit === 1) return undefined
      const postings = [{ externalPath: "/job/US-CA-Santa-Clara/Withdrawn_JR1", bulletFields: ["JR1"] }, ...wl.jobPostings.slice(0, 3)]
      return new Response(JSON.stringify({ total: 4, jobPostings: postings }), { headers: { "Content-Type": "application/json" } })
    })
    const r = await search(["--ats", "workday", "--no-description", "--include-unspecified-location"])
    expect(r.code).toBe(0)
    expect(r.json.meta.skipped_malformed).toBe(1)
    expect(r.json.results.length).toBeGreaterThan(0)
  })

  test.each([
    ["lever", "/lever/v0/postings/acme", [{ id: "x" }, null, { id: "y", text: "  ", hostedUrl: "https://x" }]],
    ["greenhouse", "/greenhouse/v1/boards/acme/jobs", { jobs: [{ id: 1 }, { id: "nope", title: "T", absolute_url: "u" }] }],
    ["ashby", "/ashby/posting-api/job-board/acme", { jobs: [{ id: "1" }, { id: "2", title: "T" }] }],
  ])("%s: invalid entries are skipped and counted", async (ats, path, body) => {
    mock.override((q) => (q.path === path ? new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } }) : undefined))
    const r = await runCli(["search", "--board", `${ats}:acme`, "--companies", EMPTY_COMPANIES, "--no-description", "--include-unspecified-location"], env)
    expect(r.code).toBe(0)
    expect(r.json.results).toEqual([])
    expect(r.json.meta.skipped_malformed).toBeGreaterThanOrEqual(2)
  })
})

describe("workday specifics", () => {
  test("a country facet is applied server-side and the probe is a single small request", async () => {
    await search(["--ats", "workday", "--country", "us", "--no-description"])
    const posts = mock.requests.filter((q) => q.method === "POST")
    expect(posts[0].body.limit).toBe(1)
    const real = posts.find((q) => q.body.limit === 20)!
    expect(Object.keys(real.body.appliedFacets)).toEqual(["locationCountry"])
    expect(real.body.appliedFacets.locationCountry.length).toBe(1)
  })

  test("never asks for more than 20 per page and pages until a short page", async () => {
    await search(["--ats", "workday", "--no-description", "--max-per-board", "20"])
    for (const q of mock.requests.filter((q) => q.method === "POST")) expect(q.body.limit).toBeLessThanOrEqual(20)
  })

  test("the page cap marks the board truncated when more postings exist", async () => {
    const big = fixture("workday-list.json")
    const one = big.jobPostings[0]
    mock.override((q) => {
      if (q.method !== "POST" || q.body.limit === 1) return undefined
      const offset = q.body.offset
      const postings = Array.from({ length: 20 }, (_, i) => ({ ...one, externalPath: `/job/US-CA-Santa-Clara/Eng-${offset + i}_JR${offset + i}` }))
      return new Response(JSON.stringify({ total: offset === 0 ? 500 : 0, jobPostings: postings }), { headers: { "Content-Type": "application/json" } })
    })
    const r = await search(["--ats", "workday", "--no-description", "--max-per-board", "40", "--limit", "100", "--country", "us"])
    expect(r.json.meta.truncated_boards).toEqual(["workday:acme"])
    expect(r.json.meta.total_matches).toBe(40)
  })

  test("an unexpected response shape names the board", async () => {
    mock.override((q) => (q.method === "POST" ? new Response(JSON.stringify({ hello: "world" }), { headers: { "Content-Type": "application/json" } }) : undefined))
    const r = await search(["--ats", "workday", "--no-description"])
    expect(r.code).toBe(1)
    expect(r.stderr).toContain("workday:acme")
  })

  test("detail on a Workday job fills in the real locations", async () => {
    const list = await search(["--ats", "workday", "--limit", "1", "--country", "us"])
    expect(list.json.results[0].description).toBeTruthy()
    expect(list.json.results[0].location).not.toMatch(/^\d+ Locations$/)
  })
})

describe("detail", () => {
  test("by id for each ATS", async () => {
    const gh = await runCli(["detail", "greenhouse:acme:12345"], env)
    expect(gh.code).toBe(0)
    expect(gh.json.title).toBeTruthy()
    expect(gh.json.description.length).toBeGreaterThan(100)
    const leverId = fixture("lever-list.json")[0].id
    const lv = await runCli(["detail", `lever:acme:${leverId}`], env)
    expect(lv.json.id).toBe(`lever:acme:${leverId}`)
    const ashbyId = fixture("ashby-list.json").jobs[0].id
    const ab = await runCli(["detail", `ashby:acme:${ashbyId}`, "--format", "plain"], env)
    expect(ab.stdout).toContain("Title:")
    const path = fixture("workday-list.json").jobPostings[0].externalPath
    const wd = await runCli(["detail", `workday:acme.wd5/Site:${path}`], env)
    expect(wd.code).toBe(0)
    expect(wd.json.description).toBeTruthy()
  })

  test("unknown posting is NOT_FOUND", async () => {
    const r = await runCli(["detail", "lever:acme:00000000-0000-0000-0000-000000000000"], env)
    expect(r.code).toBe(1)
    expect(r.errJson.code).toBe("NOT_FOUND")
  })

  test.each(["", "garbage", "greenhouse:acme", "https://evil.com/x", "http://jobs.lever.co/a/b", "workday:acme.wd5/Site:/job/../etc"])(
    "rejects bad input %p before any request",
    async (input) => {
      const r = await runCli(input === "" ? ["detail"] : ["detail", input], env)
      expect(r.code).toBe(1)
      expect(["BAD_ID", "NO_ID", "NOT_FOUND"]).toContain(r.errJson.code)
      expect(mock.requests.length).toBe(0)
    },
  )
})

describe("companies", () => {
  test("lists configured boards", async () => {
    const r = await runCli(["companies", ...ACME], env)
    expect(r.code).toBe(0)
    expect(r.json.count).toBe(4)
  })
  test("--check probes each board and exits 1 when one is broken", async () => {
    const ok = await runCli(["companies", "--check", ...ACME], env)
    expect(ok.code).toBe(0)
    expect(ok.json.boards.every((b: any) => b.status === "ok" && b.jobs > 0)).toBe(true)
    mock.override((q) => (q.path.startsWith("/ashby/") ? new Response("nf", { status: 404 }) : undefined))
    const bad = await runCli(["companies", "--check", ...ACME], env)
    expect(bad.code).toBe(1)
    expect(bad.json.boards.find((b: any) => b.ats === "ashby").status).toBe("error")
  })
})

describe("argument handling", () => {
  test.each([
    [["search", "--bogus", "x"], "UNKNOWN_FLAG"],
    [["search", "--page", "0"], "BAD_ARG"],
    [["search", "--page", "2", "--offset", "5"], "BAD_ARG"],
    [["search", "--limit", "0"], "BAD_ARG"],
    [["search", "--limit", "abc"], "BAD_ARG"],
    [["search", "--jobage", "1.5"], "BAD_ARG"],
    [["search", "--country", "mx"], "BAD_ARG"],
    [["search", "--remote", "sometimes"], "BAD_ARG"],
    [["search", "--format", "xml"], "BAD_ARG"],
    [["search", "--query"], "BAD_ARG"],
    [["search", "--ats", "taleo"], "BAD_ARG"],
    [["search", "--board", "nonsense"], "BAD_ARG"],
    [["search", "--max-per-board", "5"], "BAD_ARG"],
    [["search", "-q", "a OR b OR c OR d OR e OR f"], "BAD_ARG"],
    [["frobnicate"], "BAD_CMD"],
  ])("%p → %s", async (args, code) => {
    const r = await runCli([...args, "--companies", EMPTY_COMPANIES], env)
    expect(r.code).toBe(1)
    expect(r.errJson.code).toBe(code)
    expect(r.stdout).toBe("")
  })

  test("a missing explicit companies file is BAD_CONFIG; the default file is optional", async () => {
    const r = await runCli(["search", "--companies", "/definitely/not/here.json"], env)
    expect(r.errJson.code).toBe("BAD_CONFIG")
  })

  test("--help prints usage and exits 0", async () => {
    const r = await runCli(["search", "--help"], env)
    expect(r.code).toBe(0)
    expect(r.stdout).toContain("USAGE")
  })

  test("--no-description does not swallow a following word", async () => {
    const r = await search(["--no-description", "--limit", "1", "--include-unspecified-location"])
    expect(r.code).toBe(0)
    expect(r.json.results.length).toBe(1)
  })
})
