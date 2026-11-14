# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.14 冒烟测试（追加到 SMOKE_TEST.md 的 v6.14 章节）。

v6.14 变更（2026-11-02 用户要求）：当日排班、岗位显示两个模块里，
把轮换休息位的岗位名「轮休」改称「备勤」，生成图片同样改。改动点：
  - 后端早班模板 MORNING_SLOTS 的岗位名 _dpost("轮休") → _dpost("备勤")
    （源头常量一处）；resolve_daily_slots / person_daily_timeline 的
    post 名随模板流动，管理员 context 的 template/preview、成员
    dayview 的 preview、mine 的 timeline 全部自动跟随；
  - 后端 _slot1_letter_sets 的岗位名比较 "轮休" → "备勤"（第 1 时段
    在岗字母推导逻辑随改名同步，行为不变）；
  - 前端四处硬编码：dailyPreviewHTML（管理员预览表）、dailyImage
    （管理员早班图片）、dayTableHTML（成员当日排班表）、
    dayTableExportHTML（成员当日排班图片）的列头「轮休」与
    byPost/postsOf['轮休'] 查找键 → 「备勤」；岗位显示页面与个人
    图片渲染 t.post（后端数据），无硬编码、自动跟随。

明确不动（月排班口径）：
  - 后端 SYMBOLS 的 X = ("轮休", "✓", True)：月网格/弹层/图例/
    Excel/标题「您可勾选N天轮休」/自选上限文案全部仍称轮休；
  - 当日模块里表示「当天是月休日」的文案本就不用轮休二字（岗位
    显示「当天休假」、管理员页「当天休假（不排岗）」），无改动；
  - 无 DB 变更：岗位名是代码侧模板常量，daily_assignments 只存
    字母→人员映射，历史已保存排班解析结果自动变新名。

测试口径（临时库 + 临时端口 3022）：
  D) 数据：11 月计划发布；11-02（早班）按生产同款保存（带班CCC、
     A GGG/B CCC/C DDD/D HHH/E EEE）；
  A) 管理员 context：template 与 preview 的岗位名含「备勤」、
     全文无「轮休」；首行备勤位 = A 岗GGG；
  B) 成员 dayview：preview 岗位名含「备勤」、全文无「轮休」，
     首行备勤人员为GGG；晚班 dayview 同样无「轮休」；
  C) 岗位显示 mine：HHH（D 岗）时间轴含「备勤」段（09:15–10:00）
     且无「轮休」；GGG（A 岗）时间轴首段 07:00–07:45 为「备勤」；
  M) 月排班未动：/api/symbols 的 X 名称仍「轮休」、显示仍「✓」；
  S) 静态断言：版本标记 v6.14、后端模板/比较改名且月符号原样、
     前端四处日表改名、月标题「天轮休」仍在。
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
PORT = 3022
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


def start_server(dbpath):
    env = dict(os.environ, DUTY_DB=dbpath)
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
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()
    except Exception:
        pass


def segment(text, start_marker, end_marker):
    a = text.index(start_marker)
    b = text.index(end_marker, a)
    return text[a:b]


def post_names(slots):
    # 原始模板的岗位键为 "post"，resolve_daily_slots 解析后为 "name"
    return [(p.get("name") or p.get("post")) for s in slots for p in s["posts"]]


def post_people(slot, name):
    for p in slot["posts"]:
        if p["name"] == name:
            return [x["person_id"] for x in p["people"]]
    return None


