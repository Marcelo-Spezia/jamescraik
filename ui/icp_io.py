"""Lógica de I/O del editor de ICP (sin Streamlit, testeable).

Carga/valida/versiona/guarda archivos ICP YAML. La validación usa el mismo
schema del registry (§5/§8): un ICP inválido NO se guarda. La app Streamlit
(app.py) es una cáscara fina sobre estas funciones.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml

from icp_engine.registry.schema import ICPDefinition

# Ops cuyo `value` es una lista.
_LIST_OPS = {"in", "not_in", "contains_any", "between"}


def list_icps(icp_dir: str | Path) -> list[Path]:
    """Devuelve los archivos .yaml de la carpeta de ICPs, ordenados."""
    d = Path(icp_dir)
    if not d.exists():
        return []
    return sorted(p for p in d.glob("*.yaml"))


def load_icp_dict(path: str | Path) -> dict[str, Any]:
    """Carga un ICP YAML como dict crudo (preserva la estructura para editar)."""
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def validate_icp_dict(data: dict[str, Any]) -> tuple[bool, str | None]:
    """Valida el dict contra el schema del registry. (ok, error_legible)."""
    try:
        ICPDefinition(**data)
        return True, None
    except Exception as exc:  # pydantic ValidationError u otros
        return False, str(exc)


def save_icp_dict(data: dict[str, Any], path: str | Path) -> None:
    """Valida y, si pasa, escribe el YAML. Rechaza inválidos (§8)."""
    ok, err = validate_icp_dict(data)
    if not ok:
        raise ValueError(f"ICP inválido, no se guarda: {err}")
    Path(path).write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def bump_version(version: str, level: str) -> str:
    """Sube la versión semver. level ∈ {patch, minor, major} (§9)."""
    try:
        major, minor, patch = (int(x) for x in version.split("."))
    except ValueError as exc:
        raise ValueError(f"versión semver inválida: {version!r}") from exc
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    if level == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"level inválido: {level!r}")


def apply_version_bump(
    data: dict[str, Any], level: str, note: str, today: date
) -> dict[str, Any]:
    """Sube la versión y agrega una entrada de changelog (obligatoria, §9)."""
    meta = data.setdefault("meta", {})
    new_version = bump_version(str(meta.get("version", "0.0.0")), level)
    meta["version"] = new_version
    meta["updated"] = today.isoformat()
    changelog = meta.setdefault("changelog", [])
    changelog.append({"version": new_version, "date": today.isoformat(), "note": note})
    return data


# ---------------------------------------------------------------------------
# Conversión value <-> celda de tabla (para el data_editor de Streamlit)
# ---------------------------------------------------------------------------

def _auto_type(token: str) -> Any:
    token = token.strip()
    for cast in (int, float):
        try:
            return cast(token)
        except ValueError:
            continue
    return token


def value_to_cell(value: Any) -> str:
    """Representa el `value` de un criterio como string editable."""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return "" if value is None else str(value)


def cell_to_value(cell: str, op: str) -> Any:
    """Parsea la celda de vuelta a value, según el op (lista vs escalar)."""
    tokens = [_auto_type(t) for t in str(cell).split(",") if t.strip() != ""]
    if op in _LIST_OPS:
        return tokens
    return tokens[0] if tokens else ""
