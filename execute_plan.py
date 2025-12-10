from __future__ import annotations

import argparse
import csv
import logging
import shutil
from pathlib import Path

import settings


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
    default_target = Path(settings.SOURCE_FOLDER).parent / f"{Path(settings.SOURCE_FOLDER).name}-organized"
    parser = argparse.ArgumentParser(description="Execute a reviewed move plan.")
    parser.add_argument(
        "--plan-file",
        type=Path,
        default=Path("output/move_plan.csv"),
        help="Reviewed move plan CSV.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Directory for execution logs.",
    )
    parser.add_argument(
        "--target-root",
        type=Path,
        default=default_target,
        help="Root directory for the tidy structure (used for revert validations).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Log moves without executing them.")
    parser.add_argument("--revert", action="store_true", help="Restore files back to their original paths.")
    args = parser.parse_args()

    log_path = args.output_dir / "execute_plan.log"
    setup_logging(log_path)

    plan_path_to_use = args.plan_file
    if args.revert:
        target_plan = args.target_root / args.plan_file.name
        logging.info("Revert mode: derived target root %s", args.target_root)
        if not target_plan.exists():
            raise SystemExit(
                f"Revert requires {target_plan} inside the target root; aborting."
            )
        plan_path_to_use = target_plan

    if not plan_path_to_use.exists():
        raise SystemExit(f"Plan file not found: {plan_path_to_use}")

    moved = 0
    skipped = 0
    missing = 0
    collisions = 0

    with plan_path_to_use.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            source_key = "new_path" if args.revert else "old_path"
            destination_key = "old_path" if args.revert else "new_path"
            source = Path(row[source_key])
            destination = Path(row[destination_key])
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
                mode_label = "revert" if args.revert else "apply"
                logging.info("Dry run (%s): %s -> %s", mode_label, source, final_target)
                skipped += 1
                continue

            shutil.move(str(source), str(final_target))
            action = "Reverted" if args.revert else "Moved"
            logging.info("%s %s -> %s", action, source, final_target)
            moved += 1

    mode = "revert" if args.revert else "apply"
    logging.info(
        "Execution summary (%s): moved=%d skipped=%d missing=%d collisions=%d",
        mode,
        moved,
        skipped,
        missing,
        collisions,
    )


if __name__ == "__main__":
    main()
