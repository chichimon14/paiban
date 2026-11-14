# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.3 冒烟测试（追加到 SMOKE_TEST.md 的 v6.3 章节）。

v6.3 变更（用户 2026-11-01 三图反馈 + 追加一项，共四项）：
  1)【功能】已发布排班表人员管理员改不了（图3）：最终表原写路径只有
     超管逐格 PUT /final/cell 且已发布即锁定。后端新增批量接口
     POST /api/plans/{id}/final/edits（super+admin）：整批先套用再按
     「最终状态」校验每日硬上限（与草稿层共用抽出的 _daily_cap_error；
     最终层不查个人自选上限），净变化落 final_selections 并逐格记
     adjustments（status=applied、操作者为当前用户），计划保持已
     发布；无净变化批次 applied=0 且不落库/不记日志/不刷新时间戳。
     前端成员合并页已发布分支对 role=admin 改为最终表可编辑：点格
     本地暂存（橙色描边、finalEdits）、标题行「保存修改/撤销」、
     保存后重载；成员仍只读。
  2)【样式】岗位显示页日期控制行四控件高低不平（图1）：.daily-controls
     改为 stretch + 子控件统一 38px 高、label 横向排列（style.css
     v6.3 段第 1 条）。
  3)【样式】当日排班预览表同排姓名高低不平（图2）：.daily-table
     单元格统一 vertical-align: middle + 一致内距/行高；早班生成
     图片的内联表格同步加 vertical-align:middle（CSS v6.3 段第 2 条）。
  4)【样式】轮休符号 ✓ 在 macOS 上被 -apple-system 渲染成花体勾
     （图3）：显示假期符号的元素（网格单元格/选符号弹层/图例）强制
     改用 "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC",
     sans-serif 字体栈（不含 -apple-system），✓ 回到朴素对勾；后端
     符号定义与数据不变（CSS v6.3 段第 3 条）。

测试口径（临时库 + 临时端口 3013）：
  超管建 2026-11 计划并逐格写最终表（5 日DDD X；10 日四名干部
  X 凑满干部每日上限 4 人）→ 保存并发布 → 授权CCC为人员管理员：
  A) 管理员改他人格（HHH 6 日 X）成功、最终表与成员视角可见、
     计划仍已发布、adjustments 有CCC为操作者的 applied 记录；
  B) 普通成员调用同一接口 403；
  C) 满员日净零挪休（10 日DDD清除 + HHH X）整批通过；
  D) 结果超限的整批（附带一格合法修改）整体 400、合法格也不落表；
  E) 同值重提为无净变化：applied=0、日志不增；
  F) 当日排班 context 的在岗判定随最终表修改实时变化（6 日HHH
     转休假、10 日DDD恢复在岗/HHH转休假）；
  G) 超管亦可走批量路径（AAA 7 日 R，日志操作者为系统管理员）；
  S) 静态断言：前端已发布+管理员编辑分支与保存接线、CSS 三条
     v6.3 规则（含符号字体栈以 PingFang SC 起始且不含 -apple-system）、
     后端新接口与共用校验函数、app.js v6.3 标记。
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
PORT = 3013
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
    return out.get("token") if st == 200 else None


