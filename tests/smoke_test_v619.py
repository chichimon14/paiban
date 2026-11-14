# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.19 冒烟测试（追加到 SMOKE_TEST.md 的 v6.19 章节）。

v6.19 变更（用户 2026-11-02 定）：早班在岗 7 人时仍套用 6 人模板，
且**值班科长不参与排班**。落地口径：在岗干部 ≥7 人的早班日，
默认排班的带班（当天在岗最高职务者）只任带班、不占 A–F 任一
字母岗，六个字母在其余在岗干部中按全员历史均衡分配；默认优化
器的班替候选同样不含值班科长（不会被优化换回字母岗）。在岗恰
6 人时值班科长仍参与字母排班（否则只剩 5 人、排不满 6 岗）；
在岗 ≥8 人时同口径（值班科长除外，其余按历史均衡选 6 人）。
同此前各条默认生成规则（第 1 班次科领导、混编搭配）一样，本
规则只约束默认排班生成：管理员手动把值班科长排入字母岗仍可
保存（保存校验不拦截）。晚班、5 人早班均不受影响。
前端：管理员页在「早班 6 人方案」徽标旁对在岗 ≥7 人的日子加
一行提示「在岗 7 人及以上：值班科长只任带班、不参与字母排班
（默认排班口径，可手动调整）」。

测试口径（临时库 + 临时端口 3025）：恰 7 人在岗（带班为科长 →
其余 6 人恰排满 A–F）、8 人在岗（带班除外选 6）、恰 6 人在岗
（带班仍参与、全员排满）、科长休假时值班科长为副科长（该副
科长不占字母）、仅科长一名科领导在岗的 7 人日（优化不得把
科长换回字母岗）、手动保存含值班科长的排班仍 200、前端静态。
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
PORT = 3025
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


def segment(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i)]


