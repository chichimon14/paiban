'use strict';
/* duty-roster v6.31 */
/* 示例科室排班系统前端：左侧目录 + 分块视图（hash 路由），无构建步骤。 */
const $ = (id) => document.getElementById(id);
const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日'];
const KIND_TAG = { chief: '科长', deputy: '副科长', cadre: '科员', assistant: '协管员' };

let token = localStorage.getItem('dr_token') || '';
let me = JSON.parse(localStorage.getItem('dr_me') || 'null');
let SYMBOLS = [];
let SYM_MAP = {};
let plans = [];
let detail = null;
let pickerTarget = null;
let draftEdits = new Map(); // 我的选班未保存修改: "day" -> symbol|null
let adminEdits = new Map(); // v2.6 人员管理员对他人行的未保存修改: "personId:day" -> symbol|null（保存前不发送，刷新即丢弃、不留痕）
let finalEdits = new Map(); // v6.3 人员管理员对已发布最终表的未保存修改: "personId:day" -> symbol|null（点「保存修改」整批经 final/edits 生效）
let sheetFinalEditMode = false; // v6.3 成员合并页当前是否处于「已发布 + 管理员改最终表」分支（bindMemberSheet 据此分流绑定）
let lastSavedAt = '';
let sheetMyEditable = false; // 成员合并页：本人行当前是否可直接编辑（管理员改他人行亦为本地暂存、保存即生效）
let sheetMyLockReason = '';
let onlyMeMode = false; // v5.1：成员合并页「只看本人」模式（模块级状态，点选重渲染不重置；仅影响 gridHTML 行显示，统计/预检仍按全员数据）

/* v2.4 三级角色：super=admin 账号；admin=is_admin 的人员账号；member=普通成员。
   兼容旧会话缓存（me 里还没有 role 字段时按 username/is_admin 推导）。 */
function myRole() {
  if (!me) return 'member';
  if (me.role) return me.role;
  if (me.username === 'admin') return 'super';
  return me.is_admin ? 'admin' : 'member';
}

function symLabel(code) {
  if (!code) return '清除（上班）';
  const s = SYM_MAP[code];
  return s ? `${s.display} ${s.name}` : code;
}

/* v2.6：adjustments 表已转为管理员修改日志——applied=已生效；
   approved/rejected/superseded 为 v2.4 审批流历史；void=已作废（未生效）。
   v3.1：状态文案抽为 ADJ_STATUS_LABEL 映射，日志页筛选下拉与 chip 共用同一文案。 */
const ADJ_STATUS_LABEL = {
  applied: '已生效',
  approved: '已批准（历史）',
  rejected: '已驳回（历史）',
  superseded: '已被替代（历史）',
  void: '已作废（未生效）',
};
function adjStatusChip(st) {
  const cls = { applied: 'green', approved: 'green', rejected: 'red', superseded: 'grey', void: 'violet' }[st];
  if (!cls) return esc(st);
  return `<span class="chip ${cls}">${ADJ_STATUS_LABEL[st]}</span>`;
}

/* 登录日志只有 success 布尔，筛选与展示统一用此文案 */
function loginResultLabel(l) {
  return l.success ? '成功' : '失败';
}

/* v3.1：日志页筛选状态（模块级，页面内重渲染/数据刷新时保持，
   渲染时校验值仍在数据范围内，失效自动回落为「全部」）。
   v4.3：两卡各加 from/to 起止日期（同样保存在此、重置时一并清空）。 */
const logFilters = {
  mod: { admin: '', status: '', target: '', from: '', to: '' },
  login: { user: '', result: '', from: '', to: '' },
};

/* v4.3：时间筛选——created_at 是服务器本地（Asia/Shanghai）时间字符串，
   取前 10 位日期（YYYY-MM-DD）与起止日做字典序比较，含起止日当天，
   任一端为空表示该端不限。 */
function logDatePart(ts) { return (ts || '').slice(0, 10); }
function inDateRange(ts, from, to) {
  const d = logDatePart(ts);
  return (!from || d >= from) && (!to || d <= to);
}

function distinctVals(arr) {
  const seen = [];
  arr.forEach((v) => { if (v && !seen.includes(v)) seen.push(v); });
  return seen;
}

/* 部署基路径：根目录部署时为 '/'；经 nginx 以 /duty/ 子路径转发时为 '/duty/' */
const BASE = location.pathname.endsWith('/')
  ? location.pathname
  : location.pathname.replace(/[^/]*$/, '');
const apiUrl = (path) => BASE + String(path).replace(/^\//, '');

async function api(method, path, body) {
  const res = await fetch(apiUrl(path), {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: 'Bearer ' + token } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch (e) { /* ignore */ }
  if (!res.ok) throw new Error((data && data.detail) || ('请求失败 ' + res.status));
  return data;
}

let toastTimer = null;
function toast(msg, bad) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.toggle('bad', !!bad);
  t.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add('hidden'), 4200);
}

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

/* ---------------- 登录 ---------------- */
async function doLogin() {
  $('loginErr').textContent = '';
  try {
    const data = await api('POST', '/api/login', {
      username: $('loginUser').value.trim(),
      password: $('loginPass').value,
    });
    token = data.token; me = data;
    resetMyPostsState();   // v6.8：换账号登录先清「岗位显示」选人残留状态，防跨账号串扰
    localStorage.setItem('dr_token', token);
    localStorage.setItem('dr_me', JSON.stringify(me));
    await enterApp();
  } catch (e) { $('loginErr').textContent = e.message; }
}

function logout() {
  token = ''; me = null; detail = null; plans = [];
  resetMyPostsState();   // v6.8：退出即清「岗位显示」选人状态（此前残留会串到下一个登录的成员账号）
  document.body.classList.remove('fit-view');
  localStorage.removeItem('dr_token');
  localStorage.removeItem('dr_me');
  $('appView').classList.add('hidden');
  $('loginView').classList.remove('hidden');
}

/* ---------------- 框架/导航 ---------------- */
/* v3.0：超管三页合一——主页 / 数据管理 / 排班表合并为单个「排班表」页，
   超管「排班」组只剩这一项。图标与文字拆开渲染：图标走 .nav-ico 定宽槽位
   （见 style.css），保证各组（排班/管理/账号）标签起始列对齐、不再歪斜。
   （NAV 仅超管渲染；成员与人员管理员走 renderNav 的简化分支，同样用槽位。） */
const NAV = [
  { section: '排班' },
  { route: 'sheet', icon: '📋', label: '排班表' },
  { route: 'daily', icon: '🗓', label: '生成排班' },
  { route: 'myposts', icon: '🧭', label: '岗位显示' },
  { section: '管理', admin: true },
  { route: 'rules', icon: '⚙️', label: '规则设置', admin: true },
  { route: 'people', icon: '👥', label: '人员与权限', admin: true },
  { route: 'history', icon: '🗂', label: '历史数据', admin: true },
  { route: 'logs', icon: '📋', label: '日志管理', admin: true },
  { section: '账号' },
  { route: 'password', icon: '🔑', label: '修改密码' },
];

function renderNav() {
  const nav = $('mainNav');
  nav.innerHTML = '';
  const foot = $('footNav');
  if (foot) foot.innerHTML = '';
  if (myRole() !== 'super') {
    // 普通成员与人员管理员：主导航只留合并后的「排班表」一页；修改密码放侧栏底部账号区
    const a = document.createElement('a');
    a.href = '#/sheet';
    a.innerHTML = '<span class="nav-ico">📋</span><span>排班表</span>';
    a.dataset.route = 'sheet';
    nav.appendChild(a);
    // v6.9：普通成员（含协管员）新增「当日排班」只读整表页，位置在
    // 「排班表」与「岗位显示」之间；管理员有编辑页（生成当日排班），
    // 不加此只读项。
    if (myRole() === 'member') {
      const v = document.createElement('a');
      v.href = '#/dayview';
      v.innerHTML = '<span class="nav-ico">📅</span><span>当日排班</span>';
      v.dataset.route = 'dayview';
      nav.appendChild(v);
    }
    // v6.7：管理员侧栏把「生成当日排班」提到「岗位显示」之前（两者互换）——
    // 管理员顺序为 排班表 / 生成当日排班 / 岗位显示；普通成员没有当日排班
    // 编辑页，顺序为 排班表 / 当日排班（v6.9 只读）/ 岗位显示。
    // v6.0：生成当日排班——人员管理员也进成员式侧栏（普通成员没有）
    if (myRole() === 'admin') {
      const d = document.createElement('a');
      d.href = '#/daily';
      d.innerHTML = '<span class="nav-ico">🗓</span><span>生成排班</span>';
      d.dataset.route = 'daily';
      nav.appendChild(d);
    }
    // v6.0：岗位显示单起一个目录项（有对应人员的账号都有）
    if (me && me.person_id) {
      const m = document.createElement('a');
      m.href = '#/myposts';
      m.innerHTML = '<span class="nav-ico">🧭</span><span>岗位显示</span>';
      m.dataset.route = 'myposts';
      nav.appendChild(m);
    }
    if (foot) {
      const pw = document.createElement('a');
      pw.href = '#/password';
      pw.innerHTML = '<span class="nav-ico">🔑</span><span>修改密码</span>';
      pw.dataset.route = 'password';
      foot.appendChild(pw);
    }
    return;
  }
  NAV.forEach((item) => {
    if (item.section) {
      const d = document.createElement('div');
      d.className = 'nav-section';
      d.textContent = item.section;
      nav.appendChild(d);
    } else {
      const a = document.createElement('a');
      a.href = '#/' + item.route;
      a.innerHTML = `<span class="nav-ico">${item.icon}</span><span>${item.label}</span>`;
      a.dataset.route = item.route;
      nav.appendChild(a);
    }
  });
}

