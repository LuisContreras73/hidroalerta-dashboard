const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../docs/consola.html'),'utf8');
const source=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]).join('\n');
const live=fs.readFileSync(path.join(__dirname,'../docs/consola-live.js'),'utf8');
const nodes=new Map();
const node=id=>{if(!nodes.has(id))nodes.set(id,{textContent:'',style:{},value:'',previousElementSibling:{},showModal(){this.open=true;},close(){this.open=false;}});return nodes.get(id);};
let intervals=new Map(),timeId=0,fetchImpl;
const context=vm.createContext({console,Date,URL,AbortController,Number,Math,JSON,
 document:{getElementById:node,querySelector:s=>node(s.slice(1)),addEventListener(){}},
 location:{protocol:'http:'},localStorage:{getItem(){return null;},setItem(){}},
 Plotly:{react(){}},addEventListener(){},
 clearInterval:id=>intervals.delete(id),clearTimeout(){},
 setInterval:fn=>{intervals.set(++timeId,fn);return timeId;},setTimeout:()=>++timeId,
 fetch:(...args)=>fetchImpl(...args)});
vm.runInContext(source+'\n'+live,context);
const run=s=>vm.runInContext(s,context);
const flush=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 run('start()');
 assert.equal(node('modo').textContent,'SIN CONFIGURAR');
 assert.equal(node('s_nivel').textContent,'—');
 context.sample={station:'est_santo_domingo_01',latest:{nivel_cm:{value:123,ts:new Date().toISOString(),device:'nivel_01'},suelo:{value:0,ts:new Date().toISOString(),device:'suelo_01'}},history:[]};
 run('renderSnapshot(sample)');
 assert.equal(node('s_nivel').textContent,'1.23');
 assert.equal(node('s_turb').textContent,'0.0');
 assert.equal(node('s_caudal').textContent,'—');
 assert.equal(node('k_prob').textContent,'—');
 assert.equal(node('modo').textContent,'EN VIVO');
 context.sample.latest.suelo.ts=new Date(Date.now()-180000).toISOString();
 run('renderSnapshot(sample)');
 assert.equal(node('s_turb').textContent,'—');
 assert.equal(node('modo').textContent,'EN VIVO · PARCIAL');
 assert.throws(()=>run("validAPI('http://public.example')"));
 assert.throws(()=>run("validAPI('https://api.example/?token=secret')"));
 assert.equal(run("validAPI('https://api.example')"),'https://api.example');
 fetchImpl=async()=>({ok:false,status:401});
 run("startLive('http://localhost:8787','est_santo_domingo_01','read-test-key')");
 await flush();
 assert.equal(node('modo').textContent,'DESCONECTADO');
 assert.equal(node('s_nivel').textContent,'—');
 assert.equal(run('timer'),null);
 let resolveOld;
 fetchImpl=()=>new Promise(resolve=>resolveOld=resolve);
 run("startLive('http://localhost:8787','est_santo_domingo_01','read-test-key')");
 run('startDemo()');
 resolveOld({ok:true,json:async()=>context.sample});
 await flush();
 assert.equal(node('modo').textContent,'DEMOSTRACIÓN · HISTÓRICO');
 run('stopLive()');
 assert.equal(intervals.size,0);
 console.log('PASS: estado inicial, suelo cero, unidades, caducidad por sensor, sin caudal inventado, URL segura, error 401, respuesta tardía y limpieza de temporizadores.');
})().catch(error=>{console.error(error);process.exitCode=1;});
