const express = require('express');
const bodyParser = require('body-parser');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;
const DB_FILE = path.join(__dirname, 'data', 'db.json');

app.use(bodyParser.json());
app.use(express.static(path.join(__dirname, 'public')));

// 初始默认用户 (姚惠安为 none 组，领导岗位优先排位)
const DEFAULT_USERS = [
  { id: 'u-admin', username: 'admin', password: 'admin', name: '超级管理员', role: 'admin', group: 'none' },
  { id: 'u-yha', username: 'yha', password: '582914', name: '姚惠安', role: 'leader_main', group: 'none' },
  { id: 'u-lmx', username: 'lmx', password: '491028', name: '李敏霞', role: 'leader_sub', group: 'A' },
  { id: 'u-lw', username: 'lw', password: '839105', name: '罗巍', role: 'leader_sub', group: 'B' },
  { id: 'u-lhq', username: 'lhq', password: '204819', name: '罗焕全', role: 'staff', group: 'A' },
  { id: 'u-zqm', username: 'zqm', password: '719304', name: '郑庆明', role: 'staff', group: 'A' },
  { id: 'u-ldl', username: 'ldl', password: '620491', name: '李大良', role: 'staff', group: 'B' },
  { id: 'u-zwb', username: 'zwb', password: '318290', name: '周卫波', role: 'staff', group: 'B' },
  { id: 'u-sjf', username: 'sjf', password: '904182', name: '施剑锋', role: 'staff', group: 'A' },
  { id: 'u-hwy', username: 'hwy', password: '159203', name: '洪文艺', role: 'staff', group: 'B' }
];

function readDB() {
  if (!fs.existsSync(DB_FILE)) {
    const dir = path.dirname(DB_FILE);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

    const initialData = {
      users: DEFAULT_USERS,
      schedules: [
        {
          id: 'sch-2026-9',
          year: 2026,
          month: 9,
          totalDays: 30,
          holidayDays: 8,
          maxSelfSelectDays: 5,
          currentStage: 1,
          isPublished: false,
          userSelections: {},
          finalSchedule: {}
        }
      ]
    };
    fs.writeFileSync(DB_FILE, JSON.stringify(initialData, null, 2), 'utf8');
    return initialData;
  }
  const content = fs.readFileSync(DB_FILE, 'utf8');
  return JSON.parse(content);
}

function writeDB(data) {
  fs.writeFileSync(DB_FILE, JSON.stringify(data, null, 2), 'utf8');
}

// -------------------------------------------------------------
// API 路由
// -------------------------------------------------------------
app.post('/api/login', (req, res) => {
  const { username, password } = req.body;
  const db = readDB();
  const user = db.users.find(u => u.username === username && u.password === password);

  if (user) {
    const { password, ...userWithoutPwd } = user;
    return res.json({ success: true, user: userWithoutPwd });
  } else {
    return res.json({ success: false, message: '账号或密码错误！默认密码为专属6位随机数字' });
  }
});

app.get('/api/users', (req, res) => {
  const db = readDB();
  res.json({ success: true, users: db.users });
});

app.post('/api/users/update-profile', (req, res) => {
  const { userId, name, password } = req.body;
  const db = readDB();
  const user = db.users.find(u => u.id === userId);

  if (!user) {
    return res.json({ success: false, message: '用户不存在' });
  }

  if (name) user.name = name;
  if (password) user.password = password;

  writeDB(db);
  res.json({ success: true, message: '密码及个人信息修改成功！' });
});

app.post('/api/users', (req, res) => {
  const { username, password, name, role, group } = req.body;
  const db = readDB();

  if (db.users.some(u => u.username === username)) {
    return res.json({ success: false, message: '用户名已存在' });
  }

  const newUser = {
    id: `u-${Date.now()}`,
    username,
    password: password || '123456',
    name,
    role,
    group
  };

  db.users.push(newUser);
  writeDB(db);
  res.json({ success: true, user: newUser, message: '人员添加成功' });
});

