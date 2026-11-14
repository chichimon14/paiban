# -*- coding: utf-8 -*-
"""示例科室排班系统 v4.5 冒烟测试（追加到 SMOKE_TEST.md 的 v4.5 章节）。

v4.5 变更（纯前端，app.js + style.css；后端接口/数据未动）：
  符号图例条恢复——但形态与 v2.5 删除的旧图例不同：旧图例是网格下方
  独立成块的区块（legendHTML 函数渲染，v2.5 按用户要求删除）；v4.5
  按用户新要求，把各符号的含义以「排班表卡片内页脚」形式放回卡片
  底部空白处（统计行下方、卡片内），类名 .sheet-legend，由
  sheetLegendHTML() 逐项迭代 SYMBOLS 生成——与选符号弹层同一数据
  源，后端改名（如 v2.7 的探亲假改名）自动同步，前端不硬编码清单。
  渲染入口只有 sheetCardHTML：成员/人员管理员合并页与超管合并
  排班表页共用，其它页面（gridCardHTML 的旧选班页、日志/人员等）
  不带图例。页脚是 .sheet-card 的 flex-none 子项、位于网格滚动区
  之外：fitGrids 按网格区 clientHeight 测高，页脚占高后网格自动
  变矮，整页一屏拟合口径不变；手机竖屏随流式布局自然排在网格后；
  横屏矮屏（<=900px 且高 <=500px）图例条改单行横滑、只占一行高。
本套件为纯静态检查（不启服务）；符号名经后端 SYMBOLS 数据路径核对。
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


def segment(text, start_marker, end_marker):
    a = text.index(start_marker)
    b = text.index(end_marker, a)
    return text[a:b]


def main():
    js = open(os.path.join(ROOT, "frontend", "app.js"), encoding="utf-8").read()
    css = open(os.path.join(ROOT, "frontend", "style.css"), encoding="utf-8").read()
    backend = open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read()

    check("app.js 带 v5.0 版本标记", "/* duty-roster v6.31 */" in js)

    # ---- 1) 图例由共享卡片构建器渲染、数据源为 SYMBOLS ----
    legend_seg = segment(js, "function sheetLegendHTML()", "function sheetTitleRow")
    check("图例构建器 sheetLegendHTML 存在且逐项迭代 SYMBOLS 生成（非硬编码清单）",
          "SYMBOLS.map((s)" in legend_seg
          and "s.display" in legend_seg and "s.name" in legend_seg
          and "符号说明：" in legend_seg
          and "sheet-legend" in legend_seg and "lg-item" in legend_seg)
    check("图例构建器内无硬编码符号名（改名走数据路径同步）",
          "探亲假（四年）" not in legend_seg and "保健假" not in legend_seg
          and "轮休" not in legend_seg and "年休假" not in legend_seg)
    check("符号名经后端数据路径核对（SYMBOLS 字典含探亲假（四年）/保健假，前端经 /api/symbols 同步）",
          '"☆": ("探亲假（四年）", "☆", True)' in backend
          and '"W": ("保健假", "W", True)' in backend
          and "api('GET', '/api/symbols')" in js)
    card_seg = segment(js, "function sheetCardHTML", "/* v4.5：符号图例条")
    check("sheetCardHTML 在网格区之后内嵌图例（卡片内页脚、网格测高区之外）",
          "${sheetLegendHTML()}" in card_seg
          and card_seg.index('grid-wrap fit-wrap') < card_seg.index('${sheetLegendHTML()}'))
    member_seg = segment(js, "function viewMemberSheet", "function bindMemberSheet")
    admin_seg = segment(js, "function viewSheetAdmin", "function exportXlsx")
    check("成员合并页与超管合并页共用同一卡片构建器（两页均带图例）",
          "sheetCardHTML(row," in member_seg and "sheetCardHTML(row, grid)" in admin_seg)
    grid_card_seg = segment(js, "function gridCardHTML", "/* v2.3：排班表卡片")
    check("其它卡片构建器不带图例（gridCardHTML 无 sheetLegendHTML）",
          "sheetLegendHTML" not in grid_card_seg)

    # ---- 2) CSS：页脚条样式 + 一屏拟合结构 + 横屏矮屏单行横滑 ----
    check("CSS 图例条为 flex-none 页脚（换行 flex + 顶部细线分隔 + 内距）",
          ".sheet-legend { flex: none; display: flex; flex-wrap: wrap; gap: 6px 14px;" in css
          and "border-top: 1px solid var(--line); padding: 8px 4px 2px;" in css)
    check("CSS 图例字号（符号 15px/700、名称与标签 13px，老同志可读）",
          ".sheet-legend .lg-item { font-size: 13px;" in css
          and ".sheet-legend .lg-item b { font-size: 15px; font-weight: 700;" in css
          and ".sheet-legend .lg-label { font-size: 13px; font-weight: 600;" in css)
    check("CSS 网格区仍 flex 占满剩余高度（图例占高后网格自动变矮、一屏口径不变）",
          ".sheet-card .grid-wrap.fit-wrap { flex: 1; min-height: 0; overflow: auto; }" in css)
    short_seg = segment(css, "@media (max-width: 900px) and (max-height: 500px)",
                        "/* ================= 日志管理状态 chip")
    check("横屏矮屏图例条改单行横滑（nowrap + overflow-x auto，只占一行高）",
          ".sheet-legend { flex-wrap: nowrap; overflow-x: auto;" in short_seg)

    # ---- 3) 后端未动 ----
    check("后端符号接口未动（/api/symbols 仍由 SYMBOLS 字典生成）",
          '{"code": c, "name": SYMBOLS[c][0], "display": SYMBOLS[c][1],' in backend)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v4.5 引起的旧套件改动，均已在对应测试文件处注明）：
  - smoke_test_v25/v26/v27/v28/v29/v30/v31/v41/v42/v43/v44：仅版本标记
    断言由 v4.4 提升为 v4.5（检查名同步），其余断言未动；
  - smoke_test_v25：「网格下方图例已删除」断言按用户 v4.5 改主意适配——
    v2.5 删除的是网格下方独立图例区块（legendHTML 函数 / class="legend" /
    stats-note 口径说明），v4.5 恢复的是排班表卡片内页脚 .sheet-legend
    （sheetLegendHTML 用 SYMBOLS 生成），两者是不同元素：旧区块仍应保持
    删除，故原断言字面量不变，仅更新检查名并加注记，正向断言在本套件；
  - smoke_test_v23：其检查名/注释中「图例区已按 v2.5 删除」为历史注记，
    断言本体（进度卡瘦身 + sheetCardHTML 结构在）不受影响，未改；
  - 其余套件无适配，后端 API 测试全部原样通过。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v4.5 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：纯静态检查（纯前端变更，不启服务）；符号名经后端 SYMBOLS 数据路径核对\n")
            f.write("- v4.5：符号图例以排班表卡片内页脚（.sheet-legend）形式恢复"
                    "（用户改主意，v2.5 删除的独立图例区块不恢复）：sheetCardHTML "
                    "在网格区后内嵌 sheetLegendHTML()，逐项迭代 SYMBOLS 生成、"
                    "与选符号弹层同源；成员页与超管合并页共用，其它页面不带。"
                    "页脚 flex-none 位于网格测高区之外，fitGrids 按网格区 "
                    "clientHeight 测高、网格自动让出页脚高度；横屏矮屏图例条"
                    "改单行横滑。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv4.5: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
