# -*- coding: utf-8 -*-
"""示例科室排班系统 v5.2 冒烟测试（追加到 SMOKE_TEST.md 的 v5.2 章节）。

v5.2 变更（纯前端：frontend/style.css 小屏选择层媒体段 + app.js 版本
标记；后端/数据库未动）：v5.0 紧缩后，用户用安卓手机横屏再点格选
符号，选择层仍占约 85% 屏高，且「探亲假（单身）/探亲假（四年）」两个
长名称在 46px 行内换行成两行、溢出按钮，下方行仍要滚动。仅改小屏
媒体段（max-width: 640px 或 max-height: 500px）：① 网格 3 列 → 4 列，
19 项排 5 行；② grid-auto-rows 46px → 44px，选项区 5*44+4*6 = 244px，
整层约 320px；③ 面板宽 min(272px, 88vw) → min(344px, 94vw)、内距
10px → 8px（以宽换高）；④ 名称 11px → 10.5px 并加 white-space:
nowrap 永不换行——最长名「探亲假（单身）」7 字 x 10.5px 约 74px，
列宽约 (344-16-18)/4 约 78px、按钮横向内距收至 2px 恰可容纳；
⑤ 按钮内距在本段显式给 6px 2px。桌面基础规则（3 列 / 54px 行 /
min(320px, 92vw)）与 placePicker 定位逻辑未动。本套件为纯静态
检查（不启服务）。

【v6.0 适配】v5.3 弹层收紧随 v6.0 一并交付：本段小屏行高 44px → 40px，
  本文件行高断言随之更新、旧值残留断言追加 44px；另在其后新增
  @media (max-height: 500px) 横屏矮屏段（5 列/38px/min(400px, 94vw)），
  由 v6.0 套件断言覆盖，本文件取段锚点（首个 .picker-clear
  { margin-top: 6px; }）仍落在原段内、不受影响；版本标记断言提升为 v6.0。
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


def segment(text, start, end):
    i = text.find(start)
    if i < 0:
        return ""
    j = text.find(end, i + len(start))
    return text[i:] if j < 0 else text[i:j + len(end)]


def main():
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()
    css = open(os.path.join(fe, "style.css"), encoding="utf-8").read()
    backend = open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read()

    check("app.js 带当前版本标记（标记随版本提升，现为 v6.0）", "/* duty-roster v6.31 */" in js)

    mq = "@media (max-width: 640px), (max-height: 500px)"
    mq_seg = segment(css, mq, ".picker-clear { margin-top: 6px; }")
    check("小屏媒体段存在（max-width: 640px 或 max-height: 500px）", mq in css and bool(mq_seg))

    # ---- 1) 小屏段新口径（v5.2） ----
    check("小屏面板以宽换高（width: min(344px, 94vw) + padding: 8px）",
          ".picker { width: min(344px, 94vw); padding: 8px; }" in mq_seg)
    check("小屏网格 4 列（grid-template-columns: repeat(4, 1fr)）",
          "grid-template-columns: repeat(4, 1fr)" in mq_seg)
    check("小屏行高 40px（grid-auto-rows: 40px + gap: 6px）〔v5.3（随 v6.0）由 44px 收紧〕",
          "grid-auto-rows: 40px" in mq_seg and "gap: 6px" in mq_seg)
    check("小屏名称不换行（.nm 为 font-size: 10.5px + white-space: nowrap）",
          ".picker-grid button .nm { font-size: 10.5px; white-space: nowrap; }" in mq_seg)
    check("小屏按钮横向内距收至 2px（.picker-grid button padding: 6px 2px）",
          ".picker-grid button { padding: 6px 2px; }" in mq_seg)
    check("小屏符号字形保持 17px",
          ".picker-grid button .sym { font-size: 17px; }" in mq_seg)

    # ---- 2) 小屏段旧口径无残留 ----
    check("小屏段无旧值残留（272px / 46px / 名称 11px / v5.2 行高 44px）",
          "min(272px" not in mq_seg and "grid-auto-rows: 46px" not in mq_seg
          and "grid-auto-rows: 44px" not in mq_seg
          and ".nm { font-size: 11px" not in mq_seg)

    # ---- 3) 桌面基础规则未动 ----
    picker_rule = segment(css, ".picker {", "}")
    grid_rule = segment(css, ".picker-grid {", "}")
    check("桌面 .picker 未动（宽 min(320px, 92vw) + max-height 钳制 + 层内滚动）",
          "width: min(320px, 92vw)" in picker_rule
          and "max-height: calc(100dvh - 16px)" in picker_rule
          and "overflow-y: auto" in picker_rule)
    check("桌面 .picker-grid 未动（3 列 + grid-auto-rows: 54px）",
          "grid-template-columns: repeat(3, 1fr)" in grid_rule
          and "grid-auto-rows: 54px" in grid_rule, grid_rule.strip()[:90])
    check("桌面基础字号未动（.sym 17px/700、.nm 12px 基础规则仍在）",
          ".picker-grid button .sym { font-size: 17px; font-weight: 700; }" in css
          and ".picker-grid button .nm { font-size: 12px; color: #5B6B84; }" in css)

    # ---- 4) 后端未动 ----
    check("后端未动（main.py 无 v5.2 标记）", "v5.2" not in backend)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v5.2 引起的旧套件改动，均已在对应测试文件处注明）：
  - 全部套件（v25–v51）：仅版本标记断言由 v5.1 提升为 v5.2，其余断言未动；
  - smoke_test_v50：小屏媒体段断言（面板宽/行高/名称字号）由 v5.0 口径
    （min(272px, 88vw) + padding: 10px / 46px / 名称 11px）更新为 v5.2 口径
    （min(344px, 94vw) + padding: 8px / 4 列 44px / 名称 10.5px nowrap），
    第 3 节加【v5.2 适配】注记；v5.0 发布史描述保留原文。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v5.2 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：纯静态检查（纯前端 CSS 修复，不启服务）\n")
            f.write("- v5.2：小屏符号选择层再紧缩（用户安卓横屏截图反馈："
                    "v5.0 后仍占约 85% 屏高、长名称在 46px 行内换行溢出）。"
                    "仅改小屏媒体段：网格 3 列→4 列（19 项 5 行）、行高 "
                    "46→44px、面板宽 min(272px, 88vw)→min(344px, 94vw) "
                    "且内距 8px（以宽换高，整层约 320px）、名称 11→10.5px "
                    "并 nowrap 不换行、按钮横向内距 2px。桌面规则与定位"
                    "逻辑未动，后端与数据库未触碰。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv5.2: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
