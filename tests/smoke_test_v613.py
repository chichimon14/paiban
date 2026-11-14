# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.13 冒烟测试（追加到 SMOKE_TEST.md 的 v6.13 章节）。

v6.13 变更（2026-11-02 用户要求）：把岗位显示模块的「看其他人排班 +
生成图片」开通给两名协管员JJJ、KKK。实现为人员级能力开关：
  - people 新增列 can_view_others（INTEGER NOT NULL DEFAULT 0），
    init_db 幂等迁移（与 v6.7 work_id 同款：CREATE TABLE 带列 +
    旧库 ALTER 补列）；get_people/get_person 统一转 bool 输出；
  - 判定收敛为后端 user_can_view_others(conn, user)：admin/super
    角色，或本人 people.can_view_others=1；/api/daily/mine 传他人
    person_id 时以此放行，无资格仍 403——文案由「只有管理员可以
    查看他人的岗位」改为如实的「您没有查看他人岗位的权限」（旧
    文案已不准确：被授权成员同样可看），前端 loadMyPosts 的 403
    自愈匹配同步更新；
  - /api/me 与登录响应附带 can_view_others（实时查人员表）：前端
    canPickPerson() = admin/super 或 me.can_view_others，授权取自
    进页 /api/me 最新值；被授权成员的选人框、看他人卡片、导出他人
    图片与管理员视图完全同路（myPostsHTML/myPostsImage 不变）；
    未授权成员仍走 v6.8 守卫：请求永不带 person_id、自愈重试不变；
  - 超管「人员与权限」表新增「可看他人岗位」勾选列（pv-<id>），
    随行保存 PUT 一并提交 can_view_others，随时可授予/收回；
  - 范围红线：该开关只放大岗位显示一处——当日排班 context/保存、
    最终表批量修改、管理台接口对被授权成员仍按 member 角色 403。

测试口径（临时库 + 临时端口 3021）：
  M) 迁移：新库全员默认 False；PUT 授予后为 True；停服后用 sqlite
     删列模拟旧库 → 重启自动补列（默认 0）、既有数据（工号）不丢；
     再重启一次（列已存在的幂等分支）仍正常；
  A) /api/me 与登录响应：未授权 False、授予后同一 token 的 /api/me
     即时 True、登录响应 True，未授权成员恒 False；
  D) 数据：11 月计划发布；11-02（早班）按 A GGG/B CCC/C DDD/
     D HHH/E EEE、带班CCC保存；11-03（晚班）保存默认排班；
  P) 权限矩阵：被授权协管员看干部 → 200 对方字母岗卡（is_self=False、
     letter/timeline 对）；看另一协管员 → 200 退税岗卡；未授权成员
     看他人 → 403 且新文案；本人视图（带/不带本人 id）不变；管理员、
     超管看他人不变；
  X) 范围红线：被授权成员调 context / 保存当日排班 / 最终表批量
     修改 / 账号列表仍全部 403；
  F) 收回与再授予：PUT 关 → /api/me False 且看他人 403；再开 → 恢复；
  L) 前端链（Node 抽取真实 app.js）：被授权成员 loadMyPosts 带
     person_id 发请求；未授权成员即使 mypostsPersonId 有残留也不带；
  S) 静态断言：版本标记、后端迁移/判定/文案、前端选人门/人员表
     开关列/保存载荷、旧 403 文案全库清除。
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 3021
BASE = f"http://127.0.0.1:{PORT}"
REPORT = os.path.join(ROOT, "SMOKE_TEST.md")

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), "-", name, ("| " + str(detail) if detail else ""))


def req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}


def login(name, pw):
    st, out = req("POST", "/api/login", body={"username": name, "password": pw})
    return (out.get("token"), out) if st == 200 else (None, out)


def start_server(dbpath):
    env = dict(os.environ, DUTY_DB=dbpath)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--port", str(PORT)],
        cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(60):
        try:
            st, _ = req("GET", "/api/health")
            if st == 200:
                return proc, True
        except Exception:
            pass
        time.sleep(0.5)
    return proc, False


def stop_server(proc):
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()
    except Exception:
        pass


def segment(text, start_marker, end_marker):
    a = text.index(start_marker)
    b = text.index(end_marker, a)
    return text[a:b]


