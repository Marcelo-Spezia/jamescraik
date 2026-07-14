"""ICP loader and registry (§8 of the spec).

Responsibilities:
- Load an ICP YAML file and validate it against the schema.
- Manage multiple ICPs in memory (multi-ICP).
- Resolve an ICP by id + optional version.
- Reject invalid ICPs with clear, actionable errors.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from icp_engine.registry.schema import ICPDefinition, ICPStatus


class ICPLoadError(Exception):
    """Raised when an ICP file cannot be loaded or validated."""


def load_icp(path: str | Path) -> ICPDefinition:
    """Load and validate a single ICP YAML file.

    Args:
        path: Path to the YAML file.

    Returns:
        A validated ``ICPDefinition``.

    Raises:
        ICPLoadError: If the file cannot be read or fails validation.
    """
    path = Path(path)
    if not path.exists():
        raise ICPLoadError(f"ICP file not found: {path}")
    if path.suffix not in (".yaml", ".yml"):
        raise ICPLoadError(f"ICP file must be .yaml or .yml, got: {path.suffix}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ICPLoadError(f"Invalid YAML in {path.name}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ICPLoadError(f"ICP file must contain a YAML mapping, got {type(raw).__name__}")

    try:
        return ICPDefinition.model_validate(raw)
    except ValidationError as exc:
        raise ICPLoadError(
            f"ICP validation failed for {path.name}:\n{exc}"
        ) from exc


class ICPRegistry:
    """In-memory registry of loaded ICP definitions (§8).

    Supports multi-ICP: load several files, then resolve by id + version.
    """

    def __init__(self) -> None:
        # Keyed by (icp_id, version)
        self._store: dict[tuple[str, str], ICPDefinition] = {}

    def load(self, path: str | Path) -> ICPDefinition:
        """Load an ICP from a YAML file and register it.

        Returns the loaded definition.  Raises ``ICPLoadError`` on failure.
        """
        icp = load_icp(path)
        key = (icp.meta.id, icp.meta.version)
        self._store[key] = icp
        return icp

    def load_dir(self, directory: str | Path) -> list[ICPDefinition]:
        """Load all .yaml/.yml files from a directory.

        Skips files that fail validation (logs warning).
        Returns the list of successfully loaded ICPs.
        """
        directory = Path(directory)
        loaded: list[ICPDefinition] = []
        for p in sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml")):
            try:
                loaded.append(self.load(p))
            except ICPLoadError:
                # In a real system we'd log; for the POC we skip silently.
                continue
        return loaded

    def get(self, icp_id: str, version: str | None = None) -> ICPDefinition:
        """Resolve an ICP by id and optional version.

        If version is None, returns the latest version (by semver string sort).
        The motor never assumes a "default ICP" — the caller must specify (§8).

        Raises:
            KeyError: If no matching ICP is found.
        """
        if version is not None:
            key = (icp_id, version)
            if key not in self._store:
                raise KeyError(f"ICP not found: id={icp_id!r}, version={version!r}")
            return self._store[key]

        # Find all versions for this id
        candidates = {
            ver: defn
            for (cid, ver), defn in self._store.items()
            if cid == icp_id
        }
        if not candidates:
            raise KeyError(f"No ICP registered with id={icp_id!r}")

        latest_ver = sorted(candidates.keys())[-1]
        return candidates[latest_ver]

    def list_ids(self) -> list[str]:
        """Return all registered ICP ids (deduplicated, sorted)."""
        return sorted({cid for cid, _ in self._store})

    def list_versions(self, icp_id: str) -> list[str]:
        """Return all registered versions for a given ICP id, sorted ascending."""
        versions = sorted(ver for cid, ver in self._store if cid == icp_id)
        if not versions:
            raise KeyError(f"No ICP registered with id={icp_id!r}")
        return versions

    def filter_by_status(self, status: ICPStatus) -> list[ICPDefinition]:
        """Return all ICPs matching a given status."""
        return [defn for defn in self._store.values() if defn.meta.status == status]

    @property
    def count(self) -> int:
        return len(self._store)
