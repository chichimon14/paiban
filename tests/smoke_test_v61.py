# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.1 冒烟测试（追加到 SMOKE_TEST.md 的 v6.1 章节）。

v6.1 变更（用户 2026-11-01 定，后端 backend/main.py + 前端 app.js）：
  A) 班次改由日期推导，取消人工选班次：全科早晚班逐日轮替，锚点
     2026-11-02 = 早班、11-03 = 晚班，向前向后无限交替（11-01 = 晚班，
     与用户图4 示例吻合；跨月不重置）。后端 SHIFT_ANCHOR +
     shift_for_date()；GET /api/daily/context 只收 date（旧 shift 查询
     参数忽略）；POST /api/daily/assignments 服务端按日期推导（客户端
     传错 shift 不拒绝、按推导值落库）；GET /api/daily/mine 改单班次
     结构 {shift, shift_label, result}（原 shifts{morning,evening} 废除）。
  B) 默认排班新增「一科领导带一干部」搭配修正（软约束，仅作用于
     默认生成、不限制管理员改排）：审图查验岗的配对集合——晚班
     (A,B)/(C,D) 固定，早班为模板周期内不同时段配对 (B,C)/(D,E)/
     (A,B)/(C,E)/(A,D)；混编得分 = 配对中「一科领导 + 一干部」的对数。
     在岗科领导 ≥2 时，在历史均衡贪心之后做确定性修正：候选为
     ①字母互换（全部 10 对）、②仅当班内科领导 <2 时的班替（在岗未
     入班科领导换下班内非科领导）；按 (得分最高, 公平损失最小——
     损失 = 换岗者新岗位的历史次数之和、班替离班者计 0, 枚举顺序
     最早）取优，循环至多 5 次。在岗科领导 <2 时完全不修正（默认
     与 v6.0 纯贪心一致）。
  C) 前端：管理员页删除早/晚班分段切换，改为日期旁只读徽标 +
     一行说明「班次按日轮替：11月2日早班、3日晚班，逐日交替」；
     岗位显示页改为单班次卡片（日期标题带班次名）；生成图片逻辑
     不变（用所选日期的推导班次）。

