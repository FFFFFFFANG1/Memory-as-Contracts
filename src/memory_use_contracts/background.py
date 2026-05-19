from __future__ import annotations

import argparse
import json

from memory_use_contracts.layer import MemoryContractLayer
from memory_use_contracts.source_refresh import refresh_instruction_sources


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["refresh-instructions"])
    parser.add_argument("--root", default=".")
    parser.add_argument("--adapter", default="all")
    parser.add_argument("--workspace", default=None)
    args = parser.parse_args()

    if args.command == "refresh-instructions":
        layer = MemoryContractLayer.from_env()
        results = refresh_instruction_sources(
            layer=layer,
            root=args.root,
            adapter=args.adapter,
            workspace=args.workspace,
        )
        print(
            json.dumps(
                [
                    {
                        "path": str(result.path),
                        "adapter": result.adapter,
                        "status": result.status,
                        "contract_count": len(result.contracts),
                    }
                    for result in results
                ]
            )
        )


if __name__ == "__main__":
    main()
