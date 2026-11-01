const {test}=require('node:test');
const assert=require('node:assert/strict');
const {isRecipeUrl,exportWindow}=require('../tools/recipe-tab-exporter/export.js');
const {crc32,makeZip}=require('../tools/recipe-tab-exporter/zip.js');

test('only individual HTTPS NYT Cooking recipes are eligible',()=>{
  assert.equal(isRecipeUrl('https://cooking.nytimes.com/recipes/123-test?tracking=1'),true);
  for(const url of ['https://cooking.nytimes.com/search?q=test','https://example.com/recipes/123-test','http://cooking.nytimes.com/recipes/123-test','javascript:alert(1)']) assert.equal(isRecipeUrl(url),false);
});
test('exports unique completed tabs, reports failures, and never wakes discarded tabs',async()=>{
  const tabs=[
    {id:1,index:0,url:'https://cooking.nytimes.com/recipes/123-one',status:'complete'},
    {id:2,index:1,url:'https://cooking.nytimes.com/recipes/123-one?tracking=1',status:'complete'},
    {id:3,index:2,url:'https://cooking.nytimes.com/recipes/124-two',status:'complete',discarded:true},
    {id:4,index:3,url:'https://cooking.nytimes.com/recipes/125-three',status:'loading'},
    {id:5,index:4,url:'https://cooking.nytimes.com/recipes/126-four',status:'complete'}
  ];
  const called=[];
  const api={tabs:{query:async q=>{assert.equal(q.windowId,7);return tabs;}},scripting:{executeScript:async({target})=>{
    called.push(target.tabId);
    if(target.tabId===5)throw Error('Tab was closed');
    return [{result:{url:tabs[0].url,title:'Test recipe',html:'<!doctype html><p>Recipe</p>',structuredRecipeBlocks:1}}];
  }}};
  const result=await exportWindow(api,7,()=>{});
  assert.equal(result.files.length,1);
  assert.equal(result.records.length,4);
  assert.equal(result.records.filter(r=>r.status==='error').length,3);
  assert.deepEqual(called,[1,5]);
});
test('ZIP uses standard CRC32 and contains a valid central directory',async()=>{
  assert.equal(crc32(new TextEncoder().encode('123456789')),0xcbf43926);
  const blob=makeZip([{name:'recipes/test.html',content:'<p>Crème brûlée</p>'},{name:'index.json',content:'{}'}]);
  const data=new DataView(await blob.arrayBuffer());
  assert.equal(data.getUint32(0,true),0x04034b50);
  assert.equal(data.getUint32(data.byteLength-22,true),0x06054b50);
  assert.equal(data.getUint16(data.byteLength-12,true),2);
});
