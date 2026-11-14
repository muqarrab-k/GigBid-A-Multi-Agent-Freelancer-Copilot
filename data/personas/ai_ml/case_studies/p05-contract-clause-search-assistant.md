# Contract clause search assistant

In 2023, I worked with a client in legal (name withheld) on a fixed-engagement project to make contract review faster and more reliable. Their team needed a way to answer questions across a large contract archive without forcing lawyers to open file after file and manually hunt for the right clause. The core requirement was not just finding relevant language, but also showing exactly where each answer came from so the legal team could verify it quickly.

I built an assistant over 9,000 contracts that responds to natural-language questions and always returns the clause text and page used to support the answer. The system was designed to help lawyers move from “find me the relevant section” to “show me the exact source” in one step. That mattered because the team’s workflow depended on trust, traceability, and speed.

My implementation used Python, LangChain, the OpenAI API, pgvector, PostgreSQL, and FastAPI. I structured the system so the user query could be compared against stored contract embeddings, the most relevant passages could be pulled from the document store, and the final response could be generated with citations tied to the underlying clause and page. That made the assistant useful in practice, not just impressive in a demo.

A simple version of the retrieval layer looked like this:

```python
query = user_question
matches = vector_store.similarity_search(query, k=5)

context = []
for doc in matches:
    context.append(
        f"Clause: {doc.metadata['clause']}\n"
        f"Page: {doc.metadata['page']}\n"
        f"Text: {doc.page_content}"
    )
```

The results were strong on both quality and workflow impact. On a 120-question lawyer-written test set, the assistant reached a faithfulness score of 0.91, which gave the team confidence that the answers were grounded in the source material. Operationally, clause lookup time dropped from 25 minutes to 3 minutes. That reduction changed the economics of routine review work and gave the legal team a much faster path to the exact language they needed.
