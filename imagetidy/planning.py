from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple


FALLBACK_PROJECT_NAME = "Unsorted"
FALLBACK_TIME_RANGE_LABEL = "unknown"
FALLBACK_CATEGORY = "other"


@dataclass(frozen=True)
class TimeRange:
    label: str
    start: date
    end: date


@dataclass(frozen=True)
class ProjectDefinition:
    canonical_name: str
    alias_tokens: Tuple[str, ...]
    time_ranges: Tuple[TimeRange, ...]


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"Invalid date string: {value}") from exc


def normalize_alias(alias: str) -> Optional[str]:
    token = alias.strip().lower()
    if not token:
        return None
    return token


def normalize_extension(ext: str) -> str:
    normalized = ext.strip().lower()
    if not normalized.startswith("."):
        normalized = "." + normalized
    return normalized


def build_projects(projects_data: Sequence[Mapping[str, Any]]) -> List[ProjectDefinition]:
    parsed: List[ProjectDefinition] = []
    for entry in projects_data:
        canonical = entry.get("canonical_name", "").strip()
        if not canonical:
            raise KeyError("Each project entry must have a canonical_name")
        alias_values = entry.get("aliases") or []
        token_set: Set[str] = set()
        for alias in alias_values:
            normalized = normalize_alias(alias)
            if normalized:
                token_set.add(normalized)
        canonical_token = normalize_alias(canonical)
        if canonical_token:
            token_set.add(canonical_token)
        time_range_entries = entry.get("time_ranges") or []
        ranges: List[TimeRange] = []
        for tr in time_range_entries:
            start_str = tr.get("from")
            end_str = tr.get("to")
            if not start_str or not end_str:
                raise KeyError("Each time range must include 'from' and 'to'")
            ranges.append(TimeRange(tr["label"], parse_date(start_str), parse_date(end_str)))
        parsed.append(ProjectDefinition(canonical, tuple(sorted(token_set)), tuple(ranges)))
    return parsed  # type: ignore[return-value]


def build_categories(raw: Mapping[str, Iterable[str]]) -> Dict[str, Set[str]]:
    result: Dict[str, Set[str]] = {}
    for category, extensions in raw.items():
        normalized = {normalize_extension(ext) for ext in extensions}
        result[str(category)] = normalized
    return result


def match_project(folder_chain: str, projects: Sequence[ProjectDefinition]) -> Optional[ProjectDefinition]:
    normalized_chain = folder_chain.strip().lower()
    for project in projects:
        for token in project.alias_tokens:
            if token and token in normalized_chain:
                return project
    return None


def find_time_range(modified_date: date, project: ProjectDefinition) -> Optional[TimeRange]:
    for candidate in project.time_ranges:
        if candidate.start <= modified_date <= candidate.end:
            return candidate
    return None


def categorize_extension(extension: str, categories: Mapping[str, Set[str]]) -> str:
    ext = normalize_extension(extension)
    for category, ext_set in categories.items():
        if ext in ext_set:
            return category
    return FALLBACK_CATEGORY


def ensure_json(text: str) -> Any:
    text = text.strip()
    if not text:
        raise ValueError("Empty response cannot be parsed")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError as exc:
                logging.error("Failed to parse JSON chunk from AI response")
                raise exc
        raise
