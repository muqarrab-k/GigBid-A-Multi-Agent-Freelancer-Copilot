from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_postgres import PGVector
from langchain_core.prompts import ChatPromptTemplate

DATABASE_URL = os.getenv("DATABASE_URL", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
COLLECTION_NAME = os.getenv("PGVECTOR_COLLECTION", "clauses")


def _vectorstore() -> PGVector:
    embeddings = OpenAIEmbeddings()
    return PGVector(
        embeddings=embeddings,
        collection_name=COLLECTION_NAME,
        connection=DATABASE_URL,
        use_jsonb=True,
    )


def retrieve_clauses(question: str, k: int = 5) -> List[Any]:
    store = _vectorstore()
    return store.similarity_search(question, k=k)


def build_context(docs: List[Any]) -> str:
    parts: List[str] = []
    for i, doc in enumerate(docs, start=1):
        meta = doc.metadata or {}
        clause = meta.get("clause", meta.get("title", ""))
        page = meta.get("page", "unknown")
        parts.append(f"[{i}] page={page} clause={clause}\n{doc.page_content}")
    return "\n\n".join(parts)


def answer_question(question: str, k: int = 5) -> Dict[str, Any]:
    docs = retrieve_clauses(question, k=k)
    context = build_context(docs)

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "Answer only using the provided clauses. If the answer is not in the clauses, say you cannot determine it. "
                "Always cite the clause and page for every claim.",
            ),
            ("user", "Question: {question}\n\nClauses:\n{context}"),
        ]
    )

    llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)
    chain = prompt | llm
    response = chain.invoke({"question": question, "context": context})

    return {
        "answer": response.content,
        "sources": [
            {
                "clause": doc.metadata.get("clause"),
                "page": doc.metadata.get("page"),
                "source": doc.metadata.get("source"),
            }
            for doc in docs
        ],
    }
