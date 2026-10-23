// US / Canada location recognition for free-text ATS location strings.
//
// ATS boards give a location as text ("San Francisco, CA", "Remote - US",
// "Toronto, Ontario"), not as a structured country, so the country is inferred.
// The matcher is conservative: an ambiguous or unrecognised string resolves to
// null rather than to a guess, and the search command drops null-country jobs
// unless --include-unspecified-location is passed.

import type { Country } from "./types.js"

const US_STATES: Record<string, string> = {
  AL: "Alabama", AK: "Alaska", AZ: "Arizona", AR: "Arkansas", CA: "California", CO: "Colorado",
  CT: "Connecticut", DE: "Delaware", DC: "District of Columbia", FL: "Florida", GA: "Georgia",
  HI: "Hawaii", ID: "Idaho", IL: "Illinois", IN: "Indiana", IA: "Iowa", KS: "Kansas",
  KY: "Kentucky", LA: "Louisiana", ME: "Maine", MD: "Maryland", MA: "Massachusetts",
  MI: "Michigan", MN: "Minnesota", MS: "Mississippi", MO: "Missouri", MT: "Montana",
  NE: "Nebraska", NV: "Nevada", NH: "New Hampshire", NJ: "New Jersey", NM: "New Mexico",
  NY: "New York", NC: "North Carolina", ND: "North Dakota", OH: "Ohio", OK: "Oklahoma",
  OR: "Oregon", PA: "Pennsylvania", RI: "Rhode Island", SC: "South Carolina", SD: "South Dakota",
  TN: "Tennessee", TX: "Texas", UT: "Utah", VT: "Vermont", VA: "Virginia", WA: "Washington",
  WV: "West Virginia", WI: "Wisconsin", WY: "Wyoming", PR: "Puerto Rico",
}

const CA_PROVINCES: Record<string, string> = {
  AB: "Alberta", BC: "British Columbia", MB: "Manitoba", NB: "New Brunswick",
  NL: "Newfoundland and Labrador", NS: "Nova Scotia", NT: "Northwest Territories",
  NU: "Nunavut", ON: "Ontario", PE: "Prince Edward Island", QC: "Quebec", SK: "Saskatchewan",
  YT: "Yukon",
}

// Cities that name a single metro in the US/Canada and no well-known place
// elsewhere. Ambiguous names (Dublin, Birmingham, London, Cambridge, Paris,
// Manchester, Portland-without-state) are deliberately absent.
const US_CITIES = [
  "new york city", "new york", "nyc", "san francisco", "bay area", "silicon valley", "los angeles",
  "san diego", "san jose", "seattle", "bellevue", "redmond", "chicago", "boston", "austin",
  "dallas", "houston", "denver", "boulder", "atlanta", "miami", "washington dc", "washington, dc",
  "philadelphia", "pittsburgh", "phoenix", "minneapolis", "detroit", "nashville", "raleigh",
  "charlotte", "salt lake city", "palo alto", "mountain view", "sunnyvale", "menlo park",
  "redwood city", "santa clara", "cupertino", "oakland", "brooklyn", "san mateo", "irvine",
  "santa monica", "culver city", "las vegas", "orlando", "tampa", "kansas city", "st. louis",
  "columbus", "cleveland", "cincinnati", "indianapolis", "baltimore", "durham", "boise",
]

const CA_CITIES = [
  "toronto", "vancouver", "montreal", "montréal", "ottawa", "calgary", "edmonton", "waterloo",
  "kitchener", "mississauga", "winnipeg", "halifax", "quebec city", "victoria, bc", "markham",
]

// A whole location part that is just a state ("Maryland") or the capital. "Georgia"
// and bare "Washington" are left out: a country and a UK town share those names.
const STATE_ONLY = new RegExp(`^(${stateNamesForBareMatch()})$`, "i")
const DC = /\b(washington,?\s*d\.?\s*c\.?|d\.c\.)(?![a-z])/i

function stateNamesForBareMatch(): string {
  return Object.values(US_STATES)
    .filter((n) => n !== "Georgia" && n !== "Washington")
    .map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("|")
}

const US_WORDS = /\b(united states( of america)?|u\.s\.a?\.?|usa)\b/i
const US_BARE = /(^|[\s,(/-])US($|[\s,)/-])/ // uppercase "US" only: "us" is a pronoun
const CA_WORDS = /\bcanada\b/i

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