function currentRoute() {
  const h = location.hash.replace(/^#\//, '');
  return h || 'home';
}

function markNav() {
  const r = currentRoute();
  document.querySelectorAll('#mainNav a, #footNav a').forEach((a) => {
    a.classList.toggle('active', a.dataset.route === r);
  });
}

async function enterApp() {
  // v2.5：先用服务端最新身份覆盖本地缓存快照——管理员授权变更后，老会话
  // 刷新页面即可按新角色渲染（此前快照停留在授权前的 member，看不到调他人行入口）
  try {
    const fresh = await api('GET', '/api/me');
    me = { ...(me || {}), ...fresh };
    localStorage.setItem('dr_me', JSON.stringify(me));
  } catch (e) { /* 刷新失败时沿用本地快照，不阻断进入 */ }
  $('loginView').classList.add('hidden');
  $('appView').classList.remove('hidden');
  $('whoName').textContent = me.display_name;
  $('whoRole').textContent = { super: '超级管理员', admin: '管理员', member: '普通成员' }[myRole()];
  renderNav();
  SYMBOLS = await api('GET', '/api/symbols');
  SYM_MAP = {};
  SYMBOLS.forEach((s) => { SYM_MAP[s.code] = s; });
  await loadPlans();
  // v3.0：超管落地页与成员一致，都是合并后的「排班表」
  if (!location.hash) location.hash = '#/sheet';
  await renderRoute();
}

async function loadPlans(keepId) {
  plans = await api('GET', '/api/plans');
  const sel = $('planSelect');
  sel.innerHTML = '';
  if (!plans.length) {
    const opt = document.createElement('option');
    opt.textContent = '（暂无计划）';
    sel.appendChild(opt);
    detail = null;
    renderPlanbar();
    return;
  }
  plans.forEach((p) => {
    const opt = document.createElement('option');
    opt.value = p.id;
    opt.textContent = `${p.year}年${p.month}月（应休${p.quota}天）${p.published ? ' · 已发布' : ''}`;
    sel.appendChild(opt);
  });
  const target = keepId && plans.some((p) => p.id === keepId) ? keepId : plans[0].id;
  sel.value = target;
  await loadDetail(target);
}

async function loadDetail(planId) {
  detail = await api('GET', '/api/plans/' + planId);
  draftEdits.clear();
  finalEdits.clear(); // v6.3：切换计划/保存后重载时，最终表暂存一并清掉
  renderPlanbar();
}

function renderPlanbar() {
  if (!detail) {
    $('phaseInfo').textContent = plans.length ? '' : '暂无排班计划，管理员请到「规则设置」新建';
    $('planState').innerHTML = '';
    return;
  }
  const p = detail.plan;
  const w = p.window;
  const names = {
    0: `未开放（${w.chief} 起科长先选）`,
    1: '第1阶段：科长选休中',
    2: `第2阶段：${p.first_group}组（含该组协管员）选休中`,
    3: '第3阶段：全部开放',
  };
  $('phaseInfo').textContent = `当前阶段：${names[p.effective_phase]} ｜ 科长 ${w.chief} · 先行组 ${w.first} · 另一组 ${w.second}`;
  const chips = [];
  chips.push(`<span class="chip">${p.year}年${p.month}月 · 应休 ${p.quota} 天 · 自选上限 ${p.self_limit} 天</span>`);
  if (p.published) chips.push('<span class="chip green">已发布（最终表）</span>');
  else if (p.final_exists) chips.push('<span class="chip orange">管理员已生成最终表（未发布）</span>');
  else chips.push('<span class="chip grey">数据来源：提交源数据汇总</span>');
  $('planState').innerHTML = chips.join('');
}

/* ---------------- 通用月历网格 ---------------- */
/* v2.5：网格本身不再附带口径说明；网格最左侧「类别」列已删除
   （类别信息由姓名右侧职务标签承载），姓名列成为最左侧 sticky 列。
   行序保持：科领导 → 干部 → 协管员。
   v4.5：符号含义按用户要求恢复——以排班表卡片内页脚形式呈现
   （见 sheetLegendHTML，位于网格区下方、与网格同卡，数据源与弹层一致）。 */
function gridHTML(opts) {
  // opts: {gridData, statsArr, editableMode: null|'draft'|'final', myPersonId,
  //        adjustMode: 查看者为人员管理员时他人行也可点（v2.6：本地暂存、保存即生效）,
  //        denomMode: 'quota'（合计分母=应休 Q，默认）|'limit'（=个人适用上限：
  //        草稿/源数据展示时非科长为自选上限 S、科长为 Q),
  //        overlay: fn(personId, day, cell)->{symbol, dirty},
  //        onlyPersonId: v5.1「只看本人」——仅渲染该人员一行（纯显示过滤：
  //        表头/统计行/合计口径不变，统计与预检在调用方按全员数据计算）}
  const p = detail.plan;
  const dim = p.days_in_month;
  const stats = {};
  (opts.statsArr || []).forEach((s) => { stats[s.day] = s; });
  /* v6.5：列着色只剩周末一类——周六日整列挂 weekend（浅粉区分）；
     v6.4 的「干部在岗 ≥6 整列天蓝」已按用户口径取消，天蓝只落在
     页脚「干部在岗人数」行对应天的那一格（见下方统计行渲染）。
     统计取与页脚同一份 statsArr——编辑中调用方传本地实时重算
     结果，列色与蓝格随编辑实时跟随。 */
  const colClsOf = (d) => {
    const wd = new Date(p.year, p.month - 1, d).getDay();
    return (wd === 0 || wd === 6) ? 'weekend' : '';
  };
  const groups = [
    detail.people.filter((x) => x.is_leader),
    detail.people.filter((x) => x.is_cadre && !x.is_leader),
    detail.people.filter((x) => x.kind === 'assistant'),
  ];
  let html = '<table class="grid"><thead><tr><th class="name">姓名</th>';
  for (let d = 1; d <= dim; d++) {
    const wd = new Date(p.year, p.month - 1, d).getDay();
    const cc = colClsOf(d);
    html += `<th${cc ? ` class="${cc}"` : ''}>${d}<br><small>${WEEKDAYS[(wd + 6) % 7]}</small></th>`;
  }
  html += '<th>合计</th></tr></thead><tbody>';
  groups.forEach((members) => {
    members.forEach((person) => {
      if (opts.onlyPersonId && person.id !== opts.onlyPersonId) return; // v5.1：只看本人（纯显示过滤）
      html += '<tr>';
      const tagCls = person.is_leader ? 'leader' : (person.kind === 'assistant' ? 'assistant' : '');
      const chips = [`<span class="tag ${tagCls}">${esc(person.kind_label)}</span>`];
      if (person.grp_label && person.grp_label !== '—' && person.grp_label !== person.kind_label) {
        chips.push(`<span class="tag ${person.is_leader ? 'leader' : ''}">${esc(person.grp_label)}</span>`);
      }
      // 姓名颜色标注提交状态（v2.2）：已提交=绿，已保存草稿未提交=橙，未提交=默认色
      const stCls = person.submission_status === 'submitted' ? 'st-submitted'
        : (person.draft_leave > 0 ? 'st-draft' : '');
      html += `<td class="name"><span class="nm-flex"><span class="nm-name nm-eq ${stCls}">${esc(person.name)}</span><span class="nm-tags">${chips.join('')}</span></span></td>`;
      const cells = opts.gridData[String(person.id)] || {};
      let total = 0;   // 全部计休天数（原口径，供算「其他假期」数）
      let xTotal = 0;  // 其中轮休（X）天数——v4.7 合计主数字口径
      for (let d = 1; d <= dim; d++) {
        let cell = cells[String(d)] || null;
        let dirty = false;
        if (opts.overlay) {
          const ov = opts.overlay(person.id, d, cell);
          if (ov) { cell = ov.symbol ? { symbol: ov.symbol, source: 'edit' } : null; dirty = ov.dirty; }
        }
        if (cell && SYM_MAP[cell.symbol] && SYM_MAP[cell.symbol].counts_leave) total += 1;
        if (cell && cell.symbol === 'X') xTotal += 1;
        if (cell && cell.symbol === 'B') total += 0;
        if (cell && SYM_MAP[cell.symbol] && SYM_MAP[cell.symbol].counts_leave) { /* counted */ }
        const classes = ['cell'];
        // v6.5：人员格只挂周末列类（见 colClsOf）。
        // 已排满的日子不再挂 full 灰底类（用户口径）——每日上限的点选
        // 预检 checkDailyCaps 与后端保存校验不变，满员与否看页脚统计行。
        const cc = colClsOf(d);
        if (cc) classes.push(cc);
        if (cell && cell.source === 'auto') classes.push('auto');
        if (cell && cell.source === 'submitted') classes.push('fromsource');
        if (dirty) classes.push('dirty');
        // 可编辑判定只看「查看者」：本人行，或查看者本人是人员管理员（adjustMode
        // 由 myRole() === 'admin' 决定，他人行可点并本地暂存、保存即生效）——与
        // 目标人的 can_pick（阶段窗口/提交状态）无关，v2.5 明确固化这一点。
        const editable = opts.editableMode === 'final'
          ? true
          : (opts.editableMode === 'draft' && (person.id === opts.myPersonId || opts.adjustMode));
        if (editable) classes.push('editable');
        const disp = cell ? SYM_MAP[cell.symbol].display : '';
        html += `<td class="${classes.join(' ')}" data-person="${person.id}" data-day="${d}">${disp}</td>`;
      }
      // 合计分母：草稿/源数据口径用个人适用上限（非科长=S、科长=Q），最终表口径用 Q
      // v4.7：合计主数字改为轮休（X）数/上限；另有其他假期（总计休-X）时后缀「 +N」
      const denom = opts.denomMode === 'limit' ? person.select_limit : p.quota;
      const otherLeave = total - xTotal;
      html += `<td><b>${xTotal}</b>/${denom}${otherLeave > 0 ? ` +${otherLeave}` : ''}</td></tr>`;
    });
  });
  [['每日在岗人数', 'total_on_duty'], ['干部在岗人数', 'cadre_on_duty'], ['协管员在岗人数', 'assistant_on_duty']].forEach(([label, key]) => {
    html += `<tr class="stats"><td class="stats-label">${label}</td>`;
    for (let d = 1; d <= dim; d++) {
      const v = stats[d] ? stats[d][key] : '';
      const bad = key === 'assistant_on_duty' && stats[d] && stats[d][key] < 1;
      /* v6.5：天蓝只给「干部在岗人数」行中在岗 ≥6 的那一格（人手宽裕
         一目了然），其余两行不挂；周末那天该格同样压过粉底（CSS 中
         cadre-blue 规则后置同特异性胜出）。 */
      const blue = key === 'cadre_on_duty' && stats[d] && stats[d][key] >= 6;
      const cls = [colClsOf(d), bad ? 'stat-bad' : '', blue ? 'cadre-blue' : ''].filter(Boolean).join(' ');
      html += `<td${cls ? ` class="${cls}"` : ''}>${v}</td>`;
    }
    html += '<td></td></tr>';
  });
  html += '</tbody></table>';
  return html;
}

function bindGridCells(container, onPick) {
  container.querySelectorAll('td.cell.editable').forEach((td) => {
    td.addEventListener('click', (ev) => {
      const person = detail.people.find((x) => x.id === Number(td.dataset.person));
      openPicker(person, Number(td.dataset.day), td, onPick);
    });
  });
}

function gridCardHTML(title, inner) {
  return `<div class="card"><h2 class="grid-title">${esc(title)}</h2><div class="grid-wrap">${inner}</div></div>`;
}

/* v2.3：排班表卡片——标题行内嵌操作按钮（左/中/右三区），
   网格区 flex 占满剩余高度（配合 fitGrids 的 --cellh 自适应行高）。
   v2.5：卡片底部图例区曾按用户要求删除；
   v4.5：按用户要求恢复为卡片内页脚（见 sheetLegendHTML）——页脚是
   flex-none、位于网格区之外，fitGrids 按网格区 clientHeight 测高，
   网格自动让出页脚高度，整页一屏拟合口径不变。 */
function sheetCardHTML(titleRowHTML, inner) {
  return `<div class="card sheet-card">${titleRowHTML}<div class="grid-wrap fit-wrap">${inner}</div>${sheetLegendHTML()}</div>`;
}

/* v4.5：符号图例条——排班表卡片底部页脚（统计行下方、卡片内空白处）。
   逐项由 SYMBOLS 生成，与选符号弹层同一数据源：后端改名自动同步，
   此处不硬编码符号清单。仅经 sheetCardHTML 渲染——成员/人员管理员
   合并页与超管合并排班表页共用，其它页面（gridCardHTML 等）没有。 */
function sheetLegendHTML() {
  if (!SYMBOLS.length) return '';
  const items = SYMBOLS.map((s) =>
    `<span class="lg-item"><b>${esc(s.display)}</b>${esc(s.name)}</span>`).join('');
  return `<div class="sheet-legend"><span class="lg-label">符号说明：</span>${items}</div>`;
}

function sheetTitleRow(leftHTML, title, rightHTML) {
  return `<div class="sheet-title-row"><div class="st-zone st-left">${leftHTML}</div>` +
    `<h2 class="grid-title">${esc(title)}</h2>` +
    `<div class="st-zone st-right">${rightHTML}</div></div>`;
}

/* v2.7：排班表标题合并为一句话（与标题同字体同字号，不再用徽标）：
   查看者有本人自选上限时在括号内追加后半句（N：科长=Q、其余=S）；
   不传 myLimit（超管视图 / 已发布 / 账号无对应人员）时标题原样。
   文案沿革：v2.7 初版后半句文案（后被取代，原文见 v2.7 记录）；
   v4.6 改为「，您可勾选N天」；
   v4.7 随上限口径变更（只限定轮休）补足为「，您可勾选N天轮休」，
   如「示例科室排班表（11月可休9天，您可勾选6天轮休）」。 */
function sheetTitle(plan, myLimit) {
  const quotaPart = `${plan.month}月可休${plan.quota}天`;
  const minePart = myLimit != null ? `，您可勾选${myLimit}天轮休` : '';
  return `示例科室排班表（${quotaPart}${minePart}）`;
}

const EXPORT_BTNS = '<button id="expXlsx" class="primary">导出 Excel</button><button id="expImg">生成图片</button>';

/* ---------------- v2.3 行高自适应 ----------------
   拟合模型（与 style.css 中的高度公式严格对应）：
   表格总高 ≈ 表头(0.5*cellh + 18) + 人员行数*cellh + 统计行数*(0.45*cellh + 8) + 边框冗余(总行数+1)
   手机横屏矮屏 compact 模式下表头改为单行：(0.3*cellh + 8，拟合常数取 10 留内容冗余)。
   桌面钳制 [26, 54]，小屏钳制 [18, 54]。 */
function fitGrids() {
  const compact = window.matchMedia('(max-width: 900px) and (max-height: 500px)').matches;
  const small = window.matchMedia('(max-width: 900px)').matches;
  const minH = small ? 18 : 26;
  const headerMul = compact ? 0.3 : 0.5;
  const headerConst = compact ? 10 : 18;
  const strictFit = document.body.classList.contains('fit-view') &&
    window.matchMedia('(min-width: 901px), (max-width: 900px) and (max-height: 500px)').matches;
  document.querySelectorAll('#view .grid-wrap').forEach((wrap) => {
    const table = wrap.querySelector('table.grid');
    if (!table) return;
    const personRows = table.querySelectorAll('tbody tr:not(.stats)').length;
    const statsRows = table.querySelectorAll('tbody tr.stats').length;
    if (!personRows) return;
    let avail;
    if (strictFit && wrap.classList.contains('fit-wrap') && wrap.clientHeight > 40) {
      avail = wrap.clientHeight;
    } else {
      const rect = wrap.getBoundingClientRect();
      avail = Math.max(200, window.innerHeight - rect.top - 12);
    }
    const units = headerMul + personRows + statsRows * 0.45;
    const fixed = headerConst + statsRows * 8 + (1 + personRows + statsRows + 1);
    let cellh = (avail - fixed) / units;
    cellh = Math.max(minH, Math.min(54, cellh));
    table.style.setProperty('--cellh', cellh.toFixed(1) + 'px');
  });
}

let fitTimer = null;
function scheduleFit() {
  clearTimeout(fitTimer);
  fitTimer = setTimeout(() => requestAnimationFrame(fitGrids), 80);
}

/* ---------------- 符号选择 ---------------- */
/* v2.8：选择层定位——贴在锚点格右侧弹出（用户反馈：比正下方下拉更顺眼）：
   1) 水平优先右侧：左上角贴格子右上角（left = rect.right + 2）；
      右侧放不下则翻到格子左侧（left = rect.left - w - 2）；
      两侧都不行（窄屏）才钳制回视口内，允许与格子重叠兜底。
   2) 垂直优先上缘对齐：top = rect.top；下方超出则改为与格子下缘对齐
      （top = rect.bottom - h）；再越界则钳制到距顶 M。
   配合 .picker 的 max-height: calc(100dvh - 16px) + overflow-y:auto，
   矮屏时层内滚动保证全部选项与清除按钮可达、可点。 */
function placePicker(picker, rect) {
  const M = 8; // 距视口边缘的最小间距(px)
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const w = picker.offsetWidth;
  const h = picker.offsetHeight; // max-height 钳制后的实际高度
  // 水平：优先锚点格右侧
  let left = rect.right + 2;
  if (left + w > vw - M) {
    left = rect.left - w - 2; // 右侧放不下 → 翻到锚点格左侧
    if (left < M) {
      // 两侧都放不下（窄屏）：钳制回视口内兜底
      left = Math.max(M, Math.min(rect.right + 2, vw - w - M));
    }
  }
  // 垂直：优先与锚点格上缘对齐
  let top = rect.top;
  if (top + h > vh - M) {
    top = rect.bottom - h; // 下方放不下 → 与锚点格下缘对齐
    if (top < M) top = M; // 矮屏兜底：贴视口顶部，层内滚动到达全部选项
  }
  picker.style.left = left + 'px';
  picker.style.top = top + 'px';
}

function openPicker(person, day, anchor, onPick) {
  pickerTarget = { person, day, onPick };
  $('pickerTitle').textContent = `${person.name} · ${detail.plan.month}月${day}日`;
  const grid = $('pickerGrid');
  grid.innerHTML = '';
  SYMBOLS.forEach((s) => {
    const b = document.createElement('button');
    b.innerHTML = `<span class="sym">${s.display}</span><span class="nm">${s.name}</span>`;
    b.addEventListener('click', () => { closePicker(); pickerTarget && null; onPick(person.id, day, s.code); });
    grid.appendChild(b);
  });
  $('pickerClear').onclick = () => { closePicker(); onPick(person.id, day, null); };
  const picker = $('picker');
  picker.classList.remove('hidden');
  placePicker(picker, anchor.getBoundingClientRect());
}

function closePicker() {
  $('picker').classList.add('hidden');
  pickerTarget = null;
}

/* ---------------- 通用：提交状态 chip ----------------
   v3.0：原「主页」视图已并入超管合并排班表（见 viewSheetAdmin），viewHome 删除。 */
function statusChip(p) {
  if (p.submission_status === 'submitted') return `<span class="chip green">已提交</span>`;
  if (p.submission_status === 'returned') return `<span class="chip orange">已退回，可重提</span>`;
  return `<span class="chip grey">未提交</span>`;
}

/* ---------------- 视图：我的选班 ---------------- */
function myPerson() {
  return detail ? detail.people.find((x) => x.id === detail.my_person_id) : null;
}

function draftOverlay(personId, day, cell) {
  if (!detail) return null;
  if (personId === detail.my_person_id) {
    const key = String(day);
    if (!draftEdits.has(key)) return null;
    return { symbol: draftEdits.get(key), dirty: true };
  }
  // v2.6：人员管理员对他人行的本地暂存修改（橙色描边，保存前不发送）
  const key = personId + ':' + day;
  if (!adminEdits.has(key)) return null;
  return { symbol: adminEdits.get(key), dirty: true };
}

/* v6.3：已发布最终表的本地暂存修改叠加层（与 draftOverlay 同构，
   数据源为 detail.final_grid + finalEdits，渲染口径一致：橙色描边）。 */
function finalOverlay(personId, day, cell) {
  if (!detail) return null;
  const key = personId + ':' + day;
  if (!finalEdits.has(key)) return null;
  return { symbol: finalEdits.get(key), dirty: true };
}

/* v4.7：本人草稿的轮休（X）计数——个人自选上限只统计轮休，进度/合计/
   本地预检统一按此口径（原 myDraftLeaveCount 按全部计休符号计数，已改名）。 */
function myDraftXCount() {
  const mine = myPerson();
  if (!mine) return 0;
  const cells = { ...(detail.grid[String(mine.id)] || {}) };
  draftEdits.forEach((sym, day) => {
    if (sym) cells[day] = { symbol: sym }; else delete cells[day];
  });
  return Object.values(cells).filter((c) => c.symbol === 'X').length;
}

/* ---------------- v4.8：本地有效网格、即时统计与每日上限点选预检 ----------------
   用户实测三点：①勾选未保存时底部三行在岗统计纹丝不动（统计只按服务端
   已保存网格算）；②每日人数上限要等点「保存」才整批报错；③见后端
   _check_batch_caps 的中间状态误判修复。前端对策：
   - effectiveGridMap()：detail.grid 叠加本人 draftEdits 与他人 adminEdits
     后的「有效网格」（叠加口径与格子渲染的 draftOverlay 完全一致）；
   - localDayStats()：按有效网格本地复刻后端 day_stats 同结构统计——
     成员合并页（与旧「我的选班」页）的三行在岗人数与满员变灰改用它，
     每次点选重渲染即刷新；计休口径同后端：全部计休符号减少在岗，
     备勤 B 不计；
   - checkDailyCaps()：点选当下按有效网格预检每日上限（干部<=4 /
     科领导<=2 / 协管员<=1，按全部计休符号统计），与后端硬校验同口径，
     超限立即 toast 拦截、不记暂存；服务端的整批最终状态校验仍是兜底。 */
const CADRE_DAILY_LEAVE_CAP = 4;     // 与后端同名常量保持一致
const LEADER_DAILY_LEAVE_CAP = 2;
const ASSISTANT_DAILY_LEAVE_CAP = 1;

function countsLeave(symbol) {
  return !!(symbol && SYM_MAP[symbol] && SYM_MAP[symbol].counts_leave);
}

/* 有效网格：{personId: {day: symbol}}（仅含非空格），供统计/预检共用。 */
function effectiveGridMap() {
  const out = {};
  if (!detail) return out;
  detail.people.forEach((person) => {
    const cells = detail.grid[String(person.id)] || {};
    const row = {};
    for (let d = 1; d <= detail.plan.days_in_month; d++) {
      let cell = cells[String(d)] || null;
      const ov = draftOverlay(person.id, d, cell);
      if (ov) cell = ov.symbol ? { symbol: ov.symbol } : null;
      if (cell) row[d] = cell.symbol;
    }
    out[person.id] = row;
  });
  return out;
}

/* v6.3：最终表有效网格——detail.final_grid 叠加 finalEdits 后的
   {personId: {day: symbol}}（与 effectiveGridMap 同构，供已发布
   管理员改最终表时的统计与预检使用）。 */
function effectiveFinalGridMap() {
  const out = {};
  if (!detail) return out;
  detail.people.forEach((person) => {
    const cells = detail.final_grid[String(person.id)] || {};
    const row = {};
    for (let d = 1; d <= detail.plan.days_in_month; d++) {
      let cell = cells[String(d)] || null;
      const ov = finalOverlay(person.id, d, cell);
      if (ov) cell = ov.symbol ? { symbol: ov.symbol } : null;
      if (cell) row[d] = cell.symbol;
    }
    out[person.id] = row;
  });
  return out;
}

/* 本地每日统计：结构与后端 day_stats 一致（full=干部或科领导任一达上限）。
   v6.3：可选传入预先算好的有效网格（如最终表口径），缺省用草稿口径。 */
function localDayStats(gridMap) {
  const grid = gridMap || effectiveGridMap();
  const people = detail.people;
  const nCadre = people.filter((x) => x.is_cadre).length;
  const nLeader = people.filter((x) => x.is_leader).length;
  const nAssistant = people.filter((x) => x.kind === 'assistant').length;
  const arr = [];
  for (let d = 1; d <= detail.plan.days_in_month; d++) {
    let cadreLeave = 0, leaderLeave = 0, totalLeave = 0, assistantLeave = 0;
    people.forEach((person) => {
      if (!countsLeave((grid[person.id] || {})[d])) return;
      totalLeave += 1;
      if (person.is_cadre) { cadreLeave += 1; if (person.is_leader) leaderLeave += 1; }
      if (person.kind === 'assistant') assistantLeave += 1;
    });
    arr.push({
      day: d,
      cadre_leave: cadreLeave, leader_leave: leaderLeave, assistant_leave: assistantLeave,
      cadre_on_duty: nCadre - cadreLeave, leader_on_duty: nLeader - leaderLeave,
      assistant_on_duty: nAssistant - assistantLeave,
      assistant_full: assistantLeave >= ASSISTANT_DAILY_LEAVE_CAP,
      total_on_duty: people.length - totalLeave,
      full: cadreLeave >= CADRE_DAILY_LEAVE_CAP || leaderLeave >= LEADER_DAILY_LEAVE_CAP,
    });
  }
  return arr;
}

/* 点选时每日上限预检（本人行/他人行共用）：仅当本次点选使目标格由
   「不计休」变为「计休」（当日休假人数 delta=+1）时才可能触发；
   计休符号之间互换（delta=0）、清除（delta<0）、备勤 B 均不拦截。
   组别与后端一致：干部上限覆盖全部干部（含科领导），科领导另加一道，
   协管员单独一道；检查顺序同后端（干部 -> 科领导 -> 协管员）。 */
/* v6.3：可选传入网格/统计口径（最终表改班时传 effectiveFinalGridMap
   与其 localDayStats 结果）；缺省为草稿口径，v4.8 既有调用不变。 */
function checkDailyCaps(person, day, symbol, gridMap, statsArr) {
  if (!person || !countsLeave(symbol)) return true;
  const curSym = ((gridMap || effectiveGridMap())[person.id] || {})[day] || null;
  if (countsLeave(curSym)) return true; // 已是计休符号：换符号不增加当日休假人数
  const st = (statsArr || localDayStats(gridMap)).find((s) => s.day === day);
  if (!st) return true;
  if (person.is_cadre && st.cadre_leave + 1 > CADRE_DAILY_LEAVE_CAP) {
    toast(`${day}日干部休假已满${CADRE_DAILY_LEAVE_CAP}人（需保证至少5名干部在岗），不能再勾`, true);
    return false;
  }
  if (person.is_leader && st.leader_leave + 1 > LEADER_DAILY_LEAVE_CAP) {
    toast(`${day}日科领导休假已满${LEADER_DAILY_LEAVE_CAP}人（需保证至少1名科领导在岗），不能再勾`, true);
    return false;
  }
  if (person.kind === 'assistant' && st.assistant_leave + 1 > ASSISTANT_DAILY_LEAVE_CAP) {
    toast(`${day}日协管员休假已满${ASSISTANT_DAILY_LEAVE_CAP}人（需保证至少1名协管员在岗），不能再勾`, true);
    return false;
  }
  return true;
}

/* ---------------- v2.5：选格本地上限预检 ----------------
   此前点格只改本地 draftEdits、不做任何校验，能一路点到 12 天（橙边未保存
   状态），合计也按本地状态虚增；虽然点「保存」时后端会 400 拒绝超限部分，
   体验上像“系统允许选 12 天”。现在点格前先在本地按与后端相同的口径拦截：
   本人行看自选上限（科长=应休 Q、其余=自选上限 S）；管理员点他人行看对方上限。
   v4.7：预检口径改为只统计轮休（X），原 countsLeave 辅助函数随之退役。 */

/* 本人行点格预检：返回 true 才允许把修改记入 draftEdits。
   v4.7：上限只管轮休（X）——非 X 符号（含清除）永不被上限拦截；原格已是
   X 时替换不增计数；X 改其他符号即释放名额（与后端 PUT /cell 同口径）。 */
function checkOwnPick(day, symbol) {
  const mine = myPerson();
  if (!mine) return true;
  if (!checkDailyCaps(mine, day, symbol)) return false; // v4.8：每日上限点选时即时预检
  if (symbol !== 'X') return true;
  // 当天本地已有格子（已保存草稿叠加未保存修改）：已是轮休则替换不增计数
  let curSym = null;
  const saved = (detail.grid[String(mine.id)] || {})[String(day)];
  if (saved) curSym = saved.symbol;
  if (draftEdits.has(String(day))) curSym = draftEdits.get(String(day));
  if (curSym === 'X') return true;
  if (myDraftXCount() + 1 > mine.select_limit) {
    toast(mine.kind === 'chief'
      ? `轮休已勾满 ${mine.select_limit} 天（应休上限），其他假期仍可勾选`
      : `轮休已勾满自选上限 ${mine.select_limit} 天，其他假期仍可勾选`, true);
    return false;
  }
  return true;
}

/* 人员管理员点他人行预检（v2.6 本地暂存前）：对方草稿叠加已暂存修改后的
   轮休数不得超过其上限（后端 admin-edits 整批提交时仍会复检）。
   v4.7：只统计轮休（X），其他假期符号不占名额、永不被上限拦截。 */
function checkOtherPick(person, day, symbol) {
  if (!person) return true;
  if (!checkDailyCaps(person, day, symbol)) return false; // v4.8：每日上限点选时即时预检
  if (symbol !== 'X') return true;
  const cells = { ...(detail.grid[String(person.id)] || {}) };
  adminEdits.forEach((sym, key) => {
    const [pid, d] = key.split(':');
    if (Number(pid) !== person.id) return;
    if (sym) cells[d] = { symbol: sym }; else delete cells[d];
  });
  const cur = cells[String(day)];
  if (cur && cur.symbol === 'X') return true;
  const cnt = Object.values(cells).filter((c) => c.symbol === 'X').length;
  if (cnt + 1 > person.select_limit) {
    toast(`${person.name} 的轮休已勾满自选上限 ${person.select_limit} 天，不能再为其增加轮休（其他假期可勾）`, true);
    return false;
  }
  return true;
}

function viewPick() {
  if (!detail) return '<div class="card">暂无排班计划。</div>';
  const mine = myPerson();
  if (!mine) {
    return '<div class="card">您使用的是超级管理员账号（不对应具体人员），没有个人选班；如需代为修改，请到「排班表」编辑最终表，或用本人账号登录。</div>';
  }
  const p = detail.plan;
  const locked = mine.submission_status === 'submitted';
  const published = p.published;
  let banner = '';
  if (published) banner = '<div class="card" style="border-color:rgba(22,163,74,.35);background:rgba(22,163,74,.07)">本月排班已发布锁定，最终结果请看「主页 / 排班表」。</div>';
  else if (locked) banner = `<div class="card" style="border-color:rgba(217,119,6,.35);background:rgba(217,119,6,.08)">您已于 ${esc(mine.submitted_at)} 提交本月选班，当前已锁定。如需修改，请联系管理员退回后重新提交。</div>`;
  const editable = !locked && !published && mine.can_pick;
  let html = banner;
  html += `<div class="card">
    <div class="toolbar-row">
      <b>${esc(mine.name)}</b><span class="tag ${mine.is_leader ? 'leader' : ''}">${esc(mine.kind_label)}</span><span class="tag">${esc(mine.grp_label)}</span>
      <span>已选轮休 <b id="myCount">${myDraftXCount()}</b> / 自选上限 ${mine.select_limit} 天（应休 ${p.quota} 天，轮休不足部分由管理员一键补满；其他假期不占此名额）</span>
      <span class="spacer"></span>
      <span id="saveState" class="hint">${lastSavedAt ? '上次保存 ' + lastSavedAt : ''}</span>
      <button id="saveDraftBtn" class="primary" ${editable ? '' : 'disabled'}>保存</button>
      <button id="submitBtn" ${editable ? '' : 'disabled'}>提交</button>
      ${locked ? '<span class="chip green">已提交</span>' : ''}
    </div>
    <div class="hint">${editable ? '点击自己一行中的日期格选择假期符号（橙色描边 = 未保存修改），先点「保存」存草稿，确认无误后点「提交」。提交后将锁定，源数据保留一年。' : (mine.can_pick ? '' : '您所在的组别尚未开放选休（见顶部阶段信息）。')}</div>
  </div>`;
  html += gridCardHTML(`我的选班 · ${p.year}年${p.month}月`,
    gridHTML({ gridData: detail.grid, statsArr: localDayStats(), editableMode: editable ? 'draft' : null, myPersonId: mine.id, overlay: draftOverlay, denomMode: 'limit' }));
  return html;
}

async function saveDraft() {
  if (!draftEdits.size && !adminEdits.size) { toast('没有需要保存的修改'); return true; }
  const mine = myPerson();
  const entries = [...draftEdits.entries()];
  for (const [day, symbol] of entries) {
    try {
      const out = await api('PUT', `/api/plans/${detail.plan.id}/cell`, {
        person_id: mine.id, day: Number(day), symbol,
      });
      detail = out;
    } catch (e) {
      toast('保存失败：' + e.message, true);
      renderPlanbar();
      await renderRoute();
      return false;
    }
  }
  draftEdits.clear();
  // v2.6：他人行暂存修改整批提交（保存即生效并记日志）；失败时暂存保留可重试
  let othersLogged = null;
  if (adminEdits.size) {
    const edits = [...adminEdits.entries()].map(([key, sym]) => {
      const [pid, day] = key.split(':');
      return { person_id: Number(pid), day: Number(day), symbol: sym };
    });
    try {
      const res = await api('POST', `/api/plans/${detail.plan.id}/admin-edits`, { edits });
      othersLogged = res.logged || 0;
      adminEdits.clear();
      await loadDetail(detail.plan.id);
    } catch (e) {
      toast('保存对他人的修改失败：' + e.message, true);
      renderPlanbar();
      await renderRoute();
      return false;
    }
  }
  lastSavedAt = new Date().toLocaleTimeString('zh-CN', { hour12: false });
  renderPlanbar();
  await renderRoute();
  toast(othersLogged !== null
    ? `已保存（含对他人的 ${othersLogged} 处修改，已生效）`
    : '草稿已保存 ' + lastSavedAt);
  return true;
}

async function submitMine() {
  if (!confirm('提交后将锁定您的选班（源数据保留一年），确认提交？')) return;
  if (draftEdits.size) {
    const ok = await saveDraft();
    if (!ok) return;
  }
  try {
    const out = await api('POST', `/api/plans/${detail.plan.id}/submit`);
    toast(`已提交（${out.submitted_at}），共 ${out.days} 天选休`);
    await loadDetail(detail.plan.id);
    await renderRoute();
  } catch (e) { toast(e.message, true); }
}

function bindPick() {
  const saveBtn = $('saveDraftBtn');
  if (saveBtn) saveBtn.addEventListener('click', saveDraft);
  const subBtn = $('submitBtn');
  if (subBtn) subBtn.addEventListener('click', submitMine);
  const wrap = $('view');
  bindGridCells(wrap, (personId, day, symbol) => {
    if (!checkOwnPick(day, symbol)) return; // v2.5：本地上限预检，超限不记修改
    draftEdits.set(String(day), symbol);
    renderRoute();
  });
}

/* v5.1：「只看本人」圆形图标按钮（用户定版形态）——直径 34px 圆形，
   内嵌单人头像 SVG（头+肩剪影，currentColor），无文字、无 title
   （避免手机长按弹出提示气泡），仅以 aria-label 供无障碍识别；
   未开启为普通描边样式，开启时填充主题渐变（--grad）、图标变白。
   仅经 CSS 在手机端显示（见 style.css .only-me-btn），桌面 DOM 中
   保留占位以保证标题行左区顺序统一。 */
function onlyMeBtnHTML() {
  const label = onlyMeMode ? '显示全员' : '只看本人';
  return `<button id="onlyMeBtn" class="only-me-btn${onlyMeMode ? ' on' : ''}" aria-label="${label}" aria-pressed="${onlyMeMode}">` +
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21v-1c0-3.9 3.6-6 8-6s8 2.1 8 6v1H4z"/></svg></button>';
}

/* ---------------- 视图：排班表（成员为三页合一） ---------------- */
function viewSheet() {
  if (myRole() !== 'super') return viewMemberSheet();
  return viewSheetAdmin();
}

/* 成员合并页（v2.3）：紧凑进度卡 + 全月排班表（仅自己行可编辑）；
   保存/提交/导出按钮全部并入排班表标题行，不再有独立工具条卡片；整页一屏自适应。
   v2.6：审批流撤销——管理员改他人行与改自己一样本地暂存、保存即生效；
   v2.7：标题合并为一句话「…（X月可休Q天，您可勾选N天）」（已发布时不带后半句）；
   后半句文案 v4.6 改「您可勾选N天」、v4.7 补足为「您可勾选N天轮休」。 */
function viewMemberSheet() {
  sheetFinalEditMode = false; // v6.3：每次渲染先复位，仅已发布+管理员分支置真
  if (!detail) return '<div class="card">暂无排班计划，请等待管理员创建。</div>';
  const p = detail.plan;
  const mine = myPerson();
  const title = sheetTitle(p);
  let html = '<div class="sheet-fit">';
  if (p.published) {
    // v6.3：已发布后人员管理员仍可改最终表（用户明确口径）——点格本地
    // 暂存（橙色描边，finalEdits），标题行给「保存修改/撤销」，保存经
    // POST /final/edits 整批生效并记日志；计划保持已发布。普通成员
    // 维持只读（下方原分支）。
    if (myRole() === 'admin') {
      sheetFinalEditMode = true;
      const pending = finalEdits.size;
      const row = sheetTitleRow(
        // v6.7：左区只留「已发布」徽标——原管理员说明句（本月排班已发布。
        // 您是管理员：可直接点击格子修改…）按用户要求整句撤下；未保存
        // 修改的处数不再在此提示（保存/撤销按钮的禁用态仍随之变化）。
        (mine ? onlyMeBtnHTML() : '') +
        '<span class="chip green">已发布</span>',
        title,
        `<button id="finalEditSaveBtn" class="primary" ${pending ? '' : 'disabled'}>保存修改</button><button id="finalEditUndoBtn" ${pending ? '' : 'disabled'}>撤销</button>` + EXPORT_BTNS);
      html += `<div id="sheetWrap" class="sheet-flex">${sheetCardHTML(row,
        gridHTML({ gridData: detail.final_grid, statsArr: localDayStats(effectiveFinalGridMap()), editableMode: 'final', overlay: finalOverlay, denomMode: 'quota', onlyPersonId: onlyMeMode && mine ? mine.id : null }))}</div>`;
      html += '</div>';
      return html;
    }
    const row = sheetTitleRow(
      // v5.1：已发布分支无「保存」，只看本人按钮置于左区最前（账号无对应人员时不渲染）
      (mine ? onlyMeBtnHTML() : '') +
      '<span class="chip green">已发布</span><span class="hint">本月排班已发布，以下为最终排班表。</span>',
      title, EXPORT_BTNS);
    html += `<div id="sheetWrap" class="sheet-flex">${sheetCardHTML(row,
      gridHTML({ gridData: detail.display_grid, statsArr: detail.display_day_stats, denomMode: 'quota', onlyPersonId: onlyMeMode && mine ? mine.id : null }))}</div>`;
    html += '</div>';
    return html;
  }
  // v2.2：成员页不再有「已选情况」精简条，提交状态由排班表姓名颜色标注
  if (!mine) {
    const row = sheetTitleRow(
      '<span class="hint">您的账号未对应具体人员，可查看排班表但不能选班。</span>',
      title, EXPORT_BTNS);
    html += `<div id="sheetWrap" class="sheet-flex">${sheetCardHTML(row,
      gridHTML({ gridData: detail.grid, statsArr: detail.day_stats, denomMode: 'limit' }))}</div>`;
    html += '</div>';
    return html;
  }
  const locked = mine.submission_status === 'submitted';
  const editable = !locked && mine.can_pick;
  const isAdminRole = myRole() === 'admin';
  sheetMyEditable = editable;
  sheetMyLockReason = locked
    ? `您已于 ${mine.submitted_at} 提交本月选班，当前已锁定。如需修改，请联系超级管理员退回后重新提交。`
    : '您所在的组别尚未开放选休（见顶部阶段信息）。';
  const progressText = `我的进度：已选轮休 <b id="myCount">${myDraftXCount()}</b> / 自选上限 ${mine.select_limit} 天（应休 ${p.quota} 天，轮休不足部分由管理员一键补满；其他假期不占此名额）`;
  const hintText = locked
    ? `您已于 ${esc(mine.submitted_at)} 提交本月选班，当前已锁定。如需修改，请联系管理员退回后重新提交。`
    : (editable
      ? '在下方排班表中点击自己一行中的日期格选择假期符号（橙色描边 = 未保存修改），先点「保存」存草稿，确认无误后点「提交」。提交后将锁定，源数据保留一年。点保存左侧的圆形人像按钮，可只看自己一行排班，再点一次恢复全员。'
      : (mine.can_pick ? '' : '您所在的组别尚未开放选休（见顶部阶段信息）。'));
  html += `<div class="card slim progress-card"${locked ? ' style="border-color:rgba(217,119,6,.35);background:rgba(217,119,6,.08)"' : ''}>
    <div class="toolbar-row" style="margin-bottom:0">
      <b>${esc(mine.name)}</b><span class="tag ${mine.is_leader ? 'leader' : ''}">${esc(mine.kind_label)}</span><span class="tag">${esc(mine.grp_label)}</span>
      <span>${progressText}</span>
      ${locked ? '<span class="chip green">已提交</span>' : statusChip(mine)}
    </div>
    ${hintText ? `<div class="hint">${hintText}</div>` : ''}
    ${isAdminRole ? '<div class="hint">您是管理员：可点击他人行调整排班，与改自己一样点「保存」后生效，修改会记录在日志中。</div>' : ''}
  </div>`;
  const leftZone =
    // v5.1：「只看本人」圆形按钮紧贴「保存」左侧（顺序：只看本人 | 保存 | 提交）
    onlyMeBtnHTML() +
    // v2.6：人员管理员本人行锁定（已提交）时「保存」仍可用——用于保存对他人行的暂存修改
    `<button id="saveDraftBtn" class="primary" ${(editable || isAdminRole) ? '' : 'disabled'}>保存</button>` +
    `<button id="submitBtn" ${editable ? '' : 'disabled'}>提交</button>` +
    `<span id="saveState" class="hint">${lastSavedAt ? '上次保存 ' + lastSavedAt : ''}</span>` +
    `<span class="st-progress">已选轮休 <b>${myDraftXCount()}</b>/${mine.select_limit} 天 · ${locked ? '已提交' : '未提交'}</span>`;
  // v2.7：标题合并本人上限为同一句话（mine.select_limit：科长=Q、其余=S）
  const row = sheetTitleRow(leftZone, sheetTitle(p, mine.select_limit), EXPORT_BTNS);
  html += `<div id="sheetWrap" class="sheet-flex">${sheetCardHTML(row,
    gridHTML({ gridData: detail.grid, statsArr: localDayStats(), editableMode: (editable || isAdminRole) ? 'draft' : null, myPersonId: mine.id, overlay: draftOverlay, adjustMode: isAdminRole, denomMode: 'limit', onlyPersonId: onlyMeMode ? mine.id : null }))}</div>`;
  html += '</div>';
  return html;
}

/* v6.3：已发布最终表暂存修改整批保存（保存即生效并记日志，计划保持
   已发布）；失败时暂存保留可重试，与 saveDraft 的他人行分支同口径。 */
async function saveFinalEdits() {
  if (!finalEdits.size) { toast('没有需要保存的修改'); return; }
  const edits = [...finalEdits.entries()].map(([key, sym]) => {
    const [pid, day] = key.split(':');
    return { person_id: Number(pid), day: Number(day), symbol: sym };
  });
  try {
    const res = await api('POST', `/api/plans/${detail.plan.id}/final/edits`, { edits });
    finalEdits.clear();
    await loadDetail(detail.plan.id);
    renderPlanbar();
    await renderRoute();
    toast(`最终排班已保存（${res.logged || 0} 处修改已生效）`);
  } catch (e) {
    toast('保存失败：' + e.message, true);
  }
}

function bindMemberSheet() {
  // v5.1：「只看本人」切换——翻转模块级状态后重渲染（状态不被点选重渲染冲掉；
  // 切换不触碰 draftEdits/adminEdits 两张暂存表，管理员已暂存的他人修改保留待保存）
  const omBtn = $('onlyMeBtn');
  if (omBtn) omBtn.addEventListener('click', () => { onlyMeMode = !onlyMeMode; renderRoute(); });
  // v6.3：已发布 + 管理员分支——绑定「保存修改/撤销」与最终表点格暂存，
  // 与草稿流分流（草稿在已发布计划上已被后端锁定，不可混用），故提前返回。
  if (sheetFinalEditMode) {
    const sv = $('finalEditSaveBtn');
    if (sv) sv.addEventListener('click', saveFinalEdits);
    const un = $('finalEditUndoBtn');
    if (un) un.addEventListener('click', () => { finalEdits.clear(); renderRoute(); });
    bindGridCells($('view'), (personId, day, symbol) => {
      const target = detail.people.find((x) => x.id === personId);
      // 点选预检：仅每日硬上限（最终层无个人自选上限），按最终表有效网格口径
      const fgm = effectiveFinalGridMap();
      if (!checkDailyCaps(target, day, symbol, fgm, localDayStats(fgm))) return;
      const key = personId + ':' + day;
      const origCell = (detail.final_grid[String(personId)] || {})[String(day)];
      const orig = origCell ? origCell.symbol : null;
      if (symbol === orig) finalEdits.delete(key); else finalEdits.set(key, symbol);
      renderRoute();
    });
    bindSheet();
    return;
  }
  const saveBtn = $('saveDraftBtn');
  if (saveBtn) saveBtn.addEventListener('click', saveDraft);
  const subBtn = $('submitBtn');
  if (subBtn) subBtn.addEventListener('click', submitMine);
  bindGridCells($('view'), async (personId, day, symbol) => {
    if (detail && personId === detail.my_person_id) {
      // 本人行：与普通成员完全一致的草稿流（直存，无需审批）
      if (!sheetMyEditable) { toast(sheetMyLockReason || '当前不可修改本人选班', true); return; }
      if (!checkOwnPick(day, symbol)) return; // v2.5：本地上限预检，超限不记修改
      draftEdits.set(String(day), symbol);
      renderRoute();
      return;
    }
    // 管理员调整他人行（v2.6）：与改本人行完全一致——本地暂存（橙色描边），
    // 点「保存」后整批经 admin-edits 生效并记日志；刷新页面即丢弃、不留痕。
    // 点选前先本地预检对方上限（接口整批提交时仍会复检），超限即时提示不暂存。
    const target = detail.people.find((x) => x.id === personId);
    if (!checkOtherPick(target, day, symbol)) return;
    const key = personId + ':' + day;
    const origCell = (detail.grid[String(personId)] || {})[String(day)];
    const orig = origCell ? origCell.symbol : null;
    if (symbol === orig) adminEdits.delete(key); else adminEdits.set(key, symbol);
    renderRoute();
  });
  bindSheet();
}

/* v3.0：超管合并页——原主页 / 数据管理 / 排班表三页合一，统称「排班表」。
   v3.1：v3.0 的瘦身条与网格标题行再并为一行——即网格卡的标题行本身：
   左区 = 当前层短标签 + 一行小字状态（已提交 N/总 · 最终表 已生成/未生成 ·
   已保存/未保存 · 已发布/未发布，超宽省略），中 = 标题，右区 = 工作流按钮
   （调取/补满/保存/发布/退回控件）与导出按钮同组（放不下在行内换行）。
   网格口径（与服务端 display 口径一致）：已有最终表 → 显示最终表，点格走最终表
   编辑（未发布时，硬约束超限警告沿用原逻辑）；尚无最终表 → 显示提交源数据/草稿
   汇总只读（与原超管排班表页一致）。 */
function viewSheetAdmin() {
  sheetFinalEditMode = false; // v6.3：超管合并页不走成员页的最终表暂存分流
  if (!detail) return '<div class="card">暂无排班计划。</div>';
  const p = detail.plan;
  const isFinal = detail.display_kind === 'final';
  const kindName = { final: '最终表' + (p.published ? '（已发布）' : ''), source: '提交源数据汇总', draft: '成员草稿汇总' }[detail.display_kind];
  const submitted = detail.people.filter((x) => x.submission_status === 'submitted');
  const statusText = `已提交 ${submitted.length}/${detail.people.length} 人 · 最终表 ${p.final_exists ? '已生成' : '未生成'} · ${p.final_saved_at ? '已保存 ' + esc(p.final_saved_at) : '未保存'} · ${p.published ? '已发布' : '未发布'}`;
  const actions =
    '<button id="pullBtn" class="primary">调取数据</button>' +
    '<button id="finalAutoBtn" class="primary">一键补满（最终表）</button>' +
    '<button id="finalSaveBtn">保存</button>' +
    (p.published ? '<button id="unpublishBtn">取消发布</button>' : '<button id="finalPublishBtn">提交发布</button>') +
    (submitted.length ? `<span class="inline-ctl"><select id="returnSel">${submitted.map((x) => `<option value="${x.id}">${esc(x.name)} · ${esc(x.submitted_at || '')}</option>`).join('')}</select><button id="returnBtn">退回提交</button></span>` : '') +
    EXPORT_BTNS;
  const row = sheetTitleRow(
    `<span class="chip ${isFinal ? 'green' : 'grey'}">${kindName}</span><span class="sb-status" title="${esc(statusText)}">${statusText}</span>`,
    sheetTitle(p), actions);
  const grid = isFinal
    ? gridHTML({ gridData: detail.final_grid, statsArr: detail.final_day_stats, editableMode: p.published ? null : 'final', denomMode: 'quota' })
    : gridHTML({ gridData: detail.display_grid, statsArr: detail.display_day_stats, denomMode: 'limit' });
  return `<div class="sheet-fit"><div id="sheetWrap" class="sheet-flex">${sheetCardHTML(row, grid)}</div></div>`;
}

function exportXlsx() {
  fetch(apiUrl(`/api/plans/${detail.plan.id}/export.xlsx`), { headers: { Authorization: 'Bearer ' + token } })
    .then((res) => { if (!res.ok) throw new Error('导出失败'); return res.blob(); })
    .then((blob) => {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `示例科室排班表-${detail.plan.year}年${detail.plan.month}月.xlsx`;
      a.click();
      URL.revokeObjectURL(a.href);
    })
    .catch((e) => toast(e.message, true));
}

async function exportImage() {
  try {
    if (typeof html2canvas === 'undefined') throw new Error('图片组件未加载（可能无网络），请改用 Excel 导出');
    const src = document.querySelector('#sheetWrap .card') || $('view');
    /* v6.6：导出图顶部只留居中标题「示例科室排班表（M月）」——克隆
       卡片后把标题行换成纯标题：不带左区状态文字、右区按钮，也不
       带页面标题里的天数与个人后缀（谁导出都一样）。离屏快照克隆
       节点，页面本身一字不动；网格/统计行/底部图例照旧。 */
    const node = src.cloneNode(true);
    const titleRow = node.querySelector('.sheet-title-row');
    if (titleRow) {
      titleRow.innerHTML = `<h2 class="grid-title">示例科室排班表（${detail.plan.month}月）</h2>`;
      titleRow.style.justifyContent = 'center';
    }
    node.style.width = `${src.offsetWidth}px`;
    const holder = document.createElement('div');
    holder.style.cssText = 'position:fixed;left:-10000px;top:0;';
    holder.appendChild(node);
    document.body.appendChild(holder);
    try {
      const canvas = await html2canvas(node, { scale: 2, backgroundColor: '#FFFFFF' });
      const a = document.createElement('a');
      a.href = canvas.toDataURL('image/png');
      a.download = `示例科室排班表-${detail.plan.year}年${detail.plan.month}月.png`;
      a.click();
    } finally {
      holder.remove();
    }
  } catch (e) { toast('导出图片失败：' + e.message, true); }
}

function bindSheet() {
  const x = $('expXlsx'); if (x) x.addEventListener('click', exportXlsx);
  const i = $('expImg'); if (i) i.addEventListener('click', exportImage);
  // v3.0：超管合并排班表还需绑定标题行里的工作流按钮与（最终表状态下的）点格编辑；
  // bindMemberSheet 末尾也调用本函数，但其场景 myRole() 必非 super，不会误绑。
  if (me && myRole() === 'super') bindProcess();
}

/* ---------------- 管理：规则设置 ---------------- */
function viewRules() {
  if (myRole() !== 'super') return '<div class="card">需要超级管理员权限。</div>';
  const now = new Date();
  let html = `<div class="card"><h3>新建月度计划</h3>
    <div class="form-grid">
      <label>年份<input id="npYear" type="number" value="${now.getFullYear()}" style="width:90px"></label>
      <label>月份<input id="npMonth" type="number" min="1" max="12" value="${now.getMonth() + 1}" style="width:70px"></label>
      <label>应休天数 Q<input id="npQuota" type="number" min="0" value="9" style="width:70px"></label>
      <label>自选上限 S<input id="npSelf" type="number" min="0" value="6" style="width:70px"></label>
      <label>先行组<select id="npFirst"><option value="">自动（奇数月A/偶数月B）</option><option value="A">A组</option><option value="B">B组</option></select></label>
      <button id="createPlanBtn" class="primary">新建计划</button>
    </div></div>`;
  if (detail) {
    const p = detail.plan;
    html += `<div class="card"><h3>当前计划设置 · ${p.year}年${p.month}月</h3>
    <div class="form-grid">
      <label>应休天数 Q<input id="psQuota" type="number" min="0" value="${p.quota}" style="width:70px"></label>
      <label>自选上限 S<input id="psSelf" type="number" min="0" value="${p.self_limit}" style="width:70px"></label>
      <label>本月先行组<select id="psFirst"><option value="A" ${p.first_group === 'A' ? 'selected' : ''}>A组</option><option value="B" ${p.first_group === 'B' ? 'selected' : ''}>B组</option></select></label>
      <label>阶段覆盖（演示/特殊情况）<select id="psPhase">
        <option value="" ${p.phase_override == null ? 'selected' : ''}>按日期自动</option>
        ${[0, 1, 2, 3].map((v) => `<option value="${v}" ${p.phase_override === v ? 'selected' : ''}>${['0 未开放', '1 仅科长', '2 科长+先行组', '3 全部开放'][v]}</option>`).join('')}
      </select></label>
      <button id="saveSettingsBtn" class="primary">保存设置</button>
    </div>
    </div>
    <div class="card"><h3>每日在岗硬约束（系统强制，不可关闭）</h3>
    <div class="kv">
      <div><b>干部在岗</b>每天至少 5 人（9 名干部每日最多休 4 人）</div>
      <div><b>科领导在岗</b>每天至少 1 人（科长+副科长每日最多休 2 人）</div>
      <div><b>协管员在岗</b>每天至少 1 人（2 名协管员每日最多休 1 人，不计入干部名额）</div>
      <div><b>满员处理</b>达到上限的日期自动变灰，成员无法再选，服务端同步拒绝</div>
    </div></div>`;
  }
  return html;
}

async function createPlan() {
  try {
    const body = {
      year: Number($('npYear').value), month: Number($('npMonth').value),
      quota: Number($('npQuota').value), self_limit: Number($('npSelf').value),
      first_group: $('npFirst').value || null,
    };
    const r = await api('POST', '/api/plans', body);
    await loadPlans(r.id);
    toast('计划已创建');
    await renderRoute();
  } catch (e) { toast(e.message, true); }
}

async function saveSettings() {
  try {
    const phaseVal = $('psPhase').value;
    await api('PATCH', `/api/plans/${detail.plan.id}`, {
      quota: Number($('psQuota').value),
      self_limit: Number($('psSelf').value),
      first_group: $('psFirst').value,
      phase_override: phaseVal === '' ? null : Number(phaseVal),
      clear_phase_override: phaseVal === '',
    });
    await loadDetail(detail.plan.id);
    toast('设置已保存');
    await renderRoute();
  } catch (e) { toast(e.message, true); }
}

function bindRules() {
  const c = $('createPlanBtn'); if (c) c.addEventListener('click', createPlan);
  const s = $('saveSettingsBtn'); if (s) s.addEventListener('click', saveSettings);
}

/* ---------------- 超管合并排班表：工作流动作（原「数据管理」页，v3.0 并入排班表） ---------------- */
async function doPull() {
  if (!confirm('调取数据将用最新提交的源数据覆盖当前最终表，确认？')) return;
  try {
    const out = await api('POST', `/api/plans/${detail.plan.id}/pull-source`);
    detail = out;
    toast(`已调取：${out.pulled.members} 人提交、共 ${out.pulled.cells} 个选休格`);
    renderPlanbar();
    await renderRoute();
  } catch (e) { toast(e.message, true); }
}

async function doFinalAuto() {
  try {
    toast('正在求解补满…');
    const out = await api('POST', `/api/plans/${detail.plan.id}/final/autocomplete`);
    detail = out;
    toast(`补满完成：共补 ${out.autocomplete.filled} 天（求解器 ${out.autocomplete.solver}）`);
    renderPlanbar();
    await renderRoute();
  } catch (e) { toast(e.message, true); }
}

async function doFinalSave() {
  try {
    const out = await api('POST', `/api/plans/${detail.plan.id}/final/save`);
    toast('最终表已保存 ' + (out.final_saved_at || ''));
    await loadDetail(detail.plan.id);
    await renderRoute();
  } catch (e) { toast(e.message, true); }
}

async function doPublish() {
  if (!confirm('提交发布后，全员将看到最终表且成员不能再修改，确认发布？')) return;
  try {
    await api('POST', `/api/plans/${detail.plan.id}/publish`);
    await loadPlans(detail.plan.id);
    toast('已提交发布');
    await renderRoute();
  } catch (e) { toast(e.message, true); }
}

async function doUnpublish() {
  try {
    await api('POST', `/api/plans/${detail.plan.id}/unpublish`);
    await loadPlans(detail.plan.id);
    toast('已取消发布');
    await renderRoute();
  } catch (e) { toast(e.message, true); }
}

/* v3.0：原数据管理页的绑定入口，现由超管合并排班表的 bindSheet 调用——
   绑定标题行里的工作流按钮（v3.1 起与导出按钮同组）、退回控件与最终表点格编辑
   （非最终表状态下无可编辑格，自动空转）。 */
function bindProcess() {
  const map = { pullBtn: doPull, finalAutoBtn: doFinalAuto, finalSaveBtn: doFinalSave, finalPublishBtn: doPublish, unpublishBtn: doUnpublish };
  Object.entries(map).forEach(([id, fn]) => { const b = $(id); if (b) b.addEventListener('click', fn); });
  const returnBtn = $('returnBtn');
  if (returnBtn) returnBtn.addEventListener('click', async () => {
    const sel = $('returnSel');
    if (!sel || !sel.value) return;
    const person = detail.people.find((x) => x.id === Number(sel.value));
    if (!confirm(`确认退回「${person ? person.name : ''}」的提交？退回后该成员可修改并重新提交。`)) return;
    try {
      await api('POST', `/api/plans/${detail.plan.id}/return/${sel.value}`);
      toast('已退回，该成员可重新修改提交');
      await loadDetail(detail.plan.id);
      await renderRoute();
    } catch (e) { toast(e.message, true); }
  });
  bindGridCells($('view'), async (personId, day, symbol) => {
    try {
      const out = await api('PUT', `/api/plans/${detail.plan.id}/final/cell`, { person_id: personId, day, symbol });
      detail = out;
      renderPlanbar();
      await renderRoute();
      if (out.warnings && out.warnings.length) toast('已保存（含警告）：' + out.warnings.join('；'), true);
    } catch (e) { toast(e.message, true); }
  });
}

/* ---------------- 管理：人员与权限 ----------------
   v2.9：原「人员列表」+「账号权限」两张表合并为一张——一行一个人：
   姓名（输入框）| 类别（下拉）| 组别（下拉，科长为标签）| 角色（下拉）| 启用（勾选）| 密码（重置按钮）| 操作（保存）。
   v6.7：姓名后加「工号」列（输入框，随行保存一并 PUT；可作登录账号，
   协管员留空显示占位「无」）。
   v6.13：角色后加「可看他人岗位」列（勾选框，随行保存一并 PUT
   can_view_others）——授予后该成员在岗位显示页可看他人并导出他人
   图片，仅此一项授权，不改变其角色与其余任何权限。
   行「保存」串行调用两个既有接口：先 PUT /api/people/{id}（人员字段），
   再 PATCH /api/users/{uid}（角色/账号状态），任一失败都会明确 toast 报错。
   启用合并为一个勾选：人员 PUT 的 active 本就同步 users.active（后端既有逻辑），
   账号 PATCH 再写入同一值——停用即人员与账号同时停用、启用同时启用。
   超级管理员 admin 无对应人员行，固定保留在表末尾一行特殊行（角色/启用不可改）。 */
function viewPeoplePerms() {
  // v3.0：一屏自适应骨架（fit-view 锁高，见 style.css 的 .people-fit 系列规则）
  return '<div class="people-fit"><h2 class="section-title">人员与权限</h2><div id="peoplePermsSection"></div></div>';
}

function viewPeoplePermsTable() {
  if (myRole() !== 'super') return '<div class="card">需要超级管理员权限。</div>';
  const people = viewPeoplePerms._people || [];
  const users = viewPeoplePerms._users || [];
  const userByPerson = {};
  let adminUser = null;
  users.forEach((u) => {
    if (u.person_id) userByPerson[u.person_id] = u;
    else if (u.username === 'admin') adminUser = u;
  });
  let html = `<div class="card people-add-card"><h3>新增人员</h3>
    <div class="form-grid">
      <label>姓名<input id="addName" type="text" style="width:110px"></label>
      <label>类别<select id="addKind"><option value="cadre">科员</option><option value="deputy">副科长</option><option value="chief">科长</option><option value="assistant">协管员</option></select></label>
      <label>组别<select id="addGrp"><option value="A">A组</option><option value="B">B组</option></select></label>
      <button id="addPersonBtn" class="primary">新增（初始密码 123456）</button>
    </div></div>`;
  // v3.0：表格卡不再重复「人员与权限」标题（页面上方 section-title 已有）
  html += `<div class="card people-table-card"><table class="mini"><thead><tr><th>姓名</th><th>工号</th><th>类别</th><th>组别</th><th>角色</th><th>可看他人岗位</th><th>启用</th><th>密码</th><th>操作</th></tr></thead><tbody>`;
  people.forEach((p) => {
    const u = userByPerson[p.id];
    let grpSel;
    if (p.kind === 'chief') {
      grpSel = `<span class="tag">${esc(p.grp_label)}</span>`;
    } else if (p.kind === 'assistant') {
      grpSel = `<select id="pg-${p.id}"><option value="" ${!p.grp ? 'selected' : ''}>—</option><option value="A" ${p.grp === 'A' ? 'selected' : ''}>A组</option><option value="B" ${p.grp === 'B' ? 'selected' : ''}>B组</option></select>`;
    } else {
      grpSel = `<select id="pg-${p.id}"><option value="A" ${p.grp === 'A' ? 'selected' : ''}>A组</option><option value="B" ${p.grp === 'B' ? 'selected' : ''}>B组</option></select>`;
    }
    html += `<tr><td><input id="pn-${p.id}" value="${esc(p.name)}" style="width:100px"></td>
      <td><input id="pw-${p.id}" value="${esc(p.work_id || '')}" style="width:92px" inputmode="numeric" placeholder="无"></td>
      <td><select id="pk-${p.id}">${Object.entries(KIND_TAG).map(([k, v]) => `<option value="${k}" ${p.kind === k ? 'selected' : ''}>${v}</option>`).join('')}</select></td>
      <td>${grpSel}</td>
      <td>${u ? `<select id="ur-${u.id}"><option value="0" ${!u.is_admin ? 'selected' : ''}>普通成员</option><option value="1" ${u.is_admin ? 'selected' : ''}>管理员</option></select>` : '—'}</td>
      <td><input id="pv-${p.id}" type="checkbox" ${p.can_view_others ? 'checked' : ''}></td>
      <td><input id="pa-${p.id}" type="checkbox" ${p.active ? 'checked' : ''}></td>
      <td>${u ? `<button data-reset="${u.id}">重置为初始密码</button>` : '—'}</td>
      <td><button data-rowsave="${p.id}"${u ? ` data-user="${u.id}"` : ''}>保存</button></td></tr>`;
  });
  if (adminUser) {
    html += `<tr><td>${esc(adminUser.username)}</td><td>—</td><td>—</td><td>—</td>
      <td>超级管理员</td>
      <td>—</td>
      <td><input type="checkbox" checked disabled></td>
      <td><button data-reset="${adminUser.id}">重置为初始密码</button></td>
      <td></td></tr>`;
  }
  html += '</tbody></table></div>';
  return html;
}

async function bindPeoplePerms() {
  try {
    const [people, users] = await Promise.all([api('GET', '/api/people'), api('GET', '/api/users')]);
    viewPeoplePerms._people = people;
    viewPeoplePerms._users = users;
  } catch (e) { toast(e.message, true); }
  // 需要二次渲染以带上数据
  $('peoplePermsSection').innerHTML = viewPeoplePermsTable();
  const add = $('addPersonBtn');
  if (add) add.addEventListener('click', async () => {
    try {
      await api('POST', '/api/people', {
        name: $('addName').value.trim(), kind: $('addKind').value, grp: $('addGrp').value,
      });
      toast('人员已新增，初始密码 123456');
      await loadPlans(detail ? detail.plan.id : undefined);
      await renderRoute();
    } catch (e) { toast(e.message, true); }
  });
  document.querySelectorAll('[data-rowsave]').forEach((b) => {
    b.addEventListener('click', async () => {
      const pid = b.dataset.rowsave;
      const uid = b.dataset.user;
      const kind = $('pk-' + pid).value;
      const grpEl = $('pg-' + pid);
      const active = $('pa-' + pid).checked;
      try {
        await api('PUT', '/api/people/' + pid, {
          name: $('pn-' + pid).value.trim(),
          work_id: $('pw-' + pid).value.trim(),
          kind,
          grp: grpEl ? grpEl.value : undefined,
          can_view_others: $('pv-' + pid).checked,
          active,
        });
      } catch (e) { toast('人员信息保存失败：' + e.message, true); return; }
      if (uid) {
        try {
          await api('PATCH', '/api/users/' + uid, {
            is_admin: $('ur-' + uid).value === '1', active,
          });
        } catch (e) { toast('人员信息已保存，但账号设置保存失败：' + e.message, true); return; }
      }
      toast('已保存');
      await loadPlans(detail ? detail.plan.id : undefined);
      await renderRoute();
    });
  });
  document.querySelectorAll('[data-reset]').forEach((b) => {
    b.addEventListener('click', async () => {
      if (!confirm('确认重置该账号密码为初始密码？')) return;
      try {
        await api('PATCH', '/api/users/' + b.dataset.reset, { reset_password: true });
        toast('密码已重置');
      } catch (e) { toast(e.message, true); }
    });
  });
}

/* ---------------- 管理：历史数据 ---------------- */
function viewHistory() {
  if (myRole() !== 'super') return '<div class="card">需要超级管理员权限。</div>';
  const list = viewHistory._list || [];
  let html = `<div class="card"><h3>历史数据（近 12 个月）</h3>
    <table class="mini"><thead><tr><th>计划</th><th>应休/自选</th><th>提交人数</th><th>最终表</th><th>发布</th><th>创建时间</th><th>操作</th></tr></thead><tbody>`;
  list.forEach((p) => {
    html += `<tr><td>${p.year}年${p.month}月</td><td>${p.quota} / ${p.self_limit}</td>
      <td>${p.submitted_members} / ${p.total_members}</td>
      <td>${p.final_exists ? '有' : '无'}</td><td>${p.published ? '已发布' : '未发布'}</td>
      <td>${esc(p.created_at || '')}</td>
      <td><button data-hist="${p.id}">查看提交记录</button></td></tr>`;
  });
  html += '</tbody></table><div id="histDetail"></div></div>';
  return html;
}

async function bindHistory() {
  try { viewHistory._list = await api('GET', '/api/history'); } catch (e) { toast(e.message, true); }
  $('view').innerHTML = viewHistory();
  document.querySelectorAll('[data-hist]').forEach((b) => {
    b.addEventListener('click', async () => {
      try {
        const subs = await api('GET', `/api/plans/${b.dataset.hist}/submissions`);
        const box = $('histDetail');
        if (!subs.length) { box.innerHTML = '<p class="hint">该计划暂无提交记录。</p>'; return; }
        box.innerHTML = `<h3 style="margin-top:14px">提交记录（全部版本）</h3>
          <table class="mini"><thead><tr><th>姓名</th><th>提交时间</th><th>选休天数</th><th>状态</th></tr></thead><tbody>` +
          subs.map((s) => `<tr><td>${esc(s.person_name)}</td><td>${esc(s.submitted_at)}</td><td>${Object.keys(s.data).length} 天</td><td>${s.returned ? '已退回' : '有效'}</td></tr>`).join('') +
          '</tbody></table>';
      } catch (e) { toast(e.message, true); }
    });
  });
}

/* ---------------- 超级管理员：日志管理（v2.6） ----------------
   两部分：① 管理员修改记录——人员管理员保存即生效的修改（applied）与
   v2.4 审批流历史、作废记录（void）；② 登录日志。审批流已撤销，本页无审批环节。
   v2.9：两板块左右并排。v3.1：卡头加计数徽标、表格斑马纹/悬停高亮，
   每卡一条前端筛选工具栏（对已加载的 200 条过滤，不走后端）：
   修改记录按 管理员/状态/对象姓名，登录日志按 账号/结果，各带「重置」。
   v4.3：本页启用 fit-view 一屏锁定，两卡表格区固定划出 20 条高度
   （.log-scroll 滚动区 + thead 粘性置顶，见 style.css v4.3 段）；
   两卡工具栏各加「从/到」日期筛选，与既有条件叠加，重置一并清空。
   v4.4：显示行不足 20 行时补 .filler-row 淡格线占位行凑满 20 行版面；
   两表全部 td 单行省略号截断（变更列加 title 悬停全文），行高严格
   固定 32px、左右逐行对齐（CSS 见 style.css v4.4 段）。 */
function logSymLabel(code) {
  return code ? symLabel(code) : '上班（空白）';
}

function logCountText(total, shown, active) {
  return active ? `筛选后 ${shown} 条 · 共 ${total} 条` : `共 ${total} 条`;
}

/* v4.4：当前显示行不足 20 行时补淡格线占位行，把版面凑满 20 行（与 v4.3 的
   20 行固定高度滚动区配套）。占位行纯视觉：不进入数据数组、不影响计数徽标
   与筛选逻辑；每次渲染/筛选按当前显示行数重算。空状态行占 1 行，调用方
   传入的 shownSlots 应把该行计入（0 条时传 1）。 */
function logFillerRows(shownSlots, colCount) {
  let s = '';
  for (let i = shownSlots; i < 20; i++) {
    s += `<tr class="filler-row"><td colspan="${colCount}">&nbsp;</td></tr>`;
  }
  return s;
}

function viewLogs() {
  if (myRole() !== 'super') return '<div class="card">需要超级管理员权限。</div>';
  const data = viewLogs._data;
  if (!data) return '<div class="card">正在加载日志…</div>';
  const mods = data.modifications || [];
  const logs = data.login_logs || [];
  const mf = logFilters.mod;
  const lf = logFilters.login;
  // 筛选下拉的选项由当前数据去重生成；已选值若已不在数据内，回落为「全部」
  const adminOpts = distinctVals(mods.map((a) => a.admin_name));
  if (mf.admin && !adminOpts.includes(mf.admin)) mf.admin = '';
  const statusOpts = distinctVals(mods.map((a) => a.status));
  if (mf.status && !statusOpts.includes(mf.status)) mf.status = '';
  const userOpts = distinctVals(logs.map((l) => l.username));
  if (lf.user && !userOpts.includes(lf.user)) lf.user = '';
  const resultOpts = distinctVals(logs.map(loginResultLabel));
  if (lf.result && !resultOpts.includes(lf.result)) lf.result = '';
  const targetKw = mf.target.trim();
  const modActive = !!(mf.admin || mf.status || targetKw || mf.from || mf.to);
  const modsShown = mods.filter((a) =>
    (!mf.admin || a.admin_name === mf.admin) &&
    (!mf.status || a.status === mf.status) &&
    (!targetKw || (a.target_name || '').includes(targetKw)) &&
    inDateRange(a.created_at, mf.from, mf.to));
  const logActive = !!(lf.user || lf.result || lf.from || lf.to);
  const logsShown = logs.filter((l) =>
    (!lf.user || l.username === lf.user) &&
    (!lf.result || loginResultLabel(l) === lf.result) &&
    inDateRange(l.created_at, lf.from, lf.to));
  const optsHTML = (vals, cur, labelFn) =>
    `<option value="" ${!cur ? 'selected' : ''}>全部</option>` +
    vals.map((v) => `<option value="${esc(v)}" ${v === cur ? 'selected' : ''}>${esc(labelFn ? labelFn(v) : v)}</option>`).join('');
  /* v2.9：两个板块左右并排（.logs-cols 网格，修改记录略宽），窄屏回单列 */
  let html = '<div class="logs-cols"><div class="card logs-col"><h3>🧾 管理员修改记录（最近 200 条）' +
    `<span class="log-count">${logCountText(mods.length, modsShown.length, modActive)}</span></h3>`;
  if (!mods.length) {
    html += '<p class="hint">暂无修改记录。</p>';
  } else {
    html += '<div class="log-tools">' +
      `<label>管理员<select id="modAdminF">${optsHTML(adminOpts, mf.admin)}</select></label>` +
      `<label>状态<select id="modStatusF">${optsHTML(statusOpts, mf.status, (v) => ADJ_STATUS_LABEL[v] || v)}</select></label>` +
      `<input id="modTargetF" type="text" placeholder="对象姓名" value="${esc(mf.target)}">` +
      `<label>从<input id="modFromF" type="date" value="${esc(mf.from)}"></label>` +
      `<label>到<input id="modToF" type="date" value="${esc(mf.to)}"></label>` +
      '<button id="modResetF" type="button">重置</button></div>';
    html += '<div class="log-scroll"><table class="mini"><thead><tr><th>时间</th><th>管理员</th><th>对象</th><th>日期</th><th>变更（旧 → 新）</th><th>状态</th></tr></thead><tbody>';
    if (!modsShown.length) {
      html += '<tr><td colspan="6" class="empty-row">没有符合条件的记录</td></tr>';
    }
    modsShown.forEach((a) => {
      const change = `${logSymLabel(a.old_symbol)} → ${logSymLabel(a.symbol)}`;
      html += `<tr><td>${esc(a.created_at || '')}</td><td>${esc(a.admin_name)}</td><td>${esc(a.target_name)}</td>
        <td>${esc(a.plan_label || '')} ${a.day}日</td><td class="chg" title="${esc(change)}">${esc(change)}</td>
        <td>${adjStatusChip(a.status)}</td></tr>`;
    });
    html += logFillerRows(modsShown.length || 1, 6);
    html += '</tbody></table></div>';
  }
  html += '</div>';
  html += '<div class="card logs-col"><h3>🔐 登录日志（最近 200 条）' +
    `<span class="log-count">${logCountText(logs.length, logsShown.length, logActive)}</span></h3>`;
  if (!logs.length) {
    html += '<p class="hint">暂无登录记录。</p>';
  } else {
    html += '<div class="log-tools">' +
      `<label>账号<select id="loginUserF">${optsHTML(userOpts, lf.user)}</select></label>` +
      `<label>结果<select id="loginResultF">${optsHTML(resultOpts, lf.result)}</select></label>` +
      `<label>从<input id="loginFromF" type="date" value="${esc(lf.from)}"></label>` +
      `<label>到<input id="loginToF" type="date" value="${esc(lf.to)}"></label>` +
      '<button id="loginResetF" type="button">重置</button></div>';
    html += '<div class="log-scroll"><table class="mini"><thead><tr><th>时间</th><th>账号</th><th>结果</th><th>IP</th><th>User-Agent</th></tr></thead><tbody>';
    if (!logsShown.length) {
      html += '<tr><td colspan="5" class="empty-row">没有符合条件的记录</td></tr>';
    }
    logsShown.forEach((l) => {
      const ua = l.user_agent || '';
      html += `<tr><td>${esc(l.created_at || '')}</td><td>${esc(l.username)}</td>
        <td>${l.success ? '<span class="chip green">成功</span>' : '<span class="chip red">失败</span>'}</td>
        <td>${esc(l.ip || '—')}</td><td class="ua-cell" title="${esc(ua)}">${esc(ua)}</td></tr>`;
    });
    html += logFillerRows(logsShown.length || 1, 5);
    html += '</tbody></table></div>';
  }
  html += '</div></div>';
  return html;
}

/* 筛选控件变更后整页重渲染（数据已在本地，成本低），状态保存在 logFilters；
   对象姓名输入框重渲染后恢复焦点与光标，避免逐字输入时丢焦点。 */
function rerenderLogs(refocusTarget) {
  $('view').innerHTML = viewLogs();
  bindLogFilters();
  if (refocusTarget) {
    const el = $('modTargetF');
    if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); }
  }
}

