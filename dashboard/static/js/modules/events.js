/* ==========================================================================
   Root Event Delegation Engine
   Dispatches [data-action], [data-change], and [data-input]
   Automatically falls back to closest [data-key] for dataset.id (Rule 3)
   ========================================================================== */

const actionRegistry = new Map();
const changeRegistry = new Map();
const inputRegistry = new Map();

export function registerAction(name, handler) {
  actionRegistry.set(name, handler);
}

export function registerChange(name, handler) {
  changeRegistry.set(name, handler);
}

export function registerInput(name, handler) {
  inputRegistry.set(name, handler);
}

/**
 * Extracts action dataset parameters, automatically falling back to closest [data-key]
 * as dataset.id when dataset.id is not explicitly specified on the action element (Rule 3).
 */
function extractActionData(target) {
  const data = Object.assign({}, target.dataset);
  if (!data.id) {
    const keyEl = target.closest('[data-key]');
    if (keyEl && keyEl.dataset && keyEl.dataset.key) {
      data.id = keyEl.dataset.key;
    }
  }
  return data;
}

export function initEventDelegation() {
  // Click actions: [data-action]
  document.addEventListener('click', (e) => {
    const target = e.target.closest('[data-action]');
    if (!target) return;
    const action = target.dataset.action;
    const handler = actionRegistry.get(action);
    if (handler) {
      const data = extractActionData(target);
      handler(data, target, e);
    } else {
      console.warn(`[Events] No handler registered for data-action="${action}"`);
    }
  });

  // Change actions: [data-change]
  document.addEventListener('change', (e) => {
    const target = e.target.closest('[data-change]');
    if (!target) return;
    const changeName = target.dataset.change;
    const handler = changeRegistry.get(changeName);
    if (handler) {
      const data = extractActionData(target);
      handler(data, target, e);
    }
  });

  // Input events: [data-input]
  document.addEventListener('input', (e) => {
    const target = e.target.closest('[data-input]');
    if (!target) return;
    const inputName = target.dataset.input;
    const handler = inputRegistry.get(inputName);
    if (handler) {
      handler(target.value, target, e);
    }
  });
}
