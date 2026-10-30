// Optional release check: npm install --no-save playwright; npx playwright install chromium.
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const fs=require('node:fs');
(async()=>{
 const server=spawn(process.env.QLARITY_PYTHON||'python',['-m','uvicorn','backend.serve:app','--host','127.0.0.1','--port','8766'],{stdio:['ignore','pipe','pipe']});
 let browser;const errors=[];
 try{
  for(let i=0;i<100;i++){try{if((await fetch('http://127.0.0.1:8766/api/model')).ok)break}catch{}await new Promise(r=>setTimeout(r,200))}
  let executablePath=process.env.CHROMIUM_EXECUTABLE;
  let args=['--no-sandbox'];
  if(process.env.SPARTICUZ_PATH){const c=require(process.env.SPARTICUZ_PATH);executablePath=await c.executablePath();args=c.args}
  browser=await chromium.launch({headless:true,executablePath,args});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8766');await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('ready'));
  await page.click('#recorded');await page.waitForFunction(()=>document.querySelectorAll('.scenario').length===4);
  if(!(await page.textContent('#provenance')).includes('RECORDED'))throw Error('Recorded label missing');
  await page.locator('[data-select="2"]').click();
  await page.locator('#population').focus();await page.keyboard.press('ArrowRight');
  const download=page.waitForEvent('download');await page.click('#csv');const d=await download;if(!d.suggestedFilename().endsWith('.csv'))throw Error('CSV export failed');
  await page.screenshot({path:'/tmp/qlarity-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:'/tmp/qlarity-mobile.png',fullPage:true});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);if(overflow)throw Error('Mobile horizontal overflow');
  await page.setViewportSize({width:1440,height:1000});
  await page.locator('[name=quantum]').uncheck();await page.click('#run');
  await page.waitForFunction(()=>document.querySelector('#provenance').textContent.includes('FRESH'),{},{timeout:60000});
  await page.locator('[name=quantum]').check();await page.click('#run');
  await page.waitForFunction(()=>document.querySelector('#cancel').hidden && document.querySelector('#status').textContent==='Completed',{},{timeout:180000});
  if(await page.locator('#error').isVisible())throw Error(await page.locator('#error').textContent());
  const q=await page.locator('[data-circuit]').count();if(q<1)throw Error('No actual quantum evidence shown');
  const zip=page.waitForEvent('download');await page.click('#zip');await zip;
  await page.click('#run');await page.click('#cancel');await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Cancelled'));
  await page.reload();await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('ready'));
  if(errors.length)throw Error(errors.join('; '));
  fs.writeFileSync('evidence/browser-verification.json',JSON.stringify({desktop:'1440×1000',mobile:'390×844',horizontal_overflow:false,recorded_load:true,scenario_inspection:true,keyboard_inspection:true,csv_download:true,fresh_classical:true,fresh_quantum:true,zip_download:true,cancellation:true,reload:true,javascript_errors:errors},null,2));
  console.log('BROWSER CHECK PASSED');
 }finally{if(browser)await browser.close();server.kill('SIGTERM')}
})().catch(e=>{console.error(e);process.exitCode=1});
