# -*- coding: utf-8 -*-
"""示例科室排班系统 v2.7 冒烟测试（追加到 SMOKE_TEST.md 的 v2.7 章节）。

v2.7 变更（三处界面修复）：
1. 符号选择层永不被视口裁掉：openPicker 改传锚点格元素，新函数 placePicker
   按「优先下方 → 翻到上方 → 钳制回视口」定位；.picker 加
   max-height: calc(100dvh - 16px) + overflow-y: auto，层内可滚达全部选项。
2. 符号改名：☆「探父母假(四年一次)」→「探亲假（四年）」、
   Φ「探父母假(单身)」→「探亲假（单身）」（符号本身不变）；init_db 加幂等
   迁移兜底带 symbols 表的旧库；README/Excel 图例同步（图例由 SYMBOLS 生成）。
   选项按钮等高：.picker-grid 加 grid-auto-rows: 1fr，按钮 height:100% +
   min-height + 垂直居中，长名称换行不撑高。
3. 标题合并为一句话：删除 .pick-badge 徽标，sheetTitle(plan, myLimit) 在
   查看者有本人上限时拼「示例科室排班表（X月可休Q天，您可休N天）」；
   超管/已发布/无对应人员时不带后半句。

【v2.8 适配（2026-10-31）】placePicker 已按用户反馈改为贴锚点格右侧弹出
（水平右侧优先/翻左侧，垂直上缘/下缘对齐），本套件的定位断言改为 v2.8
口径（新算法细节由 smoke_test_v28.py 专项覆盖）；版本标记断言提升为 v2.8。
【v2.9 适配（2026-10-31）】v2.9 不触及选择层定位，仅版本标记断言提升为 v2.9。
其余断言（改名、迁移、等高、标题合并）不受影响。
【v4.6 适配（2026-11-01）】标题后半句文案由用户改为「您可勾选N天」（取代 v2.7
定下的旧文案，纯文案、计数口径不变）：标题断言字面量随之更新；「徽标已删除」
断言原含的「无『您可勾选』」一项（当年针对已删徽标的文案）随文案复活撤销，
pick-badge/pickLimit 不存在两项保留；版本标记断言提升为 v4.6。
【v4.7 适配（2026-11-01）】v4.7 规则变更（个人自选上限只统计轮休 X）后，
标题后半句补足为「，您可勾选N天轮休」：本套件标题断言只查「您可勾选」
子串仍满足，仅更新检查名与版本标记（v4.7）；下方报告串中的旧标题文案
属 v2.7 发布史记录，未改。
【v5.0 适配（2026-11-01）】v5.0 废止 v2.7 的等高实现：grid-auto-rows: 1fr
在面板被 max-height 钳高时会把行拉伸撑满整层（手机横屏按钮巨大，用户
截图反馈），改为固定行高 54px（等高要求不变、实现更换，按钮去掉
height:100%/min-height、靠 stretch 填满固定行）：本套件等高断言更新为
固定行高口径；上文 v2.7 发布史中的旧实现描述保留原文。版本标记断言
提升为 v5.0，细节由 smoke_test_v50.py 专项覆盖。
"""
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 3007
BASE = f"http://127.0.0.1:{PORT}"
REPORT = os.path.join(ROOT, "SMOKE_TEST.md")

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), "-", name, ("| " + str(detail) if detail else ""))


