// HTML → readable plain text for job descriptions, plus small string helpers.
// Regex-based on purpose (zero dependencies); ATS descriptions are simple
// block markup, and the output is read by an LLM, not rendered.

const NAMED: Record<string, string> = {
  amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " ", ndash: "–", mdash: "—",
  lsquo: "‘", rsquo: "’", ldquo: "“", rdquo: "”", hellip: "…", bull: "•", middot: "·",
  copy: "©", reg: "®", trade: "™", eacute: "é", egrave: "è", agrave: "à", ccedil: "ç",
}

export function decodeEntities(s: string): string {
  return s.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (m, body: string) => {
    if (body[0] === "#") {
      const code = body[1].toLowerCase() === "x" ? parseInt(body.slice(2), 16) : parseInt(body.slice(1), 10)
      if (!Number.isFinite(code) || code < 0 || code > 0x10ffff) return m
      try {
        return String.fromCodePoint(code)
      } catch {
        return m
      }
    }
    return NAMED[body.toLowerCase()] ?? m
  })
}

/**
 * Convert description HTML to text. Greenhouse double-escapes its `content`
 * (the markup arrives as `&lt;p&gt;`), so pass `escaped: true` to decode one
 * layer first.
 */
export function htmlToText(html: string | null | undefined, opts: { escaped?: boolean } = {}): string {
  if (!html) return ""
  let s = opts.escaped ? decodeEntities(html) : html
  s = s
    .replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1>/gi, "")
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<li\b[^>]*>/gi, "\n- ")
    .replace(/<\/(p|div|h[1-6]|ul|ol|tr|section|article|blockquote)>/gi, "\n\n")
    .replace(/<[^>]+>/g, "")
  s = decodeEntities(s)
  return s
    .replace(/ /g, " ")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n[ \t]+/g, "\n")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
}

/** Epoch-ms or ISO timestamp → `YYYY-MM-DD` (UTC), or null when unparseable. */
export function toIsoDate(value: string | number | null | undefined): string | null {
  if (value === null || value === undefined || value === "") return null
  const d = typeof value === "number" ? new Date(value) : new Date(value)
  if (Number.isNaN(d.getTime())) return null
  return d.toISOString().slice(0, 10)
}

/** Whole days between `iso` (YYYY-MM-DD) and today (UTC); null for a bad date. */
export function ageInDays(iso: string | null, now = new Date()): number | null {
  if (!iso) return null
  const t = Date.parse(`${iso}T00:00:00Z`)
  if (Number.isNaN(t)) return null
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate())
  return Math.floor((today - t) / 86_400_000)
}

export function uniq(values: string[]): string[] {
  return [...new Set(values.map((v) => v.trim()).filter(Boolean))]
}
