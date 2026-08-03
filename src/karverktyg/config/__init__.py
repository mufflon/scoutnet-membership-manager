"""
Kår configuration: brackets, avdelningar and uppflyttning rules (§13, §17).

Configuration, not code — loaded from a JSON document (mountable as a
Kubernetes ConfigMap) and validated into typed models.
"""

from karverktyg.config.loader import ConfigError, load_config
from karverktyg.config.models import (
    Avdelning,
    Bracket,
    BracketRule,
    ExpectedPost,
    KarConfig,
    TransitionKind,
    bracket_by_unit_type_code,
    unit_type_code,
)

__all__ = [
    "Avdelning",
    "Bracket",
    "BracketRule",
    "ConfigError",
    "ExpectedPost",
    "KarConfig",
    "TransitionKind",
    "bracket_by_unit_type_code",
    "load_config",
    "unit_type_code",
]
