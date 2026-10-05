// Local browser integration checks. Supply PLAYWRIGHT_MODULE and CHROMIUM_PATH.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const {spawn}=require('node:child_process');
const fs=require('node:fs');
const assert=require('node:assert/strict');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
(async()=>{
const server=spawn('python3',['-m','retryguard.web','--port','8876','--runs','/tmp/retryguard-browser-runs'],{cwd:root,env:process.env});
let browser;try{
await new Promise((resolve,reject)=>{server.stdout.on('data',d=>{if(String(d).includes('RetryGuard:'))resolve()});server.once('error',reject);server.once('exit',c=>reject(Error('Server exited '+c))) });
const args=process.env.CHROMIUM_ARGS?JSON.parse(process.env.CHROMIUM_ARGS):['--no-sandbox'];
browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH,args,headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1100},deviceScaleFactor:1});const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.goto('http://127.0.0.1:8876');await page.waitForTimeout(1500);
await page.screenshot({path:'/tmp/retryguard-ui-initial.png',fullPage:true});
assert.equal(await page.locator('canvas').count(),1,'WebGL canvas is present');
assert.equal(await page.getByRole('button').count(),2,'Only two entrance actions');
assert.equal(await page.locator('#workspace').count(),0,'Workspace is not mounted on entrance');
assert.ok(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight),'Entrance fits viewport');
let guideRequests=0;const observeRequest=r=>{if(r.url().includes('/api/'))guideRequests++};page.on('request',observeRequest);
await page.getByRole('button',{name:'How it works',exact:true}).click();await page.getByRole('dialog').waitFor();
await page.getByText('Failure changed the input.',{exact:true}).waitFor();
await page.getByRole('button',{name:'Success probability ½'}).click();await page.getByText('Success applied the target.',{exact:true}).waitFor();
await page.locator('.tour-chapters button').nth(1).click();await page.getByLabel('Apply recovery X').check();await page.getByText('Input restored; timeout can be reported.',{exact:true}).waitFor();await page.screenshot({path:'/tmp/retryguard-tour-recovery.png',fullPage:true});
await page.locator('.tour-chapters button').nth(2).click();await page.locator('#tour-cap').focus();await page.keyboard.press('End');await page.getByText('Meets an illustrative 1% timeout limit.',{exact:true}).waitFor();assert.equal(await page.locator('.tour-probabilities>div').last().locator('strong').textContent(),'0.390625%');await page.screenshot({path:'/tmp/retryguard-tour-budget.png',fullPage:true});
await page.locator('.tour-chapters button').nth(3).click();await page.getByLabel('Preserve original trial').check();assert.equal(await page.locator('.tour-alternatives .excluded').count(),3);
await page.getByRole('button',{name:'Reset guide'}).click();await page.getByText('Failure changed the input.',{exact:true}).waitFor();assert.equal(guideRequests,0,'Guide never calls the execution API');page.off('request',observeRequest);
await page.getByRole('button',{name:'Back to entrance'}).click();await page.getByRole('dialog').waitFor({state:'hidden'});
await page.getByRole('button',{name:'Enter workspace',exact:true}).click();await page.locator('#workspace').waitFor();
assert.equal(await page.locator('canvas').count(),0,'Shader is disposed on workspace entry');
await page.screenshot({path:'/tmp/retryguard-ui-workspace.png',fullPage:true});
await page.getByRole('button',{name:'Run analysis',exact:true}).click();
await page.getByRole('heading',{name:'The results are in.'}).waitFor({timeout:30000});
await page.screenshot({path:'/tmp/retryguard-ui-results.png',fullPage:true});
assert.equal(await page.locator('.recommendation h3').textContent(),'Deterministic');
await page.getByRole('tab',{name:'Alternatives'}).click();await page.waitForTimeout(600);
assert.equal(await page.locator('.candidate').count(),4);
assert.equal(await page.locator('.candidate').filter({hasText:'Both engines passed'}).count(),4);
await page.screenshot({path:'/tmp/retryguard-ui-compare.png',fullPage:true});
const [download]=await Promise.all([page.waitForEvent('download'),page.getByRole('link',{name:'All verified circuits + evidence'}).click()]);await download.saveAs('/tmp/retryguard-ui-evidence.zip');
await page.getByLabel('Preserve original trial').check();assert.equal(await page.locator('.recommendation').count(),0);
await page.getByRole('button',{name:'Run analysis',exact:true}).click();await page.getByRole('heading',{name:'The results are in.'}).waitFor({timeout:30000});assert.equal(await page.locator('.recommendation h3').textContent(),'Repaired source');
// A different configuration during a running request must not expose stale results.
await page.locator('#cap').fill('15');await page.getByRole('button',{name:'Run analysis',exact:true}).click();await page.locator('#timeout').fill('0.02');await page.getByRole('button',{name:'Run analysis',exact:true}).waitFor({timeout:30000});assert.equal(await page.locator('.recommendation').count(),0);assert.ok((await page.locator('.execution-status').textContent()).includes('Inputs changed'));
await page.locator('#example').selectOption('upload');await page.getByLabel('Manifest JSON',{exact:true}).setInputFiles({name:'bad.json',mimeType:'application/json',buffer:Buffer.from('{}')});await page.getByLabel('Trial QASM',{exact:true}).setInputFiles({name:'trial.qasm',mimeType:'text/plain',buffer:Buffer.from('OPENQASM 3.0;')});await page.getByRole('button',{name:'Run analysis',exact:true}).click();await page.getByText('Input rejected',{exact:true}).waitFor({timeout:30000});assert.equal(await page.locator('.downloads').count(),0);
await page.getByRole('button',{name:'How it works'}).click();await page.getByRole('dialog').waitFor();await page.keyboard.press('Escape');await page.getByRole('dialog').waitFor({state:'hidden'});assert.equal(await page.getByRole('dialog').count(),0);
const mobile=await browser.newPage({viewport:{width:390,height:844},deviceScaleFactor:1,reducedMotion:'reduce'});mobile.on('pageerror',e=>errors.push(e.message));await mobile.goto('http://127.0.0.1:8876');await mobile.waitForTimeout(600);assert.ok(await mobile.locator('.app').evaluate(el=>el.classList.contains('still')));assert.ok(await mobile.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await mobile.screenshot({path:'/tmp/retryguard-ui-mobile.png',fullPage:true});assert.equal(await mobile.getByRole('button').count(),2);await mobile.getByRole('button',{name:'How it works',exact:true}).click();await mobile.getByRole('dialog').waitFor();await mobile.locator('.tour-chapters button').nth(3).click();await mobile.getByLabel('Preserve original trial').waitFor();await mobile.screenshot({path:'/tmp/retryguard-tour-mobile.png',fullPage:true});assert.ok(await mobile.getByRole('dialog').evaluate(el=>el.scrollWidth<=el.clientWidth));await mobile.getByRole('button',{name:'Open real workspace'}).click();await mobile.locator('#workspace').waitFor();await mobile.getByRole('button',{name:'Run analysis',exact:true}).click();await mobile.getByRole('heading',{name:'The results are in.'}).waitFor({timeout:30000});await mobile.getByRole('tab',{name:'Alternatives'}).click();await mobile.screenshot({path:'/tmp/retryguard-ui-mobile-results.png',fullPage:true});assert.ok(await mobile.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
console.log(JSON.stringify({passed:true,checks:['interactive guide branch/recovery/cap/eligibility controls','guide sends no API requests','guide reset and workspace handoff','two-action entrance','landing instructions','shader cleanup on workspace entry','live example execution','four verified alternatives','evidence ZIP download','source constraint recommendation','stale-result suppression','invalid upload rejection','modal Escape','mobile layout','reduced motion','no JavaScript errors'],screenshots:6},null,2));
}finally{await browser?.close();server.kill('SIGTERM')}
})().catch(e=>{console.error(e);process.exitCode=1});
