# Weekly dinner planner

Generates a Sunday–Saturday dinner plan, printable shopping checklist, PDF, and dated archive from your recipe collection. Runs **Saturday at 11 PM America/New_York**, with daylight saving time handled by GitHub’s timezone-aware schedule. GitHub may start scheduled jobs late; this is a scheduled publication, not a real-time guarantee.

## Current setup

- All **64 recipe sticks** from the supplied photo are in `data/recipes.json`.
- Defaults: **6 recipes plus Friday leftovers/takeout, 4 servings**. Change these in `data/settings.json`.
- **Two ingredient lists are verified:** Chorizo Rice (The Wholesome Dish, 4 servings) and Chicken Tortilla Soup (The Pioneer Woman, 8 servings). Remaining recipes still need ingredient data. Verified dinners show their own shopping list even when other days remain drafts. Once at least six enabled recipes have verified ingredients, new weekly plans select only verified recipes.
- NYT = New York Times Cooking; CI = Cook’s Illustrated *Cook It in Cast Iron*; TN = Milk Street *Tuesday Nights*; MTN = Milk Street *Tuesday Nights Mediterranean*.
- SK, EZW, Slow Cooker and W30 book titles remain unconfirmed. Source/page transcriptions should be checked against the books; the coconut sticky rice page number was unclear in the photo.
- Recipe methods are read in the original books or linked websites. This repository stores ingredient facts and references, not copied instructions.

## Publication

### Household print template

The primary weekly PDF now follows your supplied `templates/weekly-plan.docx`:
one landscape page, Sunday–Saturday dinner columns with book/page references,
blank lunch options and lunch ingredients areas, and ingredients directly beneath
the corresponding dinner. Each shopping column belongs to the weekday above it.

Each week also produces an editable `.docx` and a separate `-shopping.pdf`
checklist. The primary PDF is exported directly from the filled Word template.
Empty trailing paragraphs are removed, and export must contain exactly one page.
If a very long ingredient list cannot fit even after reducing checklist type,
generation fails rather than dropping ingredients or publishing a second page.
Lunches remain blank because no lunch recipes have been supplied.

**Friday defaults to Leftovers / takeout** in the web page and printed sheet, with no grocery items. Change `leftovers_days` in `data/settings.json` to adjust the default. You can still select a random Friday recipe in the browser.

Each day has **Random recipe** and **Leftovers / takeout** buttons. Random avoids
the current recipe and, when possible, dishes elsewhere in the week. Leftovers
replaces the dinner and clears that day’s groceries; pressing it again restores
the previous recipe. **Reset week** restores the published choices.

Edits are saved per week in this browser, not back to GitHub or across devices.
**Print one-page plan** prints the current on-screen choices. The original Word
and PDF downloads are hidden while the plan is customized so they cannot be
mistaken for updated downloads. The original combined checklist remains an
additional download for the unmodified published plan.

Local PDF export additionally requires LibreOffice (`libreoffice-writer`). The
workflow installs its own renderer. Changes to `templates/` trigger regeneration.

The `Weekly dinner plan` action tests, generates, commits the dated plan and printable files, uploads a downloadable artifact, and deploys `docs/` to GitHub Pages.

Expected site: https://cushychicken.github.io/recipe-planner/

If deployment reports that Pages is not enabled, open [Settings → Pages](https://github.com/Cushychicken/recipe-planner/settings/pages) and choose **GitHub Actions** as the build source. Then rerun the failed workflow. Print sheets remain downloadable from the successful build job even if Pages setup is pending.

The action also runs when recipe data or planner code changes, and can be run manually from [Actions](https://github.com/Cushychicken/recipe-planner/actions/workflows/weekly-plan.yml). An existing ready week keeps its dinner choices on reruns. Each weekly JSON records the shopping quantities for that week. Archive pages and PDFs remain available.

## Add ingredient data once

For each recipe in `data/recipes.json`, fill in the real yield (`servings`), original URL, and complete ingredients; then set `ingredients_verified` to `true`. This flag means the entire ingredient list has been checked against the original recipe, including oils, seasonings, garnishes and any sides you intend to serve. Do not mark a partial or paywalled preview as verified.

Example ingredient record:

```json
{
  "item": "olive oil",
  "quantity": "2",
  "unit": "tbsp",
  "category": "Oils and spices"
}
```

Use consistent item names and categories to combine duplicates. Quantities can be integers, decimals or fractions (`"1/2"`). Use `null` with unit `as needed` or `to taste` for unspecified garnish amounts; no quantities are invented. Set an ingredient’s `shopping` to `false` for non-purchased inputs such as tap water while retaining it in the recipe record. Supported convertible units are `tsp`, `tbsp`, `cup`, `oz`, `lb`, `g`, `kg`, `ml`, and `l`. Other units (`each`, `clove`, `can`) combine only with the exact same unit. Include the package size in the item name, e.g. `white beans (15 oz can)`. Weight, volume and count are kept separate rather than guessed; e.g. a cup of flour is not converted to grams automatically. Quantities are recipe requirements, not rounded supermarket pack sizes.

Set `enabled: false` to remove a dish from the selection pool. Add normalized item names to `pantry` in `data/settings.json` to move them into a separate pantry-check section; they are never silently omitted.

Milk Street recipes: https://www.177milkstreet.com/recipes. The matching Chicken Salmoriglio page currently exposes a truncated ingredient list to unauthenticated visitors. Authenticated access or supplied cookbook pages are needed to complete those records. NYT Cooking and Cook’s Illustrated may likewise require sign-in. **Do not commit passwords, cookies, subscription tokens, or downloaded account pages.** The weekly workflow needs no publisher credentials or AI API key after the ingredients are entered.

## Run locally

Python 3.12+:

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
node --test tests/test_client.cjs
python scripts/planner.py
python scripts/planner.py --week 2026-11-08
python scripts/planner.py --require-ready
```

`--week` must be a Sunday. Without it, Saturday targets the following Sunday; Sunday reruns target the current Sunday. `--require-ready` fails instead of emitting a draft.

Selection is deterministic for each week, avoids the previous four weeks when the verified pool is large enough, and relaxes that avoidance when necessary rather than failing. A small verified pool will repeat recipes more often.

## Save open recipe tabs

Download `tools/recipe-tab-exporter.zip`, extract it, and follow the included README. The small Chrome/Chromium extension exports already-loaded NYT recipe HTML from the current browser window into one local ZIP. Source is in `tools/recipe-tab-exporter/`.
