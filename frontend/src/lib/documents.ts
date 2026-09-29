/** Document category vocabulary, mirroring DOCUMENT_CATEGORIES in
 *  backend/app/modules/documents/models.py.
 *
 *  The second group is the workspace assets the onboarding wizard uploads
 *  (logo, RERA certificate, AI knowledge base…). They live in their own module
 *  so the documents page and the setup wizard share a single list. */
export const DOCUMENT_CATEGORIES = [
  "kyc", "agreement", "payment_receipt", "booking_form", "brochure",
  "floor_plan", "legal",
  "logo", "brand_guidelines", "price_sheet", "master_plan", "rera_certificate",
  "company_profile", "sales_deck", "video", "knowledge_base",
  "other",
];

export const DOCUMENT_CATEGORY_COLORS: Record<string, string> = {
  kyc: "#f59e0b", agreement: "#3b82f6", payment_receipt: "#10b981",
  booking_form: "#06b6d4", brochure: "#8b5cf6", floor_plan: "#ec4899",
  legal: "#ef4444",
  logo: "#6366f1", brand_guidelines: "#a855f7", price_sheet: "#14b8a6",
  master_plan: "#0ea5e9", rera_certificate: "#f43f5e", company_profile: "#64748b",
  sales_deck: "#eab308", video: "#d946ef", knowledge_base: "#22c55e",
  other: "#8b98ac",
};

/** Mirrors ALLOWED_EXTENSIONS in backend/app/core/storage.py. */
export const DOCUMENT_UPLOAD_ACCEPT =
  ".pdf,.png,.jpg,.jpeg,.webp,.doc,.docx,.xls,.xlsx,.csv,.txt,.ppt,.pptx,.mp4,.mov,.webm";
