# -*- coding: utf-8 -*-
"""示例科室排班系统 v2.6 冒烟测试（追加到 SMOKE_TEST.md 的 v2.6 章节）。

v2.6 变更（取代 v2.4 审批流）：
- 姓名列标签单行：.tag/.nm-flex/.nm-tags 不折行；桌面姓名列 176px；
  641~900px 姓名列 112px + 标签 9px 紧凑字号；<=640px 姓名列 104px。
  【v4.2 适配】可读性放大（标签桌面 13px/移动 11px、姓名桌面 17px/移动 13px）
  后移动端姓名列再加宽：641~900px 132px、<=640px 124px（桌面仍 176px），
  下方宽度断言同步更新。
- 排班表标题行徽标「您可勾选 N 天」（N=查看者本人适用上限：科长 Q、其余 S；
  已发布/无对应人员时不显示）。
  【v2.7 适配】徽标已被合并标题取代，本套件的标题断言改为 v2.7 口径：
  sheetTitle(plan, myLimit) 把「，您可休N天」并入标题同一句话，.pick-badge 删除；
  版本标记断言同步提升为 v2.7。审批流/日志相关断言不受 v2.7 影响。
  【v2.8 适配】v2.8 仅改选择层定位（placePicker），仅版本标记断言提升为 v2.8。
  【v2.9 适配】v2.9 为侧栏/页面结构调整（超管导航、数据管理页、人员与权限合并表、
  日志两列），不触及本套件覆盖的逻辑，仅版本标记断言提升为 v2.9。
  【v4.6 适配】标题后半句文案由用户改为「您可勾选N天」（纯文案、计数口径不变），
  本套件的标题断言字面量随之更新；版本标记断言提升为 v4.6。
  【v4.7 适配（2026-11-01）】v4.7 规则变更：个人自选上限只统计轮休（X），
  标题后半句补足为「您可勾选N天轮休」。本套件标题断言只查「您可勾选」
  子串仍满足，仅更新检查名与版本标记（v4.7）；批量个人上限断言
  （对象已达上限被拒）勾的是 X，新口径下行为一致，未动；X 口径的
  完整行为覆盖见 smoke_test_v47.py。
- 人员管理员改他人行 = 本地暂存 + 保存即生效：新接口 POST
  /api/plans/{id}/admin-edits 整批校验（任一违反整体 400、不落表不记日志）、
  落表 source='admin'；仅实际变化的格记一行 adjustments 日志（status='applied'，
  含旧值->新值）；无变化格静默生效不留痕；对象已提交时生成新提交版本。
- 旧审批接口（创建申请/同意/驳回）删除（404）；plan_detail 不再返回
  pending_adjustments / my_adjustments；启动迁移把遗留 pending 置为 void；
  GET /api/logs 返回 {modifications, login_logs}（无 pending 键）。
- 前端：无「我发起的调整」卡、无待审批 ⏳ 标记、无日志页待审批区/审批按钮；
  管理员提示文案更新；app.js 版本标记 v2.6。
"""
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
PORT = 3006
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


