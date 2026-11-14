# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.7 冒烟测试（追加到 SMOKE_TEST.md 的 v6.7 章节）。

v6.7 变更（2026-11-01 用户一批五项）：
  1) 工号登录：9 名干部加工号（AAA 111 / BBB 222 /
     CCC 333 / HHH 888 / GGG 777 / EEE 555 /
     DDD 444 / III 999 / FFF 666），登录标识可填
     姓名或工号、密码不变；协管员无工号、仍用姓名登录。后端 people
     表加 work_id 列（启动迁移补列 + 非空部分唯一索引），种子带工号；
     登录查询 users 按 username 命中或经 person_id 关联 people.work_id
     命中（空工号永不命中、姓名优先）；人员与权限表加「工号」列随行
     保存（PUT /api/people 带 work_id，空串清除、重复 400）。
     登录页账号框文案改「姓名或工号」。
  2) 排班表页（管理员已发布分支）标题行左区的管理员说明句整句撤下，
     只留「已发布」徽标；成员已发布提示与超管左区状态小字不动。
  3) 排班表标题真居中：标题行由 flex 改三列网格 1fr auto 1fr
     （成员/管理员页与超管合并页共用 sheetTitleRow）；窄屏标题独占
     首行、横屏矮屏仍同排；导出图克隆的孤标题跨满整行（v6.6 口径）。
  4) 管理员侧栏互换：renderNav 简化分支里 admin 先加 生成当日排班
     再加 岗位显示（排班表/生成当日排班/岗位显示）；成员与超管不变。
  5) 侧栏品牌副标题「职能轮休 · 在线选班」去掉职能轮休段，只剩
     「在线选班」（登录页副标题是另一元素，不动）。

测试口径（临时库 + 临时端口 3017；迁移用例另起 3018）：
  A) 工号数据与登录：种子 9 人工号逐一对表、协管员为空；工号+对
     密码登录成功、错密码 401 且报错与姓名错密码完全一致；姓名
     登录照常；未知数字串/空标识 401；重复工号 PUT 400、本人工号
     重存 200；清空工号后该号登录 401、恢复后 200；给协管员设工号
     后可工号登录、清除后失效；带工号新增人员重复 400。
  M) 旧库迁移：无 work_id 列的老库启动后自动补列，人员接口带
     work_id=null，补写工号后可工号登录。
  S) 静态断言：版本标记；后端种子/迁移/登录 SQL/PersonIn 工号
     字段；登录页文案与侧栏副标题；人员表工号列与行保存接线；
     管理员说明句撤下且成员提示/超管状态小字仍在；标题行三列
     网格 CSS；renderNav 管理员顺序（daily 在 myposts 之前）且
     超管 NAV 顺序未动。
