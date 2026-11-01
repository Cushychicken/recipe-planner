/* Per-week choices stay in this browser; printing always uses the visible plan. */
(function () {
  'use strict';

  function restoreChoices(saved, initial, catalog) {
    if (!Array.isArray(saved) || saved.length !== initial.length) return initial.map(x => ({...x}));
    const ids = new Set(catalog.map(r => r.id));
    return initial.map((fallback, i) => {
      const choice = saved[i];
      if (choice && choice.kind === 'leftovers') {
        return {kind: 'leftovers', recipe_id: ids.has(choice.recipe_id) ? choice.recipe_id : fallback.recipe_id};
      }
      if (choice && choice.kind === 'recipe' && ids.has(choice.recipe_id)) return {kind: 'recipe', recipe_id: choice.recipe_id};
      return {...fallback};
    });
  }

  function chooseRandom(catalog, choices, day, random = Math.random) {
    const current = choices[day].recipe_id;
    const pool = catalog.filter(r => r.enabled && r.id !== current);
    const used = new Set(choices.filter((c, i) => i !== day && c.kind === 'recipe').map(c => c.recipe_id));
    const fresh = pool.filter(r => !used.has(r.id));
    const candidates = fresh.length ? fresh : pool;
    return candidates.length ? {kind: 'recipe', recipe_id: candidates[Math.floor(random() * candidates.length)].id} : null;
  }

  function toggleLeftovers(choice, fallback) {
    return choice.kind === 'leftovers' ? {...fallback, kind: fallback.recipe_id ? 'recipe' : 'empty'} : {kind: 'leftovers', recipe_id: choice.recipe_id};
  }

  function dayContents(choice, catalog) {
    if (choice.kind === 'leftovers') return {name: 'Leftovers / takeout', verified: true, shopping: [], leftovers: true};
    return catalog.find(r => r.id === choice.recipe_id) || {name: '', verified: true, shopping: []};
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = {restoreChoices, chooseRandom, toggleLeftovers, dayContents};
  if (typeof document === 'undefined') return;

  const data = JSON.parse(document.getElementById('planner-data').textContent);
  const key = `meal-planner:v1:${data.week}`;
  let saved;
  let storageAvailable = true;
  try { saved = JSON.parse(localStorage.getItem(key)); } catch (_) { storageAvailable = false; }
  let choices = restoreChoices(saved, data.initial, data.catalog);
  const element = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  };

  function render() {
    let pending = 0;
    const sources = new Set();
    choices.forEach((choice, day) => {
      const recipe = dayContents(choice, data.catalog);
      const dinner = document.getElementById(`dinner-${day}`);
      const shopping = document.getElementById(`shopping-${day}`);
      dinner.replaceChildren();
      shopping.replaceChildren();
      const title = element('strong');
      if (recipe.url && /^https?:\/\//i.test(recipe.url)) {
        const link = element('a', recipe.name);
        link.href = recipe.url;
        title.append(link);
      } else title.textContent = recipe.name;
      dinner.append(title);
      if (recipe.reference) dinner.append(element('small', recipe.reference));
      if (recipe.source) sources.add(recipe.source);
      if (recipe.leftovers) shopping.append(element('p', 'No groceries needed.', 'pending'));
      else if (!recipe.verified) {
        pending++;
        shopping.append(element('p', 'Ingredients pending verification.', 'pending'));
      } else {
        let previous;
        recipe.shopping.forEach(row => {
          if (row.category !== previous) {
            shopping.append(element('h3', row.category));
            previous = row.category;
          }
          const label = element('label');
          const checkbox = element('input');
          checkbox.type = 'checkbox';
          label.append(checkbox, element('span', `${row.item} - ${row.quantity}`));
          shopping.append(label);
        });
      }
      document.querySelector(`[data-action="leftovers"][data-day="${day}"]`).setAttribute('aria-pressed', String(choice.kind === 'leftovers'));
    });
    const status = document.getElementById('plan-status');
    status.hidden = pending === 0;
    status.textContent = pending ? `Draft plan. Ingredient lists for ${pending} dinner${pending === 1 ? '' : 's'} still need verification.` : '';
    document.getElementById('source-legend').textContent = [...sources].sort().map(code => `${code}: ${data.sources[code]?.name || code}`).join(' · ');
    const modified = JSON.stringify(choices) !== JSON.stringify(data.initial);
    document.querySelectorAll('[data-original-download]').forEach(link => { link.hidden = modified; });
    document.getElementById('reset-plan').hidden = !modified;
    document.getElementById('save-status').textContent = storageAvailable ? 'Changes are saved in this browser. Print includes your selections.' : 'Changes could not be saved. Keep this tab open; Print includes your selections.';
  }

  function persist() {
    try { localStorage.setItem(key, JSON.stringify(choices)); storageAvailable = true; }
    catch (_) { storageAvailable = false; }
    render();
  }
  document.querySelectorAll('[data-action]').forEach(button => {
    button.addEventListener('click', () => {
      const day = Number(button.dataset.day);
      if (button.dataset.action === 'random') {
        const replacement = chooseRandom(data.catalog, choices, day);
        if (!replacement) return;
        choices[day] = replacement;
      } else {
        const previous = choices[day].recipe_id;
        choices[day] = choices[day].kind === 'leftovers' && !previous
          ? chooseRandom(data.catalog, choices, day) || data.initial[day]
          : toggleLeftovers(choices[day], previous ? {kind: 'recipe', recipe_id: previous} : data.initial[day]);
      }
      persist();
    });
  });
  document.getElementById('reset-plan').addEventListener('click', () => { choices = data.initial.map(x => ({...x})); persist(); });
  document.getElementById('print-plan').addEventListener('click', () => window.print());
  render();
})();
