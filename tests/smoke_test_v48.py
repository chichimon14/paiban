# -*- coding: utf-8 -*-
"""示例科室排班系统 v4.8 冒烟测试（追加到 SMOKE_TEST.md 的 v4.8 章节）。

v4.8 变更（用户实测三图反馈，均在成员/人员管理员合并排班表页）：
- 图1：勾选后（未保存）底部三行在岗统计不刷新——统计只按服务端已保存
  网格算。前端对策：新增 effectiveGridMap()/localDayStats()，按本地
  有效网格（草稿叠加 draftEdits/adminEdits）即时统计，成员合并页与旧
  「我的选班」页改用之；满员变灰随之按有效网格走。超管页仍用服务端
  统计（无本地暂存层），不在本版范围。
- 图2：每日人数上限要等点「保存」才整批报错。前端对策：新增
  checkDailyCaps() 点选时预检（干部<=4/科领导<=2/协管员<=1，按全部
  计休符号、delta 口径），checkOwnPick/checkOtherPick 均先过此预检，
  超限立即 toast「N日…休假已满…，不能再勾」且不记暂存。
- 图3（BUG）：管理员整批保存被误报「N日干部休假已满4人」——最终状态
  并不超限。根因：admin-edits 边套用边逐格复检（_check_cell_caps），
  同日在上限时批次内「先加后减」会按中间状态误判，保存成败取决于
  点选顺序。后端对策：整批先全部套用到工作网格，再由 _check_batch_caps
  对最终状态统一校验（个人轮休上限按最终整行、每日上限按最终全员
  计数）；PUT /cell 与 PUT /final/cell 的单格校验经审计无此问题
  （单格对当前网格校验、cur_counts 已扣被替换格，互换符号计数正确），
  未改动。

本套件：后端 API 行为回归（临时库，重点复现图3 的两种顺序）+ 静态检查。
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
PORT = 3009
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
    tmpdb = os.path.join(tempfile.mkdtemp(prefix="duty-smoke-v48-"), "test.db")
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
        check("v4.8 服务启动", up)
        if not up:
            return 1

        st, atok, _ = login("admin", "admin123")
        # CCC、BBB提升为人员管理员（批量改他人行的两个操作者）
        st, users = req("GET", "/api/users", token=atok)
        for uname in ("CCC", "BBB"):
            uid = [u for u in users if u["username"] == uname][0]["id"]
            req("PATCH", f"/api/users/{uid}", token=atok, body={"is_admin": True})
        st, people = req("GET", "/api/people", token=atok)
        P = {p["name"]: p for p in people}

        st, plan = req("POST", "/api/plans", token=atok,
                       body={"year": 2026, "month": 11, "quota": 9, "self_limit": 6})
        pid = plan["id"]
        req("PATCH", f"/api/plans/{pid}", token=atok, body={"phase_override": 3})
        toks = {}
        for name in P:
            _, toks[name], _ = login(name, "123456")
        ltok = toks["CCC"]      # 人员管理员（改他人行批量接口操作者）
        lmxtok = toks["BBB"]  # 另一名人员管理员（领导互改场景操作者）

        def pick(tok, name, day, symbol):
            return req("PUT", f"/api/plans/{pid}/cell", token=tok,
                       body={"person_id": P[name]["id"], "day": day, "symbol": symbol})

        def batch(tok, edits):
            return req("POST", f"/api/plans/{pid}/admin-edits", token=tok,
                       body={"edits": edits})

        def edit(name, day, symbol):
            return {"person_id": P[name]["id"], "day": day, "symbol": symbol}

        def cell_of(name, day):
            _, d = req("GET", f"/api/plans/{pid}", token=atok)
            return (d["grid"].get(str(P[name]["id"]), {}) or {}).get(str(day))

        def sym_of(name, day):
            c = cell_of(name, day)
            return c["symbol"] if c else None

        def x_count(name):
            _, d = req("GET", f"/api/plans/{pid}", token=atok)
            cells = d["grid"].get(str(P[name]["id"]), {}) or {}
            return sum(1 for c in cells.values() if c["symbol"] == "X")

        # ===== 图3 复现（干部每日上限）：第10天先填满 4 名干部 =====
        for name in ("BBB", "FFF", "GGG", "HHH"):
            pick(atok, name, 10, "X")
        # (1) 先加后减：加EEE（中间状态 5 人）+ 清FFF -> 最终仍 4 人
        st, out = batch(ltok, [edit("EEE", 10, "X"), edit("FFF", 10, None)])
        check("(1) 干部满员日批次「先加后减」最终合法 -> 200（旧实现按中间状态误报 400）",
              st == 200 and sym_of("EEE", 10) == "X" and sym_of("FFF", 10) is None,
              f"status={st}, detail={out.get('detail')}, EEE10={sym_of('EEE', 10)}, FFF10={sym_of('FFF', 10)}")
        # (2) 先减后加：清EEE + 加FFF -> 最终仍 4 人
        st, out = batch(ltok, [edit("EEE", 10, None), edit("FFF", 10, "X")])
        check("(2) 干部满员日批次「先减后加」最终合法 -> 200（两种顺序结果一致）",
              st == 200 and sym_of("EEE", 10) is None and sym_of("FFF", 10) == "X",
              f"status={st}, detail={out.get('detail')}")
        # (3) 最终状态真超限：再加DDD -> 5 人，应 400 且不落表
        st, out = batch(ltok, [edit("DDD", 10, "X")])
        check("(3) 最终状态干部 5 人超限 -> 400（含「10日干部休假已满」「至少5名干部在岗」）且未落表",
              st == 400 and "10日干部休假已满" in str(out.get("detail"))
              and "至少5名干部在岗" in str(out.get("detail"))
              and sym_of("DDD", 10) is None,
              f"status={st}, detail={out.get('detail')}")
        # (4) 满员日同格符号互换 X->R：计数不变，应 200
        st, out = batch(ltok, [edit("BBB", 10, "R")])
        check("(4) 满员日同格互换 X->R（计数不变）-> 200 且已生效",
              st == 200 and sym_of("BBB", 10) == "R",
              f"status={st}, detail={out.get('detail')}, BBB10={sym_of('BBB', 10)}")

        # ===== 图3 复现（个人轮休上限）：III先勾满 6 天轮休 =====
        for day in range(1, 7):
            pick(atok, "III", day, "X")
        # (5) 先加后减：第20天加 X（中间 7 天）+ 清第1天 -> 最终仍 6 天
        st, out = batch(ltok, [edit("III", 20, "X"), edit("III", 1, None)])
        check("(5) 个人轮休满额批次「先加后减」最终合法 -> 200，轮休仍 6 天（旧实现误报超上限）",
              st == 200 and x_count("III") == 6 and sym_of("III", 20) == "X"
              and sym_of("III", 1) is None,
              f"status={st}, detail={out.get('detail')}, X数={x_count('III')}")
        # (6) 最终状态真超限：第21天再加 X -> 7 天，应 400 且不落表
        st, out = batch(ltok, [edit("III", 21, "X")])
        check("(6) 最终状态轮休 7 天超个人上限 -> 400（含「调整后轮休将超过自选上限」）且未落表",
              st == 400 and "调整后轮休将超过自选上限" in str(out.get("detail"))
              and sym_of("III", 21) is None,
              f"status={st}, detail={out.get('detail')}")

        # ===== 图3 复现（科领导每日上限）：第12天 2 名科领导已休 =====
        pick(atok, "AAA", 12, "X")
        pick(atok, "BBB", 12, "X")
        # (7) BBB（管理员）批次：先给CCC加（中间领导 3 人）+ 清AAA -> 最终仍 2 人
        st, out = batch(lmxtok, [edit("CCC", 12, "X"), edit("AAA", 12, None)])
        check("(7) 科领导满员日批次「先加后减」最终合法 -> 200（旧实现误报科领导已满）",
              st == 200 and sym_of("CCC", 12) == "X" and sym_of("AAA", 12) is None,
              f"status={st}, detail={out.get('detail')}")

        # ===== 图3 复现（协管员每日上限）：第14天JJJ已休 =====
        pick(atok, "JJJ", 14, "X")
        # (8) 先加后减：加KKK（中间协管员 2 人）+ 清JJJ -> 最终仍 1 人
        st, out = batch(ltok, [edit("KKK", 14, "X"), edit("JJJ", 14, None)])
        check("(8) 协管员满员日批次「先加后减」最终合法 -> 200（旧实现误报另一名协管员已休）",
              st == 200 and sym_of("KKK", 14) == "X" and sym_of("JJJ", 14) is None,
              f"status={st}, detail={out.get('detail')}")
        # (9) 最终状态真超限：JJJ再加 -> 协管员 2 人同日，应 400 且不落表
        st, out = batch(ltok, [edit("JJJ", 14, "X")])
        check("(9) 最终状态协管员 2 人同日 -> 400（含「协管员休假已满」）且未落表",
              st == 400 and "协管员休假已满" in str(out.get("detail"))
              and sym_of("JJJ", 14) is None,
              f"status={st}, detail={out.get('detail')}")

        # ===== PUT /cell 审计回归（12 月计划）：单格互换在满员日计数正确 =====
        st, plan2 = req("POST", "/api/plans", token=atok,
                        body={"year": 2026, "month": 12, "quota": 9, "self_limit": 6})
        pid2 = plan2["id"]
        req("PATCH", f"/api/plans/{pid2}", token=atok, body={"phase_override": 3})

        def pick2(tok, name, day, symbol):
            return req("PUT", f"/api/plans/{pid2}/cell", token=tok,
                       body={"person_id": P[name]["id"], "day": day, "symbol": symbol})

        for name in ("BBB", "CCC", "FFF", "GGG"):
            pick2(atok, name, 5, "X")
        st, _ = pick2(toks["FFF"], "FFF", 5, "O")
        st2, _ = pick2(toks["FFF"], "FFF", 5, "X")
        check("(10) PUT /cell 满员日单格互换 X->O->X 均 200（被替换格不重复计数，审计无误报）",
              st == 200 and st2 == 200, f"codes={st},{st2}")
        st, out = pick2(toks["EEE"], "EEE", 5, "X")
        check("(11) PUT /cell 满员日新增仍被后端兜底拒绝（400 干部休假已满）",
              st == 400 and "干部休假已满" in str(out.get("detail")),
              f"status={st}, detail={out.get('detail')}")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()

    # ---------- 静态检查（图1/图2 前端接线与后端结构） ----------
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()
    backend = open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read()

    check("app.js 带 v5.0 版本标记", "/* duty-roster v6.31 */" in js)
    check("后端整批最终状态校验 _check_batch_caps 存在且按 person_cap_count(work,…) 判个人上限",
          "def _check_batch_caps" in backend and "person_cap_count(work, pid)" in backend)
    check("后端 admin-edits 改为整批套用后统一校验（旧逐格调用已消失）",
          "_check_batch_caps(plan, people, work, body.edits, by_id)" in backend
          and "_check_cell_caps(plan, people, work" not in backend)
    check("后端每日上限最终状态文案保留（干部/科领导）且协管员文案规范化",
          "日干部休假已满 {CADRE_DAILY_LEAVE_CAP} 人" in backend
          and "日科领导休假已满 {LEADER_DAILY_LEAVE_CAP} 人" in backend
          and "日协管员休假已满 {ASSISTANT_DAILY_LEAVE_CAP} 人" in backend)
    check("前端本地有效网格/即时统计函数存在（effectiveGridMap/localDayStats/countsLeave）",
          "function effectiveGridMap" in js and "function localDayStats" in js
          and "function countsLeave" in js)
    check("成员合并页与旧选班页的三行统计改用本地有效网格统计（statsArr: localDayStats() x2）",
          js.count("statsArr: localDayStats()") >= 2)
    check("超管合并页统计口径未动（仍用服务端 display/final 统计）",
          "statsArr: detail.display_day_stats" in js and "statsArr: detail.final_day_stats" in js)
    check("点选时每日上限预检 checkDailyCaps 存在且被本人/他人两条预检链调用",
          "function checkDailyCaps" in js
          and "if (!checkDailyCaps(mine, day, symbol)) return false;" in js
          and "if (!checkDailyCaps(person, day, symbol)) return false;" in js)
    check("点选预检三组 toast 文案齐备（干部/科领导/协管员 + 「不能再勾」）",
          "干部休假已满${CADRE_DAILY_LEAVE_CAP}人（需保证至少5名干部在岗），不能再勾" in js
          and "科领导休假已满${LEADER_DAILY_LEAVE_CAP}人（需保证至少1名科领导在岗），不能再勾" in js
          and "协管员休假已满${ASSISTANT_DAILY_LEAVE_CAP}人（需保证至少1名协管员在岗），不能再勾" in js)
    check("v6.4 适配：满员灰底渲染已取消（gridHTML 不再读 stats 的 full 挂灰类）；本地统计仍产出 full/assistant_full、点选预检 checkDailyCaps 口径未变",
          "stats[d].full" not in js and "assistant_full" in js and "function checkDailyCaps" in js)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- v4.8 根因说明（问题3）：旧 admin-edits 在 for 循环里「校验一格 -> 套用
  一格」，_check_cell_caps 按只套用了本批前若干格的中间网格判定。同日
  已达每日上限时，批次内任一「加休假」编辑只要排在同日「清休假」编辑
  之前，就会按中间状态（少清一格）误判超限、整批 400——用户图3 中
  8 日/22 日均如此（两天已保存网格均为干部休假 4 人、在岗 5 人，批次内
  含同日清格与加格，最终状态合法）。修复：整批先全部套用到工作网格，
  再由 _check_batch_caps 对最终状态统一校验（个人轮休上限按每位对象
  最终整行计数；每日上限按每个被改日期的最终全员计数；检查顺序为
  个人上限按对象首次出现顺序、每日上限按日期升序且同日干部->科领导
  ->协管员）。PUT /cell、PUT /final/cell 经审计为单格对当前网格校验、
  cur_counts 已扣除被替换格，互换符号计数正确，无中间状态问题，未改。
- 适配说明（v4.8 引起的旧套件改动，均已在对应测试文件处注明）：
  - 全部套件（v25–v47）：仅版本标记断言由 v4.7 提升为 v4.8（检查名同步），
    其余断言未动；
  - smoke_test_v47：「后端两处个人上限强制点…」静态断言原钉住
    _check_cell_caps 的字面量 person_cap_count(grid, person["id"])，随
    后端改为 _check_batch_caps 最终状态校验，更新为 person_cap_count
    (work, pid) + def _check_batch_caps，并同步其文件头沿革说明；
  - smoke_test_v26 的整批校验用例（合法 2 格、无变化批次、含一处真超限
    的批次、个人上限批次）在最终状态口径下结论不变（真超限批次的最终
    状态仍为干部 5 人），全部原样通过，未改断言；
  - 协管员整批超限文案由旧逐格口径「该日另一名协管员已休假，需保证
    每天至少1名协管员在岗（N日）」规范为「N日协管员休假已满 1 人
    （需保证至少1名协管员在岗）」（最终状态下两名协管员同日休假时旧
    文案语义不成立）；PUT /cell 的协管员文案未动，无套件钉住旧整批
    文案，仅 v4.7(8b) 查「协管员」子串、仍成立。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v4.8 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：本地临时库（DUTY_DB 指向临时文件）+ 静态检查；未触碰线上数据\n")
            f.write("- v4.8（用户三图反馈）：①底部三行在岗统计改按本地有效网格"
                    "（含未保存点选）即时刷新，满员变灰同步；②每日人数上限改在"
                    "点选当下预检拦截并即时提示，不再等保存时整批报错；③修复"
                    "管理员整批保存的中间状态误判——最终状态合法的批次不再被"
                    "「N日干部休假已满」误拒（根因与修复见下方适配说明）。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv4.8: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
