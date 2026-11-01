#!/usr/bin/env node
// Local-only recipe collection UI. Node 18+, Python 3, and normal Git credentials.
import http from 'node:http';
import {randomBytes} from 'node:crypto';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {spawn,spawnSync,execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {dirname,resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {connect,websocketClass} from './export-recipe-tabs.mjs';

const run=promisify(execFile);
const ROOT=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const CDP='http://127.0.0.1:9222';
const paths=['data/recipes.json','data/sources.json','data/imports/latest.json'];

export function parseLinks(text){
  const links=[...new Set(String(text||'').split(/\s+/).filter(Boolean))];
  if(!links.length||links.length>50)throw Error('Paste between 1 and 50 recipe links.');
  return links.map(value=>{
    const url=new URL(value);
    if(url.protocol!=='https:'||url.username||url.password)throw Error('Only HTTPS recipe links without credentials are accepted.');
    url.hash='';
    return url.href;
  });
}

async function browserInfo(){
  const response=await fetch(CDP+'/json/version',{signal:AbortSignal.timeout(2000)});
  if(!response.ok)throw Error('Chrome debugging endpoint is unavailable.');
  return response.json();
}

async function ensureChrome(){
  try{return await browserInfo();}catch{}
  const binary=['google-chrome','google-chrome-stable','chromium','chromium-browser'].find(name=>spawnSync('which',[name],{stdio:'ignore'}).status===0);
  if(!binary)throw Error('Chrome/Chromium was not found. Install it, then rerun this command.');
  const profile=resolve(process.env.HOME,'.cache/recipe-export-chrome');
  spawn(binary,['--remote-debugging-port=9222','--remote-debugging-address=127.0.0.1','--user-data-dir='+profile,'--no-first-run','about:blank'],{detached:true,stdio:'ignore'}).unref();
  for(let attempt=0;attempt<30;attempt++){
    await new Promise(resolve=>setTimeout(resolve,500));
    try{return await browserInfo();}catch{}
  }
  throw Error('Chrome did not start its local debugging port. Close that dedicated Chrome window and rerun.');
}

// Runs only in the user's explicitly opened recipe tabs. Returns recipe facts,
// not page HTML, account information, cookies, or browser storage.
export const CAPTURE=`(() => {
  const found=[];
  function walk(value){
    if(Array.isArray(value)){value.forEach(walk);return;}
    if(!value||typeof value!=='object')return;
    if(value['@type']==='Recipe'||Array.isArray(value['@type'])&&value['@type'].includes('Recipe')){
      const link=document.querySelector('link[rel="canonical"]')?.href;
      found.push({name:value.name,url:value.url||link||location.origin+location.pathname,recipeYield:value.recipeYield,recipeIngredient:value.recipeIngredient});
    }
    Object.values(value).forEach(walk);
  }
  document.querySelectorAll('script[type="application/ld+json"]').forEach(script=>{try{walk(JSON.parse(script.textContent));}catch{}});
  return {title:document.title,ready:document.readyState,recipes:found};
})()`;

async function main(){
  websocketClass();
  const token=randomBytes(24).toString('hex');
  let browser;
  let capture=[];
  let lock=false;
  const hosts=new Set(['cooking.nytimes.com']);
  const recipes=()=>readFile(resolve(ROOT,'data/recipes.json'),'utf8').then(JSON.parse);
  const initial=await recipes();
  initial.forEach(r=>{if(r.url){try{hosts.add(new URL(r.url).hostname);}catch{}}});
  const server=http.createServer(async(request,response)=>{
    const base=`http://127.0.0.1:${server.address().port}`;
    const send=(status,data)=>{response.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});response.end(JSON.stringify(data));};
    try{
      if(request.headers.host!==new URL(base).host){send(403,{error:'Local access only.'});return;}
      const route=new URL(request.url,base).pathname;
      if(request.method==='GET'){
        if(route==='/'){
          const html=(await readFile(resolve(ROOT,'tools/recipe-library.html'),'utf8')).replace('<meta charset="utf-8">',`<meta charset="utf-8"><meta name="request-token" content="${token}">`);
          response.writeHead(200,{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store','Content-Security-Policy':"default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'"});response.end(html);return;
        }
        if(route==='/app.js'){response.writeHead(200,{'Content-Type':'text/javascript'});response.end(await readFile(resolve(ROOT,'tools/recipe-library-app.js')));return;}
        if(route==='/state'){
          const rows=await recipes();send(200,{total:rows.length,ready:rows.filter(r=>r.ingredients_verified).length,missing:rows.filter(r=>r.source==='NYT'&&!r.ingredients_verified).map(({name,url})=>({name,url}))});return;
        }
        if(route==='/download'){
          response.writeHead(200,{'Content-Type':'application/json','Content-Disposition':'attachment; filename="recipe-data.json"','Cache-Control':'no-store'});response.end(JSON.stringify({recipes:capture},null,2));return;
        }
        send(404,{error:'Not found'});return;
      }
      if(request.method!=='POST'||request.headers.origin!==base||request.headers['x-recipe-token']!==token){send(403,{error:'Use the recipe helper page to perform this action.'});return;}
      if(lock){send(409,{error:'Another operation is in progress.'});return;}
      let body='';for await(const chunk of request){body+=chunk;if(body.length>65536)throw Error('Request is too large.');}
      const payload=JSON.parse(body||'{}');
      lock=true;
      try{
        if(route==='/open'){
          const links=parseLinks(payload.links);
          for(const url of links){hosts.add(new URL(url).hostname);await browser.call('Target.createTarget',{url});}
          send(200,{count:links.length});return;
        }
        if(route==='/capture'){
          const targets=await (await fetch(CDP+'/json/list')).json();
          capture=[];const skipped=[];
          for(const target of targets){
            if(target.type!=='page')continue;
            let url;try{url=new URL(target.url);}catch{continue;}
            if(url.protocol!=='https:'||!hosts.has(url.hostname))continue;
            let tab;
            try{
              tab=await connect(target.webSocketDebuggerUrl);
              const result=await tab.call('Runtime.evaluate',{expression:CAPTURE,returnByValue:true});
              const data=result.result?.value;
              if(result.exceptionDetails||!data||data.ready!=='complete')throw Error('Page is not fully loaded. Visit it and try again.');
              if(!data.recipes.length)throw Error('No structured Recipe data found. Open the actual recipe, not a search page.');
              capture.push(...data.recipes);
            }catch(error){skipped.push({title:target.title||url.pathname,reason:error.message});}
            finally{tab?.close();}
          }
          if(!capture.length)throw Error('No recipe data captured. Open recipe links and make sure their ingredients are visible.');
          const directory=resolve(ROOT,'.recipe-imports');await mkdir(directory,{recursive:true});
          const input=resolve(directory,'capture.json');await writeFile(input,JSON.stringify(capture));
          let imported;
          try{imported=await run('python3',[resolve(ROOT,'scripts/import_recipes.py'),input],{cwd:ROOT,maxBuffer:4*1024*1024});}
          catch(error){if(error.stdout){try{imported={stdout:error.stdout};JSON.parse(error.stdout);}catch{throw error;}}else throw error;}
          const report=JSON.parse(imported.stdout);
          const ids=new Set(report.imported.map(item=>item.id));
          const preview=(await recipes()).filter(recipe=>ids.has(recipe.id)).map(({id,source_ingredients})=>({id,source_ingredients}));
          send(200,{report,skipped,preview});return;
        }
        if(route==='/publish'){
          const branch=(await run('git',['branch','--show-current'],{cwd:ROOT})).stdout.trim();
          if(branch!=='main')throw Error('Publication requires the main branch. Switch this checkout to main, then retry.');
          await run('git',['add','--',...paths],{cwd:ROOT});
          let changes=false;try{await run('git',['diff','--cached','--quiet','--',...paths],{cwd:ROOT});}catch(error){if(error.code===1)changes=true;else throw error;}
          if(changes)await run('git',['commit','--only','-m','Import recipe ingredients','--',...paths],{cwd:ROOT});
          // The scheduled workflow also commits generated plans. Rebase this
          // catalog-only commit over those routine updates before pushing.
          try{await run('git',['pull','--rebase','origin','main'],{cwd:ROOT,env:{...process.env,GIT_TERMINAL_PROMPT:'0'},timeout:60000});}
          catch(error){
            try{await run('git',['rev-parse','--verify','REBASE_HEAD'],{cwd:ROOT});await run('git',['rebase','--abort'],{cwd:ROOT});}catch{}
            throw error;
          }
          await run('git',['push','origin','main'],{cwd:ROOT,env:{...process.env,GIT_TERMINAL_PROMPT:'0'},timeout:60000});
          send(200,{message:'Published to GitHub. The planner rebuild is running. Your new recipes will appear on the site when it finishes.'});return;
        }
        send(404,{error:'Not found'});
      }finally{lock=false;}
    }catch(error){send(400,{error:error.message+(error.stderr?'\n'+String(error.stderr).slice(0,1500):'')});}
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const url=`http://127.0.0.1:${server.address().port}/`;
  try{
    const info=await ensureChrome();browser=await connect(info.webSocketDebuggerUrl);
    await browser.call('Target.createTarget',{url});
    console.log(`\nRecipe helper: ${url}\nUse the page that opened in Chrome. Press Ctrl+C here when finished.\n`);
  }catch(error){server.close();throw error;}
  process.on('SIGINT',()=>{browser?.close();server.close();process.exit(0);});
}

if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href){main().catch(error=>{console.error(error.message);process.exitCode=1;});}