HARNESS_JS = r"""
/* v6.13 前端链：抽取真实 app.js 函数，验被授权/未授权成员的请求口径。 */
const fs = require('fs');
const cfg = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const src = fs.readFileSync(cfg.appjs, 'utf8');
function extract(re, name) { const m = src.match(re); if (!m) throw new Error('extract: ' + name); return m[0]; }
const code = [
  extract(/function esc\(s\) \{[\s\S]*?\n\}/, 'esc'),
  extract(/function myRole\(\) \{[\s\S]*?\n\}/, 'myRole'),
  extract(/function canPickPerson\(\) \{[^}]*\}/, 'canPickPerson'),
  extract(/function resetMyPostsState\(\) \{[^}]*\}/, 'resetMyPostsState'),
  extract(/async function loadMyPosts\(\) \{[\s\S]*?\n\}/, 'loadMyPosts'),
].join('\n');
const el = () => ({ innerHTML: '', textContent: '', value: '',
  classList: { add() {}, remove() {}, toggle() {} } });
const elements = { mypostsBody: el() };
global.$ = (id) => elements[id];
global.myPostsHTML = () => 'CARD_RENDERED_OK';
global.myPostsImage = () => {};
let lastPath = null;
global.api = async (method, path) => {
  lastPath = path;
  const res = await fetch(cfg.base + path, { method,
    headers: { 'Content-Type': 'application/json',
      ...(global.token ? { Authorization: 'Bearer ' + global.token } : {}) } });
  let data = null; try { data = await res.json(); } catch (e) {}
  if (!res.ok) throw new Error((data && data.detail) || ('请求失败 ' + res.status));
  return data;
};
eval(code);
(async () => {
  const ids = cfg.ids;
  // 阶段一：被授权协管员（KKK）选人看HHH
  global.me = { role: 'member', person_id: ids['KKK'], username: 'KKK', can_view_others: true };
  global.token = cfg.btok;
  global.mypostsDate = '2026-11-02'; global.mypostsState = null;
  global.mypostsPersonId = ids['HHH'];
  const pickFlagged = canPickPerson();
  await loadMyPosts();
  const flaggedPath = lastPath, flaggedBody = elements.mypostsBody.innerHTML;
  // 阶段二：未授权成员（FFF），mypostsPersonId 带残留值
  global.me = { role: 'member', person_id: ids['FFF'], username: 'FFF' };
  global.token = cfg.xtok;
  global.mypostsPersonId = ids['HHH'];
  const pickPlain = canPickPerson();
  await loadMyPosts();
  console.log('RESULT ' + JSON.stringify({
    pickFlagged, flaggedPath, flaggedBody, pickPlain,
    plainPath: lastPath, plainBody: elements.mypostsBody.innerHTML }));
})().catch((e) => { console.error('harness error:', e); process.exit(3); });
"""


