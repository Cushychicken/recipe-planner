import copy
from datetime import date, datetime
import sys
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from planner import build_plan, load, quantity, select, shopping_list, validate, week_start, ROOT


def recipe(i, verified=True):
    return dict(id=f'r-{i}', name=f'Recipe {i}', source='TN', servings=4,
                enabled=True, ingredients_verified=verified,
                ingredients=[dict(item='olive oil', quantity='1',unit='tbsp',category='Pantry')])


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.settings = dict(dinners=7,servings=4,avoid_repeat_weeks=4,pantry=[])
        self.recipes = [recipe(i) for i in range(40)]

    def test_saturday_and_sunday_target_same_week_across_dst(self):
        zone = ZoneInfo('America/New_York')
        for saturday, sunday in [('2026-10-31T23:00','2026-11-01'),('2027-03-13T23:00','2027-03-14')]:
            self.assertEqual(week_start(datetime.fromisoformat(saturday).replace(tzinfo=zone)),date.fromisoformat(sunday))
            self.assertEqual(week_start(datetime.fromisoformat(sunday+'T04:00').replace(tzinfo=zone)),date.fromisoformat(sunday))

    def test_deterministic_and_no_repeats_for_four_weeks(self):
        history=[]
        for start in [date(2026,11,d) for d in (1,8,15,22,29)]:
            selected,draft=select(self.recipes,start,self.settings,history)
            self.assertFalse(draft)
            self.assertEqual(selected,select(self.recipes,start,self.settings,history)[0])
            used={m['recipe_id'] for p in history for m in p['meals']}
            self.assertFalse(used & {r['id'] for r in selected})
            history.append(build_plan(self.recipes,start,self.settings,history))

    def test_ready_plan_survives_rerun(self):
        start=date(2026,11,1)
        plan=build_plan(self.recipes,start,self.settings,[])
        self.assertEqual(plan,build_plan(list(reversed(self.recipes)),start,self.settings,[plan],plan))

    def test_draft_never_emits_partial_shopping_list(self):
        self.recipes[0]['ingredients_verified']=False
        plan=build_plan(self.recipes[:7],date(2026,11,1),self.settings,[])
        self.assertTrue(plan['draft'])
        self.assertEqual([],plan['shopping'])

    def test_draft_becomes_ready_after_import(self):
        old=build_plan([recipe(i,False) for i in range(10)],date(2026,11,1),self.settings,[])
        new=build_plan(self.recipes,date(2026,11,1),self.settings,[old],old)
        self.assertFalse(new['draft'])

    def test_scaling_unit_conversion_and_pantry(self):
        a=recipe(0)
        b=recipe(1)
        b['ingredients'][0].update(quantity='3',unit='tsp')
        result=shopping_list([a,b],8,['olive oil'])
        self.assertEqual(1,len(result))
        self.assertEqual('4 tbsp',quantity(result[0]))
        self.assertTrue(result[0]['pantry'])
        b['ingredients'][0]['unit']='g'
        self.assertEqual(2,len(shopping_list([a,b],4,[])))

    def test_invalid_verified_recipe_rejected(self):
        bad=recipe(0)
        bad['ingredients']=[]
        with self.assertRaises(ValueError): validate([bad],self.settings)

    def test_real_catalog_valid(self):
        validate(load(ROOT/'data/recipes.json'),load(ROOT/'data/settings.json'))


if __name__=='__main__': unittest.main()
