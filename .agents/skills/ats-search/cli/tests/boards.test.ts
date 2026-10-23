import { describe, expect, test } from "bun:test"
import { makeId, parseBoardSpec, parseIdOrUrl, parseJobId, parseJobUrl, validateBoard } from "../src/boards.js"

describe("parseBoardSpec", () => {
  test("simple boards", () => {
    expect(parseBoardSpec("greenhouse:stripe")).toEqual({ ats: "greenhouse", company: "stripe" })
    expect(parseBoardSpec("LEVER:palantir")).toEqual({ ats: "lever", company: "palantir" })
    expect(parseBoardSpec("ashby:ramp")).toEqual({ ats: "ashby", company: "ramp" })
  })
  test("workday", () => {
    expect(parseBoardSpec("workday:nvidia.wd5/NVIDIAExternalCareerSite")).toEqual({
      ats: "workday", company: "nvidia", host: "wd5", site: "NVIDIAExternalCareerSite",
    })
  })
  test.each(["stripe", "greenhouse", "taleo:acme", "greenhouse:", "greenhouse:a/b", "greenhouse:../x", "greenhouse:a b", "workday:nvidia", "workday:nvidia.wd5", "workday:nvidia.evil/Site"])(
    "rejects %s",
    (spec) => expect(() => parseBoardSpec(spec)).toThrow(),
  )
})

describe("validateBoard", () => {
  test("rejects tokens that could alter the request path or host", () => {
    for (const company of ["a/b", "a?b", "a#b", "a@evil.com", "", "-x", "a\nb"]) {
      expect(() => validateBoard({ ats: "lever", company })).toThrow()
    }
  })
})

describe("job ids", () => {
  test("round trip, including a Workday path", () => {
    const board = { ats: "workday" as const, company: "nvidia", host: "wd5", site: "NVIDIAExternalCareerSite" }
    const id = makeId(board, "/job/US-CA-Santa-Clara/Senior-Engineer_JR1")
    expect(id).toBe("workday:nvidia.wd5/NVIDIAExternalCareerSite:/job/US-CA-Santa-Clara/Senior-Engineer_JR1")
    const parsed = parseJobId(id)
    expect(parsed.board).toEqual(board)
    expect(parsed.jobRef).toBe("/job/US-CA-Santa-Clara/Senior-Engineer_JR1")
  })
  test("greenhouse and lever ids", () => {
    expect(parseJobId("greenhouse:stripe:123")).toEqual({ board: { ats: "greenhouse", company: "stripe" }, jobRef: "123" })
    expect(parseJobId("lever:palantir:abc-123").jobRef).toBe("abc-123")
  })
  test.each(["", "x", "greenhouse:stripe", "greenhouse::1", "bogus:stripe:1", "greenhouse:stripe:", "greenhouse:stripe:1 2", "greenhouse:stripe:1?x=y", "greenhouse:a/b:1"])(
    "rejects %p",
    (id) => expect(() => parseJobId(id)).toThrow(),
  )
})

describe("parseJobUrl", () => {
  test("accepts the ATS hosts", () => {
    expect(parseJobUrl("https://boards.greenhouse.io/stripe/jobs/4567")).toEqual({ board: { ats: "greenhouse", company: "stripe" }, jobRef: "4567" })
    expect(parseJobUrl("https://job-boards.greenhouse.io/stripe/jobs/4567").jobRef).toBe("4567")
    expect(parseJobUrl("https://jobs.lever.co/palantir/abc-1").board.company).toBe("palantir")
    expect(parseJobUrl("https://jobs.ashbyhq.com/ramp/uuid-1").jobRef).toBe("uuid-1")
    const wd = parseJobUrl("https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/US-CA/Senior-Engineer_JR9")
    expect(wd.board).toEqual({ ats: "workday", company: "nvidia", host: "wd5", site: "NVIDIAExternalCareerSite" })
    expect(wd.jobRef).toBe("/job/US-CA/Senior-Engineer_JR9")
  })
  test.each([
    "http://jobs.lever.co/palantir/abc",
    "https://evil.com/palantir/abc",
    "https://jobs.lever.co.evil.com/palantir/abc",
    "https://stripe.com/jobs/search?gh_jid=123",
    "https://boards.greenhouse.io/stripe",
    "https://nvidia.wd5.myworkdayjobs.com.evil.com/Site/job/x/y",
    "https://myworkdayjobs.com/Site/job/x/y",
    "not a url at all",
  ])("rejects %s", (u) => expect(() => parseIdOrUrl(u)).toThrow())
})
