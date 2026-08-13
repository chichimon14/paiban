// ==========================================================================
// 科室智能轮休排班系统 - app.js
// ==========================================================================

let currentUser = null;
let currentSchedule = null;
let allUsers = [];

// 成员划假临时数据: day -> '班' | '✅' | '假'
let tempMemberSelections = {};

// 管理员微调暂存数据: userId -> { day: type }
let adminTempSchedule = {};

// 管理员微调编辑模式
let isAdminEditMode = false;

// 老花眼大字模式状态
let isLargeFontMode = false;

// 正中央弹窗回调函数
let centerConfirmCallback = null;

document.addEventListener('DOMContentLoaded', () => {
  initApp();
});

function initApp() {
  const savedUser = sessionStorage.getItem('paiban_user');
  if (savedUser) {
    currentUser = JSON.parse(savedUser);
    showMainContent();
  } else {
    showLoginSection();
  }

  if (localStorage.getItem('paiban_large_font') === 'true') {
    isLargeFontMode = true;
    document.body.classList.add('large-font-mode');
  }

  bindEvents();
}

function bindEvents() {
  document.getElementById('loginForm').addEventListener('submit', handleLogin);
  document.getElementById('btnLogout').addEventListener('click', handleLogout);

  const btnQuick = document.getElementById('btnQuickSwitch');
  const menuQuick = document.getElementById('quickRolesMenu');
  btnQuick.addEventListener('click', (e) => {
    e.stopPropagation();
    menuQuick.classList.toggle('show');
  });
  document.addEventListener('click', () => menuQuick.classList.remove('show'));

  menuQuick.querySelectorAll('a').forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      doLogin(item.dataset.user, item.dataset.pwd);
    });
  });

  // Nav 切换
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.addEventListener('click', () => {
      switchPage(btn.dataset.page);
    });
  });

  // 快捷阶段切换演示助手
  const stageQuickSel = document.getElementById('quickStageSelect');
  if (stageQuickSel) {
    stageQuickSel.addEventListener('change', async (e) => {
      const stage = e.target.value;
      await handleSwitchStageQuick(stage);
    });
  }

  // 大字模式
  const btnFont = document.getElementById('btnToggleLargeFont');
  if (btnFont) {
    updateLargeFontBtnUI();
    btnFont.addEventListener('click', () => {
      isLargeFontMode = !isLargeFontMode;
      document.body.classList.toggle('large-font-mode', isLargeFontMode);
      localStorage.setItem('paiban_large_font', isLargeFontMode ? 'true' : 'false');
      updateLargeFontBtnUI();
      showToast(isLargeFontMode ? '已开启老花眼大字模式 🔍' : '已恢复标准字体', 'info');
    });
  }

  // 管理员排班创建
  document.getElementById('btnCreateSchedule').addEventListener('click', handleCreateSchedule);

  // 智能补全与发布
  const btnAutoFillMatrix = document.getElementById('btnAutoFillInMatrix');
  if (btnAutoFillMatrix) btnAutoFillMatrix.addEventListener('click', handleAutoFill);

  const btnPublishMatrix = document.getElementById('btnPublishInMatrix');
  if (btnPublishMatrix) btnPublishMatrix.addEventListener('click', handlePublishSchedule);

  // 一键清零重置与备份恢复绑定 (卡片右下角)
  const btnResetMatrix = document.getElementById('btnResetScheduleInMatrix');
  if (btnResetMatrix) btnResetMatrix.addEventListener('click', handleResetSchedule);

  const btnRestoreMatrix = document.getElementById('btnRestoreBackupInMatrix');
  if (btnRestoreMatrix) btnRestoreMatrix.addEventListener('click', handleRestoreBackup);

  // 管理员【开启微调编辑模式】与【保存微调结果】
  const btnEditMode = document.getElementById('btnToggleAdminEditMode');
  if (btnEditMode) {
    btnEditMode.addEventListener('click', () => {
      isAdminEditMode = !isAdminEditMode;
      btnEditMode.classList.toggle('btn-primary', isAdminEditMode);
      btnEditMode.classList.toggle('btn-outline-info', !isAdminEditMode);
      btnEditMode.innerHTML = isAdminEditMode ? 
        `<i class="fa-solid fa-xmark"></i> 退出编辑模式` : 
        `<i class="fa-solid fa-pen-to-square"></i> 开启微调编辑模式`;

      const btnSaveAdmin = document.getElementById('btnSaveAdminEdits');
      if (btnSaveAdmin) btnSaveAdmin.style.display = isAdminEditMode ? 'inline-flex' : 'none';

      initAdminTempSchedule();
      renderScheduleMatrix();
    });
  }

  const btnSaveAdmin = document.getElementById('btnSaveAdminEdits');
  if (btnSaveAdmin) {
    btnSaveAdmin.addEventListener('click', handleSaveAdminEdits);
  }

  // 成员右上角【保存划假草稿】与【提交划假方案】
  const btnSaveSel = document.getElementById('btnSaveMemberSelections');
  if (btnSaveSel) btnSaveSel.addEventListener('click', handleMemberSaveSelections);

  const btnSubmitSel = document.getElementById('btnSubmitMemberSelections');
  if (btnSubmitSel) btnSubmitSel.addEventListener('click', handleMemberSubmitSelections);

  // 成员修改密码 Modal
  const profileChip = document.getElementById('btnOpenSelfProfile');
  if (profileChip) {
    profileChip.addEventListener('click', () => openSelfProfileModal());
  }
  document.getElementById('selfProfileForm').addEventListener('submit', handleSaveSelfProfile);

  // 人员管理 Modal
  document.getElementById('btnAddUserModal').addEventListener('click', () => openUserModal());
  document.getElementById('userModalForm').addEventListener('submit', handleSaveUserModal);

  // 导出与打印
  const btnExport = document.getElementById('btnExportCSV');
  if (btnExport) btnExport.addEventListener('click', exportToCSV);

  const btnPrint = document.getElementById('btnPrintSchedule');
  if (btnPrint) btnPrint.addEventListener('click', () => window.print());
}

