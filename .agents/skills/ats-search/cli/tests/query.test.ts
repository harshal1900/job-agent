import { describe, expect, test } from "bun:test"
import { compareJobs, matchesLocationText, matchesQuery, matchesWorkplace, parseQuery } from "../src/query.js"
import type { Job } from "../src/types.js"

function job(over: Partial<Job> = {}): Job {
  return {
    id: "greenhouse:x:1", ats: "greenhouse", company: "X", title: "Senior Software Engineer", location: "Austin, TX",
    locations: ["Austin, TX"], country: "US", date: "2026-10-01", dateApproximate: false, url: "https://x", department: "Platform",
    employmentType: null, workplace: null, salary: null, description: null, detailRef: "1", ...over,
  }
}

describe("parseQuery", () => {
  test("empty means no constraint", () => {
    expect(parseQuery(undefined)).toEqual([])
    expect(parseQuery("   ")).toEqual([])
  })
  test("OR alternatives and quoted phrases", () => {
    expect(parseQuery('data scientist OR "machine learning" engineer')).toEqual([["data", "scientist"], ["machine learning", "engineer"]])
  })
  test("OR inside quotes is literal", () => {
    expect(parseQuery('"this OR that"')).toEqual([["this or that"]])
  })
  test("lowercase or is an ordinary word", () => {
    expect(parseQuery("research or development")).toEqual([["research", "or", "development"]])
  })
  test("title: prefix is accepted", () => {
    expect(parseQuery("title:staff engineer")).toEqual([["staff", "engineer"]])
  })
  test("more than 5 alternatives is rejected", () => {
    expect(() => parseQuery("a OR b OR c OR d OR e OR f")).toThrow("at most 5")
  })
})

describe("matching", () => {
  test("all terms of one alternative must match title or department", () => {
    const q = parseQuery("software engineer")
    expect(matchesQuery(job(), q)).toBe(true)
    expect(matchesQuery(job({ title: "Designer" }), q)).toBe(false)
    // substring match: "engineer" is inside "Engineering"
    expect(matchesQuery(job({ title: "Designer", department: "Software Engineering" }), q)).toBe(true)
    expect(matchesQuery(job({ title: "Designer", department: "Software" }), q)).toBe(false)
    expect(matchesQuery(job({ title: "Manager", department: "Software Engineer pod" }), q)).toBe(true)
  })
  test("any alternative may match", () => {
    expect(matchesQuery(job({ title: "Data Scientist" }), parseQuery("designer OR data scientist"))).toBe(true)
  })
  test("workplace filter, with a remote fallback on the location text", () => {
    expect(matchesWorkplace(job({ workplace: "hybrid" }), ["remote", "hybrid"])).toBe(true)
    expect(matchesWorkplace(job({ workplace: "onsite" }), ["remote"])).toBe(false)
    expect(matchesWorkplace(job({ workplace: null, location: "Remote - US" }), ["remote"])).toBe(true)
    expect(matchesWorkplace(job({ workplace: null, location: "Austin, TX" }), ["hybrid"])).toBe(false)
    expect(matchesWorkplace(job(), [])).toBe(true)
  })
  test("location text is a case-insensitive substring", () => {
    expect(matchesLocationText(job(), "austin")).toBe(true)
    expect(matchesLocationText(job(), "denver")).toBe(false)
    expect(matchesLocationText(job(), undefined)).toBe(true)
  })
  test("sort: newest first, undated last, stable on ties", () => {
    const a = job({ id: "a", date: "2026-10-02", title: "B" })
    const b = job({ id: "b", date: "2026-10-05", title: "A" })
    const c = job({ id: "c", date: null, title: "A" })
    const d = job({ id: "d", date: "2026-10-05", title: "Z" })
    expect([a, c, d, b].sort(compareJobs).map((j) => j.id)).toEqual(["b", "d", "a", "c"])
  })
})
