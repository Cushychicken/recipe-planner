chrome.action.onClicked.addListener(tab => {
  chrome.tabs.create({windowId: tab.windowId, url: chrome.runtime.getURL('export.html')});
});
