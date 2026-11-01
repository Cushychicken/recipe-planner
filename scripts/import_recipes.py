"""Import recipe facts from user-saved HTML, ZIPs, or structured JSON. Stdlib only."""
import argparse
from datetime import date
from fractions import Fraction
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlparse, urlunparse
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
ALIASES = {
    '1021476': 'sheet-pan-scallion-chicken-w-bok-choy-nyt',
    '1022985': 'rice-noodles-w-egg-drop-gravy-nyt',
    '1020970': 'turmeric-black-pepper-chicken-nyt',
    '1025701': 'crisp-gnocchi-w-feta-spinach-nyt',
    '1021277': 'baked-feta-w-tomato-broccolini-nyt',
    '1019435': 'chapli-burgers-nyt',
    '1022131': 'sheet-pan-bibimbap-nyt',
    '1019857': 'maple-miso-salmon-nyt',
    '1016135': 'rishia-zimmern-s-chicken-w-shallots-nyt',
    '1023017': 'mattar-paneer-nyt',
    '1023019': 'cauliflower-shawarma-nyt',
    '1023301': 'soy-braised-tofu-w-bok-choy-nyt',
    '1022532': 'bean-cheese-burritos-nyt',
    '1023047': 'coconut-sticky-rice-w-chicken-nyt',
    '1018910': 'sheet-pan-chicken-w-chickpeas-cumin-turmeric-nyt',
    '1019681': 'cheesy-white-bean-tomato-bake-nyt',
}
FRACTIONS = {'¼':'1/4','½':'1/2','¾':'3/4','⅓':'1/3','⅔':'2/3','⅛':'1/8','⅜':'3/8','⅝':'5/8','⅞':'7/8'}
NUMBER = r'(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)'
QUANTITY = re.compile(r'^('+NUMBER+r')(?:\s*(?:to|[-–—])\s*('+NUMBER+r'))?\s*(.*)$',re.I)
UNIT_MAP = {
    'tablespoons':'tbsp','tablespoon':'tbsp','tbsp':'tbsp','teaspoons':'tsp','teaspoon':'tsp','tsp':'tsp',
    'pounds':'lb','pound':'lb','lbs':'lb','lb':'lb','ounces':'oz','ounce':'oz','oz':'oz',
    'cups':'cup','cup':'cup','pints':'pint','pint':'pint','quarts':'quart','quart':'quart',
    'grams':'g','gram':'g','g':'g','kilograms':'kg','kilogram':'kg','kg':'kg',
    'milliliters':'ml','milliliter':'ml','ml':'ml','liters':'l','liter':'l',
    'cloves':'clove','clove':'clove','heads':'head','head':'head','bunches':'bunch','bunch':'bunch',
    'cans':'can','can':'can','packages':'package','package':'package','blocks':'block','block':'block',
    'sprigs':'sprig','sprig':'sprig','stalks':'stalk','stalk':'stalk',
}


def normalize(text):
    text = unescape(str(text)).replace('\xa0',' ').replace('⁄','/')
    for glyph, fraction in FRACTIONS.items():
        text = re.sub(r'(\d)'+glyph, r'\1 '+fraction, text)
        text = text.replace(glyph,fraction)
    return re.sub(r'\s+',' ',text).strip()


def canonical_url(url):
    if not str(url).strip():
        raise ValueError('Recipe URL is missing')
    parsed = urlparse(urljoin('https://cooking.nytimes.com/',str(url)))
    if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError('Recipe URL must be an HTTPS URL without credentials')
    return urlunparse((parsed.scheme,parsed.netloc,parsed.path,'','',''))


def number(text):
    return sum((Fraction(part) for part in text.split()),Fraction())


def recipe_nodes(value):
    if isinstance(value,dict):
        kind = value.get('@type',[])
        if kind == 'Recipe' or isinstance(kind,list) and 'Recipe' in kind:
            yield value
        for child in value.values():
            yield from recipe_nodes(child)
    elif isinstance(value,list):
        for child in value:
            yield from recipe_nodes(child)


class RecipeHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_json=False
        self.buffer=''
        self.recipes=[]
        self.canonical=None

    def handle_starttag(self,tag,attributes):
        attrs=dict(attributes)
        if tag=='script' and attrs.get('type','').lower()=='application/ld+json':
            self.in_json=True
            self.buffer=''
        if tag=='link' and 'canonical' in attrs.get('rel','').split():
            self.canonical=attrs.get('href')

    def handle_data(self,text):
        if self.in_json:
            self.buffer+=text

    def handle_endtag(self,tag):
        if tag=='script' and self.in_json:
            try:
                self.recipes.extend(recipe_nodes(json.loads(self.buffer)))
            except json.JSONDecodeError:
                pass
            self.in_json=False


