"""Deterministic adapter from sealed analysis bundles to browser episodes.

This module never scans staging and never guesses fields from column names. Every
mapping is driven by the published bundle's record_contract. The original source
candidate label remains provenance; it is not silently promoted into a biological
post-hoc label.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

HERE = Path(__file__).resolve().parent.parent
REPO_ROOT = HERE.parent
DEFAULT_EXCHANGE_ROOT = REPO_ROOT / "analysis_exchange"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analysis_exchange.python.reader import (  # noqa: E402
    PublishedBundle,
    iter_published_bundles,
)
from . import validation  # noqa: E402


class ExchangeImportError(RuntimeError):
    """Raised when a published candidate cannot be mapped without guessing."""


LEVEL_MAP = {
    "individual": "per_animal",
    "pair": "pair",
    "group": "group",
    "environment": "environment",
}


def iter_import_ready_episode_bundles(
    exchange_root: str | Path = DEFAULT_EXCHANGE_ROOT,
    *,
    verify: bool = True,
) -> Iterator[PublishedBundle]:
    for bundle in iter_published_bundles(
        exchange_root,
        destination="episode_browser",
        object_type="episode_candidate",
        verify=verify,
    ):
        handoff = bundle.manifest.get("handoff") or {}
        if handoff.get("import_ready") is True and not handoff.get("blockers"):
            yield bundle


def _primary_payload(bundle: PublishedBundle) -> tuple[dict[str, Any], Path]:
    matches = [
        payload for payload in bundle.manifest.get("payloads", [])
        if payload.get("role") == "primary_records" and "path" in payload
    ]
    if len(matches) != 1:
        raise ExchangeImportError(
            f"Bundle {bundle.bundle_id} must have exactly one local primary_records payload"
        )
    paths = bundle.local_payloads(role="primary_records")
    if len(paths) != 1:
        raise ExchangeImportError(f"Bundle {bundle.bundle_id} primary payload is unavailable")
    return matches[0], paths[0]


def _decode_csv_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return None
    if stripped[0] in "[{\"" or stripped in {"true", "false", "null"}:
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return value
    return value


def load_source_records(bundle: PublishedBundle) -> list[dict[str, Any]]:
    payload, path = _primary_payload(bundle)
    fmt = str(payload.get("format") or "").lower()
    if fmt == "jsonl":
        rows = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise ExchangeImportError(f"Non-object JSONL row in {path}")
                    rows.append(value)
        return rows
    if fmt == "json":
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            value = value.get("records")
        if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
            raise ExchangeImportError(f"JSON primary payload must contain record objects: {path}")
        return value
    if fmt == "csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [
                {key: _decode_csv_value(value) for key, value in row.items()}
                for row in csv.DictReader(handle)
            ]
    if fmt == "parquet":
        return pd.read_parquet(path).to_dict(orient="records")
    raise ExchangeImportError(f"Unsupported primary payload format {fmt!r}")


def _contract_field(spec: Any, label: str) -> str:
    if isinstance(spec, str) and spec:
        return spec
    if isinstance(spec, dict) and isinstance(spec.get("field"), str) and spec["field"]:
        return spec["field"]
    raise ExchangeImportError(f"Missing deterministic field mapping for {label}")


def _require(record: dict[str, Any], field_name: str, label: str) -> Any:
    if field_name not in record or record[field_name] is None:
        raise ExchangeImportError(f"Record lacks required {label} field {field_name!r}")
    return record[field_name]


def map_bundle_to_browser_episodes(
    bundle: PublishedBundle,
    *,
    registry_path: str | Path = validation.REGISTRY_PATH,
    schema_path: str | Path = validation.SCHEMA_PATH,
) -> list[dict[str, Any]]:
    """Map one verified import-ready interval bundle into browser episode dicts."""
    manifest = bundle.manifest
    result = manifest.get("result") or {}
    handoff = manifest.get("handoff") or {}
    if result.get("object_type") != "episode_candidate":
        raise ExchangeImportError("Only episode_candidate bundles can map to browser episodes")
    if handoff.get("recommended_destination") != "episode_browser":
        raise ExchangeImportError("Bundle is not routed to episode_browser")
    if handoff.get("import_ready") is not True or handoff.get("blockers"):
        raise ExchangeImportError("Bundle is not import-ready")
    if result.get("temporal_semantics") not in {"interval", "bounded_window"}:
        raise ExchangeImportError(
            "Browser adapter v0 requires interval or bounded_window semantics; point conversion must be explicit"
        )

    registry = validation.load_registry(registry_path)
    model_id = (result.get("detector") or {}).get("model_id")
    if model_id not in (registry.get("state_models") or {}):
        raise ExchangeImportError(
            f"State model {model_id!r} is not registered; deterministic import is blocked"
        )
    subject_level = (result.get("subject_semantics") or {}).get("level")
    if subject_level not in LEVEL_MAP:
        raise ExchangeImportError(f"Subject semantics {subject_level!r} cannot map to browser level")

    contract = manifest.get("record_contract") or {}
    time_fields = contract.get("time_fields") or {}
    subject_fields = contract.get("subject_fields") or {}
    primary_key_field = _contract_field(contract.get("primary_key"), "primary key")
    start_field = _contract_field(time_fields.get("start"), "start time")
    end_field = _contract_field(time_fields.get("end"), "end time")
    subjects_field = _contract_field(subject_fields.get("subjects"), "subjects")
    roles_spec = subject_fields.get("ordered_roles")
    roles_field = _contract_field(roles_spec, "ordered roles") if roles_spec else None
    candidate_field = _contract_field(contract.get("candidate_label_field"), "candidate label")
    run_field = _contract_field(contract.get("analysis_run_id_field"), "analysis run ID")
    qc_fields = contract.get("qc_fields") or []
    evidence_fields = contract.get("evidence_fields") or []
    state_vector_fields = contract.get("state_vector_fields") or []
    score_fields = contract.get("score_fields") or {}

    episodes: list[dict[str, Any]] = []
    for record in load_source_records(bundle):
        source_id = str(_require(record, primary_key_field, "primary key"))
        start = int(_require(record, start_field, "start time"))
        end = int(_require(record, end_field, "end time"))
        if end <= start:
            raise ExchangeImportError(f"Source record {source_id!r} has a non-positive interval")
        subjects = _require(record, subjects_field, "subjects")
        if not isinstance(subjects, list) or not subjects:
            raise ExchangeImportError(f"Source record {source_id!r} subjects are not a non-empty list")
        candidate_label = str(_require(record, candidate_field, "candidate label"))
        if candidate_label != str(result.get("candidate_label")):
            raise ExchangeImportError(f"Source record {source_id!r} candidate label disagrees with manifest")
        analysis_run_id = str(_require(record, run_field, "analysis run ID"))
        if analysis_run_id != str((manifest.get("analysis") or {}).get("run_id")):
            raise ExchangeImportError(f"Source record {source_id!r} run ID disagrees with manifest")

        roles = _require(record, roles_field, "ordered roles") if roles_field else {}
        if roles and not isinstance(roles, dict):
            raise ExchangeImportError(f"Source record {source_id!r} roles are not an object")

        qc_flags: list[str] = []
        qc_values: dict[str, Any] = {}
        for field_name in qc_fields:
            value = _require(record, field_name, "QC")
            qc_values[field_name] = value
            if isinstance(value, list):
                qc_flags.extend(str(item) for item in value)
        evidence = {
            field_name: _require(record, field_name, "evidence")
            for field_name in evidence_fields
        }
        state_vector = {
            field_name: record[field_name]
            for field_name in state_vector_fields
            if field_name in record and record[field_name] is not None
        }
        source_scores = {
            field_name: record[field_name]
            for field_name in score_fields
            if field_name in record and record[field_name] is not None
        }

        episodes.append({
            "episode_id": f"exchange--{bundle.bundle_id}--{source_id}",
            "schema_version": 1,
            "state_model_id": model_id,
            "level": LEVEL_MAP[subject_level],
            "subject_ids": [str(subject) for subject in subjects],
            "subject_confidence": None,
            "t_start": start,
            "t_end": end,
            "state_vector": state_vector,
            "state_before": None,
            "state_after": None,
            "zones": {},
            "source_streams": list(result.get("source_streams") or []),
            "boundary_confidence": None,
            "identity_confidence": None,
            "tracking_quality": None,
            "labels": [],
            "lens_scores": {},
            "environment_context": {},
            "linked_assets": {
                "analysis_exchange": {
                    "bundle_id": bundle.bundle_id,
                    "source_record_id": source_id,
                    "original_candidate_label": candidate_label,
                    "allowed_claim": result.get("allowed_claim"),
                    "forbidden_promotions": list(result.get("forbidden_promotions") or []),
                    "analysis": dict(manifest.get("analysis") or {}),
                    "detector": dict(result.get("detector") or {}),
                    "subject_roles": roles,
                    "qc": qc_values,
                    "evidence": evidence,
                    "source_scores": source_scores,
                }
            },
            "qc_flags": sorted(set(qc_flags)),
            "notes": "",
            "expert_annotations": [],
        })

    report = validation.validate_all(
        episodes,
        schema_path=schema_path,
        registry_path=registry_path,
    )
    if not report.ok:
        raise ExchangeImportError("Mapped episodes fail browser validation: " + "; ".join(report.errors))
    return episodes


def load_published_exchange_episodes(
    exchange_root: str | Path = DEFAULT_EXCHANGE_ROOT,
) -> list[dict[str, Any]]:
    """Read and map every verified import-ready browser bundle, detecting collisions."""
    episodes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for bundle in iter_import_ready_episode_bundles(exchange_root, verify=True):
        for episode in map_bundle_to_browser_episodes(bundle):
            if episode["episode_id"] in seen:
                raise ExchangeImportError(f"Duplicate mapped episode ID {episode['episode_id']!r}")
            seen.add(episode["episode_id"])
            episodes.append(episode)
    return episodes
