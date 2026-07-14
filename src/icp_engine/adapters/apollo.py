"""IngestionSource respaldado por Apollo.io — §12.

Trae organizaciones/personas de Apollo y las normaliza al modelo canónico (§4).
El motor de scoring NUNCA importa este módulo ni httpx: solo conoce la interfaz
`IngestionSource` (principio agnóstico a herramientas).

Endpoints usados (docs.apollo.io):
  - POST /api/v1/mixed_companies/search   (organizaciones → Account)
  - POST /api/v1/mixed_people/search      (personas + org anidada → Contact/Account)

Configurable por entorno: APOLLO_API_KEY (y opcional APOLLO_BASE_URL).
El mapeo de taxonomías (industry/seniority/department/funding/region) está
centralizado acá; si Apollo cambia un nombre de campo, se ajusta en un solo lugar.
"""

from __future__ import annotations

import os
from typing import Any

from icp_engine.adapters.base import IngestionSource
from icp_engine.canonical.enums import Department, FundingStage, Industry, Seniority
from icp_engine.canonical.models import Account, Contact

DEFAULT_BASE_URL = "https://api.apollo.io/api/v1"

# ---------------------------------------------------------------------------
# Mapeo de taxonomías Apollo -> enums canónicos (§4.3)
# ---------------------------------------------------------------------------

_INDUSTRY_MAP: dict[str, Industry] = {
    "computer software": Industry.SOFTWARE,
    "information technology & services": Industry.SOFTWARE,
    "internet": Industry.SOFTWARE,
    "financial services": Industry.FINTECH,
    "banking": Industry.FINTECH,
    "investment management": Industry.FINTECH,
    "insurance": Industry.INSURANCE,
    "hospital & health care": Industry.HEALTHTECH,
    "health, wellness & fitness": Industry.HEALTHTECH,
    "pharmaceuticals": Industry.HEALTHTECH,
    "primary/secondary education": Industry.EDUCATION_K12,
    "e-learning": Industry.EDTECH,
    "higher education": Industry.EDTECH,
    "education management": Industry.EDTECH,
    "government administration": Industry.GOVERNMENT,
    "government relations": Industry.GOVERNMENT,
    "public policy": Industry.GOVERNMENT,
    "military": Industry.GOVERNMENT,
    "defense & space": Industry.GOVERNMENT,
    "logistics & supply chain": Industry.LOGISTICS,
    "transportation/trucking/railroad": Industry.LOGISTICS,
    "telecommunications": Industry.TELECOM,
    "media production": Industry.MEDIA,
    "entertainment": Industry.MEDIA,
    "manufacturing": Industry.MANUFACTURING,
    "oil & energy": Industry.ENERGY,
    "utilities": Industry.ENERGY,
    "real estate": Industry.REAL_ESTATE,
    "retail": Industry.ECOMMERCE,
    "consumer goods": Industry.ECOMMERCE,
    "nonprofit organization management": Industry.NONPROFIT,
}

_SENIORITY_MAP: dict[str, Seniority] = {
    "owner": Seniority.C_LEVEL,
    "founder": Seniority.C_LEVEL,
    "c_suite": Seniority.C_LEVEL,
    "partner": Seniority.C_LEVEL,
    "vp": Seniority.VP,
    "head": Seniority.VP,
    "director": Seniority.DIRECTOR,
    "manager": Seniority.MANAGER,
    "senior": Seniority.IC,
    "entry": Seniority.IC,
    "intern": Seniority.IC,
}

_DEPARTMENT_MAP: dict[str, Department] = {
    "engineering": Department.ENGINEERING,
    "engineering & technical": Department.ENGINEERING,
    "information_technology": Department.ENGINEERING,
    "information technology": Department.ENGINEERING,
    "product_management": Department.PRODUCT,
    "product management": Department.PRODUCT,
    "product": Department.PRODUCT,
    "data_science": Department.DATA,
    "data science": Department.DATA,
    "analytics": Department.DATA,
    "operations": Department.OPS,
    "support": Department.OPS,
    "marketing": Department.MARKETING,
    "sales": Department.SALES,
    "business_development": Department.SALES,
    "c_suite": Department.EXEC,
    "executive": Department.EXEC,
}

_FUNDING_MAP: dict[str, FundingStage] = {
    "seed": FundingStage.SEED,
    "series a": FundingStage.SERIES_A,
    "series b": FundingStage.SERIES_B,
    "series c": FundingStage.GROWTH,
    "series d": FundingStage.GROWTH,
    "series e": FundingStage.GROWTH,
    "private equity": FundingStage.GROWTH,
    "ipo": FundingStage.PUBLIC,
    "public": FundingStage.PUBLIC,
}

