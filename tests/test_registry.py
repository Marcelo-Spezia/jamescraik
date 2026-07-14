"""Tests for ICP Registry — loading, validation, multi-ICP (§5, §8)."""

from pathlib import Path

import pytest

from icp_engine.registry.loader import ICPLoadError, ICPRegistry, load_icp
from icp_engine.registry.schema import ICPStatus

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "icps"


class TestLoadIcp:
    def test_load_valid_basic(self):
        icp = load_icp(FIXTURES_DIR / "valid_basic.yaml")
        assert icp.meta.id == "test-basic"
        assert icp.meta.version == "1.0.0"
        assert icp.meta.status == ICPStatus.ACTIVE
        assert len(icp.segments) == 1
        assert len(icp.segments[0].account_criteria) == 5
        assert len(icp.segments[0].contact_criteria) == 2

    def test_load_valid_with_fuzzy(self):
        icp = load_icp(FIXTURES_DIR / "valid_with_fuzzy.yaml")
        assert icp.meta.id == "test-fuzzy"
        assert icp.scoring.fuzzy.enabled is True
        assert len(icp.segments[0].fuzzy_criteria) == 1
        assert icp.segments[0].fuzzy_criteria[0].id == "digital_maturity"

    def test_reject_missing_meta(self):
        with pytest.raises(ICPLoadError, match="validation failed"):
            load_icp(FIXTURES_DIR / "invalid_missing_meta.yaml")

    def test_reject_bad_weights(self):
        with pytest.raises(ICPLoadError, match="validation failed"):
            load_icp(FIXTURES_DIR / "invalid_bad_weights.yaml")

    def test_reject_nonexistent_file(self):
        with pytest.raises(ICPLoadError, match="not found"):
            load_icp(FIXTURES_DIR / "does_not_exist.yaml")

    def test_reject_non_yaml_extension(self):
        # Create a temp file with .txt extension
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"meta: {}")
            f.flush()
            with pytest.raises(ICPLoadError, match=".yaml or .yml"):
                load_icp(f.name)

    def test_scoring_config_defaults(self):
        icp = load_icp(FIXTURES_DIR / "valid_basic.yaml")
        assert icp.scoring.account_weight == 0.6
        assert icp.scoring.contact_weight == 0.4
        assert icp.scoring.intent_max_boost == 20

    def test_tiers_sorted_descending(self):
        icp = load_icp(FIXTURES_DIR / "valid_basic.yaml")
        mins = [t.min for t in icp.scoring.tiers]
        assert mins == sorted(mins, reverse=True), "Tiers must be sorted descending by min"

    def test_knockouts_loaded(self):
        icp = load_icp(FIXTURES_DIR / "valid_basic.yaml")
        kos = icp.segments[0].knockouts
        assert len(kos) == 1
        assert kos[0].field == "employee_count"
        assert kos[0].op == "gte"

    def test_disqualifiers_loaded(self):
        icp = load_icp(FIXTURES_DIR / "valid_basic.yaml")
        dqs = icp.segments[0].disqualifiers
        assert len(dqs) == 1
        assert dqs[0].field == "industry"

    def test_intent_boost_loaded(self):
        icp = load_icp(FIXTURES_DIR / "valid_basic.yaml")
        boosts = icp.segments[0].intent_boost
        assert len(boosts) == 3

    def test_can_load_example_icp(self):
        """The docs/icp.example.yaml should also be loadable."""
        example = Path(__file__).parent.parent / "docs" / "icp.example.yaml"
        if example.exists():
            icp = load_icp(example)
            assert icp.meta.id == "icp-example"


class TestICPRegistry:
    def test_load_and_get(self):
        reg = ICPRegistry()
        reg.load(FIXTURES_DIR / "valid_basic.yaml")
        icp = reg.get("test-basic", "1.0.0")
        assert icp.meta.id == "test-basic"

    def test_get_latest_version(self):
        reg = ICPRegistry()
        reg.load(FIXTURES_DIR / "valid_basic.yaml")
        icp = reg.get("test-basic")  # No version → latest
        assert icp.meta.version == "1.0.0"

    def test_get_nonexistent_raises(self):
        reg = ICPRegistry()
        with pytest.raises(KeyError):
            reg.get("nonexistent")

    def test_get_wrong_version_raises(self):
        reg = ICPRegistry()
        reg.load(FIXTURES_DIR / "valid_basic.yaml")
        with pytest.raises(KeyError):
            reg.get("test-basic", "9.9.9")

    def test_multi_icp(self):
        reg = ICPRegistry()
        reg.load(FIXTURES_DIR / "valid_basic.yaml")
        reg.load(FIXTURES_DIR / "valid_with_fuzzy.yaml")
        assert reg.count == 2
        assert "test-basic" in reg.list_ids()
        assert "test-fuzzy" in reg.list_ids()

    def test_load_dir(self):
        reg = ICPRegistry()
        loaded = reg.load_dir(FIXTURES_DIR)
        # Should load valid ones, skip invalid ones
        assert len(loaded) >= 2
        assert reg.count >= 2

    def test_filter_by_status(self):
        reg = ICPRegistry()
        reg.load(FIXTURES_DIR / "valid_basic.yaml")
        reg.load(FIXTURES_DIR / "valid_with_fuzzy.yaml")
        active = reg.filter_by_status(ICPStatus.ACTIVE)
        draft = reg.filter_by_status(ICPStatus.DRAFT)
        assert len(active) == 1
        assert len(draft) == 1
