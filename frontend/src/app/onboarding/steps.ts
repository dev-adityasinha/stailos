/* Onboarding wizard definition.
 *
 * Step `key` values are the API's step ids and MUST match
 * backend/app/modules/onboarding/schemas.py::ONBOARDING_STEPS. They are
 * deliberately non-sequential: "1", "2", "4", "7" and "11" predate this
 * expansion (they came from the StailOS wizard and drive
 * onboarding/service.py's completion side effects), so they keep their original
 * meaning and any workspace part-way through setup keeps its saved answers. New
 * pages take suffixed ("1b", "1c") or previously unused numbers.
 *
 * Every option list below is transcribed from the form specs in the repo root —
 * the file each one comes from is named above it, so the two stay traceable.
 */

export interface StepMeta {
  key: string;
  title: string;
  sub: string;
  /** Shown in the left nav; groups the 12 pages into four phases. */
  group: "Company" | "Inventory" | "AI setup" | "Go live";
  /** Steps the user can leave entirely blank and still launch. */
  optional?: boolean;
}

export const STEPS: StepMeta[] = [
  { key: "1", group: "Company", title: "Company information",
    sub: "Legal identity, registrations, and where you are headquartered." },
  { key: "1b", group: "Company", title: "Primary contact",
    sub: "Who we escalate to. This also renames your own account." },
  { key: "1c", group: "Company", title: "Profile & footprint",
    sub: "Scale, what you build, and the cities you sell in." },
  { key: "2", group: "Inventory", title: "Project portfolio",
    sub: "Each project becomes real inventory when you launch." },
  { key: "4", group: "AI setup", title: "Ideal customer profile",
    sub: "Who buys from you — this grounds every AI suggestion." },
  { key: "5", group: "AI setup", title: "AI lead scoring",
    sub: "The rubric the scoring engine applies to every lead." },
  { key: "6", group: "AI setup", title: "AI features & integrations",
    sub: "Which AI surfaces you want switched on.", optional: true },
  { key: "7", group: "Go live", title: "Import your pipeline",
    sub: "Bring existing leads and customers in from CSV.", optional: true },
  { key: "8", group: "Go live", title: "Documents & knowledge base",
    sub: "Brand assets, brochures, and what the AI may quote.", optional: true },
  { key: "9", group: "Go live", title: "Sales process & targets",
    sub: "Your SLAs and the numbers you are measured on.", optional: true },
  { key: "11", group: "Go live", title: "Invite your team",
    sub: "Each invitee sets their own password.", optional: true },
  { key: "12", group: "Go live", title: "Compliance & consent",
    sub: "Required before AI features touch customer data." },
];

export const REVIEW_STEP = STEPS.length; // zero-based index of the review page

/* ── AI_Developer_Onboarding_Form.md §2 ─────────────────────────────────── */
export const DESIGNATIONS = [
  "Chairman", "Managing Director", "CEO", "Director", "Sales Head",
  "Marketing Head", "CRM Head", "Business Development Head", "Other",
];
export const CONTACT_CHANNELS = ["WhatsApp", "Phone Call", "Email"];

/* ── AI_Developer_Onboarding_Form.md §4 ─────────────────────────────────── */
export const BUSINESS_TYPES = [
  "Residential Developer", "Commercial Developer", "Mixed Use Developer",
  "Plotted Development", "Luxury Housing", "Affordable Housing", "Villas",
  "Farmhouses", "Industrial Parks", "Warehousing", "Hospitality",
  "Township Developer", "Redevelopment Projects",
];

/* ── AI_Developer_Onboarding_Form.md §11 ────────────────────────────────── */
export const PROPERTY_TYPES = [
  "Apartments", "Villas", "Plots", "Farmhouses", "Commercial Shops",
  "Office Spaces", "Retail", "Warehouses", "Industrial",
];

/* ── AI_Developer_Onboarding_Form.md §7 ─────────────────────────────────── */
export const LEAD_SOURCES = [
  "Meta Ads", "Google Ads", "Organic", "Referral", "Brokers",
  "Channel Partners", "Walk-ins", "Events", "WhatsApp", "Email",
];

/* ── AI_Property_Information_Form.md §2, §4, §8 ─────────────────────────── */
export const PROJECT_STATUSES = [
  { value: "pre_launch", label: "Pre-launch" },
  { value: "launched", label: "Launched" },
  { value: "under_construction", label: "Under construction" },
  { value: "nearing_possession", label: "Nearing possession" },
  { value: "ready_to_move", label: "Ready to move" },
  { value: "sold_out", label: "Sold out" },
];
export const CONFIGURATIONS = [
  "Studio", "1BHK", "2BHK", "3BHK", "4BHK", "5BHK", "Villa", "Plot", "Office", "Shop",
];
export const AMENITIES = [
  "Clubhouse", "Swimming pool", "Gym", "EV charging", "Kids' play area",
  "24x7 security", "Gated community", "Smart home", "Green spaces",
  "Metro connectivity", "Large balcony", "Lake view",
];