# País (nombre completo, como lo devuelve Apollo) -> región del modelo.
_NA = {"United States", "Canada"}
_LATAM = {
    "Mexico", "Brazil", "Argentina", "Chile", "Colombia", "Peru", "Uruguay",
    "Ecuador", "Bolivia", "Paraguay", "Venezuela", "Costa Rica", "Panama",
    "Guatemala", "Dominican Republic",
}


def _region_from_country(country: str | None) -> str | None:
    if not country:
        return None
    if country in _NA:
        return "NA"
    if country in _LATAM:
        return "LATAM"
    return "EMEA"  # fallback grueso; refinar si se agregan ICPs de otras regiones


def _norm(value: Any) -> str:
    return str(value).strip().lower() if value is not None else ""


def map_industry(value: str | None) -> Industry | None:
    if not value:
        return None
    return _INDUSTRY_MAP.get(_norm(value), Industry.OTHER)


def map_seniority(value: str | None) -> Seniority:
    return _SENIORITY_MAP.get(_norm(value), Seniority.UNKNOWN)


def map_department(values: Any) -> Department:
    """Apollo devuelve `departments`/`functions` como lista; tomamos la primera mapeable."""
    if isinstance(values, str):
        values = [values]
    for v in values or []:
        dept = _DEPARTMENT_MAP.get(_norm(v))
        if dept is not None:
            return dept
    return Department.OTHER


def map_funding(value: str | None) -> FundingStage | None:
    if not value:
        return None
    return _FUNDING_MAP.get(_norm(value), FundingStage.UNKNOWN)


# ---------------------------------------------------------------------------
# Mapeo payload Apollo -> modelo canónico
# ---------------------------------------------------------------------------

def org_to_account(org: dict[str, Any]) -> Account:
    """Normaliza una organización de Apollo a un Account canónico (§4.1)."""
    country = org.get("country")
    revenue = org.get("annual_revenue") or org.get("organization_revenue")
    return Account(
        account_id=str(org.get("id", "")),
        name=org.get("name", "") or "(sin nombre)",
        domain=org.get("primary_domain") or org.get("website_url"),
        industry=map_industry(org.get("industry")),
        employee_count=org.get("estimated_num_employees"),
        revenue_usd=int(revenue) if revenue else None,
        country=country,
        region=_region_from_country(country),
        founded_year=org.get("founded_year"),
        funding_stage=map_funding(org.get("latest_funding_stage")),
        tech_stack=[str(t) for t in org.get("technology_names", []) or []],
        source="apollo",
        raw=org,
    )


