# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.28 冒烟测试。

v6.28 变更（用户 2026-11-11 定）：「生成排班」页新增「刷新人数」
按钮——月排班表改动某天人数后（实例：11 号晚班已按 7 人在岗保存
了 6 人方案 A–F，其后月表把AAA、GGG改为轮休、在岗干部变
5 人），页面点「刷新人数」即按最新排班表重新采集：后端
/api/daily/context?refresh=1 按最新在岗干部数重判方案变体、
表单改用按最新人数生成的默认排班；刷新不落库，确认后点
「保存排班」才替换旧的已保存版本。

测试口径（临时库 + 临时端口 3028，日期 2026-11-11 晚班）：
A) 先造 7 人在岗、保存晚班 6 人方案（A–F，F 为AAA）；
B) 月表再把AAA、GGG改轮休 → 在岗干部 5 人；普通 context
   仍随已保存排班呈 evening6（旧行为/回归对照）；
C) refresh=1：variant=evening、letter_order=A–E、在岗 5 人、
   default 字母恰为在岗 5 人全集且带班为CCC（唯一在岗科领导）、
   saved 仍在（刷新不删不改已保存）；
D) 用刷新后的 default 保存 → 200，再查普通 context saved 为
   A–E 五字母、variant=evening；dayview 已保存且字母为 5 人；
S) 前后端静态：按钮「刷新人数」/ refresh=1 / 后端 refresh 口径。
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
PORT = 3028
BASE = f"http://127.0.0.1:{PORT}"
REPORT = os.path.join(ROOT, "SMOKE_TEST.md")

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), "-", name, ("| " + str(detail) if detail else ""))


def req(method, path, token="", body=None):
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
    return out.get("token", "")


