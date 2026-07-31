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


def test_list_lead_campaigns_from_stored_leads():
    store = ls.InMemoryLeadStore()
    store.upsert_leads([{"name": "A", "linkedin": "in/a"}], "atlanta-tech-week",
                       "Atlanta Tech Week")
    store.upsert_leads([{"name": "B", "linkedin": "in/b"}], "cfos-fintech", "CFOs fintech")
    camps = store.list_lead_campaigns()
    by_slug = {c["slug"]: c["name"] for c in camps}
    # el filtro del pipeline sale de los leads guardados, no de los archivos de campaña
    assert by_slug == {"atlanta-tech-week": "Atlanta Tech Week", "cfos-fintech": "CFOs fintech"}


def test_funnel_counts_are_cumulative_by_stage():
    leads = [
        {"status": "qualified"}, {"status": "connection_sent"}, {"status": "accepted"},
        {"status": "sent"}, {"status": "replied"}, {"status": "discarded"},
    ]
    c = ls.funnel_counts(leads)
    assert c["leads"] == 5                       # discarded queda afuera
    assert c["connection_sent"] == 4             # todos menos el 'qualified'
    assert c["accepted"] == 3                     # accepted, sent, replied
    assert c["sent"] == 2                         # sent, replied
    assert c["replied"] == 1


def test_campaign_metrics_groups_by_campaign():
    store = ls.InMemoryLeadStore()
    store.upsert_leads([{"name": "A", "linkedin": "in/a"}, {"name": "B", "linkedin": "in/b"}],
                       "camp-1", "Campaña 1")
    store.upsert_leads([{"name": "C", "linkedin": "in/c"}], "camp-2", "Campaña 2")
    store.set_status_by_linkedin("in/a", "accepted")
    m = {row["slug"]: row for row in ls.campaign_metrics(store)}
    assert m["camp-1"]["leads"] == 2 and m["camp-1"]["accepted"] == 1
    assert m["camp-2"]["leads"] == 1 and m["camp-2"]["accepted"] == 0


def test_campaign_metrics_with_hubspot_conversions():
    store = ls.InMemoryLeadStore()
    store.upsert_leads([{"name": "A", "linkedin": "https://linkedin.com/in/a"},
                        {"name": "B", "linkedin": "https://linkedin.com/in/b",
                         "email": "b@acme.com"}], "camp-1", "Campaña 1")
    conv = {
        "by_linkedin": {"linkedin.com/in/a": {"meeting": True, "deals": 1}},
        "by_email": {"b@acme.com": {"meeting": True, "deals": 0}},
    }
    m = {row["slug"]: row for row in ls.campaign_metrics(store, conversions=conv)}
    # A matchea por LinkedIn (reunión + deal); B por email (solo reunión)
    assert m["camp-1"]["meetings"] == 2
    assert m["camp-1"]["opportunities"] == 1


def test_campaign_metrics_without_conversions_has_no_hubspot_keys():
    store = ls.InMemoryLeadStore()
    store.upsert_leads([{"name": "A", "linkedin": "in/a"}], "camp-1", "Campaña 1")
    row = ls.campaign_metrics(store)[0]
    assert "meetings" not in row and "opportunities" not in row


def test_set_status_by_linkedin_matches_webhook():
    store = ls.InMemoryLeadStore()
    store.upsert_leads([{"name": "A", "linkedin": "https://linkedin.com/in/a"}], "camp")
    # el webhook de Expandi manda la URL con otro casing/slash → igual matchea
    n = store.set_status_by_linkedin("https://www.linkedin.com/in/A/", "accepted")
    assert n == 1
    assert store.list_leads("camp")[0]["status"] == "accepted"
