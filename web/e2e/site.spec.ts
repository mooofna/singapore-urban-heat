import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => {
    if (m.type() === 'error' && !/tiles\.openfreemap\.org|Failed to load resource/.test(m.text())) {
      errors.push(m.text());
    }
  });
  return errors;
}

async function seriousA11yViolations(page: Page) {
  const result = await new AxeBuilder({ page }).exclude('.maplibregl-canvas').analyze();
  return result.violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${v.id}: ${v.nodes.length} nodes`);
}

test('explorer renders the map and switches layers', async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /ground runs hot/i })).toBeVisible();
  await expect(page.locator('.maplibregl-canvas')).toBeVisible();
  await expect(page.getByText(/clear Landsat 8 and 9 scenes/)).toBeVisible();
  await page.getByRole('combobox', { name: 'Layer' }).selectOption('ndvi');
  await expect(page.getByText('Median NDVI of clear land pixels')).toBeVisible();
  await expect(page).toHaveURL(/layer=ndvi/);
  expect(errors).toEqual([]);
});

test('a zone from the URL opens its details and time series', async ({ page, request }) => {
  const cols = await (await request.get('/data/zones/r200.json')).json();
  const n: number[] = cols.n_obs;
  const index = n.indexOf(Math.max(...n));
  const id: string = cols.id[index];
  await page.goto(`/?zone=${encodeURIComponent(id)}`);
  const detail = page.getByRole('complementary', { name: 'Zone details' });
  await expect(detail).toBeVisible();
  await expect(detail.getByText('Relative heat', { exact: true })).toBeVisible();
  await expect(detail.locator('svg').first()).toBeVisible();
});

test('single scene mode shows the timeline', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Single scene' }).click();
  await expect(page.getByRole('slider', { name: 'Scene timeline' })).toBeVisible();
  await expect(page).toHaveURL(/when=scene/);
});

for (const path of ['/areas', '/models', '/methods', '/data', '/about']) {
  test(`page ${path} renders without errors`, async ({ page }) => {
    const errors = collectErrors(page);
    await page.goto(path);
    await expect(page.locator('h1')).toBeVisible();
    if (path === '/areas') await expect(page.locator('tbody tr').first()).toBeVisible();
    if (path === '/models')
      await expect(page.getByRole('heading', { name: 'Model comparison' })).toBeVisible();
    if (path === '/methods') await expect(page.locator('.katex').first()).toBeVisible();
    if (path === '/data') await expect(page.locator('tbody tr').first()).toBeVisible();
    expect(errors).toEqual([]);
  });
}

for (const path of ['/', '/areas', '/models', '/methods', '/data', '/about']) {
  test(`accessibility of ${path}`, async ({ page }) => {
    await page.goto(path);
    await page.waitForLoadState('networkidle');
    expect(await seriousA11yViolations(page)).toEqual([]);
  });
}
