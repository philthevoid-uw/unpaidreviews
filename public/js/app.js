/* Search, category filter and sorting for pages that list reviews.
   The review cards are already in the HTML, so this works without any data loading. */
(function () {
  var grid = document.getElementById('grid');
  if (!grid) return;
  var cards = Array.prototype.slice.call(grid.querySelectorAll('.card'));
  var chips = document.querySelectorAll('[data-cat]');
  var q = document.getElementById('q');
  var sort = document.getElementById('sort');
  var empty = document.getElementById('empty');
  var count = document.getElementById('count');
  var cat = 'all';

  try {
    var params = new URLSearchParams(window.location.search);
    if (q && params.get('q')) q.value = params.get('q');
    if (params.get('cat')) cat = params.get('cat');
  } catch (e) { /* older browsers: ignore */ }

  function apply() {
    var term = q ? q.value.trim().toLowerCase() : '';
    var shown = cards.filter(function (c) {
      var ok = (cat === 'all' || c.dataset.category === cat) &&
               (!term || c.dataset.text.indexOf(term) !== -1);
      c.hidden = !ok;
      return ok;
    });
    var by = sort ? sort.value : 'new';
    shown.sort(function (a, b) {
      if (by === 'high') return b.dataset.score - a.dataset.score;
      if (by === 'low') return a.dataset.score - b.dataset.score;
      return b.dataset.date.localeCompare(a.dataset.date);
    });
    shown.forEach(function (c) { grid.appendChild(c); });
    if (empty) empty.hidden = shown.length > 0;
    if (count) count.textContent = shown.length + (shown.length === 1 ? ' review' : ' reviews');
    chips.forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.cat === cat ? 'true' : 'false'); });
  }

  chips.forEach(function (b) {
    b.addEventListener('click', function () { cat = b.dataset.cat; apply(); });
  });
  if (q) q.addEventListener('input', apply);
  if (sort) sort.addEventListener('change', apply);
  apply();
})();