def main():
    tmpdb = os.path.join(tempfile.mkdtemp(prefix="duty-smoke-v619-"), "test.db")
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
        check("v6.19 服务启动", up)
        if not up:
            return 1

        atok = login("admin", "admin123")
        st, people = req("GET", "/api/people", token=atok)
        pid_of = {p["name"]: p["id"] for p in people}
        name_of = {v: k for k, v in pid_of.items()}

        def L(**kw):
            return {k: pid_of[v] for k, v in kw.items()}

        st, plan = req("POST", "/api/plans", token=atok,
                       body={"year": 2026, "month": 11, "quota": 9, "self_limit": 6})
        plan_id = plan["id"]
        req("PATCH", f"/api/plans/{plan_id}", token=atok, body={"phase_override": 3})

        def ctx(date):
            return req("GET", f"/api/daily/context?date={date}", token=atok)

        def off(name, day):
            return req("PUT", f"/api/plans/{plan_id}/cell", token=atok,
                       body={"person_id": pid_of[name], "day": day, "symbol": "X"})

        def names(letters):
            return {name_of[v] for v in letters.values()}

        # ---- A) 恰 7 人在岗（11-12 早班）：带班科长不占字母 ----
        off("FFF", 12)
        off("III", 12)
        st, c = ctx("2026-11-12")
        d = c["default"]
        on7 = {p["name"] for p in c["on_duty_cadre"]}
        check("A 11-12 在岗恰 7 人、variant=morning6、默认带班为科长AAA",
              len(on7) == 7 and c["variant"] == "morning6"
              and d["leader_id"] == pid_of["AAA"], str(on7))
        check("A 默认字母 A–F 恰为其余 6 人全集、值班科长AAA不在字母岗内",
              set(d["letters"].keys()) == set("ABCDEF")
              and names(d["letters"]) == on7 - {"AAA"},
              str({k: name_of[v] for k, v in d["letters"].items()}))

        # ---- B) 8 人在岗（11-14 早班）：带班除外、其余选 6 ----
        off("III", 14)
        st, c = ctx("2026-11-14")
        d = c["default"]
        on8 = {p["name"] for p in c["on_duty_cadre"]}
        check("B 11-14 在岗 8 人：默认带班AAA不占字母、A–F 为其余 7 人中 6 人互不重复",
              len(on8) == 8 and d["leader_id"] == pid_of["AAA"]
              and "AAA" not in names(d["letters"])
              and len(names(d["letters"])) == 6
              and names(d["letters"]) <= on8 - {"AAA"},
              str({k: name_of[v] for k, v in d["letters"].items()}))

        # ---- C) 恰 6 人在岗（11-08 早班）：带班仍参与、全员排满 ----
        for n in ("FFF", "GGG", "III"):
            off(n, 8)
        st, c = ctx("2026-11-08")
        d = c["default"]
        on6 = {p["name"] for p in c["on_duty_cadre"]}
        check("C 11-08 在岗恰 6 人：默认 A–F 为在岗全集（值班科长AAA仍参与字母排班）",
              len(on6) == 6 and names(d["letters"]) == on6
              and "AAA" in names(d["letters"]),
              str({k: name_of[v] for k, v in d["letters"].items()}))

        # ---- D) 科长休假的 7 人日（11-16 早班）：值班科长为BBB ----
        off("AAA", 16)
        off("FFF", 16)
        st, c = ctx("2026-11-16")
        d = c["default"]
        on7b = {p["name"] for p in c["on_duty_cadre"]}
        check("D 11-16 在岗 7 人、默认带班为副科长BBB且她不占字母、A–F 为其余 6 人全集",
              len(on7b) == 7 and d["leader_id"] == pid_of["BBB"]
              and names(d["letters"]) == on7b - {"BBB"},
              str({k: name_of[v] for k, v in d["letters"].items()}))

        # ---- E) 仅科长一名科领导在岗的 7 人日（11-18 早班）：优化不得换回 ----
        off("BBB", 18)
        off("CCC", 18)
        st, c = ctx("2026-11-18")
        d = c["default"]
        check("E 11-18 在岗科领导仅AAA：默认带班为他且字母岗内无任何科领导（优化班替未把他换回）",
              [p["name"] for p in c["on_duty_leaders"]] == ["AAA"]
              and d["leader_id"] == pid_of["AAA"]
              and not (names(d["letters"]) & {"AAA", "BBB", "CCC"})
              and len(names(d["letters"])) == 6,
              str({k: name_of[v] for k, v in d["letters"].items()}))

        # ---- F) 手动保存含值班科长的字母排班仍可（默认口径、不拦截） ----
        st, out = req("POST", "/api/daily/assignments", token=atok,
                      body={"date": "2026-11-12", "leader_id": pid_of["AAA"],
                            "letters": L(A="AAA", B="BBB", C="CCC",
                                         D="DDD", E="EEE", F="GGG")})
        check("F 管理员手动把值班科长排入 A 岗保存 → 200（本规则只约束默认排班）",
              st == 200, str(st))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    # ---- S) 静态断言 ----
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()
    backend = open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read()
    check("S app.js 带 v6.19 版本标记", "/* duty-roster v6.31 */" in js)
    check("S 后端默认排班含值班科长排除逻辑（morning6 + len(cadre) >= 7 时 pool 剔除 leader_id、优化器收 pool）",
          'if variant == "morning6" and leader_id is not None and len(cadre) >= 7:' in backend
          and 'pool = [p for p in cadre if p["id"] != leader_id]' in backend
          and "_optimize_daily_default(shift, letters, pool, leaders, history," in backend)
    check("S 前端管理员页含 ≥7 人提示文案（值班科长只任带班、不参与字母排班）且门控为 variant morning6 + 在岗 ≥7",
          "值班科长只任带班、不参与字母排班" in js
          and "ctx.on_duty_cadre.length >= 7" in js)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v6.19 引起的旧套件改动）：
  - 全部 43 个旧套件：版本标记断言字面量由 v6.18 提升为 v6.19
    （仅字面量）；
  - smoke_test_v60.py 两处确切人选断言（检查名已注明 v6.19
    适配）：11-02 零历史默认由 ADDD/BBBB/CCCC/DAAA/
    EEEE/FFFF 改为 AEEE/BCCC/CDDD/DBBB/EFFF/
    FGGG；11-04 默认由 AAAA/BGGG/CHHH/DIII/
    EEEE/FBBB 改为 ABBB/BGGG/CHHH/DIII/
    EEEE/FCCC——两次变化均仅因值班科长AAA按新规则退出
    字母池、余者顺位与优化结果随之调整；
  - smoke_test_v62.py：优化器调用字面量第三参 cadre→pool
    （检查名已注明 v6.19 适配）。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.19 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：临时数据库 + 临时服务端口 3025（API 行为）+ 纯静态检查（前端/后端）\n")
            f.write("- v6.19：早班在岗 ≥7 人仍套 6 人模板，但值班科长（默认带班）不参与"
                    "字母排班——只任带班、不占 A–F；恰 6 人时仍参与；只约束默认排班，"
                    "手动改排不拦截。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.19: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
