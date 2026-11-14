# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.20 冒烟测试（追加到 SMOKE_TEST.md 的 v6.20 章节）。

v6.20 变更（用户 2026-11-02 定，含其 11 月 3 日晚班实例）：
晚班在岗干部 ≥6 人时改用 6 人固定岗结构（新变体 evening6）：
审图查验岗 4 人分两组（第一组 A+B、第二组 C+D，按现有晚班 8 个
时段逐段交替）、申报岗 2 人（E/F 按时段交替），各岗只管自己、
不再交叉轮转顶岗（5 人晚班的 A–D 兼申报、E 顶申报等安排只存
在于 5 人变体）。默认人选新口径：带班不再默认取最高职务者，
改为三位科领导按历史晚班带班次数**轮流**（最少者优先、同数
名单顺序）；带班兼审图第一组组长（恰 6 人时）；在岗 ≥7 人时
带班不参与字母排班（只任带班，同早班 v6.19）；审图尽量
「一科领导带一干部」（两组组长优先科领导、组员干部按历史
均衡），第三位科领导去申报岗 F 位。在岗 ≤5 人晚班完全不变。
保存校验放宽：晚班同样接受 A–F 六字母。

测试口径（临时库 + 临时端口 3026）：11-03 晚班在岗恰 6 人
（同用户实例名单）零历史默认结构（带班为名单序轮流首位AAA
兼 A、两组混编、申报 E 干部/F 科领导）→ 保存后 11-05 晚班
（在岗 6 人）带班轮换到带班次数最少者 → 11-07 晚班在岗 7 人
带班不占字母且为轮流人选 → 11-09 晚班在岗 5 人仍旧 A–E 与
最高职务带班 → 晚班保存 A–F 200 / A–E 200 → 模板与变体字段
→ 前端静态（导图双申报人名、晚班 6 人方案徽标与说明）。
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
PORT = 3026
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
    tmpdb = os.path.join(tempfile.mkdtemp(prefix="duty-smoke-v620-"), "test.db")
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
        check("v6.20 服务启动", up)
        if not up:
            return 1

        atok = login("admin", "admin123")
        st, people = req("GET", "/api/people", token=atok)
        pid_of = {p["name"]: p["id"] for p in people}
        name_of = {v: k for k, v in pid_of.items()}
        LEADERS = {"AAA", "BBB", "CCC"}

        st, plan = req("POST", "/api/plans", token=atok,
                       body={"year": 2026, "month": 11, "quota": 9, "self_limit": 6})
        plan_id = plan["id"]
        req("PATCH", f"/api/plans/{plan_id}", token=atok, body={"phase_override": 3})

        def ctx(date):
            return req("GET", f"/api/daily/context?date={date}", token=atok)

        def off(name, day):
            return req("PUT", f"/api/plans/{plan_id}/cell", token=atok,
                       body={"person_id": pid_of[name], "day": day, "symbol": "X"})

        def save_default(date):
            st, c = ctx(date)
            d = c["default"]
            return req("POST", "/api/daily/assignments", token=atok,
                       body={"date": date, "leader_id": d["leader_id"],
                             "letters": d["letters"]})

        # ---- A) 11-03 晚班在岗恰 6 人（同用户实例名单）：零历史默认 ----
        for n in ("FFF", "HHH", "III"):
            off(n, 3)
        off("KKK", 3)
        st, c = ctx("2026-11-03")
        d = c["default"]
        nm = {k: name_of[v] for k, v in d["letters"].items()}
        check("A 11-03 晚班在岗 6 人、variant=evening6、模板 8 段（首段审图 A+B/申报 E、次段审图 C+D/申报 F）",
              c["shift"] == "evening" and c["variant"] == "evening6"
              and len(c["template"]) == 8
              and [p["letters"] for p in c["template"][0]["posts"]] == [["A", "B"], ["E"]]
              and [p["letters"] for p in c["template"][1]["posts"]] == [["C", "D"], ["F"]],
              str(c["variant"]))
        check("A 零历史带班轮流首位=AAA（名单序）且兼第一组组长 A；两组均混编（组长科领导+组员干部）",
              d["leader_id"] == pid_of["AAA"] and nm["A"] == "AAA"
              and nm["C"] in LEADERS and nm["B"] not in LEADERS
              and nm["D"] not in LEADERS, str(nm))
        check("A 申报岗 E 为干部、F 为第三位科领导（CCC/BBB之一）；退税岗仅JJJ",
              nm["E"] not in LEADERS and nm["F"] in LEADERS
              and d["tax_ids"] == [pid_of["JJJ"]], str(nm))

        # ---- B) 保存后下一晚班（11-05，在岗 6 人）带班轮换 ----
        st, out = save_default("2026-11-03")
        check("B 保存 11-03 晚班 6 人排班 → 200 且 A–F 落库", st == 200
              and set(out["saved"]["letters"].keys()) == set("ABCDEF"), str(st))
        for n in ("FFF", "HHH", "III"):
            off(n, 5)
        st, c = ctx("2026-11-05")
        d = c["default"]
        check("B 11-05 晚班带班轮换：AAA已带班 1 次 → 默认带班为带班次数最少者（BBB，名单序优先于CCC）",
              c["variant"] == "evening6"
              and d["leader_id"] == pid_of["BBB"]
              and name_of[d["letters"]["A"]] == "BBB",
              str(name_of.get(d["leader_id"])))

        # ---- C) 11-07 晚班在岗 7 人：带班不参与字母排班 ----
        st, out = save_default("2026-11-05")
        check("C 保存 11-05 默认排班 → 200（为轮流计数）", st == 200, str(st))
        off("FFF", 7)
        off("III", 7)
        st, c = ctx("2026-11-07")
        d = c["default"]
        nm = {k: name_of[v] for k, v in d["letters"].items()}
        check("C 11-07 在岗 7 人：带班轮换到CCC（AAA/BBB各带班 1 次）且CCC不占任何字母、A–F 为其余 6 人",
              len(c["on_duty_cadre"]) == 7 and c["variant"] == "evening6"
              and d["leader_id"] == pid_of["CCC"]
              and "CCC" not in nm.values()
              and set(nm.values()) == {p["name"] for p in c["on_duty_cadre"]} - {"CCC"},
              str(nm))

        # ---- D) 11-09 晚班在岗 5 人：完全不变 ----
        for n in ("FFF", "GGG", "HHH", "III"):
            off(n, 9)
        st, c = ctx("2026-11-09")
        d = c["default"]
        check("D 11-09 在岗 5 人晚班 variant=evening（A–E）、默认带班仍最高职务者AAA（轮流不适用于 5 人晚班）",
              c["variant"] == "evening" and set(d["letters"].keys()) == set("ABCDE")
              and d["leader_id"] == pid_of["AAA"], str(c["variant"]))

        # ---- E) 晚班保存校验：A–E 仍可（历史兼容）、乱集 400 ----
        st, out = req("POST", "/api/daily/assignments", token=atok,
                      body={"date": "2026-11-09", "leader_id": pid_of["AAA"],
                            "letters": {"A": pid_of["AAA"], "B": pid_of["BBB"],
                                        "C": pid_of["CCC"], "D": pid_of["DDD"],
                                        "E": pid_of["EEE"]}})
        check("E 5 人晚班保存 A–E → 200", st == 200, str(st))
        st, out = req("POST", "/api/daily/assignments", token=atok,
                      body={"date": "2026-11-09", "leader_id": pid_of["AAA"],
                            "letters": {"A": pid_of["AAA"], "B": pid_of["BBB"],
                                        "C": pid_of["CCC"], "D": pid_of["DDD"]}})
        check("E 字母不全（缺 E）保存 → 400", st == 400, str(st))
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
    check("S app.js 带 v6.20 版本标记", "/* duty-roster v6.31 */" in js)
    check("S 后端含 EVENING6_SLOTS 与 _default_evening6/_daily_leader_counts、变体含 evening6",
          "EVENING6_SLOTS" in backend and "_default_evening6" in backend
          and "_daily_leader_counts" in backend and '"evening6"' in backend)
    check("S 前端晚班 6 人方案徽标与固定岗说明在位（导图断言 v6.22 适配：晚班导图已改时段表格式、原 E+F 双人名文案行废止，双人名改由时段表各行呈现，见 v6.22 套件）",
          "晚班 6 人方案（A–F）" in js and "不再交叉顶岗" in js)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v6.20 引起的旧套件改动）：
  - 全部 44 个旧套件：版本标记断言字面量由 v6.19 提升为 v6.20
    （仅字面量）；
  - smoke_test_v60.py：11-03 零历史晚班默认断言改晚班 6 人结构
    确切人选（带班AAA不占字母、A BBB/B DDD/C CCC/
    D EEE/E FFF/F GGG），模板首段断言改 6 人模板段式；
  - smoke_test_v61.py：S1/S3/S4 三个晚班优化场景全部收窄到
    在岗恰 5 人（置轮休）以继续验证 5 人晚班的贪心+搭配修正；
    S1 预期人选不变；S3 由「班替」改「互换」验证（5 人晚班全员
    在班、班替不可达），E1 造历史的 E 位因 S1 轮休改排AAA，
    前置/结果人选按收窄后复算值更新；S4 断言机制不变（默认=
    复刻贪心）；
  - smoke_test_v62.py：E2（原晚班班替场景）11-11 在岗恰 6 人
    改走新结构，前置改述旧贪心会被排除的事实、结果断言改晚班
    6 人固定岗确切人选（AAA带班兼 A）；
  - smoke_test_v616.py：E「晚班保存 A–F → 400」翻转为 200；
  - smoke_test_v64.py：D 默认排班字母数 5→6；
  - smoke_test_v69.py：D 晚班 preview 首段申报断言由 C/D 两段
    改为固定申报岗 E。
  以上检查名均已注明 v6.20 适配。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.20 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：临时数据库 + 临时服务端口 3026（API 行为）+ 纯静态检查（前端/后端）\n")
            f.write("- v6.20：晚班 ≥6 人改固定岗 6 人结构（审图两组+申报 2 人、不交叉顶岗），"
                    "带班三位科领导按历史晚班带班次数轮流、≥7 人时带班不参与字母排班；"
                    "5 人晚班不变。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.20: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
