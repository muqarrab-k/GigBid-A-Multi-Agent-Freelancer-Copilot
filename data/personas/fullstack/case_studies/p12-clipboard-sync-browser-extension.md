# Clipboard sync for Clipboardly

In early 2024, I worked with **Clipboardly**, a productivity software team, on a fixed-scope build to help users carry saved text snippets from one device to another without friction. Their existing flow needed a more reliable way to keep content in sync while staying lightweight for everyday use.

I built a Chrome add-on in **TypeScript** and connected it to a small **Express** API with **MongoDB** behind it. The goal was to make snippet saving and retrieval feel immediate, while keeping the implementation simple enough for the team to maintain. On the client side, I handled the extension logic for capturing, storing, and syncing snippets. On the server side, I set up the API endpoints that accepted snippet data, returned the user’s saved items, and kept the records consistent across devices.

A small part of the API wiring looked like this:

```ts
import express from "express";

const app = express();
app.use(express.json());

app.get("/snippets", async (_req, res) => {
  const snippets = await db.collection("snippets").find({}).toArray();
  res.json(snippets);
});

app.post("/snippets", async (req, res) => {
  await db.collection("snippets").insertOne(req.body);
  res.sendStatus(201);
});
```

What mattered most was the operating model this gave Clipboardly’s team. Instead of treating saved snippets as local-only data, they now have a sync layer that supports a smoother user workflow across devices. That changed the experience from “save here and hope it’s available later” to a more dependable system the product team can build on.

The result was a shipped product with clear traction: **9k weekly active users** and a **4.7 store rating**. For Clipboardly, that meant the team could support a growing user base with a feature set centered on consistency, speed, and cross-device continuity.