def main():
    tmpdb = os.path.join(tempfile.mkdtemp(prefix="duty-smoke-v628-"), "test.db")
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
        check("v6.28 服务启动", up)
        if not up:
            return 1

        atok = login("admin", "admin123")
        st, people = req("GET", "/api/people", token=atok)
        pid_of = {p["name"]: p["id"] for p in people}
        name_of = {v: k for k, v in pid_of.items()}

        st, plan = req("POST", "/api/plans", token=atok,
                       body={"year": 2026, "month": 11, "quota": 9, "self_limit": 6})
        plan_id = plan["id"]
        req("PATCH", f"/api/plans/{plan_id}", token=atok, body={"phase_override": 3})

        def ctx(date, refresh=False):
            q = "&refresh=1" if refresh else ""
            return req("GET", f"/api/daily/context?date={date}{q}", token=atok)

        def off(name, day):
            return req("PUT", f"/api/plans/{plan_id}/cell", token=atok,
                       body={"person_id": pid_of[name], "day": day, "symbol": "X"})

        # ---- A) 11-11 晚班先造 7 人在岗并保存 6 人方案 ----
        off("BBB", 11)
        off("FFF", 11)
        st, c = ctx("2026-11-11")
        on7 = {p["name"] for p in c["on_duty_cadre"]}
        d = c["default"]
        check("A 初始在岗干部 7 人、variant=evening6、默认字母 A–F",
              len(on7) == 7 and c["variant"] == "evening6"
              and set(d["letters"].keys()) == set("ABCDEF"),
              f"on={sorted(on7)} variant={c.get('variant')}")
        letters6 = dict(d["letters"])
        # 保证 F 是其后会被改休的人之一，便于复现截图里 F 变未定的情形：
        # 7 人在岗时默认带班（AAA）不占字母，手动把 F 改给他（保存
        # 校验允许带班兼字母岗，线上已保存的 11 号正是带班兼 C 岗）。
        letters6["F"] = pid_of["AAA"]
        st, out = req("POST", "/api/daily/assignments", token=atok, body={
            "date": "2026-11-11", "leader_id": d["leader_id"], "letters": letters6})
        check("A 保存晚班 6 人方案成功（F=AAA）",
              st == 200 and out.get("saved", {}).get("letters", {}).get("F") == pid_of["AAA"],
              f"st={st}")

        # ---- B) 月表改动：AAA、GGG 11 号改轮休 → 在岗干部 5 人 ----
        off("AAA", 11)
        off("GGG", 11)
        st, c = ctx("2026-11-11")
        on5 = {p["name"] for p in c["on_duty_cadre"]}
        check("B 月表改后在岗干部 5 人（CCC/DDD/EEE/HHH/III）",
              on5 == {"CCC", "DDD", "EEE", "HHH", "III"},
              f"on={sorted(on5)}")
        check("B 普通 context 仍随已保存排班呈 evening6、saved 含 F=AAA（旧行为对照，正是用户截图的问题）",
              c["variant"] == "evening6"
              and (c.get("saved") or {}).get("letters", {}).get("F") == pid_of["AAA"]
              and c.get("refresh") is False,
              f"variant={c.get('variant')}")

        # ---- C) 刷新人数：按最新在岗数重判 ----
        st, c = ctx("2026-11-11", refresh=True)
        d = c["default"]
        check("C refresh=1 后 variant=evening、letter_order=A–E、refresh 标记为真",
              c["variant"] == "evening" and c["letter_order"] == list("ABCDE")
              and c.get("refresh") is True,
              f"variant={c.get('variant')} order={c.get('letter_order')}")
        check("C refresh 后 default 字母恰为在岗 5 人全集、带班为CCC（唯一在岗科领导）",
              set(d["letters"].keys()) == set("ABCDE")
              and {name_of[v] for v in d["letters"].values()} == on5
              and d["leader_id"] == pid_of["CCC"],
              str({k: name_of[v] for k, v in d["letters"].items()}))
        check("C refresh 不删不改已保存：saved 仍为原 6 字母（含 F）",
              (c.get("saved") or {}).get("letters", {}).get("F") == pid_of["AAA"]
              and len((c.get("saved") or {}).get("letters", {})) == 6)
        check("C refresh 预览随新模板：preview 时段数与晚班 5 人模板一致（8 段）且不含AAA",
              len(c.get("preview") or []) == 8
              and all("AAA" != pp["name"]
                      for slot in c["preview"] for post in slot["posts"]
                      for pp in post["people"]),
              f"slots={len(c.get('preview') or [])}")

        # ---- D) 用刷新结果保存 → 替换为 5 人方案 ----
        st, out = req("POST", "/api/daily/assignments", token=atok, body={
            "date": "2026-11-11", "leader_id": d["leader_id"], "letters": d["letters"]})
        check("D 保存刷新后的 5 人方案成功", st == 200, f"st={st} out={out}")
        st, c = ctx("2026-11-11")
        check("D 保存后普通 context：saved 为 A–E 五字母、variant=evening",
              set((c.get("saved") or {}).get("letters", {}).keys()) == set("ABCDE")
              and c["variant"] == "evening",
              f"variant={c.get('variant')}")
        st, dv = req("GET", "/api/daily/dayview?date=2026-11-11", token=atok)
        check("D dayview 已保存且字母为 5 人（成员端看到新人数方案）",
              dv.get("status") == "ok"
              and set((dv.get("letters") or {}).keys()) == set("ABCDE"),
              str(dv.get("letters")))

        # ---- S) 静态 ----
        backend = open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read()
        js = open(os.path.join(ROOT, "frontend", "app.js"), encoding="utf-8").read()
        check("S app.js 带 v6.28 版本标记；生成排班页含「刷新人数」按钮与 refresh=1 调用；后端含 refresh 重判口径",
              "/* duty-roster v6.31 */" in js
              and 'id="dailyRefreshBtn">刷新人数<' in js
              and "dailyState.refreshPending = true" in js and "refresh=1" in js
              and "刷新人数" in backend and "cadre_count=len(cadre)" in backend)
        return 0 if all(r[1] for r in results) else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.28 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：临时 SQLite 库 + 临时端口 3028 起真实服务走 HTTP 接口\n")
            f.write("- v6.28：「生成排班」页新增「刷新人数」按钮，context?refresh=1 按最新排班表在岗人数重判方案，刷新不落库、保存才生效。\n")
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.28: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
