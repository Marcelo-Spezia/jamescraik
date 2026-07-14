"""ICP Registry — carga, validación y gestión de ICPs (§5, §8)."""

from icp_engine.registry.loader import ICPRegistry, load_icp
from icp_engine.registry.schema import ICPDefinition

__all__ = ["ICPDefinition", "ICPRegistry", "load_icp"]