function updateLargeFontBtnUI() {
  const btnFontText = document.getElementById('largeFontBtnText');
  if (btnFontText) {
    btnFontText.textContent = isLargeFontMode ? '恢复标准字号' : '放大字体模式 🔍';
  }
}

function fillLogin(u, p) {
  document.getElementById('inputUsername').value = u;
  document.getElementById('inputPassword').value = p;
}

function switchPage(pageId) {
  document.querySelectorAll('.app-page').forEach(page => page.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(btn => btn.classList.remove('active'));

  const targetPage = document.getElementById(pageId);
  const targetNavBtn = document.querySelector(`.nav-item[data-page="${pageId}"]`);

  if (targetPage) targetPage.classList.add('active');
  if (targetNavBtn) targetNavBtn.classList.add('active');
}

// 支持单按钮与双按钮交互的正中央警示弹窗
function showCenterAlert(title, message, isConfirmDialog = false, onConfirm = null) {
  document.getElementById('centerAlertTitle').textContent = title;
  document.getElementById('centerAlertMessage').textContent = message;

  const btnCancel = document.getElementById('btnCenterCancel');
  const btnConfirm = document.getElementById('btnCenterConfirm');

  if (isConfirmDialog) {
    btnCancel.style.display = 'inline-flex';
    btnConfirm.textContent = '确定提交';
    centerConfirmCallback = onConfirm;
  } else {
    btnCancel.style.display = 'none';
    btnConfirm.textContent = '确 认';
    centerConfirmCallback = null;
  }

  document.getElementById('centerNoticeModal').classList.add('show');
}

function closeCenterAlert() {
  document.getElementById('centerNoticeModal').classList.remove('show');
}

function handleCenterConfirmAction() {
  closeCenterAlert();
  if (centerConfirmCallback) {
    centerConfirmCallback();
    centerConfirmCallback = null;
  }
}

// -------------------------------------------------------------
// 登录与身份
// -------------------------------------------------------------
async function handleLogin(e) {
  e.preventDefault();
  const username = document.getElementById('inputUsername').value.trim();
  const password = document.getElementById('inputPassword').value.trim();
  await doLogin(username, password);
}

async function doLogin(username, password) {
  try {
    const res = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    const data = await res.json();

    if (data.success) {
      currentUser = data.user;
      sessionStorage.setItem('paiban_user', JSON.stringify(currentUser));
      showToast('登录成功！欢迎使用，' + currentUser.name, 'success');
      showMainContent();
    } else {
      showToast(data.message || '登录失败', 'error');
    }
  } catch (err) {
    showToast('通信错误', 'error');
  }
}

function handleLogout() {
  currentUser = null;
  sessionStorage.removeItem('paiban_user');
  showLoginSection();
  showToast('已安全退出', 'success');
}

function showLoginSection() {
  document.getElementById('loginSection').style.display = 'flex';
  document.getElementById('appPagesContainer').style.display = 'none';
  document.getElementById('mainAppNav').style.display = 'none';
  document.getElementById('userProfileBar').style.display = 'none';
}

function showMainContent() {
  document.getElementById('loginSection').style.display = 'none';
  document.getElementById('appPagesContainer').style.display = 'block';
  document.getElementById('mainAppNav').style.display = 'flex';
  document.getElementById('userProfileBar').style.display = 'flex';

  document.getElementById('currentUserName').textContent = currentUser.name;
  document.getElementById('userAvatar').textContent = currentUser.name.charAt(0);

  let roleLabel = '普通干部';
  if (currentUser.role === 'admin') roleLabel = '系统管理员';
  else if (currentUser.role === 'leader_main') roleLabel = '正科长';
  else if (currentUser.role === 'leader_sub') roleLabel = `副科长 (${currentUser.group}组)`;
  else if (currentUser.group) roleLabel = `干部 (${currentUser.group}组)`;

  document.getElementById('currentUserRole').textContent = roleLabel;

  const adminNavs = document.querySelectorAll('.admin-only');
  if (currentUser.role === 'admin') {
    adminNavs.forEach(el => el.style.display = 'inline-flex');
    document.getElementById('adminMatrixInlineTools').style.display = 'inline-flex';
    document.getElementById('adminFooterActions').style.display = 'inline-flex';
    document.getElementById('memberActionTools').style.display = 'none';
    document.getElementById('memberCounterNotice').style.display = 'none';
  } else {
    adminNavs.forEach(el => el.style.display = 'none');
    document.getElementById('adminMatrixInlineTools').style.display = 'none';
    document.getElementById('adminFooterActions').style.display = 'none';
    document.getElementById('memberActionTools').style.display = 'inline-flex';
    document.getElementById('memberCounterNotice').style.display = 'block';
  }

  switchPage('page-matrix');
  loadScheduleData();
}

function openSelfProfileModal() {
  if (!currentUser) return;
  document.getElementById('selfProfileName').value = currentUser.name;
  document.getElementById('selfProfilePassword').value = '';
  document.getElementById('selfProfileModal').classList.add('show');
}

function closeSelfProfileModal() {
  document.getElementById('selfProfileModal').classList.remove('show');
}

async function handleSaveSelfProfile(e) {
  e.preventDefault();
  const name = document.getElementById('selfProfileName').value.trim();
  const password = document.getElementById('selfProfilePassword').value.trim();

  try {
    const res = await fetch('/api/users/update-profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        userId: currentUser.id,
        name,
        password
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'success');
      currentUser.name = name;
      sessionStorage.setItem('paiban_user', JSON.stringify(currentUser));
      document.getElementById('currentUserName').textContent = currentUser.name;
      closeSelfProfileModal();
      loadScheduleData();
    } else {
      showToast(data.message || '更新失败', 'error');
    }
  } catch (err) {
    showToast('更新失败', 'error');
  }
}

