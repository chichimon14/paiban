# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.8 冒烟测试（追加到 SMOKE_TEST.md 的 v6.8 章节）。

v6.8 变更（2026-11-01 用户两项）：
  A) 登录页清除全部默认密码提示：密码框 placeholder「初始密码 123456」
     撤下（不再设 placeholder），底部整段「普通成员初始密码 123456；
     超级管理员 admin / admin123。…」删除；登录页（index.html）不得
     再出现 123456 / admin123 / 初始密码 任一字样。v6.7 的账号框文案
     （用户名（本人姓名或工号…）/ placeholder「姓名或工号」）保持。
  B) 岗位显示成员端 403 修复（bug，先复现后修复）：根因是模块级状态
     mypostsPersonId 跨账号残留——管理员在选人框选过他人后退出（SPA
     不刷新），普通成员在同一浏览器登录，成员页无选人框却仍把残留的
     person_id 拼进 /api/daily/mine 请求，后端按规 403，前端 catch 又
     把「只有管理员可以查看他人的岗位」当正文红字渲染，成员本人岗位
     反而看不到。修复三层：① loadMyPosts 只允许 canPickPerson() 的
     账号附加 person_id，成员永远只查本人；② doLogin/logout 统一调
     resetMyPostsState() 清零岗位显示查看状态（选人/日期/缓存结果）；
     ③ 成员本人视图万一仍收到该 403，清状态后以纯本人请求重试一次，
     绝不把这句权限提示展示给成员。后端 403 保护口径不变。

测试口径（临时库 + 临时端口 3019）：
  A) 静态：index.html 无三类密码提示字样、密码框无 placeholder、
     v6.7 账号文案仍在。
  B) API：建 11 月计划并发布，给 11-03 保存一份含成员HHH字母岗
     的当日排班；成员按修复后前端的口径（不带 person_id）调 mine →
     200 且 status=ok、letter 对、is_self、timeline 非空（页面与导出
     图片数据齐备）；成员带他人 person_id → 仍 403 且文案不变（后端
     保护未动）；成员带本人 person_id → 200。
  L) 泄漏回归（Node 抽取真实 app.js 函数跑三段链）：管理员选人 →
     真实 logout() → 断言 mypostsPersonId 已清零；成员登录后本人视图
     请求不带 person_id、页面渲染本人视图标记、全程无 403 红字。
  S) 静态断言：版本标记；resetMyPostsState 存在且 doLogin/logout
     均调用；loadMyPosts 的 pid 守卫与 403 自愈重试；旧的直接以
     mypostsPersonId 拼 person_id 的写法已消失。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 3019
BASE = f"http://127.0.0.1:{PORT}"
REPORT = os.path.join(ROOT, "SMOKE_TEST.md")

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), "-", name, ("| " + str(detail) if detail else ""))


def req(method, path, token=None, body=None, base=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request((base or BASE) + path, data=data, method=method)
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


def login(identifier, pw):
    st, out = req("POST", "/api/login", body={"username": identifier, "password": pw})
    return out.get("token") if st == 200 else None


def start_server(dbpath, port):
    env = dict(os.environ, DUTY_DB=dbpath)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--port", str(port)],
        cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            st, _ = req("GET", "/api/health", base=base)
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
/* v6.8 泄漏回归：从真实 app.js 抽取函数，模拟同浏览器三段链。 */
const fs = require('fs');
const cfg = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const src = fs.readFileSync(cfg.appjs, 'utf8');
function extract(re, name) { const m = src.match(re); if (!m) throw new Error('extract: ' + name); return m[0]; }
const code = [
  extract(/function esc\(s\) \{[\s\S]*?\n\}/, 'esc'),
  extract(/function myRole\(\) \{[\s\S]*?\n\}/, 'myRole'),
  extract(/function canPickPerson\(\) \{[^}]*\}/, 'canPickPerson'),
  extract(/function logout\(\) \{[\s\S]*?\n\}/, 'logout'),
  extract(/function resetMyPostsState\(\) \{[^}]*\}/, 'resetMyPostsState'),
  extract(/async function loadMyPosts\(\) \{[\s\S]*?\n\}/, 'loadMyPosts'),
].join('\n');
const el = () => ({ innerHTML: '', textContent: '', value: '',
  classList: { add() {}, remove() {}, toggle() {} } });
const elements = { mypostsBody: el(), appView: el(), loginView: el() };
global.$ = (id) => elements[id];
global.document = { body: { classList: { add() {}, remove() {} } } };
global.localStorage = { _m: {}, setItem(k, v) { this._m[k] = v; },
  getItem(k) { return this._m[k] || null; }, removeItem(k) { delete this._m[k]; } };
