/* ARISE owner console — control-plane spec §10.
 *
 * Vanilla JS, hash router, no build step. The admin token lives in the
 * `token` variable below and nowhere else (spec §4.2): never Web Storage
 * or a cookie. Every request goes to window.location.origin.
 * All interaction is delegated on [data-action] (no inline handlers, which
 * the page CSP would block anyway).
 */
(function () {
  'use strict';

  var API = window.location.origin;
  var LOCAL = /^(localhost|127\.0\.0\.1)$/.test(location.hostname);
  var token = null;        // the 15-minute admin token — JS memory only
  var session = null;      // { userId, email, expiresAt, issuedAt }
  var pendingReason = '';  // a drawer's reason, preserved across a 401 → login
  var drawer = null;       // open drawer state (see openDrawer)
  var renderSeq = 0;       // ignore late responses after navigation or logout
  var countdownTimer = null;
  var searchTimer = null;
  var state = { detail: null, products: null };  // what the open drawers read

  var LIMIT_KEYS = [
    { key: 'scans.free_monthly', field: 'free_monthly', label: 'FREE MONTHLY SCANS', unit: '' },
    { key: 'scans.daily_limit', field: 'daily_limit', label: 'DAILY SCAN CAP', unit: '' },
    { key: 'scans.cooldown_seconds', field: 'cooldown_seconds', label: 'SCAN COOLDOWN', unit: 's' }
  ];
  var ENTITLEMENT_KEYS = ['scans.unlimited'].concat(LIMIT_KEYS.map(function (k) { return k.key; }));
  var AUDIT_ACTIONS = [
    'session.create', 'admin.bootstrap', 'credits.adjust', 'entitlement.grant', 'entitlement.revoke',
    'campaign.import', 'user.soft_delete', 'user.restore', 'user.purge', 'product.upsert',
    'maintenance.family_backfill', 'maintenance.purge_sweep', 'maintenance.seed_achievements'
  ];
  var DESTRUCTIVE_ACTIONS = ['entitlement.revoke', 'user.soft_delete', 'user.restore', 'user.purge', 'maintenance.purge_sweep'];
  var LIST_KEYS = ['q', 'deleted', 'unlimited', 'active_days', 'sort', 'order', 'offset'];
  var AUDIT_KEYS = ['target_type', 'target_id', 'actor_user_id', 'action', 'offset'];
  var TEMPLATES = ['owner_hybrid'];
  var CREDITS_STEP_UP = 50;
  var PAGE = 50;

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  var content = $('#content');
  var drawerEl = $('#drawer');
  var scrimEl = $('#scrim');

  // ── formatting ─────────────────────────────────────────────────────────

  var ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  function esc(v) {
    if (v === null || v === undefined) return '';
    return String(v).replace(/[&<>"']/g, function (c) { return ESC[c]; });
  }
  function shortId(id) {
    if (!id) return '—';
    id = String(id);
    return id.length > 12 ? id.slice(0, 4) + '…' + id.slice(-4) : id;
  }
  function parseDate(v) {
    if (!v) return null;
    if (v instanceof Date) return v;
    var s = String(v);
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return new Date(s + 'T00:00:00');
    if (/T/.test(s) && !/(Z|[+-]\d{2}:?\d{2})$/.test(s)) s += 'Z';
    var d = new Date(s);
    return isNaN(d.getTime()) ? null : d;
  }
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function fmtDate(v) {
    var d = parseDate(v);
    return d ? d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) : '—';
  }
  function fmtDT(v) {
    var d = parseDate(v);
    return d ? MONTHS[d.getMonth()] + ' ' + d.getDate() + ' · ' + pad(d.getHours()) + ':' + pad(d.getMinutes()) : '—';
  }
  function todayISO() { return fmtDate(new Date()); }
  function daysSince(v) { return Math.floor((Date.now() - parseDate(v)) / 86400000); }
  function ago(v) {
    var d = parseDate(v);
    if (!d) return '—';
    var s = (Date.now() - d.getTime()) / 1000;
    if (s < 60) return 'just now';
    if (s < 3600) return Math.floor(s / 60) + 'm ago';
    if (s < 86400) return Math.floor(s / 3600) + 'h ago';
    if (s < 86400 * 60) return Math.floor(s / 86400) + 'd ago';
    return MONTHS[d.getMonth()] + ' ' + d.getDate() + (d.getFullYear() !== new Date().getFullYear() ? ' ' + d.getFullYear() : '');
  }
  function num(n) { return n === null || n === undefined ? '—' : Number(n).toLocaleString(); }
  function plural(n, noun, pluralForm) { return n + ' ' + (n === 1 ? noun : (pluralForm || noun + 's')); }
  // ISO week label matching the server's "YYYY-Www" buckets (which are sparse: only weeks with rows)
  function isoWeek(d) {
    var t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
    var day = t.getUTCDay() || 7;
    t.setUTCDate(t.getUTCDate() + 4 - day);
    var week = Math.ceil(((t - Date.UTC(t.getUTCFullYear(), 0, 1)) / 86400000 + 1) / 7);
    return t.getUTCFullYear() + '-W' + pad(week);
  }
  function recentWeeks(n) {
    var out = [];
    for (var i = 0; i < n; i++) { var d = new Date(); d.setDate(d.getDate() - 7 * i); out.push(isoWeek(d)); }
    return out;
  }
  function sumWeeks(rows, field, n) {
    var labels = recentWeeks(n);
    return (rows || []).reduce(function (a, w) { return labels.indexOf(w.week) >= 0 ? a + (w[field] || 0) : a; }, 0);
  }
  function sign(n) { return (n > 0 ? '+' : '') + n; }
  function rankLetter(rank) {
    var c = rank ? String(rank).trim().charAt(0).toUpperCase() : '';
    return /[EDCBAS]/.test(c) ? c : '?';
  }
  function uuid() {
    if (crypto.randomUUID) return crypto.randomUUID();
    var b = new Uint8Array(16); crypto.getRandomValues(b);
    b[6] = (b[6] & 0x0f) | 0x40; b[8] = (b[8] & 0x3f) | 0x80;
    var h = Array.prototype.map.call(b, function (x) { return ('0' + x.toString(16)).slice(-2); }).join('');
    return h.slice(0, 8) + '-' + h.slice(8, 12) + '-' + h.slice(12, 16) + '-' + h.slice(16, 20) + '-' + h.slice(20);
  }
  function isPhone() { return window.matchMedia('(max-width: 767px)').matches; }
  function isObj(v) { return v !== null && typeof v === 'object' && !Array.isArray(v); }
  function deepEq(a, b) { return JSON.stringify(a) === JSON.stringify(b); }
  function hunterHref(id) { return '#/hunters/' + encodeURIComponent(id); }
  function auditHref(params) { return '#/audit' + qs(params); }
  function userPath(id, tail) { return '/admin/users/' + encodeURIComponent(id) + (tail || ''); }
  function qs(params) {
    var p = new URLSearchParams();
    Object.keys(params || {}).forEach(function (k) {
      if (params[k] !== undefined && params[k] !== null && params[k] !== '') p.set(k, params[k]);
    });
    var s = p.toString();
    return s ? '?' + s : '';
  }
  function pick(params, keys) {
    var q = {};
    keys.forEach(function (k) { var v = params.get(k); if (v) q[k] = v; });
    return q;
  }
  // Run `fn` over `items` one at a time (a failed step stops the chain; each
  // destructive POST re-verifies the password, so parallel would multiply strikes).
  function sequential(items, fn) {
    return items.reduce(function (chain, item) {
      return chain.then(function (acc) { return fn(item).then(function (r) { acc.push(r); return acc; }); });
    }, Promise.resolve([]));
  }

  // ── html fragments ─────────────────────────────────────────────────────

  function chip(text, cls) { return '<span class="chip ' + (cls || 'dim') + '">' + esc(text) + '</span>'; }
  function kv(k, v, cls) {
    return '<div class="kv"><span class="k">' + esc(k) + '</span><span class="v ' + (cls || '') + '">' + v + '</span></div>';
  }
  function sl(title, extra, cls) {
    return '<div class="sl ' + (cls || '') + '">[ ' + esc(title) + ' ]' + (extra ? '<span class="sp"></span>' + extra : '') + '</div>';
  }
  function ro(text) { return '<span class="ro">' + esc(text || 'read-only') + '</span>'; }
  function muted(text) { return '<span class="muted">' + esc(text) + '</span>'; }
  function empty(msg, card) { var e = '<div class="empty">' + msg + '</div>'; return card ? '<div class="card">' + e + '</div>' : e; }
  function opt(value, current, label) {
    return '<option value="' + esc(value) + '"' + (current === value ? ' selected' : '') + '>' + esc(label || value || '—') + '</option>';
  }
  function pageHeader(title, meta, right) {
    return '<div class="ph"><h2>' + esc(title) + '</h2>' + (meta ? '<span class="cnt">' + meta + '</span>' : '') + '<span class="sp"></span>' + (right || '') + '</div>';
  }
  function backHeader(right) { return '<div class="ph"><a class="back" href="#/hunters">‹ HUNTERS</a><span class="sp"></span>' + (right || '') + '</div>'; }
  function table(cls, ths, rows) {
    return '<div class="tblwrap' + (cls && cls.indexOf('dk') >= 0 ? ' dk' : '') + '"><table class="tbl ' + (cls || '').replace('dk', '') + '"><thead><tr>' + ths + '</tr></thead><tbody>' + rows + '</tbody></table></div>';
  }
  function sysline(title, msg, cls, actions) {
    return '<div class="sysline ' + (cls || '') + '"><div class="t">' + esc(title) + '</div><div class="m">' + msg + '</div>' +
      (actions ? '<div class="acts">' + actions + '</div>' : '') + '</div>';
  }
  function errorBlock(err, retry) {
    var title = err && err.status ? 'HTTP ' + err.status : 'SYSTEM ERROR';
    return sysline(title, esc(err && err.message ? err.message : String(err)), 'err',
      retry ? '<button type="button" class="btn sm ghost" data-action="retry">RETRY</button>' : '');
  }
  function skelRows(n) {
    var out = '';
    for (var i = 0; i < n; i++) out += '<div class="kv"><span class="skel w40"></span><span class="skel w40"></span></div>';
    return '<div class="skel-rows">' + out + '</div>';
  }
  function skelTable(cols, rows) {
    var head = '', body = '';
    for (var c = 0; c < cols; c++) head += '<th><span class="skel w60"></span></th>';
    for (var r = 0; r < rows; r++) {
      body += '<tr class="skel">';
      for (var k = 0; k < cols; k++) body += '<td><span class="skel ' + (k % 3 === 0 ? 'w80' : 'w60') + '"></span></td>';
      body += '</tr>';
    }
    return table('', head, body);
  }
  function skelCard(title, rows) { return '<div class="card">' + sl(title) + skelRows(rows || 4) + '</div>'; }
  function diffRow(k, from, to, opts) {
    opts = opts || {};
    var same = opts.same !== undefined ? opts.same : String(from) === String(to);
    return '<div class="diff' + (same ? ' same' : '') + '"><span class="k">' + esc(k) + '</span><span class="from">' + esc(from) +
      '</span><span class="ar">→</span><span class="to' + (opts.down ? ' dn' : '') + '">' + esc(to) + '</span></div>';
  }
  function fieldRow(label, note, input, first) {
    return '<div class="flabel' + (first ? ' first' : '') + '">' + esc(label) + (note ? ' <span>' + esc(note) + '</span>' : '') + '</div>' + input;
  }
  function checkbox(field, on, label, danger) {
    return '<label class="check' + (danger ? ' danger' : '') + '"><input type="checkbox" data-field="' + field + '"' + (on ? ' checked' : '') + '> ' + esc(label) + '</label>';
  }
  function avatar(rank, extra) {
    var letter = rankLetter(rank);
    return '<div class="av ' + (extra || '') + ' r-' + letter.toLowerCase() + '">' + esc(letter) + '</div>';
  }
  function creditsChip(hasUnlimited, credits) {
    return hasUnlimited ? chip('∞ unlimited', 'gold') : chip((credits === null || credits === undefined ? 0 : num(credits)) + ' credits', 'cyan');
  }
  function actionChip(action) {
    var cls = 'cyan';
    if (DESTRUCTIVE_ACTIONS.indexOf(action) >= 0) cls = 'red';
    else if (action === 'entitlement.grant') cls = 'gold';
    else if (action === 'session.create' || action === 'admin.bootstrap') cls = 'dim';
    else if (/^maintenance\./.test(action) || action === 'product.upsert') cls = 'green';
    return chip(action, cls);
  }
  function stateChips(u) {
    var out = '';
    if (u.is_admin) out += chip('Admin', 'gold') + ' ';
    if (u.is_deleted) out += chip('Deleted' + (u.deleted_at ? ' · ' + ago(u.deleted_at) : ''), 'red');
    else out += chip('Active', 'green');
    return out;
  }
  function auditActor(a) { return esc(a.actor_user_id ? shortId(a.actor_user_id) : 'system'); }
  function auditTarget(a) {
    if (a.target_type === 'user' && a.target_id) return '<a href="' + hunterHref(a.target_id) + '">' + esc(shortId(a.target_id)) + '</a>';
    return esc(a.target_type + (a.target_id ? ' · ' + shortId(a.target_id) : ''));
  }

  // ── api ────────────────────────────────────────────────────────────────

  function ApiError(status, message) {
    this.name = 'ApiError'; this.status = status; this.message = message;
  }
  ApiError.prototype = Object.create(Error.prototype);

  function detailText(data) {
    if (!data) return 'Empty response';
    var d = isObj(data) && 'detail' in data ? data.detail : data;
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) {
      return d.map(function (e) {
        var loc = Array.isArray(e.loc) ? e.loc.filter(function (x) { return x !== 'body'; }).join('.') : '';
        return (loc ? loc + ': ' : '') + (e.msg || JSON.stringify(e));
      }).join('; ');
    }
    return JSON.stringify(d);
  }

  function api(method, path, opts) {
    opts = opts || {};
    var headers = { Accept: 'application/json' };
    if (token) headers.Authorization = 'Bearer ' + token;
    if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
    Object.keys(opts.headers || {}).forEach(function (k) { headers[k] = opts.headers[k]; });
    return fetch(API + path, {
      method: method, headers: headers, cache: 'no-store', credentials: 'omit',
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined
    }).catch(function (e) {
      throw new ApiError(0, 'Network error — ' + e.message + '. Retry keeps your form.');
    }).then(function (res) {
      return res.text().then(function (text) {
        var data = null;
        try { data = text ? JSON.parse(text) : null; } catch (_) { data = text; }
        if (res.status === 401 && !opts.noExpire) return on401(data);
        if (!res.ok) throw new ApiError(res.status, detailText(data));
        return data;
      });
    });
  }

  // A 401 is either the token dying (expired, revoked, five failed step-ups)
  // or a destructive-tier step-up refusing the re-entered password (spec §4.5).
  // One probe of /admin/me tells them apart: a live token keeps the drawer
  // open with the error above Confirm; a dead one returns to Login.
  function on401(data) {
    var probeHeaders = token ? { Authorization: 'Bearer ' + token, Accept: 'application/json' } : {};
    return fetch(API + '/admin/me', { headers: probeHeaders, cache: 'no-store', credentials: 'omit' })
      .then(function (probe) { return probe.status; }, function () { return 0; })
      .then(function (status) {
        if (status === 200) throw new ApiError(401, detailText(data) || 'Wrong password');
        expireSession('The 15-minute session ended (a call answered 401). Log in again to continue.');
        throw new ApiError(401, 'Session expired');
      });
  }

  function latestAuditId(params) {
    var q = { limit: 1 };
    Object.keys(params || {}).forEach(function (k) { q[k] = params[k]; });
    return api('GET', '/admin/audit' + qs(q)).then(function (r) {
      return r && r.items && r.items[0] ? r.items[0].id : null;
    }).catch(function () { return null; });
  }

  // ── session ────────────────────────────────────────────────────────────

  function showLogin(msg) {
    $('#app').hidden = true;
    $('#login').hidden = false;
    $('#login-msg').innerHTML = msg ? sysline('SESSION', esc(msg), 'guard') : '';
    var email = $('#login-email');
    if (session && session.email && !email.value) email.value = session.email;
    setTimeout(function () { (email.value ? $('#login-password') : email).focus(); }, 30);
  }

  function startSession(data, email) {
    token = data.admin_token;
    session = { userId: null, email: email, expiresAt: parseDate(data.expires_at), issuedAt: new Date() };
    $('#login').hidden = true;
    $('#app').hidden = false;
    $('#sess-who').textContent = email;
    $('#env-chip').textContent = LOCAL ? 'LOCAL' : 'PROD';
    $('#env-chip').className = 'chip env ' + (LOCAL ? 'dim' : 'orange');
    clearInterval(countdownTimer);
    countdownTimer = setInterval(tick, 1000);
    tick();
    api('GET', '/admin/me').then(function (me) {
      if (session) { session.userId = me.user_id; session.expiresAt = parseDate(me.token_expires_at) || session.expiresAt; }
    }).catch(function () { /* the countdown falls back to the login response */ });
    onRoute();
  }

  var sessCount = $('#sess-count');
  function tick() {
    if (!session || !session.expiresAt) { sessCount.textContent = 'SESSION --:--'; return; }
    var left = Math.max(0, Math.floor((session.expiresAt.getTime() - Date.now()) / 1000));
    sessCount.textContent = 'SESSION ' + pad(Math.floor(left / 60)) + ':' + pad(left % 60);
    sessCount.className = 'sess' + (left < 60 ? ' crit' : left < 180 ? ' low' : '');
    if (left <= 0) expireSession('The 15-minute session expired. Log in again to continue.');
  }

  function expireSession(msg) {
    if (drawer && drawer.reason) pendingReason = drawer.reason;
    token = null;
    renderSeq++;                       // any screen load still in flight is now stale
    if (session) session.expiresAt = null;
    clearInterval(countdownTimer);
    closeDrawer(true);
    showLogin(msg);
  }

  function login(form) {
    var email = form.email.value.trim();
    var password = form.password.value;
    var btn = $('#login-submit');
    btn.disabled = true;
    $('#login-msg').innerHTML = '';
    api('POST', '/admin/session', { body: { email: email, password: password }, noExpire: true })
      .then(function (data) {
        form.password.value = '';
        startSession(data, email);
      })
      .catch(function (e) {
        var msg = e.message;
        if (e.status === 401) msg = 'Wrong password or unknown account (a wrong password counts toward the 10-strike lockout).';
        else if (e.status === 403) msg = 'That account is not an admin (set ADMIN_BOOTSTRAP_EMAIL on Railway and redeploy).';
        else if (e.status === 423) msg = 'Locked for 15 minutes after too many bad passwords. Break-glass: clear admin_locked_until in the database.';
        else if (e.status === 429) msg = 'Rate limited — wait a minute before the next attempt.';
        $('#login-msg').innerHTML = sysline('ACCESS · ' + (e.status || 'NETWORK'), esc(msg), 'err');
      })
      .then(function () { btn.disabled = false; });
  }

  // ── router ─────────────────────────────────────────────────────────────

  function parseHash() {
    var raw = location.hash.replace(/^#\/?/, '');
    var parts = raw.split('?');
    var segs = parts[0].split('/').filter(Boolean).map(function (seg) { try { return decodeURIComponent(seg); } catch (_) { return seg; } });
    return { name: segs[0] || 'overview', id: segs[1] || null, params: new URLSearchParams(parts[1] || '') };
  }
  function go(path, params) { location.hash = '#/' + path + qs(params); }
  // Rewrite the Hunters query in place (sort headers, filter chips, search)
  function updateHunters(mutate) {
    var q = pick(parseHash().params, LIST_KEYS);
    delete q.offset;
    mutate(q);
    go('hunters', q);
  }

  function onRoute() {
    if (!token) { showLogin(); return; }
    var route = parseHash();
    closeDrawer(true);
    $$('[data-nav]').forEach(function (b) { b.classList.toggle('on', b.dataset.nav === route.name); });
    if (route.name === 'hunters' && route.id) return screenHunter(route.id);
    if (route.name === 'hunters') return screenHunters(route.params);
    if (route.name === 'audit') return screenAudit(route.params);
    if (route.name === 'catalog') return screenCatalog();
    if (route.name === 'settings') return screenSettings();
    return screenOverview();
  }

  // Every screen: skeleton now, render when the load lands — unless another
  // navigation (or a logout) has moved renderSeq on since.
  function loadScreen(o) {
    var seq = ++renderSeq;
    content.innerHTML = o.skeleton;
    o.load().then(function (data) {
      if (seq === renderSeq) content.innerHTML = o.render(data);
    }).catch(function (e) {
      if (seq === renderSeq) content.innerHTML = o.fallback(e);
    });
  }

  // ── overview ───────────────────────────────────────────────────────────

  function screenOverview() {
    loadScreen({
      skeleton: pageHeader('Overview', 'fleet · ' + esc(todayISO())) +
        '<div class="stats">' + [1, 2, 3, 4, 5, 6].map(function () { return '<div class="stat"><span class="skel tall w60"></span><div class="l"><span class="skel w80"></span></div></div>'; }).join('') + '</div>' +
        '<div class="grid2 top">' + skelCard('ATTENTION', 3) + skelCard('RECENT ACTIONS', 4) + '</div>',
      load: function () { return Promise.all([api('GET', '/admin/usage?weeks=12'), api('GET', '/admin/audit?limit=8')]); },
      render: function (r) { return renderOverview(r[0], r[1]); },
      fallback: function (e) { return pageHeader('Overview') + errorBlock(e, true); }
    });
  }

  function renderOverview(u, audit) {
    var users = u.users || {}, bal = u.balances || {}, ex = u.exercises || {}, integ = u.integrations || {};
    var weeks = u.sessions_by_week || [], scans = u.scans_by_week || [];
    var currentWeek = isoWeek(new Date());
    var thisWeek = weeks.filter(function (w) { return w.week === currentWeek; })[0] || { sessions: 0, active_users: 0, week: currentWeek };
    var stat = function (v, cls, l, d) {
      return '<div class="stat"><div class="v ' + cls + '">' + v + '</div><div class="l">' + esc(l) + '</div><div class="d">' + d + '</div></div>';
    };
    var html = pageHeader('Overview', 'fleet · generated ' + esc(fmtDT(u.generated_at)) + ' · ' + esc(u.weeks) + ' wk window',
      '<button type="button" class="btn sm ghost" data-action="retry">REFRESH</button>');
    html += '<div class="stats">' +
      stat(num(users.total), 'c', 'Hunters', esc(num(users.total - users.deleted)) + ' active · ' + esc(num(users.deleted)) + ' deleted · ' + esc(num(users.admins)) + ' admin') +
      stat(num(users.active_7d) + ' <small>/ ' + num(users.active_30d) + '</small>', 'g', 'Active 7d / 30d', 'by session date') +
      stat(num(thisWeek.sessions), '', 'Sessions this week', esc(thisWeek.week) + ' · ' + esc(num(thisWeek.active_users)) + ' hunters') +
      stat(num(sumWeeks(scans, 'scans', 4)), '', 'Scans · 4 wk', esc(num(sumWeeks(scans, 'screenshots', 4))) + ' screenshots') +
      stat(num(bal.unlimited_count) + ' <small>∞</small>', 'y', 'Unlimited hunters', esc(num(bal.credits_total)) + ' credits across ' + esc(num(bal.rows)) + ' balances') +
      stat(num(users.purge_eligible), users.purge_eligible > 0 ? 'r' : '', 'Purge-eligible', users.purge_eligible > 0 ? 'past the grace window' : 'nothing past grace') +
      '</div>';

    // attention list — every line deep-links (spec §10.2)
    var att = '';
    var attRow = function (a, small, actions) {
      return '<div class="att"><div class="a">' + a + (small ? '<small>' + small + '</small>' : '') + '</div><div class="acts">' + actions + '</div></div>';
    };
    att += attRow(
      users.purge_eligible > 0 ? esc(plural(users.purge_eligible, 'account')) + ' past the 30-day grace window' : 'No account is purge-eligible',
      'soft-deleted accounts are listed under the Deleted filter · the sweep runs only when PURGE_SWEEP_ENABLED',
      '<a class="btn sm ghost" href="#/hunters?deleted=true">OPEN</a><button type="button" class="btn sm dk" data-action="act" data-act="sweep">DRY-RUN SWEEP</button>'
    );
    att += attRow(
      ex.without_family > 0 ? esc(plural(ex.without_family, 'exercise')) + ' without a family' : 'Every exercise has a family',
      esc(num(ex.custom)) + ' custom of ' + esc(num(ex.total)) + ' · families drive prescriptions and gates',
      '<button type="button" class="btn sm dk" data-action="act" data-act="backfill">DRY-RUN BACKFILL</button>'
    );
    var drift = u.unlimited_flag_drift || [];
    if (drift.length) {
      drift.forEach(function (d) {
        att += attRow('Unlimited-flag drift · ' + esc(shortId(d.user_id)),
          'cached has_unlimited=' + esc(String(d.has_unlimited)) + ' but the entitlement says ' + esc(String(d.derived)) + ' · grant or revoke from the hunter to reconcile',
          '<a class="btn sm ghost" href="' + hunterHref(d.user_id) + '">OPEN</a>');
      });
    } else {
      att += attRow('No unlimited-flag drift', 'every cached has_unlimited matches its entitlement rows', '');
    }
    att += attRow('WHOOP · ' + esc(num(integ.whoop_connections)) + ' connected · ' + esc(num(integ.active_device_tokens)) + ' push devices',
      'achievement definitions can be re-seeded after a catalog change (idempotent, audited)',
      '<button type="button" class="btn sm ghost dk" data-action="act" data-act="seed">SEED ACHIEVEMENTS</button>');

    html += '<div class="grid2 top"><div class="card">' + sl('ATTENTION') + att + '</div>' +
      '<div class="card">' + sl('RECENT ACTIONS', '<a class="link" href="#/audit">VIEW AUDIT</a>') +
      (audit.items && audit.items.length ? audit.items.map(auditRow).join('') : empty('No actions yet — every mutation lands here.')) +
      '</div></div>';
    return html;
  }

  function auditRow(a) {
    var summary = auditSummary(a);
    return '<div class="arow"><div class="h">' + esc(fmtDT(a.created_at)) + ' ' + actionChip(a.action) + '<span class="sp"></span>' +
      auditActor(a) + ' → ' + auditTarget(a) + '</div>' +
      (summary ? '<div class="s">' + summary + '</div>' : '') +
      (a.reason ? '<div class="q">' + esc(a.reason) + '</div>' : '') + '</div>';
  }

  function auditSummary(a) {
    var b = isObj(a.before) ? a.before : {}, f = isObj(a.after) ? a.after : {};
    var keys = Object.keys(f).filter(function (k) { return !(k in b) || !deepEq(b[k], f[k]); });
    if (!keys.length) return '';
    return keys.slice(0, 3).map(function (k) {
      var down = f[k] === false || f[k] === null || (typeof f[k] === 'number' && typeof b[k] === 'number' && f[k] < b[k]);
      return esc(k) + ' ' + (k in b ? '<span class="from">' + esc(fmtVal(b[k])) + '</span> → ' : '') + '<span class="to' + (down ? ' dn' : '') + '">' + esc(fmtVal(f[k])) + '</span>';
    }).join(' · ') + (keys.length > 3 ? ' ' + muted('+' + (keys.length - 3)) : '');
  }
  function fmtVal(v) {
    if (v === null || v === undefined) return 'null';
    if (typeof v === 'object') return JSON.stringify(v);
    return String(v);
  }

  // ── hunters ────────────────────────────────────────────────────────────

  function screenHunters(params) {
    var q = pick(params, LIST_KEYS);
    $('#search').value = q.q || '';
    loadScreen({
      skeleton: huntersHeader(q, null) + skelTable(8, 8),
      load: function () { return api('GET', '/admin/users' + qs(Object.assign({ limit: PAGE, offset: 0, sort: 'last_active', order: 'desc' }, q))); },
      render: function (r) { return huntersHeader(q, r) + renderHunters(q, r); },
      fallback: function (e) { return huntersHeader(q, null) + errorBlock(e, true); }
    });
  }

  function huntersHeader(q, r) {
    var fch = function (label, key, value) {
      var on = key ? q[key] === value : !q.deleted && !q.unlimited && !q.active_days;
      return '<button type="button" class="fchip' + (on ? ' active' : '') + '" data-action="chip" data-key="' + esc(key || '') + '" data-value="' + esc(value || '') + '">' + esc(label) + '</button>';
    };
    return pageHeader('Hunters', (r ? esc(plural(num(r.total), 'match', 'matches')) : '…') + (q.q ? ' for “' + esc(q.q) + '”' : ''),
      '<div class="fchips">' + fch('All', null) + fch('Deleted', 'deleted', 'true') + fch('Unlimited', 'unlimited', 'true') + fch('Active 30 d', 'active_days', '30') + '</div>');
  }

  function renderHunters(q, r) {
    var sort = q.sort || 'last_active', order = q.order || 'desc';
    if (!r.items.length) {
      return empty(q.q ? 'No hunter matches “' + esc(q.q) + '” — check the Deleted filter, or search by username.' : 'No hunter matches these filters.', true);
    }
    var th = function (label, key) {
      if (!key) return '<th>' + esc(label) + '</th>';
      var on = sort === key;
      return '<th class="' + (on ? 'sorted' : '') + '"><button type="button" data-action="sort" data-sort="' + key + '">' + esc(label) + (on ? (order === 'desc' ? ' ↓' : ' ↑') : '') + '</button></th>';
    };
    var rows = r.items.map(function (u) {
      var credits = u.has_unlimited ? '<td class="y">∞</td>' : '<td class="r">' + (u.scan_credits === null ? muted('—') : esc(num(u.scan_credits))) + '</td>';
      return '<tr class="row' + (u.is_deleted ? ' deleted' : '') + '" data-action="open-hunter" data-id="' + esc(u.id) + '" tabindex="0">' +
        '<td class="m">' + esc(shortId(u.id)) + '</td><td>' + esc(u.email) + '</td><td class="un">' + esc(u.username || '—') + '</td>' +
        '<td>' + (u.rank ? esc(rankLetter(u.rank)) + ' · ' + esc(u.level) : muted('—')) + '</td>' +
        '<td>' + (u.last_workout_date ? esc(ago(u.last_workout_date)) : muted('never')) + '</td>' +
        '<td class="r">' + esc(num(u.session_count)) + '</td>' + credits +
        '<td class="m">' + esc(fmtDate(u.created_at)) + '</td><td>' + stateChips(u) + '</td></tr>';
    }).join('');
    var desktop = table('dk', th('ID') + th('Email', 'email') + th('Username') + th('Rank · Lv') + th('Last active', 'last_active') +
      th('Sessions') + th('Credits', 'credits') + th('Created', 'created') + th('State'), rows);
    var phone = '<div class="ph-only">' + r.items.map(function (u) {
      return '<button type="button" class="urow' + (u.is_deleted ? ' deleted' : '') + '" data-action="open-hunter" data-id="' + esc(u.id) + '">' + avatar(u.rank, 'sm') +
        '<div><div class="un">' + esc(u.username || shortId(u.id)) + '</div><div class="em">' + esc(u.email) + (u.level ? ' · Lv ' + esc(u.level) : '') + '</div></div>' +
        '<div class="ur"><div class="la">' + esc(u.last_workout_date ? ago(u.last_workout_date) : 'never') + '</div><div class="chips">' +
        creditsChip(u.has_unlimited, u.scan_credits) + (u.is_deleted ? chip('Deleted', 'red') : '') + '</div></div></button>';
    }).join('') + '</div>';
    return desktop + phone + pager(q, r.total);
  }

  function pager(q, total) {
    var offset = parseInt(q.offset || '0', 10) || 0;
    if (total <= PAGE && offset === 0) return '';
    var from = offset + 1, to = Math.min(offset + PAGE, total);
    return '<div class="pager"><button type="button" class="btn sm ghost" data-action="page" data-offset="' + Math.max(0, offset - PAGE) + '"' + (offset === 0 ? ' disabled' : '') + '>‹ PREV</button>' +
      '<span>' + from + '–' + to + ' of ' + esc(num(total)) + '</span>' +
      '<button type="button" class="btn sm ghost" data-action="page" data-offset="' + (offset + PAGE) + '"' + (to >= total ? ' disabled' : '') + '>NEXT ›</button></div>';
  }

  // ── hunter detail ──────────────────────────────────────────────────────

  function screenHunter(id) {
    loadScreen({
      skeleton: backHeader('<span class="cnt">' + esc(shortId(id)) + '</span>') +
        '<div class="ihead"><div class="av"></div><div class="mid"><div class="nm"><span class="skel w40 tall"></span></div><div class="sub"><span class="skel w80"></span></div></div></div>' +
        '<div class="grid2 detail"><div class="col">' + skelCard('IDENTITY', 5) + skelCard('SCANS', 4) + skelCard('ENTITLEMENTS', 3) + '</div><div class="col">' + skelCard('PROGRESS', 5) + skelCard('INTEGRATIONS', 4) + skelCard('DATA HEALTH', 3) + '</div></div>',
      load: function () { return api('GET', userPath(id)); },
      render: function (d) { state.detail = d; return renderHunter(d); },
      fallback: function (e) {
        return backHeader() + errorBlock(e.status === 404 ? new ApiError(404, 'No hunter with id ' + id + ' — purged, or a typo in the link.') : e, e.status !== 404);
      }
    });
  }

  function activeRows(d, key) {
    return (d.entitlements || []).filter(function (e) { return e.active && e.key === key; });
  }

  function renderHunter(d) {
    var u = d.user, p = d.progress || {}, b = d.balance || {}, lim = d.effective_limits || { defaults: {} }, integ = d.integrations || {}, health = d.data_health || {}, prof = d.profile || {}, c = d.campaign, pv = d.preview;
    var ents = d.entitlements || [];
    var unlimitedRows = activeRows(d, 'scans.unlimited');
    var overrides = LIMIT_KEYS.map(function (k) { return { def: k, row: activeRows(d, k.key)[0] || null }; });
    var hasOverride = overrides.some(function (o) { return o.row; });
    var lastActive = p.last_workout_date || null;

    var chips = stateChips(u) + ' ' + (p.rank ? chip(rankLetter(p.rank) + '-rank · Lv ' + p.level, 'cyan') : '') + ' ' +
      creditsChip(b.has_unlimited, b.exists ? b.scan_credits : 0) + ' ' +
      (integ.whoop && integ.whoop.connected ? chip('WHOOP', 'orange') : '') + ' ' + (hasOverride ? chip('Override', 'gold') : '');

    var html = backHeader('<span class="cnt">' + esc(u.id) + '</span>');
    html += '<div class="ihead">' + avatar(p.rank) + '<div class="mid"><div class="nm">' + esc(u.username || u.email) + '</div>' +
      '<div class="sub">' + esc(u.email) + ' · created ' + esc(fmtDate(u.created_at)) + (u.is_deleted ? ' · deleted ' + esc(fmtDT(u.deleted_at)) : '') + '</div></div><div class="chips">' + chips + '</div></div>';

    // ── left column
    var identity = '<div class="card c-identity">' + sl('IDENTITY', '<button type="button" class="link" data-action="copy-id" data-id="' + esc(u.id) + '">COPY ID</button>') +
      kv('EMAIL', esc(u.email)) + kv('USERNAME', esc(u.username || '—'), u.username ? '' : 'm') +
      kv('CREATED', esc(fmtDate(u.created_at)) + ' · ' + esc(daysSince(u.created_at)) + 'd') +
      kv('LAST ACTIVE', lastActive ? esc(fmtDate(lastActive)) + ' · ' + esc(ago(lastActive)) : 'never', lastActive ? '' : 'm') +
      kv('EXPERIENCE · UNIT', esc((prof.training_experience || '—') + ' · ' + (prof.preferred_unit || '—'))) +
      (u.admin_locked_until ? kv('ADMIN LOCKOUT', esc(fmtDT(u.admin_locked_until)), 'bad') : '') +
      kv('TOKEN VERSION', esc(u.token_version), 'm') + '</div>';

    var scansActs = u.is_deleted ? '' : '<div class="acts"><button type="button" class="btn" data-action="act" data-act="credits">− / + CREDITS</button>' +
      (unlimitedRows.length ? '<button type="button" class="btn danger" data-action="act" data-act="revoke-unlimited" data-id="' + esc(unlimitedRows[0].id) + '">REVOKE UNLIMITED</button>' :
        '<button type="button" class="btn gold" data-action="act" data-act="grant-unlimited">GRANT UNLIMITED</button>') + '</div>';
    var drift = b.has_unlimited !== (unlimitedRows.length > 0);
    var scans = '<div class="card c-scans' + (drift ? ' warn' : '') + '">' + sl('SCANS', u.is_deleted ? ro('frozen while deleted') : '') +
      kv('SCAN_CREDITS', b.exists ? esc(num(b.scan_credits)) : 'no balance row yet', b.exists ? '' : 'm') +
      kv('HAS_UNLIMITED', esc(String(!!b.has_unlimited)) + (unlimitedRows.length ? ' · ' + esc(unlimitedRows[0].source) : ''), b.has_unlimited ? 'ov' : 'm') +
      kv('FREE RESET', b.free_scans_reset_at ? esc(fmtDate(b.free_scans_reset_at)) : '—', b.free_scans_reset_at ? '' : 'm') +
      kv('USED · 4 WK', esc(num(sumWeeks(d.usage && d.usage.scans && d.usage.scans.by_week, 'scans', 4)))) +
      (drift ? '<div class="hint warn">Drift: the cached flag disagrees with the entitlement rows. ' + (b.has_unlimited ? 'Grant unlimited to add the missing row, or a revoke from the audit trail.' : 'Revoke or re-grant to resync.') + '</div>' : '') +
      scansActs + '</div>';

    var ent = '<div class="card c-ent">' + sl('ENTITLEMENTS', ro('override · default')) +
      overrides.map(function (o) {
        var def = lim.defaults ? lim.defaults[o.def.field] : undefined;
        var cur = lim[o.def.field];
        return kv(o.def.label, (o.row ? '<span class="v ov">' + esc(o.row.value) + esc(o.def.unit) + '</span>' : muted('—')) + ' ' + muted('· ' + (def === undefined ? cur : def) + o.def.unit));
      }).join('') +
      '<div class="hint">' + esc(plural(ents.length, 'entitlement row')) + ' · ' + esc(ents.filter(function (e) { return e.active; }).length) + ' active</div>' +
      (u.is_deleted ? '' : '<div class="acts"><button type="button" class="btn" data-action="act" data-act="set-limits">SET LIMITS</button><button type="button" class="btn ghost" data-action="act" data-act="reset-limits"' + (hasOverride ? '' : ' disabled') + '>RESET TO DEFAULTS</button></div>') + '</div>';

    var purchases = '<div class="card c-purchases">' + sl('PURCHASES', ro()) +
      ((b.purchases || []).length ? b.purchases.map(function (r) {
        return '<div class="prow"><span class="n">' + esc(r.product_id.replace(/^.*\./, '')) + ' <span class="s">' + esc(r.purchase_type) + '</span></span><span class="r">' + (r.credits_added ? '+' + esc(num(r.credits_added)) : r.purchase_type === 'non_consumable' ? '∞' : '0') + '</span>' +
          '<span class="s">' + esc(fmtDate(r.created_at)) + ' · txn ' + esc(shortId(r.transaction_id)) + '</span><span class="s right">' + esc(shortId(r.id)) + '</span></div>';
      }).join('') : empty('No purchases.')) + '</div>';

    var campaign = '<div class="card c-campaign">' + sl('CAMPAIGN', u.is_deleted ? ro() : '') +
      (c ? kv('NAME', esc(c.name)) + kv('STATUS · SOURCE', chip(c.status, c.status === 'active' ? 'green' : 'dim') + ' · ' + esc(c.source)) +
        kv('START · END', esc(c.start_date) + ' → ' + esc(c.end_date)) +
        kv('ARC · WEEK', esc(c.current_arc_index === null || c.current_arc_index === undefined ? '—' : (c.current_arc_index + 1) + ' of ' + c.arcs) + (c.week_in_arc ? ' · wk ' + esc(c.week_in_arc) : '') + (c.deload_week ? ' · deload' : '')) +
        kv('NEXT HUNT', c.next_planned_hunt ? esc(c.next_planned_hunt) : '—', c.next_planned_hunt ? '' : 'm') +
        (c.goal ? kv('GOAL', esc(c.goal)) : '')
        : empty('No campaign. Import a template or pasted phases.')) +
      (u.is_deleted ? '' : '<div class="acts dk"><button type="button" class="btn" data-action="act" data-act="import">' + (c ? 'IMPORT / REPLACE' : 'IMPORT') + '</button></div>' +
        '<div class="hint ph-only">Import is desktop-only.</div>') + '</div>';

    // ── right column
    var progress = '<div class="card c-progress">' + sl('PROGRESS', ro()) +
      kv('LEVEL · RANK', esc(p.level) + ' · ' + esc(p.rank || '—')) + kv('TOTAL XP', esc(num(p.total_xp)) + ' ' + muted('· ' + num(p.xp_to_next_level) + ' to next')) +
      kv('STREAK · LONGEST', esc(p.current_streak) + ' · ' + esc(p.longest_streak)) + kv('WORKOUTS · PRS', esc(num(p.total_workouts)) + ' · ' + esc(num(p.total_prs))) +
      kv('LAST WORKOUT', p.last_workout_date ? esc(p.last_workout_date) : 'never', p.last_workout_date ? '' : 'm') + '</div>';

    var w = integ.whoop || {};
    var whoopStale = w.connected && w.token_expires_at && parseDate(w.token_expires_at) < new Date();
    var integrations = '<div class="card c-integrations' + (whoopStale ? ' warn' : '') + '">' + sl('INTEGRATIONS', ro()) +
      kv('WHOOP', w.connected ? (whoopStale ? 'connected · token expired' : 'connected') : 'not connected', w.connected ? (whoopStale ? 'warnv' : 'good') : 'm') +
      kv('LAST SYNC · SCOPE', w.connected ? esc(w.last_synced_at ? fmtDT(w.last_synced_at) : 'never') + (w.scope ? ' · ' + esc(w.scope) : '') : '—', w.connected ? '' : 'm') +
      kv('PUSH DEVICES', esc(num(integ.active_device_tokens)) + ' active') +
      kv('DAILY ACTIVITY', integ.latest_daily_activity_date ? esc(integ.latest_daily_activity_date) + (integ.daily_activity_sources_30d && integ.daily_activity_sources_30d.length ? ' · ' + esc(integ.daily_activity_sources_30d.join(' ')) : '') : 'none seen yet', integ.latest_daily_activity_date ? '' : 'm') + '</div>';

    var healthWarn = health.custom_exercises_without_family > 0 || health.sessions_missing_local_date > 0;
    var byStatus = function (m) { return Object.keys(m || {}).map(function (k) { return k + ' ' + m[k]; }).join(' · '); };
    var goals = byStatus(health.goals_by_status), gates = byStatus(health.gates_by_status);
    var dataHealth = '<div class="card c-health' + (healthWarn ? ' warn' : '') + '">' + sl('DATA HEALTH') +
      kv('CUSTOM EXERCISES W/O FAMILY', esc(health.custom_exercises_without_family) + ' ' + muted('of ' + health.custom_exercises), health.custom_exercises_without_family > 0 ? 'warnv' : '') +
      kv('SESSIONS W/O LOCAL_DATE', esc(health.sessions_missing_local_date) + ' ' + muted('of ' + health.sessions_total + (health.sessions_soft_deleted ? ' · ' + health.sessions_soft_deleted + ' soft-deleted' : '')), health.sessions_missing_local_date > 0 ? 'warnv' : '') +
      kv('BODYWEIGHT', esc(num(health.bodyweight_entries)) + (health.last_bodyweight_date ? ' · last ' + esc(health.last_bodyweight_date) : '')) +
      kv('GOALS · GATES', esc(goals || '—') + (gates ? ' · gates ' + esc(gates) : '')) +
      kv('ACHIEVEMENTS', esc(num(health.achievements_unlocked)) + ' unlocked') +
      '<div class="acts dk"><button type="button" class="btn" data-action="act" data-act="backfill">DRY-RUN BACKFILL</button></div><div class="hint dk">The family backfill is fleet-wide; the dry run lists every unresolved exercise before Apply.</div></div>';

    var preview = '<div class="card c-preview dk">' + sl('PREVIEW', ro('status tab as the hunter sees it')) + (pv ? renderPreview(pv) : empty('No preview.')) + '</div>';

    var auditCard = '<div class="card c-audit">' + sl('AUDIT · THIS HUNTER', '<a class="link" href="' + auditHref({ target_type: 'user', target_id: u.id }) + '">VIEW ALL</a>') +
      ((d.recent_audit || []).length ? d.recent_audit.map(auditRow).join('') : empty('No admin action on this hunter yet.')) + '</div>';

    // ── danger zone (full width)
    var dz;
    if (u.is_admin) {
      dz = '<div class="dz">' + kv('IS_DELETED', esc(String(u.is_deleted)), 'm') + kv('ADMIN', 'admin accounts cannot be deleted or purged from the console', 'm') + '</div>';
    } else if (!u.is_deleted) {
      dz = '<div class="dz">' + kv('IS_DELETED', 'false', 'm') + kv('GRACE WINDOW', '30 days after soft-delete, then purge-eligible', 'm') +
        '<div class="acts"><button type="button" class="btn danger sm" data-action="act" data-act="soft-delete">SOFT-DELETE</button></div></div>' +
        '<div class="hint">Soft-delete logs the hunter out everywhere (login → 403). Restore and Purge replace this button once deleted.</div>';
    } else {
      var eligible = u.purge_eligible_at ? parseDate(u.purge_eligible_at) : null;
      var daysLeft = eligible ? Math.ceil((eligible - Date.now()) / 86400000) : null;
      dz = '<div class="dz">' + kv('IS_DELETED · DELETED_AT', 'true · ' + esc(fmtDT(u.deleted_at))) +
        kv('PURGE', daysLeft === null ? '—' : daysLeft > 0 ? 'eligible in ' + esc(daysLeft) + 'd · ' + esc(fmtDate(eligible)) : 'eligible since ' + esc(fmtDate(eligible)), daysLeft !== null && daysLeft <= 0 ? 'bad' : 'warnv') +
        '<div class="acts"><button type="button" class="btn sm" data-action="act" data-act="restore">RESTORE</button><button type="button" class="btn danger sm dk" data-action="act" data-act="purge">PURGE</button></div></div>' +
        '<div class="hint ph-only">Purge is desktop-only.</div>';
    }
    var danger = '<div class="card danger full c-danger">' + sl('DANGER ZONE', '', 'danger') + dz + '</div>';

    html += '<div class="grid2 detail"><div class="col">' + identity + scans + ent + purchases + campaign + '</div><div class="col">' + progress + integrations + dataHealth + preview + auditCard + '</div>' + danger + '</div>';
    return html;
  }

  function renderPreview(pv) {
    var h = pv.hunt, l = pv.load || {}, cnd = pv.condition || {}, pr = pv.progress || {}, sb = pv.scan_balance || {};
    var day = parseDate(pv.today);
    var out = '<div class="pv"><div class="big c">' + esc(day ? ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'][day.getDay()] : '—') + '</div><div><div class="t">' + (h ? esc(h.title) : 'No hunt today') + '</div><div class="d">' + (h ? esc(h.type + ' · ' + h.status + (h.location_tag ? ' · ' + h.location_tag : '')) : esc(pv.today)) + '</div></div></div>';
    var bandCls = l.band === 'critical' ? 'r' : l.band === 'high' ? 'o' : l.band === 'ok' ? '' : 'y';   // the server emits critical / high / ok / cold-start
    out += '<div class="pv"><div class="big ' + bandCls + '">' + esc(l.run_acwr === null || l.run_acwr === undefined ? '—' : Number(l.run_acwr).toFixed(2)) + '</div><div><div class="t">Load · ' + esc(l.band || '—') + '</div><div class="d">7d ' + esc(Number(l.miles_7d || 0).toFixed(1)) + ' mi' + (l.miles_plan_7d ? ' of ' + esc(Number(l.miles_plan_7d).toFixed(1)) + ' planned' : '') + (l.flags && l.flags.length ? ' · ' + esc(l.flags.join(' ')) : ' · no flags') + '</div></div></div>';
    out += '<div class="pv"><div class="big">' + esc(cnd.score) + '</div><div><div class="t">Condition · ' + esc(cnd.band || '—') + '</div><div class="d">generated ' + esc(fmtDT(cnd.generated_at)) + '</div></div></div>';
    out += '<div class="pv"><div class="big c">' + esc(pr.level) + '</div><div><div class="t">' + esc(pr.rank) + ' · ' + esc(num(pr.total_xp)) + ' xp</div><div class="d">streak ' + esc(pr.current_streak) + ' · ' + (sb.has_unlimited ? '∞ scans' : esc(sb.scan_credits) + ' credits') + '</div></div></div>';
    return out;
  }

  // ── audit ──────────────────────────────────────────────────────────────

  function screenAudit(params) {
    var q = pick(params, AUDIT_KEYS);
    loadScreen({
      skeleton: auditHeader(q, null) + skelTable(6, 8),
      load: function () { return api('GET', '/admin/audit' + qs(Object.assign({ limit: PAGE, offset: 0 }, q))); },
      render: function (r) { return auditHeader(q, r) + renderAudit(q, r); },
      fallback: function (e) { return auditHeader(q, null) + errorBlock(e, true); }
    });
  }

  function auditHeader(q, r) {
    return pageHeader('Audit', (r ? esc(plural(num(r.total), 'event')) : '…') + ' · append-only') +
      '<form class="filters" id="audit-filters">' +
      '<select class="field" name="action" aria-label="Action">' + opt('', q.action || '', 'Action: all') + AUDIT_ACTIONS.map(function (a) { return opt(a, q.action || ''); }).join('') + '</select>' +
      '<select class="field" name="target_type" aria-label="Target type">' + opt('', q.target_type || '', 'Target: any') + ['user', 'product', 'system'].map(function (t) { return opt(t, q.target_type || ''); }).join('') + '</select>' +
      '<input class="field" name="target_id" placeholder="Target id" value="' + esc(q.target_id || '') + '" autocapitalize="none" spellcheck="false">' +
      '<input class="field" name="actor_user_id" placeholder="Actor id" value="' + esc(q.actor_user_id || '') + '" autocapitalize="none" spellcheck="false">' +
      '<button type="submit" class="btn sm">FILTER</button><a class="btn sm ghost" href="#/audit">CLEAR</a></form>';
  }

  function renderAudit(q, r) {
    if (!r.items.length) return empty('No actions match. Every mutation lands here — nothing is silent.', true);
    var rows = r.items.map(function (a, i) {
      return '<tr class="row" data-action="audit-toggle" data-idx="' + i + '" tabindex="0"><td>' + esc(fmtDT(a.created_at)) + '</td><td class="m">' + auditActor(a) + '</td><td>' + actionChip(a.action) + '</td>' +
        '<td>' + auditTarget(a) + '</td><td class="wrap">' + (a.reason ? esc(a.reason) : muted('—')) + '</td><td class="m">' + esc(shortId(a.request_id)) + '</td></tr>' +
        '<tr class="expand" id="audit-x-' + i + '" hidden><td colspan="6">' + jsonPanels(a.before, a.after) +
        '<div class="hint">audit ' + esc(a.id) + ' · actor ' + esc(a.actor_user_id || 'system') + (a.ip ? ' · ip ' + esc(a.ip) : '') + (a.request_id ? ' · request ' + esc(a.request_id) : '') + (a.idempotency_key ? ' · idempotency ' + esc(a.idempotency_key) : '') + '</div></td></tr>';
    }).join('');
    return table('audit', '<th class="sorted">Time ↓</th><th>Actor</th><th>Action</th><th>Target</th><th>Reason</th><th>Request</th>', rows) + pager(q, r.total);
  }

  function jsonPanels(before, after) {
    if (before === null && after === null || before === undefined && after === undefined) return '<div class="hint">No before/after payload on this row.</div>';
    var b = isObj(before) ? before : null, a = isObj(after) ? after : null;
    var pre = function (label, obj, other, cls) {
      var body;
      if (obj) {
        body = '{\n' + Object.keys(obj).sort().map(function (k) {
          var changed = other ? !(k in other) || !deepEq(other[k], obj[k]) : true;
          var line = '  "' + esc(k) + '": ' + esc(JSON.stringify(obj[k]));
          return changed && other ? '<span class="' + cls + '">' + line + '</span>' : line;
        }).join(',\n') + '\n}';
      } else {
        var raw = label === 'Before' ? before : after;
        body = raw === null || raw === undefined ? muted('null') : esc(JSON.stringify(raw, null, 2));
      }
      return '<div><div class="lbl">' + label + '</div><pre>' + body + '</pre></div>';
    };
    return '<div class="json2">' + pre('Before', b, a, 'old') + pre('After', a, b, 'chg') + '</div>';
  }

  // ── catalog ────────────────────────────────────────────────────────────

  function screenCatalog() {
    if (isPhone()) { content.innerHTML = desktopOnly('Catalog'); return; }
    loadScreen({
      skeleton: pageHeader('Catalog') + skelTable(7, 3),
      load: function () { return api('GET', '/admin/products'); },
      render: function (items) { state.products = items; return renderCatalog(items); },
      fallback: function (e) { return pageHeader('Catalog') + errorBlock(e, true); }
    });
  }

  function renderCatalog(items) {
    var rows = items.map(function (p) {
      return '<tr class="row" data-action="act" data-act="product-edit" data-id="' + esc(p.id) + '"><td>' + esc(p.id) + '</td><td>' + esc(p.kind) + '</td><td class="' + (p.entitlement_key ? 'y' : 'g') + '">' + (p.entitlement_key ? '∞' : '+' + esc(num(p.credits))) + '</td>' +
        '<td class="m">' + esc(p.entitlement_key || '—') + '</td><td class="un">' + esc(p.display_name) + '</td><td><span class="tog' + (p.active ? ' on' : '') + '"></span></td><td class="m">' + esc(p.sort_order) + '</td>' +
        '<td class="r"><button type="button" class="btn sm ghost" data-action="act" data-act="product-edit" data-id="' + esc(p.id) + '">EDIT</button></td></tr>';
    }).join('');
    return pageHeader('Catalog', esc(items.length) + ' products · StoreKit ids', '<button type="button" class="btn sm" data-action="act" data-act="product-new">ADD SKU</button>') +
      table('', '<th>Product id</th><th>Kind</th><th>Credits</th><th>Entitlement</th><th>Display name</th><th>Active</th><th>Sort</th><th></th>', rows) +
      '<div class="hint">Deactivating hides a product from the paywall and refuses new purchases of it; App Store Connect is untouched. Credits changes apply to future purchases only. Ids are immutable; nothing is ever deleted.</div>';
  }

  // ── settings (read-only) ───────────────────────────────────────────────

  function screenSettings() {
    if (isPhone()) { content.innerHTML = desktopOnly('Settings'); return; }
    var header = pageHeader('Settings', 'read-only · edit on Railway (service variables) · a redeploy applies');
    loadScreen({
      skeleton: header + '<div class="card narrow">' + sl('SCAN DEFAULTS') + skelRows(3) + '</div>',
      load: function () {
        // the only place the API exposes the global scan defaults is a hunter detail's effective_limits
        var uid = session && session.userId ? Promise.resolve(session.userId) : api('GET', '/admin/me').then(function (m) { return m.user_id; });
        return uid.then(function (id) { return api('GET', userPath(id)); });
      },
      render: function (d) {
        var def = (d.effective_limits && d.effective_limits.defaults) || {};
        var ttl = session && session.expiresAt && session.issuedAt ? Math.round((session.expiresAt - session.issuedAt) / 60000) : null;
        return header +
          '<div class="card narrow">' + sl('SCAN DEFAULTS', ro('live · every hunter without an override')) +
          kv('FREE_MONTHLY_SCANS', esc(def.free_monthly)) + kv('DAILY_SCREENSHOT_LIMIT', esc(def.daily_limit)) + kv('COOLDOWN_SECONDS', esc(def.cooldown_seconds) + 's') +
          '<div class="hint">Per-hunter overrides live in Entitlements on the hunter; these are the fallbacks.</div></div>' +
          '<div class="card narrow top">' + sl('ADMIN SESSION', ro('live')) +
          kv('ADMIN_TOKEN_EXPIRE_MINUTES', ttl === null ? '—' : esc(ttl) + ' min') + kv('SIGNED IN AS', esc(session.email), 'm') +
          kv('LOCKOUT', '10 bad passwords → 15 min ' + muted('· spec defaults')) + '</div>' +
          '<div class="card narrow top">' + sl('KILL SWITCHES · PURGE', ro('not exposed by the API')) +
          kv('PURGE_GRACE_DAYS', '30 ' + muted('· default')) + kv('PURGE_SWEEP_ENABLED', 'flip on Railway after a clean dry-run sweep from Overview', 'm') +
          kv('SCREENSHOT_PROCESSING_ENABLED', 'Railway variable', 'm') +
          '<div class="hint">Editable settings need an app_settings table (spec §14, v2). Until then the console shows what the API exposes and names the rest.</div></div>';
      },
      fallback: function (e) { return header + errorBlock(e, true); }
    });
  }

  function desktopOnly(name) {
    return pageHeader(name) + sysline('DESKTOP ONLY', esc(name) + ' is not part of the phone lane. Open the console on a laptop.', 'guard', '<a class="btn sm ghost" href="#/hunters">HUNTERS</a>');
  }

  // ── drawer engine (spec §10.4) ─────────────────────────────────────────
  //
  // A spec declares: title, who, danger/gold, intro, values, fields(v),
  // diff(v), validate(v) → problem, minReason(v), confirmLabel(v),
  // password (true | fn(v) → destructive tier), confirmEmail,
  // dryRun{label, applyLabel, run, render, canApply}, submit(v, reason,
  // password, drawer), onSuccess(result) → {message, auditId | auditLookup, after}.
  // The engine owns the reason / typed-email / password inputs (data-meta),
  // the gate, the error above Confirm, the toast, and the refresh.

  function openDrawer(spec) {
    drawer = {
      spec: spec, values: spec.values || {}, reason: pendingReason || '', password: '', typedEmail: '',
      error: null, busy: false, result: null, idem: uuid(), opener: document.activeElement
    };
    pendingReason = '';
    drawerEl.className = 'drawer' + (spec.danger ? ' danger' : '');
    drawerEl.innerHTML = '<div class="grab"></div><button type="button" class="x" data-action="drawer-close" aria-label="Close">✕</button>' +
      sl(spec.title, '', spec.danger ? 'danger' : '') + '<div class="who">' + esc(spec.who || '') + '</div>' +
      '<div class="dr-intro">' + (spec.intro || '') + '</div><div class="dr-fields"></div><div class="dr-diff diffs"></div><div class="dr-result"></div>' +
      '<div class="flabel">Reason <b>required · written to audit</b></div><textarea class="field area" data-meta="reason" placeholder="Why — this line is the audit row" rows="2">' + esc(drawer.reason) + '</textarea>' +
      '<div class="dr-email" hidden><div class="flabel">Type the email to confirm</div><input class="field" type="email" data-meta="typedEmail" autocapitalize="none" autocorrect="off" spellcheck="false" placeholder="' + esc(spec.confirmEmail || '') + '"><div class="hint err dr-email-hint"></div></div>' +
      '<div class="dr-pass" hidden><div class="flabel">Re-enter admin password <b>destructive tier</b></div><input class="field" type="password" data-meta="password" autocomplete="current-password" placeholder="••••••••"></div>' +
      '<div class="dr-hint hint">' + (spec.hint || '') + '</div><div class="dr-error"></div>' +
      '<div class="acts dr-actions"><button type="button" class="btn ghost" data-action="drawer-close">CANCEL</button><button type="button" class="btn ' + (spec.danger ? 'danger solid' : spec.gold ? 'gold solid' : 'primary') + '" data-action="drawer-confirm"></button></div>';
    drawerEl.hidden = false;
    scrimEl.hidden = false;
    renderFields();
    updateDrawer();
    setTimeout(function () { var f = $('.dr-fields input, .dr-fields select, .dr-fields textarea', drawerEl) || $('[data-meta="reason"]', drawerEl); if (f && !isPhone()) f.focus(); }, 30);
  }

  function closeDrawer(silent) {
    if (!drawer) return;
    if (!silent && drawer.reason && drawer.error) pendingReason = drawer.reason;
    var opener = drawer.opener;
    drawer = null;
    drawerEl.hidden = true;
    drawerEl.innerHTML = '';
    scrimEl.hidden = true;
    if (opener && opener.focus && document.contains(opener)) opener.focus();
  }

  function renderFields() {
    if (!drawer) return;
    $('.dr-fields', drawerEl).innerHTML = drawer.spec.fields ? drawer.spec.fields(drawer.values, drawer) : '';
  }

  function inputValue(input) {
    if (input.type === 'checkbox') return input.checked;
    if (input.type === 'number') return input.value === '' ? null : Number(input.value);
    return input.value;
  }

  function readDrawerInputs() {
    $$('[data-field], [data-meta]', drawerEl).forEach(function (input) {
      if (input.type === 'radio' && !input.checked) return;
      if (input.dataset.meta) drawer[input.dataset.meta] = inputValue(input);
      else drawer.values[input.dataset.field] = inputValue(input);
    });
  }

  function phase() { return drawer && drawer.spec.dryRun ? (drawer.result ? 'apply' : 'dry') : 'submit'; }

  // The one computation behind the Confirm button: what it says and whether it may fire.
  function drawerGate() {
    var d = drawer, s = d.spec, v = d.values, ph = phase();
    var pw = s.password;
    var needsPass = ph !== 'dry' && (pw === true || (typeof pw === 'function' && !!pw(v)));   // dry runs never take a password
    var emailOk = !s.confirmEmail || d.typedEmail.trim().toLowerCase() === String(s.confirmEmail).trim().toLowerCase();
    var minReason = s.minReason ? s.minReason(v) : 3;
    var problem = s.validate ? s.validate(v, d) : null;
    var applyBlocked = ph === 'apply' && !!s.dryRun.canApply && !s.dryRun.canApply(d.result);
    return {
      ph: ph, needsPass: needsPass, emailOk: emailOk, minReason: minReason, problem: problem,
      label: ph === 'dry' ? (s.dryRun.label || 'DRY RUN') : ph === 'apply' ? (s.dryRun.applyLabel || 'APPLY') : (s.confirmLabel ? s.confirmLabel(v) : 'CONFIRM'),
      blocked: d.busy || d.reason.trim().length < minReason || !emailOk || !!problem || (needsPass && !d.password) || applyBlocked
    };
  }

  function updateDrawer() {
    if (!drawer) return;
    var d = drawer, s = d.spec, g = drawerGate();
    $('.dr-diff', drawerEl).innerHTML = s.diff ? s.diff(d.values, d) : '';
    $('.dr-pass', drawerEl).hidden = !g.needsPass;
    $('.dr-email', drawerEl).hidden = !s.confirmEmail;
    if (s.confirmEmail) {
      var eh = $('.dr-email-hint', drawerEl);
      eh.textContent = g.emailOk ? 'Matches — unlocked' : 'Type ' + s.confirmEmail + ' exactly to unlock';
      eh.className = 'hint dr-email-hint ' + (g.emailOk ? 'ok' : 'err');
    }
    $('.dr-hint', drawerEl).innerHTML = g.problem ? '<span class="err">' + esc(g.problem) + '</span>' : (s.hint || '') + (g.minReason > 3 ? ' <span class="warn">Reason must be at least ' + g.minReason + ' characters.</span>' : '');
    $('.dr-error', drawerEl).innerHTML = d.error ? sysline('HTTP ' + (d.error.status || 'NETWORK'), esc(d.error.message), 'err') : '';
    var btn = $('[data-action="drawer-confirm"]', drawerEl);
    btn.textContent = d.busy ? '…' : g.label;
    btn.disabled = g.blocked;
  }

  function renderResult() {
    var el = drawer ? $('.dr-result', drawerEl) : null;
    if (el) el.innerHTML = drawer.result && drawer.spec.dryRun.render ? drawer.spec.dryRun.render(drawer.result, drawer.values) : '';
  }

  function confirmDrawer() {
    var d = drawer;
    if (!d) return;
    var g = drawerGate();
    if (g.blocked) return;
    var s = d.spec;
    d.error = null; d.busy = true; updateDrawer();
    var reason = d.reason.trim();
    var p;
    if (g.ph === 'dry') {
      p = Promise.resolve().then(function () { return s.dryRun.run(d.values, reason, d); }).then(function (r) { if (drawer === d) { d.result = r; renderResult(); } });
    } else {
      p = Promise.resolve().then(function () { return s.submit(d.values, reason, g.needsPass ? d.password : undefined, d); }).then(function (res) {
        var out = s.onSuccess ? s.onSuccess(res, d.values) : {};
        return Promise.resolve(out.auditId || (out.auditLookup ? latestAuditId(out.auditLookup) : null)).then(function (auditId) {
          if (drawer !== d) return;
          closeDrawer(true);
          toast(out.message || 'Done', auditId, out.auditLookup ? auditHref(out.auditLookup) : undefined);
          if (out.after) out.after(); else onRoute();   // re-render whatever screen the drawer opened from
        });
      });
    }
    p.catch(function (e) {
      if (drawer !== d) return;   // an expiry already closed this drawer and went to Login
      d.error = e;
    }).then(function () {
      d.busy = false;
      if (drawer === d) updateDrawer();
    });
  }

  // ── toast ──────────────────────────────────────────────────────────────

  function toast(message, auditId, href) {
    var el = document.createElement('div');
    el.className = 'toast';
    el.innerHTML = '✓<span class="sp">' + esc(message) + '</span>' +
      (auditId ? '<a href="' + esc(href || '#/audit') + '">audit ' + esc(shortId(auditId)) + '</a>' : '');
    el.dataset.action = 'toast-close';
    $('#toasts').appendChild(el);
    setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 7000);
  }

  // ── action specs ───────────────────────────────────────────────────────

  function who(d) { return (d.user.username ? d.user.username + ' · ' : '') + d.user.email; }
  function auditFor(d) { return { target_type: 'user', target_id: d.user.id }; }
  // Every mutation body carries the reason; the destructive tier adds the re-entered password.
  function stepUp(body, reason, password) {
    body.reason = reason;
    if (password !== undefined) body.password = password;
    return body;
  }
  function post(path, body, headers) { return api('POST', path, { body: body, headers: headers }); }

  function creditsSpec(d) {
    var before = d.balance.exists ? d.balance.scan_credits : 0;
    var display = function (v) { return '<div class="n' + (v.delta < 0 ? ' neg' : '') + '">' + esc(sign(v.delta || 0)) + '<small>CREDITS</small></div>'; };
    return {
      title: 'ADJUST CREDITS', who: who(d), values: { delta: 10 },
      fields: function (v) {
        return '<div class="stepper"><button type="button" data-action="dr" data-op="step" data-n="-1" aria-label="minus one">−</button>' + display(v) + '<button type="button" data-action="dr" data-op="step" data-n="1" aria-label="plus one">+</button></div>' +
          '<div class="presets">' + [-20, -5, 5, 20, 50, 100].map(function (n) { return '<button type="button" data-action="dr" data-op="preset" data-n="' + n + '">' + sign(n) + '</button>'; }).join('') + '</div>' +
          '<input class="field" type="number" step="1" inputmode="numeric" data-field="delta" value="' + esc(v.delta) + '" aria-label="Delta">';
      },
      onAction: function (op, el, v) {
        if (op === 'step') v.delta = (parseInt(v.delta, 10) || 0) + parseInt(el.dataset.n, 10);
        if (op === 'preset') v.delta = parseInt(el.dataset.n, 10);
      },
      afterInput: function (v, root) { var n = $('.stepper .n', root); if (n) n.outerHTML = display(v); },
      diff: function (v) {
        var delta = parseInt(v.delta, 10) || 0;
        return diffRow('SCAN_CREDITS', before, before + delta, { down: delta < 0 }) + diffRow('HAS_UNLIMITED', String(!!d.balance.has_unlimited), String(!!d.balance.has_unlimited)) +
          diffRow('FREE_SCANS_RESET_AT', fmtDate(d.balance.free_scans_reset_at), fmtDate(d.balance.free_scans_reset_at));
      },
      validate: function (v) {
        var delta = Number(v.delta);
        if (!Number.isInteger(delta) || delta === 0) return 'Delta must be a non-zero whole number.';
        if (before + delta < 0) return 'That would leave ' + (before + delta) + ' credits — the server refuses a negative balance (409).';
        return null;
      },
      password: function (v) { return Math.abs(parseInt(v.delta, 10) || 0) > CREDITS_STEP_UP; },
      confirmLabel: function (v) { return 'CONFIRM ' + sign(parseInt(v.delta, 10) || 0) + ' CREDITS'; },
      hint: 'Logged as credits.adjust. Over ±' + CREDITS_STEP_UP + ' needs your password. The Idempotency-Key was minted when this drawer opened, so a retry after a network error cannot double-apply.',
      submit: function (v, reason, password, dr) {
        return post(userPath(d.user.id, '/credits'), stepUp({ delta: parseInt(v.delta, 10) }, reason, password), { 'Idempotency-Key': dr.idem });
      },
      onSuccess: function (r) {
        return { message: 'Credits ' + r.scan_credits_before + ' → ' + r.scan_credits_after + (r.replayed ? ' (replayed)' : ''), auditId: r.audit_id, auditLookup: auditFor(d) };
      }
    };
  }

  function grantUnlimitedSpec(d) {
    var credits = d.balance.exists ? d.balance.scan_credits : 0;
    return {
      title: 'GRANT UNLIMITED', who: who(d), gold: true,
      diff: function () {
        return diffRow('HAS_UNLIMITED', String(!!d.balance.has_unlimited), 'true') + diffRow('SCAN_CREDITS', credits, credits + ' (kept)', { same: true }) +
          diffRow('ENTITLEMENT', '—', 'scans.unlimited · admin_grant');
      },
      confirmLabel: function () { return 'CONFIRM GRANT'; },
      hint: 'Adds an admin_grant row for scans.unlimited and syncs the cached flag. Revoke is destructive tier (password) from the same card.',
      submit: function (v, reason) { return post(userPath(d.user.id, '/entitlements'), stepUp({ key: 'scans.unlimited', value: true }, reason)); },
      onSuccess: function () { return { message: 'Unlimited granted · ' + d.user.email, auditLookup: auditFor(d) }; }
    };
  }

  function revokeUnlimitedSpec(d, row) {
    return {
      title: 'REVOKE UNLIMITED', who: who(d), danger: true, password: true,
      intro: row.source === 'purchase' ? sysline('GUARD · PURCHASE-SOURCED', 'This row came from an App Store purchase (' + esc(shortId(row.purchase_record_id)) + '). Revoking it survives Restore Purchases — the hunter loses what they paid for until you grant again.', 'guard') : '',
      diff: function () { return diffRow('HAS_UNLIMITED', 'true', 'false', { down: true }) + diffRow('ENTITLEMENT ' + shortId(row.id), row.source + ' · active', 'revoked', { down: true }); },
      confirmLabel: function () { return 'REVOKE'; },
      hint: 'Logged as entitlement.revoke. The row stays in history with revoked_at set.',
      submit: function (v, reason, password) { return post(userPath(d.user.id, '/entitlements/' + encodeURIComponent(row.id) + '/revoke'), stepUp({}, reason, password)); },
      onSuccess: function () { return { message: 'Unlimited revoked · ' + d.user.email, auditLookup: auditFor(d) }; }
    };
  }

  function setLimitsSpec(d) {
    var lim = d.effective_limits;
    var values = {};
    LIMIT_KEYS.forEach(function (k) { values[k.field] = lim[k.field]; });
    var changed = function (v) { return LIMIT_KEYS.filter(function (k) { return v[k.field] !== null && v[k.field] !== undefined && Number(v[k.field]) !== Number(lim[k.field]); }); };
    return {
      title: 'SET LIMITS', who: who(d), values: values,
      fields: function (v) {
        return LIMIT_KEYS.map(function (k, i) {
          return fieldRow(k.label, 'default ' + lim.defaults[k.field] + k.unit, '<input class="field" type="number" min="0" step="1" inputmode="numeric" data-field="' + k.field + '" value="' + esc(v[k.field]) + '">', i === 0);
        }).join('');
      },
      diff: function (v) { return LIMIT_KEYS.map(function (k) { return diffRow(k.key, lim[k.field] + k.unit, (v[k.field] === null ? '—' : v[k.field]) + k.unit); }).join(''); },
      validate: function (v) {
        var bad = LIMIT_KEYS.filter(function (k) { return v[k.field] === null || !Number.isInteger(Number(v[k.field])) || Number(v[k.field]) < 0; });
        if (bad.length) return bad[0].label + ' must be a whole number ≥ 0.';
        if (!changed(v).length) return 'Nothing changed yet.';
        return null;
      },
      confirmLabel: function (v) { return 'GRANT ' + plural(changed(v).length, 'OVERRIDE'); },
      hint: 'One admin_grant row per changed key; the newest active row wins. Reset to defaults revokes them.',
      submit: function (v, reason) {
        return sequential(changed(v), function (k) { return post(userPath(d.user.id, '/entitlements'), stepUp({ key: k.key, value: Number(v[k.field]) }, reason)); });
      },
      onSuccess: function (rows) { return { message: plural(rows.length, 'limit override') + ' granted · ' + d.user.email, auditLookup: auditFor(d) }; }
    };
  }

  function resetLimitsSpec(d) {
    var rows = [];
    LIMIT_KEYS.forEach(function (k) { activeRows(d, k.key).forEach(function (r) { rows.push({ def: k, row: r }); }); });
    return {
      title: 'RESET TO DEFAULTS', who: who(d), danger: true, password: true,
      diff: function () { return rows.map(function (r) { return diffRow(r.def.key, r.row.value + r.def.unit, d.effective_limits.defaults[r.def.field] + r.def.unit + ' (default)', { down: true }); }).join(''); },
      confirmLabel: function () { return 'REVOKE ' + plural(rows.length, 'OVERRIDE'); },
      hint: 'Each revoke is its own entitlement.revoke audit row; the global defaults apply immediately.',
      submit: function (v, reason, password) {
        return sequential(rows, function (r) { return post(userPath(d.user.id, '/entitlements/' + encodeURIComponent(r.row.id) + '/revoke'), stepUp({}, reason, password)); });
      },
      onSuccess: function (out) { return { message: plural(out.length, 'override') + ' revoked · defaults apply', auditLookup: auditFor(d) }; }
    };
  }

  function softDeleteSpec(d) {
    return {
      title: 'SOFT-DELETE', who: who(d), danger: true, password: true,
      diff: function () { return diffRow('IS_DELETED', 'false', 'true', { down: true }) + diffRow('DELETED_AT', 'null', 'now', { down: true }) + diffRow('PURGE ELIGIBLE', '—', 'in 30 days'); },
      confirmLabel: function () { return 'SOFT-DELETE'; },
      hint: 'The hunter\'s next request answers 401 and login 403. Data stays; Restore undoes it any time before purge.',
      submit: function (v, reason, password) { return post(userPath(d.user.id, '/delete'), stepUp({}, reason, password)); },
      onSuccess: function (r) { return { message: 'Soft-deleted · ' + d.user.email + ' · ' + fmtDT(r.deleted_at), auditLookup: auditFor(d) }; }
    };
  }

  function restoreSpec(d) {
    return {
      title: 'RESTORE', who: who(d), password: true,
      diff: function () { return diffRow('IS_DELETED', 'true', 'false') + diffRow('DELETED_AT', fmtDT(d.user.deleted_at), 'null') + diffRow('TOKEN_VERSION', d.user.token_version, d.user.token_version + 1); },
      confirmLabel: function () { return 'RESTORE'; },
      hint: 'Bumps token_version so refresh tokens minted before the deletion die; the hunter logs in again.',
      submit: function (v, reason, password) { return post(userPath(d.user.id, '/restore'), stepUp({}, reason, password)); },
      onSuccess: function () { return { message: 'Restored · ' + d.user.email, auditLookup: auditFor(d) }; }
    };
  }

  function purgeSpec(d) {
    var u = d.user, h = d.data_health || {};
    var eligible = u.purge_eligible_at ? parseDate(u.purge_eligible_at) : null;
    var inGrace = eligible ? eligible > new Date() : true;
    var daysDeleted = u.deleted_at ? daysSince(u.deleted_at) : 0;
    var impact = [[h.sessions_total, 'sessions'], [h.prs_total, 'prs'], [h.bodyweight_entries, 'bodyweight'], [h.custom_exercises, 'custom exercises'],
      [h.achievements_unlocked, 'achievements'], [(d.balance.purchases || []).length, 'receipts kept'], [(d.entitlements || []).length, 'entitlements'], [d.integrations ? d.integrations.active_device_tokens : 0, 'push devices']];
    return {
      title: 'HARD PURGE', who: who(d), danger: true, password: true, confirmEmail: u.email, values: { force: false },
      intro: (inGrace ? sysline('GUARD · GRACE WINDOW OPEN', 'Deleted <b>' + esc(daysDeleted) + ' of 30</b> days ago. Purge is blocked until <b>' + esc(fmtDate(eligible)) + '</b> unless FORCE is set — the override is its own audit fact and needs a reason of ten characters or more.', 'guard') :
        sysline('PAST GRACE', 'Eligible since <b>' + esc(fmtDate(eligible)) + '</b>. The deploy-time sweep would take this account once PURGE_SWEEP_ENABLED is on.', 'ok')) +
        '<div class="impact">' + impact.map(function (i) { return '<div><b>' + esc(num(i[0])) + '</b><small>' + esc(i[1]) + '</small></div>'; }).join('') + '</div>' +
        '<div class="hint err">Deletes the user row and every table in PURGE_ORDER. Purchase receipts are kept but detached (user_id → NULL). The audit trail keeps the id. Cannot be undone.</div>',
      fields: function (v) { return inGrace ? checkbox('force', v.force, 'FORCE — purge before the grace window ends', true) : ''; },
      minReason: function (v) { return v.force ? 10 : 3; },
      validate: function (v) { return inGrace && !v.force ? 'Inside the grace window — tick FORCE to purge now (server answers 409 otherwise).' : null; },
      confirmLabel: function () { return 'PURGE ' + (u.username || u.email); },
      hint: 'Logged as user.purge with per-table counts.',
      submit: function (v, reason, password, dr) { return post(userPath(u.id, '/purge'), stepUp({ confirm_email: dr.typedEmail.trim(), force: !!v.force }, reason, password)); },
      onSuccess: function (r) {
        var tables = Object.keys(r.tables || {});
        var rows = tables.reduce(function (a, k) { return a + (r.tables[k] || 0); }, 0);
        return { message: 'Purged ' + u.email + ' · ' + rows + ' rows across ' + plural(tables.length, 'table'), auditId: r.audit_id, auditLookup: auditFor(d), after: function () { go('hunters', { deleted: 'true' }); } };
      }
    };
  }

  function backfillSpec() {
    return {
      title: 'EXERCISE-FAMILY BACKFILL', who: 'fleet-wide · maintenance', password: true,
      hint: 'Dry run first: it lists every exercise the resolver cannot place. Apply is destructive tier (password) and writes one maintenance.family_backfill audit row.',
      dryRun: {
        label: 'DRY RUN', applyLabel: 'APPLY BACKFILL',
        run: function (v, reason) { return post('/admin/maintenance/exercise-families', stepUp({ dry_run: true }, reason)); },
        render: function (r) {
          var un = r.unresolved || [];
          return sysline('DRY RUN', '<b>' + esc(r.families_changed) + '</b> families to change · <b>' + esc(r.exercises_updated) + '</b> exercises to update · ' + esc(r.assigned) + ' of ' + esc(r.total) + ' already assigned', 'ok') +
            (un.length ? '<div class="flabel">Unresolved · ' + esc(un.length) + '</div><ul class="list">' + un.slice(0, 40).map(function (x) { return '<li><span>' + esc(x.name) + '</span>' + muted(x.is_custom ? 'custom · ' + shortId(x.user_id) : 'catalog') + '</li>'; }).join('') + (un.length > 40 ? '<li class="muted">+' + (un.length - 40) + ' more</li>' : '') + '</ul>' : '<div class="hint ok">Nothing unresolved.</div>');
        }
      },
      submit: function (v, reason, password) { return post('/admin/maintenance/exercise-families', stepUp({ dry_run: false }, reason, password)); },
      onSuccess: function (r) { return { message: 'Backfill applied · ' + r.exercises_updated + ' exercises updated · ' + r.families_changed + ' families changed', auditLookup: { action: 'maintenance.family_backfill' } }; }
    };
  }

  function sweepSpec() {
    return {
      title: 'PURGE-ELIGIBLE SWEEP', who: 'fleet-wide · maintenance', danger: true, password: true,
      hint: 'Dry run lists every soft-deleted account past the 30-day grace window. Apply purges all of them (password required). A clean dry run here is the gate for PURGE_SWEEP_ENABLED on Railway.',
      dryRun: {
        label: 'DRY RUN', applyLabel: 'PURGE LISTED ACCOUNTS',
        run: function (v, reason) { return post('/admin/maintenance/purge-eligible', stepUp({ dry_run: true }, reason)); },
        render: function (r) {
          var rows = r.eligible || [];
          if (!rows.length) return sysline('DRY RUN · CLEAN', 'No account is past the grace window. Nothing would be purged.', 'ok');
          return sysline('DRY RUN', '<b>' + esc(rows.length) + '</b> ' + esc(rows.length === 1 ? 'account' : 'accounts') + ' would be purged.', 'guard') +
            '<ul class="list">' + rows.map(function (x) { return '<li><a href="' + hunterHref(x.user_id) + '">' + esc(shortId(x.user_id)) + '</a>' + muted('deleted ' + fmtDate(x.deleted_at) + ' · ' + x.days_deleted + 'd') + '</li>'; }).join('') + '</ul>';
        },
        canApply: function (r) { return r && r.eligible && r.eligible.length > 0; }
      },
      submit: function (v, reason, password) { return post('/admin/maintenance/purge-eligible', stepUp({ dry_run: false }, reason, password)); },
      onSuccess: function (r) { return { message: 'Sweep purged ' + plural((r.purged || []).length, 'account'), auditLookup: { action: 'user.purge' } }; }
    };
  }

  function seedSpec() {
    return {
      title: 'SEED ACHIEVEMENTS', who: 'fleet-wide · maintenance',
      hint: 'Idempotent: inserts any missing achievement definition and reports the count. Audited as maintenance.seed_achievements.',
      confirmLabel: function () { return 'SEED'; },
      submit: function (v, reason) { return post('/admin/maintenance/seed-achievements', stepUp({}, reason)); },
      onSuccess: function (r) { return { message: 'Seeded ' + plural(r.seeded, 'achievement definition'), auditLookup: { action: 'maintenance.seed_achievements' } }; }
    };
  }

  function importSpec(d) {
    var hasCampaign = !!d.campaign;
    var body = function (v, dry, reason, password) {
      var out = { name: v.name.trim(), dry_run: dry, replace: !!v.replace, client_date: todayISO(), objectives: [] };
      if (v.mode === 'template') out.template = v.template; else out.phases = JSON.parse(v.phases);
      if (v.start_date) out.start_date = v.start_date;
      if (v.goal && v.goal.trim()) out.goal = v.goal.trim();
      return stepUp(out, reason, password);
    };
    var radio = function (v, value, label) {
      return '<label class="' + (v.mode === value ? 'on' : '') + '"><input type="radio" name="mode" value="' + value + '" data-field="mode"' + (v.mode === value ? ' checked' : '') + '>' + label + '</label>';
    };
    return {
      title: hasCampaign ? 'IMPORT / REPLACE CAMPAIGN' : 'IMPORT CAMPAIGN', who: who(d),
      values: { mode: 'template', template: TEMPLATES[0], phases: '', name: '', start_date: '', goal: '', replace: false },
      intro: hasCampaign ? sysline('ACTIVE CAMPAIGN', esc(d.campaign.name) + ' · ' + esc(d.campaign.status) + ' · arc ' + esc((d.campaign.current_arc_index || 0) + 1) + ' of ' + esc(d.campaign.arcs) + '. Apply answers 409 unless REPLACE is ticked; replace retires it and deletes its future planned hunts.', 'guard') : '',
      fields: function (v) {
        return '<div class="radios">' + radio(v, 'template', 'Template') + radio(v, 'paste', 'Paste phases JSON') + '</div>' +
          (v.mode === 'template' ? fieldRow('Template', '', '<select class="field" data-field="template">' + TEMPLATES.map(function (t) { return opt(t, v.template); }).join('') + '</select>') :
            fieldRow('Phases', 'JSON array of PhaseIn', '<textarea class="field area code" data-field="phases" placeholder=\'[{"label": "Months 1–2", "milesMin": 10, "milesMax": 14, "days": [...]}]\'>' + esc(v.phases) + '</textarea>')) +
          fieldRow('Name', '', '<input class="field" data-field="name" value="' + esc(v.name) + '" placeholder="Run Base + Strength" maxlength="120">') +
          fieldRow('Start date', 'optional · defaults to this week\'s Monday', '<input class="field" type="date" data-field="start_date" value="' + esc(v.start_date) + '">') +
          fieldRow('Goal', 'optional', '<input class="field" data-field="goal" value="' + esc(v.goal) + '" maxlength="500">') +
          (hasCampaign ? checkbox('replace', v.replace, 'REPLACE the active campaign', true) : '');
      },
      validate: function (v) {
        if (!v.name || !v.name.trim()) return 'Name the campaign.';
        if (v.mode === 'paste') {
          try { var p = JSON.parse(v.phases); if (!Array.isArray(p) || !p.length) return 'Phases must be a non-empty JSON array.'; } catch (e) { return 'Phases is not valid JSON.'; }
        }
        return null;
      },
      dryRun: {
        label: 'DRY RUN', applyLabel: 'APPLY IMPORT',
        run: function (v, reason) { return post(userPath(d.user.id, '/campaign/import'), body(v, true, reason)); },
        render: function (r) {
          var arcs = r.arcs_preview || [];
          return sysline('DRY RUN', '<b>' + esc(arcs.length) + '</b> arcs · ' + esc(arcs.reduce(function (a, x) { return a + (x.templates || 0); }, 0)) + ' hunt templates' + (r.retired_campaign_id ? ' · retires ' + esc(shortId(r.retired_campaign_id)) : '') + (r.planned_hunts_deleted ? ' · deletes ' + esc(r.planned_hunts_deleted) + ' planned hunts' : ''), 'ok') +
            ((r.warnings || []).length ? '<div class="hint warn">' + r.warnings.map(esc).join('<br>') + '</div>' : '') +
            (arcs.length ? table('', '<th>#</th><th>Arc</th><th>Wk</th><th>Miles</th><th>Long</th><th>Tpl</th>', arcs.map(function (a) {
              return '<tr><td class="m">' + esc(a.index + 1) + '</td><td>' + esc(a.name) + '</td><td>' + esc(a.weeks) + '</td><td>' + esc(a.run_miles_min === null ? '—' : a.run_miles_min + '–' + a.run_miles_max) + '</td><td>' + esc(a.long_run_miles === null || a.long_run_miles === undefined ? '—' : a.long_run_miles) + '</td><td>' + esc(a.templates) + '</td></tr>';
            }).join('')) : '');
        }
      },
      password: function (v) { return !!v.replace; },
      hint: 'Dry run parses and previews the arcs without writing. Apply creates the campaign (201); replace is destructive tier.',
      submit: function (v, reason, password) { return post(userPath(d.user.id, '/campaign/import'), body(v, false, reason, password)); },
      onSuccess: function (r) { return { message: 'Campaign imported · ' + r.name + ' · ' + plural((r.arcs || []).length, 'arc'), auditLookup: auditFor(d) }; }
    };
  }

  function productSpec(before) {
    var editing = !!before;
    var values = editing ? { id: before.id, kind: before.kind, credits: before.credits, entitlement_key: before.entitlement_key || '', display_name: before.display_name, sort_order: before.sort_order, active: before.active }
      : { id: '', kind: 'consumable', credits: 20, entitlement_key: '', display_name: '', sort_order: (state.products || []).length, active: true };
    return {
      title: editing ? 'EDIT PRODUCT' : 'ADD SKU', who: editing ? before.id : 'new StoreKit product', values: values,
      fields: function (v) {
        return fieldRow('Product id', 'StoreKit identifier · immutable', '<input class="field" data-field="id" value="' + esc(v.id) + '"' + (editing ? ' readonly' : ' placeholder="com.nickchua.fitnessapp.scan_100"') + ' autocapitalize="none" spellcheck="false">', true) +
          fieldRow('Kind', '', '<select class="field" data-field="kind">' + ['consumable', 'non_consumable', 'subscription'].map(function (k) { return opt(k, v.kind); }).join('') + '</select>') +
          fieldRow('Credits per purchase', '', '<input class="field" type="number" min="0" step="1" inputmode="numeric" data-field="credits" value="' + esc(v.credits) + '">') +
          fieldRow('Entitlement key', 'optional', '<select class="field" data-field="entitlement_key">' + opt('', v.entitlement_key, 'none') + ENTITLEMENT_KEYS.map(function (k) { return opt(k, v.entitlement_key); }).join('') + '</select>') +
          fieldRow('Display name', '', '<input class="field" data-field="display_name" value="' + esc(v.display_name) + '" maxlength="120">') +
          fieldRow('Sort order', '', '<input class="field" type="number" step="1" inputmode="numeric" data-field="sort_order" value="' + esc(v.sort_order) + '">') +
          checkbox('active', v.active, 'Active — visible on the paywall', editing && before.active);
      },
      diff: function (v) {
        if (!editing) return '';
        return diffRow('CREDITS', before.credits, v.credits) + diffRow('KIND', before.kind, v.kind) + diffRow('ENTITLEMENT_KEY', before.entitlement_key || '—', v.entitlement_key || '—') +
          diffRow('DISPLAY_NAME', before.display_name, v.display_name) + diffRow('ACTIVE', String(before.active), String(!!v.active), { down: before.active && !v.active }) + diffRow('SORT_ORDER', before.sort_order, v.sort_order);
      },
      validate: function (v) {
        if (!v.id || !v.id.trim()) return 'Product id is required.';
        if (!v.display_name || !v.display_name.trim()) return 'Display name is required.';
        if (v.credits === null || !Number.isInteger(Number(v.credits)) || Number(v.credits) < 0) return 'Credits must be a whole number ≥ 0.';
        if (v.sort_order === null || !Number.isInteger(Number(v.sort_order))) return 'Sort order must be a whole number.';
        return null;
      },
      password: function (v) { return !v.active; },  // any active=false body re-verifies the password (server rule)
      confirmLabel: function (v) { return editing ? (before.active && !v.active ? 'DEACTIVATE' : 'SAVE') : (v.active ? 'CREATE' : 'CREATE INACTIVE'); },
      hint: 'Logged as product.upsert. Deactivating is destructive tier (password); nothing is deleted.',
      submit: function (v, reason, password) {
        var b = stepUp({ id: v.id.trim(), kind: v.kind, credits: Number(v.credits), entitlement_key: v.entitlement_key || null, display_name: v.display_name.trim(), active: !!v.active, sort_order: Number(v.sort_order) }, reason, password);
        return editing ? api('PATCH', '/admin/products/' + encodeURIComponent(before.id), { body: b }) : post('/admin/products', b);
      },
      onSuccess: function (r) { return { message: (editing ? 'Product saved · ' : 'Product created · ') + r.id, auditLookup: { target_type: 'product', target_id: r.id } }; }
    };
  }

  // Actions that read the open hunter's detail; the rest are fleet / catalog scoped.
  var DETAIL_SPECS = {
    credits: creditsSpec, 'grant-unlimited': grantUnlimitedSpec, 'set-limits': setLimitsSpec, 'reset-limits': resetLimitsSpec,
    'soft-delete': softDeleteSpec, restore: restoreSpec, purge: purgeSpec, 'import': importSpec,
    'revoke-unlimited': function (d, el) {
      var row = (d.entitlements || []).filter(function (e) { return e.id === el.dataset.id; })[0];
      return row && revokeUnlimitedSpec(d, row);
    }
  };
  var FLEET_SPECS = {
    backfill: backfillSpec, sweep: sweepSpec, seed: seedSpec,
    'product-new': function () { return productSpec(null); },
    'product-edit': function (el) {
      var p = (state.products || []).filter(function (x) { return x.id === el.dataset.id; })[0];
      return p && productSpec(p);
    }
  };
  function openAction(act, el) {
    var spec = DETAIL_SPECS[act] ? (state.detail && DETAIL_SPECS[act](state.detail, el)) : FLEET_SPECS[act] && FLEET_SPECS[act](el);
    if (spec) openDrawer(spec);
  }

  // ── events (delegated; no inline handlers) ─────────────────────────────

  document.addEventListener('click', function (e) {
    var el = e.target.closest('[data-action]');
    if (!el) return;
    var a = el.dataset.action;
    if (a === 'nav') { e.preventDefault(); go(el.dataset.nav); return; }
    if (a === 'logout') { expireSession('Session ended.'); return; }
    if (a === 'retry') { onRoute(); return; }
    if (a === 'open-hunter') { go('hunters/' + encodeURIComponent(el.dataset.id)); return; }
    if (a === 'sort') {
      updateHunters(function (q) {
        q.order = (q.sort || 'last_active') === el.dataset.sort && (q.order || 'desc') === 'desc' ? 'asc' : 'desc';
        q.sort = el.dataset.sort;
      });
      return;
    }
    if (a === 'chip') {
      updateHunters(function (q) {
        if (!el.dataset.key) { delete q.deleted; delete q.unlimited; delete q.active_days; }
        else if (q[el.dataset.key] === el.dataset.value) delete q[el.dataset.key];
        else q[el.dataset.key] = el.dataset.value;
      });
      return;
    }
    if (a === 'page') {
      var r = parseHash(), q = pick(r.params, r.name === 'audit' ? AUDIT_KEYS : LIST_KEYS);
      q.offset = el.dataset.offset === '0' ? undefined : el.dataset.offset;
      go(r.name, q); return;
    }
    if (a === 'audit-toggle') { var x = $('#audit-x-' + el.dataset.idx); if (x) x.hidden = !x.hidden; return; }
    if (a === 'copy-id') {
      var id = el.dataset.id;
      (navigator.clipboard ? navigator.clipboard.writeText(id) : Promise.reject()).then(function () { toast('Copied ' + id); }, function () { toast(id); });
      return;
    }
    if (a === 'act') { openAction(el.dataset.act, el); return; }
    if (a === 'drawer-close') { closeDrawer(false); return; }
    if (a === 'drawer-confirm') { confirmDrawer(); return; }
    if (a === 'dr') {
      if (!drawer) return;
      readDrawerInputs();
      if (drawer.spec.onAction) drawer.spec.onAction(el.dataset.op, el, drawer.values);
      drawer.result = null; renderResult();
      renderFields(); updateDrawer(); return;
    }
    if (a === 'toast-close') { if (el.parentNode) el.parentNode.removeChild(el); }
  });

  // Discrete controls (radio / checkbox / select) report on `change`, text on
  // `input` — one run per edit whatever the browser fires.
  function onDrawerInput(e) {
    var t = e.target;
    if (!drawer || !drawerEl.contains(t) || (t.dataset.field === undefined && t.dataset.meta === undefined)) return;
    var discrete = t.type === 'radio' || t.type === 'checkbox' || t.tagName === 'SELECT';
    if (discrete !== (e.type === 'change')) return;
    readDrawerInputs();
    if (t.dataset.field !== undefined && drawer.result) { drawer.result = null; renderResult(); }   // a changed proposal invalidates a dry run
    if (drawer.spec.afterInput) drawer.spec.afterInput(drawer.values, $('.dr-fields', drawerEl));
    if (t.type === 'radio') renderFields();   // the mode switch swaps the field set
    updateDrawer();
  }
  document.addEventListener('input', onDrawerInput);
  document.addEventListener('change', onDrawerInput);

  document.addEventListener('submit', function (e) {
    if (e.target.id === 'login-form') { e.preventDefault(); login(e.target); return; }
    if (e.target.id === 'audit-filters') {
      e.preventDefault();
      var f = e.target, q = {};
      AUDIT_KEYS.forEach(function (k) { if (f[k] && f[k].value.trim()) q[k] = f[k].value.trim(); });
      go('audit', q);
    }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape' && e.key !== 'Enter') return;
    if (e.key === 'Escape' && drawer) { closeDrawer(false); return; }
    if (e.key === 'Enter' && e.target === $('#search')) { e.preventDefault(); clearTimeout(searchTimer); go('hunters', { q: e.target.value.trim() }); }
    if (e.key === 'Enter' && drawer && e.target.tagName === 'INPUT' && drawerEl.contains(e.target)) { e.preventDefault(); confirmDrawer(); }   // self-gated
    if (e.key === 'Enter' && e.target.matches && e.target.matches('tr.row[data-action]')) { e.preventDefault(); e.target.click(); }
  });
  $('#search').addEventListener('input', function (e) {
    clearTimeout(searchTimer);
    var v = e.target.value.trim();
    searchTimer = setTimeout(function () {
      var r = parseHash();
      if (r.name === 'hunters' && !r.id && (r.params.get('q') || '') !== v) updateHunters(function (q) { q.q = v; });
    }, 350);
  });

  window.addEventListener('hashchange', onRoute);
  window.addEventListener('beforeunload', function () { token = null; });

  // boot: no token yet → Login (the hash is kept so login lands on the same screen)
  showLogin();
})();
