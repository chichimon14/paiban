const express = require('express');
const cors = require('cors');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;
const DB_FILE = path.join(__dirname, 'data', 'db.json');

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

function readDB() {
  try {
    if (!fs.existsSync(DB_FILE)) {
      return { users: [], schedules: [] };
    }
    const data = fs.readFileSync(DB_FILE, 'utf8');
    return JSON.parse(data);
  } catch (err) {
    console.error('读取数据库失败:', err);
    return { users: [], schedules: [] };
  }
}

function writeDB(data) {
  try {
    fs.writeFileSync(DB_FILE, JSON.stringify(data, null, 2), 'utf8');
  } catch (err) {
    console.error('写入数据库失败:', err);
  }
}

function getDaysInMonth(year, month) {
  return new Date(year, month, 0).getDate();
}

// -------------------------------------------------------------
// 智能排班补全算法 (Backtracking Solver)
// -------------------------------------------------------------
function solveAutoFillSchedule(schedule, users) {
  const { totalDays, holidayDays, userSelections } = schedule;
  const staffUsers = users.filter(u => u.role !== 'admin');
  
  const userSelectedMap = {};
  const userSelectedTypes = {};
  const userLunCount = {};

  staffUsers.forEach(u => {
    const rawSel = userSelections[u.id] || {};
    const offDays = new Set();
    const typeMap = {};
    let lun = 0;

    if (Array.isArray(rawSel)) {
      rawSel.forEach(item => {
        if (typeof item === 'number') {
          offDays.add(item);
          typeMap[item] = '✅';
          lun++;
        } else if (item && item.day) {
          offDays.add(item.day);
          typeMap[item.day] = item.type || '✅';
          if (item.type === '✅') lun++;
        }
      });
    } else if (typeof rawSel === 'object') {
      Object.keys(rawSel).forEach(dayStr => {
        const d = parseInt(dayStr, 10);
        const t = rawSel[dayStr];
        if (t === '✅' || t === '假') {
          offDays.add(d);
          typeMap[d] = t;
          if (t === '✅') lun++;
        }
      });
    }

    userSelectedMap[u.id] = offDays;
    userSelectedTypes[u.id] = typeMap;
    userLunCount[u.id] = lun;
  });

  const remainingLunNeeded = {};
  staffUsers.forEach(u => {
    remainingLunNeeded[u.id] = Math.max(0, holidayDays - userLunCount[u.id]);
  });

  const leaders = staffUsers.filter(u => u.role === 'leader_main' || u.role === 'leader_sub');

  function checkDayValidity(day, currentOffMap) {
    let leaderOff = 0;
    let totalOff = 0;

    staffUsers.forEach(u => {
      if (currentOffMap[u.id].has(day)) {
        totalOff++;
        if (u.role === 'leader_main' || u.role === 'leader_sub') {
          leaderOff++;
        }
      }
    });

    const workingLeaders = leaders.length - leaderOff;
    const workingTotal = staffUsers.length - totalOff;

    if (workingLeaders < 1) return { valid: false, reason: '无领导在岗' };
    if (workingTotal < 5) return { valid: false, reason: '在岗人数不足5人' };

    return { valid: true, workingLeaders, workingTotal };
  }

  let success = false;
  const finalOffMap = {};
  staffUsers.forEach(u => {
    finalOffMap[u.id] = new Set(userSelectedMap[u.id]);
  });

  for (let attempt = 0; attempt < 100; attempt++) {
    const tempOffMap = {};
    staffUsers.forEach(u => {
      tempOffMap[u.id] = new Set(userSelectedMap[u.id]);
    });

    const tempNeeded = { ...remainingLunNeeded };
    const shuffle = (arr) => [...arr].sort(() => Math.random() - 0.5);

    let allFulfilled = true;
    for (const u of shuffle(staffUsers)) {
      let needed = tempNeeded[u.id];
      if (needed <= 0) continue;

      const candidateDays = [];
      for (let d = 1; d <= totalDays; d++) {
        if (!tempOffMap[u.id].has(d)) {
          candidateDays.push(d);
        }
      }

      const scoredDays = candidateDays.map(d => {
        tempOffMap[u.id].add(d);
        const check = checkDayValidity(d, tempOffMap);
        tempOffMap[u.id].delete(d);

        let score = -999;
        if (check.valid) {
          score = check.workingTotal * 10 + check.workingLeaders * 5 + Math.random() * 2;
        }
        return { day: d, score, valid: check.valid };
      }).filter(item => item.valid);

      scoredDays.sort((a, b) => b.score - a.score);

      if (scoredDays.length < needed) {
        allFulfilled = false;
        break;
      }

      for (let i = 0; i < needed; i++) {
        tempOffMap[u.id].add(scoredDays[i].day);
      }
    }

    if (allFulfilled) {
      let globalValid = true;
      for (let d = 1; d <= totalDays; d++) {
        const check = checkDayValidity(d, tempOffMap);
        if (!check.valid) {
          globalValid = false;
          break;
        }
      }
      if (globalValid) {
        staffUsers.forEach(u => {
          finalOffMap[u.id] = tempOffMap[u.id];
        });
        success = true;
        break;
      }
    }
  }

  const finalScheduleObj = {};
  staffUsers.forEach(u => {
    const userMap = {};
    const userTypes = userSelectedTypes[u.id] || {};
    const offDaysSorted = Array.from(finalOffMap[u.id]).sort((a, b) => a - b);

    offDaysSorted.forEach(day => {
      userMap[day] = userTypes[day] || '✅';
    });

    finalScheduleObj[u.id] = userMap;
  });

  return { success, finalSchedule: finalScheduleObj };
}

