r"""
environment_map.py — versioned physical-layout map for the WISER agent-policy study.

This is the PRIMARY static-opportunity representation (NOT pooled animal occupancy). It is a
thin layer over ``configs/wiser_rois.json`` (ROI geometry, placed directly in the WISER inch
frame, confirmed per-ROI) plus ``configs/environment_map/<window>.yaml`` (resource types,
nominally-symmetric groups, intervention/regime calendar, WISER dropout regions, registration
bounds). It derives frame-invariant layout predictors for the leaving-hazard and destination
processes.

Frame: WISER native INCHES, offset origin, UNVERIFIED vs the physical field frame
(``wiser_to_field_transform.json`` is absent). Only topology + COARSE (jitter-bounded)
distances are usable; fine metric-distance predictors are forbidden below
``min_resolvable_distance_in`` (see :meth:`EnvironmentMap.usable_distance`).

numpy + json + (optional) pyyaml only, so it imports in the ``cv`` env.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

try:
    import yaml
except Exception:                                    # pragma: no cover
    yaml = None


# ---------------------------------------------------------------------------
# loaders
# ---------------------------------------------------------------------------

def load_environment_map(path: str | Path) -> dict:
    """Parse the versioned environment-map YAML."""
    if yaml is None:
        raise RuntimeError("pyyaml is required to load the environment map")
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def load_rois(path: str | Path) -> dict:
    """Load ``wiser_rois.json`` (ROI geometry in the WISER inch frame)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _night_str(night) -> str:
    """Normalise a night key to 'YYYY-MM-DD' (accepts str / date / datetime / Timestamp)."""
    if isinstance(night, str):
        return night[:10]
    for attr in ("date",):
        if hasattr(night, attr):
            try:
                return night.date().isoformat()
            except Exception:
                pass
    return str(night)[:10]


# ---------------------------------------------------------------------------
# environment map
# ---------------------------------------------------------------------------