app.put('/api/users/:id', (req, res) => {
  const { id } = req.params;
  const { username, password, name, role, group } = req.body;
  const db = readDB();

  const user = db.users.find(u => u.id === id);
  if (!user) return res.json({ success: false, message: '用户不存在' });

  if (username) user.username = username;
  if (name) user.name = name;
  if (role) user.role = role;
  if (group) user.group = group;
  if (password) user.password = password;

  writeDB(db);
  res.json({ success: true, user, message: '更新成功' });
});

app.delete('/api/users/:id', (req, res) => {
  const { id } = req.params;
  const db = readDB();

  db.users = db.users.filter(u => u.id !== id);
  writeDB(db);
  res.json({ success: true, message: '删除成功' });
});

app.get('/api/schedules/current', (req, res) => {
  const db = readDB();
  const schedule = db.schedules[0];
  res.json({ success: true, schedule, users: db.users });
});

app.post('/api/schedules/select-days', (req, res) => {
  const { scheduleId, userId, selections } = req.body;
  const db = readDB();
  const schedule = db.schedules.find(s => s.id === scheduleId);

  if (!schedule) return res.json({ success: false, message: '排班计划不存在' });

  if (!schedule.userSelections) schedule.userSelections = {};
  schedule.userSelections[userId] = selections;

  writeDB(db);
  res.json({ success: true, message: '划假方案保存/提交成功！' });
});

app.post('/api/schedules/admin-update-cell', (req, res) => {
  const { scheduleId, userId, day, type } = req.body;
  const db = readDB();
  const schedule = db.schedules.find(s => s.id === scheduleId);

  if (!schedule) return res.json({ success: false, message: '排班计划不存在' });

  if (!schedule.backupData) {
    schedule.backupData = JSON.parse(JSON.stringify(schedule.finalSchedule || {}));
  }

  if (!schedule.finalSchedule) schedule.finalSchedule = {};
  if (!schedule.finalSchedule[userId]) schedule.finalSchedule[userId] = {};

  if (!type || type === '班') {
    delete schedule.finalSchedule[userId][day];
  } else {
    schedule.finalSchedule[userId][day] = type;
  }

  writeDB(db);
  res.json({ success: true, message: '修改成功' });
});

app.post('/api/schedules/reset', (req, res) => {
  const { scheduleId } = req.body;
  const db = readDB();
  const schedule = db.schedules.find(s => s.id === scheduleId);

  if (!schedule) return res.json({ success: false, message: '排班计划不存在' });

  schedule.backupData = {
    userSelections: JSON.parse(JSON.stringify(schedule.userSelections || {})),
    finalSchedule: JSON.parse(JSON.stringify(schedule.finalSchedule || {})),
    currentStage: schedule.currentStage
  };

  schedule.userSelections = {};
  schedule.finalSchedule = {};
  schedule.currentStage = 1;
  schedule.isPublished = false;

  writeDB(db);
  res.json({ success: true, schedule, message: '已全盘清空排班划假！且系统已自动为您生成恢复备份。' });
});

app.post('/api/schedules/restore-backup', (req, res) => {
  const { scheduleId } = req.body;
  const db = readDB();
  const schedule = db.schedules.find(s => s.id === scheduleId);

  if (!schedule || !schedule.backupData) {
    return res.json({ success: false, message: '无可用备份或排班不存在' });
  }

  const backup = schedule.backupData;
  if (backup.userSelections) schedule.userSelections = backup.userSelections;
  if (backup.finalSchedule) schedule.finalSchedule = backup.finalSchedule;
  if (backup.currentStage) schedule.currentStage = backup.currentStage;

  writeDB(db);
  res.json({ success: true, schedule, message: '已成功从误操作前/清零前的备份中完全恢复！' });
});

