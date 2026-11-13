/* Cached Chromium, synthetic APIs, CDP pipe / 缓存浏览器与合成 API，无外网访问。 */
'use strict';
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn,spawnSync}=require('node:child_process'),assert=require('node:assert/strict');
const output=process.env.ENDPOINT_B_ARTIFACTS_DIR||fs.mkdtempSync(path.join(os.tmpdir(),'portal-endpoint-b-browser-'));
fs.mkdirSync(output,{recursive:true});
const fixture=spawnSync(process.env.NETWORK_BROWSER_PYTHON||'python3',['-B','tools/network_readability_fixture.py',output],{encoding:'utf8'});
assert.equal(fixture.status,0,fixture.stdout+fixture.stderr);
const responses=JSON.parse(fs.readFileSync(path.join(output,'responses.json'),'utf8'));
const base=JSON.parse(responses['/api/history/v3/network?range=1h'].body);
const executable=process.env.CHROMIUM_BINARY||path.join(os.homedir(),'.cache/ms-playwright/chromium-1187/chrome-linux/chrome');
const browser=spawn(executable,['--headless','--no-sandbox','--no-first-run','--no-default-browser-check',
  '--disable-background-networking','--disable-crashpad-for-testing','--disable-gpu','--disable-dev-shm-usage','--remote-debugging-pipe',
  '--user-data-dir='+path.join(output,'profile')],{stdio:['ignore','ignore','pipe','pipe','pipe']});
let sequence=0,buffer='',session,stderr='',exited=false,mode='unique',ready=false,saved=false,active=false,scans=0,saveCalls=0;
const pending=new Map(),errors=[],report=[],ip='192.0.2.99';
function state(){return {status:'ok',discovery:{id:'synthetic-discovery',status:mode,matches:mode==='unique'?[ip]:mode==='multiple'?[ip,'192.0.2.100']:[]},
  monitors:ready?[{id:'new-hp-icmp',target:ip,interval:10}]:[],selected_monitor_id:ready?'new-hp-icmp':null,
  can_save:ready&&mode==='unique',probe_status:ready?'ready':'waiting_beszel',mapping:saved?{monitor_id:'new-hp-icmp',target:ip}:null};}
