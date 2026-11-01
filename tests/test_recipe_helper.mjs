import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {parseLinks,CAPTURE} from '../tools/recipe-library.mjs';

test('link collection deduplicates URLs and rejects credentials and unsafe schemes',()=>{
  assert.deepEqual(parseLinks('https://example.com/recipe\nhttps://example.com/recipe'),['https://example.com/recipe']);
  for(const value of ['http://example.com/recipe','javascript:alert(1)','https://user:password@example.com/recipe',''])assert.throws(()=>parseLinks(value));
});
test('capture returns only ingredient facts, excluding account state and instructions',()=>{
  const schema={'@graph':[{'@type':['Recipe'],name:'Test recipe',url:'https://example.com/dinner',recipeYield:'4 servings',recipeIngredient:['1 cup rice'],recipeInstructions:'not exported',privateUser:'not exported'}]};
  const document={title:'Recipe',readyState:'complete',querySelector:()=>null,querySelectorAll:()=>[{textContent:JSON.stringify(schema)}]};
  const result=vm.runInNewContext(CAPTURE,{document,location:{origin:'https://example.com',pathname:'/dinner'}});
  assert.equal(result.recipes.length,1);
  assert.deepEqual(Object.keys(result.recipes[0]).sort(),['name','recipeIngredient','recipeYield','url'].sort());
  assert.equal(JSON.stringify(result).includes('not exported'),false);
});