function bindLogFilters() {
  const on = (id, ev, fn) => { const el = $(id); if (el) el.addEventListener(ev, fn); };
  on('modAdminF', 'change', (e) => { logFilters.mod.admin = e.target.value; rerenderLogs(false); });
  on('modStatusF', 'change', (e) => { logFilters.mod.status = e.target.value; rerenderLogs(false); });
  on('modTargetF', 'input', (e) => { logFilters.mod.target = e.target.value; rerenderLogs(true); });
  on('modFromF', 'change', (e) => { logFilters.mod.from = e.target.value; rerenderLogs(false); });
  on('modToF', 'change', (e) => { logFilters.mod.to = e.target.value; rerenderLogs(false); });
  on('modResetF', 'click', () => { logFilters.mod.admin = ''; logFilters.mod.status = ''; logFilters.mod.target = ''; logFilters.mod.from = ''; logFilters.mod.to = ''; rerenderLogs(false); });
  on('loginUserF', 'change', (e) => { logFilters.login.user = e.target.value; rerenderLogs(false); });
  on('loginResultF', 'change', (e) => { logFilters.login.result = e.target.value; rerenderLogs(false); });
  on('loginFromF', 'change', (e) => { logFilters.login.from = e.target.value; rerenderLogs(false); });
  on('loginToF', 'change', (e) => { logFilters.login.to = e.target.value; rerenderLogs(false); });
  on('loginResetF', 'click', () => { logFilters.login.user = ''; logFilters.login.result = ''; logFilters.login.from = ''; logFilters.login.to = ''; rerenderLogs(false); });
}

