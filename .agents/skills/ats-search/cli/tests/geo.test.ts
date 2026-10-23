import { describe, expect, test } from "bun:test"
import { countriesOf, inCountries, inferCountry, primaryCountry } from "../src/geo.js"

describe("inferCountry", () => {
  const us = [
    "San Francisco, CA", "New York, NY", "Austin, Texas", "Remote - US", "Remote (United States)",
    "United States", "USA", "Seattle, WA", "Washington, DC", "Boston, Massachusetts, United States",
    "US, CA, Santa Clara", "Remote, US", "Vancouver, WA", "Portland, OR", "Chicago", "Brooklyn, NY",
    "Washington, D.C.", "Washington DC, US", "D.C.", "Maryland", "Virginia", "Austin, US",
  ]
  const ca = [
    "Toronto, ON", "Toronto, Ontario", "Vancouver, BC", "Canada", "Remote (Canada)", "Remote - Canada",
    "Montreal, QC", "Calgary, Alberta", "Canada, Remote", "Toronto, Canada (Ethoca)", "Ottawa",
  ]
  const unknown = [
    "Remote", "", "Dublin", "London, UK", "Singapore, Singapore", "2 Locations", "Berlin, Germany",
    "Bangalore, India", "Georgia", "Hybrid", "Tokyo", "Washington", "N/A", "Distributed", "In-Office", "Sydney, Australia", "Paris, France",
  ]
  test.each(us)("US: %s", (s) => expect(inferCountry(s)).toBe("US"))
  test.each(ca)("CA: %s", (s) => expect(inferCountry(s)).toBe("CA"))
  test.each(unknown)("unknown: %s", (s) => expect(inferCountry(s)).toBeNull())

  test("', CA' is California, never Canada", () => {
    expect(inferCountry("Los Angeles, CA")).toBe("US")
    expect(inferCountry("Sunnyvale, CA, USA")).toBe("US")
  })
  test("bare 'us' and 'in' in prose are not countries", () => {
    expect(inferCountry("Join us in Berlin")).toBeNull()
    expect(inferCountry("Remote, in office twice a week")).toBeNull()
  })
  test("null and undefined are unknown", () => {
    expect(inferCountry(null)).toBeNull()
    expect(inferCountry(undefined)).toBeNull()
  })
  test("both countries named is ambiguous for a single string", () => {
    expect(inferCountry("US or Canada")).toBeNull()
  })
})

describe("countriesOf", () => {
  test("bare Greenhouse office list resolves each city", () => {
    expect([...countriesOf(["Seattle, San Francisco, New York City"])]).toEqual(["US"])
    expect([...countriesOf(["Toronto, Seattle"])].sort()).toEqual(["CA", "US"])
  })
  test("multi-location with separators", () => {
    expect([...countriesOf(["Dublin; San Francisco, CA"])]).toEqual(["US"])
    expect([...countriesOf(["Remote (US) | Remote (Canada)"])].sort()).toEqual(["CA", "US"])
  })
  test("a state suffix beats a city that exists in both countries", () => {
    expect([...countriesOf(["Vancouver, WA"])]).toEqual(["US"])
  })
  test("'US or Canada' names both", () => {
    expect([...countriesOf(["Remote - US or Canada"])].sort()).toEqual(["CA", "US"])
  })
  test("semicolon lists of bare states", () => {
    expect([...countriesOf(["Maryland; Virginia; Washington, D.C."])]).toEqual(["US"])
  })
  test("unknown stays empty", () => {
    expect(countriesOf(["Remote", "Dublin"]).size).toBe(0)
  })
})

describe("primaryCountry / inCountries", () => {
  test("single country only", () => {
    expect(primaryCountry(["Austin, TX"])).toBe("US")
    expect(primaryCountry(["Toronto, ON", "Austin, TX"])).toBeNull()
    expect(primaryCountry([])).toBeNull()
  })
  test("inCountries is true when any wanted country is present", () => {
    expect(inCountries(["London, UK", "Toronto, ON"], ["CA"])).toBe(true)
    expect(inCountries(["London, UK"], ["US", "CA"])).toBe(false)
  })
})