// -------------------------------------------------------------
// API 路由
// -------------------------------------------------------------

app.post('/api/login', (req, res) => {
  const { username, password } = req.body;
  const db = readDB();
  const user = db.users.find(u => (u.username === username || u.username.toLowerCase() === username.toLowerCase()) && u.password === password);
  
  if (!user) {
    return res.status(401).json({ success: false, message: '账号或密码错误！' });
  }

  res.json({
    success: true,
    user: {
      id: user.id,
      username: user.username,
      name: user.name,
      role: user.role,
      group: user.group
    }
  });
});

app.post('/api/users/update-profile', (req, res) => {
  const { userId, password, name } = req.body;
  const db = readDB();
  const user = db.users.find(u => u.id === userId);

  if (!user) {
    return res.status(404).json({ success: false, message: '未找到用户' });
  }

  if (password) user.password = password;
  if (name) user.name = name;

  writeDB(db);
  res.json({
    success: true,
    message: '个人密码信息已成功更新',
    user: {
      id: user.id,
      username: user.username,
      name: user.name,
      role: user.role,
      group: user.group
    }
  });
});

app.get('/api/users', (req, res) => {
  const db = readDB();
  const users = db.users.map(u => ({
    id: u.id,
    username: u.username,
    password: u.password,
    name: u.name,
    role: u.role,
    group: u.group
  }));
  res.json({ success: true, users });
});

app.post('/api/users', (req, res) => {
  const { id, username, password, name, role, group } = req.body;
  const db = readDB();

  if (id) {
    const index = db.users.findIndex(u => u.id === id);
    if (index !== -1) {
      db.users[index].username = username;
      if (password) db.users[index].password = password;
      db.users[index].name = name;
      db.users[index].role = role;
      db.users[index].group = group;
    }
  } else {
    if (db.users.some(u => u.username === username)) {
      return res.status(400).json({ success: false, message: '用户名已存在' });
    }
    const newId = 'u_' + Date.now();
    const randomPwd = String(Math.floor(100000 + Math.random() * 900000));

    db.users.push({
      id: newId,
      username,
      password: password || randomPwd,
      name,
      role,
      group: group || 'A'
    });
  }

  writeDB(db);
  res.json({ success: true, message: '人员信息更新成功' });
});

app.delete('/api/users/:id', (req, res) => {
  const { id } = req.params;
  const db = readDB();
  db.users = db.users.filter(u => u.id !== id);
  writeDB(db);
  res.json({ success: true, message: '人员已删除' });
});

