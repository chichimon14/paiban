# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.2 冒烟测试（追加到 SMOKE_TEST.md 的 v6.2 章节）。

v6.2 变更（用户 2026-11-01 定，仅后端 backend/main.py 的默认生成；
前端仅版本标记 v6.1→v6.2）：
  默认排班优化由 v6.1 的「搭配修正」扩展为单一确定性优化器
  _optimize_daily_default，最大化词典序目标（高 → 低）：
    1) slot1_leader_working：第 1 个时间段必须有科领导在岗
       （早班第 1 时段在岗字母 = B/C/D/E，A 为备勤位；晚班 =
       A/B/C/D，E 在第 1 时段无岗位；字母集由模板首段推导，
       见 _slot1_letter_sets）；
    2) slot1_leader_shen：第 1 时段尽量有科领导在审图查验岗
       （早班 B/C、晚班 A/B）；
    3) mixed_pair_score：v6.1 混编得分（口径不变）。
  同目标值时取公平性代价最小者（代价口径与 v6.1 相同：字母变化
  者新字母的历史次数之和、班替离岗者计 0），再同取枚举顺序最先。
  候选动作与 v6.1 相同：字母互换（10 对）+ 班替（换入恒为在岗科
  领导），班替仅在「班内无科领导」（为满足目标 1）或 v6.1 情形
  （班内科领导 <2 且在岗科领导 ≥2）时枚举；最多 6 轮。当天无科
  领导在岗时整段跳过。目标 1、2 已满足时退化为 v6.1 搭配修正。
  管理员手动改排与保存校验不受影响（保存可违反第 1 时段规则，
  本文件末有断言）。

测试口径（临时库 + 临时端口 3012；场景均经独立脚本按实现预演
确定性结果，断言钉确切人选）：
  M1 早班：仅AAA一名科领导在岗、零历史 → 纯贪心把他排在 A
     （第 1 时段备勤位、目标 (0,0,2)）→ 优化以字母互换把他移到
     B（审图），目标 (1,1,2)，人员班不变、带班仍为AAA。
  M2 早班：仅BBB一名科领导在岗；造四日早班历史使纯贪心把她
     排在 D（第 1 时段申报岗：在岗但非审图、目标 (1,0,2)）→
     优化以字母互换把她移到 B（审图），目标 (1,1,2)，人员班
     不变；并做暴力校验（全部字母排列 + 允许的班替中，服务端
     默认的目标值 = 词典序极大、其公平代价 = 极大值候选中的
     最小代价）。
  E1 晚班：BBB/CCC在岗；造两日晚班历史使纯贪心把两名科领导
     排在 C/D（第 1 时段申报岗、目标 (1,0,0)）→ 优化把CCC移到
     A（审图），两组皆混编，目标 (1,1,2)；同做暴力校验。
  E2 晚班：仅AAA一名科领导在岗；累计七日晚班历史使纯贪心
     把他排除在五人班外（目标 (0,0,0)）→ 优化以班替把他换入
     A（第 1 时段审图岗），目标 (1,1,1)。
  S) 静态断言：后端含 _slot1_letter_sets / _daily_objective /
     _optimize_daily_default 且 default_daily_assignment 调用之；
     app.js 带 v6.2 标记。
