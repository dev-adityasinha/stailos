import { expect, test } from "@playwright/test";
import { registerAndLogin, uniqueEmail } from "./helpers";

test.describe("Lead lifecycle", () => {
  test("create a lead and move it through the pipeline", async ({ page }) => {
    await registerAndLogin(page, uniqueEmail("leads"), "E2E Leads Admin");

    const leadName = `Playwright Lead ${Date.now()}`;
    await page.goto("/leads?new=1");
    await page.getByLabel("Full name *").fill(leadName);
    await page.getByLabel("Phone *").fill("9876500000");
    await page.getByRole("button", { name: /create lead/i }).click();

    await expect(page.getByText(leadName)).toBeVisible({ timeout: 10_000 });

    await page.getByText(leadName).click();
    await expect(page).toHaveURL(/\/leads\/.+/);
    await expect(page.getByRole("heading", { name: leadName })).toBeVisible();

    await page.getByLabel("Change stage").selectOption("contacted");
    await expect(page.getByLabel("Change stage")).toHaveValue("contacted");

    await page.goto("/pipeline");
    await expect(page.getByText(leadName)).toBeVisible();
  });

  test("duplicate phone number is blocked with a warning", async ({ page }) => {
    await registerAndLogin(page, uniqueEmail("dupes"), "E2E Dupes Admin");

    await page.goto("/leads?new=1");
    await page.getByLabel("Full name *").fill("First Lead");
    await page.getByLabel("Phone *").fill("9876511111");
    await page.getByRole("button", { name: /create lead/i }).click();
    await expect(page.getByText("First Lead")).toBeVisible({ timeout: 10_000 });

    await page.getByRole("button", { name: /add lead/i }).click();
    await page.getByLabel("Full name *").fill("Second Lead Same Phone");
    await page.getByLabel("Phone *").fill("9876511111");
    await page.getByRole("button", { name: /create lead|checking/i }).click();

    await expect(page.getByText("Possible duplicate lead")).toBeVisible();
  });
});
