# -*- coding: utf-8 -*-
"""示例科室排班系统 v2.5 冒烟测试（追加到 SMOKE_TEST.md 的 v2.5 章节）。

背景（用户实测反馈 5 点）与本版结论：
1. 【Issue 1 定性】CCC（role=admin）本人行能点出 12 天 > 自选上限 6。
   复现结论：后端无问题——PUT /cell 对非 super 一律硬拒绝（本文件固化：
   人员管理员本人行第 7 天 400、每日干部/科领导上限 400；super 改他人
   仍是警告放行）。12 天纯属前端本地未保存状态（draftEdits）无任何校验、
   且合计按本地状态计数所致。本版前端补本地预检（checkOwnPick/checkOtherPick），
   并把草稿口径的合计分母改为个人适用上限（非科长=S、科长=Q）。
2. 【Issue 2】CCC看不到改他人行入口：v2.4 代码的判定本身按查看者角色
   （adjustMode），故障来自浏览器 localStorage 里的旧角色快照（授权前登录的
   member）+ 静态资源无 Cache-Control 可能缓存旧 app.js。本版加 GET /api/me
   进应用时刷新角色快照，并给 / 与 /static/* 加 Cache-Control: no-cache，
   app.js 带版本标记 /* duty-roster v2.5 */。
3. 网格删除最左侧「类别」列（Excel 导出不变，仍与纸质表一致）。
4. 姓名单元格左内距（桌面 10px / 移动 6px）。
5. 删除网格下方全部图例/口径说明区块（符号弹层、提示行保留）。

【v2.6 适配（2026-10-31）】仅一处：app.js 版本标记断言由 v2.5 改为 v2.6
（v2.6 按惯例提升版本标记）。其余断言（checkOwnPick/checkOtherPick 本地预检、
adjustMode 他人行可编辑判定、/api/me、no-cache）v2.6 全部保留，未受影响。
【v2.7 适配（2026-10-31）】同上：仅版本标记断言 v2.6 → v2.7，其余不变。
【v2.8 适配（2026-10-31）】同上：仅版本标记断言 v2.7 → v2.8，其余不变。
【v2.9 适配（2026-10-31）】同上：仅版本标记断言 v2.8 → v2.9，其余不变。
【v4.7 适配（2026-11-01）】用户定规则变更：个人自选上限改为只统计轮休
（X），其他假期不占名额。本套件的版本标记断言提升为 v4.7；「本地上限
预检存在」断言的文案字面量随新口径更新（见该检查处注记）。其余 API
断言未动——第 7 天被拒测的是轮休 X（新口径下仍被拒、报错仍含
「自选上限 6」），每日上限断言与计数口径无关。
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
PORT = 3005
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


def req_headers(path):
    r = urllib.request.Request(BASE + path, method="GET")
    with urllib.request.urlopen(r, timeout=30) as resp:
        # 响应头键名大小写不敏感地归一化（服务端发的是小写 cache-control）
        return resp.status, {k.lower(): v for k, v in resp.headers.items()}


def login(name, pw):
    st, out = req("POST", "/api/login", body={"username": name, "password": pw})
    return (st, out.get("token"), out) if st == 200 else (st, None, out)


def segment(text, start_marker, end_marker):
    a = text.index(start_marker)
    b = text.index(end_marker, a)
    return text[a:b]


def main():
    tmpdb = os.path.join(tempfile.mkdtemp(prefix="duty-smoke-v25-"), "test.db")
    env = dict(os.environ, DUTY_DB=tmpdb)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--port", str(PORT)],
        cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        up = False
        for _ in range(60):
            try:
                st, _ = req("GET", "/api/health")
                if st == 200:
                    up = True
                    break
            except Exception:
                pass
            time.sleep(0.5)
        check("v2.5 服务启动", up)
        if not up:
            return 1

        st, atok, _ = login("admin", "admin123")
        st, users = req("GET", "/api/users", token=atok)
        lw_user = [u for u in users if u["username"] == "CCC"][0]
        req("PATCH", f"/api/users/{lw_user['id']}", token=atok, body={"is_admin": True})
        st, people = req("GET", "/api/people", token=atok)
        P = {p["name"]: p for p in people}

        def new_plan(month):
            st, plan = req("POST", "/api/plans", token=atok,
                           body={"year": 2026, "month": month, "quota": 9, "self_limit": 6})
            req("PATCH", f"/api/plans/{plan['id']}", token=atok, body={"phase_override": 3})
            return plan["id"]

        pid = new_plan(11)
        toks = {}
        for name in P:
            _, toks[name], _ = login(name, "123456")

        def pick(pid_, tok, name, day, symbol="X"):
            return req("PUT", f"/api/plans/{pid_}/cell", token=tok,
                       body={"person_id": P[name]["id"], "day": day, "symbol": symbol})

        # ---------- Issue 1：人员管理员本人行配额硬拒绝 ----------
        st, _, lwinfo = login("CCC", "123456")
        check("CCC登录 role=admin（人员管理员）", lwinfo.get("role") == "admin",
              f"role={lwinfo.get('role')}")
        codes = [pick(pid, toks["CCC"], "CCC", d)[0] for d in range(1, 7)]
        check("CCC本人行前 6 天可选（200x6）", codes == [200] * 6, f"codes={codes}")
        st, out = pick(pid, toks["CCC"], "CCC", 7)
        check("CCC本人行第 7 天被后端拒绝（400 自选上限）",
              st == 400 and "自选上限 6" in str(out.get("detail")),
              f"status={st}, detail={out.get('detail')}")
        st, detail = req("GET", f"/api/plans/{pid}", token=toks["CCC"])
        lw = [p for p in detail["people"] if p["name"] == "CCC"][0]
        check("拒绝后服务端草稿恰为 6 天（12 天纯属前端未保存状态）",
              lw["draft_leave"] == 6, f"draft_leave={lw['draft_leave']}")

        # ---------- Issue 1：每日上限对人员管理员同样硬拒绝（第二计划） ----------
        pid2 = new_plan(12)
        for name in ("AAA", "BBB", "DDD", "EEE"):
            pick(pid2, toks[name], name, 10)
        st, out = pick(pid2, toks["CCC"], "CCC", 10)
        check("每日干部上限：CCC在满员日选休被拒（400）",
              st == 400 and "干部休假已满" in str(out.get("detail")),
              f"status={st}, detail={out.get('detail')}")
        for name in ("AAA", "BBB", "DDD"):
            pick(pid2, toks[name], name, 12)
        st, out = pick(pid2, toks["CCC"], "CCC", 12)
        check("每日科领导上限：CCC在领导满员日选休被拒（400）",
              st == 400 and "科领导休假已满" in str(out.get("detail")),
              f"status={st}, detail={out.get('detail')}")

        # ---------- super 改他人草稿：警告放行（口径不变） ----------
        codes = []
        last = {}
        for d in range(1, 8):
            st, last = pick(pid, atok, "FFF", d)
            codes.append(st)
        st, detail = req("GET", f"/api/plans/{pid}", token=atok)
        lx = [p for p in detail["people"] if p["name"] == "FFF"][0]
        check("super 代改成员草稿超上限仍保存（200x7、带警告、实存 7 天）",
              codes == [200] * 7 and bool(last.get("warnings")) and lx["draft_leave"] == 7,
              f"codes={codes}, warnings={last.get('warnings')}, draft={lx['draft_leave']}")

        # ---------- Issue 2：/api/me 刷新角色 ----------
        st, me_lw = req("GET", "/api/me", token=toks["CCC"])
        check("GET /api/me 返回最新角色（CCC=admin）",
              st == 200 and me_lw.get("role") == "admin" and me_lw.get("is_admin") is True,
              f"status={st}, role={me_lw.get('role')}")
        st, me_lx = req("GET", "/api/me", token=toks["FFF"])
        check("GET /api/me 普通成员 role=member", st == 200 and me_lx.get("role") == "member")
        r = urllib.request.Request(BASE + "/api/me", method="GET")
        try:
            urllib.request.urlopen(r, timeout=10)
            st_no = 200
        except urllib.error.HTTPError as e:
            st_no = e.code
        check("GET /api/me 未登录 401", st_no == 401, f"status={st_no}")

        # ---------- Issue 2：缓存头 ----------
        st, h = req_headers("/")
        check("GET / 返回 Cache-Control: no-cache",
              st == 200 and "no-cache" in (h.get("cache-control") or ""),
              f"Cache-Control={h.get('Cache-Control')}")
        st, h = req_headers("/static/app.js")
        check("GET /static/app.js 返回 Cache-Control: no-cache",
              st == 200 and "no-cache" in (h.get("cache-control") or ""),
              f"Cache-Control={h.get('Cache-Control')}")
        st, h = req_headers("/static/style.css")
        check("GET /static/style.css 返回 Cache-Control: no-cache",
              st == 200 and "no-cache" in (h.get("cache-control") or ""))

        # ---------- 静态检查：前端结构 ----------
        js = open(os.path.join(ROOT, "frontend", "app.js"), encoding="utf-8").read()
        css = open(os.path.join(ROOT, "frontend", "style.css"), encoding="utf-8").read()
        grid_seg = segment(js, "function gridHTML", "function bindGridCells")
        member_seg = segment(js, "function viewMemberSheet", "function bindMemberSheet")
        bind_member_seg = segment(js, "function bindMemberSheet", "function viewSheetAdmin")
        bind_pick_seg = segment(js, "function bindPick", "/* ---------------- 视图：排班表")

        check("app.js 带当前版本标记（v4.7，标记随版本提升）", "/* duty-roster v6.31 */" in js)
        check("网格已删除「类别」列（无 th.cat/td.cat 标记、无 rowspan 合并格）",
              '<th class="cat">' not in js and 'td class="cat"' not in js
              and "rowspan" not in grid_seg and '<th class="name">姓名</th>' in grid_seg)
        check("统计行标签改为 stats-label（不再 colspan 跨类别列）",
              'class="stats-label"' in grid_seg and 'colspan="2"' not in grid_seg
              and ".stats-label" in css)
        check("姓名列 sticky 偏移归 0 且左内距 10px（移动 6px）",
              "left: 52px" not in css and "padding-left: 10px" in css
              and "td.name { padding-left: 6px; }" in css)
        # v4.5 适配（用户改主意）：符号图例以「排班表卡片内页脚」形式恢复
        # （.sheet-legend，由 sheetLegendHTML 用 SYMBOLS 生成），与本检查在
        # v2.5 删除的网格下方独立图例区块是不同元素；旧区块仍应保持删除，
        # 故原断言字面量不变，仅更新检查名——新页脚的正向断言见 v4.5 套件。
        check("v2.5 删除的旧图例区块仍不存在（legendHTML/legend 标记/stats-note；v4.5 卡片页脚 .sheet-legend 为新元素、不在此列）",
              "legendHTML" not in js and 'class="legend"' not in js
              and "图例：空白" not in js and "stats-note" not in js)
        check("他人行可编辑判定引用查看者角色（adjustMode <- myRole()==='admin'）",
              "const isAdminRole = myRole() === 'admin'" in js
              and "adjustMode: isAdminRole" in member_seg and "opts.adjustMode" in grid_seg)
        check("进应用时用 /api/me 刷新角色快照", "/api/me" in js and "localStorage.setItem('dr_me'" in js)
        # v4.7 适配：本地预检口径改为只拦截轮休（X），toast 文案改为
        # 「轮休已勾满…其他假期仍可勾选」，原字面量「已达到自选上限/
        # 剩余天数由管理员一键补满」随之更新（新口径行为由 v4.7 套件覆盖）。
        check("本地上限预检存在（checkOwnPick/checkOtherPick + 上限文案，两处绑定均调用；v4.7 文案）",
              "function checkOwnPick" in js and "function checkOtherPick" in js
              and "轮休已勾满" in js and "其他假期仍可勾选" in js
              and "checkOwnPick" in bind_member_seg and "checkOwnPick" in bind_pick_seg
              and "checkOtherPick" in bind_member_seg)
        check("合计分母口径：草稿视图用个人上限（denomMode='limit' -> select_limit）",
              "opts.denomMode === 'limit' ? person.select_limit : p.quota" in js
              and "denomMode: 'limit'" in js)

        return 0 if all(r[1] for r in results) else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v2.5 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write(f"- 环境：独立临时数据库（端口 {PORT}），计划 2026-11 / 2026-12，Q=9，S=6\n")
            f.write("- Issue 1 定性：后端硬拒绝成立（人员管理员本人行第 7 天/满员日均 400），"
                    "线上 12 天为前端未保存本地状态无校验所致；本版补前端本地预检。\n")
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv2.5: {passed}/{len(results)} passed -> appended to {REPORT}")


if __name__ == "__main__":
    sys.exit(main())
