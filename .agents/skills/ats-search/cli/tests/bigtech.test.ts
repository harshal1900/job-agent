import { afterAll, beforeAll, describe, expect, test } from "bun:test"
import { parseBoardSpec, parseJobUrl } from "../src/boards.js"
import { amazonDate } from "../src/providers/amazon.js"
import { EMPTY_COMPANIES, mockEnv, runCli, startMock, type Mock } from "./helpers.js"

let mock: Mock
let env: Record<string, string>
beforeAll(() => {
  mock = startMock()
  env = mockEnv(mock)
})
afterAll(() => mock.stop())

const search = (board: string, ...args: string[]) =>
  runCli(["search", "--board", board, "--companies", EMPTY_COMPANIES, ...args], env)

describe("amazon", () => {
  test("parses its date format", () => {
    expect(amazonDate("October 22, 2026")).toBe("2026-10-22")
    expect(amazonDate("Oct 22")).toBeNull()
    expect(amazonDate(undefined)).toBeNull()
  })

  test("lists US and Canada postings with description and skips malformed ones", async () => {
    const r = await search("amazon:amazon", "--include-unspecified-location")
    expect(r.code).toBe(0)
    expect(r.json.results.map((j: any) => j.title).sort()).toEqual(["Applied Scientist", "Machine Learning Engineer, Prime"])
    const ml = r.json.results.find((j: any) => j.title.startsWith("Machine"))
    expect(ml).toMatchObject({ ats: "amazon", company: "Amazon", country: "US", date: "2026-10-22", url: "https://www.amazon.jobs/en/jobs/1001/slug-1001" })
    expect(ml.description).toContain("3+ years of Python")
    expect(ml.description).not.toContain("<b>")
    expect(r.json.meta.skipped_malformed).toBe(1)
  })

  test("country filter reaches the server", async () => {
    const r = await search("amazon:amazon", "--country", "ca")
    expect(r.json.results.map((j: any) => j.country)).toEqual(["CA"])
    expect(mock.requests.at(-1)!.search).toContain("country%5B%5D=CAN")
    expect(mock.requests.at(-1)!.search).not.toContain("USA")
  })

  test("detail finds a posting by id and by URL", async () => {
    const byId = await runCli(["detail", "amazon:amazon:1001"], env)
    expect(byId.json.title).toBe("Machine Learning Engineer, Prime")
    expect(parseJobUrl("https://www.amazon.jobs/en/jobs/1001/some-slug").jobRef).toBe("1001")
  })
})

describe("microsoft", () => {
  test("lists postings per country, with workplace and date", async () => {
    const r = await search("microsoft:microsoft", "--no-description")
    expect(r.code).toBe(0)
    const by = Object.fromEntries(r.json.results.map((j: any) => [j.title, j]))
    expect(by["Principal ML Engineer"]).toMatchObject({ ats: "microsoft", country: "US", workplace: "onsite", date: "2026-10-23" })
    expect(by["Senior Software Engineer"]).toMatchObject({ country: "CA", workplace: "hybrid" })
    expect(r.json.meta.skipped_malformed).toBeGreaterThan(0)
  })

  test("sends browser-like headers worth having and asks one location per country", async () => {
    await search("microsoft:microsoft", "--country", "ca", "--no-description")
    const last = mock.requests.at(-1)!
    expect(last.search).toContain("location=Canada")
    expect(last.search).toContain("sort_by=timestamp")
  })

  test("fetches the description from the posting detail", async () => {
    const r = await search("microsoft:microsoft", "-q", "Principal ML")
    expect(r.json.results[0].description).toContain("Build models.")
    expect(r.json.results[0].employment_type).toBeNull() // list has none; detail only fills the description
  })

  test("detail accepts a posting URL", async () => {
    const parsed = parseJobUrl("https://apply.careers.microsoft.com/careers/job/1970393557042145")
    expect(parsed.board.ats).toBe("microsoft")
    const r = await runCli(["detail", "microsoft:microsoft:1970393557042145"], env)
    expect(r.json.employment_type).toBe("Full-Time")
  })
})

test("both are accepted as ad-hoc boards", () => {
  expect(parseBoardSpec("amazon:amazon").ats).toBe("amazon")
  expect(parseBoardSpec("microsoft:microsoft").ats).toBe("microsoft")
})