def main():
    tmpdb = os.path.join(tempfile.mkdtemp(prefix="duty-smoke-v26-"), "test.db")
    proc, up = start_server(tmpdb)
    try:
        check("v2.6 服务启动", up)
        if not up:
            return 1

        atok = login("admin", "admin123")          # super
        ltok = login("AAA", "123456")            # 人员管理员（种子 chief 自带 is_admin）
        xtok = login("FFF", "123456")              # 普通成员
        st, people = req("GET", "/api/people", token=atok)
        P = {p["name"]: p for p in people}
        tokens = {}
        for name in P:
            tokens[name] = login(name, "123456")
        tokens["AAA"], tokens["FFF"] = ltok, xtok

        st, plan = req("POST", "/api/plans", token=atok,
                       body={"year": 2026, "month": 11, "quota": 9, "self_limit": 6})
        pid = plan["id"]
        req("PATCH", f"/api/plans/{pid}", token=atok, body={"phase_override": 3})

        def batch(tok, edits):
            return req("POST", f"/api/plans/{pid}/admin-edits", token=tok,
                       body={"edits": edits})

        def edit(name, day, symbol):
            return {"person_id": P[name]["id"], "day": day, "symbol": symbol}

        def detail(tok):
            _, d = req("GET", f"/api/plans/{pid}", token=tok)
            return d

        def cell_of(d, name, day):
            return (d["grid"].get(str(P[name]["id"]), {}) or {}).get(str(day))

        def mods(tok=atok):
            _, logs = req("GET", "/api/logs", token=tok)
            return logs

        # ---------- 批量改他人行：2 处修改即时生效 + 恰好 2 条日志 ----------
        st, out = batch(ltok, [edit("DDD", 5, "X"), edit("DDD", 6, "O")])
        d = detail(atok)
        c5, c6 = cell_of(d, "DDD", 5), cell_of(d, "DDD", 6)
        lhq_mods = [m for m in mods()["modifications"]
                    if m["target_person_id"] == P["DDD"]["id"]]
        check("批量改他人行 2 处即时生效（草稿 source='admin'）",
              st == 200 and out.get("applied") == 2
              and c5 and c5["symbol"] == "X" and c5["source"] == "admin"
              and c6 and c6["symbol"] == "O" and c6["source"] == "admin",
              f"status={st}, applied={out.get('applied')}, c5={c5}, c6={c6}")
        check("恰好 2 条修改日志（applied，含旧值->新值）",
              len(lhq_mods) == 2
              and all(m["status"] == "applied" and m["admin_name"] == "AAA"
                      and m["old_symbol"] is None for m in lhq_mods)
              and {m["day"] for m in lhq_mods} == {5, 6},
              f"logs={[(m['day'], m['old_symbol'], m['symbol'], m['status']) for m in lhq_mods]}")

        # ---------- 无变化的修改：生效但不记日志 ----------
        st, out = batch(ltok, [edit("DDD", 5, "X"),      # 与现值相同
                               edit("DDD", 7, None)])   # 清除本来为空的格
        lhq_mods2 = [m for m in mods()["modifications"]
                     if m["target_person_id"] == P["DDD"]["id"]]
        check("无变化修改（同值/清空格）返回 applied=0 且不新增日志",
              st == 200 and out.get("applied") == 0 and out.get("logged") == 0
              and len(lhq_mods2) == 2,
              f"status={st}, out={out}, 日志数={len(lhq_mods2)}")

        # ---------- 整批校验：一处违反上限 -> 整体 400、什么都不落 ----------
        for name in ("BBB", "CCC", "GGG", "HHH"):  # 第 8 天干部休假填满 4 人
            req("PUT", f"/api/plans/{pid}/cell", token=atok,
                body={"person_id": P[name]["id"], "day": 8, "symbol": "X"})
        st, out = batch(ltok, [edit("EEE", 9, "X"),      # 本身合法
                               edit("EEE", 8, "X")])     # 违反干部每日上限
        d = detail(atok)
        zqm_mods = [m for m in mods()["modifications"]
                    if m["target_person_id"] == P["EEE"]["id"]]
        check("整批含一处超每日上限 -> 400 且合法那处也未落表、无日志",
              st == 400 and "干部休假已满" in str(out.get("detail"))
              and cell_of(d, "EEE", 9) is None and not zqm_mods,
              f"status={st}, detail={out.get('detail')}, d9={cell_of(d, 'EEE', 9)}, logs={zqm_mods}")
        # 个人上限整批校验：III先由超管直填 6 天，再批量加第 7 天
        for day in range(11, 17):
            req("PUT", f"/api/plans/{pid}/cell", token=atok,
                body={"person_id": P["III"]["id"], "day": day, "symbol": "X"})
        st, out = batch(ltok, [edit("III", 20, "X")])
        check("对象已达个人上限时批量修改被拒(400)",
              st == 400 and "上限" in str(out.get("detail")),
              f"status={st}, detail={out.get('detail')}")

        # ---------- 已提交对象：保持已提交 + 版本 +1 + 记日志 ----------
        for day in (3, 4):
            req("PUT", f"/api/plans/{pid}/cell", token=xtok,
                body={"person_id": P["FFF"]["id"], "day": day, "symbol": "X"})
        req("POST", f"/api/plans/{pid}/submit", token=xtok)
        st, out = batch(ltok, [edit("FFF", 10, "X")])
        d = detail(atok)
        lx = [p for p in d["people"] if p["name"] == "FFF"][0]
        st2, subs = req("GET", f"/api/plans/{pid}/submissions", token=atok)
        lx_subs = [s for s in subs if s["person_name"] == "FFF"]
        lx_mod = [m for m in mods()["modifications"]
                  if m["target_person_id"] == P["FFF"]["id"] and m["day"] == 10]
        check("改已提交对象后仍为已提交、版本 1->2、新快照含第 10 天、日志已记",
              st == 200 and lx["submission_status"] == "submitted"
              and lx["submission_versions"] == 2
              and lx_subs and lx_subs[-1]["data"].get("10") == "X"
              and len(lx_mod) == 1 and lx_mod[0]["status"] == "applied",
              f"status={st}, 版本={lx['submission_versions']}, 快照={lx_subs[-1]['data'] if lx_subs else None}, 日志={len(lx_mod)}")

        # ---------- 角色门槛 ----------
        st, _ = batch(xtok, [edit("DDD", 12, "X")])
        check("普通成员调用 admin-edits 被拒(403)", st == 403, f"status={st}")
        st, _ = batch(atok, [edit("DDD", 12, "X")])
        check("超级管理员调用 admin-edits 被拒(403，仅人员管理员)", st == 403, f"status={st}")
        st, out = batch(ltok, [edit("AAA", 12, "X")])
        check("管理员批量改自己被拒(400，应走本人行草稿流)",
              st == 400 and "本人" in str(out.get("detail")),
              f"status={st}, detail={out.get('detail')}")

        # ---------- 旧审批接口已删除 ----------
        st, _ = req("POST", f"/api/plans/{pid}/adjustments", token=ltok,
                    body={"target_person_id": P["DDD"]["id"], "day": 5, "symbol": "X"})
        check("旧接口 POST /adjustments（创建申请）已删除(404)", st == 404, f"status={st}")
        st, _ = req("POST", "/api/adjustments/1/approve", token=atok)
        st2, _ = req("POST", "/api/adjustments/1/reject", token=atok)
        check("旧接口 approve/reject 已删除(404)", st == 404 and st2 == 404,
              f"approve={st}, reject={st2}")

        # ---------- plan_detail / logs 结构 ----------
        d = detail(ltok)
        check("plan_detail 不再返回 pending_adjustments / my_adjustments",
              "pending_adjustments" not in d and "my_adjustments" not in d,
              f"keys 含 pending={'pending_adjustments' in d}, my={'my_adjustments' in d}")
        logs = mods()
        applied_rows = [m for m in logs.get("modifications", [])
                        if m["status"] == "applied"]
        check("/api/logs 返回 {modifications, login_logs} 且无 pending 键、含 applied 记录",
              "modifications" in logs and "login_logs" in logs
              and "pending" not in logs and len(applied_rows) >= 3,
              f"keys={sorted(logs.keys())}, applied 行数={len(applied_rows)}")

        # ---------- pending -> void 启动迁移 ----------
        st, users = req("GET", "/api/users", token=atok)
        lbm_uid = [u for u in users if u["username"] == "AAA"][0]["id"]
        stop_server(proc)
        conn = sqlite3.connect(tmpdb)
        cur = conn.execute(
            "INSERT INTO adjustments (plan_id, admin_user_id, admin_name,"
            " target_person_id, day, symbol, old_symbol, status)"
            " VALUES (?,?,?,?,?,?,?, 'pending')",
            (pid, lbm_uid, "AAA", P["DDD"]["id"], 15, "X", None))
        seeded_id = cur.lastrowid
        conn.commit()
        conn.close()
        proc, up2 = start_server(tmpdb)
        check("迁移验证用服务重启成功", up2)
        if up2:
            atok2 = login("admin", "admin123")
            _, logs2 = req("GET", "/api/logs", token=atok2)
            seeded = [m for m in logs2["modifications"] if m["id"] == seeded_id]
            check("遗留 pending 申请重启后被作废（status='void'）",
                  len(seeded) == 1 and seeded[0]["status"] == "void",
                  f"seeded={seeded}")
    finally:
        stop_server(proc)

    # ---------- 前端静态检查 ----------
    js = open(os.path.join(ROOT, "frontend", "app.js"), encoding="utf-8").read()
    css = open(os.path.join(ROOT, "frontend", "style.css"), encoding="utf-8").read()
    check("app.js 带当前版本标记（v4.7，标记随版本提升）", "/* duty-roster v6.31 */" in js)

    def css_rule(selector):
        a = css.index(selector)
        return css[a:css.index("}", a)]

    check("标签单行 CSS（.tag/.nm-flex/.nm-tags 均不折行）",
          "white-space: nowrap" in css_rule(".tag {")
          and "flex-wrap: nowrap" in css_rule(".nm-flex {")
          and "flex-wrap: nowrap" in css_rule(".nm-tags {"))
    # v4.2 适配：移动端姓名列随标签/姓名放大再加宽（132/124px），桌面 176px 不变
    check("姓名列加宽（桌面 176px / 641~900 为 132px / <=640 为 124px）",
          "width: 176px; min-width: 176px" in css
          and "width: 132px; min-width: 0" in css
          and "width: 124px; min-width: 124px" in css)
    check("标题合并逻辑（v2.7：sheetTitle 并入标题后半句 + 传本人 select_limit、无徽标残留；后半句文案 v4.6 改为「您可勾选N天」、v4.7 补足为「您可勾选N天轮休」）",
          "您可勾选" in js and "function sheetTitle" in js
          and "sheetTitle(p, mine.select_limit)" in js
          and "pick-badge" not in js and ".pick-badge" not in css
          and "pickLimit" not in js)
    check("管理员提示文案为 v2.6 口径（保存后生效、记日志）",
          "您是管理员：可点击他人行调整排班，与改自己一样点「保存」后生效，修改会记录在日志中。" in js)
    check("保存汇总 toast（含对他人的 N 处修改）与 admin-edits 调用存在",
          "admin-edits" in js and "处修改，已生效" in js and "adminEdits" in js)
    check("前端无审批残留（无我发起的调整/待审批标记/审批按钮/旧接口调用）",
          "我发起的调整" not in js and "myAdjustmentsHTML" not in js
          and "pending-adj" not in js and "待审批" not in js
          and "data-approve" not in js and "/adjustments" not in js
          and "pending_adjustments" not in js and "my_adjustments" not in js)
    check("日志页为两段式（管理员修改记录 + 已作废（未生效）标签）",
          "管理员修改记录" in js and "已作废（未生效）" in js
          and "modifications" in js)

    return 0 if all(r[1] for r in results) else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v2.6 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write(f"- 环境：独立临时数据库（端口 {PORT}），计划 2026-11，Q=9，S=6\n")
            f.write("- v2.6：审批流撤销——管理员改他人行本地暂存、保存即经 admin-edits "
                    "整批生效并记修改日志；pending 遗留启动作废；标题徽标与姓名列单行标签。\n")
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv2.6: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
