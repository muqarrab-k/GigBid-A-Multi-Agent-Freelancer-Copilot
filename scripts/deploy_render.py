"""Build the slim image here, push it to Docker Hub, and create or update the free Render service.

The image is built locally because data/processed/ is git-ignored but the app needs two of its files.
Secrets go to Render through its API from the local env, never into files or the image.
Usage: python -m scripts.deploy_render [--skip-build]
"""

import argparse
import os
import subprocess
import time

import httpx
from dotenv import load_dotenv

from agent.config import ROOT

API = "https://api.render.com/v1"
NAME = "gigbid"
# render env var -> local env name
SECRETS = {"DATABASE_URL": "NEON_DATABASE_URL", "GROQ_API_KEY": "GROQ_API_KEY", "OPENROUTER_API_KEY": "OPENROUTER_API_KEY",
           "APP_SECRET_KEY": "APP_SECRET_KEY", "REVIEWER_PASSWORD": "REVIEWER_PASSWORD",
           "LANGSMITH_API_KEY": "LANGSMITH_API_KEY"}
PLAIN = {"MODEL_PROFILE": "open_hosted", "EMBEDDINGS_PROVIDER": "lite", "LANGSMITH_TRACING": "true",
         "LANGSMITH_PROJECT": "gigbid"}


def build_and_push(user: str) -> str:
    """Pushes with Docker Desktop's login; new repos on a free hub account are public."""
    tag = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    image = f"docker.io/{user}/gigbid:{tag or int(time.time())}"
    subprocess.run(["docker", "buildx", "build", "--platform", "linux/amd64", "-f", "infra/docker/Dockerfile.render",
                    "-t", image, "--push", "."], cwd=ROOT, check=True)
    return image


def env_vars() -> list[dict[str, str]]:
    found = [{"key": k, "value": os.environ[v]} for k, v in SECRETS.items() if os.getenv(v)]
    missing = [v for v in SECRETS.values() if not os.getenv(v)]
    if missing:
        print(f"not set locally, skipped: {missing}")
    return found + [{"key": k, "value": v} for k, v in PLAIN.items()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy GigBid to Render's free tier")
    parser.add_argument("--image", default=None, help="skip the build and deploy this image")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    http = httpx.Client(base_url=API, timeout=60, headers={"Authorization": f"Bearer {os.environ['RENDER_API_KEY']}"})
    image = args.image or build_and_push(os.environ["DOCKERHUB_USERNAME"])
    owner = http.get("/owners", params={"limit": 1}).raise_for_status().json()[0]["owner"]["id"]
    found = http.get("/services", params={"name": NAME, "ownerId": owner}).raise_for_status().json()
    if found:
        service = found[0]["service"]
        http.put(f"/services/{service['id']}/env-vars", json=env_vars()).raise_for_status()
        http.post(f"/services/{service['id']}/deploys", json={"imageUrl": image}).raise_for_status()
    else:
        body = {"type": "web_service", "name": NAME, "ownerId": owner,
                "image": {"ownerId": owner, "imagePath": image}, "envVars": env_vars(),
                "serviceDetails": {"runtime": "image", "plan": "free", "region": "oregon", "healthCheckPath": "/health"}}
        service = http.post("/services", json=body).raise_for_status().json()["service"]
    print(f"deploying {image}")
    print(service["serviceDetails"]["url"])


if __name__ == "__main__":
    main()
