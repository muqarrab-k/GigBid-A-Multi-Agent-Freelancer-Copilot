Monthly statement PDF worker that renders statement HTML to PDF and uploads the file to S3.

## Setup

Install dependencies and configure the runtime for Node.js, Redis, BullMQ, Puppeteer, and AWS S3 access.

Expected environment:
- Redis connection for the queue
- AWS credentials with access to the target S3 bucket
- Any template data required by the statement renderer

## Usage

Start the worker process so it can consume queued statement render tasks.

```bash
npm install
npm run worker
```

The worker reads jobs, renders the statement through Puppeteer, and uploads the resulting file to S3. Retries are handled in `worker.ts`.

## Notes

- `worker.ts` contains the BullMQ worker logic.
- `render.ts` contains the Puppeteer helper that converts an HTML template into a PDF buffer.
- This repo is meant for overnight statement rendering instead of on-demand generation.
- The queue was used to handle roughly twelve thousand statements per month.
- Moving the work off the request path eliminated the daily timeout issue.
