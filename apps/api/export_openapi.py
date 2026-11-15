"""Write openapi.json for the web client generator."""

import json

from agent.config import ROOT
from apps.api.main import app

if __name__ == "__main__":
    path = ROOT / "apps" / "api" / "openapi.json"
    path.write_text(json.dumps(app.openapi(), indent=2) + "\n")
    print(f"wrote {path.relative_to(ROOT)}")