const stateNames = Object.values(US_STATES).filter((n) => n !== "Georgia" && n !== "Washington" && n !== "New York")
const provinceNames = Object.values(CA_PROVINCES)

// ", CA" / ", Ontario" style: a state or province after a comma, dash or paren
// so that the bare words "in", "or", "me" in prose never match.
const STATE_AFTER_SEP = new RegExp(`[,(-]\\s*(${Object.keys(US_STATES).join("|")})(?![A-Za-z])`)
const PROVINCE_AFTER_SEP = new RegExp(`[,(-]\\s*(${Object.keys(CA_PROVINCES).join("|")})(?![A-Za-z])`)
const STATE_NAME_AFTER_SEP = new RegExp(`[,(-]\\s*(${[...stateNames, "Georgia", "Washington", "New York"].map(escapeRe).join("|")})(?![A-Za-z])`, "i")
const PROVINCE_NAME_ANY = new RegExp(`\\b(${provinceNames.map(escapeRe).join("|")})\\b`, "i")
const US_CITY_RE = new RegExp(`(^|[^a-z])(${US_CITIES.map(escapeRe).join("|")})($|[^a-z])`, "i")
const CA_CITY_RE = new RegExp(`(^|[^a-z])(${CA_CITIES.map(escapeRe).join("|")})($|[^a-z])`, "i")

/**
 * Infer the country of one location string, or null when it is unknown or
 * ambiguous. "Remote" alone is unknown; "Remote - US" and "Remote (Canada)" are
 * recognised through their country word.
 */
export function inferCountry(location: string | null | undefined): Country | null {
  if (!location) return null
  const text = location.trim()
  if (!text) return null
  if (STATE_ONLY.test(text) || DC.test(text)) return "US"
  const hasCa = CA_WORDS.test(text)
  const hasUs = US_WORDS.test(text) || US_BARE.test(text)
  if (hasCa && !hasUs) return "CA"
  if (hasUs && !hasCa) return "US"
  if (hasCa && hasUs) return null // "US or Canada": belongs to both, let the caller see both
  // Province before state: ", ON" and ", AB" etc. are unambiguous, and ", CA" must
  // stay California rather than Canada.
  if (PROVINCE_AFTER_SEP.test(text) && !STATE_AFTER_SEP.test(text)) return "CA"
  if (STATE_AFTER_SEP.test(text) && !PROVINCE_AFTER_SEP.test(text)) return "US"
  if (PROVINCE_NAME_ANY.test(text) && !STATE_AFTER_SEP.test(text)) return "CA"
  if (STATE_NAME_AFTER_SEP.test(text)) return "US"
  const usCity = US_CITY_RE.test(text)
  const caCity = CA_CITY_RE.test(text)
  if (caCity && !usCity) return "CA"
  if (usCity && !caCity) return "US"
  return null
}

/** Countries named by a (possibly multi-location) list of location strings. */
export function countriesOf(locations: string[]): Set<Country> {
  const found = new Set<Country>()
  for (const loc of locations) {
    // ";" or "|" separate distinct places on some boards.
    for (const part of loc.split(/[;|]/)) {
      const c = inferCountry(part)
      if (c) {
        found.add(c)
        continue
      }
      // No country, state or province in the text: Greenhouse joins offices as bare
      // city names ("Seattle, San Francisco, New York City"), so look for known
      // cities. Never done when a state/province was found, so "Vancouver, WA" stays US.
      if (/\b(US|USA|United States)\b/i.test(part) && /\bCanada\b/i.test(part)) {
        found.add("US")
        found.add("CA")
        continue
      }
      for (const city of citiesIn(part)) found.add(city)
    }
  }
  return found
}

function citiesIn(location: string): Country[] {
  const out: Country[] = []
  if (US_CITY_RE.test(location)) out.push("US")
  if (CA_CITY_RE.test(location)) out.push("CA")
  return out
}

/** The single country of a job, or null when it is unknown or spans several. */
export function primaryCountry(locations: string[]): Country | null {
  const found = countriesOf(locations)
  return found.size === 1 ? [...found][0] : null
}

/** True when the job is located in at least one of the wanted countries. */
export function inCountries(locations: string[], wanted: Country[]): boolean {
  const found = countriesOf(locations)
  return wanted.some((c) => found.has(c))
}
