/* Cached Chromium via CDP pipe; no server, downloads or npm dependencies.
 * 缓存 Chromium + CDP 管道；样本由 Flask 只读接口导出，不监听端口。
 * NETWORK_BROWSER_PYTHON=/path/to/venv/bin/python CHROMIUM_BINARY=/path/to/chrome node tests/test_network_readability_browser.js
 */
'use strict';
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const {spawn, spawnSync} = require('node:child_process'), assert = require('node:assert/strict');
const output = fs.mkdtempSync(path.join(os.tmpdir(), 'portal08-step8031-browser-'));
const fixture = spawnSync(process.env.NETWORK_BROWSER_PYTHON || 'python3', ['-B', 'tools/network_readability_fixture.py', output], {encoding:'utf8'});
assert.equal(fixture.status, 0, fixture.stdout + fixture.stderr);
const responses = JSON.parse(fs.readFileSync(path.join(output,'responses.json'),'utf8'));
const executable = process.env.CHROMIUM_BINARY || path.join(os.homedir(),'.cache/ms-playwright/chromium-1187/chrome-linux/chrome');
const browser = spawn(executable, ['--headless','--no-sandbox','--disable-gpu','--disable-dev-shm-usage',
  '--remote-debugging-pipe','--user-data-dir='+path.join(output,'profile')], {stdio:['ignore','ignore','pipe','pipe','pipe']});
