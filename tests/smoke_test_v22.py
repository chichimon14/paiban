# -*- coding: utf-8 -*-
"""示例科室排班系统 v2.2 冒烟测试（追加到 SMOKE_TEST.md 的 v2.2 章节）。

覆盖 v2.2 变更：
- 协管员纳入 A/B 组：新库种子 JJJ=A组、KKK=B组；旧库（grp 未设置）
  启动时自动迁移填充，且不覆盖管理员已设置的值；
- 协管员选休窗口随所在组开放（取代旧的按月轮流优先）；
- 新硬约束：协管员每日休假 <= 1（在岗 >= 1）——成员同日冲突被拒 400；
- 空计划一键补满后：全员恰好 Q 天，且每日干部在岗>=5、科领导>=1、协管员>=1；
- Excel 导出含第三行统计「协管员在岗人数」；
- 静态检查：前端已移除主页「已选情况」卡片面板与成员页精简条，
  网格含姓名状态色类与图例，月历单元格高度已加大。
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
PORT = 3002
BASE = f"http://127.0.0.1:{PORT}"
REPORT = os.path.join(ROOT, "SMOKE_TEST.md")

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
        with urllib.request.urlopen(r, timeout=60) as resp:
            payload = resp.read()
            return resp.status, (payload if raw else json.loads(payload or b"{}"))
    except urllib.error.HTTPError as e:
        payload = e.read()
        if raw:
            return e.code, payload
        try:
            return e.code, json.loads(payload or b"{}")
        except Exception:
            return e.code, {}


def login(name, pw):
    st, out = req("POST", "/api/login", body={"username": name, "password": pw})
    return (st, out.get("token")) if st == 200 else (st, None)


def start_server(db_path):
    env = dict(os.environ, DUTY_DB=db_path)
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
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()


def main():
    tmpdir = tempfile.mkdtemp(prefix="duty-smoke-v22-")
    db_path = os.path.join(tmpdir, "test.db")
    proc = None
    try:
        # ---------- 阶段一：全新库 ----------
        proc, up = start_server(db_path)
        check("v2.2 服务启动（全新库）", up)
        if not up:
            return 1
        st, atok = login("admin", "admin123")
        check("管理员登录", st == 200)
        st, people = req("GET", "/api/people", token=atok)
        by_name = {p["name"]: p for p in people}
        gan, bi = by_name["JJJ"], by_name["KKK"]
        check("新库种子：JJJ=A组、KKK=B组",
              gan["grp"] == "A" and bi["grp"] == "B"
              and gan["grp_label"] == "A组" and bi["grp_label"] == "B组",
              f"JJJ={gan['grp']}/{gan['grp_label']}，KKK={bi['grp']}/{bi['grp_label']}")

        _, tok_gan = login("JJJ", "123456")
        _, tok_bi = login("KKK", "123456")
        persons = by_name

        def pick(token, name, pid_, day):
            return req("PUT", f"/api/plans/{pid_}/cell", token=token,
                       body={"person_id": persons[name]["id"], "day": day, "symbol": "X"})

        # ---------- 2026-11（先行组 A）：协管员窗口随组开放 ----------
        st, plan = req("POST", "/api/plans", token=atok,
                       body={"year": 2026, "month": 11, "quota": 9, "self_limit": 6})
        pid = plan["id"]
        req("PATCH", f"/api/plans/{pid}", token=atok, body={"phase_override": 2})
        # can_pick 需以成员身份查看（管理员视角恒为 True）
        st, detail = req("GET", f"/api/plans/{pid}", token=tok_bi)
        cp = {p["name"]: p["can_pick"] for p in detail["people"]}
        check("阶段2(先行组A)：JJJ(A组协管员)可选、KKK(B组协管员)未开放",
              cp["JJJ"] and not cp["KKK"],
              f"JJJ can_pick={cp['JJJ']}，KKK can_pick={cp['KKK']}")
        st, _ = pick(tok_gan, "JJJ", pid, 20)
        check("阶段2 JJJ选第20天成功", st == 200, f"status={st}")
        st, out = pick(tok_bi, "KKK", pid, 20)
        check("阶段2 KKK选班被窗口拒绝(403)", st == 403, f"status={st}")

        # ---------- 阶段全开：协管员每日上限（同日冲突拒绝） ----------
        req("PATCH", f"/api/plans/{pid}", token=atok, body={"phase_override": 3})
        st, out = pick(tok_bi, "KKK", pid, 20)
        check("KKK与JJJ同日(20日)选休被协管员上限拒绝(400)",
              st == 400 and "协管员" in out.get("detail", "")
              and "至少1名协管员在岗" in out.get("detail", ""),
              f"status={st}, detail={out.get('detail')}")
        st, _ = pick(tok_bi, "KKK", pid, 21)
        check("KKK改选第21天成功", st == 200, f"status={st}")
        st, detail = req("GET", f"/api/plans/{pid}", token=atok)
        dst = {s["day"]: s for s in detail["day_stats"]}
        check("第20/21天协管员在岗均为1且 assistant_full 标记正确",
              dst[20]["assistant_on_duty"] == 1 and dst[21]["assistant_on_duty"] == 1
              and dst[20]["assistant_full"] and dst[22]["assistant_on_duty"] == 2,
              f"20日={dst[20]['assistant_on_duty']}，21日={dst[21]['assistant_on_duty']}，"
              f"22日={dst[22]['assistant_on_duty']}")

        # ---------- 2026-12（先行组 B）：窗口随组对调 ----------
        st, plan2 = req("POST", "/api/plans", token=atok,
                        body={"year": 2026, "month": 12, "quota": 9, "self_limit": 6})
        pid2 = plan2["id"]
        req("PATCH", f"/api/plans/{pid2}", token=atok, body={"phase_override": 2})
        st, detail2 = req("GET", f"/api/plans/{pid2}", token=tok_gan)
        cp2 = {p["name"]: p["can_pick"] for p in detail2["people"]}
        check("阶段2(先行组B)：KKK(B组协管员)可选、JJJ未开放",
              cp2["KKK"] and not cp2["JJJ"],
              f"KKK can_pick={cp2['KKK']}，JJJ can_pick={cp2['JJJ']}")
        st, _ = pick(tok_bi, "KKK", pid2, 5)
        check("阶段2 KKK在12月计划选第5天成功", st == 200, f"status={st}")
        st, _ = pick(tok_gan, "JJJ", pid2, 5)
        check("阶段2 JJJ在12月计划选班被窗口拒绝(403)", st == 403, f"status={st}")

        # ---------- 空计划一键补满（草稿层）：三类在岗约束同时满足 ----------
        st, plan3 = req("POST", "/api/plans", token=atok,
                        body={"year": 2027, "month": 1, "quota": 9, "self_limit": 6})
        pid3 = plan3["id"]
        st, out = req("POST", f"/api/plans/{pid3}/autocomplete", token=atok)
        check("空计划一键补满执行成功", st == 200,
              f"status={st}, detail={out.get('detail') if st != 200 else ''}")
        st, detail3 = req("GET", f"/api/plans/{pid3}", token=atok)
        all9 = all(p["selected_leave"] == 9 for p in detail3["people"])
        cadre_ok = all(s["cadre_on_duty"] >= 5 for s in detail3["day_stats"])
        leader_ok = all(s["leader_on_duty"] >= 1 for s in detail3["day_stats"])
        asst_ok = all(s["assistant_on_duty"] >= 1 for s in detail3["day_stats"])
        check("补满后每人恰好休满 9 天", all9,
              "，".join(f"{p['name']}:{p['selected_leave']}" for p in detail3["people"]))
        check("补满后每日干部在岗>=5、科领导>=1、协管员>=1",
              cadre_ok and leader_ok and asst_ok,
              f"干部最低 {min(s['cadre_on_duty'] for s in detail3['day_stats'])}，"
              f"科领导最低 {min(s['leader_on_duty'] for s in detail3['day_stats'])}，"
              f"协管员最低 {min(s['assistant_on_duty'] for s in detail3['day_stats'])}")

        # ---------- Excel 导出含「协管员在岗人数」行 ----------
        st, content = req("GET", f"/api/plans/{pid3}/export.xlsx", token=atok, raw=True)
        xlsx_ok, xlsx_desc = False, ""
        if st == 200:
            xlsx_path = os.path.join(tmpdir, "export.xlsx")
            with open(xlsx_path, "wb") as f:
                f.write(content)
            from openpyxl import load_workbook
            ws = load_workbook(xlsx_path).active
            for row in ws.iter_rows():
                if row[0].value == "协管员在岗人数":
                    vals = [c.value for c in row[2:2 + 31]]
                    xlsx_ok = all(isinstance(v, int) and v >= 1 for v in vals)
                    xlsx_desc = f"该行 31 天在岗数最小值={min(vals)}"
                    break
            else:
                xlsx_desc = "未找到「协管员在岗人数」行"
        check("Excel 导出含协管员在岗人数统计行且每日>=1", st == 200 and xlsx_ok,
              f"status={st}，{xlsx_desc}")

        # ---------- 阶段二：旧库迁移（grp 未设置 -> 启动自动填充；已设置不覆盖） ----------
        stop_server(proc)
        proc = None
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE people SET grp=NULL WHERE kind='assistant'")
        conn.commit()
        before = dict(conn.execute(
            "SELECT name, grp FROM people WHERE kind='assistant'").fetchall())
        conn.close()
        check("迁移前置：已把两名协管员 grp 置空（模拟旧库）",
              before.get("JJJ") is None and before.get("KKK") is None,
              f"{before}")
        proc, up = start_server(db_path)
        check("迁移后服务重启成功", up)
        st, people = req("GET", "/api/people", token=atok)
        by_name = {p["name"]: p for p in people}
        check("启动迁移：JJJ自动填 A、KKK自动填 B",
              by_name["JJJ"]["grp"] == "A" and by_name["KKK"]["grp"] == "B",
              f"JJJ={by_name['JJJ']['grp']}，KKK={by_name['KKK']['grp']}")
        st, plans_now = req("GET", "/api/plans", token=atok)
        check("迁移重启后原有计划仍在（2026-11/12、2027-01 共 3 个）",
              st == 200 and len(plans_now) == 3, f"计划数={len(plans_now) if st == 200 else '?'}")
        # 管理员已改过的值不被迁移覆盖
        stop_server(proc)
        proc = None
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE people SET grp='B' WHERE name='JJJ'")
        conn.commit()
        conn.close()
        proc, up = start_server(db_path)
        st, atok2 = login("admin", "admin123")
        st, people = req("GET", "/api/people", token=atok2)
        by_name = {p["name"]: p for p in people}
        check("迁移不覆盖已设置值：JJJ保持 B（模拟管理员调整）",
              up and by_name["JJJ"]["grp"] == "B",
              f"JJJ={by_name['JJJ']['grp']}")

        # ---------- 阶段三：前端静态检查 ----------
        app_js = open(os.path.join(ROOT, "frontend", "app.js"), encoding="utf-8").read()
        style_css = open(os.path.join(ROOT, "frontend", "style.css"), encoding="utf-8").read()
        check("前端已移除主页「已选情况」卡片面板（无 status-list 渲染）",
              "status-list" not in app_js and "status-list" not in style_css)
        check("前端已移除成员页「已选情况」精简条（无 strip-list 渲染）",
              "strip-list" not in app_js and "strip-list" not in style_css)
        # v2.5 适配：用户要求删除网格下方全部图例（含姓名颜色说明行），
        # 故此处只断言姓名状态色类本身仍在（着色功能保留、仅说明文字删除）。
        check("网格含姓名状态色类（st-submitted/st-draft；姓名颜色图例行已按 v2.5 要求删除）",
              "st-submitted" in app_js and "st-draft" in app_js)
        check("网格统计含「协管员在岗人数」行",
              "协管员在岗人数" in app_js and "assistant_on_duty" in app_js)
        check("月历单元格高度已加大（td.cell height: 54px、字号 18px）",
              "height: 54px" in style_css and "font-size: 18px" in style_css)

        return 0 if all(r[1] for r in results) else 1
    finally:
        if proc is not None:
            stop_server(proc)
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v2.2 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write(f"- 环境：独立临时数据库（端口 {PORT}），计划 2026-11 / 2026-12 / 2027-01，Q=9，S=6\n")
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv2.2: {passed}/{len(results)} passed -> appended to {REPORT}")


if __name__ == "__main__":
    sys.exit(main())