def read_records(path):
    """Read selected files without extracting ZIP paths or retaining account HTML."""
    path=Path(path)
    if path.is_dir():
        values=[]
        for entry in sorted(path.rglob('*.html')):
            values.extend(read_records(entry))
        return values
    if path.suffix.lower()=='.zip':
        records=[]
        with ZipFile(path) as archive:
            for entry in archive.infolist():
                if not entry.filename.lower().endswith(('.html','.htm')):
                    continue
                if entry.file_size>25_000_000:
                    raise ValueError('A saved HTML page exceeds the 25 MB limit')
                records.extend(parse_html(archive.read(entry).decode('utf-8-sig')))
        return records
    if path.suffix.lower()=='.json':
        value=json.loads(path.read_text())
        return value['recipes'] if isinstance(value,dict) and 'recipes' in value else value if isinstance(value,list) else [value]
    return parse_html(path.read_text(encoding='utf-8-sig'))


def parse_html(html):
    parser=RecipeHTML()
    parser.feed(html)
    records=[]
    for recipe in parser.recipes:
        # Only public recipe facts are allowed out of the uploaded HTML.
        records.append(dict(name=recipe.get('name'),url=recipe.get('url') or parser.canonical,
                            recipeYield=recipe.get('recipeYield'),recipeIngredient=recipe.get('recipeIngredient')))
    return records


def parse_yield(value):
    if isinstance(value,list):
        value=next((v for v in value if re.search('serv|burrito|portion',str(v),re.I)),value[0] if value else '')
    if isinstance(value,dict):
        value=value.get('value','')
    text=normalize(value or '')
    match=QUANTITY.match(text)
    if not match:
        raise ValueError(f'Cannot determine recipe yield: {text!r}')
    servings=number(match[1])
    if servings<=0 or servings.denominator!=1:
        raise ValueError('A positive whole-number yield is required')
    notes=[]
    if match[2]:
        notes.append(f'Yield range {text}; uses the lower end ({servings}) for conservative per-serving shopping quantities.')
    if match[3] and not re.search('serv|portion|people',match[3],re.I):
        notes.append(f'Yield is {text}; one finished item is treated as one planned serving.')
    return int(servings),text,notes


def category(item,optional=False):
    text=item.lower()
    if optional:
        return 'Optional toppings'
    if re.search(r'\bwater\b',text):
        return 'Water'
    if any(x in text for x in ('stock','broth','beans','chickpeas','coconut milk','tomato paste')):
        return 'Canned goods'
    if any(x in text for x in ('salmon','shrimp','cod','tuna')):
        return 'Seafood'
    if any(x in text for x in ('chicken','ground beef','ground pork','sausage','lamb')):
        return 'Meat'
    if any(x in text for x in ('feta','cheddar','mozzarella','paneer','yogurt','cream','unsalted butter','eggs')):
        return 'Dairy'
    if any(x in text for x in ('rice','noodle','orzo','farro','tortilla','bun','pita','flatbread','roti','gnocchi','flour','cornstarch')):
        return 'Bread and grains'
    if any(x in text for x in ('salt','pepper flakes','black pepper','powder','cumin','coriander','fennel seed','garam','oil','vinegar','sauce','sugar','honey','mustard','miso','tahini','harissa','ghee','ketchup','cashew','turmeric','paprika','cayenne','wine')):
        return 'Oils and spices'
    return 'Produce'


def parse_ingredient(raw):
    text=normalize(raw)
    optional=bool(re.search(r'\boptional\b',text,re.I))
    if any(x in text.lower() for x in ('sign up','subscribe','full access','and more.','...','…')):
        raise ValueError('Ingredient list appears to be truncated or restricted')
    quantity=None
    unit='as needed'
    rest=text
    notes=[]
    amount=QUANTITY.match(text)
    if amount:
        minimum=number(amount[1])
        maximum=number(amount[2]) if amount[2] else minimum
        quantity=str(maximum)
        rest=amount[3]
        if maximum!=minimum:
            notes.append(f'Source range {amount[1]} to {amount[2]}; shopping uses the upper end.')
        unit='each'
    package=None
    if rest.startswith('('):
        package_match=re.match(r'^\(([^)]+)\)\s*(.*)',rest)
        if package_match:
            package,rest=package_match.groups()
    measurement=re.match(r'^(?:(packed|heaping|scant)\s+)?([A-Za-z]+)\.?\s+(.*)$',rest)
    if quantity is not None and measurement and measurement[2].lower() in UNIT_MAP:
        unit=UNIT_MAP[measurement[2].lower()]
        rest=measurement[3]
        if measurement[1]:
            notes.append(measurement[1]+' measure')
    # Garlic is commonly written as "2 garlic cloves" rather than "2 cloves garlic".
    if quantity is not None and re.match(r'^(?:fat |large |medium )?garlic cloves?\b',rest,re.I):
        unit='clove'
        rest=re.sub(r'^(?:fat |large |medium )?garlic cloves?','garlic',rest,flags=re.I)
    # Commas can belong to the ingredient itself ("boneless, skinless chicken"
    # or "tomato, cucumber and olives"). Only remove actual prep suffixes.
    item=re.sub(r'\s*\([^)]*\)','',rest).strip()
    item=re.split(r',\s*(?=(?:cut\b|trimmed\b|peeled\b|halved\b|quartered\b|torn\b|thinly\b|finely\b|coarsely\b|roughly\b|drained\b|skins\b|patted\b|divided\b|seeded\b|scrubbed\b|cored\b|such as\b|each\b|ends\b|plus\b|about\b|preferably\b|for serving\b|for garnishing\b))',item,maxsplit=1,flags=re.I)[0]
    item=re.sub(r'^(?:(?:finely|coarsely|roughly|freshly)\s+)?(?:minced|chopped|grated)\s+','',item,flags=re.I)
    item=re.sub(r'^whole\s+','',item,flags=re.I)
    if package:
        package=re.sub(r'\bounces?\b','oz',package)
        package=re.sub(r'\bpounds?\b','lb',package)
        item+=f' ({package})'
    if not item:
        raise ValueError('Ingredient name is empty')
    if 'see recipe' in text.lower():
        item+=' (prepared)'
        notes.append('Separate condiment recipe not supplied; listed as a prepared ingredient.')
    if quantity is None and re.search(r'\bsalt\b|\bpepper\b',item,re.I):
        unit='to taste'
    result=dict(item=item,quantity=quantity,unit=unit,category=category(item,optional),source_text=unescape(raw).replace('\xa0',' ').strip())
    if optional:
        result['optional']=True
        result['item']+=' (optional)'
    if result['category']=='Water':
        result['shopping']=False
    if notes:
        result['notes']=' '.join(notes)
    return result