def person_to_contact(person: dict[str, Any], account_id: str | None = None) -> Contact:
    """Normaliza una persona de Apollo a un Contact canónico (§4.2)."""
    org = person.get("organization") or {}
    acc_id = account_id or str(org.get("id") or person.get("organization_id") or "")
    full_name = person.get("name") or " ".join(
        x for x in [person.get("first_name"), person.get("last_name")] if x
    )
    return Contact(
        contact_id=str(person.get("id", "")),
        account_id=acc_id,
        full_name=full_name or "(sin nombre)",
        title=person.get("title"),
        seniority=map_seniority(person.get("seniority")),
        department=map_department(person.get("departments") or person.get("functions")),
        country=person.get("country"),
        linkedin_url=person.get("linkedin_url"),
        email=person.get("email"),
        source="apollo",
        raw=person,
    )


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class ApolloIngestionSource(IngestionSource):
    """Trae cuentas/contactos de Apollo y los normaliza al modelo canónico.

    Args:
        api_key: API key de Apollo. Default: env APOLLO_API_KEY.
        base_url: override del host. Default: env APOLLO_BASE_URL o el oficial.
        client: httpx.AsyncClient inyectable (para tests; no se cierra acá).
        auth_header: nombre del header de auth. Apollo documenta ``X-Api-Key``.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        client: Any | None = None,
        auth_header: str = "X-Api-Key",
    ) -> None:
        self.api_key = api_key or os.getenv("APOLLO_API_KEY")
        self.base_url = (base_url or os.getenv("APOLLO_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.auth_header = auth_header
        self._client = client  # si es None se crea uno por request

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise RuntimeError(
                "Falta la API key de Apollo. Seteá APOLLO_API_KEY (o pasá api_key=)."
            )
        return {
            self.auth_header: self.api_key,
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
        }

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        if self._client is not None:
            resp = await self._client.post(url, headers=self._headers(), json=body)
            resp.raise_for_status()
            return resp.json()
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - depende del extra
            raise ImportError(
                'El adapter ApolloIngestionSource requiere httpx. '
                'Instalá el extra: pip install -e ".[apollo]"'
            ) from exc
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=self._headers(), json=body)
            resp.raise_for_status()
            return resp.json()

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        if self._client is not None:
            resp = await self._client.get(url, headers=self._headers(), params=params)
            resp.raise_for_status()
            return resp.json()
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - depende del extra
            raise ImportError(
                'El adapter ApolloIngestionSource requiere httpx. '
                'Instalá el extra: pip install -e ".[apollo]"'
            ) from exc
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=self._headers(), params=params)
            resp.raise_for_status()
            return resp.json()

    async def enrich_account_by_domain(self, domain: str) -> Account | None:
        """Organization Enrichment → Account con firmográficos ricos (industry,
        estimated_num_employees, technology_names, etc.). El search devuelve
        objetos livianos; este endpoint completa los datos que el scoring necesita."""
        if not domain:
            return None
        data = await self._get("organizations/enrich", {"domain": domain})
        org = data.get("organization")
        return org_to_account(org) if org else None

    async def fetch_accounts(self, **params: Any) -> list[Account]:
        """Organization Search → lista de Account. params = filtros de Apollo."""
        body = {"page": 1, "per_page": 25, **params}
        data = await self._post("mixed_companies/search", body)
        orgs = data.get("organizations") or data.get("accounts") or []
        return [org_to_account(o) for o in orgs]

    async def build_companies(self, limit: int = 25, **params: Any) -> list[Account]:
        """Armado de EMPRESAS: Organization Search (descubrir) → enrich por dominio
        (datos ricos: industry, empleados, tech) → lista de Account scoreables.

        El search es gratis; el enrich consume créditos. `limit` acota cuántas se
        enriquecen.
        """
        body = {"page": 1, "per_page": max(limit, 5), **params}
        data = await self._post("mixed_companies/search", body)
        orgs = data.get("organizations") or data.get("accounts") or []
        accounts: list[Account] = []
        for o in orgs[:limit]:
            light = org_to_account(o)
            enriched = (await self.enrich_account_by_domain(light.domain)
                        if light.domain else None)
            accounts.append(enriched or light)
        return accounts

    async def match_lead(self, **identifiers: Any) -> tuple[Account, Contact] | None:
        """People Enrichment (`/people/match`) → par (Account, Contact) completo.

        Dado un contacto conocido (ej. first_name+last_name+domain, o email), Apollo
        devuelve la persona enriquecida (título, seniority, departamento, email,
        linkedin) JUNTO con su organización enriquecida. Es el flujo del SDR:
        'tengo un nombre y una empresa' → lead completo listo para scorear.
        """
        data = await self._post("people/match", identifiers)
        person = data.get("person")
        if not person:
            return None
        org = person.get("organization") or {}
        account = org_to_account(org)
        contact = person_to_contact(person, account_id=account.account_id)
        return account, contact

    async def search_people_ids(self, **params: Any) -> list[str]:
        """People API Search (net-new prospecting) → lista de ids de Apollo.

        Usa `mixed_people/api_search` (requiere master key). Es el descubrimiento
        de contactos que matchean el ICP; NO gasta créditos y devuelve registros
        livianos (sin nombre/email/seniority). Para datos completos → `match_lead`.
        """
        body = {"page": 1, "per_page": 25, **params}
        data = await self._post("mixed_people/api_search", body)
        people = data.get("people") or data.get("contacts") or []
        return [str(p["id"]) for p in people if p.get("id")]

    async def build_leads(
        self, limit: int = 25, **search_params: Any
    ) -> list[tuple[Account, Contact]]:
        """Armado de listas end-to-end: People Search (descubrir) → People Match
        (enriquecer cada id) → pares (Account, Contact) completos y scoreables.

        OJO: el search es gratis, pero cada enrich consume créditos de Apollo.
        `limit` acota cuántos ids se enriquecen.
        """
        ids = await self.search_people_ids(**search_params)
        pairs: list[tuple[Account, Contact]] = []
        for pid in ids[:limit]:
            pair = await self.match_lead(id=pid)
            if pair is not None:
                pairs.append(pair)
        return pairs

    async def fetch_contacts(self, **params: Any) -> list[Contact]:
        """People API Search → lista de Contact (registros livianos; para datos
        completos usar `build_leads`/`match_lead`)."""
        body = {"page": 1, "per_page": 25, **params}
        data = await self._post("mixed_people/api_search", body)
        people = data.get("people") or data.get("contacts") or []
        return [person_to_contact(p) for p in people]

    async def fetch_leads(self, **params: Any) -> list[tuple[Account, Contact]]:
        """People Search → pares (Account, Contact) usando la org anidada de cada
        persona. Es la primitiva natural para armar listas y scorearlas (no es
        parte de la interfaz IngestionSource; conveniencia del lead-gen)."""
        body = {"page": 1, "per_page": 25, **params}
        data = await self._post("mixed_people/search", body)
        people = data.get("people") or data.get("contacts") or []
        pairs: list[tuple[Account, Contact]] = []
        for p in people:
            org = p.get("organization") or {}
            account = org_to_account(org)
            contact = person_to_contact(p, account_id=account.account_id)
            pairs.append((account, contact))
        return pairs