// -------------------------------------------------------------
// 数据加载与 Header 渲染
// -------------------------------------------------------------
async function loadScheduleData() {
  try {
    const res = await fetch('/api/schedules/current');
    const data = await res.json();

    if (data.success) {
      currentSchedule = data.schedule;
      allUsers = data.users || [];

      renderUsersTable();

      if (currentSchedule) {
        renderHeaderPills();
        renderStageFlow();
        initTempMemberSelections();
        initAdminTempSchedule();
        renderScheduleMatrix();

        const btnRestore = document.getElementById('btnRestoreBackupInMatrix');
        if (btnRestore) {
          btnRestore.style.display = (currentUser.role === 'admin' && currentSchedule.backupData) ? 'inline-flex' : 'none';
        }
      }
    }
  } catch (err) {
    console.error('加载失败:', err);
  }
}

function renderHeaderPills() {
  const { year, month, totalDays, holidayDays, maxSelfSelectDays, currentStage } = currentSchedule;
  document.getElementById('headerMonthTitle').textContent = `${year}年 ${month}月 科室排班大屏`;
  document.getElementById('statTotalDays').textContent = totalDays;
  document.getElementById('statHolidayDays').textContent = holidayDays;
  document.getElementById('statMaxSelfDays').textContent = maxSelfSelectDays;

  const quickStageSel = document.getElementById('quickStageSelect');
  if (quickStageSel) quickStageSel.value = currentStage;
}

function renderStageFlow() {
  if (!currentSchedule) return;
  const { month, currentStage, isPublished } = currentSchedule;
  const isOddMonth = month % 2 !== 0;
  const priorityGroup = isOddMonth ? 'A' : 'B';

  for (let i = 1; i <= 5; i++) {
    const stepEl = document.getElementById(`step${i}`);
    if (stepEl) {
      stepEl.classList.remove('active', 'completed');
      if (i < currentStage) stepEl.classList.add('completed');
      else if (i === currentStage) stepEl.classList.add('active');
    }
  }

  const step2Title = document.getElementById('step2Title');
  if (step2Title) step2Title.textContent = `优先组(${priorityGroup}组)填报`;

  const alertTextEl = document.getElementById('stageAlertMessage');
  if (!alertTextEl) return;

  if (isPublished) {
    alertTextEl.textContent = '🎉 本月排班表已由管理员正式发布！全科人员可在大屏查看。';
  } else {
    switch (currentStage) {
      case 1:
        alertTextEl.textContent = '阶段 1 [姚惠安(正科长)优先填报]：第1轮限时1天。若错过降至第3轮。';
        break;
      case 2:
        alertTextEl.textContent = `阶段 2 [优先组 (${priorityGroup}组) 填报]：第2轮限时1天，本月${priorityGroup}组优先。若错过降至第3轮。`;
        break;
      case 3:
        alertTextEl.textContent = '阶段 3 [普通组填报]：第3轮限时2天，全员开放（错过的成员在此沉降补填）。';
        break;
      case 4:
        alertTextEl.textContent = '阶段 4 [系统智能补全]：点击运行智能算法，系统将自动分配剩余轮休(✅)。';
        break;
      case 5:
        alertTextEl.textContent = '阶段 5 [管理员微调与发布]：系统已补全，管理员开启微调编辑模式可进行二次调整。';
        break;
    }
  }
}

