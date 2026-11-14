# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.16 冒烟测试（追加到 SMOKE_TEST.md 的 v6.16 章节）。

v6.16 变更（用户 2026-11-02 提供 6 人早班方案图，要求系统随之调整）：
  A) 后端新增早班 6 人模板 MORNING6_SLOTS（A–F）：6 班次×75 分钟
     （07:00–14:30，与 5 人模板同总时长），每班次 审图查验岗 2 人 /
     申报岗 1 人 / 挑查岗 1 人 / 备勤 2 人，格局逐字按图：
     第1班 A+B/C/D/E+F、第2班 D+E/F/A/B+C、第3班 B+C/A/E/F+D、
     第4班 E+F/D/B/C+A、第5班 C+A/B/F/D+E、第6班 F+D/E/C/A+B；
     每人全程恰 2 审图+1 申报+1 挑查+2 备勤。
  B) 变体判定 _daily_variant：无已保存排班时，早班在岗干部 ≥6 人
     → 默认排班排 A–F 六字母套 6 人模板（历史均衡优先级 A→F、各
     字母工作量本已均衡；优化器沿用第 1 班次科领导规则：第 1 班次
     在岗字母为 A–D、备勤 E/F 不算在岗，审图 A/B 优先有科领导，
     混编对取 6 人模板的六个审图对）；在岗恰 5 人仍 A–E 旧模板。
     有已保存排班时模板随其字母（含 F→6 人；纯 A–E→5 人，历史
     排班原样显示、仍可再保存）。晚班恒 A–E、模板与规则不变。
  C) 保存校验：晚班只接受 A–E；早班接受 A–E 或 A–F，其余 400。
     历史统计早班覆盖 A–F（两种早班记录同入早班历史一并均衡）。
     context/dayview 新增 variant 与 letter_order 字段。
  D) 前端：字母全集 A–F，管理员页字母下拉/缺岗校验/保存提交按
     ctx.letter_order（6 人日排满 A–F 并显示「早班 6 人方案（A–F）」
     徽标）；早班预览表、管理员早班导图、成员当日表及其导图的列
     改为随模板首段岗位名生成（5 人：审图/申报/挑查/备勤；6 人：
     审图/申报/挑查岗/备勤），6 人导图卡片加宽到 900px；
     历史累计文本可显示 F 次数。
  E) 附带改名（用户同日追加）：管理员目录「生成当日排班」改名为
     「生成排班」——超管 NAV label、人员管理员动态侧栏 span、页面
     标题 h3 三处同步；路由 daily、成员只读页「当日排班」与后端
     权限文案不动。

测试口径（临时库 + 临时端口 3023）：模板逐格与图核对、全员在岗
（9 干部）早班默认走 6 人、恰 6 人在岗日默认恰排满该 6 人、恰 5 人
在岗日仍走 5 人模板、6 人保存→dayview/mine 时间轴（B 岗六班次岗
位序列与图一致）、F 计入早班历史、保存校验（晚班 A–F 400、早班
非法字母 400、早班 A–E 兼容保存 200 且其 context 仍套 5 人模板）、
前端/后端静态断言。
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
PORT = 3023
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


# 图面格局（审图对, 申报, 挑查, 备勤对）与时间段，逐字按图
EXPECT6 = [
    # v6.27 适配：模板为固定分组+重岗不连排格局（8 班交替），此表为逐格期望
    ("07:00", "07:45", ["A", "B"], "F", "D", ["C", "E"]),
    ("07:45", "08:30", ["C", "D"], "E", "B", ["A", "F"]),
    ("08:30", "09:30", ["A", "B"], "F", "E", ["C", "D"]),
    ("09:30", "10:30", ["C", "D"], "E", "F", ["A", "B"]),
    ("10:30", "11:30", ["A", "B"], "F", "D", ["C", "E"]),
    ("11:30", "12:30", ["C", "D"], "E", "B", ["A", "F"]),
    ("12:30", "13:30", ["A", "B"], "F", "C", ["D", "E"]),
    ("13:30", "14:30", ["C", "D"], "E", "A", ["B", "F"]),
]
LEADERS = {"AAA", "BBB", "CCC"}


