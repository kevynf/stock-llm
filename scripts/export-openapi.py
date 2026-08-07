from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the StockLLM OpenAPI schema.")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    os.environ["STOCKLLM_DATA_DIR"] = str(project_root / ".tmp" / "openapi-data")
    sys.path.insert(0, str(project_root / "backend"))

    from stockllm.main import app

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
