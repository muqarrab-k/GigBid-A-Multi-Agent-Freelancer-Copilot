# End-to-end test suite for broker quoting

In April and May 2024, I worked with **Kestrel Insurance** on an end-to-end testing project for their broker quoting flow. The team needed a better way to catch issues before changes reached production. Because the quoting experience is a critical part of the product, even small regressions could create extra work for the team and slow down releases.

I built a browser test suite using **Playwright**, **TypeScript**, **Docker**, and **GitHub Actions**. The goal was to make the tests reliable enough to run automatically on every pull request, so the team could get fast feedback as soon as someone changed the quoting flow. I focused on the main broker journey and turned it into a set of browser checks that reflected how the application is used in practice.

A big part of the work was making the suite fit smoothly into the team’s delivery process. The tests run in a containerized environment and are wired into GitHub Actions, so developers can see failures as part of their normal review flow. That changed how the team works day to day: instead of waiting for issues to surface later, they can spot broken quoting paths before merge and address them while the code is still fresh.

Example configuration:

```yaml
name: browser-tests

on:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t quoting-tests .
      - run: docker run quoting-tests
```

By the end of the engagement, the suite covered **160 tests** and helped reduce release regressions from **6 a quarter to 1**. For Kestrel Insurance, that meant fewer surprises during release work and a more dependable path from pull request to production-ready code.
