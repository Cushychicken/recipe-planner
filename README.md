# Weekly dinner planner

Generates a Sunday–Saturday dinner plan, printable shopping checklist, PDF, and dated archive from your recipe collection. Runs **Saturday at 11 PM America/New_York**, with daylight saving time handled by GitHub’s timezone-aware schedule. GitHub may start scheduled jobs late; this is a scheduled publication, not a real-time guarantee.

## Current setup

- All **64 recipe sticks** from the supplied photo are in `data/recipes.json`.
- Defaults: **7 dinners, 4 servings**. Change these in `data/settings.json`.
- **Ingredient quantities have not been imported yet.** The initial output is explicitly a draft, without a shopping list. Once at least seven enabled recipes have verified ingredients, new plans select only verified recipes.
- NYT = New York Times Cooking; CI = Cook’s Illustrated *Cook It in Cast Iron*; TN = Milk Street *Tuesday Nights*; MTN = Milk Street *Tuesday Nights Mediterranean*.
- SK, EZW, Slow Cooker and W30 book titles remain unconfirmed. Source/page transcriptions should be checked against the books; the coconut sticky rice page number was unclear in the photo.
- Recipe methods are read in the original books or linked websites. This repository stores ingredient facts and references, not copied instructions.

## Publication

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

Use consistent item names and categories to combine duplicates. Quantities can be integers, decimals or fractions (`"1/2"`). Supported convertible units are `tsp`, `tbsp`, `cup`, `oz`, `lb`, `g`, `kg`, `ml`, and `l`. Other units (`each`, `clove`, `can`) combine only with the exact same unit. Include the package size in the item name, e.g. `white beans (15 oz can)`. Weight, volume and count are kept separate rather than guessed; e.g. a cup of flour is not converted to grams automatically. Quantities are recipe requirements, not rounded supermarket pack sizes.

Set `enabled: false` to remove a dish from the selection pool. Add normalized item names to `pantry` in `data/settings.json` to move them into a separate pantry-check section; they are never silently omitted.

Milk Street recipes: https://www.177milkstreet.com/recipes. The matching Chicken Salmoriglio page currently exposes a truncated ingredient list to unauthenticated visitors. Authenticated access or supplied cookbook pages are needed to complete those records. NYT Cooking and Cook’s Illustrated may likewise require sign-in. **Do not commit passwords, cookies, subscription tokens, or downloaded account pages.** The weekly workflow needs no publisher credentials or AI API key after the ingredients are entered.

## Run locally

Python 3.12+:

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/planner.py
python scripts/planner.py --week 2026-11-08
python scripts/planner.py --require-ready
```

`--week` must be a Sunday. Without it, Saturday targets the following Sunday; Sunday reruns target the current Sunday. `--require-ready` fails instead of emitting a draft.

Selection is deterministic for each week, avoids the previous four weeks when the verified pool is large enough, and relaxes that avoidance when necessary rather than failing. A small verified pool will repeat recipes more often.
