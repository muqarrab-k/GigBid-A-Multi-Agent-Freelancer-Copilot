"""Create or update the public Hugging Face Space and set its secrets from the local env.

Uploads only what the image needs; secrets go through the Space API, never into files.
Usage: python -m scripts.deploy_space [--space owner/name]
"""

import argparse
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent
FOLDERS = ["agent", "apps/api", "rag", "mcp_servers", "gigsim", "data/personas", "data/policy_pack"]
FILES = ["pyproject.toml", "apps/__init__.py", "data/processed/pricing_stats.json", "data/processed/scam_signals.json",
         "apps/web/package.json", "apps/web/package-lock.json", "apps/web/index.html", "apps/web/vite.config.ts",
         "apps/web/tsconfig.json"]
WEB = ["apps/web/src"]
SKIP = ("__pycache__", "/tests/", "gigsim/data/", ".pyc", ".DS_Store")
# secret name in the space -> local env name
SECRETS = {"DATABASE_URL": "NEON_DATABASE_URL", "GROQ_API_KEY": "GROQ_API_KEY", "APP_SECRET_KEY": "APP_SECRET_KEY",
           "REVIEWER_PASSWORD": "REVIEWER_PASSWORD", "LANGSMITH_API_KEY": "LANGSMITH_API_KEY"}
VARIABLES = {"MODEL_PROFILE": "open_hosted", "LANGSMITH_TRACING": "true", "LANGSMITH_PROJECT": "gigbid"}

README = """---
title: GigBid
emoji: 🧭
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: Multi-agent freelancer copilot (AI-4016 Assignment II)
---

GigBid: a multi-agent freelancer copilot. Open-weight models on Groq, Postgres on Neon, and a
simulated marketplace (GigSim) running inside the container. Nothing is sent without approval.
Source: https://github.com/muqarrab-k/GigBid-A-Multi-Agent-Freelancer-Copilot
"""


def wanted(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    return path.is_file() and not any(s in f"/{rel}" for s in SKIP)


def stage(folder: Path) -> None:
    """Copy the image's files into a clean folder."""
    paths = [ROOT / f for f in FILES]
    for name in FOLDERS + WEB:
        paths += [p for p in (ROOT / name).rglob("*") if wanted(p)]
    for src in paths:
        dst = folder / src.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
    (folder / "Dockerfile").write_bytes((ROOT / "infra/docker/Dockerfile.space").read_bytes())
    (folder / "README.md").write_text(README)


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy GigBid to a Hugging Face Space")
    parser.add_argument("--space", default=None, help="owner/name, default <you>/gigbid")
    parser.add_argument("--secrets-only", action="store_true")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    api = HfApi(token=os.environ["HF_TOKEN"])
    space = args.space or f"{api.whoami()['name']}/gigbid"
    api.create_repo(space, repo_type="space", space_sdk="docker", private=False, exist_ok=True)
    for name, env in SECRETS.items():
        if os.getenv(env):
            api.add_space_secret(space, name, os.environ[env])
        else:
            print(f"skipped secret {name}: {env} is not set")
    for name, value in VARIABLES.items():
        api.add_space_variable(space, name, value)
    if not args.secrets_only:
        with tempfile.TemporaryDirectory() as tmp:
            stage(Path(tmp))
            api.upload_folder(folder_path=tmp, repo_id=space, repo_type="space", commit_message="deploy",
                              delete_patterns=["*"])
    print(f"https://huggingface.co/spaces/{space}")


if __name__ == "__main__":
    main()
