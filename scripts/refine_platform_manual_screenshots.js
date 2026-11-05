async (page)=>{
  await page.setViewportSize({width:1440,height:1050});
  await page.goto('http://127.0.0.1:5050/datasets');
  await page.getByRole('button').filter({hasText:'Baseline hatchlings'}).click();
  const first=page.locator('.nv-gallery .nv-image-card').first();
  await first.scrollIntoViewIfNeeded();
  await page.waitForFunction(()=>{const i=document.querySelector('.nv-gallery img');return i&&i.complete&&i.naturalWidth>0});
  await page.waitForTimeout(250);
  await page.screenshot({path:'output/playwright/user_manual/05_dataset_inspection.png'});
  await page.goto('http://127.0.0.1:5050/prepare');
  await page.getByLabel('Baseline hatchlings',{exact:false}).check();
  await page.getByRole('button',{name:'Select all approved (8)',exact:true}).waitFor();
  await page.getByRole('button',{name:'Select all approved (8)',exact:true}).click();
  await page.waitForFunction(()=>{const imgs=[...document.querySelectorAll('.nv-compact-gallery img')];return imgs.length===8&&imgs.every(i=>i.complete&&i.naturalWidth>0)});
  await page.locator('section.nv-card').filter({has:page.getByRole('heading',{name:'Choose source datasets',exact:true})}).screenshot({path:'output/playwright/user_manual/15_prepare_selection.png'});
  await page.goto('http://127.0.0.1:5050/review?image=3dc56e3f56a0b819');
  await page.waitForFunction(()=>{const i=document.querySelector('.review-image-wrap img');return i&&i.complete&&i.naturalWidth>0});
  await page.waitForTimeout(1000);
  const zoom=[];
  for(const value of ['1','0.5','1.5']){
    await page.getByLabel('Image zoom').selectOption(value);await page.waitForTimeout(200);
    zoom.push({value,width:(await page.locator('.review-image-wrap').boundingBox()).width});
  }
  await page.locator('.review-controls').screenshot({path:'output/playwright/user_manual/09_review_controls.png'});
  return {refined:['05_dataset_inspection','15_prepare_selection','09_review_controls'],zoom};
}