async function bindLogs() {
  try {
    viewLogs._data = await api('GET', '/api/logs');
  } catch (e) {
    toast(e.message, true);
    viewLogs._data = { modifications: [], login_logs: [] };
  }
  $('view').innerHTML = viewLogs();
  bindLogFilters();
}

/* ---------------- 视图：修改密码 ---------------- */
function viewPassword() {
  return `<div class="pw-wrap"><div class="card pw-card"><h3>修改密码</h3>
    <div class="form-grid" style="flex-direction:column;align-items:stretch">
      <label>旧密码<input id="pwOld" type="password" autocomplete="current-password"></label>
      <label>新密码<input id="pwNew" type="password" autocomplete="new-password" placeholder="至少 4 位"></label>
      <label>确认新密码<input id="pwNew2" type="password" autocomplete="new-password"></label>
      <button id="pwBtn" class="primary">确认修改</button>
      <span id="pwMsg"></span>
    </div></div></div>`;
}

function bindPassword() {
  const b = $('pwBtn');
  if (!b) return;
  b.addEventListener('click', async () => {
    const msg = $('pwMsg');
    if ($('pwNew').value !== $('pwNew2').value) {
      msg.innerHTML = '<span class="bad-msg">两次输入的新密码不一致</span>';
      return;
    }
    try {
      await api('POST', '/api/change-password', {
        old_password: $('pwOld').value, new_password: $('pwNew').value,
      });
      msg.innerHTML = '<span class="ok-msg">密码修改成功，下次登录请用新密码。</span>';
      $('pwOld').value = $('pwNew').value = $('pwNew2').value = '';
    } catch (e) {
      msg.innerHTML = '<span class="bad-msg">' + esc(e.message) + '</span>';
    }
  });
}

