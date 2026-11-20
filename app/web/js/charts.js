/* 轻量 SVG 图表：折线/面积、迷你走势、横向条形、环形仪表、热力图、血缘图 */
(function () {
  const NS = 'http://www.w3.org/2000/svg';

  function el(name, attrs = {}) {
    const node = document.createElementNS(NS, name);
    for (const [k, v] of Object.entries(attrs)) {
      if (v !== null && v !== undefined) node.setAttribute(k, v);
    }
    return node;
  }

  function css(name, fallback) {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name);
    return (v && v.trim()) || fallback;
  }

  function niceTicks(min, max, count = 4) {
    if (min === max) { min -= 1; max += 1; }
    const raw = (max - min) / count;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const norm = raw / mag;
    const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10) * mag;
    const lo = Math.floor(min / step) * step;
    const hi = Math.ceil(max / step) * step;
    const ticks = [];
    for (let v = lo; v <= hi + step / 2; v += step) ticks.push(+v.toFixed(10));
    return { ticks, lo, hi };
  }

  function fmt(v) {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    const abs = Math.abs(v);
    if (abs >= 10000) return (v / 1000).toFixed(1) + 'k';
    if (abs >= 1000) return Math.round(v).toLocaleString();
    if (abs >= 100) return v.toFixed(0);
    if (abs >= 10) return v.toFixed(1);
    return v.toFixed(abs < 1 ? 2 : 1);
  }

  /* ---------- 折线 / 面积图 ---------- */
  function line(container, opts) {
    container.innerHTML = '';
    const series = (opts.series || []).filter(s => s.points.some(p => p.value !== null));
    if (!series.length) {
      container.innerHTML = '<div class="chart-empty">暂无数据</div>';
      return;
    }
    const W = container.clientWidth || 640;
    const H = opts.height || 268;
    const pad = { t: 14, r: 16, b: 26, l: 46 };
    const labels = opts.labels || [];
    const all = series.flatMap(s => s.points.map(p => p.value)).filter(v => v !== null);
    const { ticks, lo, hi } = niceTicks(Math.min(...all), Math.max(...all), 4);
    const iw = Math.max(W - pad.l - pad.r, 10);
    const ih = Math.max(H - pad.t - pad.b, 10);
    const x = i => pad.l + (labels.length <= 1 ? iw / 2 : (i / (labels.length - 1)) * iw);
    const y = v => pad.t + ih - ((v - lo) / (hi - lo || 1)) * ih;

    const svg = el('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}` });
    const grid = css('--line', '#22314f');
    const muted = css('--muted', '#7d8fb3');

    ticks.forEach(t => {
      svg.appendChild(el('line', { x1: pad.l, x2: W - pad.r, y1: y(t), y2: y(t), stroke: grid, 'stroke-width': 1, 'stroke-dasharray': t === 0 ? '' : '3 5', opacity: .7 }));
      const label = el('text', { x: pad.l - 9, y: y(t) + 3.5, 'text-anchor': 'end', fill: muted, 'font-size': 10 });
      label.textContent = fmt(t);
      svg.appendChild(label);
    });

    if (opts.target !== null && opts.target !== undefined && opts.target >= lo && opts.target <= hi) {
      svg.appendChild(el('line', {
        x1: pad.l, x2: W - pad.r, y1: y(opts.target), y2: y(opts.target),
        stroke: css('--warn', '#ffc75c'), 'stroke-width': 1.4, 'stroke-dasharray': '6 4', opacity: .85
      }));
      const tl = el('text', { x: W - pad.r, y: y(opts.target) - 6, 'text-anchor': 'end', fill: css('--warn', '#ffc75c'), 'font-size': 10 });
      tl.textContent = '目标 ' + fmt(opts.target);
      svg.appendChild(tl);
    }

    const step = Math.ceil(labels.length / 8);
    labels.forEach((lab, i) => {
      if (i % step !== 0 && i !== labels.length - 1) return;
      const t = el('text', { x: x(i), y: H - 7, 'text-anchor': 'middle', fill: muted, 'font-size': 10 });
      t.textContent = String(lab).replace(/^\d{4}-/, '');
      svg.appendChild(t);
    });

    series.forEach((s, si) => {
      const color = s.color || [css('--accent', '#5b8dff'), css('--accent-2', '#7c5cff'), css('--ok', '#35d39a')][si % 3];
      const pts = s.points.map((p, i) => (p.value === null ? null : [x(i), y(p.value)])).filter(Boolean);
      if (!pts.length) return;
      const gid = 'grad-' + Math.random().toString(36).slice(2, 8);
      const grad = el('linearGradient', { id: gid, x1: 0, y1: 0, x2: 0, y2: 1 });
      grad.appendChild(el('stop', { offset: '0%', 'stop-color': color, 'stop-opacity': .30 }));
      grad.appendChild(el('stop', { offset: '100%', 'stop-color': color, 'stop-opacity': 0 }));
      const defs = el('defs');
      defs.appendChild(grad);
      svg.appendChild(defs);

      const d = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
      if (opts.area !== false) {
        svg.appendChild(el('path', {
          d: `${d} L ${pts[pts.length - 1][0].toFixed(1)} ${pad.t + ih} L ${pts[0][0].toFixed(1)} ${pad.t + ih} Z`,
          fill: `url(#${gid})`, stroke: 'none'
        }));
      }
      svg.appendChild(el('path', { d, fill: 'none', stroke: color, 'stroke-width': 2.2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
      const last = pts[pts.length - 1];
      svg.appendChild(el('circle', { cx: last[0], cy: last[1], r: 3.6, fill: color, stroke: css('--panel', '#131f36'), 'stroke-width': 2 }));

      pts.forEach((p, i) => {
        const dot = el('circle', { cx: p[0], cy: p[1], r: 9, fill: 'transparent', style: 'cursor:pointer' });
        const tip = el('title');
        const val = s.points.filter(q => q.value !== null)[i];
        tip.textContent = `${labels[i] || ''} · ${fmt(val.value)}${opts.unit || ''}`;
        dot.appendChild(tip);
        svg.appendChild(dot);
      });
    });

    if (series.length > 1) {
      let lx = pad.l;
      series.forEach((s, si) => {
        const color = s.color || [css('--accent'), css('--accent-2'), css('--ok')][si % 3];
        svg.appendChild(el('rect', { x: lx, y: 2, width: 9, height: 3, rx: 2, fill: color }));
        const t = el('text', { x: lx + 13, y: 6.5, fill: muted, 'font-size': 10 });
        t.textContent = s.label || '';
        svg.appendChild(t);
        lx += 22 + (s.label || '').length * 6;
      });
    }

    container.appendChild(svg);
  }

  /* ---------- 迷你走势 ---------- */
  function spark(container, points, opts = {}) {
    container.innerHTML = '';
    const vals = points.filter(p => p !== null && p !== undefined);
    if (vals.length < 2) return;
    const W = container.clientWidth || 180;
    const H = opts.height || 34;
    const min = Math.min(...vals), max = Math.max(...vals);
    const color = opts.color || css('--accent', '#5b8dff');
    const x = i => (i / (points.length - 1)) * W;
    const y = v => H - 3 - ((v - min) / (max - min || 1)) * (H - 6);
    const svg = el('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}` });
    const d = points.map((v, i) => (v === null ? null : (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1))).filter(Boolean).join(' ');
    const gid = 'sp-' + Math.random().toString(36).slice(2, 8);
    const grad = el('linearGradient', { id: gid, x1: 0, y1: 0, x2: 0, y2: 1 });
    grad.appendChild(el('stop', { offset: '0%', 'stop-color': color, 'stop-opacity': .32 }));
    grad.appendChild(el('stop', { offset: '100%', 'stop-color': color, 'stop-opacity': 0 }));
    const defs = el('defs'); defs.appendChild(grad); svg.appendChild(defs);
    svg.appendChild(el('path', { d: `${d} L ${W} ${H} L 0 ${H} Z`, fill: `url(#${gid})` }));
    svg.appendChild(el('path', { d, fill: 'none', stroke: color, 'stroke-width': 1.7, 'stroke-linejoin': 'round' }));
    container.appendChild(svg);
  }

  /* ---------- 环形仪表 ---------- */
  function gauge(container, value, max, opts = {}) {
    container.innerHTML = '';
    const size = opts.size || 118;
    const stroke = opts.stroke || 9;
    const r = (size - stroke) / 2 - 2;
    const cx = size / 2, cy = size / 2;
    const pct = Math.max(0, Math.min(1, (value || 0) / (max || 100)));
    const color = opts.color || (pct >= .85 ? css('--ok', '#35d39a') : pct >= .6 ? css('--warn', '#ffc75c') : css('--bad', '#ff6b81'));
    const svg = el('svg', { width: size, height: size, viewBox: `0 0 ${size} ${size}` });
    svg.appendChild(el('circle', { cx, cy, r, fill: 'none', stroke: css('--line', '#22314f'), 'stroke-width': stroke, opacity: .65 }));
    const c = 2 * Math.PI * r;
    const arc = el('circle', {
      cx, cy, r, fill: 'none', stroke: color, 'stroke-width': stroke,
      'stroke-linecap': 'round', 'stroke-dasharray': `${c * pct} ${c}`,
      transform: `rotate(-90 ${cx} ${cy})`
    });
    svg.appendChild(arc);
    container.appendChild(svg);
    const label = document.createElement('div');
    label.className = 'gauge-val';
    label.innerHTML = `${value === null || value === undefined ? '—' : value}<small>${opts.label || ''}</small>`;
    container.appendChild(label);
  }

  /* ---------- 横向条形 ---------- */
  function bars(container, items, opts = {}) {
    container.innerHTML = '';
    if (!items.length) { container.innerHTML = '<div class="empty">暂无数据</div>'; return; }
    const max = Math.max(...items.map(i => i.value || 0), 1);
    items.forEach(item => {
      const row = document.createElement('div');
      row.className = 'bd-row';
      const left = document.createElement('div');
      left.innerHTML = `<div>${item.member}</div>
        <div class="bd-bar"><i style="width:${Math.max(2, ((item.value || 0) / max) * 100)}%;background:${opts.color || ''}"></i></div>`;
      const right = document.createElement('div');
      right.className = 'bd-val';
      right.textContent = item.value === null ? '—' : item.value;
      row.append(left, right);
      container.appendChild(row);
      if (opts.gap !== false) row.style.marginBottom = '10px';
    });
  }

  /* ---------- 血缘图（分层布局） ---------- */
  function lineage(container, data, opts = {}) {
    container.innerHTML = '';
    const nodes = data.nodes || [];
    if (!nodes.length) { container.innerHTML = '<div class="empty">无血缘数据</div>'; return; }
    const byId = new Map(nodes.map(n => [n.id, n]));
    // 层级 = 到最底层依赖的最长路径，保证依赖在左、派生在右
    const depth = new Map();
    const resolve = (id, guard = 0) => {
      if (depth.has(id)) return depth.get(id);
      if (guard > 24) return 0;
      const deps = (byId.get(id)?.deps || []).filter(d => byId.has(d));
      const level = deps.length ? 1 + Math.max(...deps.map(d => resolve(d, guard + 1))) : 0;
      depth.set(id, level);
      return level;
    };
    nodes.forEach(n => resolve(n.id));
    const levels = [];
    [...depth.entries()].forEach(([id, d]) => {
      levels[d] = levels[d] || [];
      levels[d].push(id);
    });
    const maxDepth = Math.max(...depth.values());
    const colW = 186, nodeH = 42, gapY = 12, padX = 24, padY = 18;
    let maxRows = 0;
    levels.forEach(l => { if (l) maxRows = Math.max(maxRows, l.length); });
    const W = padX * 2 + (maxDepth + 1) * colW;
    const H = padY * 2 + maxRows * (nodeH + gapY);
    const svg = el('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}` });
    const pos = new Map();
    levels.forEach((ids, d) => {
      if (!ids) return;
      ids.sort();
      const totalH = ids.length * (nodeH + gapY) - gapY;
      const startY = padY + (H - padY * 2 - totalH) / 2;
      ids.forEach((id, i) => {
        pos.set(id, { x: padX + d * colW, y: startY + i * (nodeH + gapY) });
      });
    });

    (data.edges || []).forEach(e => {
      const a = pos.get(e.from), b = pos.get(e.to);
      if (!a || !b) return;
      const x1 = a.x + colW - 26, y1 = a.y + nodeH / 2;
      const x2 = b.x, y2 = b.y + nodeH / 2;
      const mx = (x1 + x2) / 2;
      svg.appendChild(el('path', {
        d: `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2 - 5} ${y2}`,
        fill: 'none', stroke: css('--line', '#22314f'), 'stroke-width': 1.4, opacity: .95
      }));
      svg.appendChild(el('path', {
        d: `M ${x2 - 4} ${y2} l -6 -3.5 l 0 7 z`, fill: css('--line', '#22314f')
      }));
    });

    nodes.forEach(n => {
      const p = pos.get(n.id);
      if (!p) return;
      const g = el('g', { class: 'lg-node', style: 'cursor:pointer' });
      const isIndicator = n.indicator;
      const fill = isIndicator ? css('--accent-2', '#7c5cff')
        : n.type === 'atomic' ? css('--accent', '#5b8dff')
          : n.type === 'pair' ? css('--warn', '#ffc75c')
            : n.type === 'composite' ? css('--ok', '#35d39a') : css('--panel-2', '#17253f');
      const isSolid = isIndicator || n.type === 'atomic' || n.type === 'pair' || n.type === 'composite';
      g.appendChild(el('rect', {
        x: p.x, y: p.y, width: colW - 26, height: nodeH, rx: 9,
        fill: isSolid ? fill : css('--panel-2', '#17253f'),
        'fill-opacity': isSolid ? .16 : 1,
        stroke: isSolid ? fill : css('--line', '#22314f'),
        'stroke-width': 1.2
      }));
      const label = el('text', { x: p.x + 11, y: p.y + 17, fill: css('--fg', '#e9eefb'), 'font-size': 11.5, 'font-weight': 600 });
      label.textContent = n.label.length > 11 ? n.label.slice(0, 11) + '…' : n.label;
      g.appendChild(label);
      const sub = el('text', { x: p.x + 11, y: p.y + 31, fill: css('--muted', '#7d8fb3'), 'font-size': 9.5 });
      sub.textContent = `${n.type}${n.unit ? ' · ' + n.unit : ''}`;
      g.appendChild(sub);
      const tip = el('title');
      tip.textContent = `${n.label} (${n.id})`;
      g.appendChild(tip);
      g.addEventListener('click', () => { if (opts.onSelect) opts.onSelect(n.id); });
      svg.appendChild(g);
    });
    container.appendChild(svg);
  }

  /* ---------- 热力图 ---------- */
  function heatmap(container, labels, matrix, opts = {}) {
    container.innerHTML = '';
    if (!labels.length) { container.innerHTML = '<div class="empty">数据不足，无法计算相关性</div>'; return; }
    const table = document.createElement('table');
    const head = document.createElement('tr');
    head.appendChild(document.createElement('th'));
    labels.forEach(l => {
      const th = document.createElement('th');
      th.textContent = l;
      head.appendChild(th);
    });
    table.appendChild(head);
    matrix.forEach((row, i) => {
      const tr = document.createElement('tr');
      const th = document.createElement('th');
      th.className = 'row-h';
      th.textContent = labels[i];
      tr.appendChild(th);
      row.forEach((v, j) => {
        const td = document.createElement('td');
        td.textContent = v === null ? '—' : v.toFixed(2);
        if (v !== null) {
          const pos = v > 0;
          const a = Math.min(Math.abs(v), 1) * .72;
          td.style.background = pos ? `rgba(91,141,255,${a})` : `rgba(255,107,129,${a})`;
          td.style.color = Math.abs(v) > .55 ? '#fff' : css('--fg-dim', '#a8b7d4');
        }
        td.title = `${labels[i]} × ${labels[j]} = ${v}`;
        tr.appendChild(td);
      });
      table.appendChild(tr);
    });
    container.appendChild(table);
  }

  window.Charts = { line, spark, gauge, bars, lineage, heatmap, fmt, css };
})();
