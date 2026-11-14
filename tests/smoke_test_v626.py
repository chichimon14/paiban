# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.26 冒烟测试（追加到 SMOKE_TEST.md 的 v6.26 章节）。

v6.26 变更（用户 2026-11-07 定稿）：早班 6 人模板整体换逻辑——
固定分组：A–D 固定查验岗（审图 2 人/班）、E/F 固定申报岗（1 人
/班）；时段改 07:00–07:45、07:45–08:30 各 45 分 + 其余 1 小时
一班至 14:30（共 8 班，取代旧 6 班×75 分）；挑查：8:30–10:30
（第 3、4 班）由 E/F 中不当申报者担任，其余时段由 A–D 兼顾；
第 1 班审图固定 A+B；**B 固定为值班科长位**：恰 6 人时默认带班
（最高职务者）恒持 B（贪心先钉、优化器 pinned_letters 保护不
换走），≥7 人仍按 v6.19（带班不占字母）。钉住只约束默认生成，
管理员手动改排/保存不拦截。格局公平（分钟）：A–D 审图各 225、
非窗口挑查+备勤各 225；E/F 申报各 225、窗口挑查各 60。

测试口径（临时库 + 临时端口 3026，复用 v6.19 已标定的在岗
配方）：A) 11-08 恰 6 人——默认带班AAA且 letters.B 即他、
模板 8 班结构与窗口/分组/第 1 班 A+B 逐项核对 + 格局分钟验算；
B) 11-12 恰 7 人——带班不占字母（v6.19 不变）；C) 11-12 再减
至 6 人且科长休——带班为BBB且 B 钉给她；D) 手动把 B 改给
他人保存仍 200（钉住不拦截手动）；S) 前后端静态。
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


def segment(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i)]


