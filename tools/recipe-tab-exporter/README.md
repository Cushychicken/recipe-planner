# Recipe Tab Exporter

Save the already-loaded HTML from every NYT Cooking recipe tab in one Chrome or Chromium window into a single ZIP.

## Install once

1. Extract the supplied ZIP into a folder.
2. Open `chrome://extensions`.
3. Enable **Developer mode**.
4. Click **Load unpacked** and select the extracted `recipe-tab-exporter` folder containing `manifest.json`.

## Export

1. In one browser window, open the individual recipe pages while signed into your own NYT account. Search-result pages are skipped.
2. Visit each recipe tab and make sure its ingredients are visible and loading is finished.
3. Click the extension’s icon from that window. An export tab opens in the same window.
4. Click **Save recipe tabs** and save the ZIP. Keep the export tab open until the download begins.

The archive contains one `.html` file per unique recipe plus `index.json` with the original URLs and any errors. Discarded, unfinished, or closed tabs are reported rather than silently omitted. After visiting skipped tabs, export again.

This saves **rendered page HTML**, not the original HTTP response byte for byte. It removes executable scripts, form values, nonces, and token meta tags, retaining structured recipe JSON and the rest of the loaded markup. It does not download photos or other assets. It does not access cookies, saved passwords or account storage, and does not upload anything. It cannot make missing/paywalled ingredients appear: they must already be visible in the tabs you opened.

Permissions are limited to scripting on `cooking.nytimes.com` and downloading the local archive. No remote-debugging port, external package, account credential, or server is needed. Disable/remove the extension after exporting if you no longer need it.
