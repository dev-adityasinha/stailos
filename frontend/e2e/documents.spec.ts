import { expect, test } from "@playwright/test";
import { registerAndLogin, uniqueEmail } from "./helpers";

test.describe("Documents", () => {
  test("workspace asset categories are reachable from the documents filter", async ({
    page,
  }) => {
    // Onboarding files uploads under categories like knowledge_base and
    // rera_certificate. If this page's vocabulary drifts from the backend's,
    // those documents exist but cannot be filtered to.
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(String(e)));

    await registerAndLogin(page, uniqueEmail("docs"), "Docs Admin");
    await page.goto("/documents");

    await expect(page.getByRole("heading", { name: "Documents" })).toBeVisible();
    await expect(page.getByText("Something went wrong")).toHaveCount(0);
    for (const category of ["knowledge_base", "rera_certificate", "logo", "kyc"]) {
      await expect(page.locator(`option[value="${category}"]`).first()).toHaveCount(1);
    }
    // Only bundle-level failures matter here; WebKit reports unrelated noise
    // for Next's RSC prefetches ("Fetch API cannot load … access control").
    expect(errors.join("\n")).not.toContain("ChunkLoadError");
  });
});
