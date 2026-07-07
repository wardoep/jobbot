/* Company / source picture resolver, shared by every page.
   For each <img class="mg-logo" data-company="Name" data-domain="host">:
     1. resolve the company name -> its website domain (Clearbit autocomplete),
     2. try favicons in order [company domain, data-domain (the job's source
        website)] via Google's favicon service, showing the first real one.
   A colored initial tile sits underneath (.mg-ava), so there is ALWAYS a
   picture: real logo > source-site icon > the letter tile.
   NOTE: never lazy-load these imgs — display:none + loading="lazy" never
   fires onload. Company->domain results cache in localStorage. */
(function () {
  var cache;
  try { cache = JSON.parse(localStorage.getItem('jbLogoDomains') || '{}'); } catch (e) { cache = {}; }
  var save = function () { try { localStorage.setItem('jbLogoDomains', JSON.stringify(cache)); } catch (e) {} };

  function favicon(domain) {
    return 'https://www.google.com/s2/favicons?domain=' + encodeURIComponent(domain) + '&sz=128';
  }

  // Try each domain's favicon in order; show the first that loads as a real
  // icon (Google serves a tiny generic globe for unknown domains -> skip it).
  function tryDomains(img, domains) {
    domains = domains.filter(Boolean);
    var i = 0;
    function attempt() {
      if (i >= domains.length) return;  // nothing resolved -> letter tile shows
      var d = domains[i++];
      img.onload = function () {
        if (img.naturalWidth >= 24) img.classList.add('on'); else attempt();
      };
      img.onerror = attempt;
      img.src = favicon(d);
    }
    attempt();
  }

  function plausible(name, hit) {
    var w = name.toLowerCase().split(/[\s,]+/)[0];
    return hit && hit.domain && w.length >= 3 && hit.name.toLowerCase().indexOf(w) === 0;
  }

  var byCompany = {};
  var noCompany = [];
  document.querySelectorAll('img.mg-logo').forEach(function (img) {
    var name = (img.dataset.company || '').trim();
    if (name) (byCompany[name] = byCompany[name] || []).push(img);
    else noCompany.push(img);
  });

  // Imgs with no company name: straight to the source-site favicon.
  noCompany.forEach(function (img) { tryDomains(img, [img.dataset.domain]); });

  Object.keys(byCompany).forEach(function (name) {
    var imgs = byCompany[name];
    var run = function (companyDomain) {
      imgs.forEach(function (img) { tryDomains(img, [companyDomain, img.dataset.domain]); });
    };
    var key = name.toLowerCase();
    if (key in cache) { run(cache[key]); return; }
    fetch('https://autocomplete.clearbit.com/v1/companies/suggest?query=' + encodeURIComponent(name))
      .then(function (r) { return r.json(); })
      .then(function (list) {
        var hit = Array.isArray(list) ? list[0] : null;
        cache[key] = plausible(name, hit) ? hit.domain : '';
        save();
        run(cache[key]);
      })
      .catch(function () { run(''); });  // Clearbit down -> still try source favicon
  });
})();