app.get('/api/schedules/current', (req, res) => {
  const db = readDB();
  const schedule = db.schedules[db.schedules.length - 1];
  if (!schedule) {
    return res.json({ success: true, schedule: null });
  }
  res.json({ success: true, schedule, users: db.users });
});

app.post('/api/schedules/create', (req, res) => {
  const { year, month, holidayDays } = req.body;
  const db = readDB();

  const totalDays = getDaysInMonth(year, month);
  const holiday = parseInt(holidayDays, 10) || 8;
  const maxSelfSelect = Math.floor(holiday / 2) + 1;

  const newSchedule = {
    id: `sch_${year}_${String(month).padStart(2, '0')}`,
    year: parseInt(year, 10),
    month: parseInt(month, 10),
    totalDays,
    holidayDays: holiday,
    maxSelfSelectDays: maxSelfSelect,
    currentStage: 1,
    stageStartTime: new Date().toISOString(),
    isPublished: false,
    userSelections: {},
    finalSchedule: {},
    backupData: null
  };

  db.schedules.push(newSchedule);
  writeDB(db);
  res.json({ success: true, schedule: newSchedule, message: '新月度排班计划已成功创建' });
});

app.post('/api/schedules/stage', (req, res) => {
  const { scheduleId, stage } = req.body;
  const db = readDB();
  const sch = db.schedules.find(s => s.id === scheduleId);

  if (!sch) {
    return res.status(404).json({ success: false, message: '排班计划不存在' });
  }

  sch.currentStage = parseInt(stage, 10);
  sch.stageStartTime = new Date().toISOString();
  writeDB(db);

  res.json({ success: true, schedule: sch, message: `阶段已切换至第 ${stage} 阶段` });
});

app.post('/api/schedules/select-days', (req, res) => {
  const { scheduleId, userId, selections } = req.body;
  const db = readDB();
  const sch = db.schedules.find(s => s.id === scheduleId);
  const user = db.users.find(u => u.id === userId);

  if (!sch || !user) {
    return res.status(400).json({ success: false, message: '参数无效' });
  }

  let lunCount = 0;
  if (selections && typeof selections === 'object') {
    Object.keys(selections).forEach(d => {
      if (selections[d] === '✅') {
        lunCount++;
      }
    });
  }

  if (lunCount > sch.maxSelfSelectDays) {
    return res.status(400).json({
      success: false,
      message: `超出轮休划假上限！本月最多仅可勾选 ${sch.maxSelfSelectDays} 天轮休假(✅)`
    });
  }

  const isOddMonth = sch.month % 2 !== 0;
  const priorityGroup = isOddMonth ? 'A' : 'B';
  const stage = sch.currentStage;

  let canSubmit = false;
  if (stage === 1 && user.role === 'leader_main') canSubmit = true;
  else if (stage === 2 && user.group === priorityGroup) canSubmit = true;
  else if (stage === 3) canSubmit = true;
  else if (stage >= 4) canSubmit = true;

  if (!canSubmit) {
    return res.status(403).json({
      success: false,
      message: '当前非您的填报时间段，请耐心等待阶段流转至下一轮！'
    });
  }

  sch.userSelections[userId] = selections;
  writeDB(db);

  res.json({ success: true, message: '您的划假方案已成功保存提交！', userSelections: sch.userSelections });
});

app.post('/api/schedules/auto-fill', (req, res) => {
  const { scheduleId } = req.body;
  const db = readDB();
  const sch = db.schedules.find(s => s.id === scheduleId);

  if (!sch) {
    return res.status(404).json({ success: false, message: '排班计划不存在' });
  }

  // 自动热备份
  sch.backupData = {
    userSelections: JSON.parse(JSON.stringify(sch.userSelections || {})),
    finalSchedule: JSON.parse(JSON.stringify(sch.finalSchedule || {})),
    currentStage: sch.currentStage,
    time: new Date().toISOString()
  };

  const solveResult = solveAutoFillSchedule(sch, db.users);

  if (!solveResult.success) {
    return res.status(422).json({
      success: false,
      message: '选假冲突：当前选假方案下无法满足“每日至少1领导+5干部在岗”硬约束，请微调。'
    });
  }

  sch.finalSchedule = solveResult.finalSchedule;
  sch.currentStage = 5;
  writeDB(db);

  res.json({
    success: true,
    message: '智能补全成功！已自动分配剩余全员轮休假(✅)。',
    schedule: sch
  });
});