def main():
    tmpdb = os.path.join(tempfile.mkdtemp(prefix="duty-smoke-v626-"), "test.db")
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
        check("v6.26 服务启动", up)
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

        def ctx(date):
            return req("GET", f"/api/daily/context?date={date}", token=atok)

        def off(name, day):
            return req("PUT", f"/api/plans/{plan_id}/cell", token=atok,
                       body={"person_id": pid_of[name], "day": day, "symbol": "X"})

        # ---- A) 11-08 恰 6 人：B 钉带班 + 新模板结构 ----
        for n in ("FFF", "GGG", "III"):
            off(n, 8)
        st, c = ctx("2026-11-08")
        d = c["default"]
        on6 = {p["name"] for p in c["on_duty_cadre"]}
        check("A 11-08 在岗恰 6 人、variant=morning6、默认带班AAA且 letters.B 即AAA（B 固定带班）",
              len(on6) == 6 and c["variant"] == "morning6"
              and d["leader_id"] == pid_of["AAA"]
              and d["letters"].get("B") == pid_of["AAA"],
              str({k: name_of[v] for k, v in d["letters"].items()}))
        check("A 默认字母 A–F 恰为在岗 6 人全集、互不重复",
              set(d["letters"].keys()) == set("ABCDEF")
              and {name_of[v] for v in d["letters"].values()} == on6)

        tpl = c["template"]
        def post_letters(slot, post):
            return next(p["letters"] for p in slot["posts"] if p["post"] == post)
        check("A 模板为 8 班新时段（07:00–07:45/07:45–08:30/其后整点至 14:30）",
              len(tpl) == 8
              and [(s["start"], s["end"]) for s in tpl] == [
                  ("07:00", "07:45"), ("07:45", "08:30"), ("08:30", "09:30"),
                  ("09:30", "10:30"), ("10:30", "11:30"), ("11:30", "12:30"),
                  ("12:30", "13:30"), ("13:30", "14:30")],
              str([(s["start"], s["end"]) for s in tpl]))
        check("A 第 1 班审图固定 A+B；每班 6 字母恰各出现一次",
              post_letters(tpl[0], "审图查验岗") == ["A", "B"]
              and all(sorted(L for p in s["posts"] for L in p["letters"]) == list("ABCDEF")
                      for s in tpl))
        check("A 固定分组：审图字母恒 ⊆{A,B,C,D}、申报字母恒 ∈{E,F}；窗口（第 3、4 班）挑查为不当申报的 E/F、其余班挑查 ∈A–D",
              all(set(post_letters(s, "审图查验岗")) <= set("ABCD") for s in tpl)
              and all(post_letters(s, "申报岗")[0] in "EF" for s in tpl)
              and all(post_letters(tpl[i], "挑查岗") == [x for x in "EF"
                        if x != post_letters(tpl[i], "申报岗")[0]] for i in (2, 3))
              and all(post_letters(s, "挑查岗")[0] in "ABCD"
                      for j, s in enumerate(tpl) if j not in (2, 3)))

        def post_of(letter, slot):
            return next(p["post"] for p in slot["posts"] if letter in p["letters"])
        check("A 重岗不连排（v6.27 追加）：任何人上过审图/申报，下一班必为挑查或备勤；审图 (A+B)/(C+D) 与申报 F/E 逐班交替",
              all(not (post_of(L, tpl[i]) in ("审图查验岗", "申报岗")
                       and post_of(L, tpl[i + 1]) in ("审图查验岗", "申报岗"))
                  for L in "ABCDEF" for i in range(7))
              and all(post_letters(tpl[i], "审图查验岗") == (["A", "B"] if i % 2 == 0 else ["C", "D"])
                      for i in range(8))
              and all(post_letters(tpl[i], "申报岗") == (["F"] if i % 2 == 0 else ["E"])
                      for i in range(8)))

        def mins(letter, post):
            tot = 0
            for s in tpl:
                if letter in post_letters(s, post):
                    a = datetime.strptime(s["start"], "%H:%M")
                    b = datetime.strptime(s["end"], "%H:%M")
                    tot += (b - a).seconds // 60
            return tot
        check("A 格局公平验算：A–D 审图各 225 分；E/F 申报各 225 分、挑查各 60 分；A–D 挑查+备勤各 225 分",
              all(mins(L, "审图查验岗") == 225 for L in "ABCD")
              and all(mins(L, "申报岗") == 225 for L in "EF")
              and all(mins(L, "挑查岗") == 60 for L in "EF")
              and all(mins(L, "挑查岗") + mins(L, "备勤") == 225 for L in "ABCD"),
              str({L: (mins(L, "审图查验岗"), mins(L, "申报岗"), mins(L, "挑查岗"), mins(L, "备勤")) for L in "ABCDEF"}))

        # ---- B) 11-12 恰 7 人：带班不占字母（v6.19 不变） ----
        off("FFF", 12)
        off("III", 12)
        st, c = ctx("2026-11-12")
        d = c["default"]
        on7 = {p["name"] for p in c["on_duty_cadre"]}
        check("B 11-12 在岗 7 人：默认带班AAA不在字母内（v6.19 口径未被钉住逻辑影响）、A–F 为其余 6 人",
              len(on7) == 7 and d["leader_id"] == pid_of["AAA"]
              and pid_of["AAA"] not in d["letters"].values()
              and {name_of[v] for v in d["letters"].values()} == on7 - {"AAA"})

        # ---- C) 11-12 减至 6 人且科长休：带班BBB、B 钉给她 ----
        off("AAA", 12)
        st, c = ctx("2026-11-12")
        d = c["default"]
        on6b = {p["name"] for p in c["on_duty_cadre"]}
        check("C 11-12 在岗 6 人（科长休）：默认带班为BBB且 letters.B 即BBB",
              len(on6b) == 6 and "AAA" not in on6b
              and d["leader_id"] == pid_of["BBB"]
              and d["letters"].get("B") == pid_of["BBB"],
              str({k: name_of[v] for k, v in d["letters"].items()}))

        # ---- D) 手动改排不受钉住约束：B 换给他人仍可保存 ----
        st, c = ctx("2026-11-08")
        letters = dict(c["default"]["letters"])
        other = next(pid for L, pid in letters.items() if L == "A")
        letters["A"], letters["B"] = letters["B"], letters["A"]
        st, out = req("POST", "/api/daily/assignments", token=atok, body={
            "date": "2026-11-08", "leader_id": c["default"]["leader_id"],
            "letters": letters, "tax_ids": []})
        check("D 手动把 B 改给非带班者（与 A 互换）保存仍 200（钉住只约束默认生成）",
              st == 200, f"st={st}")
        st, dv = req("GET", "/api/daily/dayview?date=2026-11-08", token=atok)
        check("D 保存后 dayview 为已保存状态且 B 持有人为互换后的人（dayview letters 为姓名映射）",
              dv.get("status") == "ok"
              and (dv.get("letters") or {}).get("B") == name_of[other],
              str(dv.get("letters")))

        # ---- S) 静态 ----
        backend = open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read()
        js = open(os.path.join(ROOT, "frontend", "app.js"), encoding="utf-8").read()
        check("S app.js 带 v6.27 版本标记；后端含钉住逻辑与新模板说明、前端含 B 固定带班提示",
              "/* duty-roster v6.31 */" in js
              and "pinned_letters" in backend and "B 固定值班科长位" in backend
              and "B 岗固定为带班" in js)
        return 0 if all(r[1] for r in results) else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


ADAPT_NOTES = """- 适配说明（v6.26/v6.27 引起的旧套件改动）：
  - 全部旧套件：版本标记断言字面量随版本提升（仅字面量）；
  - smoke_test_v616.py：EXPECT6 逐格期望两度换格局（v6.26 固定
    分组 8 班 → v6.27 重岗不连排交替格局）、模板/预览/dayview
    段数 6→8、第 1 班次在岗集终为 {A,B,D,F}、首班次与 B 岗
    时间轴期望按现行模板重算（检查名已注明）；
  - smoke_test_v617.py：模板/dayview 段数 6→8、首班次挑查/备勤
    期望与 F（申报组）/D（查验组）时间轴序列按现行模板重算；
  - smoke_test_v69.py：早班 preview 行数 6→8、首班次映射终为
    申报=F/挑查=D/备勤=C+E、context 模板段数 8；
  - smoke_test_v60.py：次日默认优化落点随第 1 时段集合与审图对
    变化而变（C/F 持有人互换），期望值已更新并注明；
  - 本套件（v6.26 编写、v6.27 续用）：新增「重岗不连排」模板级
    断言（审图/申报不得连班、骨架逐班交替），余检查口径不变。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.26 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：临时 SQLite 库 + 临时端口 3026 起真实服务走 HTTP 接口\n")
            f.write("- v6.26：早班 6 人模板换固定分组新格局（8 班时段、窗口挑查归 E/F）+ B 固定值班科长位（恰 6 人默认带班恒持 B）。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.26: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