function initTempMemberSelections() {
  if (!currentSchedule || currentUser.role === 'admin') return;

  const { totalDays, userSelections } = currentSchedule;
  const saved = userSelections[currentUser.id] || {};
  tempMemberSelections = {};

  for (let d = 1; d <= totalDays; d++) {
    tempMemberSelections[d] = '班';
  }

  if (Array.isArray(saved)) {
    saved.forEach(item => {
      if (typeof item === 'number') tempMemberSelections[item] = '✅';
      else if (typeof item === 'object' && item.day) tempMemberSelections[item.day] = item.type || '✅';
    });
  } else if (typeof saved === 'object') {
    Object.keys(saved).forEach(d => {
      tempMemberSelections[d] = saved[d];
    });
  }
}

function initAdminTempSchedule() {
  if (!currentSchedule || currentUser.role !== 'admin') return;
  const { userSelections, finalSchedule } = currentSchedule;
  const staffUsers = allUsers.filter(u => u.role !== 'admin');
  adminTempSchedule = {};

  staffUsers.forEach(u => {
    const uMap = {};
    const userSel = (userSelections && userSelections[u.id]) || {};
    const finalSel = (finalSchedule && finalSchedule[u.id]) || {};
    const merged = { ...userSel, ...finalSel };

    if (typeof merged === 'object') {
      Object.keys(merged).forEach(d => {
        uMap[d] = merged[d];
      });
    }
    adminTempSchedule[u.id] = uMap;
  });
}

// 演示助手：快捷切换阶段
async function handleSwitchStageQuick(stage) {
  if (!currentSchedule) return;
  try {
    const res = await fetch('/api/schedules/stage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scheduleId: currentSchedule.id,
        stage
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`阶段已成功切换至：第 ${stage} 阶段`, 'success');
      loadScheduleData();
    }
  } catch (err) {
    showToast('切换阶段失败', 'error');
  }
}