"""
import itertools
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
PORT = 3012
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


# ---- 测试侧独立复刻：纯贪心 + 词典序目标 + 暴力最优（不依赖服务端实现） ----
PRIORITY = {"morning": ["A", "E", "B", "C", "D"], "evening": ["A", "B", "C", "D", "E"]}
PAIRS = {"evening": [("A", "B"), ("C", "D")],
         "morning": [("B", "C"), ("D", "E"), ("A", "B"), ("C", "E"), ("A", "D")]}
SLOT1 = {"morning": ({"B", "C", "D", "E"}, {"B", "C"}),
         "evening": ({"A", "B", "C", "D"}, {"A", "B"})}
LEADER_NAMES = {"AAA", "BBB", "CCC"}


def greedy_local(ctx):
    hist = ctx["history_stats"]
    remaining = list(ctx["on_duty_cadre"])
    letters = {}
    for letter in PRIORITY[ctx["shift"]]:
        if not remaining:
            break

        def key(p):
            h = hist.get(str(p["id"]), {})
            return (h.get(letter, 0), h.get("total", 0), p["sort_order"])

        pick = min(remaining, key=key)
        letters[letter] = pick["name"]
        remaining.remove(pick)
    return letters


def tuple_local(shift, letters_by_name):
    working, shen = SLOT1[shift]
    c1 = any(letters_by_name.get(L) in LEADER_NAMES for L in working)
    c2 = any(letters_by_name.get(L) in LEADER_NAMES for L in shen)
    c3 = sum(1 for a, b in PAIRS[shift]
             if (letters_by_name[a] in LEADER_NAMES)
             != (letters_by_name[b] in LEADER_NAMES))
    return (1 if c1 else 0, 1 if c2 else 0, c3)


def brute_best(ctx, greedy):
    """暴力枚举：贪心人员班的全部字母排列 + 允许的单步班替（换入
    在岗未入班科领导），返回 (词典序最大目标, 该目标下的最小公平
    代价)。代价以贪心结果为基准：某字母换人时计新持有人该字母的
    历史次数（班替离班者不计），与服务端单步代价口径一致。"""
    shift = ctx["shift"]
    names = ctx["names"]
    hist = {names[pid]: h for pid, h in ctx["history_stats"].items()}
    crew = list(greedy.values())
    on_duty = [p["name"] for p in ctx["on_duty_cadre"]]
    bench_leaders = [n for n in on_duty
                     if n in LEADER_NAMES and n not in crew]

    def damage(cand):
        return sum(hist.get(cand[L], {}).get(L, 0)
                   for L in cand if cand[L] != greedy[L])

    cands = []
    for perm in itertools.permutations(crew):
        cands.append(dict(zip("ABCDE", perm)))
    for L in greedy:
        for bp in bench_leaders:
            trial = dict(greedy)
            trial[L] = bp
            cands.append(trial)
    best_t = max(tuple_local(shift, c) for c in cands)
    best_d = min(damage(c) for c in cands if tuple_local(shift, c) == best_t)
    return best_t, best_d, damage


def main():
    tmpdb = os.path.join(tempfile.mkdtemp(prefix="duty-smoke-v62-"), "test.db")
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
        check("v6.2 服务启动", up)
        if not up:
            return 1

        atok = login("admin", "admin123")
        st, people = req("GET", "/api/people", token=atok)
        P = {p["name"]: p for p in people}
        pid_of = {n: P[n]["id"] for n in P}
        name_of = {v: k for k, v in pid_of.items()}

        st, plan = req("POST", "/api/plans", token=atok,
                       body={"year": 2026, "month": 11, "quota": 9, "self_limit": 6})
        plan_id = plan["id"]
        req("PATCH", f"/api/plans/{plan_id}", token=atok, body={"phase_override": 3})
        check("建 2026 年 11 月计划成功", st == 200 and plan_id is not None)

        def ctx(date_s):
            return req("GET", f"/api/daily/context?date={date_s}", token=atok)

        def save_raw(body):
            return req("POST", "/api/daily/assignments", token=atok, body=body)

        def off(name, day):
            return req("PUT", f"/api/plans/{plan_id}/cell", token=atok,
                       body={"person_id": pid_of[name], "day": day, "symbol": "X"})

        def L(**kw):
            return {k: pid_of[v] for k, v in kw.items()}

        def by_name(letters):
            return {k: name_of[v] for k, v in letters.items()}

        # ---- M1) 早班：唯一科领导被纯贪心排在 A（第 1 时段备勤位） ----
        # v6.16 适配：本场景验证 5 人早班优化器，须让当日 在岗恰 5 人
        # 走 5 人模板（≥6 人改走 6 人方案，见 v6.16 套件）：除两名副
        # 科长外，另置EEE/HHH 30 日轮休，在岗恰 5 人。
        off("BBB", 30)
        off("CCC", 30)
        off("EEE", 30)
        off("HHH", 30)
        st, c = ctx("2026-11-30")
        check("M1 前置：11-30（早班） 在岗科领导仅AAA、在岗干部恰 5 人（v6.16 适配）",
              c["shift"] == "morning"
              and [p["name"] for p in c["on_duty_leaders"]] == ["AAA"]
              and len(c["on_duty_cadre"]) == 5,
              str([p["name"] for p in c["on_duty_leaders"]]))
        g = greedy_local(c)
        check("M1 前置：纯贪心把AAA排在 A（第 1 时段备勤位），目标 (0,0,2)（v6.16 适配：在岗五人班随之变更）",
              g == {"A": "AAA", "E": "DDD", "B": "FFF", "C": "GGG", "D": "III"}
              and tuple_local("morning", g) == (0, 0, 2), str(g))
        d = by_name(c["default"]["letters"])
        check("M1 优化：AAA移到 B（第 1 时段审图查验岗），目标 (1,1,2)，人员班不变、带班为AAA（v6.16 适配人选）",
              d == {"A": "FFF", "B": "AAA", "C": "GGG", "D": "III", "E": "DDD"}
              and tuple_local("morning", d) == (1, 1, 2)
              and set(d.values()) == set(g.values())
              and c["default"]["leader_id"] == pid_of["AAA"], str(d))

        # ---- M2) 早班：唯一科领导被纯贪心排在 D（申报，非审图） ----
        saves_m2 = [
            ("2026-11-02", L(A="BBB", E="DDD", B="EEE", C="FFF", D="GGG")),
            ("2026-11-04", L(A="DDD", E="BBB", B="FFF", C="EEE", D="GGG")),
            ("2026-11-06", L(A="DDD", E="EEE", B="BBB", C="FFF", D="GGG")),
            ("2026-11-08", L(A="DDD", E="EEE", B="FFF", C="BBB", D="GGG")),
        ]
        ok = True
        for ds, letters in saves_m2:
            st, _ = save_raw({"date": ds, "leader_id": pid_of["AAA"],
                              "letters": letters})
            ok = ok and st == 200
        check("M2 造历史：四日早班保存成功", ok)
        off("AAA", 10)
        off("CCC", 10)
        # v6.16 适配：同 M1——另置FFF/EEE 10 日轮休，使在岗恰为
        # 原纯贪心五人班、走 5 人模板（纯贪心与优化期望人选不变）。
        off("FFF", 10)
        off("EEE", 10)
        st, c = ctx("2026-11-10")
        check("M2 前置：11-10 在岗科领导仅BBB、在岗干部恰 5 人（v6.16 适配）",
              [p["name"] for p in c["on_duty_leaders"]] == ["BBB"]
              and len(c["on_duty_cadre"]) == 5,
              str([p["name"] for p in c["on_duty_leaders"]]))
        g = greedy_local(c)
        check("M2 前置：纯贪心把BBB排在 D（第 1 时段申报岗：在岗非审图），目标 (1,0,2)",
              g == {"A": "HHH", "E": "III", "B": "DDD", "C": "GGG", "D": "BBB"}
              and tuple_local("morning", g) == (1, 0, 2), str(g))
        d = by_name(c["default"]["letters"])
        check("M2 优化：BBB移到 B（审图），目标 (1,1,2)，人员班不变（纯字母互换）",
              d == {"A": "HHH", "B": "BBB", "C": "GGG", "D": "DDD", "E": "III"}
              and tuple_local("morning", d) == (1, 1, 2)
              and set(d.values()) == set(g.values()), str(d))
        best_t, best_d, dmg_fn = brute_best(c, g)
        check("M2 暴力校验：默认目标 = 词典序极大 (1,1,2)，且其公平代价 = 极大值候选中的最小代价",
              tuple_local("morning", d) == best_t == (1, 1, 2)
              and dmg_fn(d) == best_d, f"best={best_t}/{best_d} got dmg={dmg_fn(d)}")

        # ---- E1) 晚班：两名科领导被纯贪心排在 C/D（第 1 时段申报） ----
        st, _ = save_raw({"date": "2026-11-01", "leader_id": pid_of["AAA"],
                          "letters": L(A="BBB", B="CCC", C="DDD", D="EEE", E="III")})
        ok1 = st == 200
        st, _ = save_raw({"date": "2026-11-03", "leader_id": pid_of["AAA"],
                          "letters": L(A="CCC", B="BBB", C="DDD", D="EEE", E="III")})
        check("E1 造历史：两日晚班保存成功", ok1 and st == 200)
        for n in ("AAA", "FFF", "GGG", "HHH"):
            off(n, 5)
        st, c = ctx("2026-11-05")
        check("E1 前置：11-05（晚班）在岗科领导为BBB+CCC、在岗干部恰 5 人",
              c["shift"] == "evening"
              and {p["name"] for p in c["on_duty_leaders"]} == {"BBB", "CCC"}
              and len(c["on_duty_cadre"]) == 5,
              str([p["name"] for p in c["on_duty_cadre"]]))
        g = greedy_local(c)
        check("E1 前置：纯贪心把两名科领导排在 C/D（第 1 时段申报岗），目标 (1,0,0)",
              g == {"A": "DDD", "B": "EEE", "C": "BBB", "D": "CCC", "E": "III"}
              and tuple_local("evening", g) == (1, 0, 0), str(g))
        d = by_name(c["default"]["letters"])
        check("E1 优化：CCC移到 A（审图），两组皆混编，目标 (1,1,2)",
              d == {"A": "CCC", "B": "EEE", "C": "BBB", "D": "DDD", "E": "III"}
              and tuple_local("evening", d) == (1, 1, 2), str(d))
        best_t, best_d, dmg_fn = brute_best(c, g)
        check("E1 暴力校验：默认目标 = 词典序极大 (1,1,2)，且其公平代价 = 极大值候选中的最小代价",
              tuple_local("evening", d) == best_t == (1, 1, 2)
              and dmg_fn(d) == best_d, f"best={best_t}/{best_d} got dmg={dmg_fn(d)}")

        # ---- E2) 晚班：唯一科领导被纯贪心排除在五人班外 → 班替换入 ----
        saves_e2 = [
            ("2026-11-07", L(A="AAA", B="BBB", C="CCC", D="III", E="DDD")),
            ("2026-11-09", L(A="BBB", B="AAA", C="CCC", D="III", E="EEE")),
            ("2026-11-13", L(A="BBB", B="CCC", C="AAA", D="III", E="FFF")),
            ("2026-11-15", L(A="BBB", B="CCC", C="GGG", D="AAA", E="HHH")),
            ("2026-11-17", L(A="BBB", B="CCC", C="III", D="EEE", E="AAA")),
        ]
        ok = True
        for ds, letters in saves_e2:
            st, _ = save_raw({"date": ds, "leader_id": pid_of["AAA"],
                              "letters": letters})
            ok = ok and st == 200
        check("E2 造历史：五日晚班保存成功（累计七日）", ok)
        off("BBB", 11)
        off("CCC", 11)
        off("III", 11)
        st, c = ctx("2026-11-11")
        check("E2 前置：11-11 在岗科领导仅AAA",
              [p["name"] for p in c["on_duty_leaders"]] == ["AAA"],
              str([p["name"] for p in c["on_duty_leaders"]]))
        g = greedy_local(c)
        check("E2 前置（v6.20 适配）：11-11 在岗恰 6 人走晚班 6 人方案（variant=evening6）；旧口径纯贪心会把AAA排除在五人班外、目标 (0,0,0)——该班替场景已被新结构取代",
              c["variant"] == "evening6"
              and g == {"A": "FFF", "B": "GGG", "C": "HHH", "D": "DDD", "E": "EEE"}
              and "AAA" not in g.values()
              and tuple_local("evening", g) == (0, 0, 0), str(g))
        d = by_name(c["default"]["letters"])
        check("E2 默认（v6.20 适配）：晚班 6 人固定岗——唯一科领导AAA任带班兼第一组组长 A（第 1 时段审图岗），B GGG/C FFF/D HHH/E DDD/F EEE",
              d == {"A": "AAA", "B": "GGG", "C": "FFF", "D": "HHH", "E": "DDD", "F": "EEE"}
              and c["default"]["leader_id"] == pid_of["AAA"], str(d))

        # ---- 手动保存不受第 1 时段规则约束（优化仅作用于默认生成） ----
        st, out = save_raw({"date": "2026-11-12", "leader_id": pid_of["AAA"],
                            "letters": L(A="AAA", B="DDD", C="EEE", D="FFF", E="GGG")})
        check("手动保存：科领导排在 A（早班第 1 时段备勤位）仍可保存（规则仅约束默认生成）",
              st == 200 and out["saved"]["letters"]["A"] == pid_of["AAA"], str(st))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    # ---- 静态断言 ----
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()
    backend = open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read()

    check("app.js 带 v6.3 版本标记", "/* duty-roster v6.31 */" in js)
    check("后端含第 1 时段词典序优化实现（_slot1_letter_sets / _daily_objective / _optimize_daily_default）",
          "def _slot1_letter_sets" in backend and "def _daily_objective" in backend
          and "def _optimize_daily_default" in backend)
    check("default_daily_assignment 调用 _optimize_daily_default（且不再调用 _repair_pairing；v6.16 适配：调用新增 template/letter_order 关键字参数；v6.19 适配：第三参改为 pool——在岗 ≥7 人早班时剔除值班科长后的候选池）",
          "letters = _optimize_daily_default(shift, letters, pool, leaders, history," in backend
          and "def _repair_pairing" not in backend)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v6.2 引起的旧套件改动，均已在对应测试文件处注明）：
  - 全部套件（v25–v61）：仅版本标记断言由 v6.1 提升为 v6.2，其余未动；
  - smoke_test_v61.py：静态断言中的后端函数名由 _repair_pairing 更新为
    _optimize_daily_default（v6.2 扩展更名）；S1–S4 行为断言经复核全部
    保留——四场景的贪心结果目标 1、2 均已满足或不可达更优，优化退化为
    v6.1 搭配修正、人选与 v6.1 完全一致；
  - smoke_test_v60.py：A/B/C 三处默认人选断言经复核全部保留（A 早班
    目标 (1,1,4) 已最优；B 节班替结果同为 (1,1,4) 且BBB@B 仍为
    最低代价最先序；C 节优化经 (D,E) 互换达 (1,1,2)、A 仍为CCC）。
  - smoke_test_v27.py：符号总数断言 18 → 19——此为 Y「支援」符号
    补丁（随 11 月定稿导入上线）的遗留适配、非 v6.2 行为变更；
    v6.1 全量回归时 Y 尚未加入，故本次顺带修正并注明。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.2 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：临时数据库 + 临时服务端口 3012（API 行为）+ 纯静态检查（前端）\n")
            f.write("- v6.2：默认排班优化升级为词典序目标（第 1 时段科领导在岗 "
                    "> 第 1 时段科领导在审图查验岗 > v6.1 混编得分），"
                    "_optimize_daily_default 统一贪心后优化（字母互换 + "
                    "必要时班替、公平代价次之）；手动改排与保存校验不变。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.2: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
