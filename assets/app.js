const state = { papers: [], activeDomain: 'all', query: '', sort: 'signal', shown: 10 };
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

function formatDate(dateStr, style='short') {
  if (!dateStr) return 'Date unavailable';
  const date = new Date(`${dateStr}T12:00:00`);
  return new Intl.DateTimeFormat('en-US', style === 'long'
    ? { month:'long', day:'numeric', year:'numeric' }
    : { month:'short', day:'numeric', year:'numeric' }).format(date);
}
function escapeHTML(value='') {
  return value.replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
}
function badge(label, css='') { return `<span class="badge ${css}">${escapeHTML(label)}</span>`; }

function renderBriefing(briefing) {
  $('#briefing-date').textContent = formatDate(briefing.date, 'long');
  $('#briefing-title').textContent = briefing.title || 'The latest signal';
  $('#briefing-summary').classList.remove('loading-card');
  $('#briefing-summary').textContent = briefing.overview || 'No daily overview was generated.';
  const grid = $('#briefing-grid');
  grid.innerHTML = '';
  (briefing.items || []).slice(0,3).forEach(item => {
    const card = document.createElement('article');
    card.className = 'brief-card';
    card.innerHTML = `
      <span class="brief-domain">${escapeHTML(item.domain_label || item.domain || 'Research')}</span>
      <h3>${escapeHTML(item.title || '')}</h3>
      <p>${escapeHTML(item.why_it_matters || item.summary || '')}</p>
      <a href="${item.url}" target="_blank" rel="noopener noreferrer">Read original ↗</a>`;
    grid.appendChild(card);
  });
}

function filteredPapers() {
  let papers = state.papers.filter(p => {
    const domainOK = state.activeDomain === 'all' || (p.domains || []).includes(state.activeDomain);
    const haystack = [p.title, p.summary, p.authors?.join(' '), p.source, p.keywords?.join(' ')].join(' ').toLowerCase();
    return domainOK && haystack.includes(state.query.toLowerCase());
  });
  papers.sort((a,b) => {
    if (state.sort === 'newest') return (b.publication_date || '').localeCompare(a.publication_date || '');
    if (state.sort === 'citations') return (b.cited_by_count || 0) - (a.cited_by_count || 0);
    return (b.signal_score || 0) - (a.signal_score || 0) || (b.publication_date || '').localeCompare(a.publication_date || '');
  });
  return papers;
}

function renderPapers() {
  const grid = $('#research-grid');
  const papers = filteredPapers();
  grid.innerHTML = '';
  papers.slice(0,state.shown).forEach(p => {
    const node = $('#paper-template').content.cloneNode(true);
    const card = node.querySelector('.paper-card');
    const badges = card.querySelector('.badges');
    (p.domains || []).forEach(d => badges.insertAdjacentHTML('beforeend', badge(d.replace('-', ' '), d)));
    badges.insertAdjacentHTML('beforeend', badge(p.evidence_label || p.work_type || 'publication'));
    if (p.open_access) badges.insertAdjacentHTML('beforeend', badge('open access'));
    card.querySelector('.signal-score').textContent = `${Math.round(p.signal_score || 0)} signal`;
    card.querySelector('.paper-title').textContent = p.title || 'Untitled publication';
    card.querySelector('.paper-authors').textContent = (p.authors || []).slice(0,5).join(', ') + ((p.authors || []).length > 5 ? ' et al.' : '');
    card.querySelector('.paper-summary').textContent = p.summary || 'No abstract was available from the source index.';
    card.querySelector('.paper-meta').innerHTML = [
      formatDate(p.publication_date),
      `${p.cited_by_count || 0} citations`,
      p.source_provider || 'source index'
    ].map(escapeHTML).map(x => `<span>${x}</span>`).join('');
    card.querySelector('.paper-source').textContent = p.source || 'Unknown venue';
    const link = card.querySelector('.paper-link');
    link.href = p.url || '#';
    grid.appendChild(node);
  });
  if (!papers.length) grid.innerHTML = '<div class="empty-state">No publications match this filter.</div>';
  $('#load-more').hidden = papers.length <= state.shown;
}

function updateCounts() {
  const counts = { all: state.papers.length, consciousness:0, quantum:0, neuroscience:0, 'cross-domain':0 };
  state.papers.forEach(p => (p.domains || []).forEach(d => { if (d in counts) counts[d]++; }));
  Object.entries(counts).forEach(([key,value]) => { const el = $(`#count-${key}`); if(el) el.textContent = value; });
}

async function boot() {
  try {
    const [feedRes, briefingRes] = await Promise.all([
      fetch('data/feed.json', { cache:'no-store' }),
      fetch('data/briefing.json', { cache:'no-store' })
    ]);
    if (!feedRes.ok || !briefingRes.ok) throw new Error('Data files unavailable');
    const feed = await feedRes.json();
    const briefing = await briefingRes.json();
    state.papers = feed.items || [];
    $('#last-updated').textContent = `Updated ${formatDate(feed.updated_at?.slice(0,10), 'long')}`;
    $('#paper-count').textContent = `${state.papers.length} records`;
    renderBriefing(briefing);
    updateCounts();
    renderPapers();
  } catch (err) {
    $('#last-updated').textContent = 'Update pending';
    $('#briefing-summary').textContent = 'The data update has not run yet. Trigger the GitHub Action once after deployment.';
    $('#research-grid').innerHTML = '<div class="empty-state">Research data will appear after the first automated update.</div>';
    $('#load-more').hidden = true;
    console.error(err);
  }
}

$$('.domain-tab').forEach(tab => tab.addEventListener('click', () => {
  $$('.domain-tab').forEach(t => t.classList.remove('active'));
  tab.classList.add('active');
  state.activeDomain = tab.dataset.domain;
  state.shown = 10;
  renderPapers();
}));
$('#search-input').addEventListener('input', e => { state.query = e.target.value.trim(); state.shown=10; renderPapers(); });
$('#sort-select').addEventListener('change', e => { state.sort = e.target.value; renderPapers(); });
$('#load-more').addEventListener('click', () => { state.shown += 10; renderPapers(); });
boot();
