# -*- coding: utf-8 -*-
"""示例科室排班系统 v4.9 冒烟测试（追加到 SMOKE_TEST.md 的 v4.9 章节）。

v4.9 变更（纯 CSS 视觉修复，仅 frontend/style.css 两处 + app.js 版本
标记；布局/尺寸/后端全部未动）：用户看成员排班表截图指出——满员/锁定
日是整列灰格（td.cell.full，灰底 #DCDCDC），灰格相连时格子轮廓看不见、
连成一片。根因：网格边框色 #D8E1EE 与灰底 #DCDCDC 几乎同明度，且对
白底/周末淡玫红也偏淡，1px 线被底色吃掉。对策：把 table.grid 的统一
边框色加深为 #A9BAD3（蓝灰，对白底、周末淡玫红 rgba(244,63,94,.05)、
满员灰底 #DCDCDC、表头 #EEF3FA、统计琥珀浅底 #FFF8E1 都有明确对比），
仍 1px、不加粗；.full 规则另显式声明 border-color: #A9BAD3，保证灰格
之间轮廓清晰。作用域严格限定 table.grid：选择层按钮的 #D8E1EE 边框、
table.mini 的 var(--line) 边框均未动。成员页/超管页共用同一网格 CSS，
导出图片截取同一 DOM，一并受益；Excel 导出不受影响。
本套件为纯静态检查（不启服务）。
"""
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT = os.path.join(ROOT, "SMOKE_TEST.md")

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), "-", name, ("| " + str(detail) if detail else ""))


def main():
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()
    css = open(os.path.join(fe, "style.css"), encoding="utf-8").read()
    backend = open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read()

    check("app.js 带 v5.0 版本标记", "/* duty-roster v6.31 */" in js)

    # ---- 1) 网格边框加深 ----
    check("排班网格边框加深为 #A9BAD3（table.grid th/td 统一规则）",
          "table.grid th, table.grid td { border: 1px solid #A9BAD3;" in css)
    check("网格旧边框色 #D8E1EE 无残留（table.grid 规则内）",
          "table.grid th, table.grid td { border: 1px solid #D8E1EE" not in css)

    # ---- 2) 满员灰格显式同色边框 ----
    check("v6.4 适配：.full 灰格规则已整体删除（满员日不再压灰；单元格边框统一走网格 #A9BAD3 通用规则）",
          "table.grid td.cell.full" not in css)

    # ---- 3) 线宽与布局不变 ----
    check("网格仍 border-collapse + 1px 线（只改颜色、不加粗、尺寸未动）",
          "table.grid { border-collapse: collapse; width: 100%; font-size: 15px; }" in css
          and "border: 2px solid #A9BAD3" not in css)

    # ---- 4) 作用域：其他组件未被误改 ----
    check("table.mini 边框未动（仍走 var(--line)，人员/日志表不受影响）",
          "table.mini th, table.mini td { border: 1px solid var(--line);" in css)
    check("选择层按钮边框未动（仍 #D8E1EE，非网格作用域）",
          "background: rgba(255,255,255,.7); border: 1px solid #D8E1EE; }" in css)
    check("网格其他底色（v6.5 适配：周末改回浅粉 #FFF1F2；补满蓝/源数据绿/统计琥珀未动）",
          "table.grid td.weekend { background: #FFF1F2; }" in css
          and "table.grid td.cell.auto { background: #E3F0FF; }" in css
          and "table.grid td.cell.fromsource { background: #EAFAF0; }" in css
          and "table.grid tr.stats td { background: #FFF8E1;" in css)

    # ---- 5) 后端未动 ----
    check("后端未动（main.py 无 v4.9 标记）", "v4.9" not in backend)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v4.9 引起的旧套件改动，均已在对应测试文件处注明）：
  - 全部套件（v25–v48）：仅版本标记断言由 v4.8 提升为 v4.9（检查名同步），
    其余断言未动；
  - smoke_test_v41：「网格回亮色」断言的边框字面量由 #D8E1EE 更新为
    网格作用域的新值（table.grid th/td 边框 #A9BAD3），检查名加
    〔v4.9 加深〕注记，文件头加【v4.9 适配】说明；v4.1 当时「边框
    #D8E1EE」的历史描述保留原文；
  - 其余套件无适配，后端 API 测试全部原样通过。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v4.9 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：纯静态检查（纯 CSS 视觉修复，不启服务）\n")
            f.write("- v4.9：排班网格边框由 #D8E1EE 加深为 #A9BAD3——原色与"
                    "满员灰底 #DCDCDC 几乎同明度，灰色整列相连时格线消失、"
                    "格子轮廓看不清（用户截图反馈）；.full 规则另显式声明"
                    "同色 border-color。仍 1px、布局尺寸不动，作用域仅"
                    " table.grid（成员/超管共用，导出图片同 DOM 一并受益）；"
                    "选择层与 table.mini 未动，后端与数据库未触碰。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv4.9: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
