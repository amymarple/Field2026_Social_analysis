"""Deterministic validation, publication, and verification for result bundles."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

SCHEMA_VERSION = "0.1.0"
MANIFEST_NAME = "manifest.json"
SEAL_NAME = "BUNDLE.SEALED"

OBJECT_DESTINATIONS = {
    "episode_candidate": "episode_browser",
    "aggregate_metric": "observation_compiler",
    "observation_candidate": "observation_registry",
    "model_evaluation": "evaluation_registry",
    "artifact_only": "artifact_store",
}

TEMPORAL_SEMANTICS = {"point", "interval", "bounded_window", "aggregate", "none"}
SUBJECT_LEVELS = {
    "individual", "pair", "group", "environment", "cohort", "none",
}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SUPPORTED_RECORD_FORMATS = {"jsonl", "json", "csv", "parquet"}
REQUIRED_TOP_LEVEL = {
    "schema_version", "bundle_id", "status", "published_at_utc",
    "supersedes_bundle_id", "producer", "analysis", "result",
    "record_contract", "payloads", "provenance", "handoff",
}


class BridgeError(RuntimeError):
    """Base error for deterministic bridge operations."""


class BundleVerificationError(BridgeError):
    """Raised when a published bundle is incomplete or has changed after sealing."""


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    message: str
    path: str = ""


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "warning"]

    @property
    def valid(self) -> bool:
        return not self.errors

    def add(self, severity: str, code: str, message: str, path: str = "") -> None:
        self.issues.append(ValidationIssue(severity, code, message, path))

    def error(self, code: str, message: str, path: str = "") -> None:
        self.add("error", code, message, path)

    def warning(self, code: str, message: str, path: str = "") -> None:
        self.add("warning", code, message, path)

    def format_lines(self) -> list[str]:
        if not self.issues:
            return ["VALID - no validation issues"]
        return [
            f"{issue.severity.upper()} {issue.code}"
            f"{f' [{issue.path}]' if issue.path else ''}: {issue.message}"
            for issue in self.issues
        ]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(_canonical_json_bytes(value))
    temporary.replace(path)


def load_manifest(bundle_dir: str | Path) -> dict[str, Any]:
    path = Path(bundle_dir) / MANIFEST_NAME
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BridgeError(f"Missing {MANIFEST_NAME}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BridgeError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BridgeError(f"Manifest root must be an object: {path}")
    return value


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_safe_id(value: Any) -> bool:
    return isinstance(value, str) and bool(SAFE_ID_RE.fullmatch(value)) and value not in {".", ".."}


def safe_relative_path(value: Any) -> PurePosixPath:
    """Return a normalized manifest path or raise for traversal/absolute paths."""
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise BridgeError("Payload path must be a non-empty POSIX relative path")
    raw_parts = value.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts) or re.match(r"^[A-Za-z]:", value):
        raise BridgeError(f"Unsafe payload path: {value!r}")
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise BridgeError(f"Unsafe payload path: {value!r}")
    return candidate


def resolve_local_payload(bundle_dir: str | Path, value: Any) -> Path:
    relative = safe_relative_path(value)
    base = Path(bundle_dir).resolve()
    candidate = base.joinpath(*relative.parts).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise BridgeError(f"Payload escapes bundle directory: {value!r}") from exc
    if candidate.is_symlink():
        raise BridgeError(f"Payload may not be a symlink: {value!r}")
    return candidate


def _is_utc_iso(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(parsed)


def _read_records(path: Path, fmt: str) -> list[dict[str, Any]] | None:
    if fmt == "jsonl":
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise BridgeError(f"JSONL row {line_number} is not an object")
                rows.append(value)
        return rows
    if fmt == "json":
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict) and isinstance(value.get("records"), list):
            value = value["records"]
        if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
            raise BridgeError("JSON primary records must be a list of objects or {'records': [...]}")
        return value
    if fmt == "csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    if fmt == "parquet":
        return None
    raise BridgeError(f"Unsupported primary record format: {fmt}")


def _field_name(spec: Any) -> str | None:
    if isinstance(spec, str):
        return spec or None
    if isinstance(spec, dict) and isinstance(spec.get("field"), str):
        return spec["field"] or None
    return None


def _time_representation(spec: Any) -> str | None:
    return spec.get("representation") if isinstance(spec, dict) else None


def _validate_time_value(value: Any, representation: str | None) -> bool:
    if representation == "unix_ms_utc":
        try:
            int(value)
        except (TypeError, ValueError):
            return False
        return True
    if representation == "iso8601_utc":
        return _is_utc_iso(value)
    return False


def _validate_episode_records(
    bundle_dir: Path,
    manifest: dict[str, Any],
    primary_payload: dict[str, Any],
    report: ValidationReport,
) -> None:
    contract = manifest.get("record_contract") or {}
    result = manifest.get("result") or {}
    analysis = manifest.get("analysis") or {}
    temporal = result.get("temporal_semantics")
    time_fields = contract.get("time_fields") or {}
    subject_fields = contract.get("subject_fields") or {}

    path_value = primary_payload.get("path")
    fmt = str(primary_payload.get("format") or "").lower()
    if fmt not in SUPPORTED_RECORD_FORMATS:
        report.error("episode_payload_format", f"Unsupported episode primary format: {fmt}", "payloads")
        return
    try:
        payload_path = resolve_local_payload(bundle_dir, path_value)
        rows = _read_records(payload_path, fmt)
    except (BridgeError, OSError, json.JSONDecodeError, csv.Error) as exc:
        report.error("primary_payload_read", str(exc), str(path_value or "payloads"))
        return
    if rows is None:
        message = (
            "Parquet row values are not inspected by the standard-library validator; "
            "use JSONL/JSON/CSV as the primary records payload and Parquet as a secondary payload"
        )
        if (manifest.get("handoff") or {}).get("import_ready") is True:
            report.error("uninspected_primary_payload", message, str(path_value))
        else:
            report.warning("parquet_rows_not_inspected", message, str(path_value))
        return
    if not rows:
        report.error("empty_primary_payload", "Episode primary payload contains no records", str(path_value))
        return

    required_fields = {
        "primary key": contract.get("primary_key"),
        "subjects": _field_name(subject_fields.get("subjects")),
        "candidate label": contract.get("candidate_label_field"),
        "analysis run ID": contract.get("analysis_run_id_field"),
    }
    if temporal == "point":
        required_fields["point time"] = _field_name(time_fields.get("point"))
    else:
        required_fields["start time"] = _field_name(time_fields.get("start"))
        required_fields["end time"] = _field_name(time_fields.get("end"))
    for qc_field in contract.get("qc_fields") or []:
        required_fields[f"QC field {qc_field}"] = qc_field
    for evidence_field in contract.get("evidence_fields") or []:
        required_fields[f"evidence field {evidence_field}"] = evidence_field

    roles_field = _field_name(subject_fields.get("ordered_roles"))
    if roles_field:
        required_fields["ordered roles"] = roles_field

    seen_keys: set[str] = set()
    for row_index, row in enumerate(rows, start=1):
        row_path = f"{path_value}:row:{row_index}"
        for label, field_name in required_fields.items():
            if not isinstance(field_name, str) or field_name not in row:
                report.error("missing_record_field", f"Missing {label} field {field_name!r}", row_path)
        primary_key = contract.get("primary_key")
        if isinstance(primary_key, str) and primary_key in row:
            key = str(row[primary_key])
            if not key:
                report.error("empty_primary_key", "Episode primary key is empty", row_path)
            elif key in seen_keys:
                report.error("duplicate_primary_key", f"Duplicate episode primary key {key!r}", row_path)
            seen_keys.add(key)

        subjects_field = _field_name(subject_fields.get("subjects"))
        subjects = row.get(subjects_field) if subjects_field else None
        if isinstance(subjects, str) and fmt == "csv":
            try:
                subjects = json.loads(subjects)
            except json.JSONDecodeError:
                pass
        if not isinstance(subjects, list) or not subjects:
            report.error("invalid_subjects", "Episode subjects must be a non-empty list", row_path)

        run_field = contract.get("analysis_run_id_field")
        if isinstance(run_field, str) and row.get(run_field) != analysis.get("run_id"):
            report.error("run_id_mismatch", "Record analysis run ID does not match manifest", row_path)

        if temporal == "point":
            point_spec = time_fields.get("point")
            point_field = _field_name(point_spec)
            if point_field in row and not _validate_time_value(row[point_field], _time_representation(point_spec)):
                report.error("non_utc_time", "Point timestamp is not in the declared UTC representation", row_path)
        else:
            start_spec = time_fields.get("start")
            end_spec = time_fields.get("end")
            start_field = _field_name(start_spec)
            end_field = _field_name(end_spec)
            start_value = row.get(start_field) if start_field else None
            end_value = row.get(end_field) if end_field else None
            if not _validate_time_value(start_value, _time_representation(start_spec)):
                report.error("non_utc_start", "Start timestamp is not in the declared UTC representation", row_path)
            if not _validate_time_value(end_value, _time_representation(end_spec)):
                report.error("non_utc_end", "End timestamp is not in the declared UTC representation", row_path)
            start_representation = _time_representation(start_spec)
            end_representation = _time_representation(end_spec)
            try:
                if start_representation != end_representation:
                    ordered = False
                elif start_representation == "unix_ms_utc":
                    ordered = int(end_value) > int(start_value)
                elif start_representation == "iso8601_utc":
                    start_dt = datetime.fromisoformat(str(start_value).replace("Z", "+00:00"))
                    end_dt = datetime.fromisoformat(str(end_value).replace("Z", "+00:00"))
                    ordered = end_dt > start_dt
                else:
                    ordered = False
            except (TypeError, ValueError):
                ordered = False
            if not ordered:
                report.error("invalid_interval", "Episode end must be after start", row_path)

        if roles_field and roles_field in row:
            roles = row[roles_field]
            if not isinstance(roles, dict):
                report.error("invalid_roles", "Ordered subject roles must be an object", row_path)
            else:
                declared_roles = (result.get("subject_semantics") or {}).get("roles") or []
                if set(roles) != set(declared_roles):
                    report.error("role_mismatch", "Record role keys do not match declared roles", row_path)
                if isinstance(subjects, list) and any(value not in subjects for value in roles.values()):
                    report.error("role_subject_mismatch", "Role values must reference record subjects", row_path)
        candidate_field = contract.get("candidate_label_field")
        if isinstance(candidate_field, str) and candidate_field in row:
            if row[candidate_field] != result.get("candidate_label"):
                report.error("candidate_label_mismatch", "Record candidate label does not match manifest", row_path)


def validate_bundle(bundle_dir: str | Path) -> ValidationReport:
    """Validate one draft or published bundle without modifying it."""
    bundle_dir = Path(bundle_dir)
    report = ValidationReport()
    try:
        manifest = load_manifest(bundle_dir)
    except BridgeError as exc:
        report.error("manifest", str(exc), MANIFEST_NAME)
        return report

    for key in sorted(REQUIRED_TOP_LEVEL):
        if key not in manifest:
            report.error("manifest_field", f"Top-level field {key!r} is required", key)

    schema_version = manifest.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        report.error("schema_version", f"Expected schema_version {SCHEMA_VERSION!r}", "schema_version")

    bundle_id = manifest.get("bundle_id")
    if not _is_safe_id(bundle_id):
        report.error("bundle_id", "bundle_id is missing or filesystem-unsafe", "bundle_id")
    elif bundle_dir.name != bundle_id:
        report.error("bundle_directory", "Bundle directory name must equal bundle_id", "bundle_id")

    status = manifest.get("status")
    if status not in {"draft", "published"}:
        report.error("status", "status must be 'draft' or 'published'", "status")
    published_at = manifest.get("published_at_utc")
    if status == "published" and not _is_utc_iso(published_at):
        report.error("published_at", "Published bundle requires an ISO-8601 UTC timestamp", "published_at_utc")
    if status == "draft" and published_at is not None:
        report.error("draft_published_at", "Draft published_at_utc must be null", "published_at_utc")

    supersedes = manifest.get("supersedes_bundle_id")
    if supersedes is not None and not _is_safe_id(supersedes):
        report.error("supersedes_id", "supersedes_bundle_id is filesystem-unsafe", "supersedes_bundle_id")
    if supersedes == bundle_id and supersedes is not None:
        report.error("self_supersedes", "A bundle may not supersede itself", "supersedes_bundle_id")

    producer = manifest.get("producer")
    if not isinstance(producer, dict) or not producer.get("tool") or not producer.get("agent"):
        report.error("producer", "producer.tool and producer.agent are required", "producer")

    analysis = manifest.get("analysis")
    if not isinstance(analysis, dict):
        report.error("analysis", "analysis must be an object", "analysis")
        analysis = {}
    for key in (
        "analysis_id", "analysis_version", "run_id", "created_at_utc",
        "code_repository", "code_commit", "code_dirty",
    ):
        if key not in analysis:
            report.error("analysis_field", f"analysis.{key} is required", f"analysis.{key}")
    for key in ("analysis_id", "analysis_version", "run_id", "created_at_utc"):
        if not analysis.get(key):
            report.error("analysis_value", f"analysis.{key} may not be empty", f"analysis.{key}")
    if analysis.get("created_at_utc") and not _is_utc_iso(analysis.get("created_at_utc")):
        report.error("analysis_time", "analysis.created_at_utc must be ISO-8601 UTC", "analysis.created_at_utc")
    if str(analysis.get("analysis_version", "")).lower() in {"", "unknown", "unversioned"}:
        report.warning("analysis_unversioned", "Analysis version is not explicit", "analysis.analysis_version")
    if not analysis.get("code_commit"):
        report.warning("missing_commit", "No code commit recorded", "analysis.code_commit")

    result = manifest.get("result")
    if not isinstance(result, dict):
        report.error("result", "result must be an object", "result")
        result = {}
    object_type = result.get("object_type")
    if object_type not in OBJECT_DESTINATIONS:
        report.error("object_type", f"object_type must be one of {sorted(OBJECT_DESTINATIONS)}", "result.object_type")
    if not result.get("title"):
        report.error("title", "result.title is required", "result.title")
    if "summary" not in result:
        report.error("summary", "result.summary field is required", "result.summary")
    elif not result.get("summary"):
        report.warning("empty_summary", "result.summary is empty", "result.summary")
    if not result.get("semantic_status"):
        report.error("semantic_status", "result.semantic_status is required", "result.semantic_status")
    if not result.get("allowed_claim"):
        report.error("allowed_claim", "result.allowed_claim must state the maximum supported claim", "result.allowed_claim")
    forbidden = result.get("forbidden_promotions")
    if not isinstance(forbidden, list):
        report.error("forbidden_promotions", "result.forbidden_promotions must be a list", "result.forbidden_promotions")
    elif not forbidden:
        report.warning("empty_forbidden_promotions", "No forbidden semantic promotions declared", "result.forbidden_promotions")
    temporal = result.get("temporal_semantics")
    if temporal not in TEMPORAL_SEMANTICS:
        report.error("temporal_semantics", f"Invalid temporal_semantics {temporal!r}", "result.temporal_semantics")
    subject_semantics = result.get("subject_semantics")
    if not isinstance(subject_semantics, dict):
        report.error("subject_semantics", "result.subject_semantics must be an object", "result.subject_semantics")
    else:
        if subject_semantics.get("level") not in SUBJECT_LEVELS:
            report.error("subject_level", "Invalid subject semantic level", "result.subject_semantics.level")
        if not isinstance(subject_semantics.get("roles"), list):
            report.error("subject_roles", "result.subject_semantics.roles must be a list", "result.subject_semantics.roles")

    handoff = manifest.get("handoff")
    if not isinstance(handoff, dict):
        report.error("handoff", "handoff must be an object", "handoff")
        handoff = {}
    destination = handoff.get("recommended_destination")
    expected_destination = OBJECT_DESTINATIONS.get(object_type)
    if expected_destination and destination != expected_destination:
        report.error(
            "destination_mismatch",
            f"{object_type} must route to {expected_destination}, not {destination!r}",
            "handoff.recommended_destination",
        )
    import_ready = handoff.get("import_ready")
    blockers = handoff.get("blockers")
    if not isinstance(import_ready, bool):
        report.error("import_ready", "handoff.import_ready must be boolean", "handoff.import_ready")
    if not isinstance(blockers, list):
        report.error("blockers", "handoff.blockers must be a list", "handoff.blockers")
        blockers = []
    if import_ready is True and blockers:
        report.error("ready_with_blockers", "import_ready cannot be true while blockers remain", "handoff")
    if import_ready is False and not blockers:
        report.warning("not_ready_without_blocker", "Draft is not import-ready but declares no blocker", "handoff")

    record_contract = manifest.get("record_contract")
    if not isinstance(record_contract, dict):
        report.error("record_contract", "record_contract must be an object", "record_contract")
        record_contract = {}
    for key in ("primary_key", "time_fields", "subject_fields"):
        if key not in record_contract:
            report.error("record_contract_field", f"record_contract.{key} is required", f"record_contract.{key}")

    payloads = manifest.get("payloads")
    if not isinstance(payloads, list) or not payloads:
        report.error("missing_payloads", "At least one payload is required", "payloads")
        payloads = []
    local_primary: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for index, payload in enumerate(payloads):
        payload_path = f"payloads[{index}]"
        if not isinstance(payload, dict):
            report.error("payload_type", "Payload entry must be an object", payload_path)
            continue
        has_path = "path" in payload
        has_uri = "uri" in payload
        if has_path == has_uri:
            report.error("payload_location", "Payload requires exactly one of path or uri", payload_path)
            continue
        if not payload.get("role") or not payload.get("format"):
            report.error("payload_metadata", "Payload role and format are required", payload_path)
        if has_path:
            try:
                relative = str(safe_relative_path(payload.get("path")))
                resolved = resolve_local_payload(bundle_dir, relative)
            except BridgeError as exc:
                report.error("unsafe_payload_path", str(exc), payload_path + ".path")
                continue
            if relative in seen_paths:
                report.error("duplicate_payload", f"Duplicate payload path {relative}", payload_path)
            seen_paths.add(relative)
            if not resolved.is_file():
                report.error("missing_payload", f"Local payload does not exist: {relative}", payload_path + ".path")
            if payload.get("role") == "primary_records":
                local_primary.append(payload)
            payload_hash = payload.get("sha256")
            if status == "published" and not (isinstance(payload_hash, str) and SHA256_RE.fullmatch(payload_hash)):
                report.error("payload_hash", "Published local payload requires a SHA-256 hash", payload_path + ".sha256")

    provenance = manifest.get("provenance")
    if not isinstance(provenance, dict):
        report.error("provenance", "provenance must be an object", "provenance")
        provenance = {}
    for key in ("inputs", "parameters", "qc", "limitations"):
        if key not in provenance:
            report.error("provenance_field", f"provenance.{key} is required", f"provenance.{key}")
    if isinstance(provenance.get("limitations"), list) and not provenance.get("limitations"):
        report.warning("empty_limitations", "No scientific limitations declared", "provenance.limitations")

    if "codex_notes" not in handoff or not isinstance(handoff.get("codex_notes"), str):
        report.error("codex_notes", "handoff.codex_notes string is required", "handoff.codex_notes")

    if object_type == "aggregate_metric" and temporal != "aggregate":
        report.error("aggregate_temporal", "aggregate_metric requires aggregate temporal semantics", "result.temporal_semantics")

    if object_type == "episode_candidate":
        if temporal not in {"point", "interval", "bounded_window"}:
            report.error("episode_temporal", "episode_candidate cannot use aggregate/none temporal semantics", "result.temporal_semantics")
        if not isinstance(provenance.get("limitations"), list) or not provenance.get("limitations"):
            report.error("episode_limitations", "Episode candidates require at least one declared limitation", "provenance.limitations")
        for key in ("primary_key", "candidate_label_field", "analysis_run_id_field"):
            if not isinstance(record_contract.get(key), str) or not record_contract.get(key):
                report.error("episode_contract", f"record_contract.{key} is required", f"record_contract.{key}")
        time_fields = record_contract.get("time_fields")
        if not isinstance(time_fields, dict):
            report.error("episode_time_fields", "Episode time_fields must be an object", "record_contract.time_fields")
            time_fields = {}
        required_time_keys = ("point",) if temporal == "point" else ("start", "end")
        for key in required_time_keys:
            spec = time_fields.get(key)
            if not _field_name(spec) or _time_representation(spec) not in {"unix_ms_utc", "iso8601_utc"}:
                report.error(
                    "episode_time_field",
                    f"Episode {key} requires field and UTC representation",
                    f"record_contract.time_fields.{key}",
                )
        if temporal in {"interval", "bounded_window"} and time_fields.get("interval_convention") != "[start,end)":
            report.error("interval_convention", "Episode intervals must declare [start,end)", "record_contract.time_fields.interval_convention")
        subjects = record_contract.get("subject_fields")
        if not isinstance(subjects, dict) or not _field_name(subjects.get("subjects")):
            report.error("episode_subject_field", "Episode subject field is required", "record_contract.subject_fields")
        if not result.get("candidate_label"):
            report.error("candidate_label", "Episode result.candidate_label is required", "result.candidate_label")
        source_streams = result.get("source_streams")
        if not isinstance(source_streams, list) or not source_streams or not all(isinstance(item, str) and item for item in source_streams):
            report.error("source_streams", "Episode result.source_streams requires at least one named source", "result.source_streams")
        detector = result.get("detector")
        if not isinstance(detector, dict):
            report.error("detector", "Episode result.detector must be an object", "result.detector")
        else:
            for key in ("model_id", "model_version", "importer_id", "importer_version"):
                if not detector.get(key):
                    report.error("detector_field", f"result.detector.{key} is required", f"result.detector.{key}")
        qc_fields = record_contract.get("qc_fields")
        if not isinstance(qc_fields, list) or not qc_fields:
            report.error("qc_fields", "Episode contract requires at least one QC field", "record_contract.qc_fields")
        evidence_fields = record_contract.get("evidence_fields")
        if not isinstance(evidence_fields, list) or not evidence_fields:
            report.error("evidence_fields", "Episode contract requires evidence-routing fields", "record_contract.evidence_fields")
        state_vector_fields = record_contract.get("state_vector_fields")
        if not isinstance(state_vector_fields, list):
            report.error("state_vector_fields", "Episode state_vector_fields must be a list (empty is allowed)", "record_contract.state_vector_fields")
        score_fields = record_contract.get("score_fields")
        if not isinstance(score_fields, dict):
            report.error("score_fields", "Episode score_fields must be an object (empty is allowed)", "record_contract.score_fields")
        else:
            for score_name, score_spec in score_fields.items():
                if not isinstance(score_spec, dict) or not score_spec.get("meaning") or not score_spec.get("unit"):
                    report.error("score_semantics", f"Score {score_name!r} requires meaning and unit", f"record_contract.score_fields.{score_name}")
                if isinstance(score_spec, dict) and score_spec.get("missing_value") not in {None, "null"}:
                    report.error("score_missing", f"Score {score_name!r} missing_value must be null", f"record_contract.score_fields.{score_name}")
        if not local_primary:
            report.error("episode_primary_payload", "Episode candidate requires a local primary_records payload", "payloads")
        elif len(local_primary) > 1:
            report.error("multiple_primary_payloads", "Episode candidate must declare exactly one primary_records payload", "payloads")
        else:
            _validate_episode_records(bundle_dir, manifest, local_primary[0], report)

    return report


def _git_value(repo_root: Path, args: list[str]) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=repo_root, text=True, stderr=subprocess.DEVNULL,
        ).strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    if not slug:
        raise BridgeError("analysis_id cannot be converted to a safe bundle ID")
    return slug[:64]


def create_draft_bundle(
    exchange_root: str | Path,
    *,
    analysis_id: str,
    analysis_version: str,
    object_type: str,
    title: str,
    bundle_id: str | None = None,
    run_id: str | None = None,
) -> Path:
    """Create a draft staging bundle and conservative manifest template."""
    if object_type not in OBJECT_DESTINATIONS:
        raise BridgeError(f"Unknown object_type {object_type!r}")
    exchange_root = Path(exchange_root).resolve()
    repo_root = exchange_root.parent
    created = utc_now()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    bundle_id = bundle_id or f"{_slug(analysis_id)}--{object_type}--{stamp}"
    if not _is_safe_id(bundle_id):
        raise BridgeError(f"Unsafe bundle_id {bundle_id!r}")
    run_id = run_id or f"run-{stamp}-{uuid.uuid4().hex[:8]}"
    target = exchange_root / "staging" / bundle_id
    if target.exists():
        raise BridgeError(f"Staging bundle already exists: {target}")
    (target / "data").mkdir(parents=True)

    commit = _git_value(repo_root, ["rev-parse", "HEAD"])
    repository = _git_value(repo_root, ["config", "--get", "remote.origin.url"])
    if repository is None:
        repository = _git_value(repo_root, ["rev-parse", "--show-toplevel"])
    dirty_text = _git_value(repo_root, ["status", "--porcelain"])
    dirty = None if commit is None else bool(dirty_text)
    temporal = {
        "episode_candidate": "interval",
        "aggregate_metric": "aggregate",
        "observation_candidate": "aggregate",
        "model_evaluation": "aggregate",
        "artifact_only": "none",
    }[object_type]
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "bundle_id": bundle_id,
        "status": "draft",
        "published_at_utc": None,
        "supersedes_bundle_id": None,
        "producer": {"tool": "claude-code", "agent": "analysis-result-bridge"},
        "analysis": {
            "analysis_id": analysis_id,
            "analysis_version": analysis_version,
            "run_id": run_id,
            "created_at_utc": created,
            "code_repository": repository,
            "code_commit": commit,
            "code_dirty": dirty,
        },
        "result": {
            "object_type": object_type,
            "title": title,
            "summary": "",
            "semantic_status": "candidate",
            "allowed_claim": "",
            "forbidden_promotions": [],
            "temporal_semantics": temporal,
            "subject_semantics": {"level": "none", "roles": []},
        },
        "record_contract": {
            "primary_key": None,
            "time_fields": {},
            "subject_fields": {},
        },
        "payloads": [],
        "provenance": {
            "inputs": [],
            "parameters": {},
            "qc": {},
            "limitations": [],
        },
        "handoff": {
            "recommended_destination": OBJECT_DESTINATIONS[object_type],
            "import_ready": False,
            "blockers": ["Populate and validate the result contract and payloads"],
            "codex_notes": "",
        },
    }
    if object_type == "episode_candidate":
        manifest["result"].update({
            "candidate_label": "",
            "source_streams": [],
            "detector": {
                "model_id": "",
                "model_version": "",
                "importer_id": "",
                "importer_version": "",
            },
        })
        manifest["record_contract"].update({
            "candidate_label_field": "",
            "analysis_run_id_field": "",
            "qc_fields": [],
            "score_fields": {},
            "evidence_fields": [],
            "state_vector_fields": [],
        })
    _write_json(target / MANIFEST_NAME, manifest)
    return target


def publish_bundle(bundle_dir: str | Path, exchange_root: str | Path) -> Path:
    """Validate, hash, seal, and move one staging bundle into published/."""
    bundle_dir = Path(bundle_dir).resolve()
    exchange_root = Path(exchange_root).resolve()
    staging = (exchange_root / "staging").resolve()
    try:
        relative = bundle_dir.relative_to(staging)
    except ValueError as exc:
        raise BridgeError("publish accepts bundles only from analysis_exchange/staging") from exc
    if len(relative.parts) != 1:
        raise BridgeError("Published bundle must be a direct child of staging/")

    manifest = load_manifest(bundle_dir)
    bundle_id = manifest.get("bundle_id")
    destination = exchange_root / "published" / str(bundle_id)
    if destination.exists():
        raise BridgeError(f"Published bundle already exists: {destination}")
    if manifest.get("status") != "draft":
        raise BridgeError("Only draft bundles may be published")
    supersedes = manifest.get("supersedes_bundle_id")
    if supersedes and not (exchange_root / "published" / supersedes).is_dir():
        raise BridgeError(f"supersedes_bundle_id is not published: {supersedes}")

    report = validate_bundle(bundle_dir)
    if not report.valid:
        raise BridgeError("Bundle validation failed:\n" + "\n".join(report.format_lines()))

    for payload in manifest.get("payloads", []):
        if "path" in payload:
            payload["sha256"] = sha256_file(resolve_local_payload(bundle_dir, payload["path"]))
    published_at = utc_now()
    manifest["status"] = "published"
    manifest["published_at_utc"] = published_at
    _write_json(bundle_dir / MANIFEST_NAME, manifest)

    published_report = validate_bundle(bundle_dir)
    if not published_report.valid:
        raise BridgeError("Published manifest validation failed:\n" + "\n".join(published_report.format_lines()))

    manifest_hash = sha256_file(bundle_dir / MANIFEST_NAME)
    seal = {
        "bundle_id": bundle_id,
        "schema_version": manifest.get("schema_version"),
        "manifest_sha256": manifest_hash,
        "sealed_at_utc": published_at,
    }
    _write_json(bundle_dir / SEAL_NAME, seal)
    verify_bundle(bundle_dir)

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(bundle_dir), str(destination))
    return destination


def verify_bundle(bundle_dir: str | Path) -> dict[str, Any]:
    """Verify exact manifest and local payload content against a publication seal."""
    bundle_dir = Path(bundle_dir)
    manifest_path = bundle_dir / MANIFEST_NAME
    seal_path = bundle_dir / SEAL_NAME
    if not manifest_path.is_file() or not seal_path.is_file():
        raise BundleVerificationError(f"Incomplete published bundle: {bundle_dir}")
    try:
        manifest = load_manifest(bundle_dir)
        seal = json.loads(seal_path.read_text(encoding="utf-8"))
    except (BridgeError, json.JSONDecodeError) as exc:
        raise BundleVerificationError(str(exc)) from exc
    if not isinstance(seal, dict):
        raise BundleVerificationError("BUNDLE.SEALED must contain a JSON object")
    if manifest.get("status") != "published":
        raise BundleVerificationError("Published bundle manifest status is not 'published'")
    if manifest.get("bundle_id") != bundle_dir.name or seal.get("bundle_id") != bundle_dir.name:
        raise BundleVerificationError("Bundle ID, directory name, and seal do not agree")
    if seal.get("schema_version") != manifest.get("schema_version"):
        raise BundleVerificationError("Seal schema version does not match manifest")
    actual_manifest_hash = sha256_file(manifest_path)
    if seal.get("manifest_sha256") != actual_manifest_hash:
        raise BundleVerificationError("Manifest hash does not match BUNDLE.SEALED")

    report = validate_bundle(bundle_dir)
    if not report.valid:
        raise BundleVerificationError("Published bundle is invalid:\n" + "\n".join(report.format_lines()))
    for payload in manifest.get("payloads", []):
        if "path" not in payload:
            continue
        try:
            path = resolve_local_payload(bundle_dir, payload["path"])
        except BridgeError as exc:
            raise BundleVerificationError(str(exc)) from exc
        expected = payload.get("sha256")
        actual = sha256_file(path)
        if expected != actual:
            raise BundleVerificationError(f"Payload hash mismatch: {payload['path']}")
    return manifest


def iter_complete_bundle_dirs(published_dir: str | Path) -> Iterable[Path]:
    published_dir = Path(published_dir)
    if not published_dir.is_dir():
        return []
    return (
        path for path in sorted(published_dir.iterdir(), key=lambda item: item.name)
        if path.is_dir() and (path / MANIFEST_NAME).is_file() and (path / SEAL_NAME).is_file()
    )
