# Private wiki question answering for Strata Engineering Group

I built an on-premise question answering assistant for **Strata Engineering Group** to help engineers search and use a large internal wiki of engineering standards without moving any documents outside the company network. The core challenge was practical as much as technical: the source material was spread across **14k pages**, and the team needed a way to ask natural-language questions and get reliable, traceable answers while keeping everything inside their environment.

My approach centered on a retrieval pipeline in Python using **LlamaIndex**, **Qdrant**, **Ollama**, **Llama 3**, and **FastAPI**. I designed the system so that documents were indexed locally, embedded into a vector store, and retrieved at query time before the model generated a response. Because the deployment had to remain inside the client network, I used a local model served through Ollama rather than any external API. That kept the entire flow private and aligned with the client’s constraints.

The architecture was intentionally simple and production-oriented: ingest standards, chunk and index the content, retrieve the most relevant passages, then generate an answer from those passages through a FastAPI service. I focused on making the pipeline robust enough for real engineering queries, where terminology is specific and answers need to come from the right section of the standards library.

```python
from llama_index.core import VectorStoreIndex, Settings
from llama_index.vector_stores.qdrant import QdrantVectorStore

vector_store = QdrantVectorStore(client=qdrant_client, collection_name="standards")
Settings.llm = ollama_llm
Settings.embed_model = local_embed_model

index = VectorStoreIndex.from_vector_store(vector_store)
query_engine = index.as_query_engine(similarity_top_k=3)
answer = query_engine.query("What is the required inspection interval?")
```

The result was an assistant that could answer questions over the internal wiki without sending data outside the network. In validation, it reached an **82% top-3 hit rate on 60 engineer questions**, and the system made **zero external API calls**. For Strata Engineering Group, that meant a practical way to surface standards quickly while preserving network isolation and keeping the deployment fully under their control.
