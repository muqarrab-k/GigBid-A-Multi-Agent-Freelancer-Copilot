import os
from typing import Iterable, List, Dict, Any

from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_postgres import PGVector


def _chunk_contract(text: str, source: str, page: int) -> List[Dict[str, Any]]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1200,
        chunk_overlap=150,
        separators=["\n\n", "\n", ". ", "; ", ", ", " "],
    )
    chunks = splitter.split_text(text)
    return [
        {
            "page_content": chunk.strip(),
            "metadata": {"source": source, "page": page, "chunk_index": idx},
        }
        for idx, chunk in enumerate(chunks)
        if chunk.strip()
    ]


def ingest_contracts(contract_pages: Iterable[Dict[str, Any]]) -> None:
    connection = os.environ["POSTGRES_CONNECTION_STRING"]
    collection_name = os.getenv("PGVECTOR_COLLECTION", "clause_search")
    embeddings = OpenAIEmbeddings(model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"))

    vectorstore = PGVector(
        connection=connection,
        embeddings=embeddings,
        collection_name=collection_name,
        use_jsonb=True,
    )

    docs: List[Document] = []
    for page_data in contract_pages:
        text = page_data.get("text", "")
        source = page_data.get("source", "")
        page = int(page_data.get("page", 0))
        for chunk in _chunk_contract(text, source, page):
            docs.append(Document(page_content=chunk["page_content"], metadata=chunk["metadata"]))

    if docs:
        vectorstore.add_documents(docs)


if __name__ == "__main__":
    raise SystemExit("Import ingest_contracts() from this module and call it with page-level contract text.")
