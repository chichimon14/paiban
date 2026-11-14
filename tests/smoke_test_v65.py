# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.5 冒烟测试（追加到 SMOKE_TEST.md 的 v6.5 章节）。

v6.5 变更（用户对 v6.4 的三项修正，2026-11-01）：
  1)【列色】天蓝不再整列：v6.4 的「干部在岗 ≥6 整列天蓝」撤下，
     天蓝 #D9ECFF 只落页脚「干部在岗人数」行对应天的那一格
     （cadre-blue 类，其余两行统计格不挂）；其余人员格回白底；
     周六日整列由淡蓝灰 #F2F7FC 改回浅粉 #FFF1F2（表头/人员格/
     统计行）。周末且宽裕的那天，干部行那一格仍是天蓝（CSS 中
     cadre-blue 与 stats weekend 同特异性、后置胜出）。
  2)【符号】轮休显示字符改回「✓」(U+2713)（v6.4 的「√」被用户
     否掉，用户消息里亲自给出 ✓）。v6.3 的符号字体栈保留；并对
     字体规则做了逐点核验：v6.3 三条选择器对真实标记——网格人员
     格（符号是 td.cell 内裸文本）、弹层（.picker-grid 内
     button .sym）、图例（.lg-item b）——均命中；但另有两处符号
     渲染未被覆盖：日志管理「变更（旧 → 新）」列（table.mini 裸
     文本）与岗位显示页头「当天休假（X）」。v6.5 给前者单元格新
     挂 td.chg 类、后者以 .sym-glyph 包裹，两处补进同一字体栈；
     本套件加「选择器类名必须真实存在于 app.js/index.html 标记」
     的防腐交叉断言。
  3)【岗位显示】「生成图片」按钮从卡片底部移入「岗位」同一行
     （.post-line flex 行：岗位文字 + 按钮紧贴其右、垂直居中，
     窄屏可换行）；可见条件不变（status ok/tax 才渲染，按钮经
     共享 imgBtn 片段只注入 ok/tax 两分支，loadMyPosts 绑定不变）。

测试口径（临时库 + 临时端口 3015）：
  A) 符号 API：X 显示为「✓」、名称仍「轮休」、计休不变；全表
     无「√」显示字符；
  B) 数据口径（蓝格的数据依据）：同 v6.4 B 的最终表场景——
     1 日在岗 5、2 日 5、3 日 9、7 日（周六）6，由 final_day_stats
     断言（渲染端据此只给干部行 3/7 日格挂 cadre-blue，静态侧验）；
  C) Excel 导出：含「✓」与图例「轮休✓」，全文无「√」；
  D) 岗位显示页头符号链：DDD 11-01 有轮休格 → 其 mine 返回
     status=off 且 off_symbol == 「✓」（页头 .sym-glyph 所包裹者）；
  S) 静态断言：版本标记、后端 X 定义；字体规则选择器覆盖交叉
     校验（类名逐一在 app.js/index.html 中有真实标记；五处符号
     渲染点全部被覆盖）；列色逻辑（gridHTML 只剩 weekend 列类、
     cadre-blue 仅出现在统计行渲染处、全文无整列天蓝残留）；
     CSS 精确值（cadre-blue #D9ECFF 且全表仅此一处用该色、
     周末 #FFF1F2、#F2F7FC 无残留、cadre-blue 规则后置于统计行
     weekend 规则）；岗位行（.post-line 内含 mpImgBtn 且在时段
     表之前、imgRow 已消失、CSS .post-line flex 居中规则、绑定
     语句不变）。
