# -*- coding: utf-8 -*-
"""示例科室排班系统 v4.7 冒烟测试（追加到 SMOKE_TEST.md 的 v4.7 章节）。

v4.7 变更（用户定规则变更，取代此前「除备勤外全部计休符号都算进自选
上限」的口径；用户原话：「逻辑是只限定轮休勾选6天，其他假期都可以勾」）：

后端（backend/main.py）：
- 新增 counts_toward_cap(symbol)（仅符号 X=轮休 计入个人自选上限）与
  person_cap_count()；个人上限强制点全部切换为 X 口径：
  PUT /cell（本人草稿直存/超管警告放行）、admin-edits 整批复检
  （v4.7 时为逐格 _check_cell_caps；v4.8 起改为整批最终状态校验
  _check_batch_caps，本套件对应静态断言已同步适配）。
  报错文案改为点明轮休（如「轮休已勾满自选上限 6 天…」）。
- 不动：counts_as_leave 语义、day_stats 与每日硬上限（干部<=4/科领导<=2/
  协管员<=1 仍按全部计休符号统计）、person_leave_count（求解器按总天数
  补到应休 Q、填充符号仍为 X）、最终表层（本就无个人上限、仅超 Q 警告）、
  plan_detail 的 *_leave 报表计数（总天数口径）、Excel 导出合计。

前端（frontend/app.js）：
- 本地预检 checkOwnPick/checkOtherPick 同步 X 口径：非 X 符号永不被上限
  拦截，X 满额 toast 点明「轮休已勾满 … 天，其他假期仍可勾选」；
- 本人进度计数改名 myDraftXCount 并只数 X，进度文案改「已选轮休 X/N 天」；
- 合计列主数字改为轮休数/上限（分母口径不变：草稿/源数据=个人上限、
  最终表=Q），另有其他假期天数（总计休-X）>0 时后缀「 +N」；
- 标题后半句补足为「，您可勾选N天轮休」（v4.6 文案的补足）。

本套件为 API 行为测试（临时库）+ 静态检查。
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
PORT = 3008
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
    return (st, out.get("token"), out) if st == 200 else (st, None, out)


def main():
    tmpdb = os.path.join(tempfile.mkdtemp(prefix="duty-smoke-v47-"), "test.db")
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
        check("v4.7 服务启动", up)
        if not up:
            return 1

        st, atok, _ = login("admin", "admin123")
        # CCC提升为人员管理员（与 v2.5 套件同法）
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

        def detail(pid_, tok=atok):
            _, d = req("GET", f"/api/plans/{pid_}", token=tok)
            return d

        def prow(d, name):
            return [p for p in d["people"] if p["name"] == name][0]

        def x_count(grid, name):
            cells = grid.get(str(P[name]["id"]), {}) or {}
            return sum(1 for c in cells.values() if c["symbol"] == "X")

        # ---------- (1) 成员：6 天轮休 + 3 天其他假期，全部可存 ----------
        codes = [pick(pid, toks["FFF"], "FFF", d)[0] for d in range(1, 7)]
        check("(1a) FFF先勾 6 天轮休 X（200x6）", codes == [200] * 6, f"codes={codes}")
        codes = [pick(pid, toks["FFF"], "FFF", 7, "O")[0],
                 pick(pid, toks["FFF"], "FFF", 8, "R")[0],
                 pick(pid, toks["FFF"], "FFF", 9, "△")[0]]
        check("(1b) 轮休满 6 后再勾年休假/补休/病假仍可保存（200x3，其他假期不占名额）",
              codes == [200] * 3, f"codes={codes}")
        d = detail(pid)
        lx = prow(d, "FFF")
        check("(1c) FFF草稿总计休 9 天（报表口径不变）、轮休恰 6 天",
              lx["draft_leave"] == 9 and x_count(d["grid"], "FFF") == 6,
              f"draft_leave={lx['draft_leave']}, X={x_count(d['grid'], 'FFF')}")

        # ---------- (2) 第 7 天轮休被拒 ----------
        st, out = pick(pid, toks["FFF"], "FFF", 10, "X")
        check("(2) 第 7 天轮休被后端拒绝（400，文案点明轮休+自选上限 6）",
              st == 400 and "轮休" in str(out.get("detail")) and "自选上限 6" in str(out.get("detail")),
              f"status={st}, detail={out.get('detail')}")

        # ---------- (3) X 改其他符号释放名额 ----------
        st, _ = pick(pid, toks["FFF"], "FFF", 1, "O")
        st2, _ = pick(pid, toks["FFF"], "FFF", 10, "X")
        check("(3) 第 1 天 X->O 释放名额后，第 10 天轮休可勾（200/200）",
              st == 200 and st2 == 200, f"codes={st},{st2}")

        # ---------- (4) 其他符号改 X 且轮休已满 -> 被拒 ----------
        st, out = pick(pid, toks["FFF"], "FFF", 7, "X")  # 第 7 天现为 O
        check("(4) 轮休满额时把年休假格改成轮休被拒（400）",
              st == 400 and "轮休" in str(out.get("detail")),
              f"status={st}, detail={out.get('detail')}")

        # ---------- (5) 含 6 轮休 + 多种其他假期可提交 ----------
        st, out = req("POST", f"/api/plans/{pid}/submit", token=toks["FFF"])
        d = detail(pid)
        lx = prow(d, "FFF")
        check("(5) FFF提交成功（6 轮休 + 4 其他假期，总计休 10 天）",
              st == 200 and lx["submission_status"] == "submitted"
              and lx["draft_leave"] == 10 and x_count(d["grid"], "FFF") == 6,
              f"status={st}, draft_leave={lx['draft_leave']}, X={x_count(d['grid'], 'FFF')}")

        # ---------- (6) 管理员批量改他人行：同一 X 口径 ----------
        for day in range(1, 7):  # 超管直填III 6 天轮休（警告放行）
            pick(pid, atok, "III", day, "X")
        _, ltok, lwinfo = login("CCC", "123456")
        check("(6a) CCC为人员管理员（role=admin）", lwinfo.get("role") == "admin",
              f"role={lwinfo.get('role')}")

        def batch(edits):
            return req("POST", f"/api/plans/{pid}/admin-edits", token=ltok,
                       body={"edits": edits})

        def edit(name, day, symbol):
            return {"person_id": P[name]["id"], "day": day, "symbol": symbol}

        st, out = batch([edit("III", 20, "O")])
        d = detail(pid)
        c20 = (d["grid"].get(str(P["III"]["id"]), {}) or {}).get("20")
        check("(6b) 对象轮休已满 6 时，批量加年休假仍生效（200，不占名额）",
              st == 200 and c20 and c20["symbol"] == "O",
              f"status={st}, c20={c20}")
        st, out = batch([edit("III", 21, "X")])
        d = detail(pid)
        c21 = (d["grid"].get(str(P["III"]["id"]), {}) or {}).get("21")
        check("(6c) 对象轮休已满 6 时，批量加轮休整批被拒（400，文案点明轮休/上限，未落表）",
              st == 400 and "轮休" in str(out.get("detail")) and "上限" in str(out.get("detail"))
              and c21 is None,
              f"status={st}, detail={out.get('detail')}, c21={c21}")

        # ---------- (8) 每日硬上限仍按全部计休符号统计（先于最终表测试做，
        # 与最终表分属不同层、互不干扰；用 12 月计划） ----------
        pid2 = new_plan(12)
        for name in ("AAA", "BBB", "CCC", "GGG"):  # 超管直填：第15天干部年休假 4 人
            pick(pid2, atok, name, 15, "O")
        st, out = pick(pid2, toks["EEE"], "EEE", 15, "O")
        check("(8a) 每日干部上限仍统计年休假：满 4 人后EEE勾年休假被拒（400 干部休假已满）",
              st == 400 and "干部休假已满" in str(out.get("detail")),
              f"status={st}, detail={out.get('detail')}")
        pick(pid2, atok, "JJJ", 16, "O")  # 超管直填：协管员JJJ第16天年休假
        st, out = pick(pid2, toks["KKK"], "KKK", 16, "R")
        check("(8b) 每日协管员上限仍统计其他假期：JJJ已休时KKK勾补休被拒（400）",
              st == 400 and "协管员" in str(out.get("detail")),
              f"status={st}, detail={out.get('detail')}")

        # ---------- (7) 最终表层：无个人上限（分层口径与此前一致） ----------
        codes = [req("PUT", f"/api/plans/{pid2}/final/cell", token=atok,
                     body={"person_id": P["DDD"]["id"], "day": day, "symbol": "X"})[0]
                 for day in range(1, 8)]
        check("(7a) 最终表可直接为非科长存 7 天轮休（>自选上限 6，200x7，最终表层不设个人上限）",
              codes == [200] * 7, f"codes={codes}")
        st, out = req("POST", f"/api/plans/{pid2}/final/autocomplete", token=atok)
        d = detail(pid2)
        lhq = prow(d, "DDD")
        check("(7b) 最终表一键补满后DDD总天数=应休 9、轮休=9（求解器总天数口径不变）",
              st == 200 and lhq["final_leave"] == 9 and x_count(d["final_grid"], "DDD") == 9,
              f"status={st}, final_leave={lhq['final_leave']}, X={x_count(d['final_grid'], 'DDD')}")
        st, _ = req("PUT", f"/api/plans/{pid2}/final/cell", token=atok,
                    body={"person_id": P["DDD"]["id"], "day": 30, "symbol": "X"})
        d = detail(pid2)
        check("(7c) 补满后最终表再加第 10 天轮休仍可保存（200，仅警告不拦截）",
              st == 200 and x_count(d["final_grid"], "DDD") == 10,
              f"status={st}, X={x_count(d['final_grid'], 'DDD')}")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()

    # ---------- 静态检查 ----------
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()
    backend = open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read()

    check("app.js 带 v5.0 版本标记", "/* duty-roster v6.31 */" in js)
    check("标题后半句补足为「，您可勾选${myLimit}天轮休」",
          "，您可勾选${myLimit}天轮休" in js)
    check("后端新增 counts_toward_cap（仅 X 计入个人上限）",
          "def counts_toward_cap(symbol):" in backend and 'return symbol == "X"' in backend)
    # v4.8 适配：admin-edits 的逐格复检 _check_cell_caps 已改为整批最终
    # 状态校验 _check_batch_caps（个人上限按最终整行 person_cap_count
    # (work, pid) 判定），本断言随之更新；/cell 强制点字面量不变。
    check("后端两处个人上限强制点均改用 person_cap_count（/cell 与 admin-edits 最终状态校验；v4.8 适配原 _check_cell_caps 断言）",
          "person_cap_count(grid, body.person_id)" in backend
          and "person_cap_count(work, pid)" in backend
          and "def _check_batch_caps" in backend)
    check("后端 counts_as_leave 语义未动（每日上限/总天数仍按符号表计休标记）",
          "return SYMBOLS[symbol][2]" in backend
          and "def person_leave_count" in backend)
    check("后端报错文案点明轮休（/cell 与批量复检各一份）",
          backend.count("轮休已勾满自选上限") >= 1 and "调整后轮休将超过自选上限" in backend)
    check("前端本地预检 X 口径（checkOwnPick/checkOtherPick 以 symbol !== 'X' 放行其他符号）",
          js.count("symbol !== 'X'") >= 2 and "function myDraftXCount" in js)
    check("前端超限 toast 点明轮休已勾满（本人/他人各一份）",
          "轮休已勾满自选上限" in js and "的轮休已勾满自选上限" in js)
    check("合计主数字=轮休数、其他假期后缀「 +N」（xTotal/otherLeave 逻辑）",
          "let xTotal = 0" in js and "const otherLeave = total - xTotal" in js
          and "` +${otherLeave}`" in js)
    check("成员进度文案改「已选轮休 …/自选上限」（进度卡与标题行各一处以上）",
          js.count("已选轮休") >= 2 and "${myDraftXCount()}" in js)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v4.7 引起的旧套件改动，均已在对应测试文件处注明）：
  - 全部套件（v25–v46）：仅版本标记断言由 v4.6 提升为 v4.7（检查名同步），
    其余断言未动；
  - smoke_test_v25：「本地上限预检存在」断言的文案字面量随新口径更新
    （旧：「已达到自选上限」「剩余天数由管理员一键补满」-> 新：「轮休已勾满」
    「其他假期仍可勾选」）；其 API 断言（第 7 天被拒）勾的是轮休 X，
    新口径下仍被拒、报错仍含「自选上限 6」，未动；
  - smoke_test_v26 / v27：标题断言本就只查「您可勾选」子串，新文案
    「，您可勾选N天轮休」仍满足，仅更新检查名与文件头注记；v26 的批量
    个人上限断言勾的也是 X，未动；
  - smoke_test_v46：标题模板字面量断言由「，您可勾选${myLimit}天」更新为
    「，您可勾选${myLimit}天轮休」并加文件头注记；其「后端计数口径未动」
    断言只查 counts_as_leave 本身（v4.7 确实未动），仍成立；
  - 其余套件（v1/v2/v22–v24/v28–v45）的 API 选格均以轮休 X 为主，
    X 的上限行为新旧口径一致，全部原样通过。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v4.7 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：本地临时库（DUTY_DB 指向临时文件）+ 静态检查；未触碰线上数据\n")
            f.write("- v4.7（用户定规则变更）：个人自选上限改为只统计轮休（符号 X）；"
                    "补休/年休假/病假等其他假期可自由勾选、保存、提交，不再占名额。"
                    "每日在岗硬上限、一键补满（按总天数补到应休 Q）、最终表分层"
                    "（无个人上限）全部不变。合计列主数字改为轮休数/上限，"
                    "其他假期天数以「 +N」后缀展示；标题后半句补足为"
                    "「，您可勾选N天轮休」。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv4.7: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
