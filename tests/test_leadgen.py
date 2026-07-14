"""Tests de la traducción ICP → query de Apollo (ui/leadgen.py). Sin red."""

from __future__ import annotations

from pathlib import Path

from icp_io import load_icp_dict
from leadgen import build_query_from_icp

REAL_ICP = Path(__file__).parent.parent / "icp" / "tech-enabled-services.yaml"


def test_query_from_icp_maps_criteria():
    data = load_icp_dict(REAL_ICP)
    q = build_query_from_icp(data, per_page=8)

    assert q["per_page"] == 8
    # employee_count between → rango de Apollo (toma el valor actual del ICP)
    emp = next(c for c in data["segments"][0]["account_criteria"]
               if c["field"] == "employee_count" and c["op"] == "between")
    lo, hi = emp["value"]
    assert q["organization_num_employees_ranges"] == [f"{lo},{hi}"]
    # region in [NA, LATAM] → países
    assert "United States" in q["organization_locations"]
    assert "Argentina" in q["organization_locations"]
    # seniority in [c_level, vp, director] → seniorities de Apollo (c_level→c_suite)
    assert set(q["person_seniorities"]) == {"c_suite", "vp", "director"}
    # NO se filtra por departamento (Apollo usa otra taxonomía)
    assert "person_department_or_subdepartments" not in q


def test_query_handles_missing_criteria():
    q = build_query_from_icp({"segments": [{}]}, per_page=5)
    assert q == {"per_page": 5}


def test_query_includes_sector_keywords():
    """Un ICP con sourcing.industry_keywords filtra la búsqueda por sector."""
    data = {"segments": [{"sourcing": {"industry_keywords": ["legal services", "law firms"]}}]}
    q = build_query_from_icp(data, per_page=5)
    assert q["q_organization_keyword_tags"] == ["legal services", "law firms"]


def test_query_includes_person_titles():
    """Títulos específicos (ej. Operating Partner) → filtro de persona en Apollo."""
    data = {"segments": [{"sourcing": {"person_titles": ["Operating Partner"]}}]}
    q = build_query_from_icp(data, per_page=5)
    assert q["person_titles"] == ["Operating Partner"]


def test_org_search_query_strips_person_filters():
    """La búsqueda de EMPRESAS no manda filtros de persona."""
    from leadgen import org_search_query
    data = load_icp_dict(REAL_ICP)
    q = org_search_query(data, per_page=5)
    assert "person_seniorities" not in q
    assert "organization_num_employees_ranges" in q  # sí conserva los de empresa


def test_parse_list_csv_with_header():
    from leadgen import parse_list
    rows = parse_list("email,company\nana@acme.com,Acme\njohn@globex.com,Globex")
    assert rows == [{"email": "ana@acme.com", "company": "Acme"},
                    {"email": "john@globex.com", "company": "Globex"}]


def test_parse_list_no_header():
    from leadgen import parse_list
    assert parse_list("ana@acme.com\njohn@globex.com") == [
        {"email": "ana@acme.com"}, {"email": "john@globex.com"}]
    assert parse_list("Ana García, Acme Legal") == [
        {"name": "Ana García", "company": "Acme Legal"}]


def test_row_to_identifiers():
    from leadgen import row_to_identifiers
    assert row_to_identifiers({"email": "x@y.com"}) == {"email": "x@y.com"}
    ident = row_to_identifiers({"name": "Ana García", "company": "Acme"})
    assert ident == {"name": "Ana García", "organization_name": "Acme"}
    ident2 = row_to_identifiers({"first_name": "Ana", "last_name": "G", "domain": "acme.com"})
    assert ident2 == {"first_name": "Ana", "last_name": "G", "domain": "acme.com"}


def test_tier_from_account_score():
    from leadgen import tier_from_score
    data = {"scoring": {"tiers": [{"tier": "A", "min": 80}, {"tier": "B", "min": 65},
                                  {"tier": "C", "min": 45}]}}
    assert tier_from_score(90, data, False) == "A"
    assert tier_from_score(70, data, False) == "B"
    assert tier_from_score(50, data, False) == "C"
    assert tier_from_score(30, data, False) == "D"
    assert tier_from_score(90, data, True) == "D"  # descalificado → D siempre
