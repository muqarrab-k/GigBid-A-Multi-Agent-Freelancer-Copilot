# Overnight statement rendering pipeline

In 2022, I worked with **Alder Property Group** on a fixed-scope project to improve how owner statements were produced and delivered. Their existing flow was generating documents at request time, which made the experience fragile under load. As volume grew, requests could stall long enough to time out, creating a poor operational experience for both staff and end users.

My solution was to move statement creation out of the request path and into an overnight processing pipeline. I built it with **Node.js**, **BullMQ**, **Redis**, **Puppeteer**, and **AWS S3**. The core idea was simple: queue statement render requests, process them in the night, generate the final files, and store them in S3 so they were ready to fetch later instead of being assembled on demand.

That shift changed the architecture in a few important ways. First, it separated user-facing actions from heavy rendering work, which made the system much more resilient. Second, using a queue gave us a controlled way to process a large monthly batch without overwhelming the application. Third, storing the completed files in S3 meant the outputs were durable and easy to serve once created.

A small part of the queue setup looked like this:

```js
import { Queue } from 'bullmq';

const statementQueue = new Queue('owner-statements', {
  connection: {
    host: process.env.REDIS_HOST,
    port: 6379
  }
});

await statementQueue.add('render-monthly-statement', {
  ownerId,
  period: '2022-07'
});
```

The result was a much smoother workflow for Alder Property Group. The system handled **12k statements a month**, and the request timeouts that had been happening daily went to none. From a technical standpoint, the biggest win was turning a synchronous bottleneck into a predictable overnight pipeline, while keeping the delivery format and storage simple for the team to use afterward.
