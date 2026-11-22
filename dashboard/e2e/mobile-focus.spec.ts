import { test, expect } from "@playwright/test";

test("mobile back navigation returns keyboard focus to the session list", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/?demo=1");
  const back = page.getByRole("button", { name: "← Sessions", exact: true });
  const list = page.getByRole("complementary", { name: "Sessions" });
  const search = page.getByRole("searchbox", { name: "Search sessions" });
  await expect(list).toBeHidden();

  await back.focus();
  await page.keyboard.press("Enter");
  await expect(list).toBeVisible();
  await expect(page.locator("body")).not.toBeFocused();
  await expect(list).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(search).toBeFocused();
  await page.keyboard.type("design-tokens");
  await expect(page.locator(".session-row")).toHaveCount(1);

  const row = page.locator(".session-row");
  await row.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "web / design-tokens" })).toBeVisible();
  await expect(list).toBeHidden();
  await back.click();
  await expect(list).toBeFocused();
  await expect(search).toHaveValue("design-tokens");
  await expect(row).toHaveCount(1);
});
