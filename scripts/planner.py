"""Offline weekly dinner planner. Ingredient data must be verified before use."""
import argparse
from collections import defaultdict
from datetime import date, datetime, timedelta
from fractions import Fraction
from html import escape
import json
from pathlib import Path
import random
import re
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(path.read_text())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def week_start(now):
    """Sunday at 23:00 Saturday targets tomorrow; Sunday reruns target today."""
    return now.date() + timedelta(days=(6 - now.weekday()) % 7)


def validate(recipes, settings):
    ids = set()
    if not 1 <= settings['dinners'] <= 7 or settings['servings'] <= 0:
        raise ValueError('Use 1–7 dinners and a positive serving count')
    for recipe in recipes:
        if not re.fullmatch(r'[a-z0-9-]+', recipe['id']) or recipe['id'] in ids:
            raise ValueError(f"Invalid or duplicate recipe ID: {recipe['id']}")
        ids.add(recipe['id'])
        if recipe['servings'] <= 0:
            raise ValueError(f"Invalid servings: {recipe['id']}")
        if recipe['ingredients_verified'] and not recipe['ingredients']:
            raise ValueError(f"Verified recipe has no ingredients: {recipe['id']}")
        for ingredient in recipe['ingredients']:
            if not all(ingredient.get(k) for k in ('item', 'unit', 'category')):
                raise ValueError(f"Incomplete ingredient: {recipe['id']}")
            if Fraction(str(ingredient['quantity'])) <= 0:
                raise ValueError(f"Invalid ingredient quantity: {recipe['id']}")


def select(recipes, start, settings, history):
    count = settings['dinners']
    ready = [r for r in recipes if r.get('enabled', True) and r['ingredients_verified']]
    # An entirely unverified catalog can still show the layout, never a shopping list.
    draft = len(ready) < count
    pool = [r for r in recipes if r.get('enabled', True)] if draft else ready
    if len(pool) < count:
        raise ValueError(f'Need at least {count} enabled recipes')
    recent = set()
    for plan in history:
        age = (start - date.fromisoformat(plan['week_start'])).days
        if 0 < age <= 7 * settings['avoid_repeat_weeks']:
            recent.update(m['recipe_id'] for m in plan['meals'])
    rng = random.Random(start.isoformat())
    fresh = sorted([r for r in pool if r['id'] not in recent], key=lambda r: r['id'])
    repeats = sorted([r for r in pool if r['id'] in recent], key=lambda r: r['id'])
    rng.shuffle(fresh)
    rng.shuffle(repeats)
    return (fresh + repeats)[:count], draft


# Compatible units normalize before aggregation; incompatible units remain separate.
UNITS = {
    'tsp': ('tsp', 1), 'tbsp': ('tsp', 3), 'cup': ('tsp', 48),
    'oz': ('oz', 1), 'lb': ('oz', 16), 'g': ('g', 1), 'kg': ('g', 1000),
    'ml': ('ml', 1), 'l': ('ml', 1000),
}


def shopping_list(recipes, servings, pantry):
    totals = defaultdict(Fraction)
    uses = defaultdict(set)
    pantry = {p.casefold().strip() for p in pantry}
    for recipe in recipes:
        for ing in recipe['ingredients']:
            item = ing['item'].casefold().strip()
            unit, factor = UNITS.get(ing['unit'], (ing['unit'], 1))
            key = (ing['category'], item, unit, item in pantry)
            totals[key] += Fraction(str(ing['quantity'])) * factor * Fraction(str(servings)) / Fraction(str(recipe['servings']))
            uses[key].add(recipe['name'])
    return [dict(category=k[0], item=k[1], unit=k[2], pantry=k[3],
                 quantity=str(v), recipes=sorted(uses[k])) for k, v in sorted(totals.items())]


def quantity(row):
    q, unit = Fraction(row['quantity']), row['unit']
    if unit == 'tsp':
        for candidate, factor in [('cup', 48), ('tbsp', 3)]:
            if q >= factor:
                q, unit = q / factor, candidate
                break
    elif unit == 'oz' and q >= 16:
        q, unit = q / 16, 'lb'
    n, remainder = divmod(q.numerator, q.denominator)
    display = str(n) if not remainder else (f'{n} ' if n else '') + str(Fraction(remainder, q.denominator))
    return f'{display} {unit}'


def reference(recipe, sources):
    source = sources.get(recipe['source'], {'name': recipe['source']})['name']
    return source + (f", p. {recipe['page']}" if recipe.get('page') else '')


def build_plan(recipes, start, settings, history, existing=None):
    by_id = {r['id']: r for r in recipes}
    if existing and not existing['draft']:
        chosen = [by_id[m['recipe_id']] for m in existing['meals']]
        draft = any(not r['ingredients_verified'] for r in chosen)
    else:
        chosen, draft = select(recipes, start, settings, history)
    return dict(week_start=start.isoformat(), servings=settings['servings'], draft=draft,
                meals=[dict(day=(start + timedelta(days=i)).isoformat(), recipe_id=r['id']) for i, r in enumerate(chosen)],
                shopping=[] if draft else shopping_list(chosen, settings['servings'], settings['pantry']))


