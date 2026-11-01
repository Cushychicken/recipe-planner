#!/usr/bin/env node
// Node 22+. Built-in APIs only. Run in your own terminal, against your own Chrome.
import {mkdir, writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

export function isRecipe(url) {
  try {
    const u = new URL(url);
    return u.origin === 'https://cooking.nytimes.com' && /^\/recipes\/\d+(?:-|\/|$)/.test(u.pathname);
  } catch { return false; }
}

export async function connect(address, Socket = globalThis.WebSocket) {
  const url = new URL(address);
  if (url.protocol !== 'ws:' || !['127.0.0.1','localhost','[::1]'].includes(url.hostname)) {
    throw Error('Only a local Chrome debugging connection is accepted.');
  }
  const socket = new Socket(address), pending = new Map();
  let sequence = 0;
  const fail = () => {
    for (const {reject,timer} of pending.values()) { clearTimeout(timer); reject(Error('Chrome connection closed.')); }
    pending.clear();
  };
  socket.addEventListener('message', event => {
    let message;
    try { message = JSON.parse(event.data); } catch { return; }
    const request = pending.get(message.id);
    if (!request) return;
    clearTimeout(request.timer);
    pending.delete(message.id);
    if (message.error) request.reject(Error(message.error.message));
    else request.resolve(message.result);
  });
  socket.addEventListener('close', fail);
  socket.addEventListener('error', fail);
  await new Promise((resolveOpen,rejectOpen) => {
    const timer = setTimeout(() => { socket.close(); rejectOpen(Error('Chrome connection timed out.')); },5000);
    socket.addEventListener('open', () => { clearTimeout(timer); resolveOpen(); }, {once:true});
    socket.addEventListener('error', () => { clearTimeout(timer); rejectOpen(Error('Cannot connect to Chrome.')); }, {once:true});
  });
  return {
    call(method,params = {}) {
      return new Promise((resolveCall,rejectCall) => {
        const id = ++sequence;
        const timer = setTimeout(() => { pending.delete(id); rejectCall(Error('Page capture timed out.')); },30000);
        pending.set(id,{resolve:resolveCall,reject:rejectCall,timer});
        try { socket.send(JSON.stringify({id,method,params})); }
        catch(error) { clearTimeout(timer); pending.delete(id); rejectCall(error); }
      });
    },
    close() { socket.close(); fail(); }
  };
}

export async function main(args = process.argv.slice(2)) {
  if (!globalThis.WebSocket) throw Error('Node.js 22 or newer is required. No npm packages are needed.');
  const directory = resolve(args[0] || 'recipe-html');
  const port = Number(args[1] || 9222);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw Error('Invalid debugging port.');
  let targets;
  try {
    const response = await fetch(`http://127.0.0.1:${port}/json/list`, {signal:AbortSignal.timeout(5000)});
    if (!response.ok) throw Error('Chrome did not return its tabs.');
    targets = await response.json();
  } catch {
    throw Error(`Cannot reach Chrome on local port ${port}. Start Chrome with --remote-debugging-port=${port} and a separate --user-data-dir first.`);
  }
  const tabs = targets.filter(tab => tab.type === 'page' && isRecipe(tab.url));
  if (!tabs.length) throw Error('No NYT recipe tabs found. Open the individual recipes in the debugging-enabled Chrome window first.');
  await mkdir(directory,{recursive:true});
  const index = [], seen = new Set();
  for (const tab of tabs) {
    const canonical = new URL(tab.url).origin + new URL(tab.url).pathname;
    if (seen.has(canonical)) continue;
    seen.add(canonical);
    const record = {url:canonical};
    let client;
    try {
      client = await connect(tab.webSocketDebuggerUrl);
      const capture = await client.call('Runtime.evaluate',{
        expression: `(() => ({url:location.origin+location.pathname,title:document.title,ready:document.readyState,html:'<!doctype html>\\n'+document.documentElement.outerHTML}))()`,
        returnByValue:true
      });
      if (capture.exceptionDetails) throw Error('Could not read this tab’s document.');
      const page = capture.result?.value;
      if (!page || !isRecipe(page.url) || page.ready !== 'complete') throw Error('Tab changed or is still loading. Visit it, wait for the ingredients, then run again.');
      const filename = new URL(page.url).pathname.split('/').filter(Boolean).pop().replace(/[^a-zA-Z0-9_-]/g,'-').slice(0,180)+'.html';
      await writeFile(resolve(directory,filename),page.html,'utf8');
      Object.assign(record,{title:page.title,file:filename,status:'saved'});
      console.log(`Saved ${filename}`);
    } catch(error) {
      Object.assign(record,{status:'error',error:error.message});
      console.error(`Skipped ${canonical}: ${error.message}`);
    } finally { client?.close(); }
    index.push(record);
  }
  await writeFile(resolve(directory,'index.json'),JSON.stringify(index,null,2)+'\n');
  const saved = index.filter(record => record.status === 'saved').length;
  console.log(`\nSaved ${saved}/${index.length} recipes to ${directory}`);
  console.log(`To package: zip -r recipe-html.zip ${JSON.stringify(directory)}`);
  if (saved !== index.length) process.exitCode = 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
}
