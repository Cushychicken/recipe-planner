import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from import_recipes import canonical_url, import_records, parse_html, parse_ingredient, parse_yield, read_records


class RecipeImportTests(unittest.TestCase):
    def test_fraction_range_and_package(self):
        item=parse_ingredient('1 ½ teaspoons ground turmeric')
        self.assertEqual(('3/2','tsp','ground turmeric'),(item['quantity'],item['unit'],item['item']))
        item=parse_ingredient('¼ to ½ teaspoon crushed red pepper')
        self.assertEqual('1/2',item['quantity'])
        self.assertIn('upper end',item['notes'])
        item=parse_ingredient('2 (15-ounce) cans white beans, drained and rinsed')
        self.assertEqual(('2','can','white beans (15-oz)'),(item['quantity'],item['unit'],item['item']))

    def test_food_names_are_not_lost_at_descriptor_commas(self):
        self.assertEqual('boneless, skinless chicken thighs',parse_ingredient('1 pound boneless, skinless chicken thighs, cut into 1-inch pieces')['item'])
        self.assertEqual('tomato, cucumber and olives',parse_ingredient('Chopped tomato, cucumber and olives, for serving')['item'])
        self.assertEqual('potato gnocchi (16- to 17-oz)',parse_ingredient('1 (16- to 17-ounce) package potato gnocchi (shelf-stable, fresh or frozen)')['item'])

    def test_no_invented_amounts_or_partial_paywall_import(self):
        item=parse_ingredient('Kimchi, for serving (optional)')
        self.assertIsNone(item['quantity'])
        self.assertTrue(item['optional'])
        self.assertFalse(parse_ingredient('½ cup boiling water')['shopping'])
        with self.assertRaises(ValueError):parse_ingredient('... and more. Sign up for full access')

    def test_yield_ranges_and_items_preserve_the_original_meaning(self):
        servings,text,notes=parse_yield('4 to 6 servings')
        self.assertEqual((4,'4 to 6 servings'),(servings,text))
        self.assertTrue(notes)
        servings,text,notes=parse_yield('6 burritos')
        self.assertEqual(6,servings)
        self.assertIn('one finished item',notes[0])
        with self.assertRaises(ValueError):parse_yield('unknown')

    def test_only_recipe_facts_leave_html(self):
        html='<link rel="canonical" href="https://example.com/dinner"><script type="application/ld+json">'+json.dumps({'@type':'Recipe','name':'Dinner','recipeYield':'4 servings','recipeIngredient':['1 cup rice'],'private':'do not retain','recipeInstructions':'do not retain'})+'</script><script>accountSecret="do not retain"</script>'
        rows=parse_html(html)
        self.assertEqual({'name','url','recipeYield','recipeIngredient'},set(rows[0]))
        self.assertNotIn('do not retain',json.dumps(rows))
        self.assertEqual('https://cooking.nytimes.com/recipes/123-test',canonical_url('//cooking.nytimes.com/recipes/123-test?tracking=1'))
        with self.assertRaises(ValueError):canonical_url('')

    def test_zip_paths_are_never_extracted_and_repeat_import_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'data').mkdir()
            (root/'data/recipes.json').write_text('[]')
            (root/'data/sources.json').write_text('{}')
            (root/'data/settings.json').write_text(json.dumps(dict(dinners=7,servings=4)))
            record=dict(name='New Dinner',url='https://example.com/dinner',recipeYield='4 servings',recipeIngredient=['1 cup rice'])
            html='<script type="application/ld+json">'+json.dumps(dict(record,**{'@type':'Recipe'}))+'</script>'
            archive=root/'saved.zip'
            with ZipFile(archive,'w') as output:output.writestr('../../outside.html',html)
            records=read_records(archive)
            first=import_records(records,root)
            second=import_records(records,root)
            self.assertTrue(first['imported'][0]['added'])
            self.assertFalse(second['imported'][0]['added'])
            self.assertEqual(1,len(json.loads((root/'data/recipes.json').read_text())))

    def test_restricted_record_does_not_replace_verified_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'data').mkdir()
            original=dict(id='keep',name='Keep',url='https://example.com/keep',source='WEB',page=None,enabled=True,servings=4,ingredients_verified=True,ingredients=[dict(item='rice',quantity='1',unit='cup',category='Grains')])
            (root/'data/recipes.json').write_text(json.dumps([original]))
            (root/'data/sources.json').write_text('{}')
            (root/'data/settings.json').write_text(json.dumps(dict(dinners=7,servings=4)))
            report=import_records([dict(name='Keep',url=original['url'],recipeYield='4 servings',recipeIngredient=['Sign up for full access'])],root)
            self.assertTrue(report['errors'])
            self.assertEqual([original],json.loads((root/'data/recipes.json').read_text()))


if __name__=='__main__':unittest.main()