/* ---------------- 当日排班（v6.0；v6.1 班次按日轮替） ---------------- */
let dailyState = { date: '', ctx: null, form: null, savedSig: '', refreshed: false, refreshPending: false };
let mypostsDate = '';
let mypostsState = null;   // v6.4：最近一次 /api/daily/mine 结果（供「生成图片」取数）
let mypostsPersonId = null;   // v6.4：选人查看的目标人员（管理员/超管有选人框；v6.13 起被授权成员同样有）
/* v6.8：岗位显示的查看状态是模块级变量，SPA 切换账号不刷新页面——管理员
   选过的人若不清，会被下一个登录的普通成员带进本人视图请求（person_id
   越权 403 被当正文红字显示，本人岗位反而看不到）。登录/退出时统一清零；
   且 loadMyPosts 对成员永不附加 person_id（见该函数）。 */
function resetMyPostsState() { mypostsDate = ''; mypostsState = null; mypostsPersonId = null; }

/* 班次按日轮替（v6.1）：锚点 2026-11-02 为早班，逐日交替（与后端
   shift_for_date 同口径；服务端返回的 shift/shift_label 为准，
   此函数只用于日期旁徽标的即时显示）。 */
const SHIFT_ANCHOR_STR = '2026-11-02';
function shiftOfDateStr(s) {
  const a = datePartsOf(SHIFT_ANCHOR_STR), b = datePartsOf(s);
  const diff = Math.round((Date.UTC(b.y, b.m - 1, b.d) - Date.UTC(a.y, a.m - 1, a.d)) / 86400000);
  return ((diff % 2) + 2) % 2 === 0 ? 'morning' : 'evening';
}

