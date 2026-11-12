/* Cached Chromium via CDP pipe; no server, downloads or npm dependencies.
 * 缓存 Chromium + CDP 管道；样本由 Flask 只读接口导出，不监听端口。
 * NETWORK_BROWSER_PYTHON=/path/to/venv/bin/python CHROMIUM_BINARY=/path/to/chrome node tests/test_network_readability_browser.js
 */
'use strict';
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const {spawn, spawnSync} = require('node:child_process'), assert = require('node:assert/strict');
const output = fs.mkdtempSync(path.join(os.tmpdir(), 'portal08-step8033-browser-'));
const report = [];
const fixture = spawnSync(process.env.NETWORK_BROWSER_PYTHON || 'python3', ['-B', 'tools/network_readability_fixture.py', output], {encoding:'utf8'});
assert.equal(fixture.status, 0, fixture.stdout + fixture.stderr);
const responses = JSON.parse(fs.readFileSync(path.join(output,'responses.json'),'utf8'));
const executable = process.env.CHROMIUM_BINARY || path.join(os.homedir(),'.cache/ms-playwright/chromium-1187/chrome-linux/chrome');
const browser = spawn(executable, ['--headless','--no-sandbox','--disable-gpu','--disable-dev-shm-usage',
  '--remote-debugging-pipe','--user-data-dir='+path.join(output,'profile')], {stdio:['ignore','ignore','pipe','pipe','pipe']});