def render_html(plan, recipes, sources, archive):
    by_id = {r['id']: r for r in recipes}
    start = date.fromisoformat(plan['week_start'])
    meals = ''
    for meal in plan['meals']:
        recipe = by_id[meal['recipe_id']]
        day = date.fromisoformat(meal['day']).strftime('%a %m/%d')
        title = escape(recipe['name'])
        if recipe.get('url'):
            title = f'<a href="{escape(recipe["url"], quote=True)}">{title}</a>'
        meals += f'<tr><th>{day}</th><td><strong>{title}</strong><small>{escape(reference(recipe, sources))}</small></td></tr>'
    warning = '<aside><b>DRAFT — ingredients not verified.</b> This is a layout preview. No shopping list is available until all selected recipes have verified ingredient quantities.</aside>' if plan['draft'] else ''
    groups = defaultdict(list)
    for row in plan['shopping']:
        groups['Pantry — check before buying' if row['pantry'] else row['category']].append(row)
    shopping = ''
    for category, rows in groups.items():
        shopping += f'<section class="category"><h3>{escape(category)}</h3>'
        for row in rows:
            shopping += f'<label><input type="checkbox"> {escape(row["item"])} <span>{escape(quantity(row))}</span></label>'
        shopping += '</section>'
    if not shopping:
        shopping = '<p class="muted">Ingredient quantities still need to be entered and checked against the original recipes.</p>'
    links = ' · '.join(f'<a href="{escape(p)}.html">{escape(p)}</a>' for p in archive)
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dinner plan · {start.isoformat()}</title><style>
*{{box-sizing:border-box}}body{{font:15px/1.45 system-ui,sans-serif;color:#202a25;background:#eeeae1;margin:0}}main{{max-width:1060px;margin:35px auto;background:#fffdf8;padding:40px;border-top:7px solid #365e47}}header{{display:flex;justify-content:space-between;align-items:center;gap:20px}}h1{{font:36px Georgia,serif;margin:0}}h2{{font:25px Georgia,serif;border-bottom:1px solid #c9ccbf;padding-bottom:8px}}h3{{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:#365e47;margin:12px 0 5px}}p{{margin:8px 0 20px}}.eyebrow{{text-transform:uppercase;letter-spacing:.15em;font-size:12px;color:#365e47}}.layout{{display:grid;grid-template-columns:1fr 1fr;gap:36px}}table{{border-collapse:collapse;width:100%}}th,td{{text-align:left;vertical-align:top;border-bottom:1px solid #e1e1d8;padding:12px 0}}th{{width:85px;font-size:13px}}small{{display:block;color:#687168;font-size:12px;margin-top:4px}}label{{display:flex;align-items:baseline;gap:7px;padding:4px 0;border-bottom:1px dotted #ddd}}label span{{margin-left:auto;white-space:nowrap;font-size:13px}}input{{accent-color:#365e47}}a{{color:inherit}}button,.button{{font:inherit;border:1px solid #365e47;background:white;padding:9px 12px;border-radius:4px;cursor:pointer;text-decoration:none;display:inline-block}}aside{{background:#fff1cd;padding:15px;border:1px solid #e3bd67;margin:20px 0}}.muted,footer{{color:#687168}}footer{{border-top:1px solid #ddd;margin-top:25px;padding-top:12px;font-size:12px}}.category{{break-inside:avoid}}nav{{display:flex;gap:8px;flex-wrap:wrap}}@media(max-width:700px){{main{{margin:0;padding:22px}}.layout{{grid-template-columns:1fr}}header{{display:block}}nav{{margin:15px 0}}}}@page{{size:letter;margin:.4in}}@media print{{body,main{{background:white}}main{{margin:0;padding:0;max-width:none;border:0}}nav,.archive{{display:none}}h1{{font-size:25px}}body{{font-size:11px}}h2{{font-size:19px}}.layout{{grid-template-columns:1fr 1fr;gap:24px}}th,td{{padding:9px 0}}small{{font-size:9px}}h3{{font-size:10px}}label span{{font-size:10px}}footer{{font-size:9px}}a{{text-decoration:none}}}}
</style><main><header><div><div class="eyebrow">The weekly dinner plan</div><h1>{start.strftime('%B %d')} – {(start+timedelta(days=6)).strftime('%B %d, %Y')}</h1></div><nav><button onclick="window.print()">Print sheet</button><a class="button" href="{start.isoformat()}.pdf">Download PDF</a><a class="button" href="catalog.html">Recipes</a></nav></header><p>{plan['servings']} servings per dinner · Sunday–Saturday</p>{warning}<div class="layout"><section><h2>On the menu</h2><table>{meals}</table></section><section><h2>Shopping list</h2>{shopping}</section></div><footer>Quantities are scaled to {plan['servings']} servings. Pantry items remain listed for checking. Recipes and methods are in the referenced books or linked originals.<div class="archive">Past plans: {links or 'First week'}</div></footer></main></html>'''


def render_pdf(path, plan, recipes, sources):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    styles = getSampleStyleSheet()
    font_dir = Path('/usr/share/fonts/truetype/dejavu')
    if (font_dir/'DejaVuSans.ttf').exists():
        pdfmetrics.registerFont(TTFont('Planner', str(font_dir/'DejaVuSans.ttf')))
        pdfmetrics.registerFont(TTFont('Planner-Bold', str(font_dir/'DejaVuSans-Bold.ttf')))
        pdfmetrics.registerFontFamily('Planner', normal='Planner', bold='Planner-Bold', italic='Planner', boldItalic='Planner-Bold')
        for style in styles.byName.values():
            if hasattr(style, 'fontName'):
                style.fontName = 'Planner-Bold' if 'Bold' in style.fontName else 'Planner'
    by_id = {r['id']: r for r in recipes}
    story = [Paragraph('Weekly dinner plan', styles['Title']),
             Paragraph(f"Week of {plan['week_start']} · {plan['servings']} servings", styles['Normal']), Spacer(1, 12)]
    if plan['draft']:
        story += [Paragraph('DRAFT — ingredient quantities are unverified. Shopping list unavailable.', styles['Heading3'])]
    rows = []
    for meal in plan['meals']:
        recipe = by_id[meal['recipe_id']]
        rows.append([date.fromisoformat(meal['day']).strftime('%a %m/%d'),
                     Paragraph(f"<b>{escape(recipe['name'])}</b><br/>{escape(reference(recipe,sources))}", styles['Normal'])])
    table = Table(rows, colWidths=[65, 475], hAlign='LEFT')
    table.setStyle(TableStyle([('FONTNAME',(0,0),(-1,-1),styles['Normal'].fontName),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),8),('LINEBELOW',(0,0),(-1,-1),.3,colors.lightgrey)]))
    story += [table, Spacer(1,12), Paragraph('Shopping list',styles['Heading2'])]
    previous = None
    for row in plan['shopping']:
        category = 'Pantry — check before buying' if row['pantry'] else row['category']
        if category != previous:
            story.append(Paragraph(escape(category), styles['Heading3']))
            previous = category
        story.append(Paragraph(f"[  ] {escape(row['item'])} — {escape(quantity(row))}", styles['Normal']))
    if plan['draft']:
        story.append(Paragraph('Check ingredient lists against the original recipes before enabling weekly shopping lists.', styles['Normal']))
    SimpleDocTemplate(str(path), pagesize=(8.5*inch,11*inch),rightMargin=36,leftMargin=36,topMargin=32,bottomMargin=32).build(story)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--week', type=date.fromisoformat, help='Sunday YYYY-MM-DD')
    parser.add_argument('--require-ready', action='store_true')
    args = parser.parse_args()
    settings = load(ROOT/'data/settings.json')
    recipes = load(ROOT/'data/recipes.json')
    sources = load(ROOT/'data/sources.json')
    validate(recipes, settings)
    start = args.week or week_start(datetime.now(ZoneInfo(settings['timezone'])))
    if start.weekday() != 6:
        parser.error('--week must be a Sunday')
    history = [load(p) for p in sorted((ROOT/'plans').glob('*.json'))]
    existing = next((p for p in history if p['week_start']==start.isoformat()),None)
    plan = build_plan(recipes,start,settings,history,existing)
    if plan['draft'] and args.require_ready:
        raise SystemExit('Ingredient setup incomplete: need verified quantities for every selected dinner.')
    save(ROOT/'plans'/f'{start}.json',plan)
    docs = ROOT/'docs'
    docs.mkdir(exist_ok=True)
    archive = sorted((p.stem for p in (ROOT/'plans').glob('*.json')),reverse=True)
    # Regenerate archived output from its persisted plan, preserving historic quantities.
    for p in sorted((ROOT/'plans').glob('*.json')):
        old = load(p)
        page = docs/f'{p.stem}.html'
        page.write_text(render_html(old,recipes,sources,archive))
        render_pdf(docs/f'{p.stem}.pdf',old,recipes,sources)
    catalog = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Recipe catalog</title><style>body{font:16px/1.5 system-ui;max-width:900px;margin:30px auto;padding:20px}li{margin-bottom:15px}small{display:block;color:#555}</style><a href="index.html">← Weekly plan</a><h1>Recipe catalog</h1><p>Only recipes with verified ingredient quantities are eligible for a ready-to-shop plan. Unconfirmed book abbreviations are preserved.</p><ol>'
    for r in recipes:
        title = escape(r['name'])
        if r.get('url'):
            title = f'<a href="{escape(r["url"], quote=True)}">{title}</a>'
        catalog += f'<li>{title}<small>{escape(reference(r,sources))} · {"Verified" if r["ingredients_verified"] else "Ingredients pending"}</small></li>'
    (docs/'catalog.html').write_text(catalog+'</ol></html>')
    latest = max(archive)
    (docs/'index.html').write_text((docs/f'{latest}.html').read_text())
    (docs/'.nojekyll').touch()
    print(f"{'DRAFT' if plan['draft'] else 'READY'}: {start}; {len(plan['meals'])} dinners; {len(plan['shopping'])} shopping items")


if __name__ == '__main__':
    main()
