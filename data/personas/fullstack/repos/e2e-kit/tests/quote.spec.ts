import { test, expect } from '@playwright/test';

test.describe('broker quote flow', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('loads the quote form', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /quote/i })).toBeVisible();
    await expect(page.getByLabel(/first name/i)).toBeVisible();
    await expect(page.getByLabel(/last name/i)).toBeVisible();
    await expect(page.getByLabel(/email/i)).toBeVisible();
  });

  test('submits a quote request', async ({ page }) => {
    await page.getByLabel(/first name/i).fill('Test');
    await page.getByLabel(/last name/i).fill('User');
    await page.getByLabel(/email/i).fill('test.user@example.com');
    await page.getByLabel(/phone/i).fill('555-0100');

    // Select a basic coverage option.
    await page.getByRole('radio', { name: /standard/i }).check();
    await page.getByRole('button', { name: /get quote/i }).click();

    await expect(page.getByText(/thank you/i)).toBeVisible();
    await expect(page.getByText(/we will review your request/i)).toBeVisible();
  });

  test('shows validation for missing required fields', async ({ page }) => {
    await page.getByRole('button', { name: /get quote/i }).click();

    await expect(page.getByText(/first name is required/i)).toBeVisible();
    await expect(page.getByText(/last name is required/i)).toBeVisible();
    await expect(page.getByText(/email is required/i)).toBeVisible();
  });

  test('allows updating quote details before submission', async ({ page }) => {
    await page.getByLabel(/first name/i).fill('Alex');
    await page.getByLabel(/last name/i).fill('River');
    await page.getByLabel(/email/i).fill('alex.river@example.com');

    // Change the plan before submitting.
    await page.getByRole('radio', { name: /premium/i }).check();
    await expect(page.getByRole('radio', { name: /premium/i })).toBeChecked();

    await page.getByRole('button', { name: /get quote/i }).click();
    await expect(page.getByText(/thank you/i)).toBeVisible();
  });
});
