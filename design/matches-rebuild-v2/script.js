/* ==================================================================
   JobBot — "Matches" tab (dark theme, v2)
   Working port of the static segment in matches-page-segment.zip.
   Every row is rendered from the jobs list below, exactly as the
   original's comment instructs ("loop over your matches and fill in:
   --p, the score number, title, company line, salary, the New pill,
   the Applied chip, and the star state").
   ================================================================== */
(function () {
  'use strict';

  // ---------- Data (from the original segment) ----------
  var JOBS = [
    { id: 'j1', title: 'Senior Software Engineer', company: 'Stripe', mode: 'Remote', loc: 'New York, NY', domain: 'stripe.com', score: 87, salary: '$160–200k', isNew: true,
      why: 'Strongest match this week — your Python, FastAPI and distributed-systems experience line up with the core requirements.' },
    { id: 'j2', title: 'Backend Developer (Python)', company: 'Airbnb', mode: 'On-site', loc: 'Boston, MA', domain: 'airbnb.com', score: 81, salary: '$130–160k', isNew: true },
    { id: 'j3', title: 'Platform Engineer', company: 'Notion', mode: 'On-site', loc: 'Hartford, CT', domain: 'notion.so', score: 73, salary: '$110–140k', isNew: true },
    { id: 'j4', title: 'Staff Engineer', company: 'Figma', mode: 'Remote', loc: 'San Francisco, CA', domain: 'figma.com', score: 79, salary: '$190–240k', isNew: false },
    { id: 'j5', title: 'Senior Backend Engineer', company: 'Datadog', mode: 'Remote', loc: 'Austin, TX', domain: 'datadoghq.com', score: 84, salary: '$150–185k', isNew: false },
    { id: 'j6', title: 'API Engineer', company: 'Plaid', mode: 'Hybrid', loc: 'Chicago, IL', domain: 'plaid.com', score: 76, salary: '$140–175k', isNew: true }
  ];

  // Initial state mirrors the original snapshot: Stripe saved (hero star on),
  // Plaid applied (✓ chip), nothing refused — hence "Saved · 1 / Applied · 1 / Refused · 0".
  var state = {
    tab: 'foryou',
    starred: { j1: true },
    applied: { j6: true },
    refused: []
  };

  // ---------- Helpers ----------
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function jobById(id) { for (var i = 0; i < JOBS.length; i++) if (JOBS[i].id === id) return JOBS[i]; return null; }
  // Queue order in the original snapshot: applied row first, then by score —
  // i.e. saved/applied outrank plain score.
  function priorityOf(j) {
    var p = j.score;
    if (state.applied[j.id]) p += 1000;
    if (state.starred[j.id]) p += 2000;
    return p;
  }
  function ranked() {
    return JOBS.filter(function (j) { return state.refused.indexOf(j.id) < 0; })
      .slice().sort(function (a, b) { return priorityOf(b) - priorityOf(a); });
  }
  function savedJobs() {
    return JOBS.filter(function (j) { return state.starred[j.id]; })
      .slice().sort(function (a, b) { return b.score - a.score; });
  }
  function appliedJobs() { return JOBS.filter(function (j) { return state.applied[j.id]; }); }
  function refusedJobs() { return state.refused.map(jobById).filter(Boolean); }

  // ---------- Row template (the original <article class="match">) ----------
  function matchRow(job, opts) {
    opts = opts || {};
    var on = !!state.starred[job.id];
    return '<article class="match' + (opts.refused ? ' refused' : '') + '" data-id="' + job.id + '">' +
      '<div class="ring" style="--p:' + job.score + '"><span>' + job.score + '</span></div>' +
      '<div class="logo"><img src="https://logo.clearbit.com/' + esc(job.domain) + '" alt=""></div>' +
      '<div class="body">' +
        '<div class="title">' + (job.isNew && !opts.refused ? '<span class="pill-new">New</span> ' : '') + esc(job.title) + '</div>' +
        '<div class="company">' + esc(job.company) + ' · ' + esc(job.mode) + ' · ' + esc(job.loc) + '</div>' +
      '</div>' +
      '<span class="salary">' + esc(job.salary) + '</span>' +
      (state.applied[job.id] && !opts.refused ? '<span class="applied-chip">✓ Applied</span>' : '') +
      (opts.refused
        ? '<button class="restore" data-action="restore" data-id="' + job.id + '">↩ Restore</button>'
        : '<button class="star' + (on ? ' on' : '') + '" data-action="star" data-id="' + job.id + '" aria-label="Save job">' + (on ? '★' : '☆') + '</button>' +
          '<button class="dismiss" data-action="dismiss" data-id="' + job.id + '" title="Not interested">×</button>') +
    '</article>';
  }

  // ---------- Panels ----------
  function renderForYou() {
    var list = ranked();
    if (!list.length) {
      return '<div class="empty"><div class="glyph">🗂️</div><div class="t">Queue is empty</div>' +
        '<p>You removed every match — restore them from the Refused tab.</p></div>';
    }
    var top = list[0];
    var on = !!state.starred[top.id];
    var html =
      '<div class="section-label">Today’s top pick</div>' +
      '<div class="hero" data-id="' + top.id + '">' +
        '<div class="halo"></div>' +
        '<div class="row">' +
          '<div class="ring lg" style="--p:' + top.score + '"><span>' + top.score + '<small>match</small></span></div>' +
          '<div style="flex:1;min-width:0">' +
            '<div class="title">' + esc(top.title) + '</div>' +
            '<div class="sub">' + esc(top.company) + ' · ' + esc(top.mode) + ' · ' + esc(top.loc) + ' · <b>' + esc(top.salary) + '</b></div>' +
          '</div>' +
          '<div class="logo-tile"><img src="https://logo.clearbit.com/' + esc(top.domain) + '" alt=""></div>' +
          '<button class="star-lg' + (on ? ' on' : '') + '" data-action="star" data-id="' + top.id + '" title="' + (on ? 'Saved' : 'Save') + '">' + (on ? '★' : '☆') + '</button>' +
          '<button class="close" data-action="dismiss" data-id="' + top.id + '" title="Not interested — remove from queue">×</button>' +
        '</div>' +
        '<div class="why">' + esc(top.why || ('Strong match — ' + top.company + ' is hiring for skills on your resume.')) + '</div>' +
        '<div class="cta">' +
          '<button class="primary">✨ Tailor &amp; apply</button>' +
          '<button class="ghost" data-action="star" data-id="' + top.id + '">' + (on ? '★ Saved' : '★ Save') + '</button>' +
        '</div>' +
      '</div>' +
      '<div class="section-label">Next in your queue · ' + (list.length - 1) + '</div>';
    list.slice(1).forEach(function (job) { html += matchRow(job); });
    return html;
  }

  function renderSaved() {
    var saved = savedJobs();
    if (!saved.length) {
      return '<div class="empty"><div class="glyph star">☆</div><div class="t">No saved jobs yet</div>' +
        '<p>Tap the star on any match to save it here.</p></div>';
    }
    return saved.map(function (j) { return matchRow(j); }).join('');
  }

  function renderApplied() {
    var applied = appliedJobs();
    if (!applied.length) {
      return '<div class="empty"><div class="glyph">📮</div><div class="t">Nothing here yet</div>' +
        '<p>Jobs you mark as applied show up here.</p></div>';
    }
    return applied.map(function (j) { return matchRow(j); }).join('');
  }

  function renderRefused() {
    var refused = refusedJobs();
    if (!refused.length) {
      return '<div class="empty"><div class="glyph">🗂️</div><div class="t">No refused jobs</div>' +
        '<p>Jobs you dismiss with × land here, so you can undo it.</p></div>';
    }
    return '<div class="hint">Jobs you removed. Restore any to send it back to your queue.</div>' +
      refused.map(function (j) { return matchRow(j, { refused: true }); }).join('');
  }

  // ---------- Render ----------
  function render() {
    var links = document.querySelectorAll('#tabs a');
    for (var i = 0; i < links.length; i++) {
      links[i].classList.toggle('on', links[i].getAttribute('data-tab') === state.tab);
    }
    document.querySelector('[data-count="saved"]').textContent = savedJobs().length;
    document.querySelector('[data-count="applied"]').textContent = appliedJobs().length;
    document.querySelector('[data-count="refused"]').textContent = refusedJobs().length;

    document.getElementById('panel').innerHTML =
      state.tab === 'saved' ? renderSaved() :
      state.tab === 'applied' ? renderApplied() :
      state.tab === 'refused' ? renderRefused() :
      renderForYou();
  }

  // ---------- Events ----------
  document.getElementById('tabs').addEventListener('click', function (e) {
    var a = e.target.closest('a[data-tab]');
    if (!a) return;
    e.preventDefault();
    state.tab = a.getAttribute('data-tab');
    render();
  });

  document.getElementById('panel').addEventListener('click', function (e) {
    var el = e.target.closest('[data-action]');
    if (!el) return;
    var id = el.getAttribute('data-id');
    var action = el.getAttribute('data-action');
    if (action === 'star') {
      if (state.starred[id]) delete state.starred[id]; else state.starred[id] = true;
      render();
    } else if (action === 'dismiss') {
      state.refused = [id].concat(state.refused.filter(function (x) { return x !== id; }));
      render();
    } else if (action === 'restore') {
      state.refused = state.refused.filter(function (x) { return x !== id; });
      render();
    }
  });

  // The source defines no refresh behavior — give the button a brief
  // pressed state so it feels alive without inventing new UI.
  document.getElementById('refresh').addEventListener('click', function () {
    var b = this;
    if (b.disabled) return;
    var label = b.textContent;
    b.disabled = true;
    b.textContent = '↻ Refreshing…';
    setTimeout(function () { b.disabled = false; b.textContent = label; }, 900);
  });

  // Keep the nav links inert (they're href="#" placeholders in the source too)
  document.querySelector('nav.links').addEventListener('click', function (e) {
    if (e.target.closest('a')) e.preventDefault();
  });

  // Company logos come from logo.clearbit.com; the source has no fallback, so a
  // failed load shows a broken-image icon. Hide it and let the tile stand alone.
  document.addEventListener('error', function (e) {
    var img = e.target;
    if (img && img.tagName === 'IMG' && img.closest('.logo, .logo-tile')) img.style.display = 'none';
  }, true);

  // Time-of-day greeting (the app computes this; the static file froze "Morning")
  var h = new Date().getHours();
  document.getElementById('greeting').textContent =
    (h < 12 ? 'Morning' : h < 18 ? 'Afternoon' : 'Evening') + ', Jordan 👋';

  render();
})();