// -------------------------------------------------------------
// 核心页面 1：月度排班矩阵大屏 (划假高亮与高级感首列)
// -------------------------------------------------------------
function renderScheduleMatrix() {
  if (!currentSchedule) return;

  const { year, month, totalDays, isPublished, currentStage, userSelections, finalSchedule } = currentSchedule;
  const staffUsers = allUsers.filter(u => u.role !== 'admin');
  const isOddMonth = month % 2 !== 0;
  const priorityGroup = isOddMonth ? 'A' : 'B';

  document.getElementById('matrixStatusChip').textContent = isPublished ? '【已正式发布】' : '【草稿/编制中】';

  let canMemberFill = false;
  let memberWaitReason = '';

  if (currentUser.role !== 'admin') {
    if (currentStage === 1) {
      if (currentUser.role === 'leader_main') canMemberFill = true;
      else memberWaitReason = `当前为 [第1轮：正科长优先填报阶段]。您所属的岗位将在后续轮次开启，或可使用右上角菜单切换至第3阶段进行体验。`;
    } else if (currentStage === 2) {
      if (currentUser.group === priorityGroup) canMemberFill = true;
      else memberWaitReason = `当前为 [第2轮：优先组 (${priorityGroup}组) 填报阶段]。您属于 ${currentUser.group || '其他'} 组，请等待下一轮全员开放。`;
    } else if (currentStage >= 3) {
      canMemberFill = true;
    }

    updateMemberCountDisplay();
  }

  const waitNoticeCard = document.getElementById('memberStageWaitNotice');
  const waitNoticeText = document.getElementById('memberStageWaitText');
  if (currentUser.role !== 'admin' && !canMemberFill && memberWaitReason) {
    waitNoticeCard.style.display = 'flex';
    waitNoticeText.textContent = memberWaitReason;
  } else {
    waitNoticeCard.style.display = 'none';
  }

  // 构建大屏表头
  const thead = document.getElementById('matrixHead');
  let headHtml = `<tr><th class="sticky-col">成员姓名 / 岗位</th>`;
  const weekDaysCN = ['日', '一', '二', '三', '四', '五', '六'];

  for (let d = 1; d <= totalDays; d++) {
    const dateObj = new Date(year, month - 1, d);
    const dayOfWeek = weekDaysCN[dateObj.getDay()];
    const isWeekend = dateObj.getDay() === 0 || dateObj.getDay() === 6;
    headHtml += `
      <th style="${isWeekend ? 'color: #ef4444;' : ''}">
        <div>${d}日</div>
        <div style="font-size:10px; opacity:0.7;">${dayOfWeek}</div>
      </th>
    `;
  }
  headHtml += `</tr>`;
  thead.innerHTML = headHtml;

  // 构建大屏表体
  const tbody = document.getElementById('matrixBody');
  tbody.innerHTML = '';

  const dayLeaderWorking = new Array(totalDays + 1).fill(0);
  const dayTotalWorking = new Array(totalDays + 1).fill(0);

  staffUsers.forEach(u => {
    const tr = document.createElement('tr');
    
    // 🌟 用户划假时高亮他这一行 (Row Highlight)
    const isSelfRow = (currentUser.role !== 'admin' && u.id === currentUser.id);
    if (isSelfRow) {
      tr.classList.add('current-user-row');
    }

    let roleTagClass = 'group-a';
    let roleText = 'A组';
    if (u.role === 'leader_main') { roleTagClass = 'leader-main'; roleText = '正科长'; }
    else if (u.role === 'leader_sub') { roleTagClass = 'leader-sub'; roleText = '副科长'; }
    else if (u.group === 'B') { roleTagClass = 'group-b'; roleText = 'B组'; }

    let rowHtml = `
      <td class="sticky-col">
        <div class="user-cell-title">
          <span class="user-name-bold">${u.name}${isSelfRow ? '<span class="my-row-badge">我</span>' : ''}</span>
          <span class="role-tag-xs ${roleTagClass}">${roleText}</span>
        </div>
      </td>
    `;

    const userStateMap = {};
    if (currentUser.role === 'admin' && isAdminEditMode) {
      const adminMap = adminTempSchedule[u.id] || {};
      for (let d = 1; d <= totalDays; d++) {
        userStateMap[d] = adminMap[d] || '班';
      }
    } else if (u.id === currentUser.id && canMemberFill) {
      for (let d = 1; d <= totalDays; d++) {
        userStateMap[d] = tempMemberSelections[d] || '班';
      }
    } else {
      const userSel = (userSelections && userSelections[u.id]) || {};
      const finalSel = (finalSchedule && finalSchedule[u.id]) || {};
      const mergedRawData = { ...userSel, ...finalSel };

      for (let d = 1; d <= totalDays; d++) {
        userStateMap[d] = '班';
      }

      if (Array.isArray(mergedRawData)) {
        mergedRawData.forEach(item => {
          if (typeof item === 'number') userStateMap[item] = '✅';
          else if (item && item.day) userStateMap[item.day] = item.type || '✅';
        });
      } else if (typeof mergedRawData === 'object') {
        Object.keys(mergedRawData).forEach(d => {
          userStateMap[d] = mergedRawData[d];
        });
      }
    }

    const isLeader = u.role === 'leader_main' || u.role === 'leader_sub';

    for (let d = 1; d <= totalDays; d++) {
      const state = userStateMap[d] || '班';
      const isOff = state === '✅' || state === '假';

      if (!isOff) {
        dayTotalWorking[d]++;
        if (isLeader) dayLeaderWorking[d]++;
      }

      // 情况 A: 超级管理员开启微调编辑模式
      if (currentUser.role === 'admin' && isAdminEditMode) {
        let dropdownClass = 'cell-select-dropdown';
        if (state === '✅') dropdownClass += ' state-lun';
        else if (state === '假') dropdownClass += ' state-jia';

        rowHtml += `
          <td style="padding:2px;">
            <select class="${dropdownClass} admin-cell-select" data-userid="${u.id}" data-day="${d}">
              <option value="班" ${state === '班' || state === '' ? 'selected' : ''}></option>
              <option value="✅" ${state === '✅' ? 'selected' : ''}>✅</option>
              <option value="假" ${state === '假' ? 'selected' : ''}>假</option>
            </select>
          </td>
        `;
      }
      // 情况 B: 普通成员在属于自己的轮次中编辑所属行
      else if (u.id === currentUser.id && canMemberFill) {
        let dropdownClass = 'cell-select-dropdown';
        if (state === '✅') dropdownClass += ' state-lun';
        else if (state === '假') dropdownClass += ' state-jia';

        rowHtml += `
          <td style="padding:2px;">
            <select class="${dropdownClass}" data-day="${d}">
              <option value="班" ${state === '班' || state === '' ? 'selected' : ''}></option>
              <option value="✅" ${state === '✅' ? 'selected' : ''}>✅</option>
              <option value="假" ${state === '假' ? 'selected' : ''}>假</option>
            </select>
          </td>
        `;
      }
      // 情况 C: 静态只读展示
      else {
        let cellClass = 'cell-state-work';
        let displaySymbol = '';
        if (state === '✅') { cellClass = 'cell-state-lun'; displaySymbol = '✅'; }
        else if (state === '假') { cellClass = 'cell-state-jia'; displaySymbol = '假'; }

        rowHtml += `
          <td class="${cellClass}">
            ${displaySymbol}
          </td>
        `;
      }
    }

    tr.innerHTML = rowHtml;
    tbody.appendChild(tr);
  });

  if (currentUser.role !== 'admin' && canMemberFill) {
    tbody.querySelectorAll('.cell-select-dropdown:not(.admin-cell-select)').forEach(select => {
      select.addEventListener('change', (e) => {
        const day = parseInt(e.target.dataset.day, 10);
        const val = e.target.value;
        const oldVal = tempMemberSelections[day] || '班';

        if (val === '✅' && oldVal !== '✅') {
          let currentLunCount = 0;
          Object.keys(tempMemberSelections).forEach(d => {
            if (tempMemberSelections[d] === '✅') currentLunCount++;
          });

          if (currentLunCount >= currentSchedule.maxSelfSelectDays) {
            showCenterAlert(
              '自主轮休额度已满',
              `❌ 选假拦截：您的自主轮休假(✅)已达上限 (${currentSchedule.maxSelfSelectDays} 天)，无法继续选择轮休假！`
            );
            e.target.value = oldVal;
            return;
          }
        }

        tempMemberSelections[day] = val;
        renderScheduleMatrix();
      });
    });
  }

  if (currentUser.role === 'admin' && isAdminEditMode) {
    tbody.querySelectorAll('.admin-cell-select').forEach(select => {
      select.addEventListener('change', (e) => {
        const userId = e.target.dataset.userid;
        const day = parseInt(e.target.dataset.day, 10);
        const type = e.target.value;

        if (!adminTempSchedule[userId]) adminTempSchedule[userId] = {};
        if (!type || type === '班' || type.trim() === '') {
          delete adminTempSchedule[userId][day];
        } else {
          adminTempSchedule[userId][day] = type;
        }

        renderScheduleMatrix();
      });
    });
  }

  // 表脚在岗统计
  const tfoot = document.getElementById('matrixFoot');
  let footLeaderHtml = `<tr class="foot-stat-row"><td class="sticky-col">在岗领导 (≥1)</td>`;
  let footTotalHtml = `<tr class="foot-stat-row"><td class="sticky-col">在岗总人数 (≥5)</td>`;

  for (let d = 1; d <= totalDays; d++) {
    const leaderCount = dayLeaderWorking[d];
    const totalCount = dayTotalWorking[d];

    let leaderClass = 'stat-good';
    if (leaderCount < 1) leaderClass = 'stat-danger';

    let totalClass = 'stat-good';
    if (totalCount === 5) totalClass = 'stat-warn';
    else if (totalCount < 5) totalClass = 'stat-danger';

    footLeaderHtml += `<td class="${leaderClass}">${leaderCount}人</td>`;
    footTotalHtml += `<td class="${totalClass}">${totalCount}人</td>`;
  }

  footLeaderHtml += `</tr>`;
  footTotalHtml += `</tr>`;
  tfoot.innerHTML = footLeaderHtml + footTotalHtml;
}

