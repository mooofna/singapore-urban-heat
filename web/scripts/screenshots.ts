// Renders the README images from a running preview server:
//   npm run build && npm run preview &   then   node scripts/screenshots.ts ../docs/assets
import { chromium, type Page } from '@playwright/test';

interface Shot {
  width?: number;
  height?: number;
  theme?: 'light' | 'dark';
  wait?: number;
  prepare?: (page: Page) => Promise<void>;
}

const base = process.env.BASE_URL ?? 'http://localhost:4173';
const out = process.argv[2] ?? '../docs/assets';
const browser = await chromium.launch();

async function shot(name: string, path: string, opts: Shot = {}): Promise<void> {
  const { width = 1440, height = 860, theme = 'dark', wait = 4000, prepare } = opts;
  const page = await browser.newPage({
    viewport: { width, height },
    deviceScaleFactor: 2,
    colorScheme: theme
  });
  await page.goto(`${base}${path}`);
  await page.waitForLoadState('networkidle');
  if (prepare) await prepare(page);
  await page.waitForTimeout(wait);
  await page.screenshot({ path: `${out}/${name}.png` });
  await page.close();
}

await shot('explorer-dark', '/?at=1.3550,103.8200,11.10', { theme: 'dark' });
await shot('explorer-light', '/?at=1.3550,103.8200,11.10', { theme: 'light' });
await shot('explorer-trend', '/?layer=trend&at=1.3550,103.8200,11.10', { theme: 'light' });
await shot('models', '/models', { theme: 'light', height: 1100 });
await browser.close();
