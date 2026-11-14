# Model deployment pipeline migration

In 2024, I worked with a client in insurance (name withheld) to modernize how their pricing models were packaged, tested, and deployed. The team had been relying on hand-copied pickle files, which made releases slow, brittle, and difficult to trust. Every deployment required manual coordination, and the path from a trained model to a live endpoint was too dependent on individual steps being done correctly.

I was engaged hourly from 2024-06 to 2024-09 to help move that process onto a more reliable foundation. My focus was on making model delivery repeatable and easier for the team to operate day to day. I built a deployment pipeline around MLflow, Docker, GitHub Actions, AWS SageMaker, and Python, and migrated 9 pricing models into an MLflow registry. I also added automated tests so the team could validate model artifacts and deployment steps before anything reached production.

A key part of the work was shifting the team away from ad hoc handoffs. Instead of manually copying files and coordinating releases by message or spreadsheet, their workflow became centered on a shared registry and a consistent deployment path. Models could now be versioned, tested, and promoted through a defined process, with SageMaker endpoints handling the runtime layer.

Here is a simplified example of the kind of registry-driven deployment configuration I used:

```yaml
name: deploy-model
on:
  push:
    branches: [main]
jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build Docker image
        run: docker build -t pricing-model .
      - name: Run tests
        run: python -m pytest
      - name: Deploy to SageMaker
        run: python deploy.py
```

The results were immediate. Deployment time dropped from 2 days to 35 minutes, and the 9 migrated models went live with no downtime. More importantly, the client’s team now works with a system that is easier to trust and much easier to repeat: model changes can move from development to production through a defined pipeline rather than a manual scramble.