function updateMemberCountDisplay() {
  if (!currentSchedule) return;
  const maxLimit = currentSchedule.maxSelfSelectDays;
  let lunCount = 0;
  let jiaCount = 0;

  Object.keys(tempMemberSelections).forEach(d => {
    if (tempMemberSelections[d] === '✅') lunCount++;
    else if (tempMemberSelections[d] === '假') jiaCount++;
  });

  const lunEl = document.getElementById('currentLunCountDisplay');
  const maxEl = document.getElementById('maxLimitCountDisplay');
  const jiaEl = document.getElementById('currentJiaCountDisplay');

  if (lunEl) lunEl.textContent = lunCount;
  if (maxEl) maxEl.textContent = maxLimit;
  if (jiaEl) jiaEl.textContent = jiaCount;
}

// 成员暂存草稿 (带有未选满弹窗提醒)
function handleMemberSaveSelections() {
  if (!currentSchedule) return;
  const maxLimit = currentSchedule.maxSelfSelectDays;
  let lunCount = 0;

  Object.keys(tempMemberSelections).forEach(d => {
    if (tempMemberSelections[d] === '✅') lunCount++;
  });

  if (lunCount < maxLimit) {
    const diff = maxLimit - lunCount;
    showCenterAlert(
      '划假额度提醒',
      `💡 提示：您本月拥有 ${maxLimit} 天自主轮休假(✅)额度，目前仅勾选了 ${lunCount} 天，尚有 ${diff} 天额度未选。\n未选的轮休假将在第 4 阶段由系统智能算法自动为您分配。确定暂存草稿吗？`,
      true,
      () => {
        showToast('已暂存您的划假草稿！', 'info');
      }
    );
  } else {
    showToast('已暂存您的划假草稿！', 'info');
  }
}

// 成员正式提交方案 (带有未选满弹窗提醒)
async function handleMemberSubmitSelections() {
  if (!currentSchedule) return;

  const maxLimit = currentSchedule.maxSelfSelectDays;
  let lunCount = 0;
  const selectionsObj = {};

  Object.keys(tempMemberSelections).forEach(d => {
    const val = tempMemberSelections[d];
    if (val === '✅' || val === '假') {
      selectionsObj[d] = val;
      if (val === '✅') lunCount++;
    }
  });

  if (lunCount > maxLimit) {
    showCenterAlert('自主轮休额度已满', `❌ 选假拦截：您的自主轮休假(✅)已满 ${maxLimit} 天上限！`);
    return;
  }

  const doSubmit = async () => {
    try {
      const res = await fetch('/api/schedules/select-days', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scheduleId: currentSchedule.id,
          userId: currentUser.id,
          selections: selectionsObj
        })
      });
      const data = await res.json();
      if (data.success) {
        showToast('划假方案已正式提交！管理员与全科大屏同步可见', 'success');
        loadScheduleData();
      } else {
        showToast(data.message || '提交失败', 'error');
      }
    } catch (err) {
      showToast('提交失败', 'error');
    }
  };

  // 🌟 未选满额度时的弹窗提醒
  if (lunCount < maxLimit) {
    const diff = maxLimit - lunCount;
    showCenterAlert(
      '划假额度未填满提醒',
      `💡 提示：您本月拥有 ${maxLimit} 天自主轮休假(✅)额度，目前仅选择了 ${lunCount} 天，剩余 ${diff} 天额度未勾选。\n剩余的 ${diff} 天轮休假将在第 4 阶段由系统智能算法自动为您补全。确定直接提交吗？`,
      true,
      () => {
        doSubmit();
      }
    );
  } else {
    doSubmit();
  }
}

