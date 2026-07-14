"""Tests del núcleo de calificación (ui/qualify.py): parseo CSV, export, qualify."""

from __future__ import annotations

import json

import qualify

SAMPLE_CSV = (
    'first_name,last_name,name,job_title,company_name,company_website,'
    'employee_count_start,employee_count_end,industries,location,email,profile_link\n'
    'Maxi,Raimondi,Maxi Raimondi,CFO,Lemon Cash,http://lemon.me,51.0,200.0,'
    '"[\'Financial Services\']","Buenos Aires, AR",m@lemon.me,https://linkedin.com/in/x\n'
    'Ale,h,Ale h,CFO,Instagram,,,,[],,,https://linkedin.com/in/y\n'
)


def test_parse_sales_nav_csv():
    leads = qualify.parse_sales_nav_csv(SAMPLE_CSV)
    assert len(leads) == 2
    a = leads[0]
    assert a["name"] == "Maxi Raimondi"
    assert a["title"] == "CFO"
    assert a["domain"] == "lemon.me"          # limpió http://
    assert a["size"] == "51-200"              # juntó start-end
    assert a["industry"] == "Financial Services"
    assert a["email"] == "m@lemon.me"
    # fila con datos pobres no rompe
    assert leads[1]["company"] == "Instagram"
    assert leads[1]["size"] == ""


def test_detect_mapping_recognizes_foreign_headers():
    # CSV con headers de otra herramienta (estilo Apollo), en inglés variado
    headers = ["Full Name", "Title", "Company", "Website", "# Employees",
               "Industry", "Person Location", "Email", "LinkedIn URL", "Extra Col"]
    m = qualify.detect_mapping(headers)
    assert m["name"] == "Full Name"
    assert m["title"] == "Title"
    assert m["company"] == "Company"
    assert m["domain"] == "Website"
    assert m["size"] == "# Employees"
    assert m["industry"] == "Industry"
    assert m["location"] == "Person Location"
    assert m["email"] == "Email"
    assert m["linkedin"] == "LinkedIn URL"


def test_detect_mapping_spanish_and_unknowns():
    headers = ["Nombre", "Cargo", "Empresa", "Sitio Web", "Rubro", "Columna Rara"]
    m = qualify.detect_mapping(headers)
    assert m["name"] == "Nombre"
    assert m["title"] == "Cargo"
    assert m["company"] == "Empresa"
    assert m["domain"] == "Sitio Web"
    assert m["industry"] == "Rubro"
    assert m["email"] == ""           # no había → queda sin asignar


def test_detect_mapping_compound_company_header():
    # header real de Apollo que no calza exacto pero contiene 'company' (2º paso)
    m = qualify.detect_mapping(["Full Name", "Company Name for Emails", "Website"])
    assert m["company"] == "Company Name for Emails"
    assert m["domain"] == "Website"


def test_leads_from_rows_manual_mapping_and_single_size():
    headers, rows = qualify.read_csv(
        "Persona,Compañía,Web,Headcount\n"
        "Ana López,Acme SRL,https://acme.io/,250\n")
    # mapeo manual (override): 'Persona'→name, 'Compañía'→company, etc.
    mapping = {"name": "Persona", "company": "Compañía", "domain": "Web", "size": "Headcount"}
    leads = qualify.leads_from_rows(rows, mapping)
    assert leads[0]["name"] == "Ana López"
    assert leads[0]["company"] == "Acme SRL"
    assert leads[0]["domain"] == "acme.io"      # limpió https:// y la barra
    assert leads[0]["size"] == "250"            # columna única de tamaño


def test_parse_any_csv_end_to_end():
    csv_text = ("first,last,Position,Organization\n"
                "Maxi,R,CFO,Lemon\n")
    leads = qualify.parse_sales_nav_csv(csv_text)
    assert leads[0]["title"] == "CFO"
    assert leads[0]["company"] == "Lemon"
    assert leads[0]["name"] == "Maxi R"          # arma name de first+last


def test_leads_to_csv_roundtrip():
    leads = [{"tier": "A", "name": "X", "company": "Acme", "reason": "fit", "title": "CFO"}]
    out = qualify.leads_to_csv(leads)
    assert out.splitlines()[0].startswith("tier,name,title,company")
    assert "A,X,CFO,Acme" in out.replace("\r", "")


class _Block:
    def __init__(self, t): self.type, self.text = "text", t


class _Resp:
    def __init__(self, payload): self.content = [_Block(json.dumps(payload))]


class _FakeClient:
    def __init__(self, payload):
        self._p = payload
        self.calls = []

    class _M:
        def __init__(self, outer):
            self.outer = outer

        def create(self, **kw):
            self.outer.calls.append(kw)
            return _Resp(self.outer._p)

    @property
    def messages(self):
        return _FakeClient._M(self)


def test_qualify_lead_uses_rubric_and_returns_tier():
    client = _FakeClient({"tier": "A", "reason": "CFO de fintech."})
    lead = {"name": "Maxi", "title": "CFO", "company": "Lemon Cash"}
    out = qualify.qualify_lead(lead, "rúbrica…", "value prop", client)
    assert out["tier"] == "A"
    assert out["reason"] == "CFO de fintech."
    assert out["name"] == "Maxi"  # preserva el lead
    call = client.calls[0]
    assert "rúbrica" in call["system"]
    assert call["output_config"]["format"]["type"] == "json_schema"


def test_qualify_batch_maps_by_index_and_caches():
    payload = {"results": [
        {"index": 0, "tier": "D", "reason": "no fit"},
        {"index": 1, "tier": "A", "reason": "ideal"},
    ]}
    client = _FakeClient(payload)
    leads = [{"name": "a", "company": "X"}, {"name": "b", "company": "Y"}]
    out = qualify.qualify_batch(leads, "rúbrica", "vp", client, context="ctx MS")
    # mapea por index (no por orden de llegada)
    assert out[0]["tier"] == "D" and out[1]["tier"] == "A"
    call = client.calls[0]
    # una sola llamada para toda la tanda
    assert len(client.calls) == 1
    # system va como bloque cacheable (prompt caching)
    assert isinstance(call["system"], list)
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "ctx MS" in call["system"][0]["text"]


def test_qualify_leads_batches_and_sorts():
    payload = {"results": [{"index": 0, "tier": "C", "reason": "x"},
                           {"index": 1, "tier": "A", "reason": "y"}]}
    client = _FakeClient(payload)
    leads = [{"name": "a"}, {"name": "b"}]
    out = qualify.qualify_leads(leads, "r", "", client, batch_size=10)
    assert [x["tier"] for x in out] == ["A", "C"]   # ordenado por tier
    assert len(client.calls) == 1                    # 2 leads → 1 tanda