let sequence=0, buffer='', session, stderr='', exited=false;
const pending = new Map(), handlers = new Map(), pageErrors=[];
const context={width:null,step:'launch Chromium',selector:'(none)'};
function step(name, selector='(none)') { context.step=name;context.selector=selector; }
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
async function visible(selector) {
  context.selector=selector;
  await until(`(function(){var e=document.querySelector(${JSON.stringify(selector)});if(!e)return false;var r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0 && r.height>0 && s.visibility!=='hidden' && s.display!=='none';}())`);
}
async function click(selector) { await visible(selector);await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`); }
async function lossPoint(container, role, failed, count) {
  context.selector=container+' [data-network-point^="'+role+':"]';
  const target=await evaluate(`networkHistoryData.targets.find(t=>t.role===${JSON.stringify(role)})`);
  assert(target,'Missing target: '+role);
  // Tokens use the returned row index; the rolling range and missing minutes change it.
  // 点位编号来自实际返回行；滚动时间边界和缺测都会改变索引。
  const matches=target.rows.map((point,index)=>({...point,index}))
    .filter(point=>point.failed_count===failed && point.count===count && point.loss_pct>0);
  assert.equal(matches.length,1,'Expected one '+role+' loss record with failed/count '+failed+'/'+count);
  const point=matches[0], selector=container+' [data-network-point="'+role+':'+point.index+'"]';
  await visible(selector);
  return {...point,selector};
}
async function pointPosition(selector) {
  await visible(selector);
  return evaluate(`(function(){var p=document.querySelector(${JSON.stringify(selector)});p.scrollIntoView({block:'center'});var c=p.querySelector('circle'),m=c.getScreenCTM();return {x:m.a*Number(c.getAttribute('cx'))+m.e,y:m.d*Number(c.getAttribute('cy'))+m.f};}())`);
}
async function styleIdentity() {
  return evaluate(`(function(){var role='public_control',line=document.querySelector('#network-rtt-public-chart [data-network-series="'+role+'"] > .network-series'),key=document.querySelector('[data-network-card="'+role+'"] .network-series');return {stroke:getComputedStyle(line).stroke,dash:line.getAttribute('stroke-dasharray'),key:getComputedStyle(key).stroke,marker:line.parentNode.querySelector('.network-marker').getAttribute('d')};}())`);
}
async function position(selector, curve=false) {
  await visible(selector);
  return evaluate(`(function(){var e=document.querySelector(${JSON.stringify(selector)});e.scrollIntoView({block:'center'});
    if(${curve}){var p=e.getPointAtLength(e.getTotalLength()*0.35),m=e.getScreenCTM();return {x:m.a*p.x+m.e,y:m.d*p.y+m.f};}
    var r=e.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};}())`);
}
async function moveTo(selector, curve=false) {
  const xy=await position(selector,curve);
  await cdp('Input.dispatchMouseEvent',{type:'mouseMoved',...xy});return xy;
}
async function tap(selector) {
  const xy=await position(selector);
  await cdp('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[xy]});
  await cdp('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
}
async function key(selector, key, code) {
  await visible(selector);await evaluate(`document.querySelector(${JSON.stringify(selector)}).focus()`);
  await cdp('Input.dispatchKeyEvent',{type:'keyDown',key,code:key===' '?'Space':key,windowsVirtualKeyCode:code});
  await cdp('Input.dispatchKeyEvent',{type:'keyUp',key,code:key===' '?'Space':key,windowsVirtualKeyCode:code});
}
async function verifyStats(range,id,role) {
  const data=JSON.parse(responses['/api/history/v3/network?range='+range].body),
    target=data.targets.find(t=>t.role===role), field=id==='network-loss-chart'?'loss_pct':'rtt_ms',
    points=target.rows.filter(p=>p[field]!==null && p[field]>=0 && p.time<data.end &&
      p.time+(data.granularity==='1d'?86400000:60000)>data.start && (field==='rtt_ms'?p.success_count:p.count)>0),
    values=points.map(p=>p[field]), total=points.reduce((n,p)=>n+(field==='rtt_ms'?p.success_count:p.count),0),
    sum=points.reduce((n,p)=>n+(field==='rtt_ms'?p.rtt_ms*p.success_count:p.failed_count*100),0),
    unit=field==='rtt_ms'?' ms':'%', formatted=n=>n===null?'—':n.toFixed(2)+unit;
  const actual=await evaluate(`(function(){var e=document.getElementById(${JSON.stringify(id+'-stats')}),chart=document.getElementById(${JSON.stringify(id)});return {
    role:e.getAttribute('data-network-stats-role'),values:Array.from(e.querySelectorAll(':scope > span > strong')).map(n=>n.textContent),
    ip:e.querySelector('.network-target-ip').textContent,pinned:chart.querySelector('[data-network-legend][aria-pressed="true"]').getAttribute('data-network-legend')};}())`);
  assert.equal(actual.role,role);assert.equal(actual.pinned,role);assert.equal(actual.ip,target.target);
  assert.deepEqual(actual.values.slice(1),[range,String(points.length),formatted(values.length?Math.max(...values):null),
    formatted(values.length?Math.min(...values):null),formatted(total?sum/total:null)],id+' stats in '+range);
  return actual;
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
    context.width=width;step('load 1h history','#network-quality-cards');
    await cdp('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:width===390});
    await cdp('Emulation.setTouchEmulationEnabled',{enabled:width===390});
    await cdp('Page.navigate',{url:'http://portal.test/'});
    await until('typeof networkHistoryData !== "undefined" && networkHistoryData && networkHistoryData.range === "1h"');
    step('open Network tab','#tab-network');await click('#tab-network');
    step('verify layout, cards and axes','#network-quality');
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
    const privateId='network-rtt-private-chart',publicId='network-rtt-public-chart',lossId='network-loss-chart';
    step('verify ordered ranges and stats below charts','.network-chart-stats');
    assert.deepEqual(await evaluate(`Array.from(document.querySelectorAll('[data-network-range]')).map(e=>e.textContent)`),['1h','3h','6h','10h','24h','7d','30d']);
    const statsLayout=await evaluate(`Array.from(document.querySelectorAll('.network-chart-stats')).map(e=>{var r=e.getBoundingClientRect(),s=e.parentNode.querySelector(':scope > svg').getBoundingClientRect();return {top:r.top,chartBottom:s.bottom,left:r.left,right:r.right,overflow:e.scrollWidth>e.clientWidth};})`);
    assert.equal(statsLayout.length,3);statsLayout.forEach(s=>{assert(s.top>=s.chartBottom);assert(s.left>=0&&s.right<=width);assert(!s.overflow);});
    await verifyStats('1h',privateId,'upstream_gateway');
    await verifyStats('1h',publicId,'public_primary');
    await verifyStats('1h',lossId,'upstream_gateway');
    const lanLegend='#'+privateId+' [data-network-legend="lan_gateway"]', upstreamLegend='#'+privateId+' [data-network-legend="upstream_gateway"]';
    step('hover temporary target and restore pin',lanLegend);
    if(width===1440) {
      await moveTo(lanLegend);
      await until(`document.getElementById('${privateId}-stats').getAttribute('data-network-stats-role')==='lan_gateway'`);
      assert(await evaluate(`document.querySelector('${upstreamLegend}').getAttribute('aria-pressed')==='true'`));
      await cdp('Input.dispatchMouseEvent',{type:'mouseMoved',x:2,y:2});
      await verifyStats('1h',privateId,'upstream_gateway');
      step('click curve to pin LAN','#'+privateId+' [data-network-series="lan_gateway"] > .network-series');
      const xy=await moveTo('#'+privateId+' [data-network-series="lan_gateway"] > .network-series',true);
      await cdp('Input.dispatchMouseEvent',{type:'mousePressed',...xy,button:'left',clickCount:1});
      await cdp('Input.dispatchMouseEvent',{type:'mouseReleased',...xy,button:'left',clickCount:1});
    } else {
      step('tap native legend to pin LAN',lanLegend);await tap(lanLegend);
    }
    await until(`document.querySelector('${lanLegend}').getAttribute('aria-pressed')==='true'`);
    await moveTo(upstreamLegend);await cdp('Input.dispatchMouseEvent',{type:'mouseMoved',x:2,y:2});
    await verifyStats('1h',privateId,'lan_gateway');
    step('keyboard focus previews and blur restores public target');
    const controlLegend='#'+publicId+' [data-network-legend="public_control"]', primaryLegend='#'+publicId+' [data-network-legend="public_primary"]';
    await evaluate(`document.querySelector('${controlLegend}').focus()`);
    assert(await evaluate(`document.getElementById('${publicId}-stats').getAttribute('data-network-stats-role')==='public_control' && document.querySelector('${primaryLegend}').getAttribute('aria-pressed')==='true'`));
    await evaluate('document.activeElement.blur()');await verifyStats('1h',publicId,'public_primary');
    step('Enter and Space pin legend targets');
    await key(controlLegend,'Enter',13);await verifyStats('1h',publicId,'public_control');
    await key(primaryLegend,' ',32);await verifyStats('1h',publicId,'public_primary');
    await key(controlLegend,'Enter',13);await evaluate('document.activeElement.blur()');
    await verifyStats('1h',publicId,'public_control');
    await screenshot(width+'-stats');
    step('verify role styles','#network-rtt-public-chart [data-network-series="public_control"]');
    const before=await styleIdentity();assert.equal(before.stroke,before.key);
    step(width===390?'tap LAN loss point':'hover LAN loss point');
    const lanPoint=await lossPoint('#network-loss-chart','lan_gateway',1,6);
    const xy=await pointPosition(lanPoint.selector);
    if(width===390) {
      await cdp('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:xy.x,y:xy.y}]});
      await cdp('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
    } else {await cdp('Input.dispatchMouseEvent',{type:'mouseMoved',x:xy.x,y:xy.y});}
    await until(`document.getElementById('network-point-detail').textContent.includes('失败 1 / Total / 总探测 6')`);
    assert(await evaluate(`document.getElementById('network-point-detail').textContent.includes('192.0.2.1') && document.getElementById('network-point-detail').textContent.includes(networkTime(${lanPoint.time}))`));
    step('select all-failed loss record');
    const allFailed=await lossPoint('#network-loss-records','public_primary',6,6);
    await click(allFailed.selector);
    assert(await evaluate(`document.getElementById('network-point-detail').textContent.includes('失败 6 / Total / 总探测 6')`));
    await screenshot(width+'-points');
    step('filter LAN and public primary targets');
    await click('[data-network-target="lan_gateway"]');await click('[data-network-target="public_primary"]');
    assert.deepEqual(await styleIdentity(),before,'Style stable after filtering at '+width);
    assert(await evaluate(`!document.querySelector('#network-loss-chart [data-network-series="lan_gateway"]') && !document.querySelector('#network-loss-records [data-network-point^="lan_gateway:"]') && document.querySelector('[data-network-card="lan_gateway"]').className.includes('network-unselected')`));
    step('capture filtered charts','#network-quality');await visible('#network-quality');
    await evaluate('document.getElementById("network-quality").scrollIntoView()');await screenshot(width+'-filtered');
    step('restore LAN and public primary targets');
    await click('[data-network-target="lan_gateway"]');await click('[data-network-target="public_primary"]');
    await click(lanLegend);await click(controlLegend);
    await click('#'+lossId+' [data-network-legend="public_primary"]');
    let priorStats;
    const rangeStats=[];
    for (const range of ['3h','6h','10h','24h','7d','30d','1h']) {
      step('switch range and verify latest/peak: '+range);
      await click('[data-network-range="'+range+'"]');await until('networkHistoryData.range === '+JSON.stringify(range));
      assert(await evaluate(`document.querySelector('[data-network-card="lan_gateway"]').textContent.includes('最新丢包 0.0%') && document.querySelector('[data-network-card="lan_gateway"]').textContent.includes('峰值 16.7%')`));
      if(range==='7d'||range==='30d') assert(await evaluate(`document.querySelector('[data-network-card="lan_gateway"]').textContent.includes('日汇总') && document.getElementById('network-loss-records').textContent.includes('失败 1000 / Total / 总探测 6000')`));
      const snapshot=await verifyStats(range,privateId,'lan_gateway');
      await verifyStats(range,publicId,'public_control');await verifyStats(range,lossId,'public_primary');
      if(priorStats)assert.notEqual(snapshot.values[5],priorStats.values[5],'Range changes recompute the average');
      priorStats=snapshot;rangeStats.push(snapshot);
      if(range==='7d')await screenshot(width+'-daily-stats');
    }
    assert(!(await evaluate('document.documentElement.scrollWidth>innerWidth')));
    report.push({width,layout,statsLayout,rangeStats});
    console.log(width+'px: full rows, seven ranges, weighted stats, hover/pin, touch/keyboard, loss records and no overflow passed');
  }
  step('verify no page errors');assert.deepEqual(pageErrors,[]);
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify({report,pageErrors},null,2));
  console.log('Browser artifacts: '+output);
}
run().catch(async error=>{
  console.error('Browser acceptance failed: width='+context.width+'px step='+JSON.stringify(context.step)+' selector='+JSON.stringify(context.selector));
  console.error(error.stack || error.message);
  const failure={...context,error:error.message,pageErrors};
  if(session && !exited) {
    try {
      failure.page=await evaluate(`(function(){var data=typeof networkHistoryData==='undefined'?null:networkHistoryData;return {range:data && data.range,points:Array.from(document.querySelectorAll('#network-loss-chart [data-network-point]')).map(function(e){return e.getAttribute('data-network-point');}),records:Array.from(document.querySelectorAll('#network-loss-records [data-network-point]')).map(function(e){return e.getAttribute('data-network-point');}),targets:data && data.targets.map(function(t){return {role:t.role,target:t.target,rows:t.rows.length,lossPoints:t.rows.map(function(p,i){return {index:i,time:p.time,failed_count:p.failed_count,count:p.count};}).filter(function(p){return p.failed_count>0;})};}),detail:document.getElementById('network-point-detail') && document.getElementById('network-point-detail').textContent};}())`);
      console.error('Page state: '+JSON.stringify(failure.page));
      fs.writeFileSync(path.join(output,'failure.html'),await evaluate('document.documentElement.outerHTML'));
      await screenshot('failure');
    } catch(diagnosticError) { failure.diagnosticError=diagnosticError.message; }
  }
  fs.writeFileSync(path.join(output,'failure.json'),JSON.stringify(failure,null,2));
  console.error('Browser artifacts: '+output);process.exitCode=1;
}).finally(()=>{browser.kill();});