app.post('/api/schedules/admin-update-cell', (req, res) => {
  const { scheduleId, userId, day, type } = req.body;
  const db = readDB();
  const sch = db.schedules.find(s => s.id === scheduleId);

  if (!sch) {
    return res.status(400).json({ success: false, message: '排班数据无效' });
  }

  // 自动热备份
  if (!sch.backupData) {
    sch.backupData = {
      userSelections: JSON.parse(JSON.stringify(sch.userSelections || {})),
      finalSchedule: JSON.parse(JSON.stringify(sch.finalSchedule || {})),
      currentStage: sch.currentStage,
      time: new Date().toISOString()
    };
  }

  if (!sch.finalSchedule) sch.finalSchedule = {};
  if (!sch.finalSchedule[userId]) sch.finalSchedule[userId] = {};

  if (!type || type === '班' || type.trim() === '') {
    delete sch.finalSchedule[userId][day];
  } else {
    sch.finalSchedule[userId][day] = type;
  }

  writeDB(db);
  res.json({ success: true, schedule: sch, message: '排班已成功微调' });
});

// 管理员一键清零重置 API
app.post('/api/schedules/reset', (req, res) => {
  const { scheduleId } = req.body;
  const db = readDB();
  const sch = db.schedules.find(s => s.id === scheduleId);

  if (!sch) {
    return res.status(404).json({ success: false, message: '排班计划不存在' });
  }

  // 强行产生快照热备份，防止误点！
  sch.backupData = {
    userSelections: JSON.parse(JSON.stringify(sch.userSelections || {})),
    finalSchedule: JSON.parse(JSON.stringify(sch.finalSchedule || {})),
    currentStage: sch.currentStage,
    isPublished: sch.isPublished,
    time: new Date().toISOString()
  };

  // 清空数据重置为第1阶段初始状态
  sch.userSelections = {};
  sch.finalSchedule = {};
  sch.currentStage = 1;
  sch.isPublished = false;

  writeDB(db);
  res.json({
    success: true,
    schedule: sch,
    message: '本月全员排班数据已完成一键清零！已为您自动创建紧急恢复备份。'
  });
});

// 管理员紧急恢复备份 API
app.post('/api/schedules/restore-backup', (req, res) => {
  const { scheduleId } = req.body;
  const db = readDB();
  const sch = db.schedules.find(s => s.id === scheduleId);

  if (!sch || !sch.backupData) {
    return res.status(400).json({ success: false, message: '无可用备份数据可恢复' });
  }

  sch.userSelections = sch.backupData.userSelections || {};
  sch.finalSchedule = sch.backupData.finalSchedule || {};
  if (sch.backupData.currentStage) sch.currentStage = sch.backupData.currentStage;
  if (sch.backupData.isPublished !== undefined) sch.isPublished = sch.backupData.isPublished;

  writeDB(db);
  res.json({
    success: true,
    schedule: sch,
    message: '排班数据已成功恢复至清零前的备份版本！'
  });
});

app.post('/api/schedules/publish', (req, res) => {
  const { scheduleId } = req.body;
  const db = readDB();
  const sch = db.schedules.find(s => s.id === scheduleId);

  if (!sch) {
    return res.status(404).json({ success: false, message: '排班计划不存在' });
  }

  sch.isPublished = true;
  sch.currentStage = 5;
  writeDB(db);

  res.json({ success: true, schedule: sch, message: '月度排班表已成功正式发布！' });
});

app.listen(PORT, () => {
  console.log(`====================================================`);
  console.log(` 🚀 科室智能轮休排班系统 http://localhost:3000`);
  console.log(`====================================================`);
});