/* ── AI_Ideal_Customer_Profile.md §1, §4, §5, §9, §12, §13, §14 ─────────── */
export const BUYER_SEGMENTS = [
  "First home buyers", "Investors", "NRIs", "HNIs", "UHNIs", "CXOs",
  "Startup founders", "Doctors", "Lawyers", "Government employees",
  "IT professionals", "Business owners", "Manufacturers",
];
export const OCCUPATIONS = [
  "Founder", "CEO", "CTO", "CFO", "Director", "Vice President", "Business owner",
  "Investor", "Software engineer", "IT professional", "Doctor", "Lawyer",
  "Chartered accountant", "Consultant", "Government officer", "Banker",
  "Industrialist", "Freelancer",
];
export const INDUSTRIES = [
  "Information technology", "SaaS", "Finance", "Banking", "Healthcare", "Pharma",
  "Manufacturing", "Automobile", "Consulting", "Education", "Government",
  "Construction", "Real estate", "FMCG", "Retail", "Hospitality", "Logistics",
  "Aviation", "Energy",
];
export const PURCHASE_TIMELINES = [
  "Immediate", "Within 3 months", "Within 6 months", "Within 1 year",
  "Just researching",
];
export const BUYING_PURPOSES = [
  "Investment", "End use", "Retirement", "Vacation home", "Rental income",
  "Tax benefits", "Portfolio diversification",
];
export const PURCHASE_TRIGGERS = [
  "High ROI", "Appreciation potential", "Rental yield", "Tax saving",
  "Exclusive community", "Lifestyle upgrade", "Family needs",
  "Retirement planning", "Limited inventory", "Prestige",
];
export const PAIN_POINTS = [
  "Trust issues", "Builder reputation", "Financing", "Hidden charges",
  "Poor connectivity", "Delayed possession", "Low appreciation",
  "Lack of transparency", "Documentation", "Legal risk", "Resale liquidity",
];
export const OBJECTIONS = [
  "Too expensive", "Wrong location", "Better alternatives",
  "Waiting for market correction", "Financing issues", "Family not convinced",
  "Need more time", "Already invested elsewhere",
];

/* ── AI_Lead_Generation_Configuration_Form.md §8 ────────────────────────────
 * These six keys are the scoring dimensions the backend actually implements
 * (backend/app/modules/ai/grading.py::DEFAULT_WEIGHTS). Sliders are 0–100 and
 * the backend renormalises them, so the numbers are relative importance, not
 * percentages that must sum to anything.
 */
export const SCORING_DIMENSIONS = [
  { key: "budget", label: "Budget match",
    hint: "Does their budget reach your entry price?" },
  { key: "intent", label: "Buying intent",
    hint: "Pipeline stage and stated timeline." },
  { key: "geography", label: "Geographic match",
    hint: "Is their preferred area inside your footprint?" },
  { key: "property_fit", label: "Property preference",
    hint: "Do you actually stock what they want?" },
  { key: "engagement", label: "Engagement",
    hint: "Logged calls, visits, and notes." },
  { key: "contactability", label: "Contactability",
    hint: "Do we have a phone number and an email?" },
];

export const DEFAULT_WEIGHTS: Record<string, number> = {
  budget: 25, intent: 25, geography: 15, property_fit: 15,
  engagement: 10, contactability: 10,
};

/* ── AI_Developer_Onboarding_Form.md §10 ────────────────────────────────── */
export const AI_FEATURE_GROUPS = [
  { key: "salesAi", label: "Sales AI",
    options: ["AI lead scoring", "AI follow-up", "AI calling assistant",
              "AI WhatsApp assistant", "AI email assistant", "AI meeting scheduler"] },
  { key: "marketingAi", label: "Marketing AI",
    options: ["AI ad generator", "AI landing page generator", "AI creative generator",
              "AI campaign optimizer", "AI audience discovery"] },
  { key: "analyticsAi", label: "Analytics AI",
    options: ["Revenue forecasting", "Sales prediction", "Customer segmentation",
              "Market insights", "ROI prediction"] },
  { key: "customerAi", label: "Customer intelligence",
    options: ["Buyer persona creation", "Affordability prediction",
              "Buying intent detection", "Property recommendation"] },
];

/* ── AI_Developer_Onboarding_Form.md §15 ────────────────────────────────── */
export const INTEGRATIONS = [
  "WhatsApp Business", "Email / SMTP", "Website forms", "Meta Ads", "Google Ads",
  "Google Analytics", "Payment gateway", "SMS gateway", "Call tracking",
];

/* ── AI_Developer_Onboarding_Form.md §16–§17 ────────────────────────────────
 * `category` values must exist in
 * backend/app/modules/documents/models.py::DOCUMENT_CATEGORIES — the upload
 * endpoint rejects anything else with `invalid_category`.
 */
export const DOCUMENT_SLOTS = [
  { category: "logo", label: "Company logo", accept: ".png,.jpg,.jpeg,.webp" },
  { category: "brand_guidelines", label: "Brand guidelines", accept: ".pdf,.doc,.docx" },
  { category: "brochure", label: "Project brochures", accept: ".pdf" },
  { category: "price_sheet", label: "Price sheets", accept: ".pdf,.xls,.xlsx,.csv" },
  { category: "master_plan", label: "Master plans", accept: ".pdf,.png,.jpg,.jpeg" },
  { category: "floor_plan", label: "Floor plans", accept: ".pdf,.png,.jpg,.jpeg" },
  { category: "rera_certificate", label: "RERA certificate", accept: ".pdf" },
  { category: "company_profile", label: "Company profile", accept: ".pdf,.doc,.docx" },
  { category: "sales_deck", label: "Sales deck", accept: ".pdf,.ppt,.pptx" },
  { category: "video", label: "Videos / drone footage", accept: ".mp4,.mov,.webm" },
];

export const KNOWLEDGE_BASE_HINT = [
  "FAQs", "Sales scripts", "Pricing and payment plans", "Competitor comparisons",
  "Project specifications", "Loan information", "Customer testimonials",
];

/* ── AI_Developer_Onboarding_Form.md §18 ────────────────────────────────── */
export const INVITE_ROLES = ["Admin", "Manager", "Sales", "Marketing", "CRM", "Support"];