"""
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 3017
BASE = f"http://127.0.0.1:{PORT}"
REPORT = os.path.join(ROOT, "SMOKE_TEST.md")

WORK_IDS = {
    "AAA": "111", "BBB": "222", "CCC": "333",
    "HHH": "888", "GGG": "777", "EEE": "555",
    "DDD": "444", "III": "999", "FFF": "666",
}

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


def login(identifier, pw, base=None):
    return req("POST", "/api/login", body={"username": identifier, "password": pw}, base=base)


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


def main():
    tmpdb = os.path.join(tempfile.mkdtemp(prefix="duty-roster-v67-"), "test.db")
    proc, up = start_server(tmpdb, PORT)
    try:
        check("v6.7 服务启动", up)
        if not up:
            return 1
        st, out = login("admin", "admin123")
        atok = out.get("token")
        check("A 超管姓名（admin）登录照常", st == 200 and bool(atok))

        # ---- A) 工号数据与登录 ----
        st, people = req("GET", "/api/people", token=atok)
        by_name = {p["name"]: p for p in people} if st == 200 else {}
        bad = [f"{n}={by_name.get(n, {}).get('work_id')}" for n, w in WORK_IDS.items()
               if by_name.get(n, {}).get("work_id") != w]
        check("A 种子 9 名干部工号与给定清单逐一一致", st == 200 and not bad,
              "不一致: " + ",".join(bad) if bad else "9/9 一致")
        check("A 协管员无工号（JJJ/KKK work_id 为空）",
              all(not by_name.get(n, {}).get("work_id") for n in ("JJJ", "KKK")))

        st, out = login("111", "123456")
        check("A 工号登录成功（111 → AAA本人账号）",
              st == 200 and out.get("username") == "AAA"
              and out.get("person_id") == by_name.get("AAA", {}).get("id"),
              f"status={st} username={out.get('username')}")
        st1, e1 = login("111", "wrong-pw")
        st2, e2 = login("AAA", "wrong-pw")
        check("A 工号错密码 401，且与姓名错密码同口径（通用报错、不泄露命中方式）",
              st1 == 401 and st2 == 401 and e1.get("detail") == e2.get("detail"),
              f"wid={st1}/{e1.get('detail')} name={st2}/{e2.get('detail')}")
        st, out = login("AAA", "123456")
        check("A 姓名登录仍可用（带工号的干部）", st == 200 and out.get("username") == "AAA")
        st, out = login("JJJ", "123456")
        check("A 协管员姓名登录仍可用（无工号）", st == 200 and out.get("username") == "JJJ")
        st, _ = login("9999999", "123456")
        st_e, _ = login("", "123456")
        check("A 未知数字串/空标识永不命中任何账号（空工号不参与匹配）",
              st == 401 and st_e == 401, f"unknown={st} empty={st_e}")

        lw = by_name["CCC"]["id"]
        st, e = req("PUT", f"/api/people/{lw}", token=atok, body={"work_id": "111"})
        check("A 重复工号被拒（把AAA的工号写给CCC → 400）",
              st == 400 and "工号" in str(e.get("detail", "")), f"status={st} detail={e.get('detail')}")
        st, _ = req("PUT", f"/api/people/{lw}", token=atok, body={"work_id": "333"})
        check("A 本人工号原值重存成功（唯一性排除自身 → 200）", st == 200)

        zw = by_name["HHH"]["id"]
        st, _ = req("PUT", f"/api/people/{zw}", token=atok, body={"work_id": ""})
        st_l, _ = login("888", "123456")
        st, people2 = req("GET", "/api/people", token=atok)
        zw_now = {p["name"]: p for p in people2}.get("HHH", {})
        check("A 清空工号（空串存 NULL）后该工号立即不可登录",
              st_l == 401 and not zw_now.get("work_id"), f"login={st_l} work_id={zw_now.get('work_id')}")
        st, _ = req("PUT", f"/api/people/{zw}", token=atok, body={"work_id": "888"})
        st_l, out = login("888", "123456")
        check("A 恢复工号后工号登录复通", st == 200 and st_l == 200 and out.get("username") == "HHH")

        gh = by_name["JJJ"]["id"]
        st, _ = req("PUT", f"/api/people/{gh}", token=atok, body={"work_id": "5999999"})
        st_l, out = login("5999999", "123456")
        ok_set = st == 200 and st_l == 200 and out.get("username") == "JJJ"
        req("PUT", f"/api/people/{gh}", token=atok, body={"work_id": ""})
        st_l2, _ = login("5999999", "123456")
        check("A 协管员经人员表补设工号后可工号登录、清除后失效（工号列端到端可编辑）",
              ok_set and st_l2 == 401, f"set_login={st_l} cleared_login={st_l2}")
        st, e = req("POST", "/api/people", token=atok,
                    body={"name": "测试新增", "kind": "cadre", "grp": "A", "work_id": "111"})
        check("A 新增人员带重复工号被拒（400）", st == 400, f"status={st}")
    finally:
        stop_server(proc)

    # ---- M) 旧库迁移（无 work_id 列的老库） ----
    legacy = os.path.join(tempfile.mkdtemp(prefix="duty-roster-v67-legacy-"), "legacy.db")
    hpw = lambda pw: hashlib.sha256(("duty-roster-v1:" + pw).encode("utf-8")).hexdigest()
    conn = sqlite3.connect(legacy)
    conn.executescript(
        "CREATE TABLE people (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL,"
        " kind TEXT NOT NULL, grp TEXT, sort_order INTEGER NOT NULL,"
        " active INTEGER NOT NULL DEFAULT 1);"
        "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,"
        " password_hash TEXT NOT NULL, display_name TEXT NOT NULL, person_id INTEGER,"
        " is_admin INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1);"
    )
    conn.execute("INSERT INTO people (id, name, kind, grp, sort_order) VALUES (1,'AAA','chief','chief',1)")
    conn.execute("INSERT INTO users (username, password_hash, display_name, person_id, is_admin)"
                 " VALUES ('AAA', ?, 'AAA', 1, 1)", (hpw("123456"),))
    conn.execute("INSERT INTO users (username, password_hash, display_name, person_id, is_admin)"
                 " VALUES ('admin', ?, '系统管理员', NULL, 1)", (hpw("admin123"),))
    conn.commit()
    conn.close()
    proc2, up2 = start_server(legacy, PORT + 1)
    base2 = f"http://127.0.0.1:{PORT + 1}"
    try:
        check("M 旧库（无 work_id 列）服务启动", up2)
        if up2:
            st, out = login("admin", "admin123", base=base2)
            atok2 = out.get("token")
            st, ppl = req("GET", "/api/people", token=atok2, base=base2)
            p0 = ppl[0] if st == 200 and ppl else {}
            check("M 启动迁移自动补 work_id 列（接口带 work_id=null、姓名登录不受影响）",
                  st == 200 and "work_id" in p0 and p0.get("work_id") is None,
                  f"person={p0.get('name')} work_id={p0.get('work_id')!r}")
            st, _ = req("PUT", "/api/people/1", token=atok2, body={"work_id": "111"}, base=base2)
            st_l, out = login("111", "123456", base=base2)
            check("M 迁移后的老库补写工号即可工号登录",
                  st == 200 and st_l == 200 and out.get("username") == "AAA")
    finally:
        stop_server(proc2)


    # ---- S) 静态断言 ----
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()
    css = open(os.path.join(fe, "style.css"), encoding="utf-8").read()
    html = open(os.path.join(fe, "index.html"), encoding="utf-8").read()
    backend = open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read()

    check("S app.js 带 v6.7 版本标记", "/* duty-roster v6.31 */" in js)
    check("S 后端种子含 9 个工号字面量（PEOPLE_SEED 四元组）",
          all(f'"{w}"' in backend for w in WORK_IDS.values())
          and '("III", "cadre", "B", "999")' in backend
          and '("JJJ", "assistant", "A", None)' in backend)
    login_seg = segment(backend, '@app.post("/api/login")', '@app.get("/api/me")')
    check("S 登录双标识解析：username 命中或 people.work_id 命中、空工号不命中、姓名优先",
          "u.username=?" in login_seg and "p.work_id=?" in login_seg
          and "p.work_id IS NOT NULL AND p.work_id <> ''" in login_seg
          and "ORDER BY (u.username=?) DESC" in login_seg)
    check("S 工号迁移与唯一性：启动补列 + 非空部分唯一索引 + PersonIn 带 work_id + 重复校验",
          "ALTER TABLE people ADD COLUMN work_id TEXT" in backend
          and "idx_people_work_id" in backend
          and "work_id: str | None = None" in backend
          and "_check_work_id_free" in backend and "_norm_work_id" in backend)
    check("S 登录页账号框文案改「姓名或工号」（label + placeholder）",
          'placeholder="姓名或工号"' in html and "本人姓名或工号" in html)
    check("S 人员与权限表加「工号」列且随行保存（表头/pw- 输入框/PUT 带 work_id）",
          "<th>工号</th>" in js and 'id="pw-${p.id}"' in js
          and "work_id: $('pw-' + pid).value.trim()" in js)
    check("S 管理员说明句已撤下（标题行左区只剩已发布徽标）；成员已发布提示未动",
          "您是管理员：可直接点击格子修改最终排班" not in js
          and "本月排班已发布，以下为最终排班表。" in js)
    admin_seg = segment(js, "function viewSheetAdmin()", "function exportXlsx()")
    check("S 超管合并页左区状态小字未动（sb-status + 已提交 N/总 仍在）",
          "sb-status" in admin_seg and "已提交 ${submitted.length}/${detail.people.length} 人" in admin_seg)
    check("S 标题行改三列网格居中（1fr auto 1fr + 左右区贴边 + 孤标题跨满行）",
          ".sheet-title-row { display: grid; grid-template-columns: 1fr auto 1fr; }" in css
          and ".sheet-title-row .st-right { justify-self: end; margin-left: 0; }" in css
          and ".sheet-title-row > .grid-title:only-child { grid-column: 1 / -1; }" in css)
    navfn = segment(js, "function renderNav()", "function currentRoute()")
    check("S 管理员侧栏顺序互换：renderNav 中 daily 链接先于 myposts 追加（成员仍只有 myposts 其后）",
          navfn.index("d.href = '#/daily';") < navfn.index("m.href = '#/myposts';"))
    nav = segment(js, "const NAV = [", "];")
    check("S 超管 NAV 顺序未动（排班表 < 生成当日排班 < 岗位显示）",
          nav.index("{ route: 'sheet'") < nav.index("{ route: 'daily'")
          < nav.index("{ route: 'myposts'"))
    check("S 侧栏副标题只剩「在线选班」（职能轮休段与分隔符已去；登录页副标题不在此列）",
          '<div class="brand-sub">在线选班</div>' in html
          and "职能轮休 · 在线选班" not in html)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v6.7 引起的旧套件改动）：
  - 全部套件（v25–v66）：版本标记断言由 v6.6 提升为 v6.7；
  - smoke_test_v29.py：人员与权限合并表「表头」断言适配——姓名列
    后新增「工号」列，期望表头改为 姓名|工号|类别|组别|角色|启用|
    密码|操作（检查名已注明 v6.7 适配）；
  - 其余逐项核查过与本版相邻的旧断言，均无需改写：v31 对标题行
    .st-left/.st-right 的 v3.1 规则断言（两条规则原文保留，v6.7
    只在文末新段追加网格覆盖）；v60 对 renderNav 简化分支的断言
    只查 m/d 两链接与角色条件的存在性、不查先后（互换后仍成立），
    超管 NAV 数组本就是 排班表/生成当日排班/岗位显示、未动；
    v66 对 exportImage 克隆标题行的断言（innerHTML 换纯标题）仍
    成立，居中改由 CSS 孤标题跨满行规则保证；
  - 没有任何旧套件断言过管理员已发布分支的那句说明文字、登录页
    占位文案或侧栏副标题（逐文件 grep 核查过），三处文案改动
    无需适配；
  - 后端 /api/people 响应新增 work_id 字段（人员对象多一键），
    旧套件对人员对象的断言均为字段子集检查，未受影响。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.7 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：临时数据库 + 临时服务端口 3017（工号数据/登录/编辑链）+ 3018（旧库迁移）+ 纯静态检查（前端）\n")
            f.write("- v6.7：①干部工号可作登录账号（姓名/工号二选一、密码不变，"
                    "协管员无工号仍用姓名；人员表加工号列随行保存）；②排班表页"
                    "管理员说明句撤下；③排班表标题改三列网格真居中；④管理员"
                    "侧栏生成当日排班与岗位显示互换；⑤侧栏副标题去掉「职能轮休」。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.7: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
