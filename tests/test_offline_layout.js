/* Optional real-browser layout regression. Node built-ins only; no live Portal APIs.
 * Run: CHROME_BIN=/opt/google/chrome/chrome node tests/test_offline_layout.js
 */
const fs = require('fs'), cp = require('child_process'), http = require('http'), assert = require('assert');
const chromeBin = process.env.CHROME_BIN || '/opt/google/chrome/chrome';
const profile = fs.mkdtempSync('/tmp/portal-offline-layout-');
let chrome, ws, server;
const sleep = ms => new Promise(r => setTimeout(r, ms));
let online = false, performanceRequests = [];
const sample = () => ({status:'ok',server_time:Date.now()/1000,sources:{metrics_status:'ok'},devices:[
  {device_id:'a',performance_history_supported:true,display_name:'Offline Device',beszel_status:online?'up':'down',last_seen:new Date(Date.now()-3720000).toISOString()},
  {device_id:'b',display_name:'Multi-day Offline Device With A Very Long Name That Wraps',beszel_status:online?'up':'paused',last_seen:new Date(Date.now()-7*86400000-3720000).toISOString()},
  {device_id:'c',display_name:'Missing Time',beszel_status:online?'up':'down'},
  {device_id:'d',performance_history_supported:true,display_name:'Online Device',beszel_status:'up',metrics_available:true,temperature:42,cpu_frequency_ghz:1.4}]});
