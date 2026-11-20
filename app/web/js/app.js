/* RDE-Onto 前端应用：视图路由、数据获取、渲染 */
(function () {
  const state = {
    view: 'dashboard',
    granularity: 'week',
    periods: 12,
    team: '',
    overview: null,
    ontology: null,
    metrics: [],
    activeMetric: null,
    trendMetric: 'lead_time_hours',
    lineageRoot: null,
    factType: '',
  };

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = Charts.fmt;

  async function api(path, opts) {
    const res = await fetch(path, opts);
    const ct = res.headers.get('content-type') || '';
    if (!res.ok) {
      const body = ct.includes('json') ? await res.json() : { error: await res.text() };
      throw new Error(body.error || res.statusText);
    }
    return ct.includes('json') ? res.json() : res.text();
  }

  function toast(msg, isError) {
    const node = $('#toast');
    node.textContent = msg;
    node.className = 'toast show' + (isError ? ' error' : '');
    clearTimeout(node._t);
    node._t = setTimeout(() => { node.className = 'toast'; }, 3200);
  }

  function deltaClass(metric) {
    if (metric.delta === null || metric.delta === undefined || metric.delta === 0) return '';
    const worse = (metric.delta > 0) !== (metric.direction === 'up');
    return worse ? 'bad' : 'good';
  }

  function deltaText(metric) {
    if (metric.delta === null || metric.delta === undefined) return '环比 —';
    const arrow = metric.delta > 0 ? '▲' : metric.delta < 0 ? '▼' : '—';
    return `环比 ${arrow} ${Math.abs(metric.delta).toFixed(1)}%`;
  }

  function componentCount(metricId) {
    const def = (state.ontology?.metrics || []).find(m => m.id === metricId);
    const n = (def?.scoring?.components || []).length;
    return n || (def?.deps || []).length || '多';
  }

  function statusPill(metric) {
    const label = metric.status === 'ok' ? '达标' : metric.status === 'off' ? '未达标' : '无数据';
    return `<span class="pill ${metric.status}">${label}</span>`;
  }

  /* ================= 总览 ================= */
  async function renderDashboard() {
    const params = new URLSearchParams({ granularity: state.granularity, periods: state.periods });
    if (state.team) params.set('team', state.team);
    const data = await api('/api/overview?' + params);
    state.overview = data;

    const ind = data.indicator;
    const hero = $('#hero');
    if (ind) {
      const pct = ind.value === null ? 0 : Math.max(0, Math.min(100, ind.value));
      const okCount = data.kpis.filter(k => k.status === 'ok').length;
      const offCount = data.kpis.filter(k => k.status === 'off').length;
      hero.innerHTML = `
        <div class="hero-score">
          <div class="gauge" id="hero-gauge"></div>
          <div class="hero-copy">
            <h2>${esc(ind.label)}</h2>
            <p>由 ${componentCount(ind.id)} 项基础指标按权重归一化合成，权重与目标值均定义在本体中。</p>
            <div class="hero-meta">
              <div><strong>${okCount}</strong>达标指标</div>
              <div><strong>${offCount}</strong>待改进</div>
              <div><strong>${data.coverage.facts}</strong>窗口内事实</div>
            </div>
          </div>
        </div>
        <div class="hero-spark"><div id="hero-chart"></div></div>`;
      Charts.gauge($('#hero-gauge'), ind.value === null ? null : Number(pct.toFixed(1)), 100, { label: ind.unit || '分' });
      Charts.line($('#hero-chart'), {
        labels: ind.series.map(p => p.bucket),
        series: [{ label: ind.label, points: ind.series }],
        height: 150, unit: ind.unit, area: true
      });
    }

    const grid = $('#kpi-grid');
    grid.innerHTML = '';
    data.kpis.filter(k => !k.indicator).forEach(metric => {
      const card = document.createElement('div');
      card.className = 'kpi';
      card.innerHTML = `
        <div class="kpi-top">
          <div class="kpi-label">${esc(metric.label)}</div>
          ${statusPill(metric)}
        </div>
        <div class="kpi-val">${metric.value === null ? '—' : fmt(metric.value)}<span>${esc(metric.unit)}</span></div>
        <div class="spark" data-spark></div>
        <div class="kpi-foot">
          <span class="delta ${deltaClass(metric)}">${deltaText(metric)}</span>
          <span>目标 ${metric.target ?? '—'}</span>
        </div>`;
      grid.appendChild(card);
      Charts.spark($('[data-spark]', card), metric.series.map(p => p.value), {
        color: metric.status === 'off' ? Charts.css('--bad', '#ff6b81') : Charts.css('--accent', '#5b8dff')
      });
      card.addEventListener('click', () => openMetric(metric.id));
    });

    const chips = $('#trend-chips');
    const preferred = ['lead_time_hours', 'deploy_frequency', 'change_failure_rate', 'mttr_minutes',
      'cycle_time_hours', 'ci_success_rate', 'throughput_points', 'sprint_completion_rate'];
    const available = preferred.filter(id => data.metrics[id]);
    if (!available.includes(state.trendMetric)) state.trendMetric = available[0];
    chips.innerHTML = available.map(id =>
      `<button class="ghost-btn ${id === state.trendMetric ? 'active' : ''}" data-m="${id}"
        style="${id === state.trendMetric ? 'border-color:var(--accent);color:var(--fg)' : ''}">${esc(data.metrics[id].label)}</button>`
    ).join('');
    $$('[data-m]', chips).forEach(b => b.addEventListener('click', () => {
      state.trendMetric = b.dataset.m;
      renderDashboard();
    }));
    const tm = data.metrics[state.trendMetric];
    if (tm) {
      Charts.line($('#trend-chart'), {
        labels: tm.series.map(p => p.bucket),
        series: [{ label: tm.label, points: tm.series }],
        target: tm.target, unit: tm.unit, height: 268,
        color: tm.status === 'off' ? Charts.css('--bad') : Charts.css('--accent')
      });
    }

    Charts.bars($('#team-bars'), data.teams.map(t => ({ member: t.member, value: t.value })));

    $('#insights-list').innerHTML = data.insights.length
      ? data.insights.map(i => `<div class="insight ${i.level}"><strong>${esc(i.title)}</strong><span>${esc(i.detail)}</span></div>`).join('')
      : '<div class="empty">本期各项指标均在目标范围内</div>';

    const mx = $('#matrix');
    mx.innerHTML = data.kpis.filter(k => !k.indicator && k.value !== null && k.target).map(k => {
      const ratio = Math.max(0, Math.min(1, k.direction === 'down'
        ? (k.target / (k.value || 1e-9)) : (k.value / k.target)));
      return `<div class="mx" title="${esc(k.description)}">
        <div class="mx-l">${esc(k.label)}</div>
        <div class="mx-v">${fmt(k.value)}<span style="font-size:10px;color:var(--muted)"> / ${k.target}</span></div>
        <div class="mx-bar"><i class="${k.status === 'off' ? 'off' : ''}" style="width:${(ratio * 100).toFixed(0)}%"></i></div>
      </div>`;
    }).join('') || '<div class="empty">无可用目标</div>';

    $('#foot-meta').textContent = `窗口 ${data.window.start} ~ ${data.window.end} · 事实 ${data.counts.facts} 条 · 实体 ${data.counts.entities} 个`;
  }

  /* ================= 指标字典 ================= */
  async function renderMetrics() {
    if (!state.metrics.length) {
      const data = await api('/api/metrics');
      state.metrics = data.metrics;
      const params = new URLSearchParams({ granularity: state.granularity, periods: state.periods });
      const overview = state.overview || await api('/api/overview?' + params);
      state.metricValues = overview.metrics;
    }
    const kw = ($('#metric-search').value || '').trim().toLowerCase();
    const rows = state.metrics.filter(m => !kw
      || m.label.toLowerCase().includes(kw) || m.id.includes(kw)
      || (m.owner || '').toLowerCase().includes(kw) || (m.description || '').toLowerCase().includes(kw));

    $('#metric-table').innerHTML = rows.map(m => {
      const v = state.metricValues?.[m.id];
      return `<div class="mt-row ${state.activeMetric === m.id ? 'active' : ''}" data-id="${m.id}">
        <div class="mt-name"><strong>${esc(m.label)}${m.indicator ? ' ★' : ''}</strong>
          <small>${esc(m.id)}</small></div>
        <div class="mt-val">${v?.value ?? '—'}<span>${esc(m.unit)}</span></div>
        <div class="type-tag ${m.type}">${({ atomic: '原子', derived: '派生', composite: '复合', pair: '配对' })[m.type] || m.type}</div>
        <div>${v ? statusPill(v) : ''}</div>
      </div>`;
    }).join('') || '<div class="empty">无匹配指标</div>';

    $$('#metric-table .mt-row').forEach(row => row.addEventListener('click', () => openMetric(row.dataset.id)));
    if (state.activeMetric) renderMetricDetail(state.activeMetric);
  }

  async function openMetric(id) {
    state.activeMetric = id;
    switchView('metrics');
    await renderMetrics();
    renderMetricDetail(id);
    $('#metric-detail').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  async function renderMetricDetail(id) {
    const box = $('#metric-detail');
    box.innerHTML = '<div class="empty">加载中…</div>';
    const params = new URLSearchParams({ granularity: state.granularity, periods: state.periods });
    const m = await api(`/api/metrics/${id}?` + params);
    const def = m.definition || {};
    const bd = m.breakdown || {};
    const bdBlocks = Object.entries(bd).map(([dim, items]) => `
      <div class="section-label">${({ team: '按团队', repo: '按代码库', worktype: '按工作类型' })[dim] || dim}</div>
      <div class="bd-list" data-bd="${dim}"></div>`).join('');

    box.innerHTML = `
      <div class="detail-head">
        <div>
          <h2>${esc(m.label)}</h2>
          <small style="color:var(--muted);font-family:var(--mono);font-size:11px">${esc(m.id)}</small>
        </div>
        ${statusPill(m)}
      </div>
      <p class="detail-desc">${esc(m.description)}</p>
      <div class="kv">
        <dt>当前值</dt><dd><strong style="font-size:16px">${m.value ?? '—'}</strong> ${esc(m.unit)}</dd>
        <dt>目标</dt><dd>${m.target ?? '—'} ${esc(m.unit)} <span class="hint">(${m.direction === 'up' ? '越高越好' : '越低越好'})</span></dd>
        <dt>达成率</dt><dd>${m.attainment === null ? '—' : (m.attainment * 100).toFixed(0) + '%'}</dd>
        <dt>环比</dt><dd class="delta ${deltaClass(m)}">${deltaText(m)}</dd>
        <dt>口径</dt><dd><code>${esc(m.formula || '—')}</code></dd>
        <dt>负责人</dt><dd>${esc(m.owner || '—')}</dd>
        <dt>类型</dt><dd>${({ atomic: '原子指标（直接聚合事实）', derived: '派生指标（公式计算）', composite: '复合指标（加权评分）', pair: '配对指标（双事实 join）' })[m.type] || m.type}</dd>
        ${m.deps?.length ? `<dt>依赖</dt><dd>${m.deps.map(d => `<code>${esc(d)}</code>`).join(' ')}</dd>` : ''}
        ${m.dependents?.length ? `<dt>被引用</dt><dd>${m.dependents.map(d => `<code>${esc(d)}</code>`).join(' ')}</dd>` : ''}
      </div>
      <div class="section-label">趋势</div>
      <div id="detail-chart" style="height:190px"></div>
      ${bdBlocks}`;

    Charts.line($('#detail-chart'), {
      labels: m.series.map(p => p.bucket),
      series: [{ label: m.label, points: m.series }],
      target: m.target, unit: m.unit, height: 190,
      color: m.status === 'off' ? Charts.css('--bad') : Charts.css('--accent')
    });
    Object.entries(bd).forEach(([dim, items]) => {
      const holder = $(`[data-bd="${dim}"]`, box);
      if (holder) Charts.bars(holder, items.slice(0, 8));
    });
  }

  /* ================= 血缘 ================= */
  async function renderLineage() {
    if (!state.ontology) state.ontology = await api('/api/ontology');
    const select = $('#lineage-root');
    if (!select.options.length) {
      const indicators = state.ontology.metrics.filter(m => m.indicator);
      const others = state.ontology.metrics.filter(m => !m.indicator && !m.hidden);
      select.innerHTML = [
        ...indicators.map(m => `<option value="${m.id}">★ ${esc(m.label)}</option>`),
        ...others.map(m => `<option value="${m.id}">${esc(m.label)}</option>`)
      ].join('');
      state.lineageRoot = indicators[0]?.id || others[0]?.id;
      select.value = state.lineageRoot;
      select.addEventListener('change', () => {
        state.lineageRoot = select.value;
        renderLineage();
      });
    }
    const data = await api('/api/lineage?metric=' + encodeURIComponent(state.lineageRoot));
    Charts.lineage($('#lineage-canvas'), data, { onSelect: id => openMetric(id) });
  }

  /* ================= 本体 ================= */
  async function renderOntology() {
    if (!state.ontology) state.ontology = await api('/api/ontology');
    const o = state.ontology;
    const s = o.stats;
    $('#onto-stats').innerHTML = [
      ['类', s.classes], ['关系', s.relations], ['事实类型', s.factTypes],
      ['指标总数', s.metrics], ['原子指标', s.atomicMetrics],
      ['派生指标', s.derivedMetrics], ['复合指标', s.compositeMetrics],
    ].map(([k, v]) => `<div class="stat"><b>${v}</b><span>${k}</span></div>`).join('');

    const byParent = new Map();
    o.classes.forEach(c => {
      const p = c.parent || '__root__';
      if (!byParent.has(p)) byParent.set(p, []);
      byParent.get(p).push(c);
    });
    const renderTree = (parentId, depth) => {
      const kids = byParent.get(parentId) || [];
      if (!kids.length) return '';
      return kids.map(c => `
        <div>
          <div class="tree-node" data-cls="${c.id}" style="padding-left:${depth * 2}px">
            <span class="ns">${c.id.split(':')[0]}</span>
            <span>${esc(c.label)}</span>
          </div>
          ${renderTree(c.id, depth + 1)}
        </div>`).join('');
    };
    $('#class-tree').innerHTML = renderTree('__root__', 0);

    $$('#class-tree .tree-node').forEach(node => node.addEventListener('click', () => {
      $$('#class-tree .tree-node').forEach(n => n.classList.remove('active'));
      node.classList.add('active');
      showClass(node.dataset.cls);
    }));

    $('#relation-list').innerHTML = o.relations.map(r => `
      <div class="rel-item" data-rel="${r.id}">
        <strong>${esc(r.id)}</strong> <span style="color:var(--fg-dim)">${esc(r.label)}</span>
        ${r.transitive ? '<span class="tag trans">传递</span>' : ''}
        ${r.inverse ? `<span class="tag inv">逆 ${esc(r.inverse)}</span>` : ''}
        <small>${esc(r.domain)} → ${esc(r.range)}</small>
      </div>`).join('');

    $('#facttype-list').innerHTML = o.factTypes.map(f => `
      <div class="fact-item" data-ft="${f.id}">
        <strong>${esc(f.id)}</strong> <span style="color:var(--fg-dim)">${esc(f.label)}</span>
        <small>主体 ${esc(f.subject)} · 时间 ${esc(f.timeField)} ·
          度量 ${f.measures.length ? f.measures.join(', ') : '—'}</small>
      </div>`).join('');

    $$('.fact-item').forEach(item => item.addEventListener('click', () => {
      const f = o.factTypes.find(x => x.id === item.dataset.ft);
      const users = o.metrics.filter(m => m.fact === f.id);
      $('#onto-detail').innerHTML = `
        <div class="detail-head"><h2>${esc(f.label)}</h2>
          <span class="pill ok">${esc(f.id)}</span></div>
        <p class="detail-desc">${esc(f.description)}</p>
        <div class="kv">
          <dt>主体类</dt><dd><code>${esc(f.subject)}</code></dd>
          <dt>时间字段</dt><dd><code>${esc(f.timeField)}</code></dd>
          <dt>度量</dt><dd>${f.measures.map(m => `<code>${esc(m)}</code>`).join(' ') || '—'}</dd>
          <dt>字段</dt><dd>${f.fields.map(m => `<code>${esc(m)}</code>`).join(' ') || '—'}</dd>
        </div>
        <div class="section-label">由该事实驱动的指标</div>
        <div class="bd-list">${users.map(m => `<div class="bd-row"><div>${esc(m.label)}</div>
          <div class="bd-val"><code style="font-size:10px">${esc(m.type)}</code></div></div>`).join('') || '<div class="hint">暂无</div>'}</div>`;
    }));

    showClass('dev:WorkItem');
    const first = $('#class-tree .tree-node');
    if (first) first.classList.add('active');
  }

  function showClass(classId) {
    const o = state.ontology;
    const c = o.classes.find(x => x.id === classId);
    if (!c) return;
    const children = o.classes.filter(x => x.parent === classId);
    const rels = o.relations.filter(r => r.domain === classId || r.range === classId);
    const facts = o.factTypes.filter(f => f.subject === classId);
    const metrics = o.metrics.filter(m => m.filter && JSON.stringify(m.filter).includes(classId));
    $('#onto-detail').innerHTML = `
      <div class="detail-head"><h2>${esc(c.label)}</h2><span class="pill ok">${esc(c.id)}</span></div>
      <p class="detail-desc">${esc(c.description)}</p>
      <div class="kv">
        <dt>父类</dt><dd>${c.parent ? `<code>${esc(c.parent)}</code>` : '<span class="hint">顶层类</span>'}</dd>
        <dt>命名空间</dt><dd><code>${esc(c.namespace)}</code> · ${esc(o.namespaces[c.namespace] || '')}</dd>
        <dt>继承深度</dt><dd>${c.depth}</dd>
        <dt>直接子类</dt><dd>${children.map(x => `<code>${esc(x.label)}</code>`).join(' ') || '—'}</dd>
      </div>
      <div class="section-label">参与的关系（${rels.length}）</div>
      <div class="bd-list">${rels.map(r => `<div class="bd-row">
        <div><code style="font-size:11px">${esc(r.id)}</code> ${esc(r.label)}</div>
        <div class="bd-val"><code style="font-size:10px">${esc(r.domain === classId ? '→ ' + r.range : r.domain + ' →')}</code></div>
      </div>`).join('') || '<div class="hint">无</div>'}</div>
      ${facts.length ? `<div class="section-label">相关事实类型</div>
        <div class="bd-list">${facts.map(f => `<div class="bd-row"><div>${esc(f.label)}</div>
          <div class="bd-val"><code style="font-size:10px">${esc(f.id)}</code></div></div>`).join('')}</div>` : ''}
      ${metrics.length ? `<div class="section-label">按此类归属推理的指标</div>
        <div class="bd-list">${metrics.map(m => `<div class="bd-row"><div>${esc(m.label)}</div>
          <div class="bd-val"><code style="font-size:10px">${esc(m.id)}</code></div></div>`).join('')}</div>` : ''}`;
  }

  /* ================= 数据接入 ================= */
  async function renderData() {
    const [facts, quality, settings] = await Promise.all([
      api('/api/facts?limit=60' + (state.factType ? '&factType=' + state.factType : '')),
      api('/api/quality'),
      api('/api/settings'),
    ]);

    $('#data-stats').innerHTML = [
      ['事实总数', settings.counts.facts], ['实体数', settings.counts.entities],
      ['关系数', settings.counts.relations], ['数据质量分', quality.score],
      ['质量问题', quality.issueCount],
    ].map(([k, v]) => `<div class="stat"><b>${v}</b><span>${k}</span></div>`).join('');

    $('#quality-score').textContent = `得分 ${quality.score} · ${quality.issueCount} 个问题`;
    const byType = Object.entries(quality.byType || {});
    $('#quality-body').innerHTML = `
      <div class="bd-list" style="margin-bottom:12px">
        ${byType.map(([k, v]) => `<div class="bd-row"><div>${esc(k)}</div><div class="bd-val">${v}</div></div>`).join('') || '<div class="hint">未发现质量问题</div>'}
      </div>
      <div style="max-height:220px;overflow:auto">
        ${quality.issues.slice(0, 30).map(i => `<div class="q-issue">
          <span class="q-sev ${i.severity}">${({ high: '高', medium: '中', low: '低' })[i.severity]}</span>
          <div><strong style="font-size:11.5px">${esc(i.type)}</strong>
            <div class="hint">${esc(i.subject)} · ${esc(i.detail)}</div></div>
        </div>`).join('') || ''}
      </div>`;

    const filter = $('#fact-type-filter');
    if (!filter.options.length) {
      filter.innerHTML = '<option value="">全部事实类型</option>' + facts.factTypes
        .map(f => `<option value="${f.id}">${esc(f.label)} (${f.count})</option>`).join('');
      filter.value = state.factType;
      filter.addEventListener('change', () => { state.factType = filter.value; renderData(); });
    }
    const tpl = $('#template-select');
    if (!tpl.options.length) {
      tpl.innerHTML = facts.factTypes.map(f => `<option value="${f.id}">${esc(f.label)} · ${f.id}</option>`).join('');
    }

    $('#fact-table').innerHTML = `
      <table><thead><tr><th>事实类型</th><th>主体</th><th>主体类</th><th>时间</th><th>度量 / 字段</th><th>来源</th></tr></thead>
      <tbody>${facts.rows.map(r => `<tr>
        <td>${esc(r.fact_type)}</td>
        <td>${esc(r.subject_id)}</td>
        <td>${esc(r.subject_class)}</td>
        <td>${esc(r.occurred_at)}</td>
        <td>${esc(Object.entries(r.measures).map(([k, v]) => `${k}=${v}`).join(' '))}
            ${esc(Object.entries(r.fields).slice(0, 3).map(([k, v]) => `${k}=${v}`).join(' '))}</td>
        <td>${esc(r.source)}</td>
      </tr>`).join('')}</tbody></table>
      <div class="hint" style="padding:8px 10px">显示 ${facts.rows.length} / ${facts.total} 条</div>`;
  }

  async function handleFile(file) {
    if (!file) return;
    const buffer = await file.arrayBuffer();
    let binary = '';
    const bytes = new Uint8Array(buffer);
    for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
    const result = await api('/api/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        filename: file.name,
        content: btoa(binary),
        factType: $('#template-select').value || null,
      }),
    });
    const box = $('#import-result');
    box.innerHTML = `
      <div class="insight ${result.rejected ? 'warning' : 'info'}" style="margin-top:14px">
        <strong>导入完成：${result.filename}</strong>
        <span>读取 ${result.rows} 行，入库 ${result.inserted} 行，拒绝 ${result.rejected} 行。</span>
      </div>
      ${result.errors.length ? `<div style="max-height:150px;overflow:auto;margin-top:8px">
        ${result.errors.map(e => `<div class="hint">第 ${e.line} 行：${esc(e.error)}</div>`).join('')}</div>` : ''}`;
    toast(result.rejected ? `入库 ${result.inserted} 行，${result.rejected} 行被拒绝` : `成功入库 ${result.inserted} 行`, !!result.rejected);
    state.metrics = [];
    renderData();
  }

  /* ================= 分析预测 ================= */
  async function renderInsights() {
    const params = new URLSearchParams({ granularity: state.granularity, periods: state.periods });
    const overview = state.overview || await api('/api/overview?' + params);
    state.overview = overview;

    const advice = [];
    const off = overview.kpis.filter(k => k.status === 'off');
    const templates = {
      lead_time_hours: '缩短前置时间：拆分大需求、减少评审排队，优先处理在制品最久的工作项。',
      cycle_time_hours: '压缩需求周期：明确验收标准，减少返工与跨团队等待。',
      change_failure_rate: '降低变更失败：补齐自动化回归与灰度发布，缩小单次变更规模。',
      mttr_minutes: '缩短恢复时间：完善告警分级与值班手册，预置回滚脚本。',
      defect_escape_rate: '降低逃逸缺陷：把缺陷高频模块纳入自动化用例，强化发布前门禁。',
      sprint_completion_rate: '提升迭代达成率：控制承诺范围，按历史速率预留缓冲。',
      review_coverage: '提高评审覆盖：设置必须评审的合并规则，避免直接推送主干。',
      wip_per_person: '降低在制品：限制并行任务数，先完成再开始。',
      tech_debt_ratio: '增加技术债投入：把技术债纳入迭代承诺，避免长期欠账。',
    };
    off.forEach(k => advice.push({
      level: k.attainment !== null && k.attainment < 0.7 ? 'critical' : 'warning',
      title: `${k.label}（${k.value}${k.unit} / 目标 ${k.target}${k.unit}）`,
      detail: templates[k.id] || k.description,
    }));
    overview.insights.filter(i => i.level === 'warning').forEach(i => {
      if (!advice.some(a => a.title.startsWith(i.title))) advice.push(i);
    });
    $('#advice-list').innerHTML = advice.length
      ? advice.slice(0, 8).map(a => `<div class="insight ${a.level}"><strong>${esc(a.title)}</strong><span>${esc(a.detail)}</span></div>`).join('')
      : '<div class="empty">暂无需要改进的项</div>';

    $('#fc-backlog').value = Math.round((overview.metrics.delivered_items?.value || 12) * 4);

    const ids = ['lead_time_hours', 'deploy_frequency', 'change_failure_rate', 'mttr_minutes',
      'cycle_time_hours', 'ci_success_rate', 'throughput_points', 'sprint_completion_rate',
      'defect_escape_rate', 'wip_per_person'];
    const seriesMap = ids.map(id => ({ id, m: overview.metrics[id] })).filter(x => x.m && x.m.series.length > 2);
    const labels = seriesMap.map(x => x.m.label);
    const matrix = seriesMap.map(a => seriesMap.map(b => pearson(
      a.m.series.map(p => p.value), b.m.series.map(p => p.value))));
    Charts.heatmap($('#corr-heatmap'), labels, matrix);
  }

  function pearson(xs, ys) {
    const pairs = xs.map((x, i) => [x, ys[i]]).filter(([x, y]) => x !== null && y !== null && !Number.isNaN(x) && !Number.isNaN(y));
    if (pairs.length < 3) return null;
    const n = pairs.length;
    const mx = pairs.reduce((s, p) => s + p[0], 0) / n;
    const my = pairs.reduce((s, p) => s + p[1], 0) / n;
    let num = 0, dx = 0, dy = 0;
    pairs.forEach(([x, y]) => { num += (x - mx) * (y - my); dx += (x - mx) ** 2; dy += (y - my) ** 2; });
    if (!dx || !dy) return null;
    return num / Math.sqrt(dx * dy);
  }

  async function runForecast() {
    const body = $('#forecast-body');
    body.innerHTML = '<div class="empty">模拟中…</div>';
    try {
      const result = await api('/api/forecast', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          metric: 'delivered_items',
          remaining: Number($('#fc-backlog').value) || null,
          periods: state.periods,
          simulations: 3000,
        }),
      });
      const max = Math.max(...result.histogram.map(h => h.count), 1);
      body.innerHTML = `
        <div class="kv" style="margin-bottom:14px">
          <dt>剩余工作量</dt><dd><strong>${result.backlog}</strong> 项</dd>
          <dt>历史均值</dt><dd>${result.mean} 项/周（${result.samples} 个样本）</dd>
          <dt>P50 完成</dt><dd><strong style="color:var(--ok)">${result.p50} 周</strong></dd>
          <dt>P85 完成</dt><dd><strong style="color:var(--warn)">${result.p85} 周</strong></dd>
          <dt>P95 完成</dt><dd><strong style="color:var(--bad)">${result.p95} 周</strong></dd>
        </div>
        <div class="section-label">完成周期分布（${result.histogram.length} 个区间）</div>
        <div class="bd-list">${result.histogram.map(h => `<div class="bd-row">
          <div>${h.from}–${h.to} 周<div class="bd-bar"><i style="width:${(h.count / max * 100).toFixed(0)}%"></i></div></div>
          <div class="bd-val">${(h.count / 3000 * 100).toFixed(1)}%</div></div>`).join('')}</div>
        <div class="hint" style="margin-top:12px">${esc(result.assumption)}</div>`;
    } catch (err) {
      body.innerHTML = `<div class="empty">${esc(err.message)}</div>`;
    }
  }

  /* ================= 视图切换 ================= */
  const VIEWS = {
    dashboard: { title: '效能总览', sub: '基于本体推理的研发提效度量', render: renderDashboard },
    metrics: { title: '指标字典', sub: '指标定义、口径与下钻', render: renderMetrics },
    lineage: { title: '指标血缘', sub: '派生关系与依赖传递闭包', render: renderLineage },
    ontology: { title: '本体模型', sub: '类、关系、事实与指标的语义定义', render: renderOntology },
    data: { title: '数据接入', sub: 'CSV 导入、质量校验与事实浏览', render: renderData },
    insights: { title: '分析预测', sub: '改进建议、交付预测与指标相关性', render: renderInsights },
  };

  async function switchView(view) {
    state.view = view;
    $$('.nav-item').forEach(b => b.classList.toggle('active', b.dataset.view === view));
    $$('.view').forEach(v => v.classList.add('hidden'));
    $(`#view-${view}`).classList.remove('hidden');
    $('#view-title').textContent = VIEWS[view].title;
    $('#view-sub').textContent = VIEWS[view].sub;
    try {
      await VIEWS[view].render();
    } catch (err) {
      toast(err.message, true);
    }
  }

  /* ================= 初始化 ================= */
  async function init() {
    const saved = localStorage.getItem('rde-theme') || 'dark';
    document.documentElement.dataset.theme = saved;

    $('#theme-toggle').addEventListener('click', () => {
      const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      document.documentElement.dataset.theme = next;
      localStorage.setItem('rde-theme', next);
      switchView(state.view);
    });

    $$('.nav-item').forEach(b => b.addEventListener('click', () => switchView(b.dataset.view)));

    $$('#granularity button').forEach(b => b.addEventListener('click', () => {
      $$('#granularity button').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      state.granularity = b.dataset.g;
      state.metrics = [];
      switchView(state.view);
    }));

    $('#periods').addEventListener('change', e => {
      state.periods = Number(e.target.value);
      state.metrics = [];
      switchView(state.view);
    });

    $('#team-filter').addEventListener('change', e => {
      state.team = e.target.value;
      state.metrics = [];
      switchView(state.view);
    });

    $('#export-report').addEventListener('click', () => {
      window.location.href = `/api/report?format=html&granularity=${state.granularity}&periods=${state.periods}`;
      toast('报告已开始下载');
    });

    $('#metric-search').addEventListener('input', () => renderMetrics());

    const zone = $('#upload-zone');
    const input = $('#file-input');
    zone.addEventListener('click', () => input.click());
    input.addEventListener('change', e => handleFile(e.target.files[0]));
    ['dragenter', 'dragover'].forEach(ev => zone.addEventListener(ev, e => {
      e.preventDefault(); zone.classList.add('drag');
    }));
    ['dragleave', 'drop'].forEach(ev => zone.addEventListener(ev, e => {
      e.preventDefault(); zone.classList.remove('drag');
    }));
    zone.addEventListener('drop', e => handleFile(e.dataTransfer.files[0]));

    $('#download-template').addEventListener('click', () => {
      window.location.href = '/api/import/template?factType=' + encodeURIComponent($('#template-select').value);
    });

    $('#reseed').addEventListener('click', async () => {
      if (!confirm('将清空当前数据并重建演示数据，确定继续？')) return;
      await api('/api/reseed', { method: 'POST' });
      state.metrics = [];
      state.overview = null;
      toast('演示数据已重建');
      switchView('data');
    });

    $('#run-forecast').addEventListener('click', runForecast);

    try {
      const onto = await api('/api/ontology');
      $('#onto-name').textContent = onto.name;
      $('#onto-version').textContent = `v${onto.version} · ${onto.stats.metrics} 个指标`;
      state.ontology = onto;
      const overview = await api('/api/overview?granularity=week&periods=12');
      const teams = overview.coverage.dimensions.team || [];
      $('#team-filter').innerHTML = '<option value="">全部团队</option>' +
        teams.map(t => `<option value="${esc(t)}">${esc(t)}</option>`).join('');
      await switchView('dashboard');
    } catch (err) {
      toast('初始化失败：' + err.message, true);
    }
  }

  window.addEventListener('resize', () => {
    clearTimeout(window._rt);
    window._rt = setTimeout(() => switchView(state.view), 220);
  });

  document.addEventListener('DOMContentLoaded', init);
})();
