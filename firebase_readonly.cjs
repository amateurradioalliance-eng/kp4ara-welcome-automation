'use strict';
// No Firebase CLI, deployment imports, credential files, artifacts or write adapter.
const crypto=require('node:crypto'),fs=require('node:fs');
const PROJECT='kp4ara-license-academy';
const EMAIL='kp4ara-welcome-publisher@'+PROJECT+'.iam.gserviceaccount.com';
const TOKEN_URL='https://oauth2.googleapis.com/token';
const SCOPES=['https://www.googleapis.com/auth/firebase.readonly','https://www.googleapis.com/auth/cloud-platform.read-only','https://www.googleapis.com/auth/cloud-billing.readonly'];

function credential(raw){
 let key;try{key=JSON.parse(raw);}catch{throw Error('Invalid secret JSON');}
 if(key.type!=='service_account'||key.project_id!==PROJECT||key.client_email!==EMAIL||typeof key.private_key!=='string'||!key.private_key.startsWith('-----BEGIN PRIVATE KEY-----'))throw Error('Unexpected dedicated identity');
 return key;
}
function allowed(url){
 const u=new URL(url);if(u.protocol!=='https:'||u.username||u.password||u.port||u.hash)return false;
 for(const k of u.searchParams.keys())if(!['pageSize','pageToken','status'].includes(k))return false;
 if(u.hostname==='cloudbilling.googleapis.com')return u.pathname==='/v1/projects/'+PROJECT+'/billingInfo';
 if(u.hostname==='cloudresourcemanager.googleapis.com')return u.pathname==='/v1/projects/'+PROJECT;
 if(u.hostname==='firebase.googleapis.com')return u.pathname==='/v1beta1/projects/'+PROJECT;
 if(u.hostname!=='firebasehosting.googleapis.com')return false;
 const root='/v1beta1/sites/'+PROJECT;
 return u.pathname===root||u.pathname===root+'/releases'||new RegExp('^'+root+'/versions/[a-zA-Z0-9_-]+(?:/files)?$').test(u.pathname);
}
class Reader{
 constructor(token,transport=fetch){this.token=token;this.transport=transport;this.calls=0;}
 async request(method,url){
  if(method!=='GET'||!allowed(url))throw Error('Read-only network guard');
  this.calls++;
  const r=await this.transport(url,{method:'GET',headers:{Authorization:'Bearer '+this.token},redirect:'error',signal:AbortSignal.timeout(45000)});
  if(!r.ok){const e=Error('Google read rejected');e.http_status=r.status;e.request_path=new URL(url).hostname+new URL(url).pathname;throw e;}
  return r.json();
 }
 get(url){return this.request('GET',url);}
}
function canonical(value){
 if(Array.isArray(value))return value.map(canonical);
 if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(k=>[k,canonical(value[k])]));
 return value;
}
function fingerprint(config,files){
 const protectedFiles=Object.fromEntries(Object.entries(files).filter(([p])=>p!=='/new-pr-hams.json'));
 return crypto.createHash('sha256').update(JSON.stringify(canonical({config,files:protectedFiles}))).digest('hex');
}
async function exchange(key,transport=fetch){
 const now=Math.floor(Date.now()/1000),base64=x=>Buffer.from(JSON.stringify(x)).toString('base64url');
 const unsigned=base64({alg:'RS256',typ:'JWT'})+'.'+base64({iss:key.client_email,scope:SCOPES.join(' '),aud:TOKEN_URL,iat:now,exp:now+600});
 const jwt=unsigned+'.'+crypto.sign('RSA-SHA256',Buffer.from(unsigned),key.private_key).toString('base64url');
 const r=await transport(TOKEN_URL,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({grant_type:'urn:ietf:params:oauth:grant-type:jwt-bearer',assertion:jwt}),redirect:'error',signal:AbortSignal.timeout(45000)});
 if(!r.ok){const e=Error('OAuth authentication rejected');e.http_status=r.status;throw e;}
 const data=await r.json();if(!data.access_token||data.token_type!=='Bearer')throw Error('Invalid OAuth response');return data.access_token;
}
async function inspect(reader,anchor){
 const billing=await reader.get('https://cloudbilling.googleapis.com/v1/projects/'+PROJECT+'/billingInfo');
 if(billing.billingEnabled||billing.billingAccountName)throw Error('Billing guard failed');
 const project=await reader.get('https://cloudresourcemanager.googleapis.com/v1/projects/'+PROJECT);
 if(project.projectId!==PROJECT||project.lifecycleState!=='ACTIVE')throw Error('Wrong/inactive project');
 const firebase=await reader.get('https://firebase.googleapis.com/v1beta1/projects/'+PROJECT);
 if(firebase.projectId!==PROJECT)throw Error('Wrong Firebase project');
 const host='https://firebasehosting.googleapis.com/v1beta1/sites/'+PROJECT;
 const site=await reader.get(host);
 const live=await reader.get(host+'/releases?pageSize=1');
 const name=live.releases?.[0]?.version?.name;
 if(!name||!name.startsWith('sites/'+PROJECT+'/versions/'))throw Error('Live version unavailable');
 if(name.split('/').pop()!==anchor.version)throw Error('Production version changed; no writes attempted');
 const version=await reader.get('https://firebasehosting.googleapis.com/v1beta1/'+name);
 if(version.status!=='FINALIZED')throw Error('Live version not finalized');
 const files={};let page;
 do{
  const u=new URL('https://firebasehosting.googleapis.com/v1beta1/'+name+'/files');u.searchParams.set('status','ACTIVE');u.searchParams.set('pageSize','1000');if(page)u.searchParams.set('pageToken',page);
  const data=await reader.get(u.href);
  for(const f of data.files||[]){if(!f.path||!f.hash||files[f.path])throw Error('Invalid/duplicate manifest');files[f.path]=f.hash;}
  page=data.nextPageToken;
 }while(page);
 if(!Object.keys(files).length)throw Error('Empty live manifest');
 const config=version.config||{},hash=fingerprint(config,files);
 if(hash!==anchor.protected_sha256)throw Error('Protected live manifest mismatch');
 const after=await reader.get(host+'/releases?pageSize=1');
 if(after.releases?.[0]?.version?.name!==name)throw Error('Live changed during read');
 return {billingEnabled:false,billingAccountLinked:false,project_read:true,firebase_project_read:true,site_read:!!site.name,live_version:name,live_unchanged:true,configuration_read:true,config_sections:Object.keys(config).sort(),manifest_read:true,manifest_files:Object.keys(files).length,protected_manifest_matches:true,protected_sha256:hash,get_requests:reader.calls,hosting_writes:0};
}
async function main(){
 const report={mode:'AUTH_READ_ONLY',result:'FAIL',hosting_writes:0,credential_files_written:0,artifacts:false,persistent_cache:false};let stage='secret_validation';
 try{
  let key=credential(process.env.FIREBASE_HOSTING_SERVICE_ACCOUNT_JSON||'');delete process.env.FIREBASE_HOSTING_SERVICE_ACCOUNT_JSON;
  stage='oauth_authentication';const token=await exchange(key);key=null;report.authentication='PASS';
  stage='firebase_read_only_checks';const anchor=JSON.parse(fs.readFileSync('production-reference.json','utf8'));
  Object.assign(report,await inspect(new Reader(token),anchor),{result:'PASS'});
 }catch(e){report.failure_stage=stage;report.http_status=e.http_status||null;report.failure_request=e.request_path||null;report.reason=e.http_status?'Read/auth denied; role NOT expanded':e.message;process.exitCode=1;}
 const safe=JSON.stringify(report,null,2);console.log(safe);
 if(process.env.GITHUB_STEP_SUMMARY)fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY,'## Firebase authentication — read only\n\n```json\n'+safe+'\n```\n');
}
module.exports={credential,allowed,Reader,canonical,fingerprint,inspect,SCOPES,EMAIL,PROJECT};
if(require.main===module)main();
