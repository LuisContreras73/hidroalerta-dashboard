// La clave de escritura nunca llega al navegador. Lectura cada 3 segundos.
const CFG={apiURL:'',station:'est_santo_domingo_01',pollMs:3000,staleMs:120000};
let liveTimer=null,freshnessTimer=null,activeRequest=null,generation=0,snapshot=null,readKey='';
const setText=(id,value)=>{document.getElementById(id).textContent=value;};
function stopLive(){
 generation++; clearInterval(timer); timer=null; clearTimeout(liveTimer); clearInterval(freshnessTimer);
 if(activeRequest)activeRequest.abort(); activeRequest=null; snapshot=null; readKey='';
}
function startDemo(){
 stopLive(); setText('modo','DEMOSTRACIÓN · HISTÓRICO'); setText('gate','datos de demostración');
 setText('age_nivel','simulado'); setText('age_suelo','simulado');
 ptr=firstObs(); drawMen(); tick(); timer=setInterval(tick,1400);
}
function neutralStatus(message){
 setText('estado','SIN EVALUACIÓN'); setText('k_prob','—');
 const lamp=document.getElementById('lamp'); lamp.style.background='#cdd8dc'; lamp.style.color='#cdd8dc';
 document.getElementById('estado').style.color=C.mut;
 setText('decision',message+' El pronóstico mostrado es histórico; no genera una alerta actual. El caudal requiere una medición o curva de aforo validada.');
}
function resetLiveView(){
 for(const id of ['s_nivel','s_caudal','s_temp','s_turb','s_bat','s_rssi','k_caudal','k_fecha'])setText(id,'—');
 setText('age_nivel','sin lecturas'); setText('age_suelo','sin lecturas');
 neutralStatus('Esperando telemetría real.');
 drawFC(D.ev.date.length-1); drawVer(D.ev.date.length-1); drawMen();
 Plotly.react('spark',[],Object.assign({},PLBASE,{xaxis:{visible:false},yaxis:{visible:false},annotations:[{text:'Nivel medido · esperando datos',showarrow:false,x:.5,y:.5,xref:'paper',yref:'paper'}]}),{displayModeBar:false});
}
function renderSnapshot(data){
 const latest=data.latest||{},now=Date.now();
 const fresh=r=>r&&Number.isFinite(r.value)&&Number.isFinite(Date.parse(r.ts))&&now-Date.parse(r.ts)<=CFG.staleMs&&Date.parse(r.ts)<=now+120000;
 const fields={nivel_cm:['s_nivel',100,2],suelo:['s_turb',1,1],temp_c:['s_temp',1,1],caudal_m3s:['s_caudal',1,1],bateria_v:['s_bat',1,2],rssi:['s_rssi',1,0]};
 for(const [field,[id,scale,digits]] of Object.entries(fields))setText(id,fresh(latest[field])?(latest[field].value/scale).toFixed(digits):'—');
 setText('k_caudal',fresh(latest.caudal_m3s)?latest.caudal_m3s.value.toFixed(1):'—');
 for(const [field,id] of [['nivel_cm','age_nivel'],['suelo','age_suelo']]){
  const r=latest[field];setText(id,r?`${r.device} · ${fresh(r)?'hace '+Math.max(0,Math.round((now-Date.parse(r.ts))/1000))+' s':'lectura antigua'}`:'sin lecturas');
 }
 const dates=Object.values(latest).map(r=>Date.parse(r.ts)).filter(Number.isFinite);
 setText('k_fecha',dates.length?new Date(Math.max(...dates)).toLocaleTimeString('es-PE',{hour:'2-digit',minute:'2-digit',second:'2-digit'}):'—');
 const count=[latest.nivel_cm,latest.suelo].filter(fresh).length;
 setText('modo',count===2?'EN VIVO':count===1?'EN VIVO · PARCIAL':dates.length?'DATOS ANTIGUOS':'SIN LECTURAS');
 setText('gate',count===2?'suelo y nivel actualizados':count===1?'falta un sensor actualizado':'esperando sensores');
 neutralStatus('Telemetría recibida; evaluación de riesgo no conectada.');
 const history=(data.history||[]).filter(r=>Number.isFinite(r.nivel_cm)&&Number.isFinite(Date.parse(r.ts)));
 const lastTime=history.length?Date.parse(history[history.length-1].ts):now;
 const firstTime=history.length?Date.parse(history[0].ts):now;
 Plotly.react('spark',[{x:history.map(r=>r.ts),y:history.map(r=>r.nivel_cm/100),mode:'lines+markers',line:{color:C.teal,width:2},connectgaps:false}],
  Object.assign({},PLBASE,{margin:{l:48,r:8,t:5,b:30},xaxis:{type:'date',tickformat:'%H:%M:%S',range:[Math.min(firstTime,lastTime-60000),lastTime+5000],title:{text:'UTC',font:{size:10}}},yaxis:{title:'nivel (m)'},uirevision:'telemetry'}),{displayModeBar:false});
}
function validAPI(value){
 const url=new URL(value);
 if(url.username||url.password||url.search||url.hash||url.pathname!=='/')throw Error('Usa solo el origen de la API, sin ruta, credenciales ni parámetros.');
 if(url.protocol!=='https:'&&!(url.protocol==='http:'&&['localhost','127.0.0.1'].includes(url.hostname)))throw Error('El receptor público debe usar HTTPS.');
 if(location.protocol==='https:'&&url.protocol!=='https:')throw Error('Desde GitHub Pages debes usar un receptor HTTPS.');
 return url.origin;
}
function startLive(url,station,key){
 stopLive();CFG.apiURL=url;CFG.station=station;readKey=key;
 resetLiveView();setText('modo','CONECTANDO');setText('gate','conectando al receptor');
 const run=generation;
 freshnessTimer=setInterval(()=>{if(snapshot&&run===generation)renderSnapshot(snapshot);},1000);
 async function poll(){
  if(run!==generation)return;
  const controller=new AbortController();activeRequest=controller;
  const timeout=setTimeout(()=>controller.abort(),8000);
  try{
   const response=await fetch(`${CFG.apiURL}/v1/stations/${encodeURIComponent(station)}/latest`,{headers:{Authorization:'Bearer '+readKey},cache:'no-store',signal:controller.signal});
   if(!response.ok)throw Error(response.status===401?'Clave de lectura inválida':`Receptor HTTP ${response.status}`);
   const data=await response.json();
   if(data.station!==station||!data.latest||!Array.isArray(data.history))throw Error('Respuesta incompatible con la consola');
   if(run!==generation)return;
   snapshot=data;renderSnapshot(data);
  }catch(e){
   if(run!==generation)return;
   snapshot=null;resetLiveView();setText('modo','DESCONECTADO');
   setText('gate',e.name==='AbortError'?'tiempo de espera agotado':e.message==='Failed to fetch'?'sin conexión o CORS no autorizado':e.message);
   neutralStatus('No se puede confirmar el estado de los sensores.');
  }finally{
   clearTimeout(timeout);if(run===generation){activeRequest=null;liveTimer=setTimeout(poll,CFG.pollMs);}
  }
 }
 poll();
}
function start(){
 resetLiveView();setText('modo','SIN CONFIGURAR');setText('gate','conecta el receptor de sensores');
 document.querySelector('#fc').previousElementSibling.textContent='Referencia histórica · 2024 · banda P10–P90 y Q90';
 document.querySelector('#ver').previousElementSibling.textContent='Verificación histórica · 2024';
 document.querySelector('#men').previousElementSibling.textContent='Referencia mensual · 2025–2026';
 const dialog=document.getElementById('connection');
 document.getElementById('configure').onclick=()=>dialog.showModal();
 document.getElementById('close-connection').onclick=()=>dialog.close();
 document.getElementById('demo-button').onclick=()=>{startDemo();document.getElementById('read-key').value='';dialog.close();};
 document.getElementById('connection-form').onsubmit=event=>{
  event.preventDefault();
  try{
   const url=validAPI(document.getElementById('api-url').value.trim()),station=document.getElementById('station-id').value.trim(),key=document.getElementById('read-key').value.trim();
   if(!/^[a-zA-Z0-9_-]{1,64}$/.test(station))throw Error('Identificador de estación inválido');
   if(key.length<32||key.startsWith('ghp_'))throw Error('Usa la clave de lectura del receptor; no el token de GitHub.');
   try{localStorage.setItem('hidroalerta.connection',JSON.stringify({url,station}));}catch(e){}
   startLive(url,station,key);document.getElementById('read-key').value='';setText('connection-error','');dialog.close();
  }catch(e){setText('connection-error',e.message);}
 };
 try{const saved=JSON.parse(localStorage.getItem('hidroalerta.connection')||'null');if(saved){document.getElementById('api-url').value=validAPI(saved.url);document.getElementById('station-id').value=saved.station;}}catch(e){}
}
