# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.25 冒烟测试（追加到 SMOKE_TEST.md 的 v6.25 章节）。

v6.25 变更（用户 2026-11-03 定）：早班 5 人模板换用优化格局
MORNING_SLOTS_V2（每人两个轻岗在 5 班周期内拆开不相邻 → 最多连上
2 班必轮到挑查/备勤；全天总量不变：审图 4、申报 2、挑查 2、备勤 2），
**自 2026-11-05 起生效**；此前日期仍用旧 MORNING_SLOTS——用户口径
「5 号之前的已经生成了，就不改了」。落地方式：后端按日期分界取
模板（_morning_slots_for / MORNING_V2_FROM=2026-11-05），默认生成
（default_daily_assignment）、管理员 context、成员 dayview 与岗位
显示 mine 的已保存排班解析全部按当日日期取模板，故旧日期的已保存
排班显示原样、新日期按新模板；6 人早班/晚班模板与变体名不变
（早班 5 人变体名仍为 "morning"），前端无改动（仅版本标记提升）。

测试口径（临时库 + 临时端口 3031）：11 月计划，11-04 与 11-06
（均为早班）各置 4 名干部休假、留 5 名干部在岗：
  A) context 11-04 模板 == 旧格局逐格（首段审图 B/C、申报 D、
     挑查 E、备勤 A）；
  B) context 11-06 模板 == 新格局逐格（首段审图 B/E、申报 C、
     挑查 D、备勤 A），且逐字母验算：连上（审图+申报）最多 2 班、
     全天计数审图 4/申报 2/挑查 2/备勤 2；
  C) 两日以同一字母→人员映射保存排班：dayview 11-04 首段按旧
     模板解析、11-06 按新模板解析；BBB（A 岗）mine 时间轴
     两日的岗位序列分别符合新旧模板；
  D) 11-05 为晚班、context shift=evening（分界日当天无早班）；
  E) 11-08 全员在岗（≥6 干部）仍走 morning6 变体、模板含 F；
  S) 静态断言：版本标记 v6.25、后端含 MORNING_SLOTS_V2 /
     MORNING_V2_FROM / _morning_slots_for。
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
PORT = 3031
BASE = f"http://127.0.0.1:{PORT}"
REPORT = os.path.join(ROOT, "SMOKE_TEST.md")

results = []

OLD_PAT = [
    (["B", "C"], "D", "E", "A"),
    (["D", "E"], "A", "C", "B"),
    (["A", "B"], "E", "D", "C"),
    (["C", "E"], "B", "A", "D"),
    (["A", "D"], "C", "B", "E"),
]
NEW_PAT = [
    (["B", "E"], "C", "D", "A"),
    (["A", "C"], "D", "E", "B"),
    (["B", "D"], "E", "A", "C"),
    (["C", "E"], "A", "B", "D"),
    (["A", "D"], "B", "C", "E"),
]


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


def pat_grid(template):
    """context 的 template（原始模板）-> [(审图对, 申报, 挑查, 备勤)]×10。"""
    out = []
    for slot in template:
        by = {p["post"]: list(p["letters"]) for p in slot["posts"]}
        out.append((by["审图查验岗"], by["申报岗"][0],
                    by["挑查岗"][0], by["备勤"][0]))
    return out


def expect_grid(pat5):
    return [pat5[i % 5] for i in range(10)]


