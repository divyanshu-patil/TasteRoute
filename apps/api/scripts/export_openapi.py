"""Write packages/contracts/openapi.json from the FastAPI app (API-01). Run: pnpm --filter api openapi"""

import json
from pathlib import Path

from stockist_api.main import app

OUT = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "openapi.json"

if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUT.relative_to(OUT.parents[2])}")