class EnvironmentMap:
    """Resolve the physical layout for a given night and derive layout predictors.

    A gap inside a dropout region is 'unknown', never 'leaving' — callers must honour
    :meth:`is_dropout` and never impute a departure there.
    """

    def __init__(self, env_map: dict, roi_cfg: dict):
        self.env = env_map or {}
        self.roi_cfg = roi_cfg or {}
        b = (self.roi_cfg.get("boundary") or {}).get("rect")
        self.boundary = [float(v) for v in b] if b else None          # [xmin,xmax,ymin,ymax]
        self.centers = {r["name"]: (float(r["x"]), float(r["y"]))
                        for r in self.roi_cfg.get("rois", [])}
        self.resource_types = dict(self.env.get("resource_types", {}))
        self._struct_names = {s["name"] for s in self.env.get("structures", [])}
        self.reg = self.env.get("registration", {})
        self.jitter_floor_in = float(self.reg.get("jitter_floor_in", 7.0))
        self.min_resolvable_in = float(self.reg.get("min_resolvable_distance_in", 14.0))

    # -- construction helper ------------------------------------------------
    @classmethod
    def from_paths(cls, env_map_path, roi_path) -> "EnvironmentMap":
        return cls(load_environment_map(env_map_path), load_rois(roi_path))

    # -- per-night resolution ----------------------------------------------
    def night_regime(self, night) -> dict:
        """Per-night regime flags (phase, wet, fireworks, truncated, burrow, n_rats)."""
        return dict(self.env.get("night_regime", {}).get(_night_str(night), {}))

    def structures_present(self, night) -> list:
        ns = _night_str(night)
        return [s["name"] for s in self.env.get("structures", [])
                if ns in (s.get("nights_present") or [])]

    def active_rois(self, night) -> list:
        """Named ROIs present on this night. ROIs listed as time-varying ``structures``
        follow their ``nights_present``; all others are always present."""
        present = set(self.structures_present(night))
        out = []
        for r in self.roi_cfg.get("rois", []):
            name = r["name"]
            if name in self._struct_names:
                if name in present:
                    out.append(name)
            else:
                out.append(name)
        return out

    def is_dropout(self, roi, night) -> bool:
        """True if ``roi`` is in a known WISER below-plane dropout regime on this night
        (e.g. the refuge_4 burrow window). Occupancy under-counts; gaps stay 'unknown'."""
        ns = _night_str(night)
        for d in self.env.get("dropout_regions", []):
            if d.get("roi") == roi and ns in (d.get("nights_affected") or []):
                return True
        return False

    # -- geometry / types ---------------------------------------------------
    def resource_type(self, roi) -> str:
        return self.resource_types.get(roi, "open")

    def center(self, roi):
        return self.centers.get(roi)

    def distance_to_edge(self, x, y) -> float:
        """Inches from (x,y) to the nearest confirmed boundary edge (frame-invariant
        under a rigid frame; coarse)."""
        if not self.boundary:
            return float("nan")
        xmin, xmax, ymin, ymax = self.boundary
        return float(min(x - xmin, xmax - x, y - ymin, ymax - y))

    def coarse_distance(self, a, b) -> float:
        ca, cb = self.centers.get(a), self.centers.get(b)
        if ca is None or cb is None:
            return float("nan")
        return float(np.hypot(ca[0] - cb[0], ca[1] - cb[1]))

    def usable_distance(self, a, b):
        """(distance_in, reliable) — ``reliable`` is False when the distance is below the
        registration/jitter resolution, in which case topology/type should be used instead."""
        d = self.coarse_distance(a, b)
        return d, bool(np.isfinite(d) and d >= self.min_resolvable_in)

    def distance_matrix(self, rois):
        rois = list(rois)
        n = len(rois)
        M = np.zeros((n, n), float)
        for i, a in enumerate(rois):
            for j, b in enumerate(rois):
                M[i, j] = 0.0 if i == j else self.coarse_distance(a, b)
        return rois, M

    # -- choice set (layout fallback) --------------------------------------
    def choice_set_layout(self, origin, night, include_open: bool = True) -> list:
        """Open-paddock reachability fallback: every other active named ROI is reachable
        from ``origin`` (the paddock is open field, not a maze), plus 'open'. The empirical
        origin-conditioned choice set (training-fold supported transitions) is built in
        ``semimarkov_decisions``; this is the topological fallback."""
        act = [r for r in self.active_rois(night) if r != origin]
        return act + (["open"] if include_open else [])

    def symmetric_groups(self) -> dict:
        """Nominally symmetric resource groups for the matched-choice analysis."""
        return dict(self.env.get("symmetric_groups", {}))

    def registration_note(self) -> dict:
        return {
            "status": self.reg.get("status", "UNVERIFIED"),
            "physical_transform": self.reg.get("physical_transform", "absent"),
            "roi_placement_confirmed": self.reg.get("roi_placement_confirmed", True),
            "jitter_floor_in": self.jitter_floor_in,
            "min_resolvable_distance_in": self.min_resolvable_in,
        }

    # -- predictor assembly -------------------------------------------------
    def layout_features(self, roi, night) -> dict:
        """Frame-invariant, coarse layout predictors for a resident/origin ROI."""
        rt = self.resource_type(roi)
        c = self.centers.get(roi)
        return {
            "roi": roi,
            "resource_type": rt,
            "is_house": int(rt == "house"),
            "is_food": int(rt == "food"),
            "is_water": int(rt == "water"),
            "is_refuge": int(rt == "refuge"),
            "is_tunnel": int(rt == "tunnel"),
            "is_open": int(rt == "open"),
            "dist_to_edge_in": self.distance_to_edge(*c) if c else float("nan"),
            "is_dropout_region": int(self.is_dropout(roi, night)),
        }

    def destination_features(self, origin, dest, night) -> dict:
        """Frame-invariant layout predictors for an origin->dest candidate (destination model).
        Coarse distance is emitted only when reliable; otherwise flagged."""
        d, reliable = self.usable_distance(origin, dest)
        rt = self.resource_type(dest)
        return {
            "dest": dest,
            "dest_resource_type": rt,
            "dest_is_house": int(rt == "house"),
            "dest_is_food": int(rt == "food"),
            "dest_is_water": int(rt == "water"),
            "dest_is_refuge": int(rt == "refuge"),
            "dest_is_open": int(rt == "open"),
            "origin_dest_dist_in": d if reliable else float("nan"),
            "distance_reliable": int(reliable),
            "dest_is_dropout_region": int(self.is_dropout(dest, night)),
        }
