# Insurance GraphQL API for Kestrel Insurance

In 2022, I worked with **Kestrel Insurance** on an hourly engagement to help support the launch of a new broker app. The core challenge was that the app needed a clean, modern API experience, but the business data still lived across **three legacy policy databases**. That made it difficult to deliver fast, consistent responses to the front end and created friction for the broker workflow.

My role was to build a **GraphQL layer** on top of the existing systems using **Node.js**, **Apollo**, **PostgreSQL**, and **DataLoader**. I designed the API so the broker app could ask for exactly the data it needed without having to understand the complexity of the underlying databases. A big part of the work was shaping the resolver structure so repeated lookups were handled efficiently, which reduced unnecessary database traffic and improved response times under real usage.

Here’s a simplified example of the kind of resolver setup I used:

```js
const resolvers = {
  Query: {
    policy: async (_, { id }, { loaders }) => {
      return loaders.policyById.load(id);
    },
  },
  Policy: {
    holder: async (parent, _, { loaders }) => {
      return loaders.holderById.load(parent.holderId);
    },
  },
};
```

The main business outcome was a much faster API for the new broker app. I brought **p95 API latency down from 1.2s to 240 ms**, which made the interface feel significantly more responsive and reduced the waiting time for brokers navigating policy data. That improvement mattered not just technically, but commercially: faster access to policy information meant a smoother product experience for users who needed answers quickly.

This project was a good example of using a modern API layer to extend the value of existing systems without replacing them all at once. For Kestrel Insurance, it provided a practical path forward: preserve the legacy data sources, but give the new broker app a cleaner, faster, and more scalable integration point.
