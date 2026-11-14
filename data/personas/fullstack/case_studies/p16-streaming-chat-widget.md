# Streaming chat widget for Quillstack

In early 2025, I worked with Quillstack, an edtech company, on a tutoring chat experience that needed to feel fast and responsive even while generating answers on the fly. The challenge was not just sending messages back and forth, but making the interface feel immediate enough for students to stay engaged while the assistant composed longer replies.

I built the front end in React and TypeScript, along with a Node.js proxy that sat between the UI and the OpenAI API. The key part of the implementation was delivering each answer incrementally, so the user could see the reply begin almost immediately instead of waiting for the full completion. That meant handling partial updates cleanly in the browser, keeping the UI stable as new text arrived, and making sure the server could pass those updates through reliably.

A small piece of the server setup looked like this:

```ts
app.get('/chat', async (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');

  for await (const chunk of streamFromOpenAI(req.query.prompt as string)) {
    res.write(`data: ${chunk}\n\n`);
  }

  res.end();
});
```

The result was a tutoring chat that felt much more responsive in day-to-day use. The first token appeared on screen in about 600 ms, which helped create a faster conversational feel for learners. The widget also supported Quillstack’s traffic at meaningful scale, handling 30k chats a month.

I worked on the project hourly from 2025-02 to 2025-04. For Quillstack, the impact was straightforward: a smoother student experience, less waiting during tutoring interactions, and a chat interface that better matched the pace of real conversation.
