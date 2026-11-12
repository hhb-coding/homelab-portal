/* Optional cached-Chromium acceptance, CDP pipe only; no server or npm packages.
 * 可选缓存 Chromium 验收，仅用 CDP 管道；合成数据，无监听服务或 npm 依赖。
 * CHROMIUM_BINARY=/path/to/chrome node tests/test_network_device_cards_browser.js
 */
'use strict';
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process'),assert=require('node:assert/strict');
const output=fs.mkdtempSync(path.join(os.tmpdir(),'portal-network-device-cards-'));
const executable=process.env.CHROMIUM_BINARY||path.join(os.homedir(),'.cache/ms-playwright/chromium-1187/chrome-linux/chrome');
const browser=spawn(executable,['--headless','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--remote-debugging-pipe','--user-data-dir='+path.join(output,'profile')],{stdio:['ignore','ignore','pipe','pipe','pipe']});
let sequence=0,buffer='',session,stderr='',exited=false;
const pending=new Map(),errors=[],context={width:null,step:'launch Chromium'};
const devices=[
  {device_id:'off-old',display_name:'Offline old',beszel_status:'down',last_seen:'2026-01-01 10:00:00',uptime_seconds:999999},
  {device_id:'up-short',display_name:'Online short',beszel_status:'up',last_seen:'2026-01-01 13:00:00',uptime_seconds:3600},
  {device_id:'unknown',display_name:'Unknown device',last_seen:'2026-01-01 11:00:00'},
  {device_id:'off-new',display_name:'Offline recent',beszel_status:'paused',last_seen:'2026-01-01 12:00:00'},
  {device_id:'up-long',display_name:'Online long',beszel_status:'up',last_seen:'2026-01-01 13:00:00',uptime_seconds:172800}
].map((device,i)=>({...device,lan_ip:'192.0.2.'+(i+1),zerotier_ip:'198.51.100.'+(i+1)}));
let dashboard={status:'ok',server_time:Date.UTC(2026,0,1,14)/1000,sources:{metrics_status:'ok'},devices};
const order=['up-long','up-short','unknown','off-new','off-old'];
function cdp(method,params={},sessionId=session){return new Promise((resolve,reject)=>{
  if(exited)return reject(Error('Chromium exited: '+stderr));
  const id=++sequence,timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout: '+method));},15000);
  pending.set(id,{resolve,reject,timer});browser.stdio[3].write(JSON.stringify({id,method,params,sessionId})+'\0');
});}
function rejectAll(error){for(const p of pending.values()){clearTimeout(p.timer);p.reject(error);}pending.clear();}
for(const pipe of [browser.stdio[3],browser.stdio[4]])pipe.on('error',()=>{});
browser.on('error',error=>{exited=true;rejectAll(error);});
browser.on('exit',(code,signal)=>{exited=true;rejectAll(Error('Chromium exited '+(signal||code)+': '+stderr));});
browser.stderr.on('data',data=>{stderr=(stderr+data).slice(-6000);});
async function response(params,sessionId){
  const url=new URL(params.request.url);let body='',type='application/json',status=200;
  if(url.pathname==='/'){
    type='text/html';body=fs.readFileSync('templates/index.html','utf8')
      .replace(/\{\{ app_name \}\}/g,'HomeLab Portal acceptance')
      .replace(/\{% if database_ready %\}[\s\S]*?\{% endif %\}/g,'<b class="ok">READY</b>')
      .replace(/\{\{ url_for\('static', filename='([^']+)'\) \}\}/g,'/static/$1')
      .replace(/\{\{ url_for\('lite'\) \}\}/g,'/lite');
  }else if(/^\/static\/(style\.css|dashboard\.js|offline-seen\.js|performance-history\.js)$/.test(url.pathname)){
    type=url.pathname.endsWith('.css')?'text/css':'application/javascript';body=fs.readFileSync('.'+url.pathname,'utf8');
  }else if(url.pathname==='/api/dashboard')body=JSON.stringify(dashboard);
  else if(url.pathname==='/api/history')body=JSON.stringify({status:'ok',devices:[]});
  else if(url.pathname==='/api/history/v3/network')body=JSON.stringify({status:'ok',schema_version:3,range:'1h',granularity:'1m',start:Date.UTC(2026,0,1,13),end:Date.UTC(2026,0,1,14),targets:[],events:[]});
  else{status=404;type='text/plain';body='Not found';}
  await cdp('Fetch.fulfillRequest',{requestId:params.requestId,responseCode:status,responseHeaders:[{name:'Content-Type',value:type}],body:Buffer.from(body).toString('base64')},sessionId);
}
browser.stdio[4].on('data',data=>{
  buffer+=data;let at;
  while((at=buffer.indexOf('\0'))>=0){
    const message=JSON.parse(buffer.slice(0,at));buffer=buffer.slice(at+1);
    if(message.id&&pending.has(message.id)){
      const p=pending.get(message.id);pending.delete(message.id);clearTimeout(p.timer);
      message.error?p.reject(Error(JSON.stringify(message.error))):p.resolve(message.result);
    }else if(message.method==='Fetch.requestPaused')response(message.params,message.sessionId).catch(e=>errors.push(e.message));
    else if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);
  }
});
async function evaluate(expression){const r=await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});assert(!r.exceptionDetails,JSON.stringify(r.exceptionDetails));return r.result.value;}
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(expression){for(let i=0;i<150;i++){if(await evaluate(expression))return;await delay(50);}throw Error('Page condition timed out: '+expression);}
async function paint(){await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');}
async function screenshot(name){const r=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});fs.writeFileSync(path.join(output,name+'.png'),Buffer.from(r.data,'base64'));}
async function inspect(){return evaluate('('+function(){
  const cards=Array.from(document.querySelectorAll('.network-device-card'));
  return {overflow:document.documentElement.scrollWidth>innerWidth,summaryWidth:document.querySelector('.network-summary-card').getBoundingClientRect().width,
    cards:cards.map(e=>{const r=e.getBoundingClientRect(),fields={};e.querySelectorAll('dt').forEach(dt=>{fields[dt.textContent]=dt.nextElementSibling.textContent;});
      return {id:e.getAttribute('data-network-device'),name:e.querySelector('h2').textContent,state:e.querySelector('.network-state').textContent,fields,
        left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,overflow:e.scrollWidth>e.clientWidth+1};}),
    qualityTop:document.getElementById('network-quality').getBoundingClientRect().top,gridBottom:document.getElementById('network-devices').getBoundingClientRect().bottom,
    sharedOrder:latestDashboardData.devices.map(d=>d.device_id),miniOrder:Array.from(document.querySelectorAll('#mini-devices [data-device]')).map(e=>e.getAttribute('data-device'))};
}.toString()+')()');}
function rows(cards){const result=[];for(const card of cards){let row=result.find(r=>Math.abs(r[0].top-card.top)<1);if(!row){row=[];result.push(row);}row.push(card);}return result.map(r=>r.length);}
async function run(){
  await cdp('Browser.getVersion',{},undefined);
  const target=await cdp('Target.createTarget',{url:'about:blank'},undefined),attached=await cdp('Target.attachToTarget',{targetId:target.targetId,flatten:true},undefined);session=attached.sessionId;
  await cdp('Page.enable');await cdp('Runtime.enable');await cdp('Fetch.enable',{patterns:[{urlPattern:'*'}]});
  await cdp('Emulation.setTimezoneOverride',{timezoneId:'America/Toronto'});
  await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await cdp('Page.navigate',{url:'http://portal.test/'});
  await until('document.querySelectorAll(".network-device-card").length===5');
  await evaluate('document.getElementById("tab-network").click()');await paint();
  const report=[];
  for(const width of [1440,768,390]){
    context.width=width;context.step='verify five-card layout and fields';
    await cdp('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:width===390});await paint();
    const actual=await inspect();assert(!actual.overflow&&!actual.cards.some(c=>c.overflow),'No horizontal overflow at '+width);
    assert.deepEqual(actual.cards.map(c=>c.id),order);assert.deepEqual(actual.sharedOrder,devices.map(d=>d.device_id));
    assert.deepEqual(actual.miniOrder,devices.map(d=>d.device_id),'Device mini cards retain their own order');
    assert.deepEqual(rows(actual.cards),width===1440?[3,2]:width===768?[2,2,1]:[1,1,1,1,1]);
    if(width===1440)assert(actual.cards.every(c=>Math.abs(c.width-actual.summaryWidth)<1),'Device and summary card widths match');
    assert(actual.qualityTop>=actual.gridBottom,'Cards do not overlap Network quality');
    for(const card of actual.cards){
      const source=devices.find(d=>d.device_id===card.id);assert.equal(card.name,source.display_name);
      assert.equal(card.fields['LAN IP'],source.lan_ip);assert.equal(card.fields['ZeroTier IP'],source.zerotier_ip);
      const expected=await evaluate('new Date('+JSON.stringify(source.last_seen.replace(' ','T')+'Z')+').toLocaleString()');
      assert.equal(card.fields['Last Seen / 最后心跳'],expected);
      assert.equal(card.state,source.beszel_status==='up'?'ONLINE / 在线':source.beszel_status?'OFFLINE / 离线':'UNKNOWN / 未知');
      assert.equal(card.fields['Uptime / 本次开机'],source.device_id==='up-long'?'2d 0h':source.device_id==='up-short'?'1h 0m':undefined);
    }
    report.push({width,rows:rows(actual.cards),overflow:false,order:actual.cards.map(c=>c.id)});await screenshot(width+'-five-cards');
    console.log(width+'px: order, local heartbeat, online uptime, '+rows(actual.cards).join('+')+' layout and no overflow passed');
  }
  context.step='verify missing fields, long content and escaping';
  dashboard={...dashboard,devices:[{device_id:'missing-online',display_name:'Long_online_device_name_'.repeat(8)+'<img src=x onerror="bad()">',beszel_status:'up'},
    {device_id:'zero-online',display_name:'Zero uptime',beszel_status:'up',uptime_seconds:0,lan_ip:'192.0.2.10'},
    {device_id:'missing-offline',display_name:'Offline without heartbeat',beszel_status:'down',lan_ip:'<img src=x onerror="bad()">'}]};
  await evaluate('loadDashboard()');await until('document.querySelectorAll(".network-device-card").length===3');await paint();
  const missing=await inspect();assert(!missing.overflow&&!missing.cards.some(c=>c.overflow));
  assert.deepEqual(missing.cards.map(c=>c.id),['zero-online','missing-online','missing-offline']);
  assert.equal(missing.cards[0].fields['Uptime / 本次开机'],'0m');assert.equal(missing.cards[1].fields['Uptime / 本次开机'],'—');
  assert.equal(missing.cards[1].fields['LAN IP'],'—');assert.equal(missing.cards[1].fields['ZeroTier IP'],'—');assert.equal(missing.cards[1].fields['Last Seen / 最后心跳'],'—');
  assert.equal(missing.cards[2].fields['Last Seen / 最后心跳'],'—');assert.equal(missing.cards[2].fields['Uptime / 本次开机'],undefined);
  assert.equal(await evaluate('document.querySelectorAll("#network-devices img,#network-devices script").length'),0);
  await screenshot('390-missing-and-long');assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(output,'acceptance.json'),JSON.stringify({report,missing:true,pageErrors:errors},null,2));console.log('Browser artifacts: '+output);
}
run().catch(async error=>{
  console.error('Device card acceptance failed: '+JSON.stringify(context));console.error(error.stack||error.message);
  if(session&&!exited){try{fs.writeFileSync(path.join(output,'failure.html'),await evaluate('document.documentElement.outerHTML'));await screenshot('failure');}catch(e){context.diagnosticError=e.message;}}
  fs.writeFileSync(path.join(output,'failure.json'),JSON.stringify({...context,error:error.message,errors},null,2));console.error('Browser artifacts: '+output);process.exitCode=1;
}).finally(()=>browser.kill());
