import { expect, test } from "@playwright/test";
import { registerAndLogin, uniqueEmail } from "./helpers";

/** Jumps to the consent page via the side nav, answers it, then jumps to review.
 *  Uses the nav rather than repeated "Next" clicks so the walk is deterministic
 *  and skipping the optional pages is exercised the way a real admin would. */
async function consentAndReview(page: import("@playwright/test").Page) {
  await page.getByRole("button", { name: "Compliance & consent" }).click();
  await expect(page.getByRole("heading", { name: "Compliance & consent" })).toBeVisible();

  // Resolved fresh per click: answering one question re-renders the group, which
  // detaches any element handle captured up front.
  const yes = page.getByRole("button", { name: "Yes" });
  for (let n = 0, total = await yes.count(); n < total; n += 1) {
    await yes.nth(n).click();
    await expect(yes.nth(n)).toHaveAttribute("aria-pressed", "true");
  }

  await page.getByRole("button", { name: "Review & launch" }).click();
  await expect(page.getByRole("heading", { name: "Review & launch" })).toBeVisible();
}

test.describe("Onboarding", () => {
  test("fresh admin completes the multi-form wizard and it creates real records", async ({
    page,
  }) => {
    await registerAndLogin(page, uniqueEmail("onboard"), "Onboard Admin", {
      skipOnboarding: false,
    });

    // ── Company information ────────────────────────────────────────────────
    await expect(page.getByRole("heading", { name: "Company information" })).toBeVisible();
    await expect(page.getByLabel("Company name")).toHaveValue(/Onboard Admin Realty/);
    await page.getByLabel("Head office city").fill("Bengaluru");
    await page.getByLabel("GST number").fill("29ABCDE1234F1Z5");
    await page.getByRole("button", { name: /^next$/i }).click();

    // ── Primary contact ────────────────────────────────────────────────────
    await expect(page.getByRole("heading", { name: "Primary contact" })).toBeVisible();
    await expect(page.getByLabel("Full name")).toHaveValue(/Onboard Admin/);
    await page.getByLabel("Designation").selectOption("Sales Head");
    await page.getByRole("button", { name: /^next$/i }).click();

    // ── Profile & footprint ────────────────────────────────────────────────
    await expect(page.getByRole("heading", { name: "Profile & footprint" })).toBeVisible();
    await page.getByLabel("Cities you operate in (comma-separated)").fill("Bengaluru, Pune");
    await page.getByRole("button", { name: "Residential Developer" }).click();
    await page.getByRole("button", { name: /^next$/i }).click();

    // ── Project portfolio: this is what becomes inventory ──────────────────
    await expect(page.getByRole("heading", { name: "Project portfolio" })).toBeVisible();
    await page.getByLabel("Project name").fill("Skyline Towers");
    await page.getByLabel("Locality").fill("Whitefield");
    await page.getByLabel("City").fill("Bengaluru");
    await page.getByLabel("Price range").fill("₹1.2Cr – ₹3.2Cr");
    await page.getByRole("button", { name: "2BHK", exact: true }).click();
    await page.getByRole("button", { name: "3BHK", exact: true }).click();
    await page.getByRole("button", { name: /^next$/i }).click();

    // ── Ideal customer profile ─────────────────────────────────────────────
    await expect(page.getByRole("heading", { name: "Ideal customer profile" })).toBeVisible();
    await page.getByRole("button", { name: "NRIs", exact: true }).click();
    await page.getByRole("button", { name: /^next$/i }).click();

    // ── AI lead scoring: sliders must render and be adjustable ─────────────
    await expect(page.getByRole("heading", { name: "AI lead scoring" })).toBeVisible();
    await expect(page.getByRole("slider", { name: "Budget match" })).toBeVisible();
    await page.getByLabel("Hot at or above").fill("75");

    // Everything from here is optional except consent.
    await consentAndReview(page);

    // ── Review & launch ────────────────────────────────────────────────────
    await expect(page.getByText("Projects to create")).toBeVisible();
    await expect(page.getByText("Units to create")).toBeVisible();
    await page.getByRole("button", { name: /launch workspace/i }).click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 20_000 });

    // Launch side effect: the two configurations became two separately priced
    // units — not the single "Unit-1 / 1BHK / ₹0" placeholder this used to make.
    await page.goto("/properties");
    await expect(page.getByText("Skyline Towers").first()).toBeVisible();
    await expect(page.getByText("#2BHK-01")).toBeVisible();
    await expect(page.getByText("#3BHK-01")).toBeVisible();
    await expect(page.getByText("₹1.20 Cr")).toBeVisible();
    await expect(page.getByText("₹3.20 Cr")).toBeVisible();

    // And what was filled shows on the company profile.
    await page.goto("/settings/company");
    await expect(page.getByText("Setup complete")).toBeVisible();
    await expect(page.getByLabel("Head office city")).toHaveValue("Bengaluru");
    await expect(page.getByLabel("GST number")).toHaveValue("29ABCDE1234F1Z5");
  });

  test("uploaded documents are stored, listed, and survive leaving the page", async ({
    page,
  }) => {
    await registerAndLogin(page, uniqueEmail("upload"), "Upload Admin", {
      skipOnboarding: false,
    });

    // Jump straight to the documents step via the left nav.
    await page.getByRole("button", { name: "Documents & knowledge base" }).click();
    await expect(
      page.getByRole("heading", { name: "Documents & knowledge base" })
    ).toBeVisible();

    await page.getByLabel("Upload Company logo").setInputFiles({
      name: "logo.png",
      mimeType: "image/png",
      buffer: Buffer.from("89504e470d0a1a0a-not-a-real-png-but-not-empty"),
    });

    // The file is uploaded immediately, so its name appears without a save step.
    await expect(page.getByText("logo.png")).toBeVisible({ timeout: 10_000 });

    // Navigate away and back: it must still be there, because it was really stored.
    await page.getByRole("button", { name: "Company information" }).click();
    await page.getByRole("button", { name: "Documents & knowledge base" }).click();
    await expect(page.getByText("logo.png")).toBeVisible();
  });

  test("consent is required before launching", async ({ page }) => {
    await registerAndLogin(page, uniqueEmail("consent"), "Consent Admin", {
      skipOnboarding: false,
    });

    await page.getByRole("button", { name: "Compliance & consent" }).click();
    await expect(page.getByRole("heading", { name: "Compliance & consent" })).toBeVisible();
    await page.getByRole("button", { name: /^next$/i }).click();

    await expect(page.getByText(/answer both consent questions/i)).toBeVisible();
    // Still on the consent page, not advanced.
    await expect(page.getByRole("heading", { name: "Compliance & consent" })).toBeVisible();
  });

  test("skip is not a trap and completed admins are not re-gated", async ({ page }) => {
    await registerAndLogin(page, uniqueEmail("skip"), "Skip Admin"); // skips by default
    // After skipping, navigating around the dashboard must not bounce back.
    await page.goto("/leads");
    await expect(page).toHaveURL(/\/leads/);
  });
});
