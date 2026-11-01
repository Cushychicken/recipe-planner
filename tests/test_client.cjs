const {test} = require('node:test');
const assert = require('node:assert/strict');
const {restoreChoices, chooseRandom, toggleLeftovers, dayContents} = require('../scripts/planner-client.js');
const catalog = [
  {id:'a', enabled:true, shopping:[{item:'apples'}]},
  {id:'b', enabled:true, shopping:[{item:'beef'}]},
  {id:'c', enabled:true, shopping:[{item:'carrots'}]},
  {id:'d', enabled:false, shopping:[]}
];
const initial = [{kind:'recipe',recipe_id:'a'},{kind:'recipe',recipe_id:'b'}];

test('random changes this day and avoids other days and disabled recipes', () => {
  assert.deepEqual(chooseRandom(catalog,initial,0,()=>0),{kind:'recipe',recipe_id:'c'});
  assert.equal(initial[0].recipe_id,'a');
  assert.equal(initial[1].recipe_id,'b');
});
test('random selection relaxes duplicate avoidance when the pool is exhausted', () => {
  assert.equal(chooseRandom(catalog.slice(0,2),initial,0,()=>0).recipe_id,'b');
  assert.equal(chooseRandom(catalog.slice(0,1),initial,0),null);
});
test('leftovers supersedes the recipe and produces no groceries', () => {
  const choice=toggleLeftovers(initial[0],initial[0]);
  assert.equal(choice.kind,'leftovers');
  assert.deepEqual(dayContents(choice,catalog).shopping,[]);
  assert.equal(dayContents(choice,catalog).name,'Leftovers / takeout');
  assert.deepEqual(toggleLeftovers(choice,initial[0]),initial[0]);
});
test('recipe choices expose only that recipe’s shopping list', () => {
  assert.deepEqual(dayContents(initial[0],catalog).shopping,[{item:'apples'}]);
  assert.deepEqual(dayContents(initial[1],catalog).shopping,[{item:'beef'}]);
});
test('reload retains valid choices and repairs malformed or deleted recipe IDs', () => {
  const saved=[{kind:'leftovers',recipe_id:'a'},{kind:'recipe',recipe_id:'c'}];
  assert.deepEqual(restoreChoices(JSON.parse(JSON.stringify(saved)),initial,catalog),saved);
  assert.deepEqual(restoreChoices([{kind:'recipe',recipe_id:'deleted'},null],initial,catalog),initial);
  assert.deepEqual(restoreChoices(null,initial,catalog),initial);
});
