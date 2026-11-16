'use strict';
const $ = (id) => document.getElementById(id);
const state = {instances: [], selected: localStorage.getItem('exy.workspace'), data: null, scope: 'week', busy: false, loading: false, receivedAt: 0, timerSignature: '', goalSignature: '', pending: null};
const token = document.querySelector('meta[name="exy-token"]').content;
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const hours = (value) => value == null ? 'Not set' : value < 1 ? `${Math.round(value * 60)}m` : `${Number(value.toFixed(1))}h`;
const clock = (value) => {const s = Math.max(0, Math.floor(value)); return [Math.floor(s/3600), Math.floor(s/60)%60, s%60].map(n => String(n).padStart(2,'0')).join(':');};
const dateLabel = (date, options) => new Date(date+'T12:00:00Z').toLocaleDateString('en', {...options, timeZone:'UTC'});
const estimate = (goal) => goal.estimate_hours.min == null || goal.estimate_hours.max == null ? 'Estimate not set' : `${hours(goal.estimate_hours.min)} - ${hours(goal.estimate_hours.max)}`;
const isLeaf = (goal) => !state.data.goals.some(g => g.parent_id === goal.id && g.status !== 'dropped');
function notice(message) {$('notice').textContent = message; $('notice').classList.toggle('hidden', !message);}
async function api(path, body) {
  const response = await fetch(path, body ? {method:'POST', headers:{'Content-Type':'application/json','X-Exy-Token':token}, body:JSON.stringify(body)} : {cache:'no-store'});
  const result = await response.json();
  if (!response.ok) {const error = new Error(result.error || 'Unable to complete the request'); error.confirmedFailure = true; throw error;}
  return result;
}
function renderSidebar() {
  const signature = JSON.stringify([state.instances, state.selected]);
  if (signature === state.sidebarSignature) return;
  state.sidebarSignature = signature;
  $('workspace-count').textContent = state.instances.length;
  $('workspaces').innerHTML = state.instances.map(item => `<button class="workspace-button ${item.name === state.selected ? 'active' : ''}" data-workspace="${esc(item.name)}" aria-current="${item.name === state.selected ? 'page' : 'false'}"><span class="workspace-monogram">${esc(item.name.replace(/^exy-/, '').slice(0,2).toUpperCase())}</span><span><strong>${esc(item.name)}</strong><small>${item.error ? 'Needs attention' : item.total ? `${item.completed} / ${item.total} outcomes` : 'Foundation in progress'}</small></span>${item.timers.some(t => t.status === 'running') ? '<span class="workspace-live" aria-label="Timer running"></span>' : ''}</button>`).join('') || '<p class="sidebar-hint">Your workspaces will appear here.</p>';
}
async function selectWorkspace(name) {
  if (state.busy) return;
  state.selected = name; localStorage.setItem('exy.workspace', name);
  state.data = null; state.timerSignature = ''; state.goalSignature = '';
  $('search').value = ''; $('status-filter').value = ''; $('focus-activity').value = '';
  $('focus-goal').innerHTML = '<option value="">General study</option>';
  $('task-dialog').close(); notice(''); renderSidebar();
  await loadDetail(name);
}
async function loadDetail(name) {
  try {
    const value = await api('/api/instance?name='+encodeURIComponent(name));
    if (state.selected !== name) return;
    state.data = value; state.receivedAt = Date.now(); render();
    $('sync-status').textContent = 'Synced just now';
  } catch(error) {
    if (state.selected !== name) return;
    state.data = null; $('workspace-view').classList.add('hidden');
    notice(error.message + '. Open the workspace connection to check its folder.');
    // Keep a connection button available even when its state cannot be read.
    $('no-workspace').classList.remove('hidden');
    $('sync-status').textContent = 'Unable to read workspace';
    $('error-settings').classList.remove('hidden');
  }
}
async function refresh() {
  if (state.loading || state.busy) return;
  state.loading = true;
  try {
    const result = await api('/api/instances'); state.instances = result.instances;
    if (!state.instances.some(i => i.name === state.selected)) {
      state.selected = state.instances[0]?.name ?? null; state.data = null; state.goalSignature = ''; state.timerSignature = '';
    }
    renderSidebar();
    $('error-settings').classList.add('hidden');
    $('no-workspace').classList.toggle('hidden', Boolean(state.selected));
    $('workspace-view').classList.toggle('hidden', !state.data);
    if (state.selected) await loadDetail(state.selected);
    else $('sync-status').textContent = 'Ready to connect';
  } catch(error) {notice('Connection lost. '+error.message); $('sync-status').textContent = 'Offline - timers remain saved';}
  finally {state.loading = false;}
}
function render() {
  const d = state.data; if (!d) return;
  $('no-workspace').classList.add('hidden'); $('workspace-view').classList.remove('hidden');
  $('workspace-name').textContent = d.name;
  $('objective-title').textContent = d.objective.title || d.foundation.objective || 'An open space for your next learning goal.';
  $('today-label').textContent = dateLabel(d.week.today,{weekday:'short',month:'short',day:'numeric',year:'numeric'});
  const leaves = d.goals.filter(g => isLeaf(g) && g.status !== 'dropped');
  $('completed-count').textContent = leaves.filter(g => g.status === 'completed').length;
  $('goal-count').textContent = `of ${leaves.length} outcomes`;
  $('week-hours').textContent = d.pace ? hours(d.pace.total_logged_hours) : 'Not set';
  $('week-target').textContent = d.plan?.budget_hours != null ? `/ ${hours(d.plan.budget_hours)} planned` : 'No weekly plan';
  $('week-range').textContent = `${dateLabel(d.week.start,{month:'short',day:'numeric'})} - ${dateLabel(d.week.end,{month:'short',day:'numeric'})}`;
  $('today-hours').textContent = d.pace ? hours(d.pace.daily_logged_hours[d.week.today]) : 'Not set';
  $('today-target').textContent = d.plan?.daily_hours?.[d.week.today] != null ? `/ ${hours(d.plan.daily_hours[d.week.today])} planned` : 'No daily target';
  $('timezone-label').textContent = d.week.timezone ? `Saved time · ${d.week.timezone}` : 'Set a time zone during goal clarification';
  const running = state.instances.filter(i => i.name !== d.name && i.timers.some(t => t.status === 'running'));
  $('other-timers').classList.toggle('hidden', !running.length);
  $('other-timers').innerHTML = running.map(i => `A timer is running in ${esc(i.name)}.<button data-workspace="${esc(i.name)}">Open workspace</button>`).join(' ');
  renderTasks(); renderChart(); renderFocus(); renderNext();
  const recommendation = d.workload?.recommendation;
  $('workload-panel').innerHTML = `<span class="eyebrow">REQUIRED TIME & AVAILABLE TIME</span>${recommendation ? `<h3>${hours(recommendation.weekly_hours_min)} - ${hours(recommendation.weekly_hours_max)} / week estimated</h3><p class="small muted">${esc(recommendation.feasibility.replaceAll('_',' '))}. ${d.objective.weekly_hours != null ? `${hours(d.objective.weekly_hours)} / week agreed.` : 'A weekly commitment has not been agreed.'} Estimates depend on the scoped work and deadline.</p>` : '<h3>Give your schedule a foundation.</h3><p class="small muted">Your tutor will estimate the time your goals require, then compare it with your availability. A recommendation will appear here after workload analysis.</p>'}`;
}
function renderTasks() {
  const d = state.data; if (!d) return;
  const planned = new Set((d.plan?.items || []).map(item => item.goal_id));
  const query = $('search').value.trim().toLowerCase(), status = $('status-filter').value;
  const signature = JSON.stringify([d.name, d.goals, d.plan, state.scope, query, status]);
  if (signature === state.taskSignature) return;
  state.taskSignature = signature;
  const goals = d.goals.filter(g => (state.scope === 'all' || planned.has(g.id)) && (!status || g.status === status) && `${g.title} ${g.notes} ${g.id}`.toLowerCase().includes(query));
  $('task-count').textContent = goals.length;
  for (const scope of ['week','all']) {$('scope-'+scope).classList.toggle('active', scope === state.scope); $('scope-'+scope).setAttribute('aria-pressed', scope === state.scope);}
  if (!goals.length) {
    let title = 'No matching outcomes', text = 'Try another search or status filter.';
    if (!d.goals.length) {title = 'Start with a clear destination'; text = 'Clarify your goal with your tutor, agree on success criteria, and build your outcome tree. Your tasks will appear here.';}
    else if (state.scope === 'week' && !d.plan) {title = 'Your week is still open'; text = 'Agree on a weekly plan with your tutor. You can already explore the full outcome tree.';}
    $('tasks').innerHTML = `<div class="empty-state"><span class="empty-icon" aria-hidden="true">↗</span><h3>${title}</h3><p>${text}</p>${d.goals.length && state.scope === 'week' ? '<button class="secondary" id="show-all">View all outcomes</button>' : ''}</div>`;
    return;
  }
  $('tasks').innerHTML = goals.map(g => {
    const parent = d.goals.find(p => p.id === g.parent_id);
    return `<div class="task-row"><button class="task-main" data-task="${esc(g.id)}"><span class="task-icon ${esc(g.status)}" aria-hidden="true">${g.status === 'completed' ? '✓' : isLeaf(g) ? '○' : '▦'}</span><span class="task-copy"><strong>${esc(g.title || g.id)}</strong><span class="task-meta"><span class="status-badge ${esc(g.status)}">${esc(g.status)}</span><span>${esc(parent?.title || (isLeaf(g) ? estimate(g) : 'Outcome group'))}</span></span></span></button>${isLeaf(g) && !['completed','dropped'].includes(g.status) ? `<button class="task-focus" data-focus="${esc(g.id)}" aria-label="Focus on ${esc(g.title)}">Focus ↗</button>` : ''}</div>`;
  }).join('');
}
function renderChart() {
  const d = state.data;
  if (!d.pace) {$('week-chart').innerHTML = '<p class="small muted">Choose your time zone to see daily totals.</p>'; $('pace-note').textContent = ''; return;}
  const actual = d.pace.daily_logged_hours, planned = d.pace.daily_planned_hours;
  const max = Math.max(.25,...Object.values(actual),...Object.values(planned));
  $('week-chart').innerHTML = Object.keys(actual).map(day => `<div class="chart-day ${day === d.week.today ? 'today' : ''}" aria-label="${esc(day)}: ${hours(actual[day])} logged, ${planned[day] == null ? 'no target' : hours(planned[day])+' planned'}"><div class="chart-value">${hours(actual[day])}${planned[day] != null ? ' / '+hours(planned[day]) : ''}</div><div class="bars"><div class="bar actual" data-height="${actual[day]/max*100}"></div><div class="bar planned" data-height="${(planned[day] || 0)/max*100}"></div></div><div class="chart-label">${dateLabel(day,{weekday:'short'})}</div></div>`).join('');
  document.querySelectorAll('[data-height]').forEach(bar => bar.style.height = bar.dataset.height+'%');
  const ratio = d.pace.past_day_adherence_ratio;
  $('pace-note').textContent = ratio == null ? (Object.keys(planned).length ? 'Your daily targets are set. Adherence will appear after the first planned day ends.' : 'Daily targets will appear when you agree on a plan. Live timer intervals are not included yet.') : `${Math.round(ratio*100)}% of planned time logged across completed days. Today is excluded from this comparison.`;
}
function primaryTimer() {return state.data?.timers.find(t => t.status === 'running') || state.data?.timers[0];}
function renderFocus() {
  const d = state.data, timer = primaryTimer();
  const signature = JSON.stringify([d.name,d.goals,d.sessions]);
  if (signature !== state.goalSignature) {
    const selected = $('focus-goal').value;
    $('focus-goal').innerHTML = '<option value="">General study</option>'+d.goals.filter(g => isLeaf(g) && !['completed','dropped'].includes(g.status)).map(g => `<option value="${esc(g.id)}">${esc(g.title || g.id)}</option>`).join('');
    if ([...$('focus-goal').options].some(o => o.value === selected)) $('focus-goal').value = selected;
    updateSessions(); state.goalSignature = signature;
  }
  const timerSignature = JSON.stringify(d.timers.map(t => [t.id,t.version,t.owner]));
  if (timerSignature !== state.timerSignature) {
    state.timerSignature = timerSignature;
    $('focus-form').classList.toggle('hidden', Boolean(timer));
    $('timer-actions').classList.toggle('hidden', !timer);
    $('timer-state').textContent = timer ? timer.status : 'Ready';
    $('timer-state').className = 'status-badge '+(timer?.status || '');
    $('timer-activity').textContent = timer?.activity || "Choose what you'll work on.";
    $('timer-owner').textContent = timer ? `Started by ${timer.owner}. ${timer.session_id ? 'Linked to a learning session.' : 'Time tracking only.'}` : '';
    $('timer-actions').innerHTML = timer ? `<button class="primary" data-timer="${esc(timer.id)}" data-action="${timer.status === 'running' ? 'pause' : 'resume'}">${timer.status === 'running' ? 'Pause' : 'Resume'}</button><button class="secondary" data-timer="${esc(timer.id)}" data-action="stop">Stop & save</button>` : '';
    $('paused-timers').innerHTML = d.timers.filter(t => t.id !== timer?.id).map(t => `<div class="paused-item"><p>${esc(t.activity)} <span class="status-badge">Paused</span></p><button class="secondary" data-timer="${esc(t.id)}" data-action="resume" ${d.timers.some(x => x.status === 'running') ? 'disabled' : ''}>Resume</button><button class="secondary" data-timer="${esc(t.id)}" data-action="stop">Stop & save</button></div>`).join('');
  }
  tick();
}
function updateSessions() {
  const chosen = $('focus-session').value, goal = $('focus-goal').value;
  const sessions = state.data.sessions.filter(s => !goal || s.goal_ids.includes(goal));
  $('focus-session').innerHTML = '<option value="">Track time only</option>'+sessions.map(s => `<option value="${esc(s.id)}">${esc(s.week_id)} - ${esc(s.id)}</option>`).join('');
  if (sessions.some(s => s.id === chosen)) $('focus-session').value = chosen;
  $('session-label').classList.toggle('hidden', !sessions.length);
}
function tick() {
  const timer = primaryTimer();
  $('timer-display').textContent = timer ? clock(timer.saved_seconds + timer.uncommitted_seconds + (timer.status === 'running' ? (Date.now()-state.receivedAt)/1000 : 0)) : '00:00:00';
}
function renderNext() {
  const d = state.data;
  if (d.foundation.status !== 'confirmed') {
    $('next-title').textContent = 'Clarify your learning goal';
    $('next-description').textContent = 'Ask your tutor to use exy-clarify-goal in this workspace. Work through your goal, starting point, deadline, and realistic time commitment.';
  } else if (!d.plan) {
    $('next-title').textContent = 'Shape the coming week';
    $('next-description').textContent = 'Ask your tutor to turn your confirmed foundation and diagnostic evidence into a weekly plan.';
  } else {
    $('next-title').textContent = 'Choose one meaningful task';
    $('next-description').textContent = 'Open an outcome, review its criteria, and start a focus timer when you begin. Save learning evidence with your tutor.';
  }
}
function showTask(id) {
  const d = state.data, goal = d.goals.find(g => g.id === id); if (!goal) return;
  const item = d.plan?.items.find(i => i.goal_id === id);
  const dependencies = goal.depends_on.map(i => d.goals.find(g => g.id === i));
  $('task-detail').innerHTML = `<h2 class="detail-title">${esc(goal.title || goal.id)}</h2><span class="status-badge ${esc(goal.status)}">${esc(goal.status)}</span><div class="detail-section"><h3>Effort</h3><p>${esc(estimate(goal))} · ${hours(d.goal_hours[id] || 0)} logged across all time</p></div><div class="detail-section"><h3>Completion criteria</h3>${goal.criteria.length ? '<ul>'+goal.criteria.map(c => `<li>${esc(c.description)}<br><span class="muted">Verify: ${esc(c.verification)}</span></li>`).join('')+'</ul>' : '<p class="muted">Criteria have not been defined yet.</p>'}</div>${item ? `<div class="detail-section"><h3>This week's activities</h3><p>${esc(item.expected_result)}</p><ul>${item.activities.map(a => `<li>${esc(a)}</li>`).join('')}</ul><p class="muted">Permitted assistance: ${esc(item.assistance_policy || 'Not specified')}</p></div>` : ''}${dependencies.length ? `<div class="detail-section"><h3>Prerequisites</h3><ul>${dependencies.map(g => `<li>${esc(g?.title || 'Unknown outcome')} (${esc(g?.status)})</li>`).join('')}</ul></div>` : ''}${goal.notes ? `<div class="detail-section"><h3>Notes</h3><p>${esc(goal.notes)}</p></div>` : ''}<p class="small muted">Completion is recorded through assessment evidence with your tutor.</p>${isLeaf(goal) && !['completed','dropped'].includes(goal.status) ? `<button class="primary wide" data-focus="${esc(id)}">Focus on this outcome</button>` : ''}`;
  $('task-dialog').showModal();
}
function focusGoal(id) {
  if (primaryTimer()) {notice('Pause or stop the current timer before choosing a different outcome.'); $('task-dialog').close(); return;}
  $('focus-goal').value = id; updateSessions();
  const goal = state.data.goals.find(g => g.id === id);
  $('focus-activity').value = goal?.title || '';
  $('task-dialog').close(); $('focus-activity').focus();
  $('focus-form').scrollIntoView({block:'center',behavior:'smooth'});
}
async function timerAction(action, timerId) {
  if (state.busy || !state.data) return;
  const timer = state.data.timers.find(t => t.id === timerId);
  let body = {instance:state.selected,request_id:crypto.randomUUID(),action};
  if (timer) {
    if (timer.owner !== 'dashboard' && !confirm(`This timer was started by ${timer.owner}. Take control for this action?`)) return;
    const long = timer.status === 'running' && timer.uncommitted_seconds+(Date.now()-state.receivedAt)/1000 > 14400 && ['pause','stop'].includes(action);
    if (long && !confirm('This interval exceeds four hours. Confirm that the full interval was study time. Cancel to correct it with your tutor.')) return;
    Object.assign(body,{timer_id:timer.id,expected_version:timer.version,actor:timer.owner,handoff:timer.owner !== 'dashboard',confirm_long:long});
  } else Object.assign(body,{actor:'dashboard',goal_id:$('focus-goal').value || null,session_id:$('focus-session').value || null,activity:$('focus-activity').value.trim()});
  if (state.pending) {
    if (!confirm('The previous request has no confirmed response. Retry that exact request first?')) return;
    body = state.pending;
  }
  state.busy = true; state.pending = body; notice('');
  document.querySelectorAll('#focus-form button,#timer-actions button,#paused-timers button').forEach(b => b.disabled = true);
  try {
    await api('/api/timer',body); state.pending = null;
    if (action === 'stop') notice('Focus time saved. Your tutor can use it in the next pace review.');
  } catch(error) {
    if (error.confirmedFailure) state.pending = null;
    notice(error.message + (error.confirmedFailure ? '. The current timer state has been refreshed.' : '. Retry to resend the same request safely.'));
  } finally {
    state.busy = false; state.timerSignature = '';
    $('start-focus').disabled = false; await refresh();
  }
}
function showSettings() {
  const item = state.instances.find(i => i.name === state.selected); if (!item) return;
  $('settings-name').textContent = item.name; $('settings-path').textContent = item.path; $('settings-error').textContent = '';
  $('settings-dialog').showModal();
}
function openConnect() {$('connect-error').textContent = ''; $('connect-dialog').showModal();}
document.addEventListener('click', event => {
  const button = event.target.closest('button'); if (!button || button.disabled) return;
  if (button.dataset.workspace) selectWorkspace(button.dataset.workspace);
  if (button.dataset.close) $(button.dataset.close).close();
  if (button.dataset.task) showTask(button.dataset.task);
  if (button.dataset.focus) focusGoal(button.dataset.focus);
  if (button.dataset.action) timerAction(button.dataset.action,button.dataset.timer);
  if (button.id === 'show-all') {state.scope = 'all'; renderTasks();}
});
$('connect-open').onclick = openConnect; $('welcome-connect').onclick = openConnect;
$('workspace-settings').onclick = showSettings; $('error-settings').onclick = showSettings;
$('refresh').onclick = async () => {notice(''); await refresh();};
$('scope-week').onclick = () => {state.scope = 'week'; renderTasks();};
$('scope-all').onclick = () => {state.scope = 'all'; renderTasks();};
$('search').oninput = renderTasks; $('status-filter').onchange = renderTasks;
$('focus-goal').onchange = updateSessions;
$('focus-form').onsubmit = event => {event.preventDefault(); timerAction('start');};
$('connect-form').onsubmit = async event => {
  event.preventDefault(); const button = event.submitter; button.disabled = true;
  try {const result = await api('/api/connect',{name:$('connect-name').value.trim(),workspace:$('connect-path').value.trim()}); $('connect-dialog').close(); state.selected = result.name; state.goalSignature = ''; state.timerSignature = ''; notice(''); await refresh(); await selectWorkspace(result.name);}
  catch(error) {$('connect-error').textContent = error.message;}
  finally {button.disabled = false;}
};
$('disconnect').onclick = async () => {
  const item = state.instances.find(i => i.name === state.selected); if (!item) return;
  if (!confirm(`Disconnect ${item.name} from the dashboard and agents? Its learning files will be kept.`)) return;
  $('disconnect').disabled = true;
  try {await api('/api/disconnect',{name:item.name,expected_path:item.path}); $('settings-dialog').close(); notice(''); await refresh();}
  catch(error) {$('settings-error').textContent = error.message;}
  finally {$('disconnect').disabled = false;}
};
setInterval(tick,1000);
setInterval(() => {if (!document.hidden && !document.querySelector('dialog[open]')) refresh();},5000);
document.addEventListener('visibilitychange', () => {if (!document.hidden) refresh();});
refresh();
