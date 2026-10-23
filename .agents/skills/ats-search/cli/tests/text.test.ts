import { describe, expect, test } from "bun:test"
import { ageInDays, decodeEntities, htmlToText, toIsoDate, uniq } from "../src/text.js"

describe("decodeEntities", () => {
  test("named, decimal and hex", () => {
    expect(decodeEntities("A &amp; B &#39;x&#39; &#x2014; &ndash; &unknown;")).toBe("A & B 'x' — – &unknown;")
  })
  test("out-of-range code points are left alone", () => {
    expect(decodeEntities("&#99999999999;")).toBe("&#99999999999;")
  })
})

describe("htmlToText", () => {
  test("blocks, lists and inline tags", () => {
    const text = htmlToText("<h2>About</h2><p>Hello <b>world</b></p><ul><li>One</li><li>Two</li></ul><br>Tail")
    expect(text).toBe("About\n\nHello world\n\n- One\n- Two\n\nTail")
  })
  test("drops scripts, styles and comments", () => {
    expect(htmlToText("<style>p{}</style><!-- hi --><script>alert(1)</script><p>ok</p>")).toBe("ok")
  })
  test("Greenhouse double-escaped content", () => {
    expect(htmlToText("&lt;p&gt;Who we are &amp;amp; why&lt;/p&gt;", { escaped: true })).toBe("Who we are & why")
  })
  test("does not decode an entity into markup that is then kept", () => {
    expect(htmlToText("<p>1 &lt; 2 &gt; 0</p>")).toBe("1 < 2 > 0")
  })
  test("empty input", () => {
    expect(htmlToText(null)).toBe("")
    expect(htmlToText("")).toBe("")
  })
  test("collapses whitespace and nbsp", () => {
    expect(htmlToText("<p>a&nbsp;&nbsp;b</p>\n\n\n\n<p>c</p>")).toBe("a b\n\nc")
  })
})

describe("dates", () => {
  test("toIsoDate", () => {
    expect(toIsoDate("2026-09-03T13:32:53-04:00")).toBe("2026-09-03")
    expect(toIsoDate(1786469891368)).toBe("2026-08-11")
    expect(toIsoDate("nonsense")).toBeNull()
    expect(toIsoDate(null)).toBeNull()
    expect(toIsoDate("")).toBeNull()
  })
  test("ageInDays", () => {
    const now = new Date("2026-10-23T12:00:00Z")
    expect(ageInDays("2026-10-23", now)).toBe(0)
    expect(ageInDays("2026-10-13", now)).toBe(10)
    expect(ageInDays(null, now)).toBeNull()
    expect(ageInDays("bad", now)).toBeNull()
  })
  test("uniq trims and drops blanks", () => {
    expect(uniq([" a ", "a", "", "b"])).toEqual(["a", "b"])
  })
})
