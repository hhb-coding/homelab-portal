/* Optional real-browser layout regression. Node built-ins only; no live Portal APIs.
 * Run: CHROME_BIN=/opt/google/chrome/chrome node tests/test_offline_layout.js
 */
const fs = require('fs'), cp = require('child_process'), http = require('http'), assert = require('assert');
const chromeBin = process.env.CHROME_BIN || '/opt/google/chrome/chrome';
const profile = fs.mkdtempSync('/tmp/portal-offline-layout-');
let chrome, ws, server;
const sleep = ms => new Promise(r => setTimeout(r, ms));
let online = false;
const sample = () => ({status:'ok',server_time:Date.now()/1000,sources:{metrics_status:'ok'},devices:[
  {device_id:'a',display_name:'Offline Device',beszel_status:online?'up':'down',last_seen:new Date(Date.now()-3720000).toISOString()},
  {device_id:'b',display_name:'Multi-day Offline',beszel_status:online?'up':'paused',last_seen:new Date(Date.now()-7*86400000-3720000).toISOString()},
  {device_id:'c',display_name:'Missing Time',beszel_status:online?'up':'down'},
  {device_id:'d',display_name:'Online Device',beszel_status:'up'}]});
(async () => {
 server = http.createServer((req,res) => {
  const path = req.url.split('?')[0];
  if(path.startsWith('/api/')) {res.setHeader('Content-Type','application/json');res.end(JSON.stringify(path==='/api/dashboard'?sample():{status:'ok',devices:[]}));return;}
  if(path==='/' || path==='/lite') {
   let html=fs.readFileSync('templates/'+(path==='/'?'index':'lite')+'.html','utf8');
   html=html.replace(/\{\{ app_name \}\}/g,'HomeLab Portal Test').replace(/\{\{ url_for\('static', filename='([^']+)'\) \}\}/g,'/static/$1')
     .replace(/\{\{ url_for\('lite'\) \}\}/g,'/lite').replace(/\{\{ url_for\('index'\) \}\}/g,'/');
   res.setHeader('Content-Type','text/html');res.end(html);return;
  }
  if(/^\/static\/[a-z-]+\.(js|css)$/.test(path)) {res.setHeader('Content-Type',path.endsWith('.js')?'application/javascript':'text/css');res.end(fs.readFileSync('.'+path));return;}
  res.writeHead(404);res.end();
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const base='http://127.0.0.1:'+server.address().port;
 chrome=cp.spawn(chromeBin,['--headless','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{stdio:'ignore'});
 let port;
 for(let i=0;i<100;i++){try{port=fs.readFileSync(profile+'/DevToolsActivePort','utf8').split('\n')[0];break;}catch(e){await sleep(100);}}
 assert(port,'Chrome unavailable');
 const targets=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
 ws=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);
 await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
 let id=0,pending={};ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id&&pending[m.id]){pending[m.id](m);delete pending[m.id];}};
 function send(method,params={}){return new Promise((resolve,reject)=>{const n=++id;pending[n]=m=>m.error?reject(Error(JSON.stringify(m.error))):resolve(m.result);ws.send(JSON.stringify({id:n,method,params}));});}
 async function evalJS(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true});assert(!r.exceptionDetails,JSON.stringify(r.exceptionDetails));return r.result.value;}
 await send('Page.enable');
 for(const path of ['/','/lite']) {
  online=false;await send('Page.navigate',{url:base+path});
  for(let i=0;i<100;i++){if(await evalJS('document.querySelectorAll(".offline-seen").length === 3'))break;await sleep(100);}
  assert(await evalJS('document.querySelectorAll(".offline-seen").length === 3'));
  for(const width of [320,375,768,1024]) {
   await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});await sleep(100);
   const layout=await evalJS(`(function(){var items=document.querySelectorAll('.offline-seen'),ok=true,aligned=true;for(var i=0;i<items.length;i++){var r=items[i].getBoundingClientRect(),p=items[i].parentNode.getBoundingClientRect();ok=ok&&r.right<=innerWidth&&items[i].scrollWidth<=items[i].clientWidth+1;if(document.querySelector('.mini-card')){var s=items[i].previousSibling.getBoundingClientRect();aligned=aligned&&r.left>=s.right-1&&Math.abs(r.top-s.top)<=1;}}return {width:innerWidth,scroll:document.documentElement.scrollWidth,ok:ok,aligned:aligned};}())`);
   assert(layout.ok&&layout.aligned&&layout.scroll<=layout.width+1,JSON.stringify(layout));
   console.log(path,'offline layout PASS',width);
  }
  // Tick retained DOM without a request; then confirm actual online polling removes hints.
  await evalJS('OfflineSeen.sync(Date.now()/1000+120); OfflineSeen.update()');
  assert(await evalJS('document.querySelector(".offline-seen").textContent.indexOf("1h 04m ago") >= 0'));
  online=true;
  for(let i=0;i<70;i++){if(await evalJS('document.querySelectorAll(".offline-seen").length === 0'))break;await sleep(100);}
  assert(await evalJS('document.querySelectorAll(".offline-seen").length === 0'));
  console.log(path,'ONLINE recovery hides all hints PASS');
 }
})().then(()=>{if(ws)ws.close();if(chrome)chrome.kill('SIGTERM');if(server)server.close();}).catch(e=>{console.error(e);if(ws)ws.close();if(chrome)chrome.kill('SIGTERM');if(server)server.close();process.exitCode=1;});
