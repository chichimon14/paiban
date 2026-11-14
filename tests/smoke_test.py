# -*- coding: utf-8 -*-
"""示例科室排班系统冒烟测试。

自动启动后端（独立临时数据库），跑完整流程：
登录 -> 校验种子分组 -> 建 2026-11 计划(Q=9,S=6) -> 阶段覆盖全开 ->
科长选9天/成员各选6天 -> 验证每日上限拒绝（干部满4 / 科领导满2）->
验证越权修改被拒 -> 一键补满 -> 验证人人9天且每日干部>=5、科领导>=1 ->
导出 Excel 并校验 -> 发布锁定后成员不可改。
结果写入 ../SMOKE_TEST.md。
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
BASE = "http://127.0.0.1:3000"
REPORT = os.path.join(ROOT, "SMOKE_TEST.md")

EXPECTED_GROUPS = {
    "AAA": "chief", "BBB": "A", "CCC": "B", "DDD": "A", "EEE": "B",
    "FFF": "A", "GGG": "A", "HHH": "B", "III": "B",
    "JJJ": "A", "KKK": "B",  # v2.2：协管员纳入 A/B 组
}

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), "-", name, ("| " + str(detail) if detail else ""))


def req(method, path, token=None, body=None, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            content = resp.read()
            return resp.status, (content if raw else json.loads(content or b"{}"))
    except urllib.error.HTTPError as e:
        content = e.read()
        if raw:
            return e.code, content
        try:
            return e.code, json.loads(content or b"{}")
        except Exception:
            return e.code, {"detail": content.decode("utf-8", "replace")}


def main():
    tmpdb = os.path.join(tempfile.mkdtemp(prefix="duty-smoke-"), "test.db")
    env = dict(os.environ, DUTY_DB=tmpdb)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--port", "3000"],
        cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    solver_used = "unknown"
    try:
        up = False
        for _ in range(60):
            try:
                status, _ = req("GET", "/api/health")
                if status == 200:
                    up = True
                    break
            except Exception:
                pass
            time.sleep(0.5)
        check("服务在 3000 端口启动", up)
        if not up:
            return 1

        # ---- 登录
        status, bad = req("POST", "/api/login", body={"username": "admin", "password": "wrong"})
        check("错误密码被拒绝(401)", status == 401, f"status={status}")
        status, admin = req("POST", "/api/login", body={"username": "admin", "password": "admin123"})
        check("超级管理员登录", status == 200 and admin.get("is_admin"), f"status={status}")
        atok = admin["token"]

        tokens = {}
        persons = {}
        status, plist = req("GET", "/api/people", token=atok)
        for p in plist:
            persons[p["name"]] = p
        for name in EXPECTED_GROUPS:
            status, u = req("POST", "/api/login", body={"username": name, "password": "123456"})
            if status == 200:
                tokens[name] = u["token"]
        check("11 名成员均可登录(初始密码123456)", len(tokens) == 11, f"成功 {len(tokens)}/11")

        # ---- 种子分组（用户更正版）
        group_ok = all(persons[n]["grp"] == g for n, g in EXPECTED_GROUPS.items())
        group_desc = "；".join(
            f"{n}={persons[n]['grp'] or '—'}" for n in EXPECTED_GROUPS
        )
        check("种子分组正确(A:BBB/DDD/FFF/GGG B:CCC/EEE/HHH/III)",
              group_ok, group_desc)

        # ---- 建计划
        status, plan = req("POST", "/api/plans", token=atok,
                           body={"year": 2026, "month": 11, "quota": 9, "self_limit": 6})
        check("创建 2026-11 计划 Q=9 S=6", status == 200, f"status={status}")
        pid = plan["id"]
        status, detail = req("GET", f"/api/plans/{pid}", token=atok)
        pl = detail["plan"]
        check("奇数月默认先行组为 A", pl["first_group"] == "A", pl["first_group"])
        check("2026-11 共 30 天", pl["days_in_month"] == 30)
        fa = [p for p in detail["people"] if p["id"] == pl["first_assistant_id"]][0]
        check("奇数月先行组(A)内协管员为JJJ", fa["name"] == "JJJ", fa["name"])

        # ---- 阶段覆盖全开
        status, _ = req("PATCH", f"/api/plans/{pid}", token=atok, body={"phase_override": 3})
        status, detail = req("GET", f"/api/plans/{pid}", token=atok)
        check("管理员阶段覆盖=3(全部开放)", status == 200 and detail["plan"]["effective_phase"] == 3)

        picked = {n: set() for n in EXPECTED_GROUPS}

        def pick(name, day, symbol="X"):
            st, out = req("PUT", f"/api/plans/{pid}/cell", token=tokens[name],
                          body={"person_id": persons[name]["id"], "day": day, "symbol": symbol})
            if st == 200:
                picked[name].add(day)
            return st, out

        # ---- 上限拒绝测试（先做，占用名额计入各自额度）
        check("科长选第1天", pick("AAA", 1)[0] == 200)
        check("科长选第2天", pick("AAA", 2)[0] == 200)
        check("BBB选第1天", pick("BBB", 1)[0] == 200)
        check("CCC选第2天", pick("CCC", 2)[0] == 200)
        # 第2天科领导已休2人（AAA+CCC），BBB再选应被科领导上限拒绝
        st, out = pick("BBB", 2)
        check("科领导每日上限拒绝(第2天BBB被拒)", st == 400 and "科领导" in out.get("detail", ""),
              f"status={st}, detail={out.get('detail')}")
        check("DDD选第1天", pick("DDD", 1)[0] == 200)
        check("EEE选第1天", pick("EEE", 1)[0] == 200)
        # 第1天干部已休4人，FFF再选应被干部上限拒绝
        st, out = pick("FFF", 1)
        check("干部每日上限拒绝(第1天FFF被拒)", st == 400 and "干部休假已满" in out.get("detail", ""),
              f"status={st}, detail={out.get('detail')}")

        # ---- 越权修改
        st, _ = req("PUT", f"/api/plans/{pid}/cell", token=tokens["FFF"],
                    body={"person_id": persons["GGG"]["id"], "day": 5, "symbol": "X"})
        check("成员不能修改他人排班(403)", st == 403, f"status={st}")

        # ---- 各自选满自选额度（贪心取最早可行的日期）
        def fill_to(name, target):
            for d in range(1, 31):
                if len(picked[name]) >= target:
                    break
                if d in picked[name]:
                    continue
                pick(name, d)
            return len(picked[name])

        fill_ok = True
        fill_desc = []
        for name, target in [("AAA", 9), ("BBB", 6), ("CCC", 6), ("DDD", 6),
                             ("EEE", 6), ("FFF", 6), ("GGG", 6), ("HHH", 6),
                             ("III", 6), ("JJJ", 6), ("KKK", 6)]:
            got = fill_to(name, target)
            fill_desc.append(f"{name}:{got}/{target}")
            fill_ok = fill_ok and got == target
        check("科长自选9天、其余10人各选6天", fill_ok, "，".join(fill_desc))

        # ---- 一键补满
        status, out = req("POST", f"/api/plans/{pid}/autocomplete", token=atok)
        if status == 200:
            solver_used = out.get("autocomplete", {}).get("solver", "unknown")
        check("一键补满执行成功", status == 200,
              f"status={status}, filled={out.get('autocomplete', {}).get('filled') if status == 200 else out.get('detail')}, solver={solver_used}")

        # ---- 补满后校验
        status, detail = req("GET", f"/api/plans/{pid}", token=atok)
        all9 = all(p["selected_leave"] == 9 for p in detail["people"])
        check("补满后每人恰好休满 9 天", all9,
              "，".join(f"{p['name']}:{p['selected_leave']}" for p in detail["people"]))
        cadre_ok = all(s["cadre_on_duty"] >= 5 for s in detail["day_stats"])
        leader_ok = all(s["leader_on_duty"] >= 1 for s in detail["day_stats"])
        min_cadre = min(s["cadre_on_duty"] for s in detail["day_stats"])
        min_leader = min(s["leader_on_duty"] for s in detail["day_stats"])
        check("每日干部在岗 >= 5", cadre_ok, f"最低 {min_cadre}")
        check("每日科领导在岗 >= 1", leader_ok, f"最低 {min_leader}")

        # ---- Excel 导出
        status, content = req("GET", f"/api/plans/{pid}/export.xlsx", token=atok, raw=True)
        xlsx_path = os.path.join(ROOT, "tests", "smoke_export.xlsx")
        if status == 200:
            with open(xlsx_path, "wb") as f:
                f.write(content)
        size = len(content) if status == 200 else 0
        title_ok = False
        if status == 200 and size > 3000:
            from openpyxl import load_workbook
            wb = load_workbook(xlsx_path)
            ws = wb.active
            title_ok = "排班表" in str(ws["A1"].value) and "11月可休9天" in str(ws["A1"].value)
        check("Excel 导出成功且标题正确", status == 200 and size > 3000 and title_ok,
              f"status={status}, size={size}B, file=tests/smoke_export.xlsx")

        # ---- 发布锁定
        status, _ = req("POST", f"/api/plans/{pid}/publish", token=atok)
        check("管理员发布计划", status == 200)
        st, _ = req("PUT", f"/api/plans/{pid}/cell", token=tokens["FFF"],
                    body={"person_id": persons["FFF"]["id"], "day": 28, "symbol": None})
        check("发布后成员不可再修改(403)", st == 403, f"status={st}")

        return 0 if all(r[1] for r in results) else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "w", encoding="utf-8") as f:
            f.write("# 冒烟测试报告\n\n")
            f.write(f"- 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"- 环境：本地以独立临时数据库启动后端（端口 3000），计划为 2026-11，Q=9，S=6\n")
            f.write(f"- 补满求解器：{solver_used}\n")
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\n{passed}/{len(results)} passed -> {REPORT}")


if __name__ == "__main__":
    sys.exit(main())
