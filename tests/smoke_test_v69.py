# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.9 冒烟测试（追加到 SMOKE_TEST.md 的 v6.9 章节）。

v6.9 变更（2026-11-01 用户追加需求）：
  普通成员与协管员新增「当日排班」只读页——看全科整张当日排班表
  （班次徽标 + 带班 + A–E 真名时段预览表 + 晚班退税岗），信息与管理
  员「生成当日排班」页的时段预览一致。后端新增
  GET /api/daily/dayview?date=：任何登录账号可查，只反映**已保存**
  的排班（未保存 → status=none，绝不返回默认排班冒充正式结果；
  当月无计划 → status=noplan），复用 resolve_daily_slots 解析预览，
  与管理员预览同源同口径。前端：成员侧栏在「排班表」与「岗位显示」
  之间加「当日排班」（route=dayview），管理员/超管导航不变；页面
  纯只读（无选人/保存/图片按钮），日期控件与岗位显示同款（默认今天；v6.15 起三页统一，v6.9 当时为默认明天）。

测试口径（临时库 + 临时端口 3020）：
  D) 端到端：建 11 月计划发布（FFF 5 日轮休）；保存 11-02（早班）、
     11-03（晚班，含退税协管员）、11-05（FFF当天休假日）三份当日
     排班；成员HHH与协管员JJJ调 dayview → 200、status=ok、
     带班与五岗真名与保存值逐字一致、preview 行数与模板映射对齐
     （早班 10 行、首行审图=B+C 等；晚班 8 行、tax_names 含两名
     协管员）；FFF在自己休假日查 11-05 → 仍 200 ok（查看不设岗
     位限制）；未保存日 11-04 → none；无计划月 2027-01 → noplan；
     未登录 → 401；管理员 context 接口原样可用、成员调 context
     仍 403（编辑口未放开）。
  S) 静态断言：版本标记；成员导航含 dayview 且位置在岗位显示前、
     超管 NAV 数组无 dayview、管理员路由白名单不变、成员白名单
     含 dayview；新视图渲染函数无 select/保存/图片控件；空态文案
     「当日排班尚未生成」在位；.daily-scroll 样式在位。
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 3020
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


def save_default_assignment(atok, datestr):
    """按管理员页口径：取 context 的默认排班原样保存，返回 (ctx, 保存状态)。"""
    st, ctx = req("GET", f"/api/daily/context?date={datestr}", token=atok)
    if st != 200:
        return None, st
    dft = ctx["default"]
    st, _ = req("POST", "/api/daily/assignments", token=atok,
                body={"date": datestr, "leader_id": dft["leader_id"],
                      "letters": dft["letters"]})
    return ctx, st


def post_people(slot, post_name):
    return [pp["name"] for post in slot["posts"] if post["name"] == post_name
            for pp in post["people"]]