def main():
    tmp = tempfile.mkdtemp(prefix="duty-roster-v63-")
    dbpath = os.path.join(tmp, "test.db")
    env = dict(os.environ, DUTY_DB=dbpath)
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
        check("v6.3 服务启动", up)
        if not up:
            return 1

        atok = login("admin", "admin123")            # super
        st, people = req("GET", "/api/people", token=atok)
        pid_of = {p["name"]: p["id"] for p in people}

        st, plan = req("POST", "/api/plans", token=atok,
                       body={"year": 2026, "month": 11, "quota": 9, "self_limit": 6})
        plan_id = plan["id"]
        check("建 2026 年 11 月计划成功", st == 200 and plan_id is not None)

        # 授权CCC为人员管理员（role=admin），HHH保持普通成员
        st, users = req("GET", "/api/users", token=atok)
        lw_user = [u for u in users if u["username"] == "CCC"][0]
        st, _ = req("PATCH", f"/api/users/{lw_user['id']}", token=atok,
                    body={"is_admin": True})
        ltok = login("CCC", "123456")
        st, me_lw = req("GET", "/api/me", token=ltok)
        check("CCC登录 role=admin", st == 200 and me_lw.get("role") == "admin",
              str(me_lw.get("role")))
        mtok = login("HHH", "123456")
        st, me_zwb = req("GET", "/api/me", token=mtok)
        check("HHH登录 role=member", st == 200 and me_zwb.get("role") == "member",
              str(me_zwb.get("role")))

        # 超管逐格写最终表（发布前）→ 保存 → 发布
        def fcell(name, day, sym):
            return req("PUT", f"/api/plans/{plan_id}/final/cell", token=atok,
                       body={"person_id": pid_of[name], "day": day, "symbol": sym})

        ok = fcell("DDD", 5, "X")[0] == 200
        for n in ("DDD", "EEE", "FFF", "GGG"):
            ok = ok and fcell(n, 10, "X")[0] == 200
        check("超管逐格写最终表（5 日 1 格 + 10 日满员 4 格）", ok)
        req("POST", f"/api/plans/{plan_id}/final/save", token=atok)
        st, _ = req("POST", f"/api/plans/{plan_id}/publish", token=atok)
        st, det = req("GET", f"/api/plans/{plan_id}", token=atok)
        check("计划已发布且展示层为最终表",
              st == 200 and det["plan"]["published"] is True
              and det["display_kind"] == "final")

        def final_cell(det_, name, day):
            row = det_["final_grid"].get(str(pid_of[name]), {})
            c = row.get(str(day))
            return c["symbol"] if c else None

        def edits(tok, items):
            return req("POST", f"/api/plans/{plan_id}/final/edits", token=tok,
                       body={"edits": items})

        def E(name, day, sym):
            return {"person_id": pid_of[name], "day": day, "symbol": sym}

        # ---- A) 管理员修改已发布最终表（他人格） ----
        st, out = edits(ltok, [E("HHH", 6, "X")])
        check("A 管理员（CCC）改已发布最终表：HHH 6 日 X 保存成功",
              st == 200 and out.get("applied") == 1 and out.get("logged") == 1,
              f"st={st} out={out}")
        st, det = req("GET", f"/api/plans/{plan_id}", token=ltok)
        check("A 最终表已反映修改且计划仍为已发布",
              final_cell(det, "HHH", 6) == "X"
              and det["plan"]["published"] is True)
        st, det_m = req("GET", f"/api/plans/{plan_id}", token=mtok)
        check("A 成员视角看到最终表新值（展示层=最终表）",
              det_m["display_kind"] == "final"
              and final_cell(det_m, "HHH", 6) == "X")
        st, logs = req("GET", "/api/logs", token=atok)
        mods = [m for m in logs["modifications"] if m["plan_id"] == plan_id]
        hit = [m for m in mods if m["admin_name"] == "CCC"
               and m["target_name"] == "HHH" and m["day"] == 6
               and m["symbol"] == "X" and m["old_symbol"] is None
               and m["status"] == "applied"]
        check("A adjustments 日志有CCC的操作记录（applied，含旧值）",
              len(hit) == 1, f"mods={len(mods)}")
        log_count_after_a = len(mods)

        # ---- B) 普通成员禁止 ----
        st, out = edits(mtok, [E("III", 6, "X")])
        check("B 普通成员调用最终表批量接口被拒（403）且不落表",
              st == 403)
        st, det = req("GET", f"/api/plans/{plan_id}", token=atok)
        check("B III 6 日仍为空", final_cell(det, "III", 6) is None)

        # ---- C) 满员日净零挪休（最终状态合法） ----
        st, out = edits(ltok, [E("DDD", 10, None), E("HHH", 10, "X")])
        check("C 满员日（干部休假已满 4）净零挪休整批通过",
              st == 200 and out.get("applied") == 2, f"st={st} out={out}")
        st, det = req("GET", f"/api/plans/{plan_id}", token=atok)
        stat10 = [s for s in det["final_day_stats"] if s["day"] == 10][0]
        check("C 挪休后：DDD 10 日清除、HHH 10 日 X、当日干部休假仍 4 人",
              final_cell(det, "DDD", 10) is None
              and final_cell(det, "HHH", 10) == "X"
              and stat10["cadre_leave"] == 4, str(stat10))

        # ---- D) 结果超限整批拒绝（原子性） ----
        st, out = edits(ltok, [E("HHH", 12, "X"), E("III", 10, "X")])
        check("D 结果超限（10 日干部休假将达 5）的整批被拒（400）",
              st == 400, f"st={st} out={out}")
        st, det = req("GET", f"/api/plans/{plan_id}", token=atok)
        check("D 整批不落表：同批合法格（HHH 12 日）也未写入",
              final_cell(det, "HHH", 12) is None
              and final_cell(det, "III", 10) is None)

        # ---- E) 无净变化批次 ----
        st, logs = req("GET", "/api/logs", token=atok)
        before = len([m for m in logs["modifications"] if m["plan_id"] == plan_id])
        st, out = edits(ltok, [E("HHH", 6, "X")])   # 已是 X，同值重提
        st2, logs2 = req("GET", "/api/logs", token=atok)
        after = len([m for m in logs2["modifications"] if m["plan_id"] == plan_id])
        check("E 同值重提为无净变化：applied=0 且日志不增",
              st == 200 and out.get("applied") == 0 and after == before,
              f"applied={out.get('applied')} logs {before}->{after}")
        check("E（计数自洽）A+C 两批共记 3 条日志", before == log_count_after_a + 2,
              f"before={before}")

        # ---- F) 当日排班在岗判定随最终表修改实时变化 ----
        st, c6 = req("GET", "/api/daily/context?date=2026-11-06", token=ltok)
        off6 = {p["name"] for p in c6["off_duty"]}
        on6 = {p["name"] for p in c6["on_duty_cadre"]}
        check("F 11-06 context：HHH（已被管理员改休）不在岗名单",
              "HHH" in off6 and "HHH" not in on6, str(off6))
        st, c10 = req("GET", "/api/daily/context?date=2026-11-10", token=ltok)
        off10 = {p["name"] for p in c10["off_duty"]}
        on10 = {p["name"] for p in c10["on_duty_cadre"]}
        check("F 11-10 context：DDD恢复在岗、HHH在休假名单",
              "DDD" in on10 and "HHH" in off10
              and "DDD" not in off10, f"off={off10}")

        # ---- G) 超管亦可走批量路径 ----
        st, out = edits(atok, [E("AAA", 7, "R")])
        st, det = req("GET", f"/api/plans/{plan_id}", token=atok)
        st, logs = req("GET", "/api/logs", token=atok)
        hit_g = [m for m in logs["modifications"]
                 if m["plan_id"] == plan_id and m["admin_name"] == "系统管理员"
                 and m["target_name"] == "AAA" and m["day"] == 7
                 and m["symbol"] == "R" and m["status"] == "applied"]
        check("G 超管走批量路径改最终表成功且日志操作者为系统管理员",
              st == 200 and final_cell(det, "AAA", 7) == "R" and len(hit_g) == 1)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    # ---- S) 静态断言 ----
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()
    css = open(os.path.join(fe, "style.css"), encoding="utf-8").read()
    backend = open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read()
    css63 = css.split("/* ================= v6.3")[1] if "/* ================= v6.3" in css else ""

    check("S app.js 带 v6.3 版本标记", "/* duty-roster v6.31 */" in js)
    check("S 后端含最终表批量接口与共用每日校验（final/edits / final_batch_edits / _daily_cap_error）",
          '"/api/plans/{plan_id}/final/edits"' in backend
          and "def final_batch_edits" in backend
          and "def _daily_cap_error" in backend)
    check("S 前端成员页含已发布+管理员最终表编辑分支与保存接线（finalEditSaveBtn/finalEditUndoBtn/sheetFinalEditMode/effectiveFinalGridMap）",
          "finalEditSaveBtn" in js and "finalEditUndoBtn" in js
          and "sheetFinalEditMode" in js and "effectiveFinalGridMap" in js
          and "/final/edits" in js)
    check("S CSS v6.3：岗位显示日期控制行对齐规则（.daily-controls 等高 38px + label 横向）",
          ".daily-controls" in css63 and "height: 38px" in css63
          and "flex-direction: row" in css63)
    check("S CSS v6.3：当日排班预览表单元格 vertical-align: middle 规则",
          ".daily-table th, .daily-table td" in css63
          and "vertical-align: middle" in css63)
    check("S app.js：早班生成图片内联表格同步 vertical-align:middle",
          "vertical-align:middle" in js)
    sym_stack = '"PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif'
    check("S CSS v6.3：符号字体栈以 PingFang SC 起始（不含 -apple-system 的字体栈）且作用于单元格/弹层/图例",
          sym_stack in css63 and "-apple-system" not in sym_stack
          and "table.grid td.cell" in css63 and ".picker-grid button .sym" in css63
          and ".sheet-legend .lg-item b" in css63)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v6.3 引起的旧套件改动）：
  - 全部套件（v25–v62）：仅版本标记断言由 v6.2 提升为 v6.3，其余未动；
  - 后端 _check_batch_caps 的每日上限校验抽为共用函数 _daily_cap_error
    （草稿层与最终层共用，文案与判定顺序不变）——v26/v48 等草稿层
    批量套件行为断言经全量回归复核不变；
  - smoke_test_v51.py：checkDailyCaps 静态断言字面量随 v6.3 的可选
    gridMap/statsArr 参数更新（缺省仍为草稿全员口径），并以函数段内
    不引用 onlyMeMode/onlyPersonId 继续钉死「预检不受只看本人显示
    过滤影响」的原口径；行为断言未动。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.3 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：临时数据库 + 临时服务端口 3013（API 行为）+ 纯静态检查（前端）\n")
            f.write("- v6.3：①已发布最终表开放人员管理员批量修改（POST /final/edits，"
                    "整批最终状态校验、记日志、保持已发布）；②岗位显示日期控制行"
                    "四控件等高对齐；③当日排班预览表单元格 vertical-align:middle；"
                    "④假期符号改用 PingFang/YaHei 字体栈（去花体勾）。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.3: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
