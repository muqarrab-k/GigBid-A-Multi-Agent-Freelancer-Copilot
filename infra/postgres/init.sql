-- runs once on a fresh volume
CREATE EXTENSION IF NOT EXISTS vector;
-- portfolio chunks and embeddings
CREATE SCHEMA IF NOT EXISTS rag;
-- langgraph checkpointer, later
CREATE SCHEMA IF NOT EXISTS langgraph;