测试口径（临时库 + 临时端口 3011）：
  - 奇偶：11-01 晚 / 11-02 早 / 11-03 晚 / 11-30 早（锚点 +28 天）/
    12-01 晚（跨月延续）；矛盾 shift 参数被忽略（晚班参数查早班日
    仍回早班；非法 shift 值不报错）；POST 传错班次按推导落库（早班
    日传 evening → saved.shift=morning 且退税岗空；晚班日传 morning
    → saved.shift=evening 且退税岗带两名协管员）；mine 单班次形状
    （无 shifts 键、result 为当日班次、无计划月份 result=noplan 且
    shift 仍按锚点推导）。
  - 搭配修正（场景均经独立脚本预演确定性结果，断言钉确切人选）：
    S1 晚班零历史：纯贪心 AB 双科领导同组得分 1 → 修正交换 A/E 后
    两组皆混编得分 2（A EEE/B BBB/C CCC/D DDD/E AAA）；
    S2 早班（造两日历史 + CCC当日休假、在岗科领导 2 人）：纯贪心
    得分 2 → 修正达该班人员暴力枚举极大值 4 且人员班不变（无班替）
    （v6.25 适配：11-06 适用新模板，重造历史使纯贪心把两名科领导
    排到 B/E 同对位、修正交换 A/B 达极大，详见 S2 处注释）；
    S3 晚班搭配修正（v6.20 适配：原班替场景因晚班 ≥6 人改走
    6 人固定岗结构而收窄到在岗恰 5 人）：造两日晚班历史使纯贪心
    混编得分 1（BBB被挤到 E 位）→ 修正互换 C/E，BBB入 C
    岗、班内科领导 2 名、得分 2；
    S4 在岗科领导仅 1 人 → 默认与测试侧复刻的纯贪心逐字一致
    （v6.20 适配：在岗收窄为恰 5 人）。
  - 测试侧复刻纯贪心：用 context 返回的 on_duty_cadre +
    history_stats 按 v6.0 口径（优先级 早 A→E→B→C→D / 晚 A→E 依次；
    键=(该字母次数, 班次总数, 名单顺序））独立计算，与服务端默认
    对照——修正断言不依赖服务端自报。
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
from datetime import date, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 3011
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
    i = text.find(start)
    if i < 0:
        return ""
    j = text.find(end, i + len(start))
    return text[i:] if j < 0 else text[i:j + len(end)]


# ---- 测试侧独立复刻：v6.0 纯贪心 + 混编得分（不依赖服务端实现） ----
PRIORITY = {"morning": ["A", "E", "B", "C", "D"], "evening": ["A", "B", "C", "D", "E"]}
PAIRS = {"evening": [("A", "B"), ("C", "D")],
         # v6.25 适配：morning 审图对改为新模板的对（B,E)/(A,C)/(B,D)/
         # (C,E)/(A,D)——本套件唯一用 morning 得分的 S2 场景日在
         # 2026-11-06（分界 11-05 之后、适用新模板）；旧对
         # (B,C)/(D,E)/(A,B)/(C,E)/(A,D) 为分界前模板的对。
         "morning": [("B", "E"), ("A", "C"), ("B", "D"), ("C", "E"), ("A", "D")]}
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


def score_local(shift, letters_by_name):
    return sum(1 for a, b in PAIRS[shift]
               if (letters_by_name[a] in LEADER_NAMES)
               != (letters_by_name[b] in LEADER_NAMES))


def parity_local(ds):
    d = date.fromisoformat(ds)
    return "morning" if (d - date(2026, 11, 2)).days % 2 == 0 else "evening"


def main():
    tmpdb = os.path.join(tempfile.mkdtemp(prefix="duty-smoke-v61-"), "test.db")
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
        check("v6.1 服务启动", up)
        if not up:
            return 1

        atok = login("admin", "admin123")
        st, users = req("GET", "/api/users", token=atok)
        lw_user = [u for u in users if u["username"] == "CCC"][0]
        req("PATCH", f"/api/users/{lw_user['id']}", token=atok, body={"is_admin": True})
        xtok = login("FFF", "123456")
        st, people = req("GET", "/api/people", token=atok)
        P = {p["name"]: p for p in people}
        pid_of = {n: P[n]["id"] for n in P}
        name_of = {v: k for k, v in pid_of.items()}

        st, plan = req("POST", "/api/plans", token=atok,
                       body={"year": 2026, "month": 11, "quota": 9, "self_limit": 6})
        plan_id = plan["id"]
        req("PATCH", f"/api/plans/{plan_id}", token=atok, body={"phase_override": 3})
        st, plan12 = req("POST", "/api/plans", token=atok,
                         body={"year": 2026, "month": 12, "quota": 9, "self_limit": 6})
        check("建 2026 年 11 月与 12 月计划成功（12 月用于跨月奇偶断言）",
              st == 200 and "id" in plan12)

        def ctx(date_s, token=atok, extra=""):
            return req("GET", f"/api/daily/context?date={date_s}{extra}", token=token)

        def save_raw(body, token=atok):
            return req("POST", "/api/daily/assignments", token=token, body=body)

        def L(**kw):
            return {k: pid_of[v] for k, v in kw.items()}

        def by_name(letters):
            return {k: name_of[v] for k, v in letters.items()}

        # ---- P0) 班次奇偶（锚点 2026-11-02 = 早班，逐日交替、跨月延续） ----
        for ds, want, label in (("2026-11-01", "evening", "晚班"),
                                ("2026-11-02", "morning", "早班"),
                                ("2026-11-03", "evening", "晚班"),
                                ("2026-11-30", "morning", "早班"),
                                ("2026-12-01", "evening", "晚班")):
            st, c = ctx(ds)
            check(f"奇偶：{ds} 推导为 {label}（shift={want}）",
                  st == 200 and c["shift"] == want and c["shift_label"] == label
                  and parity_local(ds) == want,
                  f"got {c.get('shift')}")

        # ---- P1) 矛盾/非法 shift 参数被忽略 ----
        st, c = ctx("2026-11-02", extra="&shift=evening")
        check("context 传 shift=evening 查 11-02（早班日）→ 仍回早班（参数被忽略）",
              st == 200 and c["shift"] == "morning", f"got {c.get('shift')}")
        st, c = ctx("2026-11-03", extra="&shift=morning")
        check("context 传 shift=morning 查 11-03（晚班日）→ 仍回晚班",
              st == 200 and c["shift"] == "evening", f"got {c.get('shift')}")
        st, c = ctx("2026-11-02", extra="&shift=garbage")
        check("context 传非法 shift 值 → 不报错、按日期推导早班",
              st == 200 and c["shift"] == "morning", f"got {st}/{c.get('shift')}")

        # ---- S1) 晚班搭配修正：零历史纯贪心得分 1 → 修正得分 2 ----
        # v6.20 适配：本场景验证 5 人晚班搭配修正，须让 11-01 在岗恰
        # 5 人走 5 人模板（≥6 人改走晚班 6 人固定岗结构，见 v6.20
        # 套件）；置FFF/GGG/HHH/III 1 日轮休，在岗恰为原
        # 纯贪心五人班（S3 的 E1 造历史保存随之把 E 位改排AAA，
        # 见 S3 处适配说明）。
        for _n in ("FFF", "GGG", "HHH", "III"):
            req("PUT", f"/api/plans/{plan_id}/cell", token=atok,
                body={"person_id": pid_of[_n], "day": 1, "symbol": "X"})
        st, c = ctx("2026-11-01")
        g = greedy_local(c)
        check("S1 前置：零历史晚班纯贪心 = 名单顺序且混编得分 1（AB 组双科领导同组）",
              g == {"A": "AAA", "B": "BBB", "C": "CCC", "D": "DDD", "E": "EEE"}
              and score_local("evening", g) == 1, str(g))
        d = by_name(c["default"]["letters"])
        check("S1 修正后晚班默认两组皆混编（得分 2）：A EEE/B BBB/C CCC/D DDD/E AAA（交换 A/E、公平损失 0）",
              d == {"A": "EEE", "B": "BBB", "C": "CCC", "D": "DDD", "E": "AAA"}
              and score_local("evening", d) == 2, str(d))

        # ---- S2) 早班搭配修正：得分 2 → 达暴力极大 4（无班替） ----
        # v6.25 适配：场景日 11-06 在新模板分界后，审图对与第 1 时段
        # 字母集合随新模板变化，原造历史下纯贪心已达极大（无修正
        # 空间）；故重造两日历史（经独立复刻预演）：纯贪心把两名科
        # 领导排到 B/E（新模板审图对之一、两人同对不混编），混编
        # 得分 2；修正交换 A/B（公平代价 0）后科领导分占 A/E，
        # 得分达暴力极大 4、人员班不变。
        st, out = save_raw({"date": "2026-11-02", "leader_id": pid_of["AAA"],
                            "letters": L(A="AAA", B="DDD", C="EEE", D="HHH", E="FFF")})
        check("S2 造历史：11-02 早班保存成功（M1）", st == 200, str(st))
        st, out = save_raw({"date": "2026-11-04", "leader_id": pid_of["AAA"],
                            "letters": L(A="III", B="EEE", C="BBB", D="HHH", E="DDD")})
        check("S2 造历史：11-04 早班保存成功（M2）", st == 200, str(st))
        req("PUT", f"/api/plans/{plan_id}/cell", token=atok,
            body={"person_id": pid_of["CCC"], "day": 6, "symbol": "X"})
        # v6.16 适配：本场景验证 5 人早班搭配修正，须让 11-06 在岗恰
        # 5 人走 5 人模板（≥6 人将改走 6 人方案 A–F，见 v6.16 套件）；
        # 另置EEE/HHH/III 6 日轮休，在岗恰为原纯贪心五人班。
        for _n in ("EEE", "HHH", "III"):
            req("PUT", f"/api/plans/{plan_id}/cell", token=atok,
                body={"person_id": pid_of[_n], "day": 6, "symbol": "X"})
        st, c = ctx("2026-11-06")
        check("S2 前置：11-06 在岗科领导恰为AAA+BBB（CCC当日轮休）、在岗干部恰 5 人（v6.16 适配，走 5 人模板）",
              {p["name"] for p in c["on_duty_leaders"]} == {"AAA", "BBB"}
              and len(c["on_duty_cadre"]) == 5,
              str([p["name"] for p in c["on_duty_leaders"]]))
        g = greedy_local(c)
        check("S2 前置：纯贪心把两名科领导排到 B/E 同对位（新模板审图对）、混编得分 2（v6.25 适配）",
              g == {"A": "GGG", "B": "BBB", "C": "FFF", "D": "DDD", "E": "AAA"}
              and score_local("morning", g) == 2, str(g))
        crew_ids = [pid_of[n] for n in g.values()]
        best = max(score_local("morning", {L_: name_of[p] for L_, p in zip("ABCDE", perm)})
                   for perm in itertools.permutations(crew_ids))
        d = by_name(c["default"]["letters"])
        check("S2 修正后得分 = 该班人员暴力枚举极大值 4，且高于纯贪心的 2",
              best == 4 and score_local("morning", d) == 4, f"best={best} default={d}")
        check("S2 修正只换字母不换人（人员班与纯贪心一致，无班替）：A BBB/B GGG/C FFF/D DDD/E AAA（v6.25 适配：交换 A/B）",
              set(d.values()) == set(g.values())
              and d == {"A": "BBB", "B": "GGG", "C": "FFF", "D": "DDD", "E": "AAA"},
              str(d))

        # ---- S3) 晚班搭配修正：纯贪心混编得分 1 → 互换修正得分 2 ----
        # v6.20 适配：原场景为「班替」（班内仅 1 名科领导、换入未排
        # 的第二名）；晚班 ≥6 人已改走 6 人固定岗结构、5 人晚班全员
        # 在班无未排人员，班替在晚班不可达，故本场景收窄到在岗恰
        # 5 人（置CCC/FFF/GGG/III 7 日轮休），改以字母互换
        # 验证同一搭配修正目标（混编得分 1→2）。另 S1 已置 11-01
        # 四人轮休，E1 的 E 位原排HHH当日不在岗，改排AAA。
        st, out = save_raw({"date": "2026-11-01", "leader_id": pid_of["AAA"],
                            "letters": L(A="BBB", B="CCC", C="DDD", D="EEE", E="AAA")})
        check("S3 造历史：11-01 晚班保存成功（E1）", st == 200, str(st))
        st, out = save_raw({"date": "2026-11-03", "leader_id": pid_of["AAA"],
                            "letters": L(A="CCC", B="BBB", C="FFF", D="GGG", E="III")})
        check("S3 造历史：11-03 晚班保存成功（E2）", st == 200, str(st))
        for _n in ("CCC", "FFF", "GGG", "III"):
            req("PUT", f"/api/plans/{plan_id}/cell", token=atok,
                body={"person_id": pid_of[_n], "day": 7, "symbol": "X"})
        st, c = ctx("2026-11-07")
        g = greedy_local(c)
        check("S3 前置：纯贪心混编得分 1（BBB被历史挤到 E 位、第二组 C/D 无科领导）",
              g == {"A": "HHH", "B": "AAA", "C": "EEE", "D": "DDD", "E": "BBB"}
              and score_local("evening", g) == 1, str(g))
        d = by_name(c["default"]["letters"])
        check("S3 互换修正：BBB与EEE互换 C/E、班内科领导 2 名、混编得分 2",
              d == {"A": "HHH", "B": "AAA", "C": "BBB", "D": "DDD", "E": "EEE"}
              and {n for n in d.values() if n in LEADER_NAMES} == {"AAA", "BBB"}
              and score_local("evening", d) == 2, str(d))

        # ---- S4) 在岗科领导 <2 → 不修正（默认 = 纯贪心） ----
        req("PUT", f"/api/plans/{plan_id}/cell", token=atok,
            body={"person_id": pid_of["BBB"], "day": 9, "symbol": "X"})
        req("PUT", f"/api/plans/{plan_id}/cell", token=atok,
            body={"person_id": pid_of["CCC"], "day": 9, "symbol": "X"})
        # v6.20 适配：再置FFF/GGG 9 日轮休使在岗恰 5 人走 5 人
        # 晚班（≥6 人改走 6 人固定岗结构、默认不再是纯贪心+修正）。
        for _n in ("FFF", "GGG"):
            req("PUT", f"/api/plans/{plan_id}/cell", token=atok,
                body={"person_id": pid_of[_n], "day": 9, "symbol": "X"})
        st, c = ctx("2026-11-09")
        g = greedy_local(c)
        d = by_name(c["default"]["letters"])
        check("S4 在岗科领导仅AAA 1 人时默认与纯贪心逐字一致（修正整体跳过）、带班为AAA",
              [p["name"] for p in c["on_duty_leaders"]] == ["AAA"]
              and d == g and c["default"]["leader_id"] == pid_of["AAA"],
              f"default={d} greedy={g}")

        # ---- S5) POST 传错班次 → 按推导落库 ----
        st, out = save_raw({"date": "2026-11-10", "shift": "evening",
                            "leader_id": pid_of["AAA"],
                            "letters": L(A="AAA", B="BBB", C="CCC", D="DDD", E="EEE")})
        check("S5 早班日（11-10）POST 传 shift=evening → 不拒绝、按早班落库（v6.31 适配：退税岗所有班次都带，早班亦带两名协管员）",
              st == 200 and out["saved"]["shift"] == "morning" and out["saved"]["tax_ids"] == [pid_of["JJJ"], pid_of["KKK"]],
              str(out.get("saved")))
        st, c = ctx("2026-11-10")
        check("S5 回读 11-10：已保存记录为早班",
              c["saved"] is not None and c["saved"]["shift"] == "morning")
        st, out = save_raw({"date": "2026-11-11", "shift": "morning",
                            "leader_id": pid_of["AAA"],
                            "letters": L(A="GGG", B="HHH", C="AAA", D="EEE", E="BBB")})
        check("S5 晚班日（11-11）POST 传 shift=morning → 按晚班落库且退税岗带两名协管员",
              st == 200 and out["saved"]["shift"] == "evening"
              and out["saved"]["tax_ids"] == [pid_of["JJJ"], pid_of["KKK"]],
              str(out.get("saved")))
        st, c = ctx("2026-11-11")
        check("S5 回读 11-11：已保存记录为晚班",
              c["saved"] is not None and c["saved"]["shift"] == "evening")

        # ---- S6) mine 单班次结构 ----
        ctok = login("AAA", "123456")
        st, mine = req("GET", "/api/daily/mine?date=2026-11-11", token=ctok)
        check("S6 mine 晚班日：单班次结构（无 shifts 键）、shift/shift_label 为晚班、result 为本人 C 岗",
              "shifts" not in mine and mine["shift"] == "evening"
              and mine["shift_label"] == "晚班"
              and mine["result"]["status"] == "ok" and mine["result"]["letter"] == "C",
              str(mine.get("result")))
        st, mine = req("GET", "/api/daily/mine?date=2026-11-10", token=ctok)
        check("S6 mine 早班日：shift 为早班、result 为本人 A 岗",
              mine["shift"] == "morning" and mine["result"]["status"] == "ok"
              and mine["result"]["letter"] == "A", str(mine.get("result")))
        st, mine = req("GET", "/api/daily/mine?date=2027-03-01", token=xtok)
        check("S6 mine 无计划月份：plan=null、result=noplan，且 shift 仍按锚点推导（2027-03-01 为晚班）",
              mine["plan"] is None and mine["result"]["status"] == "noplan"
              and mine["shift"] == parity_local("2027-03-01") == "evening",
              str(mine.get("shift")))
        st, mine = req("GET", "/api/daily/mine?date=2026-11-10", token=atok)
        check("S6 mine 超管无对应人员（v6.4 适配：默认名单第一人视图 has_person=true、viewer=AAA）且仍带单班次字段（无 shifts 键）",
              st == 200 and mine["has_person"] is True
              and (mine.get("view_person") or {}).get("name") == "AAA"
              and "shifts" not in mine and mine["shift"] == "morning")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    # ---- S7) 前端/后端静态断言 ----
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()
    backend = open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read()

    check("app.js 带 v6.3 版本标记", "/* duty-roster v6.31 */" in js)
    dv = segment(js, "function viewDaily()", "function bindDaily()")
    check("管理员页：班次切换已删除（无 dailyShiftSeg）、改为只读徽标 + 轮替说明文案",
          "dailyShiftSeg" not in js and "dailyShiftBadge" in dv
          and "班次按日轮替：11月2日早班、3日晚班，逐日交替" in dv)
    check("前端奇偶 helper 与后端同锚点（shiftOfDateStr + 2026-11-02）",
          "function shiftOfDateStr" in js and "'2026-11-02'" in js)
    ld = segment(js, "async function loadDaily()", "function dailyOnDutyNames")
    check("loadDaily 只按日期取上下文（URL 无 &shift=、全文无 dailyState.shift）",
          "/api/daily/context?date=${dailyState.date}" in ld
          and "&shift=" not in js and "dailyState.shift" not in js)
    mph = segment(js, "function myPostsHTML(out)", "function myShiftCardHTML")
    check("岗位显示页单班次渲染（myPostsHTML 读 out.result + 标题带 shift_label、无 out.shifts）",
          "out.result" in mph and "out.shift_label" in mph and "out.shifts" not in js)
    # 【v6.2 适配】_repair_pairing 已扩展更名为 _optimize_daily_default
    # （词典序目标：第 1 时段在岗 > 第 1 时段审图 > 混编得分），静态断言随之更新。
    check("后端含班次推导与搭配修正实现（SHIFT_ANCHOR / shift_for_date / _daily_pairs / _optimize_daily_default）",
          "SHIFT_ANCHOR = date(2026, 11, 2)" in backend and "def shift_for_date" in backend
          and "def _daily_pairs" in backend and "def _optimize_daily_default" in backend)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v6.1 引起的 v6.0 套件改动，均已在 smoke_test_v60.py 对应处注明）：
  - smoke_test_v60.py：ctx() 不再传 shift（服务端按日期推导）；场景日期按
    奇偶全部对齐目标班次（B 节次日早班 11-03→11-04、C 节晚班保存
    11-02→11-03 且次日晚班 11-03→11-05、D 节早班退税检查 11-05→11-06、
    F 节 upsert 11-07→11-08、G 节晚班保存与岗位显示 11-08→11-09、休假
    场景 11-09→11-10）；mine 断言改读单班次 result；F 节历史断言随
    11-06 人员管理员保存按推导入早班账更新（AAA A=1、B=2 不变）；
  - 因搭配修正，v60 两处默认人选断言更新：A 节晚班零历史默认改为修正
    结果（A EEE/B BBB/C CCC/D DDD/E AAA）、B 节次日早班
    默认 B 岗由HHH改为班替换入的BBB；C 节「次日晚班默认 A=CCC」
    经核验修正不改动 A、断言保留；
  - 全部套件（v25–v52、v60）：仅版本标记断言由 v6.0 提升为 v6.1，其余未动。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.1 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：临时数据库 + 临时服务端口 3011（API 行为）+ 纯静态检查（前端）\n")
            f.write("- v6.1：班次按日期轮替推导（锚点 2026-11-02=早班、逐日交替、跨月"
                    "不重置），管理员页取消班次切换改只读徽标、岗位显示改单班次；"
                    "默认排班在历史均衡贪心之后新增「一科领导带一干部」搭配修正"
                    "（字母互换 + 必要时班替，得分优先、公平损失次之，在岗科领导"
                    "<2 时不修正）。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.1: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