function cdp(method,params={},sessionId=session){return new Promise((resolve,reject)=>{
  if(exited)return reject(Error('Chromium exited: '+stderr));
  const id=++sequence,timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout: '+method+': '+stderr));},30000);
  pending.set(id,{resolve,reject,timer});browser.stdio[3].write(JSON.stringify({id,method,params,sessionId})+'\0');
});}
function rejectAll(error){for(const p of pending.values()){clearTimeout(p.timer);p.reject(error);}pending.clear();}
for(const pipe of [browser.stdio[3],browser.stdio[4]])pipe.on('error',()=>{});
browser.on('error',error=>{exited=true;rejectAll(error);});
browser.on('exit',(code,signal)=>{exited=true;rejectAll(Error('Chromium exited '+(signal||code)+': '+stderr));});
browser.stderr.on('data',data=>{stderr=(stderr+data).slice(-6000);});
async function response(params,sessionId){
  const url=new URL(params.request.url);let status=200,type='application/json',body='';
  if(url.pathname==='/api/network/endpoint-b/discover'){
    scans+=1;await new Promise(resolve=>setTimeout(resolve,150));body=JSON.stringify(state());
  }else if(url.pathname==='/api/network/endpoint-b'){
    if(params.request.method==='POST'){
      const payload=JSON.parse(params.request.postData);assert.equal(payload.monitor_id,'new-hp-icmp');assert.equal(payload.discovery_id,'synthetic-discovery');
      assert(ready&&mode==='unique');saved=true;saveCalls+=1;
    }
    body=JSON.stringify(state());
  }else if(url.pathname==='/api/history/v3/network'){
    const data=JSON.parse(JSON.stringify(base)),target=data.targets.find(t=>t.role==='endpoint_b');
    if(saved){
      target.target=ip;target.mapping_status=active?'active':'waiting_archive';target.monitor_id='new-hp-icmp';
      if(active){const point={time:data.end-60000,rtt_ms:3.5,loss_pct:0,count:6,success_count:6,failed_count:0};
        target.rows=[point];target.latest_sample=point;target.peak_loss_pct=0;}
    }
    body=JSON.stringify(data);
  }else if(url.pathname==='/static/endpoint-b.js'){
    type='application/javascript';body=fs.readFileSync('static/endpoint-b.js','utf8');
  }else{
    const found=responses[url.pathname];
    if(found){type=found.type;body=found.body;}else{status=404;type='text/plain';body='Not found';}
  }
  await cdp('Fetch.fulfillRequest',{requestId:params.requestId,responseCode:status,responseHeaders:[{name:'Content-Type',value:type}],
    body:Buffer.from(body).toString('base64')},sessionId);
}
browser.stdio[4].on('data',data=>{
  buffer+=data;let at;
  while((at=buffer.indexOf('\0'))>=0){
    const message=JSON.parse(buffer.slice(0,at));buffer=buffer.slice(at+1);
    if(message.id&&pending.has(message.id)){
      const p=pending.get(message.id);pending.delete(message.id);clearTimeout(p.timer);
      message.error?p.reject(Error(JSON.stringify(message.error))):p.resolve(message.result);
    }else if(message.method==='Fetch.requestPaused')response(message.params,message.sessionId).catch(e=>errors.push(e.stack||e.message));
    else if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);
  }
});
async function evaluate(expression){const r=await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});assert(!r.exceptionDetails,JSON.stringify(r.exceptionDetails));return r.result.value;}
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(expression){for(let i=0;i<150;i++){if(await evaluate(expression))return;await delay(50);}throw Error('Condition timed out: '+expression);}
async function click(id){await evaluate('document.getElementById('+JSON.stringify(id)+').click()');}
async function screenshot(name){
  await evaluate('document.querySelector("[data-network-card=endpoint_b]").scrollIntoView()');
  const r=await cdp('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(output,name+'.png'),Buffer.from(r.data,'base64'));
}
async function run(){
  await cdp('Browser.getVersion',{},undefined);
  const target=await cdp('Target.createTarget',{url:'about:blank'},undefined),attached=await cdp('Target.attachToTarget',{targetId:target.targetId,flatten:true},undefined);session=attached.sessionId;
  await cdp('Page.enable');await cdp('Runtime.enable');await cdp('Fetch.enable',{patterns:[{urlPattern:'*'}]});
  for(const width of [1440,768,390,320]){
    mode='unique';ready=false;saved=false;active=false;
    await cdp('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:width<600});
    await cdp('Emulation.setTouchEmulationEnabled',{enabled:width<600});
    await cdp('Page.navigate',{url:'http://portal.test/'});
    await until('typeof endpointBState!=="undefined" && endpointBState && document.getElementById("endpoint-b-discover")');
    await click('tab-network');
    assert(await evaluate('document.getElementById("endpoint-b-monitor").selectedOptions[0].textContent.indexOf("'+ip+'")>=0'));
    assert(await evaluate('document.getElementById("endpoint-b-save").disabled'));
    assert(await evaluate('document.getElementById("endpoint-b-controls").textContent.indexOf("请在 Beszel 更新探测目标")>=0'));
    await screenshot(width+'-waiting-beszel');
    mode='none';const before=scans;await click('endpoint-b-discover');await click('endpoint-b-discover');
    assert(await evaluate('document.getElementById("endpoint-b-discover").disabled'));
    await until('!endpointBBusy');assert.equal(scans,before+1);
    assert(await evaluate('document.getElementById("endpoint-b-controls").textContent.indexOf("未找到 TL-WDR5620")>=0'));
    assert(await evaluate('!document.getElementById("endpoint-b-save")'));
    mode='multiple';await click('endpoint-b-discover');await until('!endpointBBusy');
    assert(await evaluate('document.getElementById("endpoint-b-controls").textContent.indexOf("找到多个 TL-WDR5620")>=0'));
    assert(await evaluate('!document.getElementById("endpoint-b-save")'));
    mode='unique';await click('endpoint-b-discover');await until('!endpointBBusy');
    ready=true;await click('endpoint-b-refresh');await until('!endpointBBusy');
    assert.equal(await evaluate('document.getElementById("endpoint-b-monitor").value'),'new-hp-icmp');
    assert(!(await evaluate('document.getElementById("endpoint-b-save").disabled')));
    await click('endpoint-b-save');await until('!endpointBBusy && document.querySelector(".endpoint-b-mapping")');
    assert(await evaluate('document.querySelector(".endpoint-b-mapping").textContent.indexOf("等待首个归档样本")>=0'));
    assert.equal(await evaluate('document.querySelector("[data-network-card=endpoint_b] .network-target-ip").textContent'),ip);
    assert.equal(await evaluate('networkHistoryData.targets.find(t=>t.role==="endpoint_b").rows.length'),0);
    active=true;await evaluate('loadNetworkHistory()');await until('document.querySelector(".endpoint-b-mapping").textContent.indexOf("映射已生效")>=0');
    assert(await evaluate('document.querySelector("[data-network-card=endpoint_b]").textContent.indexOf("3.50 ms")>=0'));
    assert(await evaluate('document.querySelector("#network-rtt-private-chart [data-network-series=endpoint_b] .network-series").getAttribute("d").indexOf(" M")>=0'));
    await evaluate('document.querySelector("#network-rtt-private-chart [data-network-legend=endpoint_b]").click()');
    assert.equal(await evaluate('document.querySelector("#network-rtt-private-chart-stats .network-target-ip").textContent'),ip);
    const layout=await evaluate(`(function(){var e=document.getElementById('endpoint-b-controls'),r=e.getBoundingClientRect();return {
      overflow:document.documentElement.scrollWidth>innerWidth,controlOverflow:e.scrollWidth>e.clientWidth+1,
      buttons:Array.from(e.querySelectorAll('button,select')).every(n=>{var b=n.getBoundingClientRect();return b.left>=r.left-1 && b.right<=r.right+1;})};})()`);
    assert(!layout.overflow&&!layout.controlOverflow&&layout.buttons,JSON.stringify({width,layout}));
    await screenshot(width+'-active');report.push({width,layout,states:['none','multiple','waiting_beszel','ready','waiting_archive','active']});
    console.log(width+'px: discovery states, preselection, save, first sample, shared IP/curve and no overflow passed');
  }
  assert.equal(saveCalls,4);assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(output,'acceptance.json'),JSON.stringify({report,errors},null,2));console.log('Browser artifacts: '+output);
}
run().catch(async error=>{
  console.error(error.stack||error.message);console.error(stderr);process.exitCode=1;
  if(session&&!exited){try{await screenshot('failure');}catch(e){errors.push(e.message);}}
  fs.writeFileSync(path.join(output,'failure.json'),JSON.stringify({error:error.message,errors},null,2));console.error('Browser artifacts: '+output);
}).finally(()=>browser.kill());