function localDateStr(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function tomorrowStr() { const t = new Date(); t.setDate(t.getDate() + 1); return localDateStr(t); }
function todayStr() { return localDateStr(new Date()); }
function datePartsOf(s) { const [y, m, d] = String(s).split('-').map(Number); return { y, m, d }; }
function weekdayOf(s) { const p = datePartsOf(s); return ['日', '一', '二', '三', '四', '五', '六'][new Date(p.y, p.m - 1, p.d).getDay()]; }
function shiftDateStr(s, delta) { const p = datePartsOf(s); return localDateStr(new Date(p.y, p.m - 1, p.d + delta)); }
/* v6.16：早班 6 人方案新增 F 岗。字母全集 A–F；某日实际排的字母序
   以后端 ctx.letter_order 为准（早班 6 人=A–F、其余=A–E，已保存的
   5 人早班仍为 A–E）。表单内部恒持 A–F 六个键（未用字母为 null），
   保存时只提交该日字母序内的键。 */
const ALL_DAILY_LETTERS = ['A', 'B', 'C', 'D', 'E', 'F'];
function dailyLettersOf(ctx) {
  return (ctx && ctx.letter_order && ctx.letter_order.length)
    ? ctx.letter_order : ['A', 'B', 'C', 'D', 'E'];
}
function blankDailyLetters() {
  const o = {};
  ALL_DAILY_LETTERS.forEach((L) => { o[L] = null; });
  return o;
}
function dailySig(a) {
  if (!a) return '';
  return JSON.stringify({ l: a.leader_id || null, L: ALL_DAILY_LETTERS.map((k) => (a.letters || {})[k] || null) });
}

/* -------- 管理：生成当日排班 -------- */
function viewDaily() {
  if (myRole() !== 'super' && myRole() !== 'admin') return '<div class="card">需要管理员权限。</div>';
  /* v6.18：管理员「生成排班」默认日期改回明天（用户 2026-11-02 指定，
     管理员通常提前一天排次日班）；岗位显示与成员当日排班仍默认今天
     （v6.15 口径不变），三页不再统一。 */
  if (!dailyState.date) dailyState.date = tomorrowStr();
  return `<div class="card"><h3>生成排班</h3>
    <div class="form-grid daily-controls">
      <label>日期<input id="dailyDate" type="date" value="${dailyState.date}"></label>
      <span class="chip daily-shift-badge" id="dailyShiftBadge">${shiftOfDateStr(dailyState.date) === 'morning' ? '早班' : '晚班'}</span>
      <span class="hint">班次按日轮替：11月2日早班、3日晚班，逐日交替（默认明天，改日期会自动重新载入）</span>
    </div>
    <div id="dailyBody"><p class="hint">正在加载…</p></div>
  </div>`;
}

function bindDaily() {
  const di = $('dailyDate');
  if (di) di.addEventListener('change', () => {
    dailyState.date = di.value || tomorrowStr();
    const badge = $('dailyShiftBadge');
    if (badge) badge.textContent = shiftOfDateStr(dailyState.date) === 'morning' ? '早班' : '晚班';
    loadDaily();
  });
  loadDaily();
}

/* v6.28「刷新人数」（用户 2026-11-11 定）：「刷新人数」按钮先置
   dailyState.refreshPending 再调本函数，本函数据此带 refresh=1
   重新采集最新排班表——后端按最新当天在岗干部数重判方案
   （5 人 A–E / 6 人方案 A–F），表单改用按最新人数生成的
   默认排班，不再被已保存的旧人数方案锁住。刷新本身不落库：
   已保存版本仍在，管理员确认后点「保存排班」才生效。 */
async function loadDaily() {
  const refresh = !!dailyState.refreshPending;
  dailyState.refreshPending = false;
  const body = $('dailyBody');
  if (!body) return;
  body.innerHTML = '<p class="hint">正在加载…</p>';
  try {
    const ctx = await api('GET', `/api/daily/context?date=${dailyState.date}${refresh ? '&refresh=1' : ''}`);
    dailyState.ctx = ctx;
    dailyState.refreshed = !!refresh;
    const init = refresh ? ctx.default : (ctx.saved || ctx.default);
    const letters = blankDailyLetters();
    Object.assign(letters, init.letters || {});
    dailyState.form = { leader_id: init.leader_id || null, letters };
    dailyState.savedSig = ctx.saved ? dailySig(ctx.saved) : '';
    renderDailyBody();
    if (refresh) {
      const order = dailyLettersOf(ctx);
      toast(`已刷新人数：当天在岗干部 ${ctx.on_duty_cadre.length} 人，当前为 ${order.length} 个字母岗（${order[0]}–${order[order.length - 1]}），确认后点「保存排班」生效`);
    }
  } catch (e) {
    dailyState.ctx = null;
    body.innerHTML = `<p class="bad-msg">${esc(e.message)}</p>`;
  }
}

function dailyHistText(pid) {
  const h = (dailyState.ctx.history_stats || {})[pid];
  if (!h) return '暂无';
  const parts = ALL_DAILY_LETTERS.filter((L) => h[L] > 0).map((L) => `${L}×${h[L]}`);
  return parts.length ? `${parts.join(' · ')} · 共${h.total}` : '暂无';
}

function dailyPreviewHTML() {
  const ctx = dailyState.ctx;
  const L = dailyState.form.letters;
  const nm = (letter) => (L[letter] ? esc(ctx.names[L[letter]] || '') : '—');
  if (ctx.shift === 'morning') {
    /* v6.16：早班两套模板列结构随模板首段岗位名生成，不再硬编码
       列名（两套模板岗位名相同：审图/申报/挑查/备勤，v6.17 口径）。 */
    const heads = (ctx.template[0] ? ctx.template[0].posts : []).map((p) => p.post);
    const rows = ctx.template.map((slot) => {
      const cells = slot.posts.map((p) => `<td>${p.letters.map(nm).join('+')}</td>`).join('');
      return `<tr><td>${slot.start}–${slot.end}</td>${cells}</tr>`;
    }).join('');
    return `<table class="daily-table"><tr><th>时间</th>${heads.map((h) => `<th>${esc(h)}</th>`).join('')}</tr>${rows}</table>`;
  }
  const rows = ctx.template.map((slot) => {
    const shentu = slot.posts.filter((p) => p.post === '审图查验岗');
    const shenbao = slot.posts.filter((p) => p.post === '申报岗');
    const stTxt = shentu.length ? shentu[0].letters.map(nm).join('+') : '';
    let sbTxt = '';
    if (shenbao.length > 1) sbTxt = shenbao.map((p) => p.letters.map(nm).join('+')).join('+') + '（各半小时）';
    else if (shenbao.length === 1) sbTxt = shenbao[0].letters.map(nm).join('+') + (shenbao[0].note ? `（${shenbao[0].note}）` : '');
    return `<tr><td>${slot.start}–${slot.end}</td><td>${stTxt}</td><td>${sbTxt}</td></tr>`;
  }).join('');
  return `<table class="daily-table"><tr><th>时间</th><th>审图查验岗</th><th>申报岗</th></tr>${rows}</table>`;
}

function renderDailyBody() {
  const body = $('dailyBody');
  const ctx = dailyState.ctx;
  if (!body || !ctx) return;
  const badge = $('dailyShiftBadge');
  if (badge) badge.textContent = ctx.shift_label;
  const f = dailyState.form;
  /* v6.6：字母岗下拉列出全部在岗干部、不禁用任何人。改选已在其他
     岗的人时由 onDailyLetterChange 走「抢占」口径——自动清空其原
     岗（见 stealLetterPost），不再用 disabled 把管理员堵死。 */
  const letterSel = (L) => `<label>${L} 岗<select id="dl-${L}" class="daily-letter-sel">
      <option value="" ${!f.letters[L] ? 'selected' : ''}>— 未定 —</option>
      ${ctx.on_duty_cadre.map((p) => `<option value="${p.id}" ${f.letters[L] === p.id ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}
    </select></label>`;
  const leaderOpts = ctx.on_duty_leaders.map((p) =>
    `<option value="${p.id}" ${f.leader_id === p.id ? 'selected' : ''}>${esc(p.name)}（${esc(p.kind_label)}）</option>`).join('');
  const savedNote = dailyState.refreshed
    ? `<span class="chip">已刷新人数 · 未保存</span> <span class="hint">已按最新排班表重新采集：当天在岗干部 ${ctx.on_duty_cadre.length} 人${ctx.saved ? '；此前已保存的版本仍在，确认后点「保存排班」才替换' : ''}</span>`
    : (ctx.saved
      ? `<span class="chip chip-final">已保存</span> <span class="hint">更新于 ${esc(ctx.saved.updated_at || '')}</span>`
      : '<span class="chip">未保存</span> <span class="hint">当前为按全员历史均衡生成的默认排班，可调整后保存</span>');
  const roster = ctx.on_duty_cadre.map((p) =>
    `<tr><td><b>${esc(p.name)}</b> <span class="muted">${esc(p.kind_label)}${p.grp ? ' · ' + esc(p.grp_label) : ''}</span></td><td>${dailyHistText(p.id)}</td></tr>`).join('');
  const offLine = ctx.off_duty.length
    ? `<p class="hint">当天休假（不排岗）：${ctx.off_duty.map((p) => esc(p.name)).join('、')}</p>` : '';
  /* v6.31：退税岗所有班次都带——早班同样显示本行（此前仅晚班）。 */
  const taxRow = `<div class="form-grid"><label>退税岗（自动）<input type="text" disabled value="${ctx.on_duty_assistants.length ? ctx.on_duty_assistants.map((p) => p.name).join('、') : '今日无协管员在岗'}"></label>
       <span class="hint">当天在岗的协管员全部上退税岗，无需手动选。</span></div>`;
  const dirty = dailySig(f) !== dailyState.savedSig;
  const imgBtn = ctx.saved
    ? `<button id="dailyImgBtn" ${dirty ? 'disabled' : ''}>生成图片</button>${dirty ? '<span class="hint">改动未保存，先点「保存排班」再生成图片</span>' : ''}`
    : '<button disabled>生成图片</button><span class="hint">保存后可生成图片</span>';
  /* v6.30：复制岗位按钮恒在生成图片右边、不随未保存置灰——复制的
     是表单当前选中的岗位（dailyCopyText 读 dailyState.form），改完
     没保存也能先复制；未排满的岗在文本里记「未定」。 */
  const copyBtn = '<button id="dailyCopyBtn">复制岗位</button>';
  body.innerHTML = `
    <p>${savedNote} ${ctx.variant === 'morning6' ? '<span class="chip">早班 6 人方案（A–F）</span>' : ''} ${ctx.variant === 'evening6' ? '<span class="chip">晚班 6 人方案（A–F）</span>' : ''} ${ctx.variant === 'morning6' && ctx.on_duty_cadre.length >= 7 ? '<span class="hint">在岗 7 人及以上：值班科长只任带班、不参与字母排班（默认排班口径，可手动调整）</span>' : ''} ${ctx.variant === 'evening6' && ctx.on_duty_cadre.length >= 7 ? '<span class="hint">在岗 7 人及以上：带班科长只任带班、不参与字母排班（默认排班口径，可手动调整）</span>' : ''} ${ctx.variant === 'evening6' ? '<span class="hint">晚班 6 人方案：审图两组与申报岗各管各岗、不再交叉顶岗；带班由三位科领导按历史带班次数轮流</span>' : ''} ${ctx.variant === 'morning6' ? '<span class="hint">早班 6 人方案：A–D 固定查验岗、E/F 固定申报岗，8:30–10:30 挑查归不当申报的 E/F；恰 6 人时 B 岗固定为带班（默认排班口径，可手动调整）</span>' : ''} <span class="hint">· 在岗判定依据：${{ final: '最终表', source: '提交源数据汇总', draft: '草稿汇总' }[ctx.display_kind] || ''}</span></p>
    <div class="form-grid">
      <label>带班（值班科长）<select id="dlLeader">${leaderOpts}</select></label>
      ${dailyLettersOf(ctx).map(letterSel).join('')}
    </div>
    ${taxRow}
    <div class="form-grid daily-actions">
      <button id="dailySaveBtn" class="primary">保存排班</button>
      <button id="dailyRefreshBtn">刷新人数</button>
      <button id="dailyResetBtn">按轮换重置默认</button>
      ${imgBtn}
      ${copyBtn}
    </div>
    <h4>时段预览（${esc(ctx.shift_label)}）</h4>
    ${dailyPreviewHTML()}
    <h4>当天在岗干部 · 本班次历史累计（默认排班按此均衡）</h4>
    <table class="daily-table daily-roster"><tr><th>人员</th><th>历史岗位（字母×次数）</th></tr>${roster}</table>
    ${offLine}`;
  const leaderSel = $('dlLeader');
  if (leaderSel) leaderSel.addEventListener('change', () => { dailyState.form.leader_id = leaderSel.value ? Number(leaderSel.value) : null; renderDailyBody(); });
  dailyLettersOf(ctx).forEach((L) => {
    const sel = $('dl-' + L);
    if (sel) sel.addEventListener('change', () => onDailyLetterChange(L, sel.value));
  });
  const sv = $('dailySaveBtn'); if (sv) sv.addEventListener('click', saveDaily);
  const rf = $('dailyRefreshBtn'); if (rf) rf.addEventListener('click', () => { dailyState.refreshPending = true; loadDaily(); });
  const rs = $('dailyResetBtn'); if (rs) rs.addEventListener('click', () => {
    const d = dailyState.ctx.default;
    const letters = blankDailyLetters();
    Object.assign(letters, d.letters || {});
    dailyState.form = { leader_id: d.leader_id || null, letters };
    renderDailyBody();
    toast('已按全员历史均衡重置为默认排班');
  });
  const im = $('dailyImgBtn'); if (im) im.addEventListener('click', dailyImage);
  const cp = $('dailyCopyBtn'); if (cp) cp.addEventListener('click', copyDailyPosts);
}

/* v6.6「抢占」：把 pid 当前占用的其他字母岗清空（回到未定），
   返回被清掉的岗字母；没有占用时返回 null。只动 letters——带班
   （leader_id）可与字母岗重合，与字母改选互不影响。 */
function stealLetterPost(letter, pid) {
  const f = dailyState.form;
  let cleared = null;
  ALL_DAILY_LETTERS.forEach((o) => {
    if (o !== letter && pid && f.letters[o] === pid) {
      f.letters[o] = null;
      cleared = o;
    }
  });
  return cleared;
}

function onDailyLetterChange(letter, val) {
  const f = dailyState.form;
  const pid = val ? Number(val) : null;
  if (pid) {
    const cleared = stealLetterPost(letter, pid);
    if (cleared) {
      const name = (dailyState.ctx.names || {})[pid] || '该人员';
      toast(`${name} 已从 ${cleared} 岗移除，改排到 ${letter} 岗`);
    }
  }
  f.letters[letter] = pid;
  renderDailyBody();
}

async function saveDaily() {
  const f = dailyState.form;
  if (!f.leader_id) { toast('请选择带班（值班科长）', true); return; }
  /* v6.16：按该日字母序（letter_order）校验与提交——6 人早班须排满
     A–F、其余排满 A–E；表单里未用字母的 null 不进请求体。 */
  const order = dailyLettersOf(dailyState.ctx);
  const missing = order.filter((L) => !f.letters[L]);
  if (missing.length) { toast(`岗位未排满：${missing.join('、')} 岗还没选人`, true); return; }
  const letters = {};
  order.forEach((L) => { letters[L] = f.letters[L]; });
  try {
    const out = await api('POST', '/api/daily/assignments', {
      date: dailyState.date,
      leader_id: f.leader_id, letters,
    });
    dailyState.ctx.saved = out.saved;
    dailyState.savedSig = dailySig(out.saved);
    dailyState.refreshed = false;
    toast('当日排班已保存');
    renderDailyBody();
  } catch (e) { toast(e.message, true); }
}

/* v6.30「复制岗位」（用户 2026-11-11 定）：「生成排班」页在
   「生成图片」右边加「复制岗位」按钮，把当前岗位信息复制成
   纯文本、直接粘贴到微信等地。文本格式按用户给的示例：
   第一行「X月X日 早班/晚班」、第二行「带班：X」、第三行各
   字母岗一行排开「A：X B：X …」（6 人方案带 F），末行加
   一行「退税岗：X」（当天在岗协管员）。内容取表单当前选中的
   带班与字母岗（不要求先保存），未排满的岗记「未定」。
   v6.31（用户 2026-11-11 续定）：退税岗所有班次都要带上——
   v6.30 初版早班不带此行，用户明确所有班次都带，改为恒带。 */
function dailyCopyText(ctx, form) {
  const p = datePartsOf(ctx.date);
  const nm = (pid) => (ctx.names || {})[pid] || '未定';
  const lines = [
    `${p.m}月${p.d}日 ${ctx.shift_label || ''}`,
    `带班：${form.leader_id ? nm(form.leader_id) : '未定'}`,
    dailyLettersOf(ctx).map((L) => `${L}：${form.letters[L] ? nm(form.letters[L]) : '未定'}`).join(' '),
  ];
  const tax = (ctx.on_duty_assistants || []).map((a) => a.name).filter(Boolean);
  lines.push(`退税岗：${tax.length ? tax.join(' ') : '无'}`);
  return lines.join('\n');
}

/* 剪贴板写入：站点是 http（非安全上下文）时 navigator.clipboard
   多半不可用，回退到临时 textarea + execCommand('copy')。 */
async function copyTextToClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.cssText = 'position:fixed;left:-10000px;top:0;opacity:0;';
  document.body.appendChild(ta);
  ta.select();
  try {
    if (!document.execCommand('copy')) throw new Error('浏览器拒绝了复制操作');
  } finally {
    ta.remove();
  }
}

async function copyDailyPosts() {
  const ctx = dailyState.ctx;
  if (!ctx || !dailyState.form) { toast('排班还没加载完，请稍候', true); return; }
  try {
    await copyTextToClipboard(dailyCopyText(ctx, dailyState.form));
    toast('岗位已复制，可直接粘贴');
  } catch (e) { toast('复制失败：' + e.message, true); }
}

/* v6.22：导图卡片 HTML（纯函数，供 dailyImage 与测试共用）。
   早晚班统一为用户确认的时段表格式（其 2026-11-02 发来的早班图
   样）：标题「X月X日 早班/晚班」+「带班：X」+ 整张时段表；晚班
   在带班行下多一行「退税岗：X」。晚班不再用旧图4
   四行文案版。列与行均随模板生成：早班列随首段岗位名（两套模板
   通用），晚班固定审图查验岗/申报岗两列、申报多段同格合并并注
   「（各半小时）」（与页面预览、成员当日排班导图同口径）。
   v6.29（用户 2026-11-11 定）：带班、退税岗不再各占一行，挪到
   标题行最右边（标题左、带班/退税右，同一行），省图面高度；
   字号保持 20px 不缩。成员当日排班导图（dayViewImage）同此理。 */
function dailyImageCardHTML(ctx, saved, names) {
  const p = datePartsOf(ctx.date);
  const L = saved.letters;
  const nmL = (letter) => esc(names[L[letter]] || '—');
  const cell = 'border:1px solid #999999;padding:6px 10px;text-align:center;vertical-align:middle;';
  let heads, rows;
  if (ctx.shift === 'morning') {
    heads = (ctx.template[0] ? ctx.template[0].posts : []).map((pp) => pp.post);
    rows = ctx.template.map((slot) => {
      const cells = slot.posts.map((pp) => `<td style="${cell}">${pp.letters.map(nmL).join('+')}</td>`).join('');
      return `<tr><td style="${cell}">${slot.start}–${slot.end}</td>${cells}</tr>`;
    }).join('');
  } else {
    heads = ['审图查验岗', '申报岗'];
    rows = ctx.template.map((slot) => {
      const shentu = slot.posts.filter((pp) => pp.post === '审图查验岗');
      const shenbao = slot.posts.filter((pp) => pp.post === '申报岗');
      const stTxt = shentu.length ? shentu[0].letters.map(nmL).join('+') : '';
      let sbTxt = '';
      if (shenbao.length > 1) sbTxt = shenbao.map((pp) => pp.letters.map(nmL).join('+')).join('+') + '（各半小时）';
      else if (shenbao.length === 1) sbTxt = shenbao[0].letters.map(nmL).join('+') + (shenbao[0].note ? `（${esc(shenbao[0].note)}）` : '');
      return `<tr><td style="${cell}">${slot.start}–${slot.end}</td><td style="${cell}">${stTxt}</td><td style="${cell}">${sbTxt}</td></tr>`;
    }).join('');
  }
  const taxNames = (saved.tax_ids || []).map((pid) => names[pid]).filter(Boolean);
  /* v6.31：退税岗所有班次都带——早班导图标题行同样带退税岗。 */
  const taxHTML = `<span style="margin-left:24px;">退税岗：${taxNames.length ? taxNames.map(esc).join(' ') : '无'}</span>`;
  /* v6.16：早班 6 人模板每格双人名更宽，卡片宽度随之放宽到 900px。 */
  return `<div style="background:#FFFFFF;color:#111111;width:${L.F && ctx.shift === 'morning' ? 900 : 760}px;padding:28px 32px;font-family:'PingFang SC','Microsoft YaHei',sans-serif;">
        <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:12px;">
          <span style="font-size:24px;font-weight:700;">${p.m}月${p.d}日 ${esc(ctx.shift_label || '')}</span>
          <span style="font-size:20px;text-align:right;">带班：${esc(names[saved.leader_id] || '')}${taxHTML}</span>
        </div>
        <table style="border-collapse:collapse;width:100%;font-size:17px;"><tr><th style="${cell}">时间</th>${heads.map((h) => `<th style="${cell}">${esc(h)}</th>`).join('')}</tr>${rows}</table>
      </div>`;
}

async function dailyImage() {
  const ctx = dailyState.ctx;
  const saved = ctx && ctx.saved;
  if (!saved) { toast('请先保存排班再生成图片', true); return; }
  try {
    if (typeof html2canvas === 'undefined') throw new Error('图片组件未加载（可能无网络）');
    const cardHTML = dailyImageCardHTML(ctx, saved, ctx.names || {});
    const holder = document.createElement('div');
    holder.style.cssText = 'position:fixed;left:-10000px;top:0;';
    holder.innerHTML = cardHTML;
    document.body.appendChild(holder);
    try {
      const canvas = await html2canvas(holder.firstElementChild, { scale: 2, backgroundColor: '#FFFFFF' });
      const a = document.createElement('a');
      a.href = canvas.toDataURL('image/png');
      a.download = `当日排班-${ctx.date}-${ctx.shift_label}.png`;
      a.click();
    } finally {
      holder.remove();
    }
  } catch (e) { toast('生成图片失败：' + e.message, true); }
}

/* -------- 成员：岗位显示 -------- */
/* v6.4：管理员/超管多一个「人员」选人框，可查看任一人的岗位并导出其
   图片；普通成员无选人框、只能看自己（后端 person_id 越权 403 兜底）。
   超管账号无对应人员，靠选人使用本页（默认名单第一人）。
   v6.13：选人资格放宽——被超管在「人员与权限」授予 can_view_others
   的成员（首批两名协管员）同样有选人框、可看他人并导出他人图片；
   授权取自进页时 /api/me 的最新值（me.can_view_others），不读旧快照。
   未授权成员仍无选人框、请求永不带 person_id（v6.8 守卫不变）。 */
function canPickPerson() { return myRole() === 'admin' || myRole() === 'super' || !!(me && me.can_view_others); }

function viewMyPosts() {
  if (!canPickPerson() && (!me || !me.person_id)) return '<div class="card">您的账号未对应具体人员，暂无岗位显示。</div>';
  /* v6.15：岗位显示默认日期改为今天（原为明天），回跳按钮文案随之
     改为回今天；成员「当日排班」页同为默认今天。管理员「生成排班」
     页 v6.18 起单独改回默认明天（提前排次日班），不在此列。 */
  if (!mypostsDate) mypostsDate = todayStr();
  const picker = canPickPerson()
    ? '<label>人员<select id="mpPerson"></select></label>' : '';
  return `<div class="card"><h3>岗位显示</h3>
    <div class="form-grid daily-controls">
      <button id="mpPrev">← 前一天</button>
      <label>日期<input id="mpDate" type="date" value="${mypostsDate}"></label>
      <button id="mpNext">后一天 →</button>
      <button id="mpToday">回到今天</button>
      ${picker}
    </div>
    <div id="mypostsBody"><p class="hint">正在加载…</p></div>
  </div>`;
}

function bindMyPosts() {
  const di = $('mpDate');
  if (di) di.addEventListener('change', () => { mypostsDate = di.value || todayStr(); loadMyPosts(); });
  const pv = $('mpPrev'); if (pv) pv.addEventListener('click', () => { mypostsDate = shiftDateStr(mypostsDate, -1); if (di) di.value = mypostsDate; loadMyPosts(); });
  const nx = $('mpNext'); if (nx) nx.addEventListener('click', () => { mypostsDate = shiftDateStr(mypostsDate, 1); if (di) di.value = mypostsDate; loadMyPosts(); });
  const tm = $('mpToday'); if (tm) tm.addEventListener('click', () => { mypostsDate = todayStr(); if (di) di.value = mypostsDate; loadMyPosts(); });
  const ps = $('mpPerson');
  if (ps) {
    ps.addEventListener('change', () => { mypostsPersonId = ps.value ? Number(ps.value) : null; loadMyPosts(); });
    /* v6.21：选人框选项不再一次性拉全员名单，改由每次 loadMyPosts
       按 mine 响应里的 on_duty_people（当天在岗名单）同步生成——
       只列当天上班的人；这里只给初始选中值（本人），超管无对应
       人员时先留空、由首次同步落到当天第一名在岗者。 */
    if (mypostsPersonId == null) mypostsPersonId = (me && me.person_id) || null;
  }
  loadMyPosts();
}

let mypostsPickerFix = false;

async function loadMyPosts() {
  const body = $('mypostsBody');
  if (!body) return;
  body.innerHTML = '<p class="hint">正在加载…</p>';
  const isFix = typeof mypostsPickerFix !== 'undefined' && mypostsPickerFix;
  mypostsPickerFix = false;
  const render = (out) => {
    mypostsState = out;
    body.innerHTML = myPostsHTML(out);
    const im = $('mpImgBtn'); if (im) im.addEventListener('click', myPostsImage);
    /* v6.21：选人框按当天在岗名单同步——选项只含当天上班的人；
       当前选中者当天休假（不在名单）时自动落到本人（在岗时）或
       名单第一人，并以新选中者重查一次（isFix 防循环）。 */
    const ps = $('mpPerson');
    if (ps && canPickPerson() && out) {
      const list = out.on_duty_people || [];
      ps.innerHTML = list.map((p) => `<option value="${p.id}">${esc(p.name)}</option>`).join('');
      if (list.length && !list.some((p) => p.id === mypostsPersonId)) {
        mypostsPersonId = (me && list.some((p) => p.id === me.person_id))
          ? me.person_id : list[0].id;
        if (!isFix && out.viewer && out.viewer.id !== mypostsPersonId) {
          mypostsPickerFix = true;
          loadMyPosts();
          return;
        }
      }
      if (mypostsPersonId) ps.value = String(mypostsPersonId);
    }
  };
  /* v6.8：person_id 只允许有选人资格者（管理员/超管，v6.13 起另加被
     授权成员）附加；未授权成员永远只查本人——模块级 mypostsPersonId
     即使残留着上一账号的选人值，成员请求也不会带上它，从源头杜绝
     成员本人视图触发后端「查看他人」403。 */
  const pid = canPickPerson() ? mypostsPersonId : null;
  const q = pid ? `&person_id=${pid}` : '';
  try {
    render(await api('GET', `/api/daily/mine?date=${mypostsDate}${q}`));
  } catch (e) {
    /* v6.8 兜底：成员本人视图万一仍收到该 403（任何残留路径），清状态后
       以纯本人请求重试一次，绝不把这句权限提示当作页面正文展示给成员。
       v6.13：后端 403 文案已改为「您没有查看他人岗位的权限」，匹配随之更新。 */
    if (!canPickPerson() && String(e.message).includes('您没有查看他人岗位的权限')) {
      mypostsPersonId = null;
      try { render(await api('GET', `/api/daily/mine?date=${mypostsDate}`)); return; }
      catch (e2) { body.innerHTML = `<p class="bad-msg">${esc(e2.message)}</p>`; return; }
    }
    body.innerHTML = `<p class="bad-msg">${esc(e.message)}</p>`;
  }
}

function myShiftCardHTML(label, e, selfName, words) {
  const head = `<h3>${label}</h3>`;
  if (!e || e.status === 'noplan') return `<div class="card">${head}<p class="hint">该月尚无排班计划。</p></div>`;
  if (e.status === 'none') return `<div class="card">${head}<p class="hint">尚未生成当日排班。</p></div>`;
  /* v6.4：本人当天确有岗位（字母岗/退税岗）时给出「生成图片」，方便
     每个人把自己的当日排班存成图片；休假/未生成/未排岗时不显示。
     v6.5：按钮从卡片底部移入「岗位」同一行（.post-line flex 行，按钮
     紧贴岗位文字右侧、垂直居中），不再单独占一行落在卡片底部。 */
  const imgBtn = '<button id="mpImgBtn">生成图片</button>';
  let inner = '';
  if (e.status === 'off') {
    inner = `<p>${words.subj}当天休假。</p>`;
  } else if (e.status === 'ok') {
    const rows = (e.timeline || []).map((t) =>
      `<tr><td>${t.time}</td><td>${esc(t.post)}${t.note ? `（${esc(t.note)}）` : ''}</td><td>${t.partners && t.partners.length ? t.partners.map(esc).join('、') : '—'}</td></tr>`).join('');
    inner = `<div class="post-line"><p>${words.poss}岗位：<span class="post-big">${esc(e.letter)}</span>岗</p>${imgBtn}</div>
      <table class="daily-table"><tr><th>时间</th><th>岗位</th><th>同岗同事</th></tr>${rows}</table>`;
  } else if (e.status === 'tax') {
    const others = (e.tax_names || []).filter((n) => n !== selfName);
    /* v6.11：无同岗协管员时不再渲染任何说明行（原「仅本人一名协管员
       在岗」提示已按用户要求去掉）；有同岗时才显示「同岗：X」一行。 */
    const partnerLine = others.length ? `<p class="hint">同岗：${others.map(esc).join('、')}</p>` : '';
    /* v6.31：退税岗所有班次都带——括号里跟实际班次（早班/晚班）。 */
    inner = `<div class="post-line"><p>${words.poss}岗位：<b>退税岗（${esc(label)}）</b></p>${imgBtn}</div>${partnerLine}`;
  } else if (e.status === 'na') {
    inner = `<p class="hint">当天无${words.poss}岗位安排。</p>`;
  } else {
    inner = `<p>当天未排${words.subj}上岗（备勤/其他工作）。</p>`;
  }
  const crewTxt = e.crew && e.crew.length ? e.crew.map((c) => `${c.letter} 岗 ${esc(c.name)}`).join(' · ') : '';
  const taxTxt = e.tax_names && e.tax_names.length ? ` ｜ 退税岗 ${e.tax_names.map(esc).join(' ')}` : '';
  const footer = `<p class="hint">带班：${esc(e.leader_name || '—')}${crewTxt ? ' ｜ ' + crewTxt : ''}${taxTxt}</p>`;
  return `<div class="card">${head}${inner}${footer}</div>`;
}

function myPostsHTML(out) {
  const p = datePartsOf(out.date);
  /* v6.4：选人查看他人时文案换成「某人的岗位 / 某人当天休假」，看自己
     时沿用「您的岗位 / 您当天休假」（is_self 由后端判定）。 */
  const isSelf = out.is_self !== false;
  const vname = out.viewer ? out.viewer.name : '';
  /* v6.11：原 words.only（单人退税岗时的提示文案）已随说明行口径
     取消而删除，words 只保留 poss/subj。 */
  const words = isSelf
    ? { poss: '您的', subj: '您' }
    : { poss: `${vname}的`, subj: vname };
  const head = `<p><b>${p.m}月${p.d}日（周${weekdayOf(out.date)}）· ${esc(out.shift_label || '')}</b>${out.off_symbol ? ` · ${words.subj}当天休假（<span class="sym-glyph">${esc(out.off_symbol)}</span>）` : ''}</p>`;
  if (!out.has_person) return head + '<div class="card"><p class="hint">您的账号未对应具体人员，暂无岗位显示。</p></div>';
  const selfName = out.viewer ? out.viewer.name : '';
  return head + myShiftCardHTML(out.shift_label || '', out.result, selfName, words);
}

/* v6.23：岗位显示个人导图卡片 HTML（纯函数，供 myPostsImage 与测试
   共用）。版式按用户 2026-11-03 定：图片里去掉带班行；岗位移到最
   上面、标题行姓名的右边。v6.24（同日续定）：标题行左侧已有姓名，
   右侧不再重复「您的/某人的岗位：」，只留岗位本身——「X岗」（字母
   蓝色大字）或「退税岗（班次）」；其下字母岗附时段表（时间/岗位/
   同岗同事）、退税岗附同岗说明行（v6.11 口径：有同岗才渲染）。
   页面本身不变。v6.31：退税岗所有班次都带，括号内跟实际班次。 */
function myPostsImageCardHTML(out) {
  const e = out.result;
  const p = datePartsOf(out.date);
  const cell = 'border:1px solid #999999;padding:6px 10px;text-align:center;vertical-align:middle;';
  const vname = out.viewer ? out.viewer.name : '';
  let postHTML, bodyHTML = '';
  if (e.status === 'ok') {
    postHTML = `<span style="font-size:26px;font-weight:800;color:#2563EB;">${esc(e.letter)}</span>岗`;
    const rows = (e.timeline || []).map((t) =>
      `<tr><td style="${cell}">${t.time}</td><td style="${cell}">${esc(t.post)}${t.note ? `（${esc(t.note)}）` : ''}</td><td style="${cell}">${t.partners && t.partners.length ? t.partners.map(esc).join('、') : '—'}</td></tr>`).join('');
    bodyHTML = `<table style="border-collapse:collapse;width:100%;font-size:17px;"><tr><th style="${cell}">时间</th><th style="${cell}">岗位</th><th style="${cell}">同岗同事</th></tr>${rows}</table>`;
  } else {
    /* v6.31：退税岗所有班次都带——括号里跟实际班次（早班/晚班）。 */
    postHTML = `退税岗（${esc(out.shift_label || '')}）`;
    const others = (e.tax_names || []).filter((n) => n !== vname);
    if (others.length) bodyHTML = `<div style="font-size:17px;line-height:1.8;color:#444444;">同岗：${others.map(esc).join('、')}</div>`;
  }
  return `<div style="background:#FFFFFF;color:#111111;width:680px;padding:28px 32px;font-family:'PingFang SC','Microsoft YaHei',sans-serif;">
      <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:10px;">
        <span style="font-size:24px;font-weight:700;">${p.m}月${p.d}日 ${esc(out.shift_label || '')} · ${esc(vname)}</span>
        <span style="font-size:20px;">${postHTML}</span>
      </div>
      ${bodyHTML}
    </div>`;
}

/* v6.4：岗位显示「生成图片」——把当前查看的人当日岗位存成 PNG。与当日
   排班图片同一套机制（离屏 DOM + html2canvas、白底卡片、易读字号）；
   v6.23 起卡片版式见 myPostsImageCardHTML（去带班行、岗位上移标题行）。 */
async function myPostsImage() {
  const out = mypostsState;
  const e = out && out.result;
  if (!out || !e || (e.status !== 'ok' && e.status !== 'tax')) { toast('当前没有可生成图片的岗位', true); return; }
  try {
    if (typeof html2canvas === 'undefined') throw new Error('图片组件未加载（可能无网络）');
    const isSelf = out.is_self !== false;
    const vname = out.viewer ? out.viewer.name : '';
    const cardHTML = myPostsImageCardHTML(out);
    const holder = document.createElement('div');
    holder.style.cssText = 'position:fixed;left:-10000px;top:0;';
    holder.innerHTML = cardHTML;
    document.body.appendChild(holder);
    try {
      const canvas = await html2canvas(holder.firstElementChild, { scale: 2, backgroundColor: '#FFFFFF' });
      const a = document.createElement('a');
      a.href = canvas.toDataURL('image/png');
      a.download = `${isSelf ? '我的岗位' : `${vname}的岗位`}-${out.date}-${out.shift_label || ''}.png`;
      a.click();
    } finally {
      holder.remove();
    }
  } catch (err) { toast('生成图片失败：' + err.message, true); }
}

/* -------- 成员：当日排班（v6.9 只读整表） -------- */
/* 普通成员与协管员看全科当日排班整表：班次徽标 + 带班 + 与管理员
   预览同一张时段表（真名）+ 晚班退税岗。纯只读：无下拉选人、无
   保存；v6.10 起加「生成图片」（仅已保存排班 status=ok 时显示，
   把整张当日表存成 PNG）；v6.12 起按钮移入「时段预览」标题行右侧
   （随 dayViewHTML 渲染、仅 ok 分支出现，不再挂在日期控件行）。
   数据只来自后端已保存的排班（/api/daily/dayview），
   未保存/无计划时显示中性空态文案（非报错样式）；本人当天是否在岗
   不影响查看。日期控件与岗位显示同口径（默认明天、前后翻日）。 */
let dayviewDate = '';
let dayviewState = null;

function viewDayView() {
  if (!dayviewDate) dayviewDate = todayStr();
  return `<div class="card"><h3>当日排班</h3>
    <div class="form-grid daily-controls">
      <button id="dvPrev">← 前一天</button>
      <label>日期<input id="dvDate" type="date" value="${dayviewDate}"></label>
      <button id="dvNext">后一天 →</button>
      <button id="dvToday">回到今天</button>
    </div>
    <div id="dayviewBody"><p class="hint">正在加载…</p></div>
  </div>`;
}

function bindDayView() {
  const di = $('dvDate');
  if (di) di.addEventListener('change', () => { dayviewDate = di.value || todayStr(); loadDayView(); });
  const pv = $('dvPrev'); if (pv) pv.addEventListener('click', () => { dayviewDate = shiftDateStr(dayviewDate, -1); if (di) di.value = dayviewDate; loadDayView(); });
  const nx = $('dvNext'); if (nx) nx.addEventListener('click', () => { dayviewDate = shiftDateStr(dayviewDate, 1); if (di) di.value = dayviewDate; loadDayView(); });
  const tm = $('dvToday'); if (tm) tm.addEventListener('click', () => { dayviewDate = todayStr(); if (di) di.value = dayviewDate; loadDayView(); });
  loadDayView();
}

async function loadDayView() {
  const body = $('dayviewBody');
  if (!body) return;
  /* v6.10：切日期先清导出状态，杜绝导出上一日期的图。
     v6.12：图片按钮随 dayViewHTML 渲染进「时段预览」标题行（仅
     status=ok 分支才有该行），加载中/未生成/无计划时按钮随内容
     一并不存在，门控由渲染分支天然保证；渲染后按 mpImgBtn 同款
     模式补绑点击——innerHTML 每次整段替换，旧按钮连同旧监听
     一并销毁，不会重复出现或叠加监听。 */
  dayviewState = null;
  body.innerHTML = '<p class="hint">正在加载…</p>';
  try {
    const out = await api('GET', `/api/daily/dayview?date=${dayviewDate}`);
    dayviewState = out;
    body.innerHTML = dayViewHTML(out);
    const im = $('dvImgBtn'); if (im) im.addEventListener('click', dayViewImage);
  } catch (e) {
    body.innerHTML = `<p class="bad-msg">${esc(e.message)}</p>`;
  }
}

/* 时段表渲染：与管理员预览（dailyPreviewHTML）同一张表、同样文案
   （晚班各半小时/轮流注记逐字对齐），数据改由 dayview 的 preview
   （后端 resolve_daily_slots 解析结果）驱动。外层 .daily-scroll
   保证窄屏可横向滚动，字号沿用 .daily-table 既有排版。 */
function dayTableHTML(out) {
  const postsOf = (slot, name) => slot.posts.filter((p) => p.name === name);
  const names = (post) => (post ? post.people.map((p) => esc(p.name)).join('+') : '');
  if (out.shift === 'morning') {
    /* v6.16：列随 preview 首段岗位名生成（5 人与 6 人两套早班模板通用）。 */
    const heads = ((out.preview || [])[0] ? out.preview[0].posts : []).map((p) => p.name);
    const rows = (out.preview || []).map((slot) =>
      `<tr><td>${slot.start}–${slot.end}</td>${slot.posts.map((p) => `<td>${names(p)}</td>`).join('')}</tr>`).join('');
    return `<div class="daily-scroll"><table class="daily-table"><tr><th>时间</th>${heads.map((h) => `<th>${esc(h)}</th>`).join('')}</tr>${rows}</table></div>`;
  }
  const rows = (out.preview || []).map((slot) => {
    const sb = postsOf(slot, '申报岗');
    let sbTxt = '';
    if (sb.length > 1) sbTxt = sb.map(names).join('+') + '（各半小时）';
    else if (sb.length === 1) sbTxt = names(sb[0]) + (sb[0].note ? `（${esc(sb[0].note)}）` : '');
    return `<tr><td>${slot.start}–${slot.end}</td><td>${names(postsOf(slot, '审图查验岗')[0])}</td><td>${sbTxt}</td></tr>`;
  }).join('');
  return `<div class="daily-scroll"><table class="daily-table"><tr><th>时间</th><th>审图查验岗</th><th>申报岗</th></tr>${rows}</table></div>`;
}

function dayViewHTML(out) {
  const p = datePartsOf(out.date);
  const head = `<p><b>${p.m}月${p.d}日（周${weekdayOf(out.date)}）</b> <span class="chip">${esc(out.shift_label || '')}</span></p>`;
  if (out.status === 'noplan') return head + `<p class="hint">${p.m}月尚无排班计划。</p>`;
  if (out.status === 'none') return head + `<p class="hint">${p.m}月${p.d}日 当日排班尚未生成</p>`;
  /* v6.31：退税岗所有班次都带——早班当日排班页同样显示退税岗行。 */
  const taxLine = `<p class="hint">退税岗：${out.tax_names && out.tax_names.length ? out.tax_names.map(esc).join('、') : '无'}</p>`;
  return head
    + `<p>带班：<b>${esc(out.leader_name || '—')}</b></p>`
    + `<div class="post-line"><h4 style="margin:0">时段预览（${esc(out.shift_label || '')}）</h4><button id="dvImgBtn">生成图片</button></div>`
    + dayTableHTML(out)
    + taxLine;
}

/* v6.10：成员「当日排班」「生成图片」——把当前查看的整张当日表存成
   PNG。与 myPostsImage / dailyImage 同一套机制（离屏 DOM +
   html2canvas、白底卡片、内联样式、易读字号）：标题「{M}月{D}日
   当日排班（早/晚班）」居中 + 带班行 + 完整时段表（与页面同列、
   同注记口径）+ 晚班退税岗行；不含日期控件与任何按钮。仅
   status=ok（已保存排班）可导出，页内按钮亦只在该状态显示。
   v6.29（用户 2026-11-11 定）：同管理员导图——带班、退税岗挪到
   标题行最右边（标题改为左对齐与右信息同排），不再各占一行、
   退税岗不再挂在表尾。 */
function dayTableExportHTML(out) {
  const cell = 'border:1px solid #999999;padding:6px 10px;text-align:center;vertical-align:middle;';
  const postsOf = (slot, name) => slot.posts.filter((p) => p.name === name);
  const names = (post) => (post ? post.people.map((p) => esc(p.name)).join('+') : '');
  if (out.shift === 'morning') {
    /* v6.16：列随 preview 首段岗位名生成（5 人与 6 人两套早班模板通用）。 */
    const heads = ((out.preview || [])[0] ? out.preview[0].posts : []).map((p) => p.name);
    const rows = (out.preview || []).map((slot) =>
      `<tr><td style="${cell}">${slot.start}–${slot.end}</td>${slot.posts.map((p) => `<td style="${cell}">${names(p)}</td>`).join('')}</tr>`).join('');
    return `<table style="border-collapse:collapse;width:100%;font-size:17px;"><tr><th style="${cell}">时间</th>${heads.map((h) => `<th style="${cell}">${esc(h)}</th>`).join('')}</tr>${rows}</table>`;
  }
  const rows = (out.preview || []).map((slot) => {
    const sb = postsOf(slot, '申报岗');
    let sbTxt = '';
    if (sb.length > 1) sbTxt = sb.map(names).join('+') + '（各半小时）';
    else if (sb.length === 1) sbTxt = names(sb[0]) + (sb[0].note ? `（${esc(sb[0].note)}）` : '');
    return `<tr><td style="${cell}">${slot.start}–${slot.end}</td><td style="${cell}">${names(postsOf(slot, '审图查验岗')[0])}</td><td style="${cell}">${sbTxt}</td></tr>`;
  }).join('');
  return `<table style="border-collapse:collapse;width:100%;font-size:17px;"><tr><th style="${cell}">时间</th><th style="${cell}">审图查验岗</th><th style="${cell}">申报岗</th></tr>${rows}</table>`;
}

async function dayViewImage() {
  const out = dayviewState;
  if (!out || out.status !== 'ok') { toast('当日排班尚未生成，暂无图片可导出', true); return; }
  try {
    if (typeof html2canvas === 'undefined') throw new Error('图片组件未加载（可能无网络）');
    const p = datePartsOf(out.date);
    /* v6.31：退税岗所有班次都带——早班成员导图标题行同样带退税岗。 */
    const taxHTML = `<span style="margin-left:24px;">退税岗：${out.tax_names && out.tax_names.length ? out.tax_names.map(esc).join('、') : '无'}</span>`;
    const cardHTML = `<div style="background:#FFFFFF;color:#111111;width:${out.shift === 'morning' ? (out.variant === 'morning6' ? 900 : 760) : 680}px;padding:28px 32px;font-family:'PingFang SC','Microsoft YaHei',sans-serif;">
      <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:12px;">
        <span style="font-size:24px;font-weight:700;">${p.m}月${p.d}日 当日排班（${esc(out.shift_label || '')}）</span>
        <span style="font-size:20px;text-align:right;">带班：${esc(out.leader_name || '—')}${taxHTML}</span>
      </div>
      ${dayTableExportHTML(out)}
    </div>`;
    const holder = document.createElement('div');
    holder.style.cssText = 'position:fixed;left:-10000px;top:0;';
    holder.innerHTML = cardHTML;
    document.body.appendChild(holder);
    try {
      const canvas = await html2canvas(holder.firstElementChild, { scale: 2, backgroundColor: '#FFFFFF' });
      const a = document.createElement('a');
      a.href = canvas.toDataURL('image/png');
      a.download = `当日排班-${out.date}-${out.shift_label || ''}.png`;
      a.click();
    } finally {
      holder.remove();
    }
  } catch (err) { toast('生成图片失败：' + err.message, true); }
}

/* ---------------- 路由 ---------------- */
const VIEWS = {
  pick: { render: viewPick, bind: bindPick },
  sheet: { render: viewSheet, bind: () => { if (me && myRole() !== 'super') bindMemberSheet(); else bindSheet(); } },
  daily: { render: viewDaily, bind: bindDaily },
  dayview: { render: viewDayView, bind: bindDayView },
  myposts: { render: viewMyPosts, bind: bindMyPosts },
  rules: { render: viewRules, bind: bindRules },
  people: { render: viewPeoplePerms, bind: bindPeoplePerms },
  history: { render: viewHistory, bind: bindHistory },
  logs: { render: viewLogs, bind: bindLogs },
  password: { render: viewPassword, bind: bindPassword },
};

async function renderRoute() {
  if (!me) return;
  markNav();
  let route = currentRoute();
  if (route === 'perms') route = 'people'; // 旧链接兼容：权限设置已并入人员与权限
  // v3.0：超管三页合一——主页 / 我的选班 / 数据管理旧链接统一重定向到合并后的「排班表」
  if (myRole() === 'super' && (route === 'pick' || route === 'home' || route === 'process')) route = 'sheet';
  if (!VIEWS[route]) route = 'sheet';
  // v2.4：管理台仅超级管理员可用；人员管理员与成员共用合并排班表页
  // v6.0：成员侧可用路由扩为 排班表/修改密码/岗位显示；人员管理员另加 生成当日排班
  // v6.9：普通成员再加 当日排班（只读整表）；管理员/超管不开放该路由（有编辑页）
  if (myRole() !== 'super') {
    const allowed = myRole() === 'admin'
      ? ['sheet', 'password', 'myposts', 'daily']
      : ['sheet', 'password', 'myposts', 'dayview'];
    if (!allowed.includes(route)) route = 'sheet';
  }
  // v2.3：排班表页启用一屏锁高模式（fit-view），其余页面恢复普通滚动；
  // v3.0：人员与权限页同样启用一屏自适应；v4.3：日志管理页也纳入
  document.body.classList.toggle('fit-view', route === 'sheet' || route === 'people' || route === 'logs');
  const v = VIEWS[route];
  $('view').innerHTML = v.render();
  if (v.bind) await v.bind();
  requestAnimationFrame(fitGrids);
}

/* ---------------- 绑定 ---------------- */
document.addEventListener('DOMContentLoaded', async () => {
  $('loginBtn').addEventListener('click', doLogin);
  $('loginPass').addEventListener('keydown', (e) => { if (e.key === 'Enter') doLogin(); });
  $('logoutBtn').addEventListener('click', logout);
  $('planSelect').addEventListener('change', async (e) => {
    await loadDetail(Number(e.target.value));
    await renderRoute();
  });
  $('pickerClose').addEventListener('click', closePicker);
  document.addEventListener('click', (e) => {
    const picker = $('picker');
    if (!picker.classList.contains('hidden') && !picker.contains(e.target) && !e.target.closest('td.cell')) closePicker();
  });
  window.addEventListener('hashchange', renderRoute);
  window.addEventListener('resize', scheduleFit);
  window.addEventListener('orientationchange', scheduleFit);
  if (token && me) {
    try { await enterApp(); } catch (e) { logout(); }
  }
});
