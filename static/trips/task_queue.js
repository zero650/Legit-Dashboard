(() => {
  const workspace = document.getElementById('task-workspace');
  if (!workspace) return;
  const storageKey = `legit-task-view:${workspace.dataset.user}`;
  // Explicit URLs always win; pagination is deliberately not remembered.
  try {
    if (!location.search && localStorage.getItem(storageKey)) {
      const saved = new URLSearchParams(localStorage.getItem(storageKey));
      saved.delete('page');
      if (saved.size) { location.replace(`${workspace.dataset.listUrl}?${saved}`); return; }
    }
    const params = new URLSearchParams(location.search);
    params.delete('page');
    localStorage.setItem(storageKey, params.toString());
  } catch (_) { /* Storage may be disabled; the URL remains the source of truth. */ }
  workspace.querySelectorAll('[data-reset]').forEach(link => link.addEventListener('click', () => {
    try { localStorage.removeItem(storageKey); } catch (_) { /* Optional preference. */ }
  }));

  const filterForm = document.getElementById('queue-filters');
  document.getElementById('filter-toggle').addEventListener('click', event => {
    const panel = document.getElementById('advanced-filters');
    panel.hidden = !panel.hidden;
    event.currentTarget.setAttribute('aria-expanded', String(!panel.hidden));
  });
  document.getElementById('task-sort').addEventListener('change', () => filterForm.requestSubmit());
  // Status filtering should also work when starting from the default open view.
  document.getElementById('status').addEventListener('change', event => {
    if (event.target.value) filterForm.elements.view.value = 'all';
  });
  const tasks = new Map(JSON.parse(document.getElementById('task-data').textContent).map(task => [String(task.id), task]));
  const rows = new Map([...workspace.querySelectorAll('[data-task-id]')].map(row => [row.dataset.taskId, row]));
  const csrf = workspace.querySelector('[name=csrfmiddlewaretoken]')?.value;
  const pending = new Set();
  let bulkBusy = false;
  const canEdit = Boolean(document.getElementById('bulk-form'));
  const refreshNotice = document.getElementById('refresh-notice');

  async function post(url, data) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(url, { method: 'POST', body: data, signal: controller.signal,
        headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrf } });
      if (response.redirected) throw new Error('Your session may have expired. Reload and sign in to continue.');
      if (response.status === 403) throw new Error('You do not have permission to save. Reload to check your access.');
      let payload;
      try { payload = await response.json(); } catch (_) { throw new Error('Could not save. Check your connection and retry.'); }
      if (!response.ok || !payload.ok) {
        const errors = payload.errors ? Object.entries(payload.errors).map(([field, values]) => `${field.replaceAll('_', ' ')}: ${values.map(value => value.message).join(' ')}`).join(' ') : '';
        throw new Error(errors || payload.error || (response.status === 403 ? 'You do not have permission to change these tasks.' : 'Could not save. Please retry.'));
      }
      return payload;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('Save timed out. Retry to confirm your changes.');
      throw error;
    } finally { clearTimeout(timeout); }
  }

  function renderRow(task) {
    const row = rows.get(String(task.id));
    row.dataset.tone = task.tone;
    row.querySelector('.task-title').textContent = task.name;
    row.querySelector('.due-label').textContent = task.due_label;
    const mobileContext = row.querySelector('.mobile-context');
    if (mobileContext) mobileContext.textContent = `${task.assigned_to} · ${task.status_label}`;
    row.querySelectorAll('[data-field]').forEach(field => {
      const key = field.dataset.field;
      field.value = key === 'assigned_to' ? task.assigned_to_id : task[key];
      field.setAttribute('aria-label', `${key.replaceAll('_', ' ')} for ${task.name}`);
      if (key === 'status') field.dataset.status = task.status;
    });
    const complete = row.querySelector('.complete-button');
    if (complete) {
      complete.textContent = task.status === 'done' ? '✓' : '';
      complete.setAttribute('aria-pressed', String(task.status === 'done'));
      complete.setAttribute('aria-label', `${task.status === 'done' ? 'Reopen' : 'Complete'} ${task.name}`);
      complete.title = task.status === 'done' ? 'Reopen task' : 'Mark complete';
    }
    row.querySelector('.row-select')?.setAttribute('aria-label', `Select ${task.name}`);
  }

  async function saveTask(id, changes) {
    if (pending.has(id) || bulkBusy) throw new Error('Please wait for the current save to finish.');
    const row = rows.get(id);
    pending.add(id);
    row.dataset.saving = 'true';
    row.dataset.error = 'false';
    row.querySelector('[data-save-state]').textContent = 'Saving…';
    row.querySelectorAll('button, select, input').forEach(control => control.disabled = true);
    updateSelection();
    const data = new FormData();
    Object.entries(changes).forEach(([key, value]) => data.set(key, value));
    try {
      const payload = await post(row.dataset.url, data);
      tasks.set(id, payload.task);
      renderRow(payload.task);
      row.querySelector('[data-save-state]').textContent = 'Saved';
      Object.entries(payload.counts).forEach(([key, count]) => {
        workspace.querySelector(`[data-count="${key}"]`).textContent = count;
      });
      refreshNotice.hidden = false;
      return payload.task;
    } catch (error) {
      renderRow(tasks.get(id));
      row.dataset.error = 'true';
      row.querySelector('[data-save-state]').textContent = error.message || 'Could not save. Please retry.';
      throw error;
    } finally {
      pending.delete(id);
      row.dataset.saving = 'false';
      row.querySelectorAll('button, select, input').forEach(control => control.disabled = !canEdit && !control.matches('[data-open-task]'));
      updateSelection();
    }
  }

  rows.forEach((row, id) => {
    const retry = row.querySelector('[data-retry]');
    const undo = row.querySelector('[data-undo]');
    let failedChange = null;
    let completionStatus = null;
    async function perform(changes, undoing = false) {
      if (pending.has(id) || bulkBusy) return;
      retry.hidden = true;
      const previousStatus = tasks.get(id).status;
      try {
        await saveTask(id, changes);
        failedChange = null;
        if ('status' in changes) {
          if (!undoing && changes.status === 'done' && previousStatus !== 'done') {
            completionStatus = previousStatus;
            undo.hidden = false;
          } else { completionStatus = null; undo.hidden = true; }
        }
      } catch (_) { failedChange = { changes, undoing }; retry.hidden = false; }
    }
    row.querySelectorAll('[data-field]').forEach(field => field.addEventListener('change', () => perform({ [field.dataset.field]: field.value })));
    row.querySelector('.complete-button')?.addEventListener('click', () => perform({status: tasks.get(id).status === 'done' ? 'not_started' : 'done'}));
    retry.addEventListener('click', () => { if (failedChange) perform(failedChange.changes, failedChange.undoing); });
    undo.addEventListener('click', () => { if (completionStatus !== null) perform({ status: completionStatus }, true); });
    row.querySelector('[data-open-task]').addEventListener('click', () => openDrawer(id));
  });

  const bulkForm = document.getElementById('bulk-form');
  const selectAll = document.getElementById('select-all');
  const selectionToggle = document.getElementById('selection-toggle');
  workspace.classList.add('selection-ready');
  function setSelecting(selecting) {
    workspace.classList.toggle('is-selecting', selecting);
    if (selectionToggle) {
      selectionToggle.setAttribute('aria-pressed', String(selecting));
      selectionToggle.textContent = selecting ? 'Done selecting' : 'Select tasks';
    }
  }
  const selectedRows = () => [...rows.values()].filter(row => row.querySelector('.row-select')?.checked);
  function updateSelection() {
    if (!canEdit) return;
    const count = selectedRows().length;
    if (count) setSelecting(true);
    document.getElementById('selection-count').textContent = `${count} selected on this page`;
    bulkForm.hidden = !count;
    selectAll.checked = count > 0 && count === rows.size;
    selectAll.indeterminate = count > 0 && count < rows.size;
    bulkForm.querySelectorAll('button, select, input').forEach(control => control.disabled = bulkBusy || pending.size > 0);
  }
  if (bulkForm) {
    selectionToggle.hidden = false;
    selectionToggle.addEventListener('click', () => {
      const selecting = !workspace.classList.contains('is-selecting');
      if (!selecting) rows.forEach(row => { row.querySelector('.row-select').checked = false; });
      setSelecting(selecting);
      updateSelection();
    });
    rows.forEach(row => row.querySelector('.row-select').addEventListener('change', updateSelection));
    selectAll.addEventListener('change', () => {
      rows.forEach(row => { row.querySelector('.row-select').checked = selectAll.checked; });
      updateSelection();
    });
    document.getElementById('clear-selection').addEventListener('click', () => {
      rows.forEach(row => { row.querySelector('.row-select').checked = false; });
      setSelecting(false);
      updateSelection();
    });
    document.getElementById('bulk-field').addEventListener('change', event => {
      bulkForm.querySelectorAll('[data-bulk-value]').forEach(control => control.hidden = control.dataset.bulkValue !== event.target.value);
    });
    bulkForm.addEventListener('submit', async event => {
      event.preventDefault();
      if (pending.size || bulkBusy) return;
      const data = new FormData();
      selectedRows().forEach(row => data.append('task_ids', row.dataset.taskId));
      const field = document.getElementById('bulk-field').value;
      data.set('field', field);
      data.set('value', bulkForm.querySelector(`[data-bulk-value="${field}"]`).value);
      bulkBusy = true;
      updateSelection();
      workspace.querySelectorAll('.queue-table button, .queue-table input, .queue-table select').forEach(control => control.disabled = true);
      const feedback = document.getElementById('bulk-feedback');
      feedback.textContent = 'Saving selected tasks…';
      try {
        await post(workspace.dataset.bulkUrl, data);
        try { sessionStorage.setItem('legit-task-bulk-result', `${selectedRows().length} tasks updated.`); } catch (_) { /* Saving succeeded even if storage is unavailable. */ }
        const url = new URL(location.href);
        url.searchParams.delete('page');
        location.assign(url);
      } catch (error) {
        feedback.textContent = error.message;
        bulkBusy = false;
        workspace.querySelectorAll('.queue-table button, .queue-table input, .queue-table select').forEach(control => control.disabled = false);
        updateSelection();
      }
    });
    try {
      const result = sessionStorage.getItem('legit-task-bulk-result');
      if (result) { refreshNotice.textContent = result; refreshNotice.hidden = false; sessionStorage.removeItem('legit-task-bulk-result'); }
    } catch (_) { /* Optional feedback persistence. */ }
  }

  const drawer = document.getElementById('task-drawer');
  const drawerForm = document.getElementById('drawer-form');
  const drawerFeedback = document.getElementById('drawer-feedback');
  let drawerId = null;
  let drawerInitial = '';
  let drawerBusy = false;
  const drawerValues = () => Object.fromEntries(['name', 'assigned_to', 'status', 'due_date', 'notes'].map(key => [key, drawerForm.elements[key].value]));
  function openDrawer(id) {
    if (pending.has(id) || bulkBusy) return;
    drawerId = id;
    const task = tasks.get(id);
    document.getElementById('drawer-heading').textContent = task.name;
    document.getElementById('drawer-trip').textContent = task.trip;
    for (const key of ['name', 'notes', 'status', 'due_date', 'assigned_to']) drawerForm.elements[key].value = key === 'assigned_to' ? task.assigned_to_id : task[key];
    drawerInitial = JSON.stringify(drawerValues());
    drawerFeedback.textContent = '';
    drawerFeedback.dataset.error = 'false';
    drawer.showModal();
  }
  function closeDrawer() {
    if (drawerBusy) return;
    if (canEdit && JSON.stringify(drawerValues()) !== drawerInitial && !window.confirm('Discard your unsaved changes?')) return;
    drawer.close();
  }
  document.getElementById('close-drawer').addEventListener('click', closeDrawer);
  drawer.addEventListener('cancel', event => { event.preventDefault(); closeDrawer(); });
  drawerForm.addEventListener('submit', async event => {
    event.preventDefault();
    if (!canEdit || drawerBusy) return;
    const values = drawerValues();
    const initial = JSON.parse(drawerInitial);
    const changes = Object.fromEntries(Object.entries(values).filter(([key, value]) => value !== initial[key]));
    if (!Object.keys(changes).length) { drawerFeedback.textContent = 'No changes to save.'; return; }
    drawerBusy = true;
    drawerForm.querySelector('fieldset').disabled = true;
    drawerForm.querySelector('[type=submit]').disabled = true;
    drawerFeedback.textContent = 'Saving…';
    drawerFeedback.dataset.error = 'false';
    try {
      const task = await saveTask(drawerId, changes);
      drawerInitial = JSON.stringify(values);
      document.getElementById('drawer-heading').textContent = task.name;
      drawerFeedback.textContent = 'All changes saved.';
      rows.get(drawerId).querySelector('[data-retry]').hidden = true;
      rows.get(drawerId).querySelector('[data-undo]').hidden = true;
    } catch (error) {
      drawerFeedback.textContent = `${error.message} Your edits are kept here; press Save changes to retry.`;
      drawerFeedback.dataset.error = 'true';
    } finally {
      drawerBusy = false;
      drawerForm.querySelector('fieldset').disabled = false;
      drawerForm.querySelector('[type=submit]').disabled = false;
    }
  });
  window.addEventListener('beforeunload', event => {
    if (pending.size || (drawer.open && canEdit && JSON.stringify(drawerValues()) !== drawerInitial)) {
      event.preventDefault(); event.returnValue = '';
    }
  });
})();