def main():
    tmpdb = os.path.join(tempfile.mkdtemp(prefix="duty-roster-v614-"), "test.db")
    proc, up = start_server(tmpdb)
    try:
        check("v6.14 服务启动", up)
        if not up:
            return 1
        atok = login("admin", "admin123")
        st, people = req("GET", "/api/people", token=atok)
        pid_of = {p["name"]: p["id"] for p in people}
        name_of = {p["id"]: p["name"] for p in people}

        # ---- M) 月排班符号未动（先验，独立于当日数据） ----
        st, syms = req("GET", "/api/symbols")
        by_code = {s["code"]: s for s in syms} if st == 200 else {}
        check("M /api/symbols：X 名称仍「轮休」、显示仍「✓」、计休不变（月口径未动）",
              by_code.get("X", {}).get("name") == "轮休"
              and by_code.get("X", {}).get("display") == "✓"
              and by_code.get("X", {}).get("counts_leave") is True,
              f"X={by_code.get('X')}")

        # ---- D) 数据准备 ----
        st, plan = req("POST", "/api/plans", token=atok,
                       body={"year": 2026, "month": 11, "quota": 9, "self_limit": 6})
        plan_id = plan["id"] if st in (200, 201) else None
        check("D 建 2026 年 11 月计划成功", plan_id is not None, f"status={st}")
        req("PUT", f"/api/plans/{plan_id}/final/cell", token=atok,
            body={"person_id": pid_of["FFF"], "day": 5, "symbol": "X"})
        req("POST", f"/api/plans/{plan_id}/final/save", token=atok)
        req("POST", f"/api/plans/{plan_id}/publish", token=atok)
        letters_1102 = {"A": pid_of["GGG"], "B": pid_of["CCC"],
                        "C": pid_of["DDD"], "D": pid_of["HHH"],
                        "E": pid_of["EEE"]}
        st, _ = req("POST", "/api/daily/assignments", token=atok,
                    body={"date": "2026-11-02", "leader_id": pid_of["CCC"],
                          "letters": letters_1102})
        check("D 保存 11-02（早班）当日排班（与生产同款人选）", st == 200,
              f"status={st}")

        # ---- A) 管理员 context：template / preview 改名 ----
        st, ctx = req("GET", "/api/daily/context?date=2026-11-02", token=atok)
        tpl_names = post_names(ctx.get("template") or []) if st == 200 else []
        pv = ctx.get("preview") or []
        pv_names = post_names(pv)
        check("A context 模板岗位名：含「备勤」、无「轮休」（源头常量已改名）",
              st == 200 and "备勤" in tpl_names and "轮休" not in tpl_names,
              f"names={sorted(set(tpl_names))}")
        check("A context 预览岗位名：含「备勤」、无「轮休」；首行备勤位 = A 岗GGG",
              "备勤" in pv_names and "轮休" not in pv_names
              and post_people(pv[0], "备勤") == [pid_of["GGG"]],
              f"row0_standby={post_people(pv[0], '备勤') if pv else None}")
        check("A context 全文（11-02 早班）无「轮休」字样",
              "轮休" not in json.dumps(ctx, ensure_ascii=False))

        # ---- B) 成员 dayview ----
        ztok = login("HHH", "123456")
        st, dv = req("GET", "/api/daily/dayview?date=2026-11-02", token=ztok)
        dv_pv = dv.get("preview") or []
        dv_names = post_names(dv_pv)
        check("B dayview（成员HHH）11-02：status=ok、preview 含「备勤」无「轮休」、首行备勤 = GGG",
              st == 200 and dv.get("status") == "ok"
              and "备勤" in dv_names and "轮休" not in dv_names
              and [name_of[i] for i in (post_people(dv_pv[0], "备勤") or [])] == ["GGG"],
              f"status={dv.get('status')}")
        check("B dayview 全文无「轮休」字样",
              "轮休" not in json.dumps(dv, ensure_ascii=False))
        st, dv3 = req("GET", "/api/daily/dayview?date=2026-11-03", token=ztok)
        check("B dayview 11-03（晚班，未保存）：status=none 且全文无「轮休」",
              st == 200 and dv3.get("status") == "none"
              and "轮休" not in json.dumps(dv3, ensure_ascii=False))

        # ---- C) 岗位显示 mine 时间轴 ----
        st, mine = req("GET", "/api/daily/mine?date=2026-11-02", token=ztok)
        res = mine.get("result") or {}
        tl = res.get("timeline") or []
        standby_times = [e["time"] for e in tl if e["post"] == "备勤"]
        check("C mine HHH（D 岗）：时间轴含备勤段 09:15–10:00 与 13:00–13:45、全轴无「轮休」",
              st == 200 and res.get("status") == "ok"
              and standby_times == ["09:15–10:00", "13:00–13:45"]
              and all(e["post"] != "轮休" for e in tl),
              f"standby={standby_times}")
        stok = login("GGG", "123456")
        st, mine_s = req("GET", "/api/daily/mine?date=2026-11-02", token=stok)
        res_s = mine_s.get("result") or {}
        tl_s = res_s.get("timeline") or []
        check("C mine GGG（A 岗）：首段 07:00–07:45 岗位为「备勤」（个人图片同源数据）",
              st == 200 and tl_s and tl_s[0]["time"] == "07:00–07:45"
              and tl_s[0]["post"] == "备勤",
              f"first={tl_s[0] if tl_s else None}")
        check("C mine 全文（HHH）无「轮休」字样",
              "轮休" not in json.dumps(mine, ensure_ascii=False))
    finally:
        stop_server(proc)

    # ---- S) 静态断言 ----
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()
    backend = open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read()
    prev_seg = segment(js, "function dailyPreviewHTML", "function renderDailyBody")
    dimg_seg = segment(js, "function dailyImageCardHTML", "/* -------- 成员：岗位显示")
    dtbl_seg = segment(js, "function dayTableHTML", "function dayViewHTML")
    dexp_seg = segment(js, "function dayTableExportHTML", "async function dayViewImage()")

    check("S app.js 带 v6.14 版本标记", "/* duty-roster v6.31 */" in js)
    check("S 后端早班模板岗位名已改：_dpost(\"备勤\" 在位、_dpost(\"轮休\" 已清除",
          '_dpost("备勤", [pat[3]])' in backend and '_dpost("轮休"' not in backend)
    check("S 后端 _slot1_letter_sets 比较随改名（\"备勤\" 比较在位、无 \"轮休\" 比较）",
          'post["post"] == "备勤"' in backend and 'post["post"] == "轮休"' not in backend)
    check("S 后端月符号 X 定义原样：(\"轮休\", \"✓\", True) 未动",
          '"X": ("轮休", "✓", True)' in backend)
    check("S 管理员预览 dailyPreviewHTML：列随模板首段岗位名生成（v6.16 适配：不再硬编码备勤列；5 人模板「备勤」名由后端模板断言与本套件 API 段保证）",
          "ctx.template[0].posts" in prev_seg)
    check("S 管理员图片 dailyImage：列随模板首段岗位名生成（v6.16 适配，同上；v6.22 适配：卡片构建已抽至纯函数 dailyImageCardHTML、分段随之）",
          "ctx.template[0].posts" in dimg_seg)
    check("S 成员当日表 dayTableHTML：列随 preview 首段岗位名生成（v6.16 适配，同上）",
          "out.preview[0].posts" in dtbl_seg)
    check("S 成员当日图片 dayTableExportHTML：列随 preview 首段岗位名生成（v6.16 适配，同上）",
          "out.preview[0].posts" in dexp_seg)
    check("S 月排班前端文案未动：标题「您可勾选N天轮休」仍在 app.js",
          "天轮休" in js)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v6.14 引起的旧套件改动）：
  - smoke_test_v60.py：mine 时间轴首段岗位断言「轮休」→「备勤」
    （含检查名，注 v6.14 适配）；早班图片静态断言表头串
    「轮休」→「备勤」（含检查名）；
  - smoke_test_v69.py：dayview 首行 post_people 查找键
    「轮休」→「备勤」（含检查名）；
  - smoke_test_v610.py：dayTableExportHTML 段断言「轮休」in
    →「备勤」in 且「轮休」not in（含检查名）；
  - smoke_test_v62.py：检查名/注释中的「第 1 时段轮休位」措辞
    →「备勤位」（仅命名，断言逻辑未动）；
  - 月口径断言全部原样保留：v27/v47/v64/v65/v66 等对符号 X
    名称「轮休」、标题「您可勾选N天轮休」、上限文案的断言未动；
  - v61 中「CCC当日轮休」是检查名前置说明、指其月休日状态，
    非当日岗位名，按口径保留未改。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.14 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：临时数据库 + 临时服务端口 3022（API 行为）+ 纯静态检查（前端）\n")
            f.write("- v6.14：当日排班/岗位显示模块的轮换休息位岗位名"
                    "「轮休」→「备勤」（后端早班模板源头常量 + "
                    "_slot1_letter_sets 比较 + 前端四处日表硬编码）；"
                    "三张生成图片（管理员早班表图、成员当日表图、个人"
                    "岗位图）随数据/表头跟随；月排班轮休符号与口径"
                    "全部未动；无 DB 变更。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.14: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
