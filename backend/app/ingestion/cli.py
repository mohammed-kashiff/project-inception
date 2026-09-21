import sys

from app.ingestion.pipeline import run_source
from app.ingestion.sources import SOURCE_REGISTRY


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {*SOURCE_REGISTRY.keys(), "all"}:
        sources = ", ".join(SOURCE_REGISTRY.keys())
        print(f"Usage: python -m app.ingestion.cli <{sources}|all>")
        sys.exit(1)

    targets = SOURCE_REGISTRY.keys() if sys.argv[1] == "all" else [sys.argv[1]]

    for source_name in targets:
        run = run_source(source_name)
        print(
            f"[{source_name}] status={run.status} record_count={run.record_count} "
            f"error={run.error_detail}"
        )


if __name__ == "__main__":
    main()
