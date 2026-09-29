import { expect, test } from "@playwright/test";
import { registerAndLogin, uniqueEmail } from "./helpers";

test.describe("Landing page", () => {
  test("logged-out visitor sees the marketing page and can reach register", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: /the follow-up writes itself/i })
    ).toBeVisible();
    await expect(page.getByText("Scoring you can argue with")).toBeVisible();

    await page.getByRole("link", { name: /create a workspace/i }).click();
    await expect(page).toHaveURL(/\/register/);
  });

  test("logged-in user gets a dashboard link", async ({ page }) => {
    await registerAndLogin(page, uniqueEmail("landing"), "Landing Admin");

    await page.goto("/");
    const toDashboard = page.getByRole("link", { name: /open dashboard/i });
    await expect(toDashboard).toBeVisible();
    await toDashboard.click();
    await expect(page).toHaveURL(/\/dashboard/);
  });

  test("public surfaces stay dark even when the app theme is light", async ({ page }) => {
    // The product UI follows the user's preference; the front door does not, so
    // the auth panel and landing page cannot drift apart for a light-theme user.
    await page.addInitScript(() => localStorage.setItem("theme", "light"));
    for (const path of ["/", "/login", "/register"]) {
      await page.goto(path);
      const bg = await page.evaluate(() =>
        getComputedStyle(document.querySelector(".surface-dark")!).backgroundColor
      );
      expect(bg, `${path} should render on the dark canvas`).toBe("rgb(13, 13, 15)");
    }
  });
});
