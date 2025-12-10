from __future__ import annotations

import argparse
import csv
import logging
import shutil
from pathlib import Path


def setup_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def resolve_collision(destination: Path) -> Path:
    if not destination.exists():
        return destination
    parent = destination.parent
    stem = destination.stem
    suffix = destination.suffix
    counter = 1
    while True:
        candidate = parent / f"{stem}_dup{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute a reviewed move plan.")
    parser.add_argument("--plan-file", type=Path, default=Path("output/move_plan.csv"), help="Reviewed move plan CSV.")
    parser.add_argument("--output-dir", type=Path, default=Path("output"), help="Directory for execution logs.")
    parser.add_argument("--dry-run", action="store_true", help="Log moves without executing them.")
    args = parser.parse_args()

    log_path = args.output_dir / "execute_plan.log"
    setup_logging(log_path)

    if not args.plan_file.exists():
        raise SystemExit(f"Plan file not found: {args.plan_file}")

    moved = 0
    skipped = 0
    missing = 0
    collisions = 0

    with args.plan_file.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            source = Path(row["old_path"])
            destination = Path(row["new_path"])
            if not source.exists():
                logging.warning("Source deleted or missing: %s", source)
                missing += 1
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)

            final_target = destination
            if destination.exists():
                final_target = resolve_collision(destination)
                collisions += 1
                logging.warning("Target exists, using %s", final_target)

            if args.dry_run:
                logging.info("Dry run: %s -> %s", source, final_target)
                skipped += 1
                continue

            shutil.move(str(source), str(final_target))
            logging.info("Moved %s -> %s", source, final_target)
            moved += 1

    logging.info(
        "Execution summary: moved=%d skipped=%d missing=%d collisions=%d",
        moved,
        skipped,
        missing,
        collisions,
    )


if __name__ == "__main__":
    main()
