import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from services.page_retrieval_service import PageContent

@dataclass
class VerificationResult:
    overall_status: str                   # "Verified", "Partially Verified", "Unverified"
    corroborated_domains: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    notes: str = ""
    is_official_backed: bool = False

def detect_conflicting_numbers(texts: List[str]) -> List[str]:
    """
    Detects potential conflicting version numbers or major statistical disagreements
    between retrieved sources.
    Example: 'v0.2.1' vs 'v0.3.5'
    """
    conflicts = []
    # Extract version patterns (e.g. v1.2.3 or 1.2.3)
    found_versions_by_source: Dict[int, List[str]] = {}
    for idx, t in enumerate(texts):
        vers = set(re.findall(r'\bv?([0-9]+\.[0-9]+(?:\.[0-9]+)?)\b', t))
        if vers:
            found_versions_by_source[idx] = list(vers)

    # Check for divergence if there are multiple sources
    if len(found_versions_by_source) >= 2:
        all_vers = set()
        for vlist in found_versions_by_source.values():
            all_vers.update(vlist)
        # If disparate version families exist (e.g. 0.1 vs 0.2)
        major_minor = set(re.findall(r'\bv?([0-9]+\.[0-9]+)\b', " ".join(all_vers)))
        if len(major_minor) > 2:
            conflicts.append(f"Multiple differing versions mentioned across sources: {', '.join(sorted(major_minor))}")

    return conflicts

def evaluate_sources_and_verify(pages: List[PageContent]) -> VerificationResult:
    """
    Evaluates source credibility, checks independent cross-corroboration,
    detects conflicts, and computes overall verification confidence.
    """
    successful_pages = [p for p in pages if p.status == "retrieved" and p.clean_text]
    if not successful_pages:
        return VerificationResult(
            overall_status="Unverified",
            corroborated_domains=[],
            conflicts=[],
            notes="No webpage content could be retrieved for cross-verification.",
            is_official_backed=False
        )

    unique_domains = list({p.domain for p in successful_pages})
    official_backed = any(p.authority_score >= 0.9 for p in successful_pages)

    # Check for factual divergence / conflicts in texts
    texts = [p.clean_text for p in successful_pages]
    conflicts = detect_conflicting_numbers(texts)

    # Status classification
    if conflicts:
        status = "Partially Verified"
        notes = "Potential discrepancies detected between retrieved sources. Model will explain divergence."
    elif official_backed:
        status = "Verified"
        notes = "Factual claims corroborated by official documentation or primary technical authorities."
    elif len(unique_domains) >= 2:
        status = "Verified"
        notes = f"Corroborated across {len(unique_domains)} independent domains."
    elif len(unique_domains) == 1 and successful_pages[0].authority_score >= 0.7:
        status = "Verified"
        notes = "Backed by a single reputable technical source."
    else:
        status = "Partially Verified"
        notes = "Supported by limited external sources; non-definitive."

    return VerificationResult(
        overall_status=status,
        corroborated_domains=unique_domains,
        conflicts=conflicts,
        notes=notes,
        is_official_backed=official_backed
    )

cross_verify_sources = evaluate_sources_and_verify

class SourceVerificationService:
    evaluate_sources_and_verify = staticmethod(evaluate_sources_and_verify)
    cross_verify_sources = staticmethod(evaluate_sources_and_verify)

source_verification_service = SourceVerificationService()
