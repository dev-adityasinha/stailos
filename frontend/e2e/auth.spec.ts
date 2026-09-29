import { expect, test } from "@playwright/test";
import { PASSWORD, uniqueEmail } from "./helpers";

test.describe("Authentication", () => {
  test("register, sign in (via onboarding), and sign out", async ({ page }) => {
    const email = uniqueEmail("auth");

    await page.goto("/register");
    await page.getByLabel("Full name").fill("E2E Test User");
    await page.getByLabel("Company name").fill("E2E Test Co");
    await page.getByLabel("Email").fill(email);
    await page.locator('input[type="password"]').fill(PASSWORD);
    await page.getByRole("button", { name: /create account/i }).click();

    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByText(/account created/i)).toBeVisible();

    await page.getByLabel("Email").fill(email);
    await page.locator('input[type="password"]').fill(PASSWORD);
    await page.getByRole("button", { name: /sign in/i }).click();

    // Fresh workspace admins land on the setup wizard first, by design.
    await expect(page).toHaveURL(/\/onboarding/);
    await page.getByText("Skip for now").click();

    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.getByText(/good (morning|afternoon|evening)/i)).toBeVisible();

    await page.getByRole("button", { name: /user menu/i }).click();
    await page.getByRole("button", { name: /sign out/i }).click();
    await expect(page).toHaveURL(/\/login/);
  });

  test("rejects wrong password", async ({ page }) => {
    const email = uniqueEmail("wrongpw");
    await page.goto("/register");
    await page.getByLabel("Full name").fill("E2E Wrong Password");
    await page.getByLabel("Company name").fill("E2E Wrong Co");
    await page.getByLabel("Email").fill(email);
    await page.locator('input[type="password"]').fill(PASSWORD);
    await page.getByRole("button", { name: /create account/i }).click();
    await expect(page).toHaveURL(/\/login/);

    await page.getByLabel("Email").fill(email);
    await page.locator('input[type="password"]').fill("WrongPassword123!");
    await page.getByRole("button", { name: /sign in/i }).click();

    await expect(page.getByText(/login failed|invalid/i)).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });
});