def main():
    tmpdir = tempfile.mkdtemp(prefix="duty-roster-v69-")
    tmpdb = os.path.join(tmpdir, "test.db")
    proc, up = start_server(tmpdb, PORT)
    try:
        check("v6.9 服务启动", up)
        if not up:
            return 1
        atok = login("admin", "admin123")
        st, people = req("GET", "/api/people", token=atok)
        pid_of = {p["name"]: p["id"] for p in people} if st == 200 else {}
        name_of = {p["id"]: p["name"] for p in people} if st == 200 else {}

        # ---- 数据准备：11 月计划发布（FFF 5 日轮休，与 v6.8 同夹具） ----
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

        # ---- 保存三份当日排班：11-02 早班 / 11-03 晚班 / 11-05（FFF休假日） ----
        ctx02, st02 = save_default_assignment(atok, "2026-11-02")
        ctx03, st03 = save_default_assignment(atok, "2026-11-03")
        ctx05, st05 = save_default_assignment(atok, "2026-11-05")
        check("D 保存 11-02（早班）/11-03（晚班）/11-05 当日排班成功",
              st02 == 200 and st03 == 200 and st05 == 200,
              f"st={st02}/{st03}/{st05}")
        d02, d03 = ctx02["default"], ctx03["default"]
        exp_letters02 = {L: name_of[pid] for L, pid in d02["letters"].items()}

        mtok = login("HHH", "123456")
        gtok = login("JJJ", "123456")

        # ---- D) 成员查早班整表 ----
        st, dv = req("GET", "/api/daily/dayview?date=2026-11-02", token=mtok)
        check("D 成员调 dayview 11-02 → 200 且 status=ok、班次为早班",
              st == 200 and dv.get("status") == "ok" and dv.get("shift") == "morning"
              and dv.get("shift_label") == "早班",
              f"status={st}/{dv.get('status')}")
        check("D 带班与 A–F 六岗真名与保存值逐字一致（v6.16 适配：该日默认已保存为 6 人方案）",
              dv.get("leader_name") == name_of[d02["leader_id"]]
              and dv.get("letters") == exp_letters02,
              f"leader={dv.get('leader_name')} letters={dv.get('letters')}")
        pv = dv.get("preview") or []
        row0 = pv[0] if pv else {"posts": []}
        check("D 早班 preview 共 8 行且模板映射对齐（v6.27 适配：新模板首班次 审图=A+B、申报=F、挑查岗=D、备勤=C+E）",
              len(pv) == 8
              and sorted(post_people(row0, "审图查验岗")) == sorted([exp_letters02["A"], exp_letters02["B"]])
              and post_people(row0, "申报岗") == [exp_letters02["F"]]
              and post_people(row0, "挑查岗") == [exp_letters02["D"]]
              and sorted(post_people(row0, "备勤")) == sorted([exp_letters02["C"], exp_letters02["E"]]),
              f"rows={len(pv)}")
        check("D 早班 tax_names 带两名协管员（v6.31 适配：退税岗所有班次都带）", dv.get("tax_names") == ["JJJ", "KKK"])

        # ---- D) 协管员查晚班整表（含退税岗） ----
        st, dv3 = req("GET", "/api/daily/dayview?date=2026-11-03", token=gtok)
        pv3 = dv3.get("preview") or []
        row3 = pv3[0] if pv3 else {"posts": []}
        exp_letters03 = {L: name_of[pid] for L, pid in d03["letters"].items()}
        check("D 协管员调 dayview 11-03 → 200、status=ok、晚班、带班与五岗真名一致",
              st == 200 and dv3.get("status") == "ok" and dv3.get("shift") == "evening"
              and dv3.get("leader_name") == name_of[d03["leader_id"]]
              and dv3.get("letters") == exp_letters03,
              f"status={st}/{dv3.get('status')}")
        check("D 晚班 preview 共 8 行且首行审图=A+B、申报为 E（v6.20 适配：11-03 在岗 ≥6 人、保存的是晚班 6 人方案默认排班，首段申报为固定申报岗 E，不再 C/D 两段）",
              len(pv3) == 8
              and sorted(post_people(row3, "审图查验岗")) == sorted([exp_letters03["A"], exp_letters03["B"]])
              and post_people(row3, "申报岗") == [exp_letters03["E"]],
              f"rows={len(pv3)}")
        check("D 晚班 tax_names 含当天在岗的两名协管员",
              sorted(dv3.get("tax_names") or []) == ["KKK", "JJJ"],
              f"tax={dv3.get('tax_names')}")

        # ---- D) 查看者当天休假也照常可看 ----
        xtok = login("FFF", "123456")
        st, dv5 = req("GET", "/api/daily/dayview?date=2026-11-05", token=xtok)
        check("D FFF在本人休假日（11-05）查 dayview → 仍 200 且 status=ok",
              st == 200 and dv5.get("status") == "ok", f"status={st}/{dv5.get('status')}")

        # ---- D) 空态与鉴权 ----
        st, dv4 = req("GET", "/api/daily/dayview?date=2026-11-04", token=mtok)
        check("D 未保存日期 11-04 → status=none（不冒充默认排班、无 preview/letters）",
              st == 200 and dv4.get("status") == "none"
              and "preview" not in dv4 and "letters" not in dv4,
              f"status={st}/{dv4.get('status')}")
        st, dvnp = req("GET", "/api/daily/dayview?date=2027-01-15", token=mtok)
        check("D 无计划月份 2027-01 → status=noplan",
              st == 200 and dvnp.get("status") == "noplan",
              f"status={st}/{dvnp.get('status')}")
        st, _ = req("GET", "/api/daily/dayview?date=2026-11-02")
        check("D 未登录调 dayview → 401", st == 401, f"status={st}")
        st, dvadm = req("GET", "/api/daily/dayview?date=2026-11-02", token=atok)
        check("D 超管调 dayview 亦可（同一只读口径）",
              st == 200 and dvadm.get("status") == "ok", f"status={st}")

        # ---- D) 管理员编辑口未受影响 ----
        st, ctx = req("GET", "/api/daily/context?date=2026-11-02", token=atok)
        check("D 管理员 context 接口行为不变（saved/default/template 齐备；v6.26 适配：该日已保存 6 人排班、模板 8 段）",
              st == 200 and bool(ctx.get("saved")) and bool(ctx.get("default"))
              and len(ctx.get("template") or []) == 8, f"status={st}")
        st, _ = req("GET", "/api/daily/context?date=2026-11-02", token=mtok)
        check("D 成员调 context（编辑口）仍 403", st == 403, f"status={st}")
    finally:
        stop_server(proc)

    # ---- S) 静态断言 ----
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()
    css = open(os.path.join(fe, "style.css"), encoding="utf-8").read()

    check("S app.js 带 v6.9 版本标记", "/* duty-roster v6.31 */" in js)
    nav_seg = segment(js, "function renderNav()", "function currentRoute()")
    check("S 成员导航含「当日排班」且仅 member 角色添加（myRole() === 'member' 守卫）",
          "v.href = '#/dayview';" in nav_seg and "当日排班" in nav_seg
          and "if (myRole() === 'member')" in nav_seg)
    check("S 导航顺序：当日排班位于 排班表 之后、岗位显示 之前",
          nav_seg.index("<span>当日排班</span>") > nav_seg.index("<span>排班表</span>")
          and nav_seg.index("<span>当日排班</span>") < nav_seg.index("<span>岗位显示</span>"))
    nav_const = segment(js, "const NAV = [", "];")
    check("S 超管 NAV 数组不变（无 dayview 路由项，仍为 生成排班/岗位显示；v6.16 适配：daily 标签改名「生成排班」）",
          "dayview" not in nav_const and "label: '生成排班'" in nav_const
          and "岗位显示" in nav_const)
    check("S 路由白名单：成员含 dayview、管理员白名单原样不变",
          "['sheet', 'password', 'myposts', 'dayview']" in js
          and "['sheet', 'password', 'myposts', 'daily']" in js
          and "dayview: { render: viewDayView, bind: bindDayView }" in js)
    dv_seg = segment(js, "function viewDayView()", "/* ---------------- 路由")
    check("S 当日排班视图无编辑控件（无 select/保存接口/person_id；v6.10 适配：已加生成图片、门控断言见 v6.10 套件）",
          "<select" not in dv_seg and "/api/daily/assignments" not in dv_seg
          and "person_id" not in dv_seg
          and "/api/daily/dayview?date=" in dv_seg)
    check("S 空态文案与控件在位（当日排班尚未生成 / 尚未生成不带报错样式、日期控件同岗位显示；v6.15 适配：默认日期改今天）",
          "当日排班尚未生成" in dv_seg and 'id="dvDate"' in dv_seg
          and 'id="dvPrev"' in dv_seg and 'id="dvNext"' in dv_seg
          and "dayviewDate = todayStr()" in dv_seg)
    check("S 退税行与带班行在位（退税岗：…或无、带班：姓名；v6.31 适配：退税行不再按班次门控，dv 段已无 evening 门控）",
          "退税岗：" in dv_seg and "带班：" in dv_seg
          and "out.shift === 'evening'" not in dv_seg)
    check("S .daily-scroll 横向滚动样式在位（窄屏整表可横滚）",
          ".daily-scroll { overflow-x: auto;" in css)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v6.9 引起的旧套件改动）：
  - 全部旧套件：版本标记断言由 v6.8 提升为 v6.9（仅标记字面量）；
  - 其余旧套件逐项核查：成员/管理员侧栏断言（v60/v64/v67 等）钉的
    是各自角色的条目与顺序——v6.9 只在 member 分支、排班表之后新
    插入 dayview 一项，未动 admin 分支与超管 NAV 数组，断言原样
    成立；
  - smoke_test_v60.py「路由 guard」断言适配（回归实测唯一命中）：
    成员白名单字面量由 ['sheet', 'password', 'myposts'] 更新为
    ['sheet', 'password', 'myposts', 'dayview']，检查名已注明
    v6.9 适配；管理员白名单与超管重定向断言未动；
  - 后端为纯新增端点 /api/daily/dayview：context/mine/save 三个
    既有当日排班接口零改动，v60–v68 的当日排班断言不受影响。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.9 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：临时数据库 + 临时服务端口 3020（API 端到端）+ 纯静态检查（前端）\n")
            f.write("- v6.9：普通成员/协管员新增「当日排班」只读页：后端新端点 "
                    "/api/daily/dayview 只返回已保存排班（未保存 none、无计划 noplan），"
                    "前端成员侧栏加「当日排班」（排班表与岗位显示之间），整表与管理员预览同源。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.9: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
