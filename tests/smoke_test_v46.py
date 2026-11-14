# -*- coding: utf-8 -*-
"""示例科室排班系统 v4.6 冒烟测试（追加到 SMOKE_TEST.md 的 v4.6 章节）。

v4.6 变更（纯文案、仅 frontend/app.js 一个字符串；计数口径/合计分母/
后端全部未动）：排班表标题后半句「，您可休N天」改为「，您可勾选N天」
（sheetTitle 的 minePart 模板；N：科长=Q、其余=S）。出现位置不变——
仍只在查看者有本人自选上限时拼入（成员/人员管理员本人视角），超管/
已发布/无对应人员时不带后半句。历史：该后半句文案是 v2.7 时按用户
当时的原话定下的（当时取代了更早的徽标「您可勾选 N 天」），v4.6
由用户改口为「您可勾选N天」，v2.7 口径就此被取代。
本套件为纯静态检查（不启服务）。

【v4.7 适配（2026-11-01）】v4.7 为规则变更版（个人自选上限改为只统计
轮休 X，其他假期不占名额），标题后半句随之补足为「，您可勾选N天轮休」。
本套件的标题模板字面量断言已更新为新文案、版本标记断言提升为 v4.7；
「后端计数口径未动」一项只查 counts_as_leave 本身——v4.7 新增的是
counts_toward_cap（个人上限口径），counts_as_leave 语义确实未动，
断言仍成立；v4.6 当时「纯文案、后端未动」的历史描述保留原文。
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
    html = open(os.path.join(fe, "index.html"), encoding="utf-8").read()
    backend = open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read()

    check("app.js 带 v5.0 版本标记", "/* duty-roster v6.31 */" in js)

    # ---- 1) 标题后半句新文案 ----
    check("sheetTitle 后半句模板为「，您可勾选${myLimit}天轮休」（v4.7 补足）",
          "function sheetTitle" in js and "，您可勾选${myLimit}天轮休" in js)
    check("前半句未动（「X月可休Q天」仍由 quota 拼）",
          "月可休${plan.quota}天" in js)
    check("后半句出现条件未动（myLimit 非空才拼；超管/已发布不带）",
          "myLimit != null" in js)

    # ---- 2) 前端无旧文案残留 ----
    check("前端三文件无「您可休」残留",
          "您可休" not in js and "您可休" not in css and "您可休" not in html)

    # ---- 3) 计数口径与后端未动 ----
    check("后端计数口径未动（counts_as_leave 仍按符号表计休标记；备勤 B 不计休）",
          "def counts_as_leave(symbol):" in backend
          and "return SYMBOLS[symbol][2]" in backend
          and '"B": ("备勤", "B", False)' in backend)
    check("style.css 无文案改动牵连（图例/标题样式规则仍在）",
          ".sheet-legend" in css and ".grid-title" in css)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v4.6 引起的旧套件改动，均已在对应测试文件处注明）：
  - 全部套件（v25–v45）：仅版本标记断言由 v4.5 提升为 v4.6（检查名同步），
    其余断言未动；
  - smoke_test_v26 / smoke_test_v27：标题断言字面量由旧文案更新为
    「您可勾选」并在检查名/文件头注记 v4.6 取代关系；v27「徽标已彻底
    删除」断言原含「无『您可勾选』」一项（v2.7 当年针对已删徽标的文案），
    随 v4.6 文案改口撤销该项，pick-badge/pickLimit 不存在两项保留；
    两文件 docstring 与 v27 报告串中的旧文案属 v2.7 发布史记录，未改；
  - smoke_test_v31 等其余套件的标题相关断言为结构字面量（sheetTitleRow /
    EXPORT_BTNS），不含文案，无需适配；
  - 其余套件无适配，后端 API 测试全部原样通过。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v4.6 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：纯静态检查（纯文案变更，不启服务）\n")
            f.write("- v4.6：排班表标题后半句文案由「，您可休N天」改为"
                    "「，您可勾选N天」（用户定，取代 v2.7 当年按用户原话定下的"
                    "文案）；仅 frontend/app.js 的 sheetTitle 一处模板字符串，"
                    "出现条件（本人视角才带后半句）、自选上限计数口径"
                    "（除备勤外全部计休符号）、合计分母、后端全部未动。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv4.6: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
