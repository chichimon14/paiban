# -*- coding: utf-8 -*-
"""示例科室排班系统 v2 冒烟测试（追加到 SMOKE_TEST.md 的 v2 章节）。

覆盖 v2 新增/变更：
- 科长组别为 'chief'、显示标签“科长”，任何接口载荷不出现 grp=null 的科长；
- 成员保存草稿 -> 提交（快照锁定、submitted_at 记录）-> 提交后本人改格被拒；
- 管理员调取数据只拉已提交者的选休，未提交者的草稿不进最终表；
- 无人选班时最终表一键补满：全员恰好 Q 天且每日干部在岗>=5、科领导>=1；
- 管理员保存最终表 + 提交发布 -> 首页展示最终表、成员被锁定；
- 修改密码：旧密码错误被拒、正确修改后新密码可登录；
- 历史数据列出该计划（源数据保留一年）。
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
PORT = 3001
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
    return (st, out.get("token")) if st == 200 else (st, None)


def main():
    tmpdb = os.path.join(tempfile.mkdtemp(prefix="duty-smoke-v2-"), "test.db")
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
        check("v2 服务启动", up)
        if not up:
            return 1

        st, atok = login("admin", "admin123")
        check("管理员登录", st == 200)
        st, people = req("GET", "/api/people", token=atok)
        by_name = {p["name"]: p for p in people}
        persons = by_name

        # ---- 变更1：科长组别
        chief = by_name["AAA"]
        check("科长 grp='chief' 且标签为“科长”",
              chief["grp"] == "chief" and chief["grp_label"] == "科长",
              f"grp={chief['grp']}, label={chief['grp_label']}")
        grp_null_bad = [p["name"] for p in people
                        if p["grp"] is None and p["kind"] != "assistant"]
        labels_bad = [p["name"] for p in people
                      if not p["grp_label"] or p["grp_label"] == "null"]
        check("干部无人 grp=null、所有人组别标签不为空/null",
              not grp_null_bad and not labels_bad,
              f"grp为空干部={grp_null_bad}, 标签异常={labels_bad}")

        # ---- 建计划并全开阶段
        st, plan = req("POST", "/api/plans", token=atok,
                       body={"year": 2026, "month": 11, "quota": 9, "self_limit": 6})
        pid = plan["id"]
        req("PATCH", f"/api/plans/{pid}", token=atok, body={"phase_override": 3})
        st, detail = req("GET", f"/api/plans/{pid}", token=atok)
        chief_in_detail = [p for p in detail["people"] if p["name"] == "AAA"][0]
        check("计划详情中科长 grp_label=科长", chief_in_detail["grp_label"] == "科长")

        tokens = {}
        for name in by_name:
            _, tokens[name] = login(name, "123456")

        def pick(name, day, symbol="X"):
            return req("PUT", f"/api/plans/{pid}/cell", token=tokens[name],
                       body={"person_id": persons[name]["id"], "day": day, "symbol": symbol})

        # ---- 变更3：FFF选2天并提交；GGG只存草稿不提交
        check("FFF保存草稿2天", pick("FFF", 3)[0] == 200 and pick("FFF", 4)[0] == 200)
        check("GGG保存草稿1天(不提交)", pick("GGG", 5)[0] == 200)
        st, sub = req("POST", f"/api/plans/{pid}/submit", token=tokens["FFF"])
        check("FFF提交成功且返回 submitted_at",
              st == 200 and bool(sub.get("submitted_at")) and sub.get("days") == 2,
              f"status={st}, at={sub.get('submitted_at')}, days={sub.get('days')}")
        st, out = pick("FFF", 6)
        check("提交后本人再改格被拒(403)", st == 403, f"status={st}, detail={out.get('detail')}")
        st, detail = req("GET", f"/api/plans/{pid}", token=atok)
        lx = [p for p in detail["people"] if p["name"] == "FFF"][0]
        check("详情中FFF状态=已提交且有提交时间",
              lx["submission_status"] == "submitted" and bool(lx["submitted_at"]))

        # ---- 管理员调取数据：只拉已提交者
        st, out = req("POST", f"/api/plans/{pid}/pull-source", token=atok)
        check("管理员调取数据成功", st == 200 and out.get("pulled", {}).get("members") == 1,
              f"status={st}, pulled={out.get('pulled')}")
        fgrid = out["final_grid"]
        lx_final = fgrid.get(str(persons["FFF"]["id"]), {})
        sjf_final = fgrid.get(str(persons["GGG"]["id"]), {})
        check("最终表含FFF已提交的2天", set(lx_final.keys()) == {"3", "4"},
              f"FFF最终表天数={sorted(lx_final.keys())}")
        check("未提交者(GGG)草稿不进最终表", len(sjf_final) == 0,
              f"GGG最终表格数={len(sjf_final)}")

        # ---- 最终表补满（在只有FFF2天的基础上补全员到9天）
        st, out = req("POST", f"/api/plans/{pid}/final/autocomplete", token=atok)
        check("最终表一键补满成功", st == 200,
              f"status={st}, filled={out.get('autocomplete', {}).get('filled') if st == 200 else out.get('detail')}")
        if st == 200:
            all9 = all(p["final_leave"] == 9 for p in out["people"])
            cadre_ok = all(s["cadre_on_duty"] >= 5 for s in out["final_day_stats"])
            leader_ok = all(s["leader_on_duty"] >= 1 for s in out["final_day_stats"])
            check("补满后最终表每人恰好9天", all9,
                  "，".join(f"{p['name']}:{p['final_leave']}" for p in out["people"]))
            check("最终表每日干部在岗>=5", cadre_ok,
                  f"最低 {min(s['cadre_on_duty'] for s in out['final_day_stats'])}")
            check("最终表每日科领导在岗>=1", leader_ok,
                  f"最低 {min(s['leader_on_duty'] for s in out['final_day_stats'])}")

        # ---- 保存 + 提交发布
        st, out = req("POST", f"/api/plans/{pid}/final/save", token=atok)
        check("管理员保存最终表(带时间戳)", st == 200 and bool(out.get("final_saved_at")))
        st, _ = req("POST", f"/api/plans/{pid}/publish", token=atok)
        st, detail = req("GET", f"/api/plans/{pid}", token=tokens["FFF"])
        check("提交发布后首页展示口径=最终表",
              st == 200 and detail["plan"]["published"] and detail["display_kind"] == "final",
              f"published={detail['plan']['published']}, display={detail['display_kind']}")
        st, _ = pick("FFF", 7)
        check("发布后成员改格被拒(403)", st == 403, f"status={st}")

        # ---- 变更2：无人选班也能补满（新计划 2026-12，不调取、不选班，直接最终表补满）
        st, plan2 = req("POST", "/api/plans", token=atok,
                        body={"year": 2026, "month": 12, "quota": 9, "self_limit": 6})
        pid2 = plan2["id"]
        st, out = req("POST", f"/api/plans/{pid2}/final/autocomplete", token=atok)
        ok = st == 200
        detail2 = out if ok else {}
        check("无人选班时一键补满可执行", ok,
              f"status={st}, detail={out.get('detail') if not ok else ''}")
        if ok:
            all9 = all(p["final_leave"] == 9 for p in detail2["people"])
            cadre_ok = all(s["cadre_on_duty"] >= 5 for s in detail2["final_day_stats"])
            leader_ok = all(s["leader_on_duty"] >= 1 for s in detail2["final_day_stats"])
            check("空表补满后每人恰好9天(含科长)", all9,
                  "，".join(f"{p['name']}:{p['final_leave']}" for p in detail2["people"]))
            check("空表补满每日干部在岗>=5、科领导>=1", cadre_ok and leader_ok,
                  f"干部最低 {min(s['cadre_on_duty'] for s in detail2['final_day_stats'])}, "
                  f"科领导最低 {min(s['leader_on_duty'] for s in detail2['final_day_stats'])}")

        # ---- 修改密码（用III账号）
        st, out = req("POST", "/api/change-password", token=tokens["III"],
                      body={"old_password": "wrong-old", "new_password": "newpass456"})
        check("改密时旧密码错误被拒(400)", st == 400, f"status={st}")
        st, out = req("POST", "/api/change-password", token=tokens["III"],
                      body={"old_password": "123456", "new_password": "newpass456"})
        check("正确旧密码改密成功", st == 200, f"status={st}")
        st, _ = login("III", "newpass456")
        check("新密码可登录", st == 200, f"status={st}")
        st, _ = login("III", "123456")
        check("旧密码已失效(401)", st == 401, f"status={st}")

        # ---- 退回 -> 重提生成新版本（源数据版本保留）
        req("POST", f"/api/plans/{pid}/unpublish", token=atok)
        st, _ = req("POST", f"/api/plans/{pid}/return/{persons['FFF']['id']}", token=atok)
        check("管理员退回FFF提交", st == 200, f"status={st}")
        st, sub2 = req("POST", f"/api/plans/{pid}/submit", token=tokens["FFF"])
        st, subs = req("GET", f"/api/plans/{pid}/submissions", token=atok)
        lx_versions = [s for s in subs if s["person_name"] == "FFF"] if st == 200 else []
        check("退回后重提生成新版本(旧版本保留)",
              len(lx_versions) == 2, f"FFF提交版本数={len(lx_versions)}")

        # ---- 历史数据（保留一年清单）
        st, hist = req("GET", "/api/history", token=atok)
        hit = [h for h in hist if h["id"] == pid] if st == 200 else []
        check("历史数据列出 2026-11 计划",
              st == 200 and len(hit) == 1 and hit[0]["submitted_members"] >= 1,
              f"status={st}, 命中={len(hit)}")

        return 0 if all(r[1] for r in results) else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v2 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write(f"- 环境：独立临时数据库（端口 {PORT}），计划 2026-11 / 2026-12，Q=9，S=6\n")
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv2: {passed}/{len(results)} passed -> appended to {REPORT}")


if __name__ == "__main__":
    sys.exit(main())
