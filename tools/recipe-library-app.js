'use strict';
const status=document.getElementById('status');
const results=document.getElementById('results');
const token=document.querySelector('meta[name="request-token"]').content;
async function request(path,body){
  const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Recipe-Token':token},body:JSON.stringify(body||{})});
  const data=await response.json();
  if(!response.ok)throw Error(data.error||'Request failed');
  return data;
}
async function refresh(){
  const state=await (await fetch('state')).json();
  document.getElementById('stats').textContent=`${state.ready} recipes with ingredients · ${state.total} recipes in your catalog`;
  return state;
}
function busy(value){document.querySelectorAll('button').forEach(button=>{button.disabled=value;});}
function addResult(text){const item=document.createElement('li');item.textContent=text;results.append(item);}
document.getElementById('open').onclick=async()=>{
  busy(true);
  try{const data=await request('open',{links:document.getElementById('links').value});status.textContent=`Opened ${data.count} tabs. Visit the recipes, sign in if needed, then return here and click Capture and import recipes.`;}
  catch(error){status.textContent=error.message;}
  finally{busy(false);}
};
document.getElementById('missing').onclick=async()=>{
  busy(true);
  try{
    const state=await refresh();
    const links=state.missing.map(r=>r.url||'https://cooking.nytimes.com/search?q='+encodeURIComponent(r.name));
    document.getElementById('links').value=links.join('\n');
    if(!links.length){status.textContent='All NYT entries have ingredients. Paste new recipe links above to expand the catalog.';return;}
    await request('open',{links:links.join('\n')});
    status.textContent=`Opened ${links.length} missing-recipe tabs. Choose the matching recipes from any search results, then return here to import.`;
  }catch(error){status.textContent=error.message;}
  finally{busy(false);}
};
document.getElementById('capture').onclick=async()=>{
  busy(true);results.replaceChildren();status.textContent='Reading recipe facts from your open tabs…';
  try{
    const data=await request('capture');
    for(const item of data.report.imported){
      addResult(`${item.added?'Added':'Updated'}: ${item.name} · ${item.ingredient_count} ingredients · original yield: ${item.source_yield}`);
      for(const note of item.notes)addResult(note);
      const preview=data.preview.find(recipe=>recipe.id===item.id);
      if(preview){
        const detail=document.createElement('details');
        const summary=document.createElement('summary');summary.textContent='Review original ingredient list';detail.append(summary);
        const list=document.createElement('ul');
        for(const line of preview.source_ingredients){const entry=document.createElement('li');entry.textContent=line;list.append(entry);}
        detail.append(list);results.lastElementChild.append(detail);
      }
    }
    for(const item of data.report.errors)addResult(`Needs review: ${item.name} — ${item.error}`);
    for(const item of data.skipped)addResult(`Skipped: ${item.title} — ${item.reason}`);
    status.textContent=`Imported ${data.report.imported.length} recipes. Review the list, then publish when ready.`;
    document.getElementById('download').hidden=false;
    await refresh();
  }catch(error){status.textContent=error.message;}
  finally{busy(false);}
};
document.getElementById('publish').onclick=async()=>{
  busy(true);status.textContent='Committing and pushing the recipe catalog…';
  try{const data=await request('publish');status.textContent=data.message;}
  catch(error){status.textContent=error.message;}
  finally{busy(false);}
};
refresh().catch(error=>{status.textContent=error.message;});
