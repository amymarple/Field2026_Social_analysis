from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from analysis_exchange.python.bridge import (
    BridgeError,
    BundleVerificationError,
    create_draft_bundle,
    publish_bundle,
    validate_bundle,
    verify_bundle,
)
from analysis_exchange.python.reader import iter_published_bundles
from episode_browser.utils.exchange_import import (
    ExchangeImportError,
    iter_import_ready_episode_bundles,
    map_bundle_to_browser_episodes,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = REPO_ROOT / "analysis_exchange" / "examples" / "lagged-path-reuse-example"


def _read_manifest(bundle: Path) -> dict:
    return json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))


def _write_manifest(bundle: Path, manifest: dict) -> None:
    (bundle / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


class BridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.exchange = Path(self.temporary.name) / "analysis_exchange"
        for name in ("staging", "published", "rejected"):
            (self.exchange / name).mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def copy_example(self, *, bundle_id: str = "lagged-path-reuse-example") -> Path:
        destination = self.exchange / "staging" / bundle_id
        shutil.copytree(EXAMPLE, destination)
        if bundle_id != "lagged-path-reuse-example":
            manifest = _read_manifest(destination)
            manifest["bundle_id"] = bundle_id
            _write_manifest(destination, manifest)
        return destination

    def make_aggregate(self, bundle_id: str = "aggregate-example") -> Path:
        bundle = self.copy_example(bundle_id=bundle_id)
        manifest = _read_manifest(bundle)
        manifest["result"] = {
            "object_type": "aggregate_metric",
            "title": "Aggregate example",
            "summary": "A test-only aggregate result.",
            "semantic_status": "candidate",
            "allowed_claim": "One aggregate value was computed over the declared unit.",
            "forbidden_promotions": ["time-local episode"],
            "temporal_semantics": "aggregate",
            "subject_semantics": {"level": "cohort", "roles": []},
        }
        manifest["record_contract"] = {
            "primary_key": None,
            "time_fields": {},
            "subject_fields": {},
        }
        manifest["handoff"]["recommended_destination"] = "observation_compiler"
        _write_manifest(bundle, manifest)
        return bundle

    def test_valid_example_bundle_passes(self) -> None:
        report = validate_bundle(EXAMPLE)
        self.assertTrue(report.valid, report.format_lines())

    def test_new_creates_conservative_routed_template(self) -> None:
        bundle = create_draft_bundle(
            self.exchange,
            analysis_id="test-analysis",
            analysis_version="1.2.3",
            object_type="model_evaluation",
            title="Test evaluation",
            bundle_id="test-analysis-evaluation",
            run_id="test-run",
        )
        manifest = _read_manifest(bundle)
        self.assertEqual(manifest["handoff"]["recommended_destination"], "evaluation_registry")
        self.assertFalse(manifest["handoff"]["import_ready"])
        self.assertTrue(manifest["handoff"]["blockers"])
        self.assertIn("code_dirty", manifest["analysis"])
        self.assertTrue((bundle / "data").is_dir())

    def test_import_ready_episode_rejects_uninspected_parquet_primary(self) -> None:
        bundle = self.copy_example()
        manifest = _read_manifest(bundle)
        manifest["payloads"][0]["format"] = "parquet"
        _write_manifest(bundle, manifest)
        self.assertIn(
            "uninspected_primary_payload",
            {issue.code for issue in validate_bundle(bundle).errors},
        )

    def test_invalid_destination_object_mapping_fails(self) -> None:
        bundle = self.copy_example()
        manifest = _read_manifest(bundle)
        manifest["handoff"]["recommended_destination"] = "evaluation_registry"
        _write_manifest(bundle, manifest)
        report = validate_bundle(bundle)
        self.assertIn("destination_mismatch", {issue.code for issue in report.errors})

    def test_invalid_status_fails(self) -> None:
        bundle = self.copy_example()
        manifest = _read_manifest(bundle)
        manifest["status"] = "final"
        _write_manifest(bundle, manifest)
        self.assertIn("status", {issue.code for issue in validate_bundle(bundle).errors})

    def test_missing_allowed_claim_fails(self) -> None:
        bundle = self.copy_example()
        manifest = _read_manifest(bundle)
        manifest["result"]["allowed_claim"] = ""
        _write_manifest(bundle, manifest)
        self.assertIn("allowed_claim", {issue.code for issue in validate_bundle(bundle).errors})

    def test_import_ready_with_blockers_fails(self) -> None:
        bundle = self.copy_example()
        manifest = _read_manifest(bundle)
        manifest["handoff"]["blockers"] = ["Evidence mapping unresolved"]
        _write_manifest(bundle, manifest)
        self.assertIn("ready_with_blockers", {issue.code for issue in validate_bundle(bundle).errors})

    def test_aggregate_metric_routed_to_browser_fails(self) -> None:
        bundle = self.make_aggregate()
        manifest = _read_manifest(bundle)
        manifest["handoff"]["recommended_destination"] = "episode_browser"
        _write_manifest(bundle, manifest)
        report = validate_bundle(bundle)
        self.assertFalse(report.valid)
        self.assertIn("destination_mismatch", {issue.code for issue in report.errors})

    def test_episode_without_utc_time_fields_fails(self) -> None:
        bundle = self.copy_example()
        manifest = _read_manifest(bundle)
        manifest["record_contract"]["time_fields"] = {
            "start": {"field": "local_start", "representation": "local_wall_clock"},
            "end": {"field": "local_end", "representation": "local_wall_clock"},
            "interval_convention": "[start,end)",
        }
        _write_manifest(bundle, manifest)
        report = validate_bundle(bundle)
        self.assertIn("episode_time_field", {issue.code for issue in report.errors})

    def test_missing_payload_fails(self) -> None:
        bundle = self.copy_example()
        (bundle / "data" / "records.jsonl").unlink()
        report = validate_bundle(bundle)
        self.assertIn("missing_payload", {issue.code for issue in report.errors})

    def test_publish_creates_hashes_and_seal(self) -> None:
        bundle = self.copy_example()
        published = publish_bundle(bundle, self.exchange)
        manifest = _read_manifest(published)
        self.assertEqual(manifest["status"], "published")
        self.assertRegex(manifest["payloads"][0]["sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue((published / "BUNDLE.SEALED").is_file())

    def test_published_bundle_verifies(self) -> None:
        published = publish_bundle(self.copy_example(), self.exchange)
        manifest = verify_bundle(published)
        self.assertEqual(manifest["bundle_id"], published.name)

    def test_modified_published_payload_fails_verification(self) -> None:
        published = publish_bundle(self.copy_example(), self.exchange)
        with (published / "data" / "records.jsonl").open("a", encoding="utf-8") as handle:
            handle.write("{}\n")
        with self.assertRaises(BundleVerificationError):
            verify_bundle(published)

    def test_modified_published_manifest_fails_verification(self) -> None:
        published = publish_bundle(self.copy_example(), self.exchange)
        manifest = _read_manifest(published)
        manifest["result"]["title"] = "Tampered title"
        _write_manifest(published, manifest)
        with self.assertRaises(BundleVerificationError):
            verify_bundle(published)

    def test_duplicate_publication_is_refused(self) -> None:
        publish_bundle(self.copy_example(), self.exchange)
        duplicate = self.copy_example()
        with self.assertRaises(BridgeError):
            publish_bundle(duplicate, self.exchange)

    def test_reader_filters_destination_and_object_type(self) -> None:
        publish_bundle(self.copy_example(), self.exchange)
        publish_bundle(self.make_aggregate(), self.exchange)
        episodes = list(iter_published_bundles(
            self.exchange,
            destination="episode_browser",
            object_type="episode_candidate",
            verify=True,
        ))
        aggregates = list(iter_published_bundles(
            self.exchange,
            destination="observation_compiler",
            object_type="aggregate_metric",
            verify=True,
        ))
        self.assertEqual([bundle.bundle_id for bundle in episodes], ["lagged-path-reuse-example"])
        self.assertEqual([bundle.bundle_id for bundle in aggregates], ["aggregate-example"])

    def test_unsafe_payload_path_is_rejected(self) -> None:
        bundle = self.copy_example()
        manifest = _read_manifest(bundle)
        manifest["payloads"][0]["path"] = "../outside.jsonl"
        _write_manifest(bundle, manifest)
        report = validate_bundle(bundle)
        self.assertIn("unsafe_payload_path", {issue.code for issue in report.errors})

    def test_browser_adapter_maps_verified_example(self) -> None:
        publish_bundle(self.copy_example(), self.exchange)
        bundles = list(iter_import_ready_episode_bundles(self.exchange, verify=True))
        self.assertEqual(len(bundles), 1)
        episodes = map_bundle_to_browser_episodes(bundles[0])
        self.assertEqual(len(episodes), 1)
        episode = episodes[0]
        provenance = episode["linked_assets"]["analysis_exchange"]
        self.assertEqual(episode["state_model_id"], "wiser_lagged_path_reuse_v1")
        self.assertEqual(episode["labels"], [])
        self.assertEqual(episode["lens_scores"], {})
        self.assertEqual(provenance["original_candidate_label"], "lagged_path_reuse_candidate")
        self.assertIn("social following", provenance["forbidden_promotions"])

    def test_browser_adapter_rejects_unknown_state_model(self) -> None:
        bundle = self.copy_example()
        manifest = _read_manifest(bundle)
        manifest["result"]["detector"]["model_id"] = "unregistered_model_v1"
        _write_manifest(bundle, manifest)
        publish_bundle(bundle, self.exchange)
        published = next(iter_import_ready_episode_bundles(self.exchange, verify=True))
        with self.assertRaises(ExchangeImportError):
            map_bundle_to_browser_episodes(published)

    def test_reader_ignores_incomplete_directory(self) -> None:
        incomplete = self.exchange / "published" / "incomplete"
        incomplete.mkdir()
        (incomplete / "manifest.json").write_text("{}", encoding="utf-8")
        self.assertEqual(list(iter_published_bundles(self.exchange, verify=True)), [])

    def test_repository_published_example_is_readable(self) -> None:
        exchange_root = REPO_ROOT / "analysis_exchange"
        bundles = list(iter_published_bundles(
            exchange_root,
            destination="episode_browser",
            object_type="episode_candidate",
            verify=True,
        ))
        self.assertIn("lagged-path-reuse-example", [bundle.bundle_id for bundle in bundles])
        selected = next(bundle for bundle in bundles if bundle.bundle_id == "lagged-path-reuse-example")
        self.assertEqual(len(map_bundle_to_browser_episodes(selected)), 1)


if __name__ == "__main__":
    unittest.main()