def main():
    tmpdb = os.path.join(tempfile.mkdtemp(prefix="duty-smoke-v616-"), "test.db")
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
        check("v6.16 服务启动", up)
        if not up:
            return 1

        atok = login("admin", "admin123")
        st, people = req("GET", "/api/people", token=atok)
        P = {p["name"]: p for p in people}
        pid_of = {n: P[n]["id"] for n in P}
        name_of = {v: k for k, v in pid_of.items()}

        def L(**kw):
            return {k: pid_of[v] for k, v in kw.items()}

        st, plan = req("POST", "/api/plans", token=atok,
                       body={"year": 2026, "month": 11, "quota": 9, "self_limit": 6})
        plan_id = plan["id"]
        req("PATCH", f"/api/plans/{plan_id}", token=atok, body={"phase_override": 3})

        def ctx(date):
            return req("GET", f"/api/daily/context?date={date}", token=atok)

        def save(date, leader, letters, token=atok):
            return req("POST", "/api/daily/assignments", token=token,
                       body={"date": date, "leader_id": leader, "letters": letters})

        def set_off(name, day):
            return req("PUT", f"/api/plans/{plan_id}/cell", token=atok,
                       body={"person_id": pid_of[name], "day": day, "symbol": "X"})

        # ---- A) 模板逐格与图核对 + 全员在岗早班默认走 6 人 ----
        st, c = ctx("2026-11-02")
        tpl = c["template"]
        tpl_ok = len(tpl) == 8
        for slot, (s, e, shen, bao, tiao, xiu) in zip(tpl, EXPECT6):
            posts = {p["post"]: p["letters"] for p in slot["posts"]}
            tpl_ok = tpl_ok and slot["start"] == s and slot["end"] == e \
                and posts.get("审图查验岗") == shen \
                and posts.get("申报岗") == [bao] \
                and posts.get("挑查岗") == [tiao] \
                and posts.get("备勤") == xiu \
                and [p["post"] for p in slot["posts"]] == \
                    ["审图查验岗", "申报岗", "挑查岗", "备勤"]
        check("A 6 人模板逐格与定稿一致（v6.26 适配：8 班次时间/审图对/申报/挑查/备勤对）",
              st == 200 and tpl_ok, str(tpl)[:200])
        d = c["default"]
        check("A 全员在岗（9 干部）早班 context：variant=morning6、letter_order=A–F、模板 8 段（v6.26 适配）",
              c["shift"] == "morning" and c["variant"] == "morning6"
              and c["letter_order"] == ["A", "B", "C", "D", "E", "F"]
              and len(c["template"]) == 8)
        check("A 默认排班排满 A–F 六个不同干部、带班为科长",
              set(d["letters"].keys()) == set("ABCDEF")
              and len(set(d["letters"].values())) == 6
              and d["leader_id"] == pid_of["AAA"], str(d["letters"]))
        slot1_names = {name_of[d["letters"][k]] for k in "ABDF"}
        shen_names = {name_of[d["letters"][k]] for k in "AB"}
        check("A 默认排班第 1 班次规则：A/B/D/F（在岗位，v6.27 适配：新模板首段在岗集）含科领导且审图 A/B 含科领导（备勤 C/E 不计）",
              bool(slot1_names & LEADERS) and bool(shen_names & LEADERS),
              f"slot1={slot1_names} shen={shen_names}")
        hs0 = c["history_stats"][str(pid_of["AAA"])]
        check("A 历史统计覆盖 F 键（早班 A–F）", "F" in hs0 and hs0["F"] == 0, str(hs0))
        pv = c["preview"]
        check("A 预览为 8 段、首段岗位序为 审图/申报/挑查岗/备勤、首段审图真名与默认 A/B 一致（v6.26 适配）",
              len(pv) == 8
              and [p["name"] for p in pv[0]["posts"]] == ["审图查验岗", "申报岗", "挑查岗", "备勤"]
              and [p["name"] for p in pv[0]["posts"][0]["people"]] ==
                  [name_of[d["letters"]["A"]], name_of[d["letters"]["B"]]])

        # ---- B) 恰 6 人在岗：默认恰排满该 6 人 ----
        for n in ("FFF", "GGG", "III"):
            set_off(n, 4)
        st, c = ctx("2026-11-04")
        on6 = {p["name"] for p in c["on_duty_cadre"]}
        check("B 11-04 在岗干部恰 6 人且 variant=morning6",
              len(c["on_duty_cadre"]) == 6 and c["variant"] == "morning6",
              str(on6))
        check("B 默认 A–F 恰为在岗 6 人全集（无人落空、无休假者混入）",
              {name_of[v] for v in c["default"]["letters"].values()} == on6
              and set(c["default"]["letters"].keys()) == set("ABCDEF"),
              str(c["default"]["letters"]))

        # ---- C) 恰 5 人在岗：仍走 5 人模板 ----
        for n in ("DDD", "FFF", "GGG", "HHH"):
            set_off(n, 6)
        st, c = ctx("2026-11-06")
        on5 = {p["name"] for p in c["on_duty_cadre"]}
        check("C 11-06 在岗干部恰 5 人：variant=morning、letter_order=A–E、模板 10 段",
              len(c["on_duty_cadre"]) == 5 and c["variant"] == "morning"
              and c["letter_order"] == ["A", "B", "C", "D", "E"]
              and len(c["template"]) == 10, str(on5))
        check("C 默认仍排 A–E 且恰为在岗 5 人全集",
              {name_of[v] for v in c["default"]["letters"].values()} == on5
              and set(c["default"]["letters"].keys()) == set("ABCDE"))

        # ---- D) 6 人保存 → dayview / mine / 历史 ----
        st, out = save("2026-11-04", pid_of["AAA"],
                       L(A="AAA", B="DDD", C="BBB", D="CCC", E="EEE", F="HHH"))
        check("D 6 人排班保存成功（A–F 六字母）",
              st == 200 and set(out["saved"]["letters"].keys()) == set("ABCDEF"),
              str(st))
        st, dv = req("GET", "/api/daily/dayview?date=2026-11-04", token=atok)
        check("D 成员当日表 dayview：status=ok、variant=morning6、crew 6 人、preview 8 段（v6.26 适配）",
              dv["status"] == "ok" and dv["variant"] == "morning6"
              and len(dv["crew"]) == 6 and len(dv["preview"]) == 8)
        first = {p["name"]: [x["name"] for x in p["people"]] for p in dv["preview"][0]["posts"]}
        check("D dayview 首班次真名与定稿位一致（v6.27 适配：首班 审图 A+B/申报 F/挑查 D/备勤 C+E）：审图 AAA+DDD / 申报 HHH / 挑查 CCC / 备勤 BBB+EEE",
              first.get("审图查验岗") == ["AAA", "DDD"]
              and first.get("申报岗") == ["HHH"]
              and first.get("挑查岗") == ["CCC"]
              and first.get("备勤") == ["BBB", "EEE"], str(first))
        ltok = login("DDD", "123456")
        st, mine = req("GET", "/api/daily/mine?date=2026-11-04", token=ltok)
        mo = mine["result"]
        posts_seq = [e["post"] for e in mo["timeline"]] if mo.get("timeline") else []
        check("D 岗位显示：DDD为 B 岗、时间轴 8 段且岗位序列与定稿一致（审图/挑查岗/审图/备勤/审图/挑查岗/审图/备勤；v6.27 适配：重岗轻岗交替）",
              mo["status"] == "ok" and mo["letter"] == "B"
              and posts_seq == ["审图查验岗", "挑查岗", "审图查验岗", "备勤", "审图查验岗", "挑查岗", "审图查验岗", "备勤"]
              and mo["timeline"][0]["time"] == "07:00–07:45"
              and mo["timeline"][-1]["time"] == "13:30–14:30",
              str(posts_seq))
        check("D B 岗首班次审图同岗同事为 A 岗AAA",
              mo["timeline"][0]["partners"] == ["AAA"],
              str(mo["timeline"][0]))
        st, c = ctx("2026-11-08")
        hs_l = c["history_stats"][str(pid_of["DDD"])]
        hs_z = c["history_stats"][str(pid_of["HHH"])]
        check("D F 计入早班历史：HHH F=1、DDD B=1（11-08 全员在岗、默认仍 morning6）",
              hs_z.get("F") == 1 and hs_l.get("B") == 1
              and c["variant"] == "morning6", f"{hs_z} / {hs_l}")

        # ---- E) 保存校验与 5 人兼容 ----
        st, _ = save("2026-11-05", pid_of["AAA"],
                     L(A="AAA", B="BBB", C="CCC", D="DDD", E="EEE", F="FFF"))
        check("E 晚班保存 A–F → 200（v6.20 适配：晚班 6 人方案同为 A–F，原「晚班恒 A–E」口径已被取代）",
              st == 200, str(st))
        bad = L(A="AAA", B="BBB", C="CCC", D="DDD", E="EEE")
        bad["G"] = pid_of["FFF"]
        st, _ = save("2026-11-08", pid_of["AAA"], bad)
        check("E 早班保存含非法字母 G（A–E+G）→ 400", st == 400, str(st))
        st, _ = save("2026-11-08", pid_of["AAA"],
                     L(A="AAA", B="BBB", C="CCC", D="DDD", E="AAA", F="EEE"))
        check("E 早班 6 人保存同一人占两岗 → 400", st == 400, str(st))
        st, out = save("2026-11-08", pid_of["AAA"],
                       L(A="AAA", B="BBB", C="CCC", D="DDD", E="EEE"))
        check("E 早班 A–E 五人保存仍兼容 → 200", st == 200, str(st))
        st, c = ctx("2026-11-08")
        check("E 已保存 A–E 的日子 context 随保存走 5 人模板（variant=morning、模板 10 段、letter_order A–E）",
              c["variant"] == "morning" and len(c["template"]) == 10
              and c["letter_order"] == ["A", "B", "C", "D", "E"])
        st, dv = req("GET", "/api/daily/dayview?date=2026-11-08", token=atok)
        check("E 该日 dayview 仍为 5 人表（preview 10 段、首段含备勤岗）",
              dv["status"] == "ok" and dv["variant"] == "morning"
              and len(dv["preview"]) == 10
              and "备勤" in [p["name"] for p in dv["preview"][0]["posts"]])
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

    check("S app.js 带 v6.16 版本标记", "/* duty-roster v6.31 */" in js)
    check("S 后端含 6 人模板与变体判定（MORNING6_SLOTS / _daily_variant / LETTER_ORDER6；v6.17 适配：6 人模板岗位名用系统既有口径 挑查岗/备勤）",
          "MORNING6_SLOTS" in backend and "def _daily_variant" in backend
          and "LETTER_ORDER6" in backend
          and '_dpost("挑查岗", [pat[2]])' in segment(backend, "MORNING6_SLOTS", "EVENING_SLOTS")
          and '_dpost("备勤", pat[3])' in segment(backend, "MORNING6_SLOTS", "EVENING_SLOTS"))
    check("S 前端字母全集与字母序助手（ALL_DAILY_LETTERS 含 F / dailyLettersOf 读 ctx.letter_order / blankDailyLetters）",
          "const ALL_DAILY_LETTERS = ['A', 'B', 'C', 'D', 'E', 'F'];" in js
          and "function dailyLettersOf(ctx)" in js and "ctx.letter_order" in js
          and "function blankDailyLetters()" in js)
    prev_seg = segment(js, "function dailyPreviewHTML", "function renderDailyBody")
    check("S 管理员早班预览列随模板生成（ctx.template[0].posts 驱动表头）",
          "ctx.template[0].posts" in prev_seg)
    check("S 管理员页 6 人徽标与按字母序渲染下拉（早班 6 人方案（A–F） / dailyLettersOf(ctx).map(letterSel)）",
          "早班 6 人方案（A–F）" in js and "dailyLettersOf(ctx).map(letterSel)" in js)
    save_seg = segment(js, "async function saveDaily", "async function dailyImage")
    check("S 保存按该日字母序校验并只提交字母序内键（dailyLettersOf(dailyState.ctx) + order.forEach 组装 letters）",
          "dailyLettersOf(dailyState.ctx)" in save_seg and "order.forEach" in save_seg)
    dtbl_seg = segment(js, "function dayTableHTML", "function dayViewHTML")
    dexp_seg = segment(js, "function dayTableExportHTML", "async function dayViewImage()")
    check("S 成员当日表与导图列随 preview 首段岗位名生成（out.preview[0].posts 两处）",
          "out.preview[0].posts" in dtbl_seg and "out.preview[0].posts" in dexp_seg)
    dimg_seg = segment(js, "function dailyImageCardHTML", "/* -------- 成员：岗位显示")
    check("S 管理员早班导图列随模板生成且 6 人卡片加宽（ctx.template[0].posts / 含 F 早班卡宽 900；v6.22 适配：卡片构建抽至纯函数 dailyImageCardHTML、宽度条件改为 L.F && morning ? 900 : 760）",
          "ctx.template[0].posts" in dimg_seg and "L.F && ctx.shift === 'morning' ? 900 : 760" in dimg_seg)
    nav_const = segment(js, "const NAV = [", "];")
    navfn = segment(js, "function renderNav()", "function currentRoute()")
    check("S 管理员目录改名「生成排班」（用户 2026-11-02 追加）：超管 NAV label 与管理员动态侧栏 span 均为「生成排班」、页面标题同步、无「生成当日排班」标签残留",
          "{ route: 'daily', icon: '🗓', label: '生成排班' }" in nav_const
          and "<span>生成排班</span>" in navfn
          and "<h3>生成排班</h3>" in js
          and "label: '生成当日排班'" not in js and "<span>生成当日排班</span>" not in js)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v6.16 引起的旧套件改动，均已在对应测试文件处注明）：
  - 全部 34 个旧套件：版本标记断言字面量由 v6.15 提升为 v6.16
    （仅字面量），其余未动；
  - smoke_test_v60.py：零历史早班默认与次日早班默认两项改为 6 人
    方案的确切人选（在岗 9 人走 A–F）；超管 NAV 与成员式侧栏的
    daily 标签断言随改名改为「生成排班」；
  - smoke_test_v61.py：S2 场景另置EEE/HHH/III 6 日轮休，
    使 11-06 在岗恰 5 人、继续验证 5 人模板的搭配修正（纯贪心与
    修正期望人选不变）；
  - smoke_test_v62.py：M1/M2 两早班场景同理收窄到在岗恰 5 人
    （M1 在岗五人班变更，纯贪心/优化期望人选已按新班重算；M2
    期望人选不变）；晚班 E1/E2 未动；另静态断言中优化器调用
    字面量适配新增的 template/letter_order 关键字参数；
  - smoke_test_v66.py：A 项 context 默认岗数 5→6（9 人在岗走
    6 人方案）；
  - smoke_test_v69.py：D 项随其保存的默认排班已是 6 人方案——
    dayview letters 改 A–F、preview 改 6 行并按 6 人模板首班次
    映射断言、context 模板 10→6 段；NAV 标签断言随改名更新；
  - smoke_test_v610.py / v614.py：早班表格列改为随模板生成后，
    原硬编码列名（挑查岗/备勤）断言改为生成机制断言
    （template[0].posts / preview[0].posts 驱动表头）；
  - 其余套件逐项核查：已保存 A–E 的日子仍套 5 人模板（v6.16
    套件 E 组专项断言），晚班与月排班断言不受影响。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.16 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：临时数据库 + 临时服务端口 3023（API 行为）+ 纯静态检查（前端/后端）\n")
            f.write(ADAPT_NOTES)
            f.write("- v6.16：早班新增 6 人方案——在岗干部 ≥6 人且无已保存排班时默认排 A–F "
                    "套用户图面 6 班次模板（审图2/申报1/挑查1/备勤2）；恰 5 人仍旧 "
                    "5 人模板；已保存 A–E 历史排班原样兼容；晚班不变。\n")
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.16: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
