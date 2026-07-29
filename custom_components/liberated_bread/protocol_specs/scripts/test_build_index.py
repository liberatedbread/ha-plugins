"""Tests for scripts/build_index.py.

Prerequisites: run from the repo root, with pyyaml + jsonschema installed.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

# Make scripts/ importable
_scripts_dir = Path(__file__).resolve().parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

import build_index  # noqa: E402


def test_discover_specs():
    """Glob finds every YAML file under device-specs/devices/."""
    paths = build_index.discover_specs()
    assert len(paths) > 0, "Expected at least one device spec"
    stems = {Path(p).stem for p in paths}

    # Compare against the directory itself rather than a hardcoded list: the
    # registry grows, and a list baked into the test only ever rots into a
    # false failure. What matters is that the glob misses nothing.
    on_disk = {p.stem for p in build_index.SPECS_DIR.glob("*.yaml")}
    assert stems == on_disk, f"Glob missed {sorted(on_disk - stems)}"

    # A few long-standing specs, so an empty or wrongly-rooted glob still fails.
    assert {"ember-mug", "wemo-devices", "vector-robot"} <= stems


def test_load_yaml():
    """load_yaml returns a dict from a real spec."""
    paths = build_index.discover_specs()
    chef = [p for p in paths if "chef-iq-sense" in str(p)][0]
    spec = build_index.load_yaml(Path(chef))
    assert isinstance(spec, dict)
    assert "device" in spec
    assert spec["device"]["name"] == "Chef iQ Sense"


def test_validate_all_specs_pass():
    """Every device spec in devices/ validates against schema.json."""
    schema = build_index.load_schema()
    paths = build_index.discover_specs()
    for path in paths:
        spec = build_index.load_yaml(Path(path))
        build_index.validate_spec(spec, schema, Path(path))


def test_manifest_structure(monkeypatch):
    """Manifest has the documented keys and valid device entries."""
    schema = build_index.load_schema()
    paths = build_index.discover_specs()

    generated_at = "2026-01-01T00:00:00+00:00"
    # Force git fallback so updated_at is deterministic
    monkeypatch.setattr(
        build_index, "git_last_modified", lambda _path, _fallback: generated_at
    )

    # Load + serialize every spec
    specs = [build_index.load_and_serialize_spec(Path(p), schema) for p in paths]
    manifest = build_index.build_manifest(specs, schema, generated_at)

    assert manifest["api_version"] == "1"
    assert manifest["generated_at"] == generated_at
    assert "https://opengreeniot.pigscanfly.ca/device-spec.schema.json" in manifest["schema"]
    assert manifest["device_count"] == len(paths)
    assert len(manifest["devices"]) == len(paths)

    for entry in manifest["devices"]:
        assert "id" in entry
        assert "name" in entry
        assert "manufacturer" in entry
        assert "protocol" in entry
        assert "status" in entry
        assert "updated_at" in entry
        assert entry["updated_at"] == generated_at  # forced fallback
        assert entry["url"].startswith("/api/v1/devices/")
        assert entry["url"].endswith(f"/{entry['id']}.json")
        assert entry["checksum"].startswith("sha256:")

    # Devices are sorted alphabetically
    ids = [e["id"] for e in manifest["devices"]]
    assert ids == sorted(ids), f"devices not sorted: {ids}"


def test_deterministic_output():
    """Two runs produce the same manifest and per-device JSON."""
    schema = build_index.load_schema()
    paths = build_index.discover_specs()
    generated_at = "2026-01-01T00:00:00+00:00"

    specs = [build_index.load_and_serialize_spec(Path(p), schema) for p in paths]
    m1 = build_index.build_manifest(specs, schema, generated_at)
    m2 = build_index.build_manifest(specs, schema, generated_at)

    assert build_index.json_dumps(m1) == build_index.json_dumps(m2)


def test_per_device_json():
    """Per-device JSON is valid JSON with expected structure."""
    paths = build_index.discover_specs()
    schema = build_index.load_schema()

    for path in paths:
        spec = build_index.load_yaml(Path(path))
        json_text, _checksum = build_index.serialize_device_spec(spec)
        # json_text includes trailing "\n"; strip it for round-trip
        per_device = json.loads(json_text)
        assert "device" in per_device
        # Must carry at least one transport block. The accepted set is READ FROM
        # the schema's top-level anyOf rather than restated here: this test used
        # to hardcode the list and claim to mirror it, which meant every new
        # transport (bus, cloud) failed a test that was only ever out of date.
        transports = [
            required
            for branch in schema["anyOf"]
            for required in branch.get("required", [])
        ]
        assert transports, "schema anyOf declares no transport blocks"
        assert any(k in per_device for k in transports), (
            f"{Path(path).stem} missing transport (expected one of {transports})"
        )


def test_manifest_checksums_match_disk_files():
    """Every manifest checksum equals sha256 of the bytes-on-disk JSON file.

    This is the regression test for the blocking bug: the manifest checksum
    must match the EXACT bytes written to each ``<id>.json`` file, including
    the trailing newline.
    """
    schema = build_index.load_schema()
    paths = build_index.discover_specs()
    generated_at = "2026-01-01T00:00:00+00:00"

    # Load + serialize every spec once (single source of truth)
    specs = [build_index.load_and_serialize_spec(Path(p), schema) for p in paths]
    manifest = build_index.build_manifest(specs, schema, generated_at)

    with tempfile.TemporaryDirectory() as tmpdir:
        api_dir = Path(tmpdir) / "api" / "v1"
        build_index.write_output(manifest, specs, api_dir)

        # Now read each file from disk and verify checksums match
        devices_dir = api_dir / "devices"
        for entry in manifest["devices"]:
            dev_path = devices_dir / f"{entry['id']}.json"
            assert dev_path.exists(), f"Missing: {dev_path}"

            # Hash the exact bytes on disk
            disk_bytes = dev_path.read_bytes()
            actual_checksum = f"sha256:{hashlib.sha256(disk_bytes).hexdigest()}"

            assert (
                entry["checksum"] == actual_checksum
            ), (
                f"Checksum mismatch for {entry['id']}:\n"
                f"  manifest says: {entry['checksum']}\n"
                f"  disk file is:  {actual_checksum}"
            )
