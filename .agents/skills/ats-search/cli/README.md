# ats-search CLI

Searches the public job boards of the companies in `config/target_companies.json` on
Greenhouse, Lever, Ashby and Workday, filtered to the US and Canada. See `../SKILL.md`
for the full flag reference and `../url-reference.md` for the endpoints.

```bash
bun install            # dev types only; there are no runtime dependencies
bun run src/cli.ts companies --check
bun run src/cli.ts search -q "software engineer" --jobage 14 --format table
bun test               # offline: runs the real CLI against a local mock of all four APIs
bun run typecheck
```

## Layout

| File | Role |
|---|---|
| `src/cli.ts` | Flag parsing, validation, dispatch |
| `src/commands/` | `search` (fan out, filter, sort, hydrate), `detail`, `companies` |
| `src/providers/` | One adapter per ATS: list, one posting, normalisation |
| `src/boards.ts` | Board/job-id/URL parsing; every token placed in a URL is validated here |
| `src/geo.ts` | US/Canada inference from free-text locations |
| `src/query.ts` | `a OR b` syntax and the match predicates |
| `src/http.ts` | fetch with timeout, retry/backoff, `Retry-After`, bounded concurrency |
| `src/text.ts` | HTML to text, dates |
| `tests/` | Unit tests plus CLI tests against `tests/helpers.ts`'s mock server; `tests/fixtures/` are trimmed real API responses |

Each provider honours `ATS_GREENHOUSE_URL`, `ATS_LEVER_URL`, `ATS_ASHBY_URL` and
`ATS_WORKDAY_URL` so the tests (and a local proxy) can replace the API hosts.