def req(method, path, token=None, body=None, raw=False):
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
    tmpdb = os.path.join(tempfile.mkdtemp(prefix="duty-smoke-v27-"), "test.db")
    proc, up = start_server(tmpdb)
    try:
        check("v2.7 服务启动", up)
        if not up:
            return 1

        # ---------- 符号改名：API ----------
        st, syms = req("GET", "/api/symbols")
        by_code = {s["code"]: s for s in syms} if st == 200 else {}
        # 【Y 支援符号补丁适配（随 11 月定稿导入上线，非 v6.2 变更）】
        # SYMBOLS 新增 Y「支援」后总数 18 → 19，断言随之更新。
        check("符号 API 可用且共 19 个符号（含 Y 支援）", st == 200 and len(syms) == 19,
              f"status={st}, n={len(syms) if st == 200 else 0}")
        check("☆ 改名为「探亲假（四年）」（符号本身不变）",
              by_code.get("☆", {}).get("name") == "探亲假（四年）"
              and by_code.get("☆", {}).get("display") == "☆",
              f"☆={by_code.get('☆')}")
        check("Φ 改名为「探亲假（单身）」（符号本身不变）",
              by_code.get("Φ", {}).get("name") == "探亲假（单身）"
              and by_code.get("Φ", {}).get("display") == "Φ",
              f"Φ={by_code.get('Φ')}")
        check("符号 API 输出中无旧名「探父母假」",
              st == 200 and "探父母假" not in json.dumps(syms, ensure_ascii=False))

        # ---------- Excel 图例同步新名 ----------
        atok = login("admin", "admin123")
        st, plan = req("POST", "/api/plans", token=atok,
                       body={"year": 2026, "month": 11, "quota": 9, "self_limit": 6})
        pid = plan["id"] if st in (200, 201) else None
        check("建 2026-11 计划供导出验证", pid is not None, f"status={st}")
        if pid:
            st, blob = req("GET", f"/api/plans/{pid}/export.xlsx", token=atok, raw=True)
            xml_text = ""
            if st == 200:
                # openpyxl 导出为内联字符串：拼接全部 XML 部件后查图例文字
                zf = zipfile.ZipFile(io.BytesIO(blob))
                xml_text = "\n".join(
                    zf.read(n).decode("utf-8", "replace")
                    for n in zf.namelist() if n.endswith(".xml"))
            check("Excel 图例含新名且无旧名",
                  st == 200 and "探亲假（四年）" in xml_text and "探亲假（单身）" in xml_text
                  and "探父母假" not in xml_text,
                  f"status={st}, xml_len={len(xml_text)}")

        # ---------- 启动迁移：带 symbols 表的旧库 ----------
        stop_server(proc)
        conn = sqlite3.connect(tmpdb)
        conn.execute("CREATE TABLE IF NOT EXISTS symbols "
                     "(code TEXT PRIMARY KEY, name TEXT, display TEXT, counts_leave INTEGER)")
        conn.execute("INSERT OR REPLACE INTO symbols VALUES ('☆', '探父母假(四年一次)', '☆', 1)")
        conn.execute("INSERT OR REPLACE INTO symbols VALUES ('Φ', '探父母假(单身)', 'Φ', 1)")
        conn.execute("INSERT OR REPLACE INTO symbols VALUES ('X', '轮休', '✓', 1)")
        conn.commit()
        conn.close()
        proc, up2 = start_server(tmpdb)
        check("迁移验证用服务重启成功", up2)
        if up2:
            conn = sqlite3.connect(tmpdb)
            rows = dict(conn.execute("SELECT code, name FROM symbols").fetchall())
            conn.close()
            check("启动迁移把 symbols 表旧名改为新名（其他行不动）",
                  rows.get("☆") == "探亲假（四年）" and rows.get("Φ") == "探亲假（单身）"
                  and rows.get("X") == "轮休",
                  f"rows={rows}")
            st, syms2 = req("GET", "/api/symbols")
            by2 = {s["code"]: s for s in syms2} if st == 200 else {}
            check("旧库重启后符号 API 仍返回新名",
                  by2.get("☆", {}).get("name") == "探亲假（四年）"
                  and by2.get("Φ", {}).get("name") == "探亲假（单身）")
    finally:
        stop_server(proc)

    # ---------- 前端静态检查 ----------
    js = open(os.path.join(ROOT, "frontend", "app.js"), encoding="utf-8").read()
    css = open(os.path.join(ROOT, "frontend", "style.css"), encoding="utf-8").read()
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()

    check("app.js 带当前版本标记（v4.7，标记随版本提升）", "/* duty-roster v6.31 */" in js)

    place_seg = segment(js, "function placePicker", "function openPicker")
    check("选择层定位函数 placePicker 存在且 openPicker 传入锚点格矩形",
          "function placePicker" in js
          and "placePicker(picker, anchor.getBoundingClientRect())" in js)
    check("placePicker 含视口钳制与翻转逻辑（v2.8：右侧优先 rect.right + 2 / 翻左侧 / 下缘对齐 rect.bottom - h）",
          "window.innerWidth" in place_seg and "window.innerHeight" in place_seg
          and "rect.right + 2" in place_seg and "rect.bottom - h" in place_seg)

    picker_rule = segment(css, ".picker {", "}")
    check(".picker 高度钳制 + 层内滚动（max-height: calc(100dvh - 16px) + overflow-y: auto）",
          "max-height: calc(100dvh - 16px)" in picker_rule
          and "overflow-y: auto" in picker_rule)
    grid_rule = segment(css, ".picker-grid {", "}")
    btn_rule = segment(css, ".picker-grid button {", "}")
    check("选项按钮等高（v5.0：固定行高 grid-auto-rows: 54px，按钮无 height:100%、垂直居中）【v5.0 适配：原 1fr 等分口径已被固定行高取代，等高要求不变】",
          "grid-auto-rows: 54px" in grid_rule and "height: 100%" not in btn_rule
          and "justify-content: center" in btn_rule)

    check("标题合并逻辑（sheetTitle 条件拼标题后半句 + 成员页传本人 select_limit；后半句文案 v4.6 改为「，您可勾选N天」、v4.7 补足为「，您可勾选N天轮休」）",
          "function sheetTitle" in js and "您可勾选" in js
          and "myLimit != null" in js
          and "sheetTitle(p, mine.select_limit)" in js
          and "const title = sheetTitle(p);" in js)
    check("徽标已彻底删除（app.js/css 无 pick-badge、无 pickLimit）",
          "pick-badge" not in js and ".pick-badge" not in css
          and "pickLimit" not in js)  # v4.6 适配：标题后半句文案改为「您可勾选N天」（用户定），原「无『您可勾选』」断言随之撤销
    check("README 符号表同步新名且无旧名",
          "探亲假（四年）" in readme and "探亲假（单身）" in readme
          and "探父母假" not in readme)

    return 0 if all(r[1] for r in results) else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v2.7 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write(f"- 环境：独立临时数据库（端口 {PORT}），计划 2026-11，Q=9，S=6\n")
            f.write("- v2.7：选择层 placePicker 翻转/钳制定位 + max-height 层内滚动；"
                    "符号 ☆/Φ 改名探亲假（四年）/探亲假（单身）+ 旧库迁移兜底；"
                    "选项按钮等高；标题合并「，您可休N天」、删除 pick-badge 徽标。\n")
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv2.7: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
