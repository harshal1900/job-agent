# ats-search endpoint reference

What each ATS exposes and how `ats-search` uses it. Re-check here first when a board
stops working.

## Greenhouse (official Job Board API)

| Call | URL |
|---|---|
| List | `GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs` |
| One posting | `GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{id}?pay_transparency=true` |

List fields used: `id`, `title`, `absolute_url`, `company_name`, `location.name`,
`first_published`, `updated_at`, `departments[0].name`, `pay_input_ranges`. The list omits
`content` (the description) unless `?content=true`, which makes large boards very big,
so descriptions come from the one-posting call. `content` is **HTML-escaped twice**
(`&lt;p&gt;`), so it is entity-decoded before tags are stripped. `location.name` is free
text and sometimes several offices joined by commas. Unknown token → `404`.

## Lever (official Postings API)

| Call | URL |
|---|---|
| List | `GET https://api.lever.co/v0/postings/{token}?mode=json` |
| One posting | `GET https://api.lever.co/v0/postings/{token}/{uuid}` |

Fields used: `id`, `text` (title), `hostedUrl`, `createdAt` (epoch ms), `country`,
`workplaceType` (`remote|hybrid|on-site`), `categories.{location,team,commitment,allLocations}`,
`descriptionPlain`, `lists`, `additionalPlain`, `salaryRange`. Unknown token → `404`.

## Ashby (public job-board API)

| Call | URL |
|---|---|
| List (and the only source for one posting) | `GET https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true` |

Fields used: `id`, `title`, `department`, `team`, `employmentType`, `location`,
`secondaryLocations[].location`, `publishedAt`, `isListed`, `isRemote`, `workplaceType`,
`jobUrl`, `descriptionHtml`/`descriptionPlain`, `compensation.scrapeableCompensationSalarySummary`.
There is no single-posting endpoint, so `detail` re-reads the board. Unknown token → `404`.

## Workday (unofficial CXS endpoints)

| Call | URL |
|---|---|
| List / search | `POST https://{tenant}.{wdN}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` body `{"appliedFacets":{},"limit":20,"offset":0,"searchText":""}` |
| One posting | `GET https://{tenant}.{wdN}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{externalPath}` |

- `limit` above **20** returns `400`. `total` is reported on the first page only.
- List item: `title`, `externalPath` (`/job/<location>/<slug>_<reqId>`), `locationsText`
  (often `"3 Locations"`), `postedOn` (`"Posted 4 Days Ago"`, `"Posted 30+ Days Ago"`).
- Posting: `jobPostingInfo.{title, jobDescription (HTML), location, additionalLocations,
  startDate, country.descriptor, timeType, remoteType, externalUrl}`.
- `facets` in the list response describe the tenant's filters. Location facets differ per
  tenant: `locationHierarchy1` (NVIDIA), `locationCountry` (Adobe), or only per-site
  `locations` (Salesforce). Different facet parameters are ANDed, so exactly one is applied.
- Public posting URL: `https://{tenant}.{wdN}.myworkdayjobs.com/{site}{externalPath}`.
- Wrong tenant/host/site → `404` or `422`.