// 管理员点击【保存微调结果】
async function handleSaveAdminEdits() {
  if (!currentSchedule || currentUser.role !== 'admin') return;
  showToast('正在保存管理员排班微调结果并产生热备份...', 'info');

  try {
    const userIds = Object.keys(adminTempSchedule);
    for (const userId of userIds) {
      const uMap = adminTempSchedule[userId];
      for (let d = 1; d <= currentSchedule.totalDays; d++) {
        const type = uMap[d] || '班';
        await fetch('/api/schedules/admin-update-cell', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            scheduleId: currentSchedule.id,
            userId,
            day: d,
            type
          })
        });
      }
    }

    showToast('管理员排班微调结果已成功保存生效！', 'success');
    isAdminEditMode = false;
    
    const btnEditMode = document.getElementById('btnToggleAdminEditMode');
    if (btnEditMode) {
      btnEditMode.classList.remove('btn-primary');
      btnEditMode.classList.add('btn-outline-info');
      btnEditMode.innerHTML = `<i class="fa-solid fa-pen-to-square"></i> 开启微调编辑模式`;
    }
    const btnSaveAdmin = document.getElementById('btnSaveAdminEdits');
    if (btnSaveAdmin) btnSaveAdmin.style.display = 'none';

    loadScheduleData();
  } catch (err) {
    showToast('保存微调失败', 'error');
  }
}

// 管理员【一键清零重置】
async function handleResetSchedule() {
  if (!currentSchedule || currentUser.role !== 'admin') return;
  if (!confirm('⚠️ 危险操作警告：确定要一键清零本月全员的所有划假数据吗？清零后系统将自动为您产生恢复备份。')) return;

  showToast('正在执行全盘一键清零...', 'info');

  try {
    const res = await fetch('/api/schedules/reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scheduleId: currentSchedule.id })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'success');
      currentSchedule = data.schedule;
      isAdminEditMode = false;
      loadScheduleData();
    }
  } catch (err) {
    showToast('一键清零失败', 'error');
  }
}

// 管理员【恢复清零前备份】
async function handleRestoreBackup() {
  if (!currentSchedule || currentUser.role !== 'admin') return;
  if (!confirm('确定要恢复至清零前/修改前的最后一版热备份排班吗？')) return;

  showToast('正在从热备份中恢复数据...', 'info');

  try {
    const res = await fetch('/api/schedules/restore-backup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scheduleId: currentSchedule.id })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'success');
      currentSchedule = data.schedule;
      loadScheduleData();
    } else {
      showToast(data.message || '恢复失败', 'error');
    }
  } catch (err) {
    showToast('恢复备份失败', 'error');
  }
}

// -------------------------------------------------------------
// 管理员阶段与算法
// -------------------------------------------------------------
async function handleAutoFill() {
  if (!currentSchedule) return;
  showToast('智能算法回溯求解中，请稍候...', 'info');

  try {
    const res = await fetch('/api/schedules/auto-fill', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scheduleId: currentSchedule.id })
    });
    const data = await res.json();

    if (data.success) {
      showToast(data.message, 'success');
      currentSchedule = data.schedule;
      renderStageFlow();
      renderScheduleMatrix();
    } else {
      showToast(data.message || '补全算法失败', 'error');
    }
  } catch (err) {
    showToast('后端通信失败', 'error');
  }
}

async function handleCreateSchedule() {
  const year = document.getElementById('inputNewYear').value;
  const month = document.getElementById('inputNewMonth').value;
  const holidayDays = document.getElementById('inputHolidayDays').value;

  try {
    const res = await fetch('/api/schedules/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ year, month, holidayDays })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'success');
      loadScheduleData();
    }
  } catch (err) {
    showToast('创建失败', 'error');
  }
}

async function handlePublishSchedule() {
  if (!currentSchedule) return;
  if (!confirm('确定要正式发布本月排班表吗？发布后全科成员可随时在大屏查看。')) return;

  try {
    const res = await fetch('/api/schedules/publish', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scheduleId: currentSchedule.id })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'success');
      currentSchedule = data.schedule;
      renderStageFlow();
      renderScheduleMatrix();
    }
  } catch (err) {
    showToast('发布失败', 'error');
  }
}

