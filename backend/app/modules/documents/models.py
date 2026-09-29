"""Document management with immutable version history (Task 18)."""
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin

DOCUMENT_CATEGORIES = [
    # Deal documents, attached to a lead / customer / booking.
    "kyc", "agreement", "payment_receipt", "booking_form", "brochure",
    "floor_plan", "legal",
    # Workspace documents collected during onboarding (§16 and §17 of
    # AI_Developer_Onboarding_Form.md). These attach to the tenant, not a deal.
    "logo", "brand_guidelines", "price_sheet", "master_plan", "rera_certificate",
    "company_profile", "sales_deck", "video",
    # "knowledge_base" is what the AI agents are allowed to ground answers in —
    # FAQs, sales scripts, payment plans, project specs (§17).
    "knowledge_base",
    "other",
]

# Categories that describe the workspace itself rather than a specific deal.
WORKSPACE_CATEGORIES = {
    "logo", "brand_guidelines", "price_sheet", "master_plan", "rera_certificate",
    "company_profile", "sales_deck", "video", "knowledge_base", "brochure",
    "floor_plan",
}


class Document(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "documents"

    title: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(30), default="other", index=True)
    entity_type: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    current_version: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", lazy="selectin",
        order_by="DocumentVersion.version_number",
    )


class DocumentVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "document_versions"

    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    version_number: Mapped[int] = mapped_column(default=1)
    filename: Mapped[str] = mapped_column(String(300))
    stored_path: Mapped[str] = mapped_column(String(500))
    size: Mapped[int] = mapped_column(default=0)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    uploaded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    document: Mapped[Document] = relationship(back_populates="versions")
