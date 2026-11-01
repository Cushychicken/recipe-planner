'use strict';

function isRecipeUrl(url) {
  try {
    const parsed = new URL(url);
    return parsed.origin === 'https://cooking.nytimes.com' && /^\/recipes\/\d+(?:-|\/|$)/.test(parsed.pathname);
  } catch (_) { return false; }
}

// This function is serialized by Chrome and runs in each tab's isolated world.
// No network calls, cookies, browser storage, or credential APIs are accessed.
function capturePage() {
  const clone = document.documentElement.cloneNode(true);
  // Keep the rendered markup and structured recipe JSON; omit executable scripts
  // and form values so an exported page is safer to inspect or share.
  clone.querySelectorAll('script').forEach(script => {
    if (script.type !== 'application/ld+json') script.remove();
  });
  clone.querySelectorAll('input').forEach(input => input.removeAttribute('value'));
  clone.querySelectorAll('textarea').forEach(input => { input.textContent = ''; });
  clone.querySelectorAll('[nonce]').forEach(node => node.removeAttribute('nonce'));
  clone.querySelectorAll('meta[name]').forEach(meta => {
    if (/csrf|token|authorization|secret/i.test(meta.name)) meta.remove();
  });
  return {
    url: location.origin + location.pathname,
    title: document.title,
    readyState: document.readyState,
    structuredRecipeBlocks: clone.querySelectorAll('script[type="application/ld+json"]').length,
    html: '<!doctype html>\n' + clone.outerHTML,
  };
}

async function exportWindow(api, windowId, report) {
  const tabs = (await api.tabs.query({windowId, url:'https://cooking.nytimes.com/recipes/*'}))
    .filter(tab => isRecipeUrl(tab.url)).sort((a,b) => a.index-b.index);
  const records = [], files = [], seen = new Set();
  for (let i=0; i<tabs.length; i++) {
    const tab = tabs[i];
    const record = {url:new URL(tab.url).origin+new URL(tab.url).pathname};
    if (seen.has(record.url)) continue;
    seen.add(record.url);
    report(`Saving ${i+1} of ${tabs.length}…`);
    try {
      // Discarded/sleeping tabs need a normal user visit; do not wake or reload.
      if (tab.discarded || tab.status !== 'complete') throw Error('Visit this tab and wait for the recipe to finish loading, then export again.');
      const [result] = await api.scripting.executeScript({target:{tabId:tab.id},func:capturePage});
      const page = result?.result;
      if (!page?.html || !isRecipeUrl(page.url)) throw Error('The tab changed or did not return recipe HTML.');
      const slug = new URL(page.url).pathname.split('/').filter(Boolean).pop().replace(/[^a-zA-Z0-9_-]/g,'-').slice(0,160);
      record.filename = `recipes/${slug}.html`;
      record.title = page.title;
      record.status = 'saved';
      record.structuredRecipeBlocks = page.structuredRecipeBlocks;
      files.push({name:record.filename,content:page.html});
    } catch (error) {
      record.status = 'error';
      record.error = error.message;
    }
    records.push(record);
  }
  return {files,records};
}

if (typeof module !== 'undefined' && module.exports) module.exports = {isRecipeUrl,exportWindow};
if (typeof document !== 'undefined') {
  const button = document.getElementById('export');
  const status = document.getElementById('status');
  const results = document.getElementById('results');
  button.addEventListener('click', async () => {
    button.disabled = true;
    results.replaceChildren();
    try {
      const tab = await chrome.tabs.getCurrent();
      const {files,records} = await exportWindow(chrome,tab.windowId,text => { status.textContent=text; });
      if (!records.length) { status.textContent='No NYT recipe tabs found in this window. Search-result tabs are not recipes; open the individual recipes first.'; return; }
      for (const record of records) {
        const li=document.createElement('li');
        li.textContent=record.status==='saved' ? `Saved: ${record.title}` : `Skipped: ${record.url} — ${record.error}`;
        results.append(li);
      }
      if (!files.length) { status.textContent='No pages were saved. Review the messages below.'; return; }
      const count=files.length;
      files.push({name:'index.json',content:JSON.stringify({exported_at:new Date().toISOString(),capture:'Rendered DOM; executable scripts and form values removed.',recipes:records},null,2)});
      files.push({name:'README.txt',content:'Recipe HTML export\n\nContains the rendered HTML already loaded in your open recipe tabs, with executable scripts and form values removed. Structured recipe JSON is retained. Assets such as photos and stylesheets are not downloaded. The index lists original URLs and any failed tabs. A saved page can still be incomplete if the ingredients were not visible in the original tab.\n'});
      const blob = RecipeZip.makeZip(files);
      const url = URL.createObjectURL(blob);
      try {
        await chrome.downloads.download({url,filename:`recipe-pages-${new Date().toISOString().replace(/[:.]/g,'-')}.zip`,saveAs:true});
        status.textContent=`Exported ${count} recipe page${count===1?'':'s'}. Save the ZIP in the download dialog.`;
      } finally { setTimeout(() => URL.revokeObjectURL(url),60000); }
    } catch(error) { status.textContent=`Export failed: ${error.message}`; }
    finally { button.disabled=false; }
  });
}