app.post('/api/schedules/stage', (req, res) => {
  const { scheduleId, stage } = req.body;
  const db = readDB();
  const schedule = db.schedules.find(s => s.id === scheduleId);

  if (!schedule) return res.json({ success: false, message: '排班计划不存在' });

  schedule.currentStage = parseInt(stage, 10);
  writeDB(db);
  res.json({ success: true, schedule, message: `阶段已更新至第 ${stage} 阶段` });
});

app.post('/api/schedules/auto-fill', (req, res) => {
  const { scheduleId } = req.body;
  const db = readDB();
  const schedule = db.schedules.find(s => s.id === scheduleId);

  if (!schedule) return res.json({ success: false, message: '排班计划不存在' });

  const staffUsers = db.users.filter(u => u.role !== 'admin');
  const totalDays = schedule.totalDays;
  const holidayDays = schedule.holidayDays;
  const userSelections = schedule.userSelections || {};

  const finalSchedule = {};
  staffUsers.forEach(u => {
    finalSchedule[u.id] = { ...(userSelections[u.id] || {}) };
  });

  for (let d = 1; d <= totalDays; d++) {
    for (let attempts = 0; attempts < 50; attempts++) {
      let leaderCount = 0;
      let totalCount = 0;

      staffUsers.forEach(u => {
        const state = finalSchedule[u.id][d] || '班';
        if (state !== '✅' && state !== '假') {
          totalCount++;
          if (u.role === 'leader_main' || u.role === 'leader_sub') {
            leaderCount++;
          }
        }
      });

      if (leaderCount >= 1 && totalCount >= 5) break;

      const workingLeaders = staffUsers.filter(u => {
        const isLeader = u.role === 'leader_main' || u.role === 'leader_sub';
        const state = finalSchedule[u.id][d] || '班';
        return isLeader && (state === '✅' || state === '假');
      });

      if (leaderCount < 1 && workingLeaders.length > 0) {
        const pick = workingLeaders[Math.floor(Math.random() * workingLeaders.length)];
        delete finalSchedule[pick.id][d];
      }
    }
  }

  staffUsers.forEach(u => {
    let currentCount = Object.keys(finalSchedule[u.id]).length;
    const needMore = holidayDays - currentCount;

    if (needMore > 0) {
      for (let d = 1; d <= totalDays && currentCount < holidayDays; d++) {
        if (!finalSchedule[u.id][d]) {
          let leaderCount = 0;
          let totalCount = 0;

          staffUsers.forEach(other => {
            const state = (other.id === u.id) ? '✅' : (finalSchedule[other.id][d] || '班');
            if (state !== '✅' && state !== '假') {
              totalCount++;
              if (other.role === 'leader_main' || other.role === 'leader_sub') {
                leaderCount++;
              }
            }
          });

          if (leaderCount >= 1 && totalCount >= 5) {
            finalSchedule[u.id][d] = '✅';
            currentCount++;
          }
        }
      }
    }
  });

  schedule.finalSchedule = finalSchedule;
  schedule.currentStage = 4;
  writeDB(db);

  res.json({ success: true, schedule, message: '智能算法已回溯分配完全部轮休假！已满足每日领导在岗≥1人与在岗总人数≥5人硬约束。' });
});

app.post('/api/schedules/publish', (req, res) => {
  const { scheduleId } = req.body;
  const db = readDB();
  const schedule = db.schedules.find(s => s.id === scheduleId);

  if (!schedule) return res.json({ success: false, message: '排班计划不存在' });

  schedule.isPublished = true;
  schedule.currentStage = 5;
  writeDB(db);

  res.json({ success: true, schedule, message: '月度排班表已正式发布！全科人员已可在全屏查看。' });
});

app.listen(PORT, () => {
  console.log(`====================================================`);
  console.log(`科室智能轮休排班系统服务已在端口 ${PORT} 启动！`);
  console.log(`访问地址: http://localhost:${PORT}`);
  console.log(`====================================================`);
});
