import { expect, test } from "@playwright/test";
import { registerAndLogin, uniqueEmail } from "./helpers";

/** The API origin the app was built against. Mirrors NEXT_PUBLIC_API_BASE so
 *  this works in CI and against a locally relocated backend alike. */
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";

/** Creates a lead and returns its detail URL. */
async function createLead(page: import("@playwright/test").Page, name: string) {
  await page.goto("/leads");
  await page.getByRole("button", { name: "Add lead" }).first().click();
  await page.getByLabel("Full name").fill(name);
  await page.getByRole("textbox", { name: "Phone *" }).fill(
    `98${Date.now().toString().slice(-8)}`
  );
  await page.getByRole("button", { name: /create lead/i }).click();
  await page.getByText(name).first().click();
  await expect(page.getByRole("heading", { name })).toBeVisible();
}

test.describe("AI policy from onboarding answers", () => {
  test("declining AI consent hides the AI actions and says why", async ({ page }) => {
    await registerAndLogin(page, uniqueEmail("consent-off"), "Consent Off");
    await createLead(page, "Policy Lead");
    // Baseline: the actions are there.
    await expect(page.getByRole("button", { name: "Summarize" })).toBeVisible();

    await page.goto("/settings/company");
    const consentCard = page.locator("div").filter({ hasText: "AI usage consent" }).last();
    await consentCard.getByRole("button", { name: "No" }).last().click();
    await page.getByRole("button", { name: /save consent/i }).click();
    await expect(page.getByText("AI features are currently switched off")).toBeVisible();
    // That warning shows as soon as "No" is picked; only "Saved" means the
    // PATCH landed. Navigating before it aborts the save.
    await expect(page.getByText("Saved")).toBeVisible();

    await page.goto("/leads");
    await page.getByText("Policy Lead").first().click();
    await expect(page.getByText(/AI is switched off for this workspace/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Summarize" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Score lead" })).toHaveCount(0);
  });

  test("unticking a feature removes just that action", async ({ page }) => {
    await registerAndLogin(page, uniqueEmail("feat"), "Feature Admin");
    await createLead(page, "Feature Lead");
    await expect(page.getByRole("button", { name: "Draft follow-up" })).toBeVisible();

    await page.goto("/settings/company");
    // Selecting only lead scoring leaves follow-up drafting off.
    await page.getByRole("button", { name: "AI lead scoring", exact: true }).click();
    await page.getByRole("button", { name: /save ai features/i }).click();
    // Wait for the save to land. Navigating immediately aborts the in-flight
    // PATCH in WebKit, and the assertions below would then be testing an
    // unchanged workspace.
    await expect(page.getByText("Saved")).toBeVisible();

    await page.goto("/leads");
    await page.getByText("Feature Lead").first().click();
    await expect(page.getByRole("button", { name: "Score lead" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Draft follow-up" })).toHaveCount(0);
    // Core actions survive a narrow selection.
    await expect(page.getByRole("button", { name: "Summarize" })).toBeVisible();
  });
});

test.describe("Onboarding targets reach analytics", () => {
  test("monthly targets render with month-to-date progress", async ({ page }) => {
    await registerAndLogin(page, uniqueEmail("targets"), "Targets Admin");

    await page.goto("/analytics");
    await expect(page.getByText("This month vs target")).toHaveCount(0);

    await page.goto("/settings/company");
    await expect(page.getByText("Company profile")).toBeVisible();

    // Set the target through the wizard step the settings page doesn't expose.
    await page.evaluate(async (base) => {
      const token = localStorage.getItem("pappu_access_token");
      await fetch(`${base}/onboarding/step`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        credentials: "include",
        body: JSON.stringify({ step_id: "9", data: { monthlyLeadTarget: 4 } }),
      });
    }, API_BASE);

    await page.goto("/analytics");
    await expect(page.getByText("This month vs target")).toBeVisible();
    await expect(
      page.locator("span.font-medium").filter({ hasText: /^Leads$/ })
    ).toBeVisible();
    await expect(page.getByText("of the monthly target").first()).toBeVisible();
  });
});
