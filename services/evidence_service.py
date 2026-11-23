import re
from dataclasses import dataclass
from typing import List, Optional
from services.page_retrieval_service import PageContent
from services.source_verification_service import VerificationResult

@dataclass
class EvidenceClaim:
    claim_summary: str
    evidence_snippet: str
    source_url: str
    source_domain: str
    source_title: str
    publication_date: Optional[str]
    authority_score: float

def extract_evidence_claims(pages: List[PageContent], max_claims: int = 5) -> List[EvidenceClaim]:
    """
    Extracts key informative claims and direct evidence snippets from retrieved pages.
    """
    claims: List[EvidenceClaim] = []

    for page in pages:
        if page.status != "retrieved" or not page.clean_text:
            continue

        # Split into sentences or key bullet points
        sentences = re.split(r'(?<=[.!?])\s+|\n+', page.clean_text)
        filtered_sentences = [
            s.strip() for s in sentences
            if len(s.strip()) > 35 and not any(k in s.lower() for k in ["cookie", "privacy policy", "terms of service", "all rights reserved"])
        ]

        # Take the top 1-2 most informative sentences
        for sentence in filtered_sentences[:2]:
            claims.append(EvidenceClaim(
                claim_summary=sentence[:100] + "..." if len(sentence) > 100 else sentence,
                evidence_snippet=sentence[:250],
                source_url=page.url,
                source_domain=page.domain,
                source_title=page.title,
                publication_date=page.publication_date,
                authority_score=page.authority_score
            ))
            if len(claims) >= max_claims:
                break

        if len(claims) >= max_claims:
            break

    return claims

def package_research_context(
    query: str,
    claims: List[EvidenceClaim],
    pages: List[PageContent],
    verification: VerificationResult
) -> str:
    """
    Packages verified research findings into a strict, compact context prompt for Qwen 2.5 3B.
    Contains prompt injection fences and explicit citation mappings.
    """
    if not claims and not pages:
        return (
            "\n--- RESEARCH STATUS ---\n"
            "Live internet search was attempted, but no verifiable evidence could be retrieved.\n"
            "State clearly: 'I couldn't verify this information using the available sources.'\n"
            "-------------------------\n"
        )

    lines = [
        "\n<<<UNTRUSTED_EXTERNAL_EVIDENCE>>>",
        "--- VERIFIED RESEARCH EVIDENCE (GROUNDING CONTEXT) ---",
        f"Research Question: {query}",
        f"Verification State: {verification.overall_status} (Backed by: {', '.join(verification.corroborated_domains) or 'None'})"
    ]

    if verification.conflicts:
        lines.append("CAUTION - DETECTED SOURCE DISAGREEMENTS:")
        for c in verification.conflicts:
            lines.append(f"• {c}")

    lines.append("\nRETRIEVED SOURCE EVIDENCE:")

    for idx, page in enumerate(pages, start=1):
        if page.status != "retrieved" or not page.clean_text:
            continue

        date_str = page.publication_date if page.publication_date else "Not specified"
        authority_label = "Official/Primary" if page.authority_score >= 0.9 else "Reputable" if page.authority_score >= 0.7 else "General"

        lines.append(
            f"[{idx}] Source: {page.title} ({page.domain})\n"
            f"    URL: {page.url}\n"
            f"    Date: {date_str} | Authority: {authority_label}\n"
            f"    Evidence: \"{page.clean_text[:450]}\""
        )

    lines.append(
        "\nCRITICAL GROUNDING RULES FOR ANSWER GENERATION:\n"
        "1. Base external, temporal, or post-2024 claims strictly on the evidence above.\n"
        "2. Attach inline citations [1], [2], etc., corresponding to the sources above.\n"
        "3. Do not invent facts, release dates, versions, or URLs not present in the evidence.\n"
        "4. If sources conflict, explicitly explain the conflict.\n"
        "5. If evidence is insufficient, state: 'I couldn't verify this information using the available sources.'\n"
        "----------------------------------------------------\n"
        "<<</UNTRUSTED_EXTERNAL_EVIDENCE>>>\n"
    )

    return "\n".join(lines)

class EvidenceService:
    extract_evidence_claims = staticmethod(extract_evidence_claims)
    package_research_context = staticmethod(package_research_context)

evidence_service = EvidenceService()
