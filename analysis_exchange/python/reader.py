"""Stable, browser-independent API for reading sealed published bundles only."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from .bridge import (
    iter_complete_bundle_dirs,
    load_manifest,
    resolve_local_payload,
    verify_bundle,
)


@dataclass(frozen=True)
class PublishedBundle:
    path: Path
    manifest: dict[str, Any]

    @property
    def bundle_id(self) -> str:
        return str(self.manifest["bundle_id"])

    def local_payloads(self, role: str | None = None) -> tuple[Path, ...]:
        paths = []
        for payload in self.manifest.get("payloads", []):
            if "path" not in payload or (role is not None and payload.get("role") != role):
                continue
            paths.append(resolve_local_payload(self.path, payload["path"]))
        return tuple(paths)


def iter_published_bundles(
    exchange_root: str | Path,
    *,
    destination: str | None = None,
    object_type: str | None = None,
    verify: bool = True,
) -> Iterator[PublishedBundle]:
    """Yield complete published bundles matching optional deterministic filters.

    Incomplete directories are ignored. A complete but invalid/tampered bundle raises
    when ``verify`` is true; it is never silently consumed.
    """
    published_dir = Path(exchange_root) / "published"
    for bundle_dir in iter_complete_bundle_dirs(published_dir):
        manifest = verify_bundle(bundle_dir) if verify else load_manifest(bundle_dir)
        result = manifest.get("result") or {}
        handoff = manifest.get("handoff") or {}
        if destination is not None and handoff.get("recommended_destination") != destination:
            continue
        if object_type is not None and result.get("object_type") != object_type:
            continue
        yield PublishedBundle(bundle_dir, manifest)

