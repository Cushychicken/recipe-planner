from datetime import date
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from planner import ROOT, build_plan, load, quantity
from template_sheet import render_docx, render_template_sheet
from docx import Document
from pypdf import PdfReader


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.recipes=load(ROOT/'data/recipes.json')
        self.sources=load(ROOT/'data/sources.json')
        self.plan=build_plan(self.recipes,date(2026,11,1),load(ROOT/'data/settings.json'),[])

    def test_template_has_correct_weekday_meals_and_no_fake_lunches(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'plan.docx'
            render_docx(path,self.plan,self.recipes,self.sources,quantity)
            doc=Document(path)
            table=doc.tables[0]
            self.assertEqual('Lunch Options',table.cell(1,0).text)
            self.assertEqual('Lunch Ingredients',table.cell(1,4).text)
            by_id={r['id']:r for r in self.recipes}
            for i,meal in enumerate(self.plan['meals'],1):
                expected='Leftovers / takeout' if meal.get('kind')=='leftovers' else by_id[meal['recipe_id']]['name']
                self.assertIn(expected,table.cell(2,i).text)
            self.assertIn('DRAFT',table.cell(3,1).text)
            self.assertGreater(doc.sections[0].page_width,doc.sections[0].page_height)

    @unittest.skipUnless(shutil.which('soffice') or shutil.which('libreoffice'),'LibreOffice required')
    def test_populated_shopping_sheet_is_exactly_one_page(self):
        self.plan['draft']=False
        self.plan['shopping']=[dict(item=f'ingredient {i:02d}',quantity='2',unit='cup',
                                    category=['Produce','Meat','Pantry'][i//14],pantry=False)
                               for i in range(42)]
        for i, meal in enumerate(self.plan['meals']):
            meal['kind']='recipe'
            meal['recipe_id']=self.recipes[i]['id']
            meal['ingredients_verified']=True
            meal['shopping']=self.plan['shopping'][i*6:(i+1)*6]
        with tempfile.TemporaryDirectory() as directory:
            docx=Path(directory)/'plan.docx'
            pdf=Path(directory)/'plan.pdf'
            render_template_sheet(docx,pdf,self.plan,self.recipes,self.sources,quantity)
            table=Document(docx).tables[0]
            for i in range(7):
                for item in self.plan['meals'][i]['shopping']:
                    self.assertIn(item['item'],table.cell(3,i+1).text)
                next_item=self.plan['meals'][(i+1)%7]['shopping'][0]['item']
                self.assertNotIn(next_item,table.cell(3,i+1).text)
            output=PdfReader(pdf)
            self.assertEqual(1,len(output.pages))
            text=' '.join(output.pages[0].extract_text().split())
            for i in range(42):
                self.assertIn(f'ingredient {i:02d}',text)
            self.assertNotIn('DRAFT',text)


if __name__=='__main__':unittest.main()