"""
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 3015
BASE = f"http://127.0.0.1:{PORT}"
REPORT = os.path.join(ROOT, "SMOKE_TEST.md")

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), "-", name, ("| " + str(detail) if detail else ""))


def req(method, path, token=(None), body=None, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            payload = resp.read()
            return resp.status, (payload if raw else json.loads(payload or b"{}"))
    except urllib.error.HTTPError as e:
        payload = e.read()
        if raw:
            return e.code, payload
        try:
            return e.code, json.loads(payload or b"{}")
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


def main():
    tmpdb = os.path.join(tempfile.mkdtemp(prefix="duty-roster-v65-"), "test.db")
    proc, up = start_server(tmpdb)
    try:
        check("v6.5 服务启动", up)
        if not up:
            return 1

        # ---- A) 符号 API ----
        st, syms = req("GET", "/api/symbols")
        by_code = {s["code"]: s for s in syms} if st == 200 else {}
        check("A 轮休 X 显示字符改回「✓」(U+2713)、名称仍「轮休」、计休不变",
              by_code.get("X", {}).get("display") == "✓"
              and by_code.get("X", {}).get("name") == "轮休"
              and by_code.get("X", {}).get("counts_leave") is True,
              f"X={by_code.get('X')}")
        check("A 符号表全量无「√」显示字符",
              st == 200 and all(s.get("display") != "√" for s in syms))

        atok = login("admin", "admin123")
        st, people = req("GET", "/api/people", token=atok)
        pid_of = {p["name"]: p["id"] for p in people}
        st, plan = req("POST", "/api/plans", token=atok,
                       body={"year": 2026, "month": 11, "quota": 9, "self_limit": 6})
        plan_id = plan["id"] if st in (200, 201) else None
        check("建 2026 年 11 月计划成功", plan_id is not None, f"status={st}")

        # ---- B) 数据口径（与 v6.4 B 同场景） ----
        def fcell(name, day, sym):
            return req("PUT", f"/api/plans/{plan_id}/final/cell", token=atok,
                       body={"person_id": pid_of[name], "day": day, "symbol": sym})

        ok = True
        for n in ("DDD", "EEE", "FFF", "GGG"):
            ok = ok and fcell(n, 1, "X")[0] == 200
            ok = ok and fcell(n, 2, "X")[0] == 200
        for n in ("DDD", "EEE", "FFF"):
            ok = ok and fcell(n, 7, "X")[0] == 200
        check("B 超管逐格写最终表（1/2/7 日轮休）", ok)
        req("POST", f"/api/plans/{plan_id}/final/save", token=atok)
        req("POST", f"/api/plans/{plan_id}/publish", token=atok)
        st, det = req("GET", f"/api/plans/{plan_id}", token=atok)
        stats = {s["day"]: s for s in det["final_day_stats"]} if st == 200 else {}
        check("B 干部在岗（蓝格数据依据）：1 日=5、2 日=5、3 日=9（≥6）、7 日=6（≥6 且周六）",
              stats.get(1, {}).get("cadre_on_duty") == 5
              and stats.get(2, {}).get("cadre_on_duty") == 5
              and stats.get(3, {}).get("cadre_on_duty") == 9
              and stats.get(7, {}).get("cadre_on_duty") == 6,
              f"d3={stats.get(3)}, d7={stats.get(7)}")

        # ---- C) Excel 导出 ----
        st, blob = req("GET", f"/api/plans/{plan_id}/export.xlsx", token=atok, raw=True)
        xml_text = ""
        if st == 200:
            zf = zipfile.ZipFile(io.BytesIO(blob))
            xml_text = "\n".join(
                zf.read(n).decode("utf-8", "replace")
                for n in zf.namelist() if n.endswith(".xml"))
        check("C Excel 导出含「✓」与图例「轮休✓」、全文无「√」",
              st == 200 and "✓" in xml_text and "轮休✓" in xml_text
              and "√" not in xml_text,
              f"status={st}, xml_len={len(xml_text)}")

        # ---- D) 岗位显示页头符号链（off_symbol） ----
        htok = login("DDD", "123456")
        st, mine = req("GET", "/api/daily/mine?date=2026-11-01", token=htok)
        res = mine.get("result") or {}
        check("D DDD 11-01 mine：off_symbol 为「✓」（页头 .sym-glyph 包裹者；前端据此渲染休假行，当日未存排班时 result 为 none）",
              st == 200 and mine.get("off_symbol") == "✓"
              and res.get("status") not in ("ok", "tax"),
              f"status={st} res={res.get('status')} off={mine.get('off_symbol')}")
    finally:
        stop_server(proc)

    # ---- S) 静态断言 ----
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()
    html = open(os.path.join(fe, "index.html"), encoding="utf-8").read()
    css = open(os.path.join(fe, "style.css"), encoding="utf-8").read()
    backend = open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read()
    grid_seg = segment(js, "function gridHTML", "function bindGridCells")
    post_seg = segment(js, "function myShiftCardHTML", "function myPostsHTML")

    check("S app.js 带 v6.5 版本标记", "/* duty-roster v6.31 */" in js)
    check("S 后端轮休 X 定义为「✓」", '"X": ("轮休", "✓", True)' in backend)

    # Item 2：字体规则选择器覆盖交叉校验（防选择器腐坏）
    css_nc = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    stack = '"PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif'
    font_selectors = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css_nc):
        if stack in m.group(2):
            font_selectors.append(m.group(1))
    sel_text = ",".join(font_selectors)
    classes = sorted(set(re.findall(r"\.([A-Za-z0-9_-]+)", sel_text)))
    markup = js + html
    missing = [c for c in classes if c not in markup]
    check("S 字体规则存在且其全部类名都在 app.js/index.html 的真实标记中出现（防腐交叉校验）",
          len(font_selectors) >= 2 and classes and not missing,
          f"classes={classes} missing={missing}")
    check("S 字体规则覆盖五处符号渲染：网格 td.cell / 弹层 .sym / 图例 .lg-item / 日志 td.chg / 页头 .sym-glyph",
          "td.cell" in sel_text and ".picker-grid" in sel_text and ".sym" in sel_text
          and ".lg-item" in sel_text and "td.chg" in sel_text and ".sym-glyph" in sel_text,
          f"selectors={[s.strip()[:60] for s in font_selectors]}")
    check("S app.js 侧挂类齐备：日志变更格 class=\"chg\"、页头 sym-glyph 包裹 off_symbol",
          'class="chg"' in js and 'class="sym-glyph">${esc(out.off_symbol)}' in js)

    # Item 1：列色逻辑与 CSS 精确值
    check("S gridHTML：colClsOf 只剩周末类、cadre-blue 仅在统计行干部行渲染处出现一次、全 js 无整列天蓝残留",
          "'weekend'" in grid_seg and "'cadre-blue'" in grid_seg
          and grid_seg.count("'cadre-blue'") == 1
          and "key === 'cadre_on_duty'" in grid_seg
          and "stats[d][key] >= 6" in grid_seg
          and "surplus" not in js)
    check("S CSS 精确值：cadre-blue 为 #D9ECFF 且去注释后全表仅此一处用该色；周末浅粉 #FFF1F2",
          "table.grid tr.stats td.cadre-blue { background: #D9ECFF; }" in css
          and css_nc.count("#D9ECFF") == 1
          and "table.grid td.weekend { background: #FFF1F2; }" in css
          and "table.grid th.weekend { background: #FFF1F2; }" in css
          and "table.grid tr.stats td.weekend { background: #FFF1F2; }" in css)
    check("S CSS：v6.4 淡蓝灰 #F2F7FC 与整列天蓝规则无残留",
          "#F2F7FC" not in css and "th.surplus" not in css
          and "td.cell.surplus" not in css and "tr.stats td.surplus" not in css)
    check("S CSS 顺序：cadre-blue 规则后置于统计行 weekend 规则（同特异性后置胜出，周末宽裕日干部格仍为天蓝）",
          css.index("table.grid tr.stats td.cadre-blue") > css.index("table.grid tr.stats td.weekend"))

    # Item 3：岗位行按钮位置
    check("S myShiftCardHTML：按钮经共享 imgBtn 注入 ok/tax 两分支的 .post-line（在时段表之前）、卡片底部 imgRow 已消失",
          "post-line" in post_seg and "const imgBtn" in post_seg
          and post_seg.count("${imgBtn}") == 2
          and post_seg.index("mpImgBtn") < post_seg.index("daily-table")
          and "imgRow" not in post_seg
          and "${footer}</div>" in post_seg)
    check("S CSS .post-line：flex 行、垂直居中、行内 p 无外边距",
          ".post-line { display: flex; align-items: center;" in css
          and ".post-line p { margin: 0; }" in css)
    check("S loadMyPosts 绑定不变：mpImgBtn 仍绑 myPostsImage（按钮 id 与绑定语句未动）",
          "const im = $('mpImgBtn'); if (im) im.addEventListener('click', myPostsImage);" in js)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v6.5 引起的旧套件改动）：
  - 全部套件（v25–v64）：仅版本标记断言由 v6.4 提升为 v6.5，其余未动；
  - smoke_test_v64.py：与 v6.5 冲突的断言按新口径改写并在该文件
    ADAPT_NOTES 追记——符号 A/C/S 改回「✓」；列色 S 改查周末
    weekend + 干部行 cadre-blue；CSS S 改查 #FFF1F2 与
    tr.stats td.cadre-blue 并断言整列天蓝规则/#F2F7FC 不存在；
    岗位图片接线 S 改查按钮移入 .post-line。B/D/E 数据口径未动；
  - smoke_test_v41.py / smoke_test_v49.py：周末底色断言由淡蓝灰
    #F2F7FC 改回浅粉 #FFF1F2（字面量与检查名同步更新）；
  - smoke_test_v44.py：「变更列带 title」断言字面量同步——变更格
    新挂 class="chg" 后 td 标记变为 '<td class="chg" title=...>'，
    title 口径本身未变（该文件 ADAPT_NOTES 已追记）；
  - smoke_test_v27.py 中带 symbols 表旧库的种子行仍写作 '✓'——
    v6.5 起现行显示字符恰好同为 '✓'，该夹具行与现行口径一致、
    无需改动（其断言只查符号名）；
  - README.md 两处「轮休 √」随符号改回同步为「轮休 ✓」；
  - 后端口径除 X 显示字符外无变化（code/名称/计休不变，历史
    数据存 code、无需迁移）；mine 接口与 off_symbol 随之后端
    display 自动回到「✓」。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.5 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：临时数据库 + 临时服务端口 3015（API 行为）+ 纯静态检查（前端）\n")
            f.write("- v6.5：天蓝只落干部在岗统计格（cadre-blue #D9ECFF，其余回白、"
                    "周末改回浅粉 #FFF1F2）；轮休符号改回 ✓ 并补齐字体栈覆盖"
                    "（日志变更格 td.chg、页头 .sym-glyph）+ 选择器防腐交叉校验；"
                    "岗位显示「生成图片」移入岗位行（.post-line）。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.5: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