// -------------------------------------------------------------
// 人员名册管理
// -------------------------------------------------------------
function renderUsersTable() {
  const tbody = document.getElementById('usersTableBody');
  if (!tbody) return;
  tbody.innerHTML = '';

  allUsers.forEach(u => {
    const tr = document.createElement('tr');
    let roleText = '普通干部';
    if (u.role === 'admin') roleText = '系统管理员';
    else if (u.role === 'leader_main') roleText = '正科长 (领导)';
    else if (u.role === 'leader_sub') roleText = '副科长 (领导)';

    tr.innerHTML = `
      <td><strong>${u.username}</strong></td>
      <td>${u.name}</td>
      <td>${roleText}</td>
      <td><span class="badge ${u.group === 'A' ? 'badge-blue' : 'badge-orange'}">${u.group} 组</span></td>
      <td><span class="font-mono text-primary font-bold" style="background:#eff6ff; padding:2px 8px; border-radius:4px; border:1px solid #bfdbfe;">${u.password}</span></td>
      <td>
        <button class="btn btn-sm btn-light-ghost" onclick="editUser('${u.id}')"><i class="fa-solid fa-pen"></i> 编辑/重置密码</button>
        ${u.role !== 'admin' ? `<button class="btn btn-sm btn-outline-danger" onclick="deleteUser('${u.id}')"><i class="fa-solid fa-trash"></i> 删除</button>` : ''}
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function openUserModal(user = null) {
  document.getElementById('modalUserId').value = user ? user.id : '';
  document.getElementById('modalUsername').value = user ? user.username : '';
  document.getElementById('modalName').value = user ? user.name : '';
  document.getElementById('modalRole').value = user ? user.role : 'staff';
  document.getElementById('modalGroup').value = user ? user.group : 'A';
  document.getElementById('modalPassword').value = '';

  document.getElementById('userModalTitle').textContent = user ? '编辑人员与密码' : '添加新成员';
  document.getElementById('userModalOverlay').classList.add('show');
}

function closeUserModal() {
  document.getElementById('userModalOverlay').classList.remove('show');
}

function editUser(id) {
  const u = allUsers.find(item => item.id === id);
  if (u) openUserModal(u);
}

async function deleteUser(id) {
  if (!confirm('确定删除该成员吗？')) return;
  try {
    const res = await fetch(`/api/users/${id}`, { method: 'DELETE' });
    const data = await res.json();
    if (data.success) {
      showToast('删除成功', 'success');
      loadScheduleData();
    }
  } catch (err) {
    showToast('删除失败', 'error');
  }
}

// -------------------------------------------------------------
// 导出 Excel/CSV
// -------------------------------------------------------------
function exportToCSV() {
  if (!currentSchedule) return;

  const { year, month, totalDays, finalSchedule, userSelections } = currentSchedule;
  const staffUsers = allUsers.filter(u => u.role !== 'admin');

  let csvContent = `\uFEFF`;
  csvContent += `${year}年${month}月科室轮休排班矩阵大屏表格\n`;

  let headerRow = `姓名,角色,分组`;
  for (let d = 1; d <= totalDays; d++) {
    headerRow += `,${d}日`;
  }
  csvContent += headerRow + `\n`;

  staffUsers.forEach(u => {
    let roleText = '干部';
    if (u.role === 'leader_main') roleText = '正科长';
    else if (u.role === 'leader_sub') roleText = '副科长';

    let rowStr = `${u.name},${roleText},${u.group}组`;

    const userSel = (userSelections && userSelections[u.id]) || {};
    const finalSel = (finalSchedule && finalSchedule[u.id]) || {};
    const mergedRawData = { ...userSel, ...finalSel };

    const userStateMap = {};
    for (let d = 1; d <= totalDays; d++) userStateMap[d] = ' ';

    if (Array.isArray(mergedRawData)) {
      mergedRawData.forEach(item => {
        if (typeof item === 'number') userStateMap[item] = '✅';
        else if (item && item.day) userStateMap[item.day] = item.type || '✅';
      });
    } else if (typeof mergedRawData === 'object') {
      Object.keys(mergedRawData).forEach(d => {
        userStateMap[d] = mergedRawData[d];
      });
    }

    for (let d = 1; d <= totalDays; d++) {
      rowStr += `,${userStateMap[d] === '✅' || userStateMap[d] === '假' ? userStateMap[d] : '上班'}`;
    }
    csvContent += rowStr + `\n`;
  });

  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.setAttribute('href', url);
  link.setAttribute('download', `${year}年${month}月科室轮休排班表.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  showToast('排班表格已成功导出！', 'success');
}

function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;

  let icon = '<i class="fa-solid fa-circle-info" style="color:#2563eb;"></i>';
  if (type === 'success') icon = '<i class="fa-solid fa-circle-check" style="color:#10b981;"></i>';
  else if (type === 'error') icon = '<i class="fa-solid fa-circle-xmark" style="color:#ef4444;"></i>';

  toast.innerHTML = `${icon} <span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.remove();
  }, 4000);
}