let sequence=0, buffer='', session, stderr='', exited=false;
const pending = new Map(), handlers = new Map(), pageErrors=[];
function cdp(method, params={}, sessionId=session) {
  return new Promise((resolve,reject) => {
    if (exited) return reject(Error('Chromium exited: '+stderr));
    const id=++sequence, timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout: '+method));},15000);
    pending.set(id,{resolve,reject,timer}); browser.stdio[3].write(JSON.stringify({id,method,params,sessionId})+'\0');
  });
}
function rejectAll(error) { for (const p of pending.values()) {clearTimeout(p.timer);p.reject(error);} pending.clear(); }
for (const pipe of [browser.stdio[3],browser.stdio[4]]) pipe.on('error',()=>{});
browser.on('error',error=>{exited=true;rejectAll(error);});
browser.on('exit',(code,signal)=>{exited=true;rejectAll(Error('Chromium exited '+(signal || code)+': '+stderr));});
browser.stderr.on('data',data=>{stderr=(stderr+data).slice(-6000);});
browser.stdio[4].on('data',data=>{
  buffer+=data;
  let at;
  while ((at=buffer.indexOf('\0'))>=0) {
    const message=JSON.parse(buffer.slice(0,at)); buffer=buffer.slice(at+1);
    if (message.id && pending.has(message.id)) {
      const p=pending.get(message.id);pending.delete(message.id);clearTimeout(p.timer);
      message.error ? p.reject(Error(JSON.stringify(message.error))) : p.resolve(message.result);
    } else if (handlers.has(message.method)) {
      Promise.resolve(handlers.get(message.method)(message.params,message.sessionId)).catch(error=>{pageErrors.push(error.message);});
    }
  }
});
async function evaluate(expression) {
  const result=await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  assert(!result.exceptionDetails,JSON.stringify(result.exceptionDetails));return result.result.value;
}
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(expression) {
  for (let i=0;i<100;i++) {if (await evaluate(expression)) return;await delay(50);}
  throw Error('Page condition timed out: '+expression);
}
async function screenshot(name) {
  const result=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
  fs.writeFileSync(path.join(output,name+'.png'),Buffer.from(result.data,'base64'));
}
async function click(selector) { await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`); }
async function pointPosition() {
  return evaluate(`(function(){var p=document.querySelector('#network-loss-chart [data-network-point="lan_gateway:20"]');p.scrollIntoView({block:'center'});var c=p.querySelector('circle'),m=c.getScreenCTM();return {x:m.a*Number(c.getAttribute('cx'))+m.e,y:m.d*Number(c.getAttribute('cy'))+m.f};}())`);
}
async function styleIdentity() {
  return evaluate(`(function(){var role='public_control',line=document.querySelector('#network-rtt-public-chart [data-network-series="'+role+'"] > .network-series'),key=document.querySelector('[data-network-card="'+role+'"] .network-series');return {stroke:getComputedStyle(line).stroke,dash:line.getAttribute('stroke-dasharray'),key:getComputedStyle(key).stroke,marker:line.parentNode.querySelector('.network-marker').getAttribute('d')};}())`);
}
async function run() {
  await cdp('Browser.getVersion',{},undefined);
  const target=await cdp('Target.createTarget',{url:'about:blank'},undefined);
  const attach=await cdp('Target.attachToTarget',{targetId:target.targetId,flatten:true},undefined); session=attach.sessionId;
  handlers.set('Fetch.requestPaused',async(params,sessionId)=>{
    const url=new URL(params.request.url), key=url.pathname==='/api/history/v3/network' ? url.pathname+'?range='+url.searchParams.get('range') : url.pathname;
    const response=responses[key] || {type:'text/plain',body:'Not found'};
    await cdp('Fetch.fulfillRequest',{requestId:params.requestId,responseCode:responses[key]?200:404,
      responseHeaders:[{name:'Content-Type',value:response.type}],body:Buffer.from(response.body).toString('base64')},sessionId);
  });
  handlers.set('Runtime.exceptionThrown',params=>{pageErrors.push(JSON.stringify(params.exceptionDetails));});
  await cdp('Page.enable');await cdp('Runtime.enable');await cdp('Fetch.enable',{patterns:[{urlPattern:'*'}]});
  await cdp('Emulation.setTimezoneOverride',{timezoneId:'America/Toronto'});
  for (const width of [1440,390]) {
    await cdp('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:width===390});
    await cdp('Emulation.setTouchEmulationEnabled',{enabled:width===390});
    await cdp('Page.navigate',{url:'http://portal.test/'});
    await until('typeof networkHistoryData !== "undefined" && networkHistoryData && networkHistoryData.range === "1h"');
    await click('#tab-network');
    const layout=await evaluate(`(function(){var ids=['network-rtt-private-chart','network-rtt-public-chart','network-loss-chart'],q=document.getElementById('network-quality').getBoundingClientRect();return {overflow:document.documentElement.scrollWidth>innerWidth,cards:document.querySelectorAll('[data-network-card]').length,charts:ids.map(function(id){var e=document.getElementById(id),r=e.getBoundingClientRect(),svg=e.querySelector(':scope > svg'),m=svg.getScreenCTM();return {width:r.width,left:r.left,top:r.top,bottom:r.bottom,start:m.a*64+m.e,end:m.a*(svg.viewBox.baseVal.width-16)+m.e};}),width:q.width,left:q.left,private:document.querySelectorAll('#network-rtt-private-chart [data-network-series]').length,public:document.querySelectorAll('#network-rtt-public-chart [data-network-series]').length,lossTicks:document.querySelector('#network-loss-chart').textContent};}())`);
    assert(!layout.overflow,'Horizontal overflow at '+width);assert.equal(layout.cards,6);assert.equal(layout.private,4);assert.equal(layout.public,2);
    layout.charts.forEach((chart,i)=>{
      assert(Math.abs(chart.width-layout.width)<1,'Full row at '+width);assert(Math.abs(chart.left-layout.left)<1);
      assert(Math.abs(chart.start-layout.charts[0].start)<1);assert(Math.abs(chart.end-layout.charts[0].end)<1);
      if(i)assert(chart.top>layout.charts[i-1].bottom);
    });
    assert(layout.lossTicks.includes('100 %') && layout.lossTicks.includes('0 %'));
    assert(await evaluate(`document.querySelector('[data-network-card="lan_gateway"]').textContent.includes('最新丢包 0.0%') && document.querySelector('[data-network-card="lan_gateway"]').textContent.includes('峰值 16.7%')`));
    assert(await evaluate(`document.querySelectorAll('.network-y-tick').length === 15 && document.querySelector('#network-rtt-private-chart .network-y-tick').textContent.includes('ms') && document.querySelector('#network-rtt-public-chart .network-y-tick').textContent.includes('ms')`));
    const before=await styleIdentity();assert.equal(before.stroke,before.key);
    const xy=await pointPosition();
    if(width===390) {
      await cdp('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:xy.x,y:xy.y}]});
      await cdp('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
    } else {await cdp('Input.dispatchMouseEvent',{type:'mouseMoved',x:xy.x,y:xy.y});}
    await until(`document.getElementById('network-point-detail').textContent.includes('失败 1 / Total / 总探测 6')`);
    assert(await evaluate(`document.getElementById('network-point-detail').textContent.includes('192.0.2.1') && document.getElementById('network-point-detail').textContent.includes(networkTime(networkHistoryData.targets[0].rows[20].time))`));
    await click('#network-loss-records [data-network-point="public_primary:54"]');
    assert(await evaluate(`document.getElementById('network-point-detail').textContent.includes('失败 6 / Total / 总探测 6')`));
    await screenshot(width+'-points');
    await click('[data-network-target="lan_gateway"]');await click('[data-network-target="public_primary"]');
    assert.deepEqual(await styleIdentity(),before,'Style stable after filtering at '+width);
    assert(await evaluate(`!document.querySelector('#network-loss-chart [data-network-series="lan_gateway"]') && !document.querySelector('#network-loss-records [data-network-point^="lan_gateway:"]') && document.querySelector('[data-network-card="lan_gateway"]').className.includes('network-unselected')`));
    await evaluate('document.getElementById("network-quality").scrollIntoView()');await screenshot(width+'-filtered');
    await click('[data-network-target="lan_gateway"]');await click('[data-network-target="public_primary"]');
    for (const range of ['24h','7d','30d','1h']) {
      await click('[data-network-range="'+range+'"]');await until('networkHistoryData.range === '+JSON.stringify(range));
      assert(await evaluate(`document.querySelector('[data-network-card="lan_gateway"]').textContent.includes('最新丢包 0.0%') && document.querySelector('[data-network-card="lan_gateway"]').textContent.includes('峰值 16.7%')`));
      if(range==='7d'||range==='30d') assert(await evaluate(`document.querySelector('[data-network-card="lan_gateway"]').textContent.includes('日汇总') && document.getElementById('network-loss-records').textContent.includes('失败 1000 / Total / 总探测 6000')`));
    }
    console.log(width+'px: full rows, aligned axes, latest/peak, point interaction, stable styles and four ranges passed');
  }
  assert.deepEqual(pageErrors,[]);console.log('Browser artifacts: '+output);
}
run().catch(error=>{console.error(error.message);console.error('Browser artifacts: '+output);process.exitCode=1;}).finally(()=>{browser.kill();});
