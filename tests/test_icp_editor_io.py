"""Tests de la lógica del editor de ICP (ui/icp_io.py) — sin Streamlit."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from icp_io import (
    apply_version_bump,
    bump_version,
    cell_to_value,
    load_icp_dict,
    save_icp_dict,
    validate_icp_dict,
    value_to_cell,
)

REAL_ICP = Path(__file__).parent.parent / "icp" / "tech-enabled-services.yaml"


def test_bump_version():
    assert bump_version("0.1.1", "patch") == "0.1.2"
    assert bump_version("0.1.1", "minor") == "0.2.0"
    assert bump_version("1.2.3", "major") == "2.0.0"
    with pytest.raises(ValueError):
        bump_version("abc", "patch")


def test_value_cell_roundtrip():
    assert value_to_cell([200, 2000]) == "200, 2000"
    assert value_to_cell(["software", "fintech"]) == "software, fintech"
    assert value_to_cell(50) == "50"
    assert cell_to_value("200, 2000", "between") == [200, 2000]
    assert cell_to_value("software, fintech", "in") == ["software", "fintech"]
    assert cell_to_value("50", "gte") == 50  # escalar para ops no-lista


def test_validate_real_icp_ok():
    data = load_icp_dict(REAL_ICP)
    ok, err = validate_icp_dict(data)
    assert ok, err


def test_validate_rejects_bad_weights():
    data = load_icp_dict(REAL_ICP)
    data["scoring"]["account_weight"] = 0.9
    data["scoring"]["contact_weight"] = 0.9  # suma != 1.0 → inválido (§5.4)
    ok, err = validate_icp_dict(data)
    assert not ok
    assert "weight" in err.lower()


def test_save_roundtrip_and_version_bump(tmp_path):
    data = load_icp_dict(REAL_ICP)
    # editar un peso y subir versión patch con changelog
    data["segments"][0]["fuzzy_criteria"][0]["weight"] = 55
    before = data["meta"]["version"]
    apply_version_bump(data, "patch", "Ajuste de peso tech_enabled.", date(2026, 6, 19))

    out = tmp_path / "edited.yaml"
    save_icp_dict(data, out)

    reloaded = load_icp_dict(out)
    ok, err = validate_icp_dict(reloaded)
    assert ok, err
    assert reloaded["meta"]["version"] == bump_version(before, "patch")
    assert reloaded["segments"][0]["fuzzy_criteria"][0]["weight"] == 55
    assert reloaded["meta"]["changelog"][-1]["note"] == "Ajuste de peso tech_enabled."


def test_save_refuses_invalid(tmp_path):
    data = load_icp_dict(REAL_ICP)
    data["scoring"]["tiers"] = [{"tier": "Z", "min": 200}]  # tier inválido
    with pytest.raises(ValueError):
        save_icp_dict(data, tmp_path / "bad.yaml")