def main():
    tmpdb = os.path.join(tempfile.mkdtemp(prefix="duty-smoke-v625-"), "test.db")
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
        check("v6.25 服务启动", up)
        if not up:
            return 1

        atok = login("admin", "admin123")
        st, people = req("GET", "/api/people", token=atok)
        pid_of = {p["name"]: p["id"] for p in people}

        st, plan = req("POST", "/api/plans", token=atok,
                       body={"year": 2026, "month": 11, "quota": 9, "self_limit": 6})
        plan_id = plan["id"]
        req("PATCH", f"/api/plans/{plan_id}", token=atok, body={"phase_override": 3})
        # 11-04 与 11-06 各留 5 名干部在岗（AAA/BBB/CCC/GGG/EEE）
        for day in (4, 6):
            for n in ("DDD", "FFF", "HHH", "III"):
                req("PUT", f"/api/plans/{plan_id}/cell", token=atok,
                    body={"person_id": pid_of[n], "day": day, "symbol": "X"})

        # ---- A) 11-04（分界前）旧模板 ----
        st, c4 = req("GET", "/api/daily/context?date=2026-11-04", token=atok)
        g4 = pat_grid(c4["template"])
        check("A context 11-04：variant=morning、模板逐格 == 旧格局（首段审图 B/C、申报 D、挑查 E、备勤 A）",
              st == 200 and c4["variant"] == "morning" and g4 == expect_grid(OLD_PAT),
              str(g4[:1]))

        # ---- B) 11-06（分界后）新模板 + 连上验算 ----
        st, c6 = req("GET", "/api/daily/context?date=2026-11-06", token=atok)
        g6 = pat_grid(c6["template"])
        ok_grid = st == 200 and c6["variant"] == "morning" and g6 == expect_grid(NEW_PAT)
        # 逐字母：H=审图/申报、L=挑查/备勤；最大连续 H 与全天计数
        prop_ok = True
        for L in "ABCDE":
            seq = []
            for (shen, shenbao, tiao, bei) in g6:
                if L in shen:
                    seq.append("审图查验岗")
                elif L == shenbao:
                    seq.append("申报岗")
                elif L == tiao:
                    seq.append("挑查岗")
                else:
                    seq.append("备勤")
            run = mx = 0
            for r in seq:
                run = run + 1 if r in ("审图查验岗", "申报岗") else 0
                mx = max(mx, run)
            cnt = {k: seq.count(k) for k in
                   ("审图查验岗", "申报岗", "挑查岗", "备勤")}
            prop_ok &= (mx <= 2 and cnt == {"审图查验岗": 4, "申报岗": 2,
                                            "挑查岗": 2, "备勤": 2})
        check("B context 11-06：模板逐格 == 新格局（首段审图 B/E、申报 C、挑查 D、备勤 A），且每人最多连上 2 班、全天审图4/申报2/挑查2/备勤2",
              ok_grid and prop_ok, str(g6[:1]))

        # ---- C) 同一映射保存两日：解析按各自日期模板 ----
        letters = {"A": pid_of["BBB"], "B": pid_of["AAA"],
                   "C": pid_of["CCC"], "D": pid_of["GGG"],
                   "E": pid_of["EEE"]}
        for dstr in ("2026-11-04", "2026-11-06"):
            st, out = req("POST", "/api/daily/assignments", token=atok,
                          body={"date": dstr, "leader_id": pid_of["AAA"],
                                "letters": letters})
            assert st == 200, (dstr, st, out)

        def dayview_slot1(dstr):
            st, dv = req("GET", f"/api/daily/dayview?date={dstr}", token=atok)
            posts = dv["preview"][0]["posts"]
            return {p["name"]: [x["name"] for x in p["people"]] for p in posts}

        dv4 = dayview_slot1("2026-11-04")
        check("C dayview 11-04 已保存排班按旧模板解析：首段审图=AAA+CCC、申报=GGG、挑查=EEE、备勤=BBB",
              dv4.get("审图查验岗") == ["AAA", "CCC"]
              and dv4.get("申报岗") == ["GGG"]
              and dv4.get("挑查岗") == ["EEE"]
              and dv4.get("备勤") == ["BBB"], str(dv4))
        dv6 = dayview_slot1("2026-11-06")
        check("C dayview 11-06 已保存排班按新模板解析：首段审图=AAA+EEE、申报=CCC、挑查=GGG、备勤=BBB",
              dv6.get("审图查验岗") == ["AAA", "EEE"]
              and dv6.get("申报岗") == ["CCC"]
              and dv6.get("挑查岗") == ["GGG"]
              and dv6.get("备勤") == ["BBB"], str(dv6))

        ltok = login("BBB", "123456")
        st, m4 = req("GET", "/api/daily/mine?date=2026-11-04", token=ltok)
        seq4 = [e["post"] for e in m4["result"].get("timeline") or []]
        st, m6 = req("GET", "/api/daily/mine?date=2026-11-06", token=ltok)
        seq6 = [e["post"] for e in m6["result"].get("timeline") or []]
        check("C mine BBB（A 岗）时间轴：11-04 旧序 备勤/申报/审图/挑查/审图…；11-06 新序 备勤/审图/挑查/申报/审图…",
              seq4[:5] == ["备勤", "申报岗", "审图查验岗", "挑查岗", "审图查验岗"]
              and seq6[:5] == ["备勤", "审图查验岗", "挑查岗", "申报岗", "审图查验岗"],
              f"{seq4[:5]} vs {seq6[:5]}")

        # ---- D) 分界日 11-05 是晚班 ----
        st, c5 = req("GET", "/api/daily/context?date=2026-11-05", token=atok)
        check("D context 11-05：shift=evening（分界日当天为晚班、无早班模板切换问题）",
              st == 200 and c5["shift"] == "evening", str(c5.get("shift")))

        # ---- E) 6 人早班不受影响 ----
        st, c8 = req("GET", "/api/daily/context?date=2026-11-08", token=atok)
        letters8 = set()
        for slot in c8["template"]:
            for p in slot["posts"]:
                letters8.update(p["letters"])
        check("E context 11-08（全员在岗）：variant=morning6、模板含 F 字母",
              st == 200 and c8["variant"] == "morning6" and "F" in letters8,
              str(c8.get("variant")))
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
    check("S app.js 带 v6.25 版本标记", "/* duty-roster v6.31 */" in js)
    check("S 后端含新模板与分界：MORNING_SLOTS_V2 / MORNING_V2_FROM = date(2026, 11, 5) / _morning_slots_for",
          "MORNING_SLOTS_V2" in backend
          and "MORNING_V2_FROM = date(2026, 11, 5)" in backend
          and "_morning_slots_for" in backend)
    check("S 旧模板 MORNING_SLOTS 与旧格局首行仍在（分界前日期继续使用）",
          '_M_PATTERNS = [' in backend and '(["B", "C"], "D", "E", "A")' in backend)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v6.25 引起的旧套件改动）：全部旧套件版本标记断言
  字面量 v6.24→v6.25；另有两处行为断言因场景日在分界后、随新模板
  调整（均已在对应文件内注明）：smoke_test_v60.py 的 A 岗时间轴
  断言（11-08：审图同岗改钉 07:45–08:30 与 C 岗CCC、08:30–09:15
  改为挑查岗）；smoke_test_v61.py 的 S2 场景（测试侧 morning 审图
  对改用新模板对、重造两日历史使纯贪心把两名科领导排到 B/E 同对
  位得分 2、修正交换 A/B 达暴力极大 4，人员班与无班替口径不变）。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.25 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：临时数据库 + 临时服务端口 3031（API 行为）+ 纯静态检查（前端/后端）\n")
            f.write("- v6.25：早班 5 人模板自 2026-11-05 起换用优化格局（最多连上 2 班 "
                    "必轮到挑查/备勤），此前日期仍用旧模板、已生成排班不变；按日期分界取模板。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.25: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
