"""Tests del store de leads (ui/leads_store.py) con el stub en memoria."""

from __future__ import annotations

import leads_store as ls


def test_norm_linkedin():
    assert ls.norm_linkedin("https://www.linkedin.com/in/Maxi/") == "linkedin.com/in/maxi"
    assert ls.norm_linkedin("http://linkedin.com/in/x?foo=1") == "linkedin.com/in/x"
    assert ls.norm_linkedin("") is None


def test_lead_to_row_splits_base_and_enrichment():
    lead = {"name": "Maxi", "company": "Lemon", "linkedin": "https://linkedin.com/in/x",
            "tier": "A", "reason": "fintech", "hook": "hablar de su ronda",
            "value_prop_match": "MS moderniza"}
    row = ls.lead_to_row(lead, "cfos-fintech", "CFOs fintech")
    assert row["campaign_slug"] == "cfos-fintech"
    assert row["linkedin_url"] == "linkedin.com/in/x"       # normalizado
    assert row["tier"] == "A"
    # hook / value_prop_match van al jsonb de enrichment, no como columnas
    assert row["enrichment"] == {"hook": "hablar de su ronda",
                                 "value_prop_match": "MS moderniza"}


def test_upsert_dedups_by_linkedin_and_preserves_pipeline():
    store = ls.InMemoryLeadStore()
    leads = [{"name": "A", "linkedin": "https://linkedin.com/in/a", "tier": "A", "reason": "x"},
             {"name": "B", "linkedin": "https://linkedin.com/in/b", "tier": "B", "reason": "y"}]
    ins, upd = store.upsert_leads(leads, "camp")
    assert (ins, upd) == (2, 0)
    # avanzamos a 'A' en el pipeline
    a = next(ld for ld in store.list_leads("camp") if ld["name"] == "A")
    store.update_fields(a["id"], {"status": "sent", "message": "hola"})
    # re-calificar la MISMA lista no duplica ni pisa el estado del pipeline
    ins2, upd2 = store.upsert_leads(leads, "camp")
    assert (ins2, upd2) == (0, 2)
    a2 = next(ld for ld in store.list_leads("camp") if ld["name"] == "A")
    assert a2["status"] == "sent" and a2["message"] == "hola"


def test_list_filters_by_status_and_row_to_lead_flattens():
    store = ls.InMemoryLeadStore()
    store.upsert_leads([{"name": "A", "linkedin": "in/a", "tier": "A",
                         "hook": "un ángulo"}], "camp")
    lead = store.list_leads("camp")[0]
    assert lead["hook"] == "un ángulo"          # enrichment aplanado al raíz
    assert lead["status"] == "qualified"
    assert store.list_leads("camp", statuses=["sent"]) == []


def test_set_status_by_linkedin_matches_webhook():
    store = ls.InMemoryLeadStore()
    store.upsert_leads([{"name": "A", "linkedin": "https://linkedin.com/in/a"}], "camp")
    # el webhook de Expandi manda la URL con otro casing/slash → igual matchea
    n = store.set_status_by_linkedin("https://www.linkedin.com/in/A/", "accepted")
    assert n == 1
    assert store.list_leads("camp")[0]["status"] == "accepted"
