import { describe, expect, test } from "bun:test"
import { loadConfig, parseConfig } from "../src/config.js"

describe("parseConfig", () => {
  test("valid boards, with names and a workday entry", () => {
    const boards = parseConfig(
      JSON.stringify({ boards: [{ ats: "greenhouse", company: "stripe", name: " Stripe " }, { ats: "workday", company: "nvidia", host: "wd5", site: "S" }] }),
      "t.json",
    )
    expect(boards).toEqual([
      { ats: "greenhouse", company: "stripe", name: "Stripe" },
      { ats: "workday", company: "nvidia", host: "wd5", site: "S" },
    ])
  })
  test("duplicates are collapsed", () => {
    const b = { ats: "lever", company: "x" }
    expect(parseConfig(JSON.stringify({ boards: [b, b, { ...b, company: "X" }] }), "t").length).toBe(1)
  })
  test.each([
    ["not json", "invalid JSON"],
    [JSON.stringify({}), "expected"],
    [JSON.stringify({ boards: [{ ats: "taleo", company: "x" }] }), "ats"],
    [JSON.stringify({ boards: [{ ats: "lever" }] }), "company"],
    [JSON.stringify({ boards: [{ ats: "lever", company: "a/b" }] }), "invalid"],
    [JSON.stringify({ boards: [{ ats: "workday", company: "x" }] }), "host"],
  ])("rejects %p", (text, message) => expect(() => parseConfig(text, "t.json")).toThrow(message))
  test("error messages name the entry", () => {
    expect(() => parseConfig(JSON.stringify({ boards: [{ ats: "lever", company: "ok" }, { ats: "nope", company: "x" }] }), "f.json")).toThrow("f.json boards[1]")
  })
})

describe("loadConfig", () => {
  test("a missing default file means no boards, a missing explicit file is an error", () => {
    expect(loadConfig("/nonexistent/none.json", false)).toEqual([])
    expect(() => loadConfig("/nonexistent/none.json", true)).toThrow("not found")
  })
  test("the shipped watchlist parses and has every ATS", () => {
    const boards = loadConfig(undefined, true)
    expect(new Set(boards.map((b) => b.ats))).toEqual(new Set(["greenhouse", "lever", "ashby", "workday"]))
  })
})
