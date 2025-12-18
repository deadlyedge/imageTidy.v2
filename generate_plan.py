from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import shutil
from collections import Counter
from datetime import datetime, UTC, date
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

import settings
from imagetidy.planning import (
    FALLBACK_PROJECT_NAME,
    FALLBACK_TIME_RANGE_LABEL,
    ProjectDefinition,
    TimeRange,
    build_categories,
    build_projects,
    categorize_extension,
    derive_time_ranges,
    ensure_json,
    find_time_range,
    match_project,
    parse_date,
)
from openai import OpenAI

load_dotenv()

DEFAULT_CATEGORIES = {
    "cad": [".dwg", ".dxf", ".cad"],
    "photos": [".jpg", ".jpeg", ".png", ".tif", ".bmp"],
    "docs": [".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".pdf"],
    "other": [],
}
TARGET_PATTERN = "<time-range>-<project-name>/<category>"


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


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Configuration file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def call_ai_for_config(
    tag_list: list[dict[str, Any]],
    overview: dict[str, Any],
    temperature: float,
    max_tokens: int,
) -> dict[str, Any]:
    api_key = os.getenv("OPENROUTER_API_KEY")
    openai_client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY must be set to contact the configured LLM")

    payload = settings.AI_PROMPT.strip()
    payload += "\n\nFolder overview (JSON):\n"
    payload += json.dumps(overview, ensure_ascii=False, indent=2)
    payload += "\n\nTag list (JSON):\n"
    payload += json.dumps(tag_list, ensure_ascii=False, indent=2)

    response = openai_client.chat.completions.create(
        model=settings.MODEL_NAME,
        messages=[{"role": "user", "content": payload}],
        temperature=temperature,
        # max_tokens=max_tokens,
    )
    content = response.choices[0].message.content

    if not content:
        raise SystemExit("AI did not return any content")

    return ensure_json(content)


def derive_project_date_map(
    metadata: list[dict[str, Any]], projects: list["ProjectDefinition"]
) -> dict[str, list[date]]:
    date_map: dict[str, list[date]] = {
        project.canonical_name: [] for project in projects
    }
    for record in metadata:
        candidate = match_project(record.get("folder_chain", ""), projects)
        record["_matched_project"] = candidate
        parsed_date = record.get("_parsed_date")
        if not parsed_date:
            parsed_date = parse_date(record["modified_time"])
            record["_parsed_date"] = parsed_date
        if candidate:
            date_map[candidate.canonical_name].append(parsed_date)
    return date_map


def derive_project_time_ranges(
    project_dates: dict[str, list[date]],
) -> dict[str, list[TimeRange]]:
    ranges: dict[str, list[TimeRange]] = {}
    for canonical, dates in project_dates.items():
        if dates:
            ranges[canonical] = derive_time_ranges(sorted(dates))
        else:
            ranges[canonical] = []
    return ranges


def derive_target_filename(folder_chain: str, original_name: str) -> str:
    parts = [
        segment.strip() for segment in folder_chain.split(" / ") if segment.strip()
    ]
    if not parts:
        return original_name
    return "-".join(parts + [original_name])


def build_plan_entries(
    metadata: list[dict[str, Any]],
    config: dict[str, Any],
    target_root: Path,
    project_time_ranges: dict[str, list[TimeRange]],
) -> tuple[list[dict[str, str]], list[str]]:
    if (
        "projects" not in config
        or "categories" not in config
        or "target_pattern" not in config
    ):
        raise KeyError(
            "Plan configuration missing required keys (projects, categories, target_pattern)"
        )

    projects = build_projects(config["projects"])
    categories = build_categories(config["categories"])
    pattern = config["target_pattern"]
    seen_targets: set[str] = set()
    entries: list[dict[str, str]] = []
    warnings: list[str] = []

    for record in metadata:
        folder_chain = record.get("folder_chain", "")
        candidate = record.get("_matched_project") or match_project(
            folder_chain, projects
        )
        canonical = candidate.canonical_name if candidate else FALLBACK_PROJECT_NAME
        if not candidate:
            warnings.append(f"Could not match project for {record['full_path']}")
        modified_date = record.get("_parsed_date")
        if not modified_date:
            modified_date = parse_date(record["modified_time"])
        assigned_range = FALLBACK_TIME_RANGE_LABEL
        if candidate:
            overrides = project_time_ranges.get(canonical)
            time_range = find_time_range(modified_date, candidate, overrides)
            if time_range:
                assigned_range = time_range.label
            else:
                warnings.append(
                    f"{record['full_path']} falls outside derived time ranges for {canonical}"
                )
        category = categorize_extension(record.get("file_ext", ""), categories)

        target_pattern = pattern.replace("<time-range>", assigned_range)
        target_pattern = target_pattern.replace("<project-name>", canonical)
        target_pattern = target_pattern.replace("<category>", category)

        target_dir = target_root / target_pattern
        base_name = Path(record["full_path"]).name
        tagged_name = derive_target_filename(folder_chain, base_name)
        new_path = target_dir / tagged_name
        note_parts = []
        if not candidate:
            note_parts.append("project fallback")
        if assigned_range == FALLBACK_TIME_RANGE_LABEL:
            note_parts.append("time range fallback")
        if str(new_path) in seen_targets:
            note_parts.append("target collision")
        seen_targets.add(str(new_path))

        entries.append(
            {
                "old_path": record["full_path"],
                "new_path": str(new_path),
                "project": canonical,
                "time_range": assigned_range,
                "category": category,
                "modified_time": record.get("modified_time", ""),
                "notes": "; ".join(note_parts) or "ok",
            }
        )
    return entries, warnings


def write_csv(entries: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "old_path",
        "new_path",
        "project",
        "time_range",
        "category",
        "modified_time",
        "notes",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for entry in entries:
            writer.writerow(entry)


def summarize(entries: list[dict[str, str]]) -> dict[str, Any]:
    projects = Counter(entry["project"] for entry in entries)
    categories = Counter(entry["category"] for entry in entries)
    time_ranges = Counter(entry["time_range"] for entry in entries)
    return {
        "entry_count": len(entries),
        "unique_projects": len(projects),
        "unique_categories": len(categories),
        "time_ranges": dict(time_ranges),
        "category_distribution": dict(categories),
        "project_distribution": dict(projects),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate move plan based on AI output."
    )
    parser.add_argument(
        "--metadata-file",
        type=Path,
        default=Path("output/metadata.json"),
        help="Collected metadata to analyze.",
    )
    parser.add_argument(
        "--folder-summary",
        type=Path,
        default=Path("output/folder_summary.json"),
        help="Folder tree summary previously generated.",
    )
    parser.add_argument(
        "--tag-summary",
        type=Path,
        default=Path("output/tag_summary.json"),
        help="Deduplicated folder tags for record keeping.",
    )
    parser.add_argument(
        "--tag-input",
        type=Path,
        default=Path("output/tag_input.json"),
        help="Tag list (just keywords) that is fed to the AI.",
    )
    parser.add_argument(
        "--overview",
        type=Path,
        default=Path("output/folder_overview.json"),
        help="Folder overview used to explain folder weights to the AI.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Directory where plans and logs will be stored.",
    )
    parser.add_argument(
        "--plan-path",
        type=Path,
        default=Path("output/move_plan.csv"),
        help="CSV that captures the reviewed move plan.",
    )
    parser.add_argument(
        "--config-output",
        type=Path,
        default=Path("output/plan_config.json"),
        help="Location to write the parsed plan configuration.",
    )
    parser.add_argument(
        "--target-root",
        type=Path,
        default=Path(settings.SOURCE_FOLDER).parent
        / f"{Path(settings.SOURCE_FOLDER).name}-organized",
        help="Root directory that will house the tidied structure.",
    )
    parser.add_argument(
        "--manual-config",
        type=Path,
        help="Skip LLM call and use an existing plan configuration.",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Do not call the LLM; requires --manual-config.",
    )
    parser.add_argument(
        "--ai-temperature",
        type=float,
        default=0.1,
        help="Temperature for the LLM call.",
    )
    parser.add_argument(
        "--ai-max-tokens", type=int, default=8000, help="Max tokens for the LLM call."
    )
    parser.add_argument(
        "--cover-missing",
        action="store_true",
        help="If some tags remain without canonical mapping, request a second pass for them.",
    )
    args = parser.parse_args()

    if args.no_ai and not args.manual_config:
        raise SystemExit("--no-ai requires --manual-config to be provided")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.output_dir / "generate_plan.log"
    setup_logging(log_path)

    if not args.metadata_file.exists():
        raise SystemExit(f"Metadata file not found: {args.metadata_file}")
    metadata = json.loads(args.metadata_file.read_text(encoding="utf-8"))
    if not isinstance(metadata, list):
        raise SystemExit("Metadata file must contain a JSON array")

    if not args.folder_summary.exists():
        raise SystemExit(f"Folder summary missing: {args.folder_summary}")
    folder_summary = json.loads(args.folder_summary.read_text(encoding="utf-8"))
    if not args.tag_summary.exists():
        raise SystemExit(f"Tag summary missing: {args.tag_summary}")
    tag_summary = json.loads(args.tag_summary.read_text(encoding="utf-8"))
    if not args.tag_input.exists():
        raise SystemExit(f"Tag input missing: {args.tag_input}")
    tag_input = json.loads(args.tag_input.read_text(encoding="utf-8"))
    if not args.overview.exists():
        raise SystemExit(f"Folder overview missing: {args.overview}")
    overview = json.loads(args.overview.read_text(encoding="utf-8"))

    if args.manual_config:
        config = load_json(args.manual_config)
    elif args.no_ai:
        raise SystemExit("Either provide --manual-config or allow AI lookup")
    else:
        raw_config = call_ai_for_config(
            tag_input.get("tags", []),
            overview,
            args.ai_temperature,
            args.ai_max_tokens,
        )
        project_entries = raw_config.get("projects")
        if not isinstance(project_entries, list) or not project_entries:
            raise SystemExit("AI output must include a non-empty 'projects' array")
        config = {
            "projects": project_entries,
            "categories": DEFAULT_CATEGORIES,
            "target_pattern": TARGET_PATTERN,
        }

        if args.cover_missing:
            submitted_tags = set(tag_input.get("tags", []))
            mapped_tags: set[str] = set()
            for project in config["projects"]:
                canonical = project["canonical_name"]
                mapped_tags.add(canonical)
                mapped_tags.update(project.get("aliases", []))

            missing = sorted(submitted_tags - mapped_tags)
            if missing:
                logging.info("Asking for coverage for %d missing tags", len(missing))
                extra = call_ai_for_config(
                    missing,
                    overview,
                    args.ai_temperature,
                    args.ai_max_tokens,
                )
                additions = extra.get("projects", [])
                if isinstance(additions, list):
                    existing = {p["canonical_name"]: p for p in config["projects"]}
                    for project in additions:
                        canonical = project["canonical_name"]
                        if canonical in existing:
                            aliases = existing[canonical].setdefault("aliases", [])
                            existing_set = set(aliases)
                            for alias in project.get("aliases", []):
                                if alias not in existing_set:
                                    aliases.append(alias)
                                    existing_set.add(alias)
                        else:
                            config["projects"].append(project)

    projects = build_projects(config["projects"])
    project_dates = derive_project_date_map(metadata, projects)
    project_time_ranges = derive_project_time_ranges(project_dates)

    for project_entry in config["projects"]:
        canonical = project_entry["canonical_name"]
        derived_ranges = project_time_ranges.get(canonical, [])
        project_entry["time_ranges"] = [
            {
                "label": timerange.label,
                "from": timerange.start.isoformat(),
                "to": timerange.end.isoformat(),
            }
            for timerange in derived_ranges
        ]

    config_output = args.config_output
    config_output.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logging.info("Plan configuration saved to %s", config_output)

    entries, warnings = build_plan_entries(
        metadata, config, args.target_root, project_time_ranges
    )
    write_csv(entries, args.plan_path)
    args.target_root.mkdir(parents=True, exist_ok=True)
    plan_copy = args.target_root / args.plan_path.name
    shutil.copy(args.plan_path, plan_copy)
    if not plan_copy.exists():
        raise SystemExit(f"Failed to copy move plan to target root at {plan_copy}")
    logging.info("Plan copied to %s", plan_copy)
    summary = summarize(entries)
    summary.update(
        {
            "target_root": str(args.target_root),
            "generated_at": datetime.now(UTC).isoformat(),
            "metadata_count": len(metadata),
            "folder_summary": str(args.folder_summary),
            "tag_summary": str(args.tag_summary),
            "tag_input": str(args.tag_input),
            "overview": overview,
            "overview_path": str(args.overview),
            "derived_time_ranges": {
                canonical: [tr.label for tr in ranges]
                for canonical, ranges in project_time_ranges.items()
            },
            "warnings": warnings,
        }
    )
    summary_path = args.output_dir / "plan_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    logging.info("Plan written to %s (%d entries)", args.plan_path, len(entries))
    logging.info("Summary written to %s", summary_path)
    for warning in warnings:
        logging.warning(warning)


if __name__ == "__main__":
    main()
