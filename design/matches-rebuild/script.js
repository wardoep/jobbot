/* ============================================================
   JobBot — Matches tab (standalone rebuild)
   Vanilla-JS port of the mockup's state logic (JobBot.html).
   Same seed data, ranking rules, timings and copy as the original.
   ============================================================ */
(function () {
  'use strict';

  // ---------- Seed data (verbatim from the mockup) ----------
  var JOBS = [
    { id: 'j1', grad: 'linear-gradient(135deg,#1e3a8a,#2563eb)', title: 'Senior Software Engineer', company: 'Stripe', domain: 'stripe.com', mode: 'Remote', loc: 'New York, NY', isNew: true, score: 87, skills: ['Python', 'FastAPI', 'Distributed systems'] },
    { id: 'j2', grad: 'linear-gradient(135deg,#0f766e,#14b8a6)', title: 'Backend Developer (Python)', company: 'Airbnb', domain: 'airbnb.com', mode: 'On-site', loc: 'Boston, MA', isNew: true, score: 81, skills: ['Python', 'PostgreSQL', 'REST APIs'] },
    { id: 'j3', grad: 'linear-gradient(135deg,#7c3aed,#a855f7)', title: 'Platform Engineer', company: 'Notion', domain: 'notion.so', mode: 'On-site', loc: 'Hartford, CT', isNew: true, score: 73, skills: ['Kubernetes', 'CI/CD', 'Go'] },
    { id: 'j4', grad: 'linear-gradient(135deg,#b45309,#f59e0b)', title: 'Staff Engineer', company: 'Figma', domain: 'figma.com', mode: 'Remote', loc: 'San Francisco, CA', isNew: false, score: 79, skills: ['System design', 'Python', 'Mentoring'] },
    { id: 'j5', grad: 'linear-gradient(135deg,#be123c,#fb7185)', title: 'Senior Backend Engineer', company: 'Datadog', domain: 'datadoghq.com', mode: 'Remote', loc: 'Austin, TX', isNew: false, score: 84, skills: ['Python', 'FastAPI', 'AWS'] },
    { id: 'j6', grad: 'linear-gradient(135deg,#1e40af,#3b82f6)', title: 'API Engineer', company: 'Plaid', domain: 'plaid.com', mode: 'Hybrid', loc: 'Chicago, IL', isNew: true, score: 76, skills: ['Java', 'Kafka', 'Microservices'] }
  ];
  var SALARY = { j1: '$160–200k', j2: '$130–160k', j3: '$110–140k', j4: '$190–240k', j5: '$150–185k', j6: '$140–175k' };
  var STAGES = ['Applied', 'Screening', 'Interview', 'Offer', 'Rejected'];
  var STAGE_COLOR = { Applied: '#2563eb', Screening: '#7c3aed', Interview: '#b45309', Offer: '#15803d', Rejected: '#94a3b8' };
  var REMINDERS = {
    Applied: { text: 'Follow up in 3 days', cls: 'blue' },
    Screening: { text: 'Recruiter call — prep notes', cls: 'blue' },
    Interview: { text: 'Send a thank-you note', cls: 'orange' },
    Offer: { text: 'Review & negotiate your offer', cls: 'green' },
    Rejected: { text: 'Closed — archived', cls: 'gray' }
  };
  var SCAN_SOURCES = [
    { name: 'adzuna', found: 18 }, { name: 'remotive', found: 9 }, { name: 'ctstatejobs', found: 6 },
    { name: 'greenhouse', found: 11 }, { name: 'lever', found: 4 }, { name: 'workday', found: 7 }
  ];
  // Dark-theme logo-fallback tints (light theme uses each company's gradient)
  var LOGO_TINTS = ['#38BDF8', '#ED93B1', '#5DCAA5', '#EF9F27', '#AFA9EC'];

  // ---------- State (mockup defaults) ----------
  var state = {
    tab: 'foryou',
    starred: { j1: true },
    applied: { j6: true },
    refused: [],
    stages: { j6: 'Interview' },
    pipeFilter: 'All',
    resumes: 2,          // mockup starts with two uploaded resumes
    scanning: false,
    scanStage: 0,
    dragHome: false,
    profile: { name: 'Jordan Lee', email: 'you@example.com' }
  };
  var scanInterval = null, scanTimeout = null, flashTimeout = null;
  var lastRiseTab = null; // the entrance animation only plays when the tab actually changes

  // ---------- Helpers ----------
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function fitOf(score) {
    if (score >= 85) return { label: 'Excellent fit', green: true };
    if (score >= 78) return { label: 'Strong fit', green: true };
    return { label: 'Good fit', green: false };
  }
  function jobById(id) { for (var i = 0; i < JOBS.length; i++) if (JOBS[i].id === id) return JOBS[i]; return null; }
  function tintFor(job) { return LOGO_TINTS[Math.max(0, JOBS.indexOf(job)) % LOGO_TINTS.length]; }
  // Queue ranking: favorited first, then applied, then by fit score.
  function priorityOf(j) {
    var p = j.score;
    if (state.applied[j.id]) p += 1000;
    if (state.starred[j.id]) p += 2000;
    return p;
  }
  function rankedJobs() {
    return JOBS.filter(function (j) { return state.refused.indexOf(j.id) < 0; })
      .slice().sort(function (a, b) { return priorityOf(b) - priorityOf(a); });
  }
  function appliedAll() {
    return JOBS.filter(function (j) { return state.applied[j.id]; }).map(function (j) {
      return { job: j, stage: state.stages[j.id] || 'Applied' };
    });
  }
  function appliedFiltered() {
    var all = appliedAll();
    if (state.pipeFilter === 'All') return all;
    return all.filter(function (a) { return a.stage === state.pipeFilter; });
  }
  function savedJobs() {
    return JOBS.filter(function (j) { return state.starred[j.id]; })
      .slice().sort(function (a, b) { return b.score - a.score; });
  }
  function refusedJobs() {
    return state.refused.slice(0, 10).map(jobById).filter(Boolean);
  }

  function showFlash(type, msg) {
    var el = document.getElementById('flash');
    el.className = 'flash ' + type;
    el.textContent = msg;
    el.hidden = false;
    clearTimeout(flashTimeout);
    flashTimeout = setTimeout(function () { el.hidden = true; }, 3600);
  }

  // ---------- Shared row pieces ----------
  function logoHtml(job, featured) {
    // <img> from Clearbit (external, as in the original); gradient/tint mark shown if it fails to load.
    return '<img class="logo-img" src="https://logo.clearbit.com/' + esc(job.domain) + '" alt="' + esc(job.company) + ' logo">' +
      '<div class="logo-mark' + (featured ? ' featured-mark' : '') + '" style="--mark-grad:' + job.grad + ';--mark-tint:' + tintFor(job) + '"><div class="notch"></div></div>';
  }
  function fitPillHtml(job) {
    var fit = fitOf(job.score);
    return '<span class="fit-pill ' + (fit.green ? 'green' : 'blue') + '">' + fit.label + '</span>';
  }
  function starBtnHtml(job, glow) {
    // Only the For-You queue stars glow on hover in the original; Saved-tab stars don't.
    var on = !!state.starred[job.id];
    return '<button class="star-btn' + (on ? ' on' : '') + (glow ? ' glow' : '') + '" data-action="star" data-id="' + job.id + '" aria-label="Save job">' + (on ? '★' : '☆') + '</button>';
  }

  // ---------- For You tab ----------
  function renderForYou() {
    if (state.resumes === 0) return renderUpload();
    if (state.scanning) return renderScan();

    var ranked = rankedJobs();
    if (!ranked.length) {
      return '<div class="empty-card"><div class="glyph">🗂️</div><div class="empty-title">Queue is empty</div>' +
        '<p>You dismissed every match. Restore jobs from the Refused tab to bring them back.</p></div>';
    }
    var featured = ranked[0];
    var fStar = !!state.starred[featured.id];
    var html =
      '<div class="list-eyebrow sg">Today&#39;s top pick</div>' +
      '<div class="featured jhover" data-action="open" data-id="' + featured.id + '">' +
        '<div class="featured-ring"></div>' +
        '<div class="featured-row">' +
          '<div class="featured-tile">' + logoHtml(featured, true) + '</div>' +
          '<div class="featured-main">' +
            '<div class="featured-title sg">' + esc(featured.title) + '</div>' +
            '<div class="featured-sub">' + esc(featured.company) + ' · ' + esc(featured.mode) + ' · ' + esc(featured.loc) +
              ' · <span class="salary-hi">' + esc(SALARY[featured.id]) + '</span></div>' +
          '</div>' +
          '<button class="featured-star' + (fStar ? ' on' : '') + '" data-action="star" data-id="' + featured.id + '" aria-label="Save job">' + (fStar ? '★' : '☆') + '</button>' +
          '<button class="featured-x" data-action="dismiss" data-id="' + featured.id + '" title="Not interested — remove from queue">×</button>' +
        '</div>' +
        '<div class="featured-why">Strongest match this week — your ' + esc(featured.skills[0]) + ', ' + esc(featured.skills[1]) + ' and ' + esc(featured.skills[2]) + ' experience line up with the core requirements.</div>' +
        '<div class="featured-actions">' +
          '<button class="btn-light sg" data-action="open" data-id="' + featured.id + '">✨ Tailor &amp; apply</button>' +
          '<button class="btn-ghost sg" data-action="star" data-id="' + featured.id + '">' + (fStar ? '★ Saved' : '★ Save') + '</button>' +
        '</div>' +
      '</div>';

    var queue = ranked.slice(1);
    html += '<div class="list-eyebrow queue sg">Next in your queue · ' + queue.length + '</div>';
    queue.forEach(function (job, i) {
      html +=
        '<div class="job-row jhover" data-action="open" data-id="' + job.id + '">' +
          '<div class="rank">' + pad(i + 2) + '</div>' +
          '<div class="logo-tile">' + logoHtml(job) + '</div>' +
          '<div class="job-main">' +
            '<div class="job-title-row">' +
              (job.isNew ? '<span class="badge-new">New</span>' : '') +
              '<span class="job-title sg">' + esc(job.title) + '</span>' +
            '</div>' +
            '<div class="company-line">' + esc(job.company) + ' · ' + esc(job.mode) + ' · ' + esc(job.loc) + '</div>' +
          '</div>' +
          '<span class="salary">' + esc(SALARY[job.id]) + '</span>' +
          (state.applied[job.id] ? '<span class="badge-applied">✓ Applied</span>' : '') +
          fitPillHtml(job) +
          starBtnHtml(job, true) +
          '<button class="dismiss-btn" data-action="dismiss" data-id="' + job.id + '" title="Not interested — remove from queue">×</button>' +
        '</div>';
    });
    return '<div class="rise">' + html + '</div>';
  }

  function renderUpload() {
    return '<div class="rise"><div class="upload-card">' +
      '<div class="bot-mark"><div class="bot-eyes"><span></span><span></span></div><div class="bot-smile"></div></div>' +
      '<div class="bot-bubble">' +
        '<div class="bub-title">Hi ' + esc(state.profile.name.split(' ')[0]) + ', I&#39;m JobBot 👋</div>' +
        '<p>Drop your resume and I&#39;ll start hunting for roles that actually fit — then tell you why each one made the cut.</p>' +
      '</div>' +
      '<label class="upload-zone' + (state.dragHome ? ' drag' : '') + '" id="upload-zone">' +
        '<input type="file" accept=".pdf,.docx" id="resume-file">' +
        '<div class="zone-title">⬆ Drag &amp; drop your resume</div>' +
        '<div class="zone-sub">or <b>browse files</b> · PDF or DOCX</div>' +
      '</label>' +
    '</div></div>';
  }

  function renderScan() {
    var total = SCAN_SOURCES.length;
    var stage = state.scanStage;
    var found = 0;
    SCAN_SOURCES.forEach(function (s, i) { if (i < stage) found += s.found; });
    var width = Math.min(100, Math.round((stage / total) * 100));
    var rows = '';
    SCAN_SOURCES.forEach(function (s, i) {
      if (i > stage || i >= total) return;
      var done = i < stage;
      rows += '<div class="scan-row">' +
        (done ? '<span class="scan-done-icon">✓</span>' : '<span class="scan-row-spinner"></span>') +
        '<span class="scan-name">' + esc(s.name) + '</span>' +
        (done ? '<span class="scan-found">' + s.found + ' found</span>' : '<span class="scan-wait">scanning…</span>') +
      '</div>';
    });
    return '<div class="scan-card">' +
      '<div class="scan-head"><div class="scan-spinner"></div><h1 class="sg">Scanning ' + total + ' sources…</h1></div>' +
      '<p class="scan-sub">Checking jobs posted in the last 24 hours — ' + found + ' postings found so far.</p>' +
      '<div class="scan-track"><div class="scan-bar" style="width:' + width + '%"></div></div>' +
      '<div class="scan-rows">' + rows + '</div>' +
    '</div>';
  }

  // ---------- Saved tab ----------
  function renderSaved() {
    var saved = savedJobs();
    if (!saved.length) {
      return '<div class="rise"><div class="empty-card"><div class="glyph star">☆</div>' +
        '<div class="empty-title">No saved jobs yet</div>' +
        '<p>Tap the star on any match to save it here for tailoring later.</p></div></div>';
    }
    var html = '';
    saved.forEach(function (job) {
      html +=
        '<div class="job-row jhover" data-action="open" data-id="' + job.id + '">' +
          '<div class="logo-tile">' + logoHtml(job) + '</div>' +
          '<div class="job-main">' +
            '<div class="job-title sg">' + esc(job.title) + '</div>' +
            '<div class="company-line">' + esc(job.company) + ' · ' + esc(job.mode) + ' · ' + esc(job.loc) + '</div>' +
          '</div>' +
          '<span class="salary">' + esc(SALARY[job.id]) + '</span>' +
          fitPillHtml(job) +
          starBtnHtml(job) +
        '</div>';
    });
    return '<div class="rise">' + html + '</div>';
  }

  // ---------- Applied tab ----------
  function renderApplied() {
    var all = appliedAll();
    var html = '';
    if (all.length) {
      var counts = { All: all.length };
      STAGES.forEach(function (s) { counts[s] = 0; });
      all.forEach(function (a) { counts[a.stage] = (counts[a.stage] || 0) + 1; });
      html += '<div class="pipe-chips">';
      ['All'].concat(STAGES).forEach(function (s) {
        html += '<div class="pipe-chip' + (state.pipeFilter === s ? ' active' : '') + '" data-action="pipe" data-stage="' + s + '">' +
          s + '<span class="cnt">' + counts[s] + '</span></div>';
      });
      html += '</div>';
    }
    var list = appliedFiltered();
    if (!list.length) {
      html += '<div class="empty-card"><div class="glyph">📮</div>' +
        '<div class="empty-title">Nothing here yet</div>' +
        '<p>Open a match, tailor it, and mark it applied to track it through your pipeline.</p></div>';
      return '<div class="rise">' + html + '</div>';
    }
    list.forEach(function (a) {
      var job = a.job, stg = a.stage, rem = REMINDERS[stg] || REMINDERS.Applied;
      var opts = '';
      STAGES.forEach(function (o) {
        opts += '<option value="' + o + '"' + (o === stg ? ' selected' : '') + '>' + o + '</option>';
      });
      html +=
        '<div class="applied-card">' +
          '<div class="applied-top jhover" data-action="open" data-id="' + job.id + '">' +
            '<div class="logo-tile">' + logoHtml(job) + '</div>' +
            '<div class="job-main">' +
              '<div class="job-title sg">' + esc(job.title) + '</div>' +
              '<div class="company-line">' + esc(job.company) + ' · ' + esc(job.loc) + '</div>' +
            '</div>' +
            '<span class="applied-meta">Applied 2 days ago</span>' +
          '</div>' +
          '<div class="applied-foot">' +
            '<div class="stage-wrap">' +
              '<span class="stage-dot" style="background:' + (STAGE_COLOR[stg] || '#2563eb') + '"></span>' +
              '<select class="stage-select" data-action="stage" data-id="' + job.id + '">' + opts + '</select>' +
            '</div>' +
            '<span class="reminder ' + rem.cls + '">⏰ ' + rem.text + '</span>' +
            '<div class="foot-spacer"></div>' +
            (stg === 'Offer' ? '<span class="offer-link" data-action="open" data-id="' + job.id + '">💰 Offer insights →</span>' : '') +
          '</div>' +
        '</div>';
    });
    return '<div class="rise">' + html + '</div>';
  }

  // ---------- Refused tab ----------
  function renderRefused() {
    var refused = refusedJobs();
    if (!refused.length) {
      return '<div class="rise"><div class="empty-card"><div class="glyph">🗂️</div>' +
        '<div class="empty-title">No refused jobs</div>' +
        '<p>Jobs you dismiss with × land here, so you can undo it if you change your mind.</p></div></div>';
    }
    var html = '<div class="refused-hint">The last 10 jobs you removed. Restore any to send it back to your queue.</div>';
    refused.forEach(function (job) {
      html +=
        '<div class="job-row jhover refused" data-action="open" data-id="' + job.id + '">' +
          '<div class="logo-tile">' + logoHtml(job) + '</div>' +
          '<div class="job-main">' +
            '<div class="job-title sg">' + esc(job.title) + '</div>' +
            '<div class="company-line">' + esc(job.company) + ' · ' + esc(job.mode) + ' · ' + esc(job.loc) + '</div>' +
          '</div>' +
          '<span class="salary">' + esc(SALARY[job.id]) + '</span>' +
          '<button class="btn-restore" data-action="restore" data-id="' + job.id + '">↩ Restore</button>' +
        '</div>';
    });
    return '<div class="rise">' + html + '</div>';
  }

  // ---------- Render ----------
  // Patch the mounted scan card instead of rebuilding it, so the progress bar's
  // width transition actually animates and existing rows don't replay their
  // entrance animations (the original runtime diffs the DOM in place).
  function updateScan(panel) {
    var total = SCAN_SOURCES.length, stage = state.scanStage, found = 0;
    SCAN_SOURCES.forEach(function (s, i) { if (i < stage) found += s.found; });
    panel.querySelector('.scan-bar').style.width = Math.min(100, Math.round((stage / total) * 100)) + '%';
    panel.querySelector('.scan-sub').textContent = 'Checking jobs posted in the last 24 hours — ' + found + ' postings found so far.';
    var rowsEl = panel.querySelector('.scan-rows');
    SCAN_SOURCES.forEach(function (s, i) {
      if (i > stage || i >= total) return;
      var done = i < stage;
      var inner = (done ? '<span class="scan-done-icon">✓</span>' : '<span class="scan-row-spinner"></span>') +
        '<span class="scan-name">' + esc(s.name) + '</span>' +
        (done ? '<span class="scan-found">' + s.found + ' found</span>' : '<span class="scan-wait">scanning…</span>');
      var row = rowsEl.children[i];
      if (!row) {                       // new row mounts → its jbrise plays once
        row = document.createElement('div');
        row.className = 'scan-row';
        row.innerHTML = inner;
        rowsEl.appendChild(row);
      } else if (done && row.querySelector('.scan-row-spinner')) {
        row.innerHTML = inner;          // row persists; the ✓ icon mounts → jbpop plays once
      }
    });
  }

  function render() {
    // Tab bar: active state + counts (Applied count reflects the pipeline filter, as in the original)
    var tabs = document.querySelectorAll('#tabs .tab');
    for (var i = 0; i < tabs.length; i++) {
      tabs[i].classList.toggle('active', tabs[i].getAttribute('data-tab') === state.tab);
    }
    document.getElementById('count-saved').textContent = savedJobs().length;
    document.getElementById('count-applied').textContent = appliedFiltered().length;
    document.getElementById('count-refused').textContent = refusedJobs().length;

    // Time-of-day greeting — recomputed every render like the original, so it
    // rolls over correctly at noon and 6pm.
    var first = state.profile.name.split(' ')[0];
    var h = new Date().getHours();
    var part = h < 12 ? 'Morning' : h < 18 ? 'Afternoon' : 'Evening';
    document.getElementById('greeting').textContent = part + ', ' + first + ' 👋';

    var panel = document.getElementById('panel');
    if (state.tab === 'foryou' && state.scanning && panel.querySelector('.scan-card')) {
      updateScan(panel);
      return;
    }
    panel.innerHTML =
      state.tab === 'saved' ? renderSaved() :
      state.tab === 'applied' ? renderApplied() :
      state.tab === 'refused' ? renderRefused() :
      renderForYou();
    // In the original, the jbrise wrapper persists across in-tab updates —
    // replay the entrance only when the tab itself changed.
    if (state.tab === lastRiseTab) {
      var riser = panel.querySelector('.rise');
      if (riser) riser.classList.remove('rise');
    }
    lastRiseTab = state.tab;
  }

  // ---------- Actions ----------
  function setTab(tab) { state.tab = tab; render(); }
  function toggleStar(id) {
    if (state.starred[id]) delete state.starred[id]; else state.starred[id] = true;
    render();
  }
  function dismissJob(id) {
    state.refused = [id].concat(state.refused.filter(function (x) { return x !== id; }));
    render();
    showFlash('info', 'Removed from your queue.');
  }
  function restoreJob(id) {
    state.refused = state.refused.filter(function (x) { return x !== id; });
    render();
    showFlash('success', 'Restored to your queue.');
  }
  function setStage(id, stage) {
    state.stages[id] = stage;
    render();
  }
  function refresh() {
    if (state.scanning) return;
    var total = SCAN_SOURCES.length;
    state.scanning = true;
    state.scanStage = 0;
    render();
    clearInterval(scanInterval);
    scanInterval = setInterval(function () {
      if (state.scanStage >= total) { clearInterval(scanInterval); return; }
      state.scanStage += 1;
      render();
    }, 540);
    clearTimeout(scanTimeout);
    scanTimeout = setTimeout(function () {
      clearInterval(scanInterval);
      state.scanning = false;
      render();
      showFlash('success', '✓ Scan complete — 6 new matches found.');
    }, total * 540 + 900);
  }
  function addResume(file) {
    var name = file && file.name ? file.name : 'Resume.pdf';
    state.resumes += 1;
    state.dragHome = false;
    render();
    showFlash('success', '✓ ' + name + ' uploaded — skills added to your preferences.');
  }
  // Job detail, Home, Resumes, Preferences and Options screens are outside
  // the Matches-only scope of this rebuild.
  function openJob() { showFlash('info', 'Job detail opens here in the full app — outside this Matches-only rebuild.'); }
  function navOther(dest) { showFlash('info', dest + ' isn’t included — this rebuild covers the Matches tab only.'); }

  // ---------- Events (delegated so re-renders keep working) ----------
  // closest() resolves to the innermost [data-action], so a click on a
  // star/dismiss/restore button never also triggers its parent row's "open".
  document.addEventListener('click', function (e) {
    var el = e.target.closest('[data-action]');
    if (!el) return;
    var action = el.getAttribute('data-action');
    var id = el.getAttribute('data-id');
    switch (action) {
      case 'tab': setTab(el.getAttribute('data-tab')); break;
      case 'refresh': refresh(); break;
      case 'star': toggleStar(id); break;
      case 'dismiss': dismissJob(id); break;
      case 'restore': restoreJob(id); break;
      case 'pipe': state.pipeFilter = el.getAttribute('data-stage'); render(); break;
      case 'open': openJob(id); break;
      case 'nav-other': navOther(el.getAttribute('data-dest')); break;
    }
  });

  document.addEventListener('change', function (e) {
    var el = e.target.closest('[data-action="stage"]');
    if (el) setStage(el.getAttribute('data-id'), el.value);
    var file = e.target.closest('#resume-file');
    if (file && file.files && file.files[0]) addResume(file.files[0]);
  });

  // Company logos load from logo.clearbit.com; on failure show the fallback mark.
  document.addEventListener('error', function (e) {
    var img = e.target;
    if (img && img.classList && img.classList.contains('logo-img')) {
      img.style.display = 'none';
      if (img.nextElementSibling) img.nextElementSibling.style.display = 'grid';
    }
  }, true);

  // Drag & drop for the first-run upload zone (only present when no resumes exist)
  document.addEventListener('dragover', function (e) {
    var zone = e.target.closest && e.target.closest('#upload-zone');
    if (!zone) return;
    e.preventDefault();
    if (!state.dragHome) { state.dragHome = true; zone.classList.add('drag'); }
  });
  document.addEventListener('dragleave', function (e) {
    var zone = e.target.closest && e.target.closest('#upload-zone');
    if (!zone) return;
    e.preventDefault();
    state.dragHome = false;
    zone.classList.remove('drag');
  });
  document.addEventListener('drop', function (e) {
    var zone = e.target.closest && e.target.closest('#upload-zone');
    if (!zone) return;
    e.preventDefault();
    addResume(e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]);
  });

  // ---------- Init ----------
  function init() {
    var first = state.profile.name.split(' ')[0];
    document.getElementById('user-name').textContent = first;
    document.getElementById('user-email').textContent = state.profile.email;
    document.getElementById('avatar').textContent = (first[0] || 'Y').toUpperCase();

    // Deep-link convenience (not in the original): #saved / #applied / #refused / #scan / #firstrun
    var hash = (location.hash || '').replace('#', '');
    if (hash === 'saved' || hash === 'applied' || hash === 'refused') state.tab = hash;
    if (hash === 'firstrun') state.resumes = 0;
    render();
    if (hash === 'scan') refresh();
  }
  init();
})();
