import { describe, expect, test } from "bun:test"
import { readFileSync } from "node:fs"
import { countriesOf } from "../src/geo.js"
import { normalizeGreenhouse } from "../src/providers/greenhouse.js"
import { normalizeLever } from "../src/providers/lever.js"
import { normalizeAshby } from "../src/providers/ashby.js"
import { isSafeWorkdayPath, normalizeWorkdayListing, pickCountryFacet, postedDays } from "../src/providers/workday.js"

const fx = (name: string) => JSON.parse(readFileSync(new URL(`./fixtures/${name}`, import.meta.url), "utf8"))

describe("greenhouse", () => {
  const board = { ats: "greenhouse" as const, company: "stripe" }
  test("normalises a live listing", () => {
    const jobs = fx("greenhouse-list.json").jobs.map((j: any) => normalizeGreenhouse(board, j, false))
    const sf = jobs.find((j: any) => j.location.includes("San Francisco"))
    expect(sf.id).toBe(`greenhouse:stripe:${sf.detailRef}`)
    expect(sf.country).toBe("US")
    expect(sf.company).toBe("Stripe")
    expect(sf.date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(sf.description).toBeNull()
    expect(sf.url).toStartWith("https://")
    expect(jobs.find((j: any) => j.location === "Dublin").country).toBeNull()
  })
  test("detail has a text description with entities decoded", () => {
    const j = normalizeGreenhouse(board, fx("greenhouse-detail.json"), true)
    expect(j.description).not.toBeNull()
    expect(j.description).not.toContain("&lt;")
    expect(j.description).not.toContain("<p>")
    expect(j.description!.length).toBeGreaterThan(200)
  })
  test("pay ranges become a salary string", () => {
    const raw = { ...fx("greenhouse-list.json").jobs[0], pay_input_ranges: [{ min_cents: 15000000, max_cents: 22500000, currency_type: "USD" }] }
    expect(normalizeGreenhouse(board, raw, false).salary).toBe("$150,000 – $225,000")
    expect(normalizeGreenhouse(board, { ...raw, pay_input_ranges: [] }, false).salary).toBeNull()
  })
  test("geography kept in a custom metadata field (Cloudflare style)", () => {
    const raw = {
      id: 9, title: "Account Executive", absolute_url: "https://x", location: { name: "Hybrid" },
      metadata: [
        { id: 1, name: "Cost Center", value: "5150 - Field Sales", value_type: "single_select" },
        { id: 2, name: "Job Posting Location", value: ["Austin, US", "New York, US"], value_type: "multi_select" },
      ],
    }
    const j = normalizeGreenhouse(board, raw, false)
    expect(j.locations).toEqual(["Hybrid", "Austin, US", "New York, US"])
    expect(j.location).toBe("Austin, US") // the first candidate that names a place
    expect(j.country).toBe("US")
    expect(normalizeGreenhouse(board, { ...raw, metadata: null }, false).locations).toEqual(["Hybrid"])
  })
  test("office locations are used when the location name is not a place", () => {
    const raw = { id: 9, title: "T", absolute_url: "https://x", location: { name: "N/A" }, offices: [{ name: "Toronto", location: "Toronto, Ontario, Canada" }] }
    const j = normalizeGreenhouse(board, raw, false)
    expect(j.country).toBe("CA")
  })
  test("missing optional fields do not throw", () => {
    const j = normalizeGreenhouse(board, { id: 1, title: " T ", absolute_url: "https://x" }, false)
    expect(j.title).toBe("T")
    expect(j.location).toBe("")
    expect(j.date).toBeNull()
  })
})

describe("lever", () => {
  const board = { ats: "lever" as const, company: "palantir" }
  const postings = fx("lever-list.json")
  test("normalises live postings", () => {
    const us = normalizeLever(board, postings.find((p: any) => p.country === "US"))
    expect(us.country).toBe("US")
    expect(us.id).toStartWith("lever:palantir:")
    expect(us.url).toStartWith("https://jobs.lever.co/palantir/")
    expect(us.employmentType).toBe("Full-time")
    expect(us.description).toBeTruthy()
    expect(["remote", "hybrid", "onsite", null]).toContain(us.workplace)
    expect(normalizeLever(board, postings.find((p: any) => p.country === "SG")).country).toBeNull()
  })
  test("salary range formatting", () => {
    const p = { ...postings[0], salaryRange: { min: 100000, max: 150000, currency: "USD", interval: "per-year-salary" } }
    expect(normalizeLever(board, p).salary).toBe("USD 100,000 – 150,000 per year-salary")
    expect(normalizeLever(board, { ...postings[0], salaryRange: null }).salary).toBeNull()
  })
})

describe("ashby", () => {
  const board = { ats: "ashby" as const, company: "ramp" }
  test("normalises live jobs with locations and compensation", () => {
    const j = normalizeAshby(board, fx("ashby-list.json").jobs[0])
    expect(j.id).toStartWith("ashby:ramp:")
    expect(j.locations.length).toBeGreaterThanOrEqual(1)
    // US and Canada locations on one posting: no single country, both in countriesOf
    expect(j.country).toBeNull()
    expect([...countriesOf(j.locations)].sort()).toEqual(["CA", "US"])
    expect(j.salary).toContain("$")
    expect(j.description).toBeTruthy()
    expect(j.description).not.toContain("<")
    expect(j.workplace).toBe("hybrid")
  })
  test("isRemote with no workplaceType is remote", () => {
    const raw = { ...fx("ashby-list.json").jobs[0], workplaceType: undefined, isRemote: true }
    expect(normalizeAshby(board, raw).workplace).toBe("remote")
  })
})

describe("workday", () => {
  const board = { ats: "workday" as const, company: "nvidia", host: "wd5", site: "NVIDIAExternalCareerSite" }
  test("postedDays", () => {
    expect(postedDays("Posted Today")).toBe(0)
    expect(postedDays("Posted Yesterday")).toBe(1)
    expect(postedDays("Posted 4 Days Ago")).toBe(4)
    expect(postedDays("Posted 30+ Days Ago")).toBeNull()
    expect(postedDays(undefined)).toBeNull()
    expect(postedDays("whenever")).toBeNull()
  })
  test("listing normalisation derives an approximate date and keeps the path", () => {
    const now = new Date("2026-10-23T09:00:00Z")
    const p = { title: "Eng", externalPath: "/job/US-CA-Santa-Clara/Eng_JR1", locationsText: "US, CA, Santa Clara", postedOn: "Posted 3 Days Ago" }
    const j = normalizeWorkdayListing(board, p, null, now)
    expect(j.date).toBe("2026-10-20")
    expect(j.dateApproximate).toBe(true)
    expect(j.country).toBe("US")
    expect(j.url).toBe("https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/US-CA-Santa-Clara/Eng_JR1")
    const old = normalizeWorkdayListing(board, { ...p, postedOn: "Posted 30+ Days Ago", locationsText: "2 Locations" }, "US", now)
    expect(old.date).toBeNull()
    expect(old.country).toBe("US") // forced by the server-side country facet
  })
  test("path safety", () => {
    expect(isSafeWorkdayPath("/job/US-CA/Senior-Engineer_JR1")).toBe(true)
    for (const bad of ["/job/../x", "/job/a/../../b", "job/x", "/other/x", "/job/x?y=1", "/job/x#f", "https://evil.com/job/x", "/job/"]) {
      expect(isSafeWorkdayPath(bad)).toBe(false)
    }
  })
  test("country facet: tenant with a country group (live Adobe facets)", () => {
    const picked = pickCountryFacet(fx("workday-facets-adobe.json"), ["US", "CA"])
    expect(picked).not.toBeNull()
    const [param, ids] = Object.entries(picked!)[0]
    expect(param).toBe("locationCountry")
    expect(ids.length).toBe(2)
  })
  test("country facet: only US selected when only US is wanted", () => {
    const picked = pickCountryFacet(fx("workday-facets-adobe.json"), ["CA"])
    expect(Object.values(picked!)[0].length).toBe(1)
  })
  test("country facet: tenant with locationHierarchy1 (live NVIDIA facets)", () => {
    const picked = pickCountryFacet(fx("workday-facets-nvidia.json"), ["US"])
    expect(Object.keys(picked!)).toEqual(["locationHierarchy1"])
    expect(Object.values(picked!)[0].length).toBe(1)
  })
  test("country facet: falls back to per-site values, one parameter only", () => {
    const facets = [{ facetParameter: "locationMainGroup", values: [{ facetParameter: "locations", descriptor: "Locations", values: [
      { descriptor: "Canada - Toronto", id: "a" }, { descriptor: "Berlin", id: "b" }, { descriptor: "Austin, TX", id: "c" },
    ] }] }]
    expect(pickCountryFacet(facets, ["CA", "US"])).toEqual({ locations: ["a", "c"] })
  })
  test("country facet: none when nothing matches", () => {
    expect(pickCountryFacet([{ facetParameter: "locationMainGroup", values: [{ facetParameter: "locations", values: [{ descriptor: "Berlin", id: "b" }] }] }], ["US"])).toBeNull()
    expect(pickCountryFacet([], ["US"])).toBeNull()
  })
})