(async () => {
 server = http.createServer((req,res) => {
  const path = req.url.split('?')[0];
  if(path==='/api/history/v2/performance') {
   const params=new URL(req.url,'http://localhost').searchParams;
   const start=params.get('start'),end=params.get('end'),base=Date.parse(start),seconds=(Date.parse(end)-base)/1000;
   const width=seconds<=3600?60:seconds<=21600?300:seconds<=86400?900:Math.ceil(seconds/500/60)*60;
   const count=Math.ceil(seconds/width);
   performanceRequests.push({device:params.get('device_id'),seconds,width,count,extended:params.get('extended')});
   res.setHeader('Content-Type','application/json');
   res.end(JSON.stringify({status:'ok',device_id:params.get('device_id'),start,end,bucket_seconds:width,mapping_note:'Current mapping / 当前关联',
    series:(params.get('extended')==='1'?['CPU Frequency','CPU Usage','CPU Temperature','Memory Usage','Disk Usage','Upload','Download']:['CPU Frequency','CPU Usage','CPU Temperature']).map((label,i)=>({label,metric:['cpu_frequency_ghz','cpu_percent','cpu_temperature_c','memory_percent','disk_percent','network_upload_bytes_per_second','network_download_bytes_per_second'][i],unit:['GHz','%','°C','%','%','B/s','B/s'][i],stats:{count:count-1,average:2,peak:3},points:Array.from({length:count},(_,n)=>({timestamp:new Date(base+n*width*1000).toISOString(),value:n===2?null:n%3+1,count:n===2?0:1,gap:n===3}))}))}));return;
  }
  if(path==='/api/history') {res.setHeader('Content-Type','application/json');res.end(JSON.stringify({status:'ok',devices:[{device_id:'a',points:[{timestamp:new Date(Date.now()-60000).toISOString(),cpu_percent:10},{timestamp:new Date().toISOString(),cpu_percent:20}]}]}));return;}
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
   if(path==='/lite') {
    // Temp/Freq stays below metrics and wraps without horizontal overflow.
    // 温度/频率位于指标下方，窄屏换行且不产生横向溢出。
    assert(await evalJS(`(function(){
      var rows=document.querySelectorAll('.temp-freq');
      if(rows.length!==4 || rows[3].textContent!=='Temp/Freq: 42.0 °C / 1.40 GHz'){return false;}
      for(var i=0;i<rows.length;i++){
        var r=rows[i].getBoundingClientRect(),m=rows[i].previousSibling.getBoundingClientRect();
        if(r.top<m.bottom || r.right>innerWidth || rows[i].scrollWidth>rows[i].clientWidth+1){return false;}
      }
      return document.documentElement.scrollWidth<=innerWidth;
    }())`), 'Lite Temp/Freq layout at '+width);
   }
   const layout=await evalJS(`(function(){
     var items=document.querySelectorAll('.offline-seen'),ok=true,aligned=true,styles=true;
     function textRect(node){var range=document.createRange();range.selectNodeContents(node);return range.getClientRects()[0];}
     for(var i=0;i<items.length;i++){
       var note=items[i],r=note.getBoundingClientRect(),style=getComputedStyle(note);
       ok=ok&&r.right<=innerWidth&&note.scrollWidth<=note.clientWidth+1;
       styles=styles&&style.fontSize==='13px'&&style.color==='rgb(85, 85, 85)'&&style.fontWeight==='400';
       var isFull=!!document.querySelector('.mini-card');
       var status=note.previousSibling;
       var a=textRect(status),b=textRect(note);
       if(a&&b){aligned=aligned&&(b.top>=a.bottom+3);}
       styles=styles&&style.display==='block'&&parseFloat(style.marginLeft)===0;
       var name=isFull?note.parentNode.firstChild:note.nextSibling;
       var n=textRect(name);
       aligned=aligned&&(isFull?n.bottom<=a.top:n.top>=b.bottom+5);
       if(isFull){aligned=aligned&&note.parentNode.nextSibling.getBoundingClientRect().top>=r.bottom;}
       var red=getComputedStyle(isFull?status.firstChild:status);
       styles=styles&&red.fontWeight==='700'&&(red.color==='rgb(160, 0, 32)');
       if(i===0){ok=ok&&/^Last seen: (?:\\d{4}-\\d{2}-\\d{2} )?\\d{2}:\\d{2} \\(1h 2m ago\\)$/.test(note.textContent);}
       if(i===1){ok=ok&&/^Last seen: \\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2} \\(7d 1h 2m ago\\)$/.test(note.textContent);}
       if(i===2){ok=ok&&note.textContent==='Last seen: —';}
     }
     var cards=document.querySelectorAll('.mini-card'),grid=true;
     if(cards.length===4){
       var expected=innerWidth>800?4:innerWidth>600?2:1;
       for(var j=0;j<cards.length;j++){
         var c=cards[j].getBoundingClientRect();
         grid=grid&&Math.abs(c.height-cards[0].getBoundingClientRect().height)<=1&&cards[j].scrollHeight<=cards[j].clientHeight+1;
         if(j%expected){var prev=cards[j-1].getBoundingClientRect();grid=grid&&Math.abs(c.top-prev.top)<=1&&c.left>=prev.right;}
         else if(j){grid=grid&&c.top>=cards[j-expected].getBoundingClientRect().bottom;}
       }
     }
     return {width:innerWidth,scroll:document.documentElement.scrollWidth,ok:ok,aligned:aligned,styles:styles,grid:grid};
   }())`);
   assert(layout.ok&&layout.aligned&&layout.styles&&layout.grid&&layout.scroll<=layout.width+1,JSON.stringify(layout));
   console.log(path,'offline layout PASS',width);
  }
  // Tick retained DOM without a request; then confirm actual online polling removes hints.
  await evalJS('OfflineSeen.sync(Date.now()/1000+120); OfflineSeen.update()');
  assert(await evalJS('document.querySelector(".offline-seen").textContent.indexOf("(1h 4m ago)") >= 0'));
  online=true;
  for(let i=0;i<70;i++){if(await evalJS('document.querySelectorAll(".offline-seen").length === 0'))break;await sleep(100);}
  assert(await evalJS('document.querySelectorAll(".offline-seen").length === 0'));
  assert(await evalJS('Array.prototype.every.call(document.querySelectorAll(".mini-card"),function(c){return c.style.height === "";})'));
  console.log(path,'ONLINE recovery hides all hints PASS');
  if(path==='/') {
   for(let i=0;i<50;i++){if(await evalJS('document.querySelectorAll("#performance-detail svg").length===3'))break;await sleep(100);}
   assert(await evalJS('document.querySelectorAll("#performance-detail svg").length===3'));
   assert(await evalJS('document.getElementById("devices").textContent.indexOf("Live trends")>=0 && document.getElementById("devices").textContent.indexOf("Historical trends")>=0'));
   assert(await evalJS('document.getElementById("performance-detail-range").value==="24"'));
   for(const [hours,width,count] of [[1,60,60],[6,300,72],[24,900,96]]) {
    const before=performanceRequests.length;
    await evalJS('document.getElementById("performance-detail-range").value="'+hours+'";document.getElementById("performance-detail-range").dispatchEvent(new Event("change"))');
    for(let i=0;i<50;i++){if(await evalJS('document.querySelectorAll("#performance-detail svg").length===3'))break;await sleep(100);}
    assert.strictEqual(performanceRequests.length,before+1,'Single shared request');
    assert.deepStrictEqual(performanceRequests[performanceRequests.length-1],{device:'a',seconds:hours*3600,width,count,extended:null});
    assert(await evalJS(`(function(){var a=document.querySelectorAll('#performance-detail .performance-time-axis');return a.length===3&&a[0].innerHTML===a[1].innerHTML&&a[1].innerHTML===a[2].innerHTML&&document.querySelectorAll('#performance-detail circle').length===0&&document.querySelectorAll('#performance-detail .chart-isolated').length===3&&document.querySelectorAll('#performance-detail .device-history-y-axis')[1].textContent.indexOf('4.0 %')>=0;}())`),'Shared axes and adaptive usage without circles');
   }

   for(const width of [320,375,768,1024]) {
    await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});await sleep(100);
    assert(await evalJS(`(function(){var b=document.querySelectorAll('#performance-detail .chart-box'),a=b[0].getBoundingClientRect(),c=b[1].getBoundingClientRect(),d=b[2].getBoundingClientRect();return document.documentElement.scrollWidth<=innerWidth+1&&(innerWidth>600?Math.abs(a.top-c.top)<1&&Math.abs(c.top-d.top)<1&&c.left>=a.right&&d.left>=c.right:c.top>=a.bottom&&d.top>=c.bottom);}())`),'Three-chart layout '+width);
    assert(await evalJS(`(function(){
      var boxes=document.querySelectorAll('#performance-detail .chart-box');
      var expected=[['3.16 GHz','2.00 GHz','0.84 GHz'],['4.0 %','2.0 %','0.0 %'],['3.2 °C','2.0 °C','0.8 °C']];
      if(document.querySelectorAll('#performance-detail .chart-axis').length!==0){return false;}
      for(var i=0;i<boxes.length;i++){
        var box=boxes[i].getBoundingClientRect(),svg=boxes[i].querySelector('svg'),r=svg.getBoundingClientRect();
        var ticks=boxes[i].querySelectorAll('.device-history-y-axis span'),axis=boxes[i].querySelector('.performance-time-axis').getBoundingClientRect();
        var reference=svg.querySelector('.device-history-reference');
        if(ticks.length!==3 || !reference || reference.getAttribute('d')!=='M0,5 H300 M0,60 H300 M0,115 H300'
            || getComputedStyle(svg).height!=='120px' || r.width<80 || axis.top<r.bottom || axis.right>box.right+1){return false;}
        for(var j=0;j<3;j++){
          var t=ticks[j].getBoundingClientRect(),p=svg.createSVGPoint();p.y=[5,60,115][j];
          if(ticks[j].textContent!==expected[i][j] || t.left<box.left || t.right>r.left-3
              || Math.abs((t.top+t.bottom)/2-p.matrixTransform(svg.getScreenCTM()).y)>0.6){return false;}
        }
      }
      return true;
    }())`),'Device Y ticks match SVG coordinates without overlap at '+width);
   }
   await evalJS('document.getElementById("performance-detail-range").value="6";document.getElementById("performance-detail-range").dispatchEvent(new Event("change"));selectDeviceCard({getAttribute:function(){return "d";}})');
   for(let i=0;i<50;i++){if(await evalJS('document.querySelectorAll("#performance-detail svg").length===3'))break;await sleep(100);}
   assert(await evalJS('document.getElementById("performance-detail-range").value==="6"'));
   await evalJS('document.getElementById("tab-history").click()');
   for(let i=0;i<50;i++){if(await evalJS('document.querySelectorAll("#history-result svg").length===6'))break;await sleep(100);}
   assert(await evalJS('document.querySelectorAll("#history-device option").length===2 && document.querySelectorAll("#history-result svg").length===6'));
   assert.strictEqual(performanceRequests[performanceRequests.length-1].extended,'1','Only History opts into extended API');
   assert(await evalJS('document.getElementById("history-result").textContent.indexOf("Peak / 峰值")>=0'));
   for(const width of [320,375,768,1024]) {
    await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});await sleep(100);
    assert(await evalJS(`(function(){
      var boxes=document.querySelectorAll('#history-result .chart-box'),left=null,previous=null;
      if(boxes.length!==6 || document.querySelectorAll('#history-result .chart-axis').length!==0){return false;}
      for(var i=0;i<boxes.length;i++){
        var r=boxes[i].getBoundingClientRect(),svg=boxes[i].querySelector('svg').getBoundingClientRect();
        var ticks=boxes[i].querySelectorAll('.history-y-axis span');
        if(ticks.length!==3 || ticks[0].getBoundingClientRect().right>svg.left || (left!==null&&Math.abs(left-svg.left)>1)){return false;}
        if(previous!==null&&r.top<previous || boxes[i].scrollWidth>boxes[i].clientWidth+1){return false;}
        left=svg.left;previous=r.bottom;
      }
      var axes=document.querySelectorAll('#history-result .performance-time-axis');
      return axes.length===6&&Array.prototype.every.call(axes,function(a){return a.innerHTML===axes[0].innerHTML;})
        &&document.querySelectorAll('#history-result .chart-line.history-upload').length>0
        &&document.querySelectorAll('#history-result .chart-line.history-download').length>0
        &&document.documentElement.scrollWidth<=innerWidth+1;
    }())`),'Six rows, left Y ticks, shared time axes and network at '+width);
   }
   await evalJS('document.getElementById("history-device").value="d";document.getElementById("history-range").value="30";document.getElementById("history-device").onchange()');
   for(let i=0;i<50;i++){if(await evalJS('document.querySelectorAll("#history-result svg").length===6'))break;await sleep(100);}
   assert(await evalJS('document.querySelectorAll("#history-result svg").length===6'));
   await evalJS('document.getElementById("history-range").value="custom";document.getElementById("history-range").onchange();document.getElementById("history-start").value="2026-01-01T00:00";document.getElementById("history-end").value="2026-01-02T00:00";document.getElementById("history-form").onsubmit()');
   for(let i=0;i<50;i++){if(await evalJS('document.querySelectorAll("#history-result svg").length===6'))break;await sleep(100);}
   assert(await evalJS('document.getElementById("history-result").textContent.indexOf("Local (UTC")>=0'));
   assert(await evalJS('document.getElementById("history-start").type === "datetime-local"'));
   for (const width of [320,375,768,1024]) {
    await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});
    assert(await evalJS('document.documentElement.scrollWidth <= innerWidth+1'), 'Custom controls overflow at '+width);
   }
   await send('Emulation.setTimezoneOverride', {timezoneId:'America/Montreal'});
   await evalJS('document.getElementById("history-start").value="2026-01-01T10:00";document.getElementById("history-end").value="2026-01-01T11:00";document.getElementById("history-start").oninput();document.getElementById("history-end").oninput()');
   assert(await evalJS('["history-start-choice-label","history-end-choice-label"].every(function(id){return getComputedStyle(document.getElementById(id)).display === "none";})'), 'Ordinary dates hide both occurrence labels');
   await evalJS('document.getElementById("history-start").value="2026-11-01T01:30";document.getElementById("history-start").oninput()');
   assert(await evalJS('getComputedStyle(document.getElementById("history-start-choice-label")).display === "inline-block" && getComputedStyle(document.getElementById("history-end-choice-label")).display === "none"'), 'Only ambiguous endpoint shows occurrence');
   await evalJS('document.getElementById("history-end").value="2026-11-01T01:45";document.getElementById("history-end").oninput()');
   assert(await evalJS('getComputedStyle(document.getElementById("history-end-choice-label")).display === "inline-block"'), 'Ambiguous end shows occurrence');
   for (const width of [320,375]) {
    await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});
    assert(await evalJS('document.documentElement.scrollWidth <= innerWidth+1'), 'Occurrence controls overflow at '+width);
   }
   const retainedInput = await evalJS('document.getElementById("history-start").value');
   await evalJS('renderDevicePanels([])');
   assert.strictEqual(await evalJS('document.getElementById("history-start").value'), retainedInput);
   console.log('Performance history: Device left Y ticks align to SVG; three-column responsiveness and History six rows preserved at 320/375/768/1024; Local/DST and API modes PASS');
  }

 }
})().then(()=>{if(ws)ws.close();if(chrome)chrome.kill('SIGTERM');if(server)server.close();}).catch(e=>{console.error(e);if(ws)ws.close();if(chrome)chrome.kill('SIGTERM');if(server)server.close();process.exitCode=1;});
