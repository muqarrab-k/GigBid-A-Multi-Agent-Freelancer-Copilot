End-to-end test suite for the broker quoting flow, built with Playwright and wired for pull-request runs.

## Setup

Install dependencies in the repo root:

```bash
npm install
```

The suite uses TypeScript, Playwright, Docker, and GitHub Actions. Review `playwright.config.ts` for retry and trace settings before running in different environments.

## Usage

Run the browser tests locally:

```bash
npx playwright test
```

To run the single broker quote spec:

```bash
npx playwright test tests/quote.spec.ts
```

If you need to inspect the configuration used in automation, check `playwright.config.ts` for the CI project definition and failure tracing behavior.

## Notes

- `tests/quote.spec.ts` contains the broker quote flow coverage.
- `playwright.config.ts` enables retries and saves traces on failure.
- The suite was built to run on every pull request.
- Coverage reached 160 tests.
- The work helped reduce release regressions from 6 per quarter to 1.
