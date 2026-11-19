'use strict';
/* Renders data/summary.json. Built with DOM APIs only (no innerHTML) so data can never inject markup. */
(() => {
  const $ = id => document.getElementById(id);
  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
  const SVG = 'http://www.w3.org/2000/svg';
  const svg = (tag, attrs) => { const n = document.createElementNS(SVG, tag); for (const k in attrs) n.setAttribute(k, attrs[k]); return n; };

  const pct = v => v == null ? '—' : (v >= 99.995 ? '100' : v.toFixed(v >= 99 ? 2 : 1)) + '%';
  const ago = ts => {
    const s = Math.max(0, Date.now() / 1000 - ts);
    if (s < 90) return 'just now';
    if (s < 3600) return Math.round(s / 60) + ' min ago';
    if (s < 86400) return Math.round(s / 3600) + ' h ago';
    return Math.round(s / 86400) + ' d ago';
  };
  const dur = s => { const m = Math.round(s / 60); if (m < 60) return m + ' min'; const h = Math.floor(m / 60); return h < 24 ? `${h} h ${m % 60} min` : `${Math.floor(h / 24)} d ${h % 24} h`; };
  const when = ts => new Date(ts * 1000).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });

  function stat(value, label, extra) { const s = el('div', 'stat' + (extra ? ' ' + extra : '')); s.append(el('b', null, value), el('span', null, label)); return s; }

  function chart(points) {
    const W = 600, H = 64, box = svg('svg', { class: 'chart', viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'none', role: 'img' });
    if (points.length < 2) { box.setAttribute('aria-label', 'Not enough data yet'); return box; }
    const t0 = points[0][0], t1 = points[points.length - 1][0], span = Math.max(1, t1 - t0);
    const ms = points.filter(p => p[2] && p[1] != null).map(p => p[1]);
    const max = Math.max(200, ...ms) * 1.15;
    const x = t => ((t - t0) / span) * W, y = v => H - (v / max) * (H - 4);
    let d = '', started = false;
    for (const [t, v, ok] of points) {
      if (ok && v != null) { d += (started ? 'L' : 'M') + x(t).toFixed(1) + ' ' + y(v).toFixed(1); started = true; }
      else started = false;  // break the line where checks failed
    }
    const okPts = points.filter(p => p[2] && p[1] != null);
    if (okPts.length > 1) {
      const area = `M${x(okPts[0][0]).toFixed(1)} ${H}` + okPts.map(p => `L${x(p[0]).toFixed(1)} ${y(p[1]).toFixed(1)}`).join('') + `L${x(okPts[okPts.length - 1][0]).toFixed(1)} ${H}Z`;
      box.append(svg('path', { class: 'area', d: area }));
    }
    box.append(svg('path', { class: 'ln', d }));
    for (const [t, , ok] of points) if (!ok) box.append(svg('rect', { class: 'fail', x: Math.max(0, x(t) - 2), y: 0, width: 4, height: H }));
    box.setAttribute('aria-label', `Response times over the last 24 hours, up to ${Math.round(Math.max(...ms, 0))} ms`);
    return box;
  }

  function siteCard(s) {
    const card = el('article', 'card');
    const head = el('div', 'card-head'), title = el('div');
    title.append(el('h3', null, s.name));
    const a = el('a', 'url', s.url.replace(/^https?:\/\//, '')); a.href = s.url; a.rel = 'noopener'; title.append(a);
    const state = s.ok == null ? 'unknown' : s.ok ? 'ok' : 'down';
    head.append(title, el('span', 'pill ' + state, state === 'ok' ? 'Operational' : state === 'down' ? 'Down' : 'No data'));
    card.append(head);

    const cert = s.last && s.last.cert_days;
    const stats = el('div', 'stats');
    stats.append(
      stat(pct(s.uptime.h24), 'Uptime 24 h'),
      stat(pct(s.uptime.d7), 'Uptime 7 days'),
      stat(pct(s.uptime.d30), 'Uptime 30 days', 'opt'),
      stat(s.avg_ms_24h == null ? '—' : s.avg_ms_24h + ' ms', 'Avg response', 'opt'),
      stat(cert == null ? '—' : cert + ' d', 'Certificate left', cert != null && cert <= 14 ? 'warn' : ''));
    card.append(stats, chart(s.spark || []));
    const foot = el('div', 'chart-foot'); foot.append(el('span', null, '24 hours ago'), el('span', null, 'now')); card.append(foot);
    if (state === 'down' && s.last) card.append(el('p', 'reason', `${s.last.error || 'Down'} · since ${when(s.since)}`));
    return card;
  }

  function render(d) {
    const texts = { ok: 'All systems operational', partial: 'Some systems are down', down: 'All systems are down', unknown: 'Waiting for the first check' };
    $('overallDot').className = 'dot ' + d.overall;
    $('overallText').textContent = texts[d.overall] || texts.unknown;
    $('updated').textContent = `Last checked ${ago(d.generated)} · ${when(d.generated)}`;
    $('interval').textContent = d.interval_minutes;
    $('sites').replaceChildren(...d.sites.map(siteCard));

    const list = $('incidents'); list.replaceChildren();
    for (const i of d.incidents) {
      const li = el('li'), left = el('div');
      left.append(el('b', null, i.site), document.createTextNode(' · ' + i.reason));
      const right = el('div', 'muted', i.end ? `${when(i.start)} · lasted ${dur(i.end - i.start)}` : `Since ${when(i.start)}`);
      li.append(left, right, el('span', 'tag ' + (i.end ? 'closed' : 'open'), i.end ? 'Resolved' : 'Ongoing'));
      list.append(li);
    }
    $('noIncidents').hidden = d.incidents.length > 0;
  }

  async function load() {
    try {
      const r = await fetch('data/summary.json?t=' + Date.now(), { cache: 'no-store' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      render(await r.json());
      $('error').hidden = true;
    } catch (e) {
      $('error').hidden = false;
      if ($('overallText').textContent === 'Loading status…') $('overallText').textContent = 'Status unavailable';
    }
  }
  $('retry').addEventListener('click', load);
  load();
  setInterval(() => { if (!document.hidden) load(); }, 60000);
})();
