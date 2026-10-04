'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {Reader,allowed,credential,fingerprint,inspect,SCOPES}=require('./firebase_readonly.cjs');
test('reject every Hosting mutating verb before network',async()=>{
 let calls=0;const r=new Reader('SYNTHETIC',async()=>{calls++;return {};});
 for(const verb of ['POST','PUT','PATCH','DELETE'])await assert.rejects(()=>r.request(verb,'https://firebasehosting.googleapis.com/v1beta1/sites/kp4ara-license-academy'));
 assert.equal(calls,0);
});
test('restrict known HTTPS hosts and project',()=>{
 assert(allowed('https://firebasehosting.googleapis.com/v1beta1/sites/kp4ara-license-academy/versions/abc/files?status=ACTIVE'));
 for(const url of ['http://firebasehosting.googleapis.com/v1beta1/sites/kp4ara-license-academy','https://evil.example','https://firebasehosting.googleapis.com/v1beta1/sites/other','https://firebasehosting.googleapis.com/v1beta1/sites/kp4ara-license-academy/versions','https://firebasehosting.googleapis.com/v1beta1/sites/kp4ara-license-academy:populateFiles'])assert(!allowed(url));
});
test('only readonly scopes',()=>assert(SCOPES.every(x=>/readonly|read-only/.test(x))));
test('reject personal/wrong-project credential',()=>{
 assert.throws(()=>credential('{}'));
 assert.throws(()=>credential(JSON.stringify({type:'authorized_user',project_id:'other'})));
});
test('protected manifest fingerprint excludes only Welcome',()=>{
 assert.equal(fingerprint({}, {'/index.html':'x','/new-pr-hams.json':'old'}),fingerprint({}, {'/index.html':'x','/new-pr-hams.json':'new'}));
 assert.notEqual(fingerprint({}, {'/index.html':'x'}),fingerprint({}, {'/index.html':'changed'}));
});
function fakeReader({changed=false,corrupt=false}={}){
 const calls=[],files={'/index.html':'synthetic-hash'},config={rewrites:[{glob:'**',path:'/index.html'}]};
 const version='sites/kp4ara-license-academy/versions/synthetic';
 const reader=new Reader('SYNTHETIC',async(url,options)=>{
  calls.push({url,method:options.method});let data;
  if(url.includes('cloudresourcemanager'))data={projectId:'kp4ara-license-academy',lifecycleState:'ACTIVE'};
  else if(url.includes('firebase.googleapis'))data={projectId:'kp4ara-license-academy'};
  else if(url.includes('/releases'))data={releases:[{version:{name:changed?version+'changed':version}}]};
  else if(url.includes('/files'))data={files:[{path:'/index.html',hash:corrupt?'corrupt':'synthetic-hash'}]};
  else if(url.includes('/versions/'))data={status:'FINALIZED',config};
  else data={name:'sites/kp4ara-license-academy'};
  return {ok:true,json:async()=>data};
 });
 return {reader,calls,anchor:{version:'synthetic',protected_sha256:fingerprint(config,files)}};
}
test('complete inspection uses only GET and aggregates public state',async()=>{
 const f=fakeReader();const result=await inspect(f.reader,f.anchor);
 assert.equal(result.hosting_writes,0);assert(result.protected_manifest_matches);assert.equal(result.manifest_files,1);assert(f.calls.every(x=>x.method==='GET'));
 assert(!JSON.stringify(result).includes('SYNTHETIC'));assert(!('files' in result));
});
test('operational identity cannot call Cloud Billing and requests no billing scope',async()=>{
 assert(!SCOPES.some(x=>x.includes('billing')));assert(!allowed('https://cloudbilling.googleapis.com/v1/projects/kp4ara-license-academy/billingInfo'));
 const f=fakeReader();await inspect(f.reader,f.anchor);assert(!f.calls.some(x=>x.url.includes('cloudbilling')));
});
test('403 aborts immediately and preserves successful read results',async()=>{
 let calls=0;const results={};const reader=new Reader('SYNTHETIC',async()=>{calls++;return calls===1?{ok:true,json:async()=>({projectId:'kp4ara-license-academy',lifecycleState:'ACTIVE'})}:{ok:false,status:403};});
 await assert.rejects(()=>inspect(reader,{version:'synthetic'},results),e=>e.http_status===403&&e.request_path==='firebase.googleapis.com/v1beta1/projects/kp4ara-license-academy');assert.equal(calls,2);assert.equal(results.project_read,'PASS');
});
test('unexpected live version aborts',async()=>{
 const f=fakeReader({changed:true});await assert.rejects(()=>inspect(f.reader,f.anchor));assert(f.calls.every(x=>x.method==='GET'));
});
test('changed protected file rejected',async()=>{
 const f=fakeReader({corrupt:true});await assert.rejects(()=>inspect(f.reader,f.anchor));assert(f.calls.every(x=>x.method==='GET'));
});
