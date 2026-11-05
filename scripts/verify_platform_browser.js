async (page) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 1000 });
  const routes = [
    ['/', 'Project overview'], ['/datasets', 'Dataset library'], ['/quality', 'Dataset quality'],
    ['/review?image=3dc56e3f56a0b819', 'Human annotation review'],
    ['/prepare', 'Dataset preparation'], ['/training', 'Model training'],
    ['/models', 'Model registry'], ['/evaluation', 'Model evaluation'],
    ['/improvement', 'Active learning'], ['/monitoring', 'Video monitoring'],
    ['/reports', 'Reports & experiment history'],
  ];
  const checked = [];
  for (const [route, heading] of routes) {
    await page.goto('http://127.0.0.1:5050' + route);
    await page.getByRole('heading', { name: heading, exact: true, level: 1 }).waitFor();
    await page.waitForLoadState('networkidle');
    const alerts = await page.getByRole('alert').allTextContents();
    if (alerts.length) throw new Error(route + ': ' + alerts.join('; '));
    if (route.startsWith('/review')) {
      await page.locator('.review-image-wrap img').waitFor();
      await page.getByRole('button', { name: 'Save review', exact: true }).waitFor();
      await page.screenshot({ path: 'output/playwright/platform-review.png', fullPage: true });
    }
    if (route === '/models') await page.screenshot({ path: 'output/playwright/platform-models.png', fullPage: true });
    checked.push(route);
  }
  await page.goto('http://127.0.0.1:5050/inference');
  await page.waitForLoadState('networkidle');
  await page.locator('#media-input').setInputFiles('C:/Users/haytham/Downloads/engineering_design_I/backend/tests/fixtures/hatchling_nps.jpg');
  const responsePromise = page.waitForResponse(response => response.url().endsWith('/api/detect/image') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Run Detection', exact: false }).click();
  const response = await responsePromise;
  const inference = await response.json();
  if (response.status() !== 200 || inference.status !== 'completed') throw new Error('Image inference failed');
  await page.getByRole('link', { name: 'Download image', exact: true }).waitFor();
  const downloadPath = await page.getByRole('link', { name: 'Download image', exact: true }).getAttribute('href');
  const download = await page.request.get(new URL(downloadPath, page.url()).toString());
  if (download.status() !== 200 || !download.headers()['content-disposition']?.includes('attachment')) throw new Error('Download link did not serve the result');
  await page.screenshot({ path: 'output/playwright/platform-inference-full.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('http://127.0.0.1:5050/');
  await page.waitForLoadState('networkidle');
  const fits = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
  await page.screenshot({ path: 'output/playwright/platform-mobile.png', fullPage: true });
  if (!fits) throw new Error('Mobile overview has horizontal document overflow');
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('http://127.0.0.1:5050/');
  await page.waitForLoadState('networkidle');
  await page.screenshot({ path: 'output/playwright/platform-overview-full.png', fullPage: true });
  if (errors.length) throw new Error(errors.join('; '));
  return { routes: checked, browserErrors: errors, mobileFits: fits, inferenceJob: inference.job_id, detections: inference.detections.length, downloadVerified: download.status() === 200 };
}
