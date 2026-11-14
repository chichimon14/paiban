# -*- coding: utf-8 -*-
"""示例科室排班系统 v2.4 冒烟测试（v2.6 修订版，追加到 SMOKE_TEST.md）。

【v2.6 修订说明】本文件原覆盖 v2.4 的「调整审批流」（发起申请 -> 待审批 ->
超管同意/驳回）。v2.6 已按用户要求整体撤销审批流，改为「管理员本地暂存、
保存即生效、仅实际修改记日志」，故原审批相关断言（创建 pending、标记可见、
同格替代、驳回不改表、同意写草稿、同意时失效 400 等）全部失效并移除，
其行为覆盖已迁移到 tests/smoke_test_v26.py（批量生效/整批回滚/无变化不记
日志/已提交对象再生成/旧接口 404/pending 作废迁移）。本文件保留并按 v2.6
语义更新的部分：
- 三级角色：super（admin 账号）/ admin（is_admin 的人员账号）/ member，
  登录响应含 role；管理台接口（建计划、改计划、改账号、最终表拉取）仅
  super 可用，人员管理员调用一律 403；
- 人员管理员改他人行：set_cell 直改 403（提示走批量保存）；admin-edits
  仅 role='admin' 可用（member / super 均 403），改自己 400；
- 人员管理员本人行仍可直接改格；批量改他人行保存即写入草稿 source='admin'；
- 登录日志：成功/失败均记录且带 IP；/api/logs 仅 super 可见（成员/人员
  管理员 403），v2.6 返回 {modifications, login_logs} 两部分（无 pending 键）。
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
PORT = 3004
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
    return req("POST", "/api/login", body={"username": name, "password": pw})


def main():
    tmpdb = os.path.join(tempfile.mkdtemp(prefix="duty-smoke-v24-"), "test.db")
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
        check("v2.4 服务启动", up)
        if not up:
            return 1

        # ---------- 角色：登录响应 role ----------
        st, sup = login("admin", "admin123")
        atok = sup.get("token")
        check("超级管理员登录 role=super", st == 200 and sup.get("role") == "super",
              f"status={st}, role={sup.get('role')}")
        st, lbm = login("AAA", "123456")
        ltok = lbm.get("token")
        check("AAA（is_admin 人员）登录 role=admin",
              st == 200 and lbm.get("role") == "admin",
              f"status={st}, role={lbm.get('role')}")
        st, lx = login("FFF", "123456")
        xtok = lx.get("token")
        check("FFF（普通成员）登录 role=member",
              st == 200 and lx.get("role") == "member",
              f"status={st}, role={lx.get('role')}")

        st, people = req("GET", "/api/people", token=atok)
        persons = {p["name"]: p for p in people}
        tokens = {"AAA": ltok, "FFF": xtok}
        for name in persons:
            if name not in tokens:
                _, u = login(name, "123456")
                tokens[name] = u.get("token")

        # ---------- 超管建计划并全开阶段 ----------
        st, plan = req("POST", "/api/plans", token=atok,
                       body={"year": 2026, "month": 11, "quota": 9, "self_limit": 6})
        pid = plan["id"]
        req("PATCH", f"/api/plans/{pid}", token=atok, body={"phase_override": 3})
        check("超管建 2026-11 计划并设阶段覆盖=3", st == 200, f"status={st}")

        # ---------- 人员管理员调用管理台接口一律 403 ----------
        st, _ = req("POST", "/api/plans", token=ltok,
                    body={"year": 2027, "month": 2, "quota": 9, "self_limit": 6})
        check("人员管理员建计划被拒(403)", st == 403, f"status={st}")
        st, _ = req("PATCH", f"/api/plans/{pid}", token=ltok, body={"quota": 8})
        check("人员管理员改计划设置被拒(403)", st == 403, f"status={st}")
        st, users = req("GET", "/api/users", token=atok)
        lx_uid = [u for u in users if u["username"] == "FFF"][0]["id"]
        st, _ = req("PATCH", f"/api/users/{lx_uid}", token=ltok, body={"is_admin": True})
        check("人员管理员改账号权限被拒(403)", st == 403, f"status={st}")
        st, _ = req("POST", f"/api/plans/{pid}/pull-source", token=ltok)
        check("人员管理员调最终表接口(调取数据)被拒(403)", st == 403, f"status={st}")

        # ---------- v2.6：admin-edits 角色门槛（取代原审批申请门槛） ----------
        def batch(tok, name, day, symbol):
            return req("POST", f"/api/plans/{pid}/admin-edits", token=tok,
                       body={"edits": [{"person_id": persons[name]["id"],
                                         "day": day, "symbol": symbol}]})

        st, _ = batch(xtok, "DDD", 5, "X")
        check("普通成员调用 admin-edits 被拒(403)", st == 403, f"status={st}")
        st, _ = batch(atok, "DDD", 5, "X")
        check("超级管理员调用 admin-edits 被拒(403，仅人员管理员)", st == 403, f"status={st}")
        st, out = batch(ltok, "AAA", 5, "X")
        check("管理员批量改自己被拒(400，应直接改本人行)",
              st == 400 and "本人行" in out.get("detail", ""),
              f"status={st}, detail={out.get('detail')}")

        def detail_as(token):
            _, d = req("GET", f"/api/plans/{pid}", token=token)
            return d

        def draft_cell(d, name, day):
            return d["grid"].get(str(persons[name]["id"]), {}).get(str(day))

        # ---------- v2.6：批量改他人行保存即生效（无 pending、无审批） ----------
        st, out = batch(ltok, "DDD", 5, "X")
        d = detail_as(atok)
        cell5 = draft_cell(d, "DDD", 5) or {}
        check("人员管理员批量改DDD第5天即时写入草稿(source='admin')",
              st == 200 and out.get("applied") == 1
              and cell5.get("symbol") == "X" and cell5.get("source") == "admin",
              f"status={st}, cell={cell5}")
        check("plan_detail 无 pending/my 调整字段（v2.6 已移除）",
              "pending_adjustments" not in d and "my_adjustments" not in d)

        # ---------- 人员管理员本人行直改 / 经 set_cell 改他人行 403 ----------
        st, _ = req("PUT", f"/api/plans/{pid}/cell", token=ltok,
                    body={"person_id": persons["AAA"]["id"], "day": 15, "symbol": "X"})
        check("人员管理员本人行可直接改格(200)", st == 200, f"status={st}")
        st, out = req("PUT", f"/api/plans/{pid}/cell", token=ltok,
                      body={"person_id": persons["DDD"]["id"], "day": 8, "symbol": "X"})
        check("人员管理员经 set_cell 改他人行被拒(403，提示走批量保存)",
              st == 403 and "保存" in out.get("detail", ""),
              f"status={st}, detail={out.get('detail')}")

        # ---------- 批量修改的协管员每日上限 ----------
        st, _ = req("PUT", f"/api/plans/{pid}/cell", token=tokens["JJJ"],
                    body={"person_id": persons["JJJ"]["id"], "day": 7, "symbol": "X"})
        st, out = batch(ltok, "KKK", 7, "X")
        check("协管员同日批量修改被拒(400，需至少1名协管员在岗)",
              st == 400 and "协管员" in out.get("detail", ""),
              f"status={st}, detail={out.get('detail')}")

        # ---------- 日志接口权限与内容（v2.6 两部分） ----------
        st, _ = req("GET", "/api/logs", token=xtok)
        check("普通成员访问 /api/logs 被拒(403)", st == 403, f"status={st}")
        st, _ = req("GET", "/api/logs", token=ltok)
        check("人员管理员访问 /api/logs 被拒(403)", st == 403, f"status={st}")
        req("POST", "/api/login", body={"username": "FFF", "password": "wrong-pw"})
        st, logs = req("GET", "/api/logs", token=atok)
        sections_ok = st == 200 and "modifications" in logs and "login_logs" in logs \
            and "pending" not in logs
        applied = [m for m in logs.get("modifications", [])
                   if m["status"] == "applied"
                   and m["target_person_id"] == persons["DDD"]["id"] and m["day"] == 5]
        ll = logs.get("login_logs", []) if st == 200 else []
        ok_rows = [r for r in ll if r["username"] == "FFF" and r["success"] and r["ip"]]
        bad_rows = [r for r in ll if r["username"] == "FFF" and not r["success"] and r["ip"]]
        check("超管可查日志且为 v2.6 两部分(modifications/login_logs，无 pending)",
              sections_ok, f"status={st}, keys={sorted(logs.keys()) if st == 200 else []}")
        check("修改记录含DDD第5天的已生效修改（旧->新）",
              len(applied) == 1 and applied[0]["old_symbol"] is None
              and applied[0]["symbol"] == "X",
              f"applied={applied}")
        check("登录日志含成功与失败记录且均带 IP",
              len(ok_rows) >= 1 and len(bad_rows) >= 1,
              f"FFF成功行={len(ok_rows)}(ip={ok_rows[0]['ip'] if ok_rows else None}), "
              f"失败行={len(bad_rows)}")

        return 0 if all(r[1] for r in results) else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v2.4 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}，v2.6 修订版）\n\n")
            f.write(f"- 环境：独立临时数据库（端口 {PORT}），计划 2026-11，Q=9，S=6\n")
            f.write("- 修订：v2.4 审批流断言已按 v2.6 语义改写（审批行为覆盖移至 "
                    "smoke_test_v26.py），本文件保留三级角色/管理台权限/日志结构与登录日志。\n")
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv2.4: {passed}/{len(results)} passed -> appended to {REPORT}")


if __name__ == "__main__":
    sys.exit(main())