def main():
    tmpdir = tempfile.mkdtemp(prefix="duty-roster-v613-")
    tmpdb = os.path.join(tmpdir, "test.db")

    # ================= M) 迁移 =================
    proc, up = start_server(tmpdb)
    try:
        check("M v6.13 服务启动（新库）", up)
        if not up:
            return 1
        atok, _ = login("admin", "admin123")
        st, people = req("GET", "/api/people", token=atok)
        pid_of = {p["name"]: p["id"] for p in people} if st == 200 else {}
        check("M 新库全员带 can_view_others 字段且默认 False",
              st == 200 and len(people) == 11
              and all(p.get("can_view_others") is False for p in people),
              f"n={len(people) if st == 200 else st}")
        st, _ = req("PUT", f"/api/people/{pid_of['JJJ']}", token=atok,
                    body={"can_view_others": True})
        st2, people2 = req("GET", "/api/people", token=atok)
        by_name = {p["name"]: p for p in people2} if st2 == 200 else {}
        check("M 超管 PUT 授予JJJ → 仅她为 True（随行保存通道可用）",
              st == 200 and by_name.get("JJJ", {}).get("can_view_others") is True
              and by_name.get("KKK", {}).get("can_view_others") is False,
              f"put={st}")
    finally:
        stop_server(proc)

    # 模拟旧库：删掉 can_view_others 列（其余数据保留），重启应自动补列
    conn = sqlite3.connect(tmpdb)
    conn.execute("ALTER TABLE people DROP COLUMN can_view_others")
    conn.commit()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(people)").fetchall()]
    wid = conn.execute("SELECT work_id FROM people WHERE name='AAA'").fetchone()[0]
    conn.close()
    check("M 旧库模拟就绪（列已删、工号数据保留）",
          "can_view_others" not in cols and wid == "111", f"work_id={wid}")

    proc, up = start_server(tmpdb)
    try:
        check("M 旧库重启启动成功（迁移补列不报错）", up)
        if not up:
            return 1
        atok, _ = login("admin", "admin123")
        st, people = req("GET", "/api/people", token=atok)
        by_name = {p["name"]: p for p in people} if st == 200 else {}
        check("M 迁移后全员 can_view_others 回到默认 False、工号等既有数据不丢",
              st == 200 and all(p.get("can_view_others") is False for p in people)
              and by_name.get("AAA", {}).get("work_id") == "111")
    finally:
        stop_server(proc)

    proc, up = start_server(tmpdb)
    try:
        check("M 列已存在时再重启仍正常（迁移幂等）", up)
        if not up:
            return 1
        atok, _ = login("admin", "admin123")
        st, people = req("GET", "/api/people", token=atok)
        pid_of = {p["name"]: p["id"] for p in people} if st == 200 else {}

        # ================= A) /api/me 暴露 =================
        btok, blogin = login("KKK", "123456")
        check("A 未授权时KKK登录响应 can_view_others=False",
              blogin.get("can_view_others") is False, str(blogin.get("can_view_others")))
        st, me_b = req("GET", "/api/me", token=btok)
        check("A 未授权时KKK /api/me can_view_others=False、role=member",
              st == 200 and me_b.get("can_view_others") is False
              and me_b.get("role") == "member")
        xtok, _ = login("FFF", "123456")
        st, me_x = req("GET", "/api/me", token=xtok)
        check("A 未授权成员FFF /api/me can_view_others=False",
              st == 200 and me_x.get("can_view_others") is False)
        for nm in ("JJJ", "KKK"):
            req("PUT", f"/api/people/{pid_of[nm]}", token=atok,
                body={"can_view_others": True})
        st, me_b2 = req("GET", "/api/me", token=btok)
        check("A 授予后KKK同一 token 的 /api/me 即时变 True（实时查库）",
              st == 200 and me_b2.get("can_view_others") is True)
        gtok, glogin = login("JJJ", "123456")
        st, me_g = req("GET", "/api/me", token=gtok)
        check("A JJJ登录响应与 /api/me 均为 True",
              glogin.get("can_view_others") is True
              and st == 200 and me_g.get("can_view_others") is True)
        st, me_x2 = req("GET", "/api/me", token=xtok)
        check("A FFF仍为 False（授权只给两人）",
              st == 200 and me_x2.get("can_view_others") is False)

        # ================= D) 数据准备 =================
        st, plan = req("POST", "/api/plans", token=atok,
                       body={"year": 2026, "month": 11, "quota": 9, "self_limit": 6})
        plan_id = plan["id"] if st in (200, 201) else None
        check("D 建 2026 年 11 月计划成功", plan_id is not None, f"status={st}")
        req("PUT", f"/api/plans/{plan_id}/final/cell", token=atok,
            body={"person_id": pid_of["FFF"], "day": 5, "symbol": "X"})
        req("POST", f"/api/plans/{plan_id}/final/save", token=atok)
        req("POST", f"/api/plans/{plan_id}/publish", token=atok)
        st, det = req("GET", f"/api/plans/{plan_id}", token=atok)
        check("D 计划已发布", st == 200 and det["plan"]["published"] is True)
        letters_1102 = {"A": pid_of["GGG"], "B": pid_of["CCC"],
                        "C": pid_of["DDD"], "D": pid_of["HHH"],
                        "E": pid_of["EEE"]}
        st, _ = req("POST", "/api/daily/assignments", token=atok,
                    body={"date": "2026-11-02", "leader_id": pid_of["CCC"],
                          "letters": letters_1102})
        check("D 保存 11-02（早班）当日排班（带班CCC、D=HHH）",
              st == 200, f"status={st}")
        st, ctx = req("GET", "/api/daily/context?date=2026-11-03", token=atok)
        dft = ctx.get("default") if st == 200 else None
        st2, _ = req("POST", "/api/daily/assignments", token=atok,
                     body={"date": "2026-11-03", "leader_id": dft["leader_id"],
                           "letters": dft["letters"]})
        check("D 保存 11-03（晚班）默认当日排班（退税岗自动带出）",
              st == 200 and st2 == 200 and dft is not None,
              f"ctx={st} save={st2}")
        holder_letter = next(L for L, v in dft["letters"].items() if v)
        holder_id = dft["letters"][holder_letter]

        # ================= P) 权限矩阵 =================
        st, mine = req("GET", f"/api/daily/mine?date=2026-11-02&person_id={pid_of['HHH']}",
                       token=btok)
        res = mine.get("result") or {}
        check("P 被授权协管员KKK看HHH → 200 对方卡（is_self=False、D 岗、timeline 非空、带班CCC）",
              st == 200 and mine.get("is_self") is False
              and (mine.get("view_person") or {}).get("id") == pid_of["HHH"]
              and res.get("status") == "ok" and res.get("letter") == "D"
              and len(res.get("timeline") or []) > 0
              and res.get("leader_name") == "CCC",
              f"status={st} res={res.get('status')}/{res.get('letter')}")
        st, mine = req("GET", f"/api/daily/mine?date=2026-11-03&person_id={pid_of['JJJ']}",
                       token=btok)
        res = mine.get("result") or {}
        check("P KKK看JJJ（晚班）→ 200 退税岗卡（status=tax、tax_names 含JJJ、is_self=False）",
              st == 200 and res.get("status") == "tax"
              and "JJJ" in (res.get("tax_names") or [])
              and mine.get("is_self") is False,
              f"status={st} res={res.get('status')}")
        st, mine = req("GET", f"/api/daily/mine?date=2026-11-03&person_id={holder_id}",
                       token=gtok)
        res = mine.get("result") or {}
        check("P JJJ看字母岗干部 → 200 对方卡（status=ok、letter 与保存值一致）",
              st == 200 and res.get("status") == "ok"
              and res.get("letter") == holder_letter
              and mine.get("is_self") is False,
              f"status={st} letter={res.get('letter')}")
        st, out403 = req("GET", f"/api/daily/mine?date=2026-11-02&person_id={pid_of['HHH']}",
                         token=xtok)
        check("P 未授权成员FFF看他人 → 403 且文案为「您没有查看他人岗位的权限」",
              st == 403 and out403.get("detail") == "您没有查看他人岗位的权限",
              f"status={st} detail={out403.get('detail')}")
        st, mine = req("GET", "/api/daily/mine?date=2026-11-02", token=xtok)
        st2, mine2 = req("GET", f"/api/daily/mine?date=2026-11-02&person_id={pid_of['FFF']}",
                         token=xtok)
        check("P FFF本人视图不变（不带参/带本人 id 均 200、is_self=True）",
              st == 200 and mine.get("is_self") is True
              and st2 == 200 and mine2.get("is_self") is True,
              f"st={st}/{st2}")
        st, mine = req("GET", "/api/daily/mine?date=2026-11-03", token=btok)
        res = mine.get("result") or {}
        check("P KKK本人视图不变（11-03 晚班本人退税岗、is_self=True）",
              st == 200 and mine.get("is_self") is True
              and res.get("status") == "tax",
              f"status={st} res={res.get('status')}")
        st, users = req("GET", "/api/users", token=atok)
        lw_user = [u for u in users if u["username"] == "CCC"][0]
        req("PATCH", f"/api/users/{lw_user['id']}", token=atok, body={"is_admin": True})
        ltok, _ = login("CCC", "123456")
        st, mine = req("GET", f"/api/daily/mine?date=2026-11-02&person_id={pid_of['HHH']}",
                       token=ltok)
        res = mine.get("result") or {}
        check("P 管理员CCC看他人不变（200、D 岗、is_self=False）",
              st == 200 and res.get("letter") == "D" and mine.get("is_self") is False,
              f"status={st}")
        st, mine = req("GET", f"/api/daily/mine?date=2026-11-03&person_id={pid_of['JJJ']}",
                       token=atok)
        res = mine.get("result") or {}
        check("P 超管看他人不变（200、JJJ退税岗）",
              st == 200 and res.get("status") == "tax", f"status={st}")

        # ================= X) 范围红线 =================
        st, _ = req("GET", "/api/daily/context?date=2026-11-02", token=btok)
        check("X 被授权成员调当日排班 context（编辑口）仍 403",
              st == 403, f"status={st}")
        st, _ = req("POST", "/api/daily/assignments", token=btok,
                    body={"date": "2026-11-02", "leader_id": None, "letters": {}})
        check("X 被授权成员保存当日排班仍 403", st == 403, f"status={st}")
        st, _ = req("POST", f"/api/plans/{plan_id}/final/edits", token=btok,
                    body={"edits": []})
        check("X 被授权成员改最终表（final/edits）仍 403", st == 403, f"status={st}")
        st, _ = req("GET", "/api/users", token=btok)
        check("X 被授权成员调账号列表（超管口）仍 403", st == 403, f"status={st}")
        st, _ = req("PUT", f"/api/people/{pid_of['FFF']}", token=btok,
                    body={"can_view_others": True})
        check("X 被授权成员不能给他人开授权（人员 PUT 为超管口）仍 403",
              st == 403, f"status={st}")

        # ================= F) 收回 / 再授予 =================
        req("PUT", f"/api/people/{pid_of['KKK']}", token=atok,
            body={"can_view_others": False})
        st, me_b3 = req("GET", "/api/me", token=btok)
        st2, _ = req("GET", f"/api/daily/mine?date=2026-11-02&person_id={pid_of['HHH']}",
                     token=btok)
        check("F 收回后KKK /api/me 变 False、看他人回到 403",
              st == 200 and me_b3.get("can_view_others") is False and st2 == 403,
              f"me={st} mine={st2}")
        req("PUT", f"/api/people/{pid_of['KKK']}", token=atok,
            body={"can_view_others": True})
        st, me_b4 = req("GET", "/api/me", token=btok)
        st2, _ = req("GET", f"/api/daily/mine?date=2026-11-02&person_id={pid_of['HHH']}",
                     token=btok)
        check("F 再授予后恢复（/api/me True、看他人 200）",
              st == 200 and me_b4.get("can_view_others") is True and st2 == 200,
              f"me={st} mine={st2}")

        # ================= L) 前端链（Node 抽取真实 app.js） =================
        node = shutil.which("node")
        check("L Node 可用（前端函数级回归）", bool(node))
        if node:
            cfg = {"base": BASE, "btok": btok, "xtok": xtok, "ids": pid_of,
                   "appjs": os.path.join(ROOT, "frontend", "app.js")}
            cfg_path = os.path.join(tmpdir, "harness-env.json")
            js_path = os.path.join(tmpdir, "harness.js")
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False)
            with open(js_path, "w", encoding="utf-8") as f:
                f.write(HARNESS_JS)
            run = subprocess.run([node, js_path, cfg_path],
                                 capture_output=True, text=True, timeout=120)
            line = next((ln for ln in run.stdout.splitlines()
                         if ln.startswith("RESULT ")), "")
            out = json.loads(line[7:]) if line else {}
            check("L 被授权成员 canPickPerson()=True、请求带 person_id、渲染对方卡片",
                  out.get("pickFlagged") is True
                  and f"person_id={pid_of['HHH']}" in (out.get("flaggedPath") or "")
                  and out.get("flaggedBody") == "CARD_RENDERED_OK",
                  f"path={out.get('flaggedPath')} rc={run.returncode}")
            check("L 未授权成员 canPickPerson()=False、残留 person_id 永不发出、渲染本人卡片",
                  out.get("pickPlain") is False
                  and "person_id=" not in (out.get("plainPath") or "person_id=")
                  and out.get("plainBody") == "CARD_RENDERED_OK",
                  f"path={out.get('plainPath')}")
    finally:
        stop_server(proc)

    # ================= S) 静态断言 =================
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()
    backend = open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read()

    check("S app.js 带 v6.13 版本标记", "/* duty-roster v6.31 */" in js)
    check("S 后端迁移与字段：people 建表带列 + 旧库 ALTER 补列 + PersonIn 字段 + PUT 落库",
          "can_view_others INTEGER NOT NULL DEFAULT 0" in backend
          and 'if "can_view_others" not in _cols("people")' in backend
          and "ALTER TABLE people ADD COLUMN can_view_others INTEGER NOT NULL DEFAULT 0" in backend
          and "can_view_others: bool | None = None" in backend
          and 'sets.append("can_view_others=?")' in backend)
    check("S 后端判定收敛：user_can_view_others 定义且 mine 与 /api/me 均调用",
          "def user_can_view_others(conn, user)" in backend
          and "if not user_can_view_others(conn, user)" in backend
          and backend.count("user_can_view_others(") >= 4,
          f"count={backend.count('user_can_view_others(')}")
    check("S 403 文案更新且旧文案全库清除（后端 raise 与前端自愈匹配同为新文案）",
          'raise HTTPException(403, "您没有查看他人岗位的权限")' in backend
          and "只有管理员可以查看他人的岗位" not in backend
          and "只有管理员可以查看他人的岗位" not in js
          and "String(e.message).includes('您没有查看他人岗位的权限')" in js)
    check("S 前端选人门：canPickPerson 含角色或 me.can_view_others（取自 /api/me 的 me 对象）",
          "function canPickPerson() { return myRole() === 'admin' || myRole() === 'super' || !!(me && me.can_view_others); }" in js
          and "canPickPerson() ? mypostsPersonId : null" in js)
    check("S 人员与权限表开关列：表头「可看他人岗位」+ pv- 勾选随人员行渲染（按 p.can_view_others 回显）",
          "<th>可看他人岗位</th>" in js
          and 'id="pv-${p.id}" type="checkbox"' in js
          and "${p.can_view_others ? 'checked' : ''}" in js)
    check("S 行保存载荷带 can_view_others（pv- 勾选值随 PUT 提交）",
          "can_view_others: $('pv-' + pid).checked," in js)
    check("S 范围红线静态面：当日排班管理员守卫与最终表角色守卫均未引用该开关（仍纯按角色判定）",
          "can_view_others" not in segment(backend, "def _require_daily_admin",
                                           '@app.get("/api/daily/context")')
          and 'if user["role"] not in ("admin", "super"):' in backend)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v6.13 引起的旧套件改动）：
  - 全部旧套件：版本标记断言由 v6.12 提升为 v6.13（仅标记字面量）；
  - smoke_test_v29.py：合并表表头断言适配——角色后新增「可看他人
    岗位」列，表头字面量同步更新（检查名已注明 v6.13 适配）；其行
    保存载荷断言（active, 结尾字面量）因新字段插在 active 之前而
    原样成立；
  - smoke_test_v64.py：「S 选人后端」断言适配——403 文案改查新
    文案「您没有查看他人岗位的权限」并加查 user_can_view_others
    判定（检查名已注明）；E 组行为断言（成员看他人 403、管理员/
    超管口径）不变、原样成立；
  - smoke_test_v68.py：两处断言适配——B 组 403 文案等值断言与 S
    组自愈匹配字面量同步改为新文案（检查名已注明）；L 组泄漏回归
    的前端函数抽取正则（canPickPerson 单行无花括号体）对新实现
    原样适用，行为断言不变；
  - 后端口径变化仅三处：people 加列（默认 0，老数据零影响）、
    mine 看他人判定放宽至被授权成员、403 文案改字；其余接口与
    响应结构不变（/api/me、登录响应为纯新增字段）。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.13 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：临时数据库 + 临时服务端口 3021（API 端到端 + 迁移重启链）+ Node 函数级回归（抽取真实 app.js 的 canPickPerson/loadMyPosts）+ 纯静态检查\n")
            f.write("- v6.13：岗位显示「看他人 + 导出他人图片」按人员授权开通（people.can_view_others，"
                    "超管人员与权限表可开关）；判定收敛 user_can_view_others（角色或被授权）；"
                    "403 文案改为「您没有查看他人岗位的权限」；开关仅作用于岗位显示，"
                    "当日排班编辑/最终表/管理台对被授权成员仍 403。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.13: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
