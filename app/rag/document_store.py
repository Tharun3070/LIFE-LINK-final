"""Trusted Clinical Document Store and Ingestion Models for LifeLink RAG."""
import hashlib
from typing import List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class ClinicalDocument(BaseModel):
    doc_id: str
    title: str
    issuing_organization: str
    source_url: str
    publication_date: str
    domain: str  # e.g., "blood_transfusion", "organ_viability", "trauma_triage"
    version: str
    checksum: Optional[str] = None
    content: str
    ingested_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def compute_checksum(self) -> str:
        """Computes SHA-256 hash of document content for version and tamper tracking."""
        return hashlib.sha256(self.content.strip().encode("utf-8")).hexdigest()


# Initial authoritative clinical guidance documents for verified healthcare retrieval
TRUSTED_CLINICAL_DOCUMENTS: List[ClinicalDocument] = [
    ClinicalDocument(
        doc_id="DOC-WHO-BTC-2021",
        title="WHO Manual on the Management, Maintenance and Use of Blood Cold Chain Equipment",
        issuing_organization="World Health Organization (WHO)",
        source_url="https://www.who.int/publications/i/item/9789240035041",
        publication_date="2021-10-15",
        domain="blood_transfusion",
        version="v2.1",
        content="""Whole blood and packed red blood cells must be stored at a temperature between +2°C and +6°C at all times.
During transit, red blood cell units must be kept in validated cold boxes maintaining temperatures between +1°C and +10°C, not exceeding 24 hours.
Fresh Frozen Plasma (FFP) must be maintained in a continuously frozen state at -25°C or colder to preserve labile clotting factors (Factor VIII and Factor V).
Platelets must be kept at +20°C to +24°C with continuous agitation and must never be refrigerated.
Transfusion of compatible blood must begin within 30 minutes of release from temperature-controlled storage and complete within 4 hours.""",
    ),
    ClinicalDocument(
        doc_id="DOC-AABB-STANDARDS-2022",
        title="AABB Standards for Blood Banks and Transfusion Services (32nd Edition)",
        issuing_organization="Association for the Advancement of Blood & Biotherapies (AABB)",
        source_url="https://www.aabb.org/standards-accreditation/standards/blood-banks",
        publication_date="2022-04-01",
        domain="blood_transfusion",
        version="32.0",
        content="""ABO and RhD typing must be performed on all recipient specimens and donor units before cellular components are issued.
O-negative packed red blood cells are considered the universal cellular donor component for emergency uncrossmatched release in critical trauma resuscitation.
AB-positive individuals are universal recipients for packed red blood cell units, but can only donate plasma universally.
Emergency release of uncrossmatched blood requires explicit clinician sign-off with retrospective crossmatch completion.
Minimum donor inter-donation interval for whole blood is 56 days (8 weeks) for male and female donors to allow adequate erythrocyte replenishment.""",
    ),
    ClinicalDocument(
        doc_id="DOC-NOTTO-ORGAN-VIABILITY-2023",
        title="National Organ & Tissue Transplant Clinical Viability and Ischemic Time Guidelines",
        issuing_organization="National Organ and Tissue Transplant Organization (NOTTO)",
        source_url="https://notto.mohfw.gov.in/guidelines-organ-viability",
        publication_date="2023-01-20",
        domain="organ_viability",
        version="v1.4",
        content="""Cold ischemic time (CIT) thresholds govern graft viability during organ preservation:
- Heart: Maximum cold ischemic time is 4 to 6 hours. Beyond 6 hours, primary graft dysfunction risk escalates substantially.
- Lung: Maximum cold ischemic time is 6 to 8 hours.
- Liver: Maximum cold ischemic time is 12 hours, with optimal outcomes achieved when warm reperfusion occurs within 8 hours.
- Kidney: Maximum cold ischemic time is 24 to 36 hours for static cold storage, extendable up to 48 hours with continuous hypothermic machine perfusion.
- Pancreas: Maximum cold ischemic time is 12 to 14 hours.
Organs must be preserved in specialized hypothermic preservation solutions (UW or Custodiol HTK) at 0°C to 4°C during all ambulance transit.""",
    ),
]