def slug(text):
    return re.sub(r'[^a-z0-9]+','-',text.lower()).strip('-')


def import_records(records,root=ROOT):
    root=Path(root)
    recipes=json.loads((root/'data/recipes.json').read_text())
    sources=json.loads((root/'data/sources.json').read_text())
    by_id={r['id']:r for r in recipes}
    by_url={canonical_url(r['url']):r for r in recipes if r.get('url')}
    by_name={slug(r['name']):r for r in recipes}
    report=dict(imported=[],errors=[],duplicate_urls=[])
    seen=set()
    for record in records:
        if not isinstance(record,dict):
            report['errors'].append(dict(name='Invalid recipe record',error='Recipe data must be an object'))
            continue
        try:
            url=canonical_url(record.get('url') or '')
            if url in seen:
                report['duplicate_urls'].append(url)
                continue
            seen.add(url)
            name=normalize(record.get('name') or '')
            raw=record.get('recipeIngredient')
            if not name or not isinstance(raw,list) or not raw or not all(isinstance(x,str) and x.strip() for x in raw):
                raise ValueError('Recipe needs a name and a complete ingredient list')
            ingredients=[parse_ingredient(line) for line in raw]
            servings,yield_text,notes=parse_yield(record.get('recipeYield'))
            host=urlparse(url).netloc
            number=re.search(r'/recipes/(\d+)',url)
            alias=ALIASES.get(number[1]) if host=='cooking.nytimes.com' and number else None
            recipe=by_url.get(url) or by_id.get(alias)
            named=by_name.get(slug(name))
            if recipe is None and named and not named.get('url'):
                recipe=named
            source='NYT' if host=='cooking.nytimes.com' else next((key for key,value in sources.items() if value.get('url') and urlparse(value['url']).netloc==host),None)
            if not source:
                source='WEB-'+slug(host)
                sources[source]=dict(name=host,url=f'https://{host}/')
            added=recipe is None
            if added:
                identity=slug(name)+'-'+slug(source)
                if identity in by_id:
                    identity+='-'+str(len(recipes)+1)
                recipe=dict(id=identity,name=name,source=source,page=None,enabled=True)
                recipes.append(recipe)
                by_id[identity]=recipe
            recipe.update(url=url,source=source,source_title=name,servings=servings,source_yield=yield_text,
                          source_ingredients=[unescape(x).replace('\xa0',' ').strip() for x in raw],ingredients=ingredients,
                          ingredients_verified=True,verified_on=date.today().isoformat(),
                          notes='Imported from user-saved structured recipe data. '+ ' '.join(notes))
            by_url[url]=recipe
            by_name[slug(name)]=recipe
            report['imported'].append(dict(id=recipe['id'],name=recipe['name'],url=url,added=added,
                                           ingredient_count=len(ingredients),source_yield=yield_text,servings=servings,notes=notes))
        except (ValueError,TypeError,KeyError,ZeroDivisionError) as error:
            report['errors'].append(dict(name=str(record.get('name') or 'Unnamed recipe'),error=str(error)))
    # Validation is performed before any catalog changes are written.
    from planner import validate
    validate(recipes,json.loads((root/'data/settings.json').read_text()))
    if report['imported']:
        for filename,data in [('recipes.json',recipes),('sources.json',sources)]:
            destination=root/'data'/filename
            temporary=destination.with_suffix('.json.tmp')
            temporary.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
            temporary.replace(destination)
        destination=root/'data/imports/latest.json'
        destination.parent.mkdir(exist_ok=True)
        destination.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args()
    report=import_records(read_records(args.input),args.root)
    print(json.dumps(report,indent=2,ensure_ascii=False))
    if report['errors'] or not report['imported']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
