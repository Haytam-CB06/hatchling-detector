async (page) => {
  const base = 'http://127.0.0.1:5051';
  const fixtureName = 'Browser verification fixture ' + Date.now();
  const errors = [];
  page.setDefaultTimeout(10000);
  page.on('pageerror', error => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 1000 });
  const read = async path => {
    const response = await page.request.get(base + path);
    if (!response.ok()) throw new Error(path + ': ' + response.status());
    return response.json();
  };
  const waitJob = async id => {
    for (let i = 0; i < 160; i++) {
      const job = await read('/api/platform/jobs/' + id);
      if (job.status === 'completed') return job;
      if (['failed','stopped','interrupted'].includes(job.status)) throw new Error(JSON.stringify(job));
      await page.waitForTimeout(250);
    }
    throw new Error('Background job did not finish: ' + id);
  };
  await page.goto(base + '/datasets');
  await page.getByRole('heading', { name: 'Dataset library', level: 1, exact: true }).waitFor();
  await page.getByLabel('Dataset name', { exact: true }).fill(fixtureName);
  await page.getByLabel('Source and recording details').fill('Isolated software test using copies of existing approved labels; no source independence claim.');
  await page.getByLabel('Dataset files', { exact: true }).setInputFiles('C:/Users/haytham/Downloads/engineering_design_I/output/playwright/review-fixture.zip');
  const importing = page.waitForResponse(r => r.url().endsWith('/api/platform/datasets/upload') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Create versioned import' }).click();
  const imported = await (await importing).json();
  await waitJob(imported.job.id);
  const images = (await read('/api/platform/datasets/' + imported.dataset_id)).images;
  if (images.length !== 3 || images.some(i => i.status !== 'unreviewed')) throw new Error('Import approval integrity failed');
  const positives = images.filter(i => i.original.length);
  const negative = images.find(i => !i.original.length);
  if (positives.length !== 2 || !negative) throw new Error('Unexpected verified-source fixture');
  const open = async image => {
    await page.goto(base + '/review?dataset=' + imported.dataset_id + '&image=' + image.id);
    await page.locator('.review-image-wrap img').waitFor();
    await page.getByRole('button', { name: 'Save review', exact: true }).waitFor();
  };
  const save = async () => {
    const saving = page.waitForResponse(r => /\/api\/review\/images\/[^/]+$/.test(new URL(r.url()).pathname) && r.request().method() === 'PUT');
    await page.getByRole('button', { name: 'Save review', exact: true }).click();
    const response = await saving;
    if (!response.ok()) throw new Error(await response.text());
    const saved = await response.json();
    await page.getByRole('status').filter({ hasText: 'Saved revision' }).waitFor();
    return saved;
  };
  await open(positives[0]);
  const initial = await page.locator('.review-box-row').count();
  await page.getByRole('button', { name: 'Draw hatchling', exact: true }).click();
  const canvas = page.locator('.review-image-wrap svg');
  await canvas.scrollIntoViewIfNeeded();
  const area = await canvas.boundingBox();
  if (!area) throw new Error('Annotation canvas is missing');
  await page.mouse.move(area.x + area.width * .05, area.y + area.height * .05);
  await page.mouse.down();
  await page.mouse.move(area.x + area.width * .2, area.y + area.height * .2, { steps: 6 });
  await page.mouse.up();
  if (await page.locator('.review-box-row').count() !== initial + 1) throw new Error('Drawing failed');
  await page.getByRole('button', { name: 'Select / move', exact: true }).click();
  const extra = page.locator('.review-box').last();
  const beforeMove = await extra.getAttribute('x');
  const extraBounds = await extra.boundingBox();
  await page.mouse.move(extraBounds.x + extraBounds.width / 2, extraBounds.y + extraBounds.height / 2);
  await page.mouse.down();
  await page.mouse.move(extraBounds.x + extraBounds.width / 2 + 15, extraBounds.y + extraBounds.height / 2 + 10, { steps: 5 });
  await page.mouse.up();
  if (await extra.getAttribute('x') === beforeMove) throw new Error('Moving failed');
  const beforeWidth = await extra.getAttribute('width');
  const handle = page.locator('.review-handle').last();
  const corner = await handle.boundingBox();
  await page.mouse.move(corner.x + corner.width / 2, corner.y + corner.height / 2);
  await page.mouse.down();
  await page.mouse.move(corner.x + corner.width / 2 + 12, corner.y + corner.height / 2 + 12, { steps: 5 });
  await page.mouse.up();
  if (await extra.getAttribute('width') === beforeWidth) throw new Error('Resizing failed');
  await page.getByLabel('Image zoom').selectOption('1.5');
  await page.getByLabel('Image zoom').selectOption('1');
  await page.getByLabel('Delete box ' + (initial + 1), { exact: true }).click();
  if (await page.locator('.review-box-row').count() !== initial) throw new Error('Deletion failed');
  await page.getByLabel('Reviewer name').fill('Browser software-test operator');
  await page.getByPlaceholder('Why did you change this annotation?').fill('Software-only draft edit check. Approved geometry will be restored from existing human-reviewed source.');
  const draft = await save();
  if (draft.status !== 'in_review') throw new Error('Draft was incorrectly approved');
  await open(positives[0]);
  if (await page.locator('.review-box-row').count() !== initial) throw new Error('Draft did not persist');
  await page.getByRole('button', { name: 'Load source label candidates', exact: true }).click();
  await page.getByLabel('Review status', { exact: true }).selectOption('verified_positive');
  await page.getByPlaceholder('Why did you change this annotation?').fill('Software verification: exact annotation copied from existing human-approved source; test database only.');
  await save();
  for (const image of images.filter(i => i.id !== positives[0].id)) {
    await open(image);
    await page.getByLabel('Reviewer name').fill('Browser software-test operator');
    await page.getByLabel('Review status', { exact: true }).selectOption(image.original.length ? 'verified_positive' : 'verified_negative');
    await page.getByPlaceholder('Why did you change this annotation?').fill('Exact existing approved source annotation; isolated software test only.');
    await save();
  }
  await open(positives[0]);
  const persisted = await read('/api/review/images/' + positives[0].id);
  if (persisted.revision !== 2 || persisted.status !== 'verified_positive') throw new Error('Approved review did not persist');
  await page.screenshot({ path: 'output/playwright/platform-review-workflow.png', fullPage: true });
  const negativeSaved = await read('/api/review/images/' + negative.id);
  if (negativeSaved.status !== 'verified_negative' || negativeSaved.boxes.length) throw new Error('Empty negative was lost');
  await page.goto(base + '/datasets');
  await page.getByRole('button').filter({ hasText: fixtureName }).click();
  await page.getByRole('button', { name: 'Check and approve dataset decisions', exact: true }).click();
  await page.goto(base + '/prepare');
  await page.getByLabel(fixtureName, { exact: false }).check();
  await page.getByRole('button', { name: 'Select all approved (3)', exact: true }).waitFor();
  await page.getByRole('button', { name: 'Select all approved (3)', exact: true }).click();
  await page.getByRole('button', { name: 'Continue', exact: false }).click();
  await page.getByLabel('Reviewer for grouping decisions').fill('Browser software-test operator');
  for (const image of images) {
    await page.getByLabel('Source group ' + image.id, { exact: true }).fill('browser-software-fixture:' + image.id);
    await page.getByLabel('Source evidence ' + image.id, { exact: true }).fill('Isolated software fixture assignment; source independence unverified; never use this fixture as a benchmark.');
    await page.getByLabel('Partition ' + image.id, { exact: true }).selectOption(image.id === positives[1].id ? 'val' : 'train');
    const row = page.getByRole('row').filter({ has: page.getByLabel('Source group ' + image.id, { exact: true }) });
    await row.getByLabel('Group confirmed', { exact: true }).check();
    const grouping = page.waitForResponse(r => r.url().endsWith('/images/' + image.id + '/group') && r.request().method() === 'PUT');
    await row.getByRole('button', { name: 'Save grouping', exact: true }).click();
    if (!(await grouping).ok()) throw new Error('Source group save failed');
  }
  await page.getByRole('button', { name: 'Continue', exact: false }).click();
  await page.getByLabel('Dataset version name').fill('Browser software fixture — not a scientific dataset');
  await page.getByRole('button', { name: 'Run readiness checks', exact: false }).click();
  await page.getByRole('heading', { name: 'Ready for preparation', exact: true }).waitFor();
  const preparing = page.waitForResponse(r => r.url().endsWith('/api/platform/prepare') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Generate immutable version', exact: false }).click();
  const preparation = await (await preparing).json();
  const completed = await waitJob(preparation.id);
  const versions = await read('/api/platform/versions');
  if (!versions.some(v => v.id === completed.result.version_id && !v.summary.independent_test)) throw new Error('Version integrity failed');
  const download = await page.request.get(base + '/api/platform/versions/' + completed.result.version_id + '/download');
  if (!download.ok()) throw new Error('YOLO archive download failed');
  await page.screenshot({ path: 'output/playwright/platform-preparation-workflow.png', fullPage: true });
  if (errors.length) throw new Error(errors.join('; '));
  const result = { dataset_id: imported.dataset_id, version_id: completed.result.version_id,
    approved_images: 3, positive_images: 2, negative_images: 1,
    draw_move_resize_delete: true, zoom: true, draft_and_approval_persisted: true,
    yolo_download_verified: true, browser_errors: errors, storage: 'isolated test database only' };
  console.log(JSON.stringify(result));
  return result;
}
