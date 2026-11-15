"""The hosted embedder must match the local model the Neon index was built with."""

import os

import numpy as np
import pytest
from dotenv import load_dotenv

from agent.config import ROOT, get_config
from rag.embeddings import build

load_dotenv(ROOT / ".env")
TEXTS = ["build a RAG chatbot with LangChain", "Power BI sales dashboard for a retail chain",
         "React and Django full-stack app with Stripe payments"]

pytestmark = pytest.mark.skipif(not os.getenv("NOMIC_API_KEY"), reason="NOMIC_API_KEY not set")


def test_hosted_matches_local() -> None:
    pytest.importorskip("sentence_transformers")
    cfg = get_config().rag.embeddings
    assert cfg.hosted and cfg.hosted.model == cfg.model and cfg.hosted.dim == cfg.dim
    local, hosted = build(cfg), build(cfg.hosted)
    for a, b in [(local.embed_query(t), hosted.embed_query(t)) for t in TEXTS] + list(
            zip(local.embed_documents(TEXTS), hosted.embed_documents(TEXTS), strict=True)):
        cos = float(np.dot(a, b) / np.linalg.norm(a) / np.linalg.norm(b))
        assert cos > 0.99, cos
