"""Data-quality and membership-roll findings (CLAUDE.md §11).

Advisory only — the tool never changes a member to resolve a finding. Findings
are computed live on every page load and never stored. Only acknowledgements
are persisted, keyed to a hash of the offending value (§11)."""

from karverktyg.findings.engine import compute_findings
from karverktyg.findings.models import Finding, FindingType, Severity

__all__ = ["Finding", "FindingType", "Severity", "compute_findings"]