global.detail = null; global.plans = [];
global.myPostsHTML = () => 'SELF_VIEW_RENDERED_OK';
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
  global.me = { role: 'admin', person_id: ids['CCC'], username: 'CCC' };
  global.token = cfg.atok;
  global.mypostsPersonId = null; global.mypostsDate = '2026-11-03'; global.mypostsState = null;
  global.mypostsPersonId = Number(String(ids['FFF']));   // 选人框 change 处理器的同一句
  logout();                                              // 真实退出函数
  const afterLogout = global.mypostsPersonId;
  global.me = { role: 'member', person_id: ids['HHH'], username: 'HHH' };
  global.token = cfg.mtok;
  if (!global.mypostsDate) global.mypostsDate = '2026-11-03';  // viewMyPosts 的默认日期句
  await loadMyPosts();                                   // 成员页无选人框、直调
  console.log('RESULT ' + JSON.stringify({
    afterLogout, lastPath, body: elements.mypostsBody.innerHTML }));
})().catch((e) => { console.error('harness error:', e); process.exit(3); });
"""


def main():
    tmpdir = tempfile.mkdtemp(prefix="duty-roster-v68-")
    tmpdb = os.path.join(tmpdir, "test.db")
    proc, up = start_server(tmpdb, PORT)
    try:
        check("v6.8 服务启动", up)
        if not up:
            return 1
        atok = login("admin", "admin123")
        st, people = req("GET", "/api/people", token=atok)
        pid_of = {p["name"]: p["id"] for p in people} if st == 200 else {}

        # ---- B) 数据准备：11 月计划发布 + 11-03 当日排班（含HHH字母岗） ----
        st, plan = req("POST", "/api/plans", token=atok,
                       body={"year": 2026, "month": 11, "quota": 9, "self_limit": 6})
        plan_id = plan["id"] if st in (200, 201) else None
        check("B 建 2026 年 11 月计划成功", plan_id is not None, f"status={st}")
        req("PUT", f"/api/plans/{plan_id}/final/cell", token=atok,
            body={"person_id": pid_of["FFF"], "day": 5, "symbol": "X"})
        req("POST", f"/api/plans/{plan_id}/final/save", token=atok)
        st, _ = req("POST", f"/api/plans/{plan_id}/publish", token=atok)
        st, det = req("GET", f"/api/plans/{plan_id}", token=atok)
        check("B 计划已发布（当日排班依据最终表在岗判定）",
              st == 200 and det["plan"]["published"] is True)

        st, ctx = req("GET", "/api/daily/context?date=2026-11-03", token=atok)
        dft = ctx.get("default") if st == 200 else None
        letters = dict(dft["letters"]) if dft else {}
        zw_id = pid_of["HHH"]
        zw_letter = next((L for L, v in letters.items() if v == zw_id), None)
        if not zw_letter:
            zw_letter = "A"
            letters["A"] = zw_id
        st, _ = req("POST", "/api/daily/assignments", token=atok,
                    body={"date": "2026-11-03", "leader_id": dft["leader_id"],
                          "letters": letters})
        check("B 保存 11-03 当日排班成功且HHH持字母岗",
              st == 200 and letters.get(zw_letter) == zw_id,
              f"status={st} letter={zw_letter}")

        # ---- B) 成员本人视图（修复后前端的调用口径：不带 person_id） ----
        mtok = login("HHH", "123456")
        st, mine = req("GET", "/api/daily/mine?date=2026-11-03", token=mtok)
        res = mine.get("result") or {}
        check("B 成员不带 person_id 调 mine → 200 本人数据（status=ok、letter 对、timeline 非空、is_self）",
              st == 200 and res.get("status") == "ok" and res.get("letter") == zw_letter
              and len(res.get("timeline") or []) > 0 and bool(res.get("leader_name"))
              and mine.get("is_self") is True
              and (mine.get("viewer") or {}).get("id") == zw_id,
              f"status={st} res={res.get('status')}/{res.get('letter')}")
        st, out403 = req("GET", f"/api/daily/mine?date=2026-11-03&person_id={pid_of['AAA']}",
                         token=mtok)
        check("B 成员传他人 person_id → 仍 403（后端保护未动；v6.13 适配：文案改为「您没有查看他人岗位的权限」）",
              st == 403 and out403.get("detail") == "您没有查看他人岗位的权限",
              f"status={st} detail={out403.get('detail')}")
        st, mine_own = req("GET", f"/api/daily/mine?date=2026-11-03&person_id={zw_id}",
                           token=mtok)
        check("B 成员传本人 person_id → 200 且 is_self（后端原口径不变）",
              st == 200 and mine_own.get("is_self") is True, f"status={st}")

        # ---- L) 跨账号状态泄漏回归（Node 跑真实前端函数） ----
        node = shutil.which("node")
        check("L Node 可用（前端函数级回归）", bool(node))
        if node:
            cfg = {"base": BASE, "atok": atok, "mtok": mtok, "ids": pid_of,
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
            check("L 管理员选人后真实 logout() 已清零 mypostsPersonId（残留根源切断）",
                  out.get("afterLogout") is None,
                  f"afterLogout={out.get('afterLogout')} rc={run.returncode}")
            check("L 成员本人视图请求不带 person_id（前端永不为成员拼越权参数）",
                  bool(out.get("lastPath")) and "person_id=" not in out["lastPath"],
                  f"path={out.get('lastPath')}")
            check("L 成员页面渲染本人视图、全程无「只有管理员…」红字",
                  out.get("body") == "SELF_VIEW_RENDERED_OK",
                  f"body={out.get('body')!r}")
    finally:
        stop_server(proc)

    # ---- A/S) 静态断言 ----
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()
    html = open(os.path.join(fe, "index.html"), encoding="utf-8").read()

    check("S app.js 带 v6.8 版本标记", "/* duty-roster v6.31 */" in js)
    check("A 登录页无任何默认密码提示字样（123456 / admin123 / 初始密码 全清）",
          "123456" not in html and "admin123" not in html and "初始密码" not in html)
    pw_line = next((ln for ln in html.splitlines() if 'id="loginPass"' in ln), "")
    check("A 密码框不再带 placeholder（提示文案整段与底部说明段均已删除）",
          "loginPass" in pw_line and "placeholder" not in pw_line
          and 'class="hint"' not in html)
    check("A v6.7 账号框文案保持（本人姓名或工号 / placeholder 姓名或工号）",
          "本人姓名或工号" in html and 'placeholder="姓名或工号"' in html)
    check("S resetMyPostsState 存在且 doLogin/logout 均调用（换账号/退出清零）",
          "function resetMyPostsState()" in js
          and "resetMyPostsState();" in segment(js, "async function doLogin()", "function logout()")
          and "resetMyPostsState();" in segment(js, "function logout()", "/* ---------------- 框架/导航"))
    lmp = segment(js, "async function loadMyPosts()", "function myShiftCardHTML")
    check("S loadMyPosts 守卫：person_id 仅 canPickPerson() 时附加（成员永不带）",
          "canPickPerson() ? mypostsPersonId : null" in lmp
          and "&person_id=${pid}" in lmp
          and "&person_id=${mypostsPersonId}" not in js)
    check("S loadMyPosts 403 自愈：成员收到该文案时清状态并以纯本人请求重试一次（v6.13 适配：匹配文案随后端改字）",
          "String(e.message).includes('您没有查看他人岗位的权限')" in lmp
          and "api('GET', `/api/daily/mine?date=${mypostsDate}`)" in lmp
          and "mypostsPersonId = null;" in lmp)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v6.8 引起的旧套件改动）：
  - 全部套件（v25–v67）：版本标记断言由 v6.7 提升为 v6.8；
  - smoke_test_v64.py：「S 选人接线」断言适配——loadMyPosts 改经
    守卫变量 pid 附加选人参数（成员为 null），字面量由
    &person_id=${mypostsPersonId} 改为 &person_id=${pid}（检查名
    已注明 v6.8 适配）；
  - smoke_test_v65.py「loadMyPosts 绑定不变」断言原文仍成立：
    mpImgBtn 绑定语句逐字保留（移入 loadMyPosts 内的 render 闭包），
    无需改写；
  - 其余旧套件逐项核查过：无任何套件断言过登录页密码框 placeholder
    或底部密码说明段（ grep 核查「普通成员初始密码 / placeholder=
    初始密码」零命中），Item A 删除无需适配；各套件以初始密码登录
    测试账号的调用是测试夹具、与页面文案无关，不受影响；
  - 后端零改动：/api/daily/mine 的 403 保护与响应结构未动，v64
    的 E 组选人权限断言原样成立。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.8 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：临时数据库 + 临时服务端口 3019（API/成员端到端）+ Node 函数级回归（抽取真实 app.js 的 loadMyPosts/logout 等函数跑跨账号泄漏链）+ 纯静态检查（前端）\n")
            f.write("- v6.8：①登录页清除全部默认密码提示（密码框 placeholder 与底部说明段删除）；"
                    "②岗位显示成员端 403 修复：person_id 仅管理员/超管可附加、登录/退出清零"
                    "选人状态、成员遇该 403 自愈重试本人视图；后端保护不变。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.8: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
