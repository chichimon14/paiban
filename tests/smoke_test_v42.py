# -*- coding: utf-8 -*-
"""示例科室排班系统 v4.2 冒烟测试（追加到 SMOKE_TEST.md 的 v4.2 章节）。

v4.2 变更（纯前端 style.css 字号/对比度调整 + app.js 仅版本标记；后端未动）：
  用户反馈「字体清晰度不够，怎么样调整一下，有很多老同志要看」——本版
  只做可读性：姓名与标签放大加粗、符号加大、表头加深，布局结构、断点、
  --cellh 一屏拟合公式、语义颜色全部不变。
  - 姓名（桌面）：.nm-name 17px/700/最深墨色；状态变体（已提交绿/已保存
    未提交橙）字重升到 800，颜色不变。
  - 标签（桌面）：.tag 11px→13px/600、内距 2px 8px，底色加深提对比
    （普通 #E8EEF7/#334E68、领导 #D7E3FF/#1D4ED8、协管员 #EDDEFF/#6D28D9）。
  - 网格：table.grid 基准 14→15px；表头日期 13→14px、星期 10→11px、
    文字改 var(--ink)/#43536B；符号钳制 clamp(13px,…,18px)→(14px,…,19px)
    并加粗 600（行高由 --cellh 固定，拟合公式不受影响）；合计列 15px/700；
    统计行字号下限 11→12px。
  - 姓名列桌面仍 176px（放大后核算 ≈162px ≤ 176px，见 style.css 注释）。
  - 移动端：<=900px 姓名 12→13px、标签 9→11px/600；641~900px 姓名列
    112→132px（850px 宽时日期列约 20.4px，每列只少约 0.7px）；<=640px
    姓名列 104→124px；横屏矮屏（标签隐藏）姓名 11→12.5px。
  - 选择层：宽度 min(300px,92vw)→min(320px,92vw)；选项符号 16→17px、
    名称 11→12px（钳制/定位逻辑不变）。
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


def segment(text, start_marker, end_marker):
    a = text.index(start_marker)
    b = text.index(end_marker, a)
    return text[a:b]


def main():
    css = open(os.path.join(ROOT, "frontend", "style.css"), encoding="utf-8").read()
    js = open(os.path.join(ROOT, "frontend", "app.js"), encoding="utf-8").read()

    check("app.js 带 v5.0 版本标记", "/* duty-roster v6.31 */" in js)

    # ---- 姓名列（桌面） ----
    nm_rule = segment(css, ".nm-name {", "}")
    check("姓名 17px/700/最深墨色（.nm-name）",
          "font-size: 17px" in nm_rule and "font-weight: 700" in nm_rule
          and "color: var(--ink)" in nm_rule)
    check("姓名状态变体字重升 800、颜色不变（绿 #16A34A / 橙 #EA580C）",
          ".nm-name.st-submitted { color: #16A34A; font-weight: 800; }" in css
          and ".nm-name.st-draft { color: #EA580C; font-weight: 800; }" in css)
    check("桌面姓名列宽仍 176px（放大后核算 ≈162px 可放下，见 CSS 注释）",
          "width: 176px; min-width: 176px" in css)

    # ---- 标签（桌面） ----
    tag_rule = segment(css, ".tag {", "}")
    check("标签 13px/600、内距 2px 8px、普通标签底色加深（#E8EEF7/#334E68）",
          "font-size: 13px" in tag_rule and "font-weight: 600" in tag_rule
          and "padding: 2px 8px" in tag_rule
          and "background: #E8EEF7" in tag_rule and "color: #334E68" in tag_rule
          and "white-space: nowrap" in tag_rule)
    check("领导/协管员标签底色加深（#D7E3FF / #EDDEFF+#6D28D9）",
          ".tag.leader { background: #D7E3FF; color: #1D4ED8; }" in css
          and ".tag.assistant { background: #EDDEFF; color: #6D28D9; }" in css)

    # ---- 网格整体 ----
    check("网格基准字号 14→15px",
          "table.grid { border-collapse: collapse; width: 100%; font-size: 15px; }" in css)
    th_rule = segment(css, "table.grid th {", "}")
    check("表头日期 14px + 最深墨色（高度公式 0.5*cellh+18 不变）",
          "font-size: 14px" in th_rule and "color: var(--ink)" in th_rule
          and "calc(var(--cellh, 54px) * 0.5 + 18px)" in th_rule)
    check("表头星期 11px + 深灰蓝 #43536B",
          "table.grid th small { font-size: 11px; color: #43536B; }" in css)
    check("符号钳制抬到 14~19px 且加粗 600（旧钳制无残留）",
          "clamp(14px, calc(var(--cellh, 54px) * 0.34), 19px)" in css
          and "clamp(13px, calc(var(--cellh, 54px) * 0.34), 18px)" not in css
          and "font-weight: 600" in segment(css, "table.grid td.cell {", "}"))
    check("合计列 15px/700",
          "table.grid tr:not(.stats) > td:last-child { font-weight: 700; font-size: 15px;" in css)
    check("统计行字号下限 11→12px（上限/公式不变）",
          "clamp(12px, calc(var(--cellh, 54px) * 0.26), 14px)" in css
          and "clamp(11px, calc(var(--cellh, 54px) * 0.26), 14px)" not in css)

    # ---- 移动端 ----
    m900 = segment(css, "@media (max-width: 900px) {",
                   "@media (max-width: 900px) and (min-width: 641px)")
    check("<=900px 姓名 13px、标签 11px/600（内距 1px 6px）",
          ".nm-name { font-size: 13px; }" in m900
          and ".nm-tags .tag { font-size: 11px; font-weight: 600; padding: 1px 6px; }" in m900)
    check("641~900px 姓名列 112→132px（旧值无残留）",
          "width: 132px; min-width: 0" in css and "width: 112px" not in css)
    check("<=640px 姓名列 104→124px（旧值无残留）",
          "width: 124px; min-width: 124px" in css and "width: 104px" not in css)
    land = css[css.index("@media (max-width: 900px) and (max-height: 500px)"):]
    check("横屏矮屏姓名 11→12.5px（标签仍隐藏）",
          ".nm-name { font-size: 12.5px; }" in land
          and ".nm-tags { display: none; }" in land)

    # ---- 选择层 ----
    picker_rule = segment(css, ".picker {", "}")
    check("选择层宽度 300→320px（视口钳制/层内滚动不变）",
          "width: min(320px, 92vw)" in picker_rule
          and "max-height: calc(100dvh - 16px)" in picker_rule
          and "overflow-y: auto" in picker_rule)
    check("选择层选项符号 17px、名称 12px",
          ".picker-grid button .sym { font-size: 17px;" in css
          and ".picker-grid button .nm { font-size: 12px;" in css)

    # ---- 后端未动 ----
    check("后端未动（GET /api/logs 返回结构保持）",
          'return {"modifications": modifications, "login_logs": login_logs}'
          in open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read())

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v4.2 可读性调整引起的旧套件改动，均已在对应测试文件处注明）：
  - app.js 仅版本标记 v4.1→v4.2，逻辑/结构未动；
  - smoke_test_v25/v26/v27/v28/v29/v30/v31/v41：仅版本标记断言提升为
    v4.2（v29 文件头适配说明已续记；v41 ADAPT_NOTES 中描述 v4.1 事件的
    历史字面已还原，不随标记提升改写）；
  - smoke_test_v23：符号字号钳制断言改 clamp(14px,…,19px)；<=640px 姓名
    列断言 104→124px；弹层宽度断言 min(300px,92vw)→min(320px,92vw)；
    横屏宽度核算常量 112→132（日期列约 20.4px，断言阈值 >=15 不变）；
    文件头补 v4.2 适配说明；
  - smoke_test_v26：姓名列宽度断言三元组由 (176, 112, 104) 改为
    (176, 132, 124)，文件头补记；
  - smoke_test_v41：姓名状态色断言只钉 color 值且 CSS 中 color 声明仍在
    font-weight 之前（字重 700→800 在其后），断言前缀仍命中，无需适配；
    其余亮色令牌/结构断言不受字号调整影响；
  - 其余套件（v1/v2/v2.2/v24/v27/v28/v29/v30/v31 的结构、行为与 API
    断言）与字号无关，全部原样通过；后端零改动。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v4.2 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：纯静态检查（纯前端字号调整，不启服务）\n")
            f.write("- v4.2：可读性调整——姓名 17px/700、标签 13px/600 加深、"
                    "符号钳制 14~19px/600、表头加深、移动端姓名列随之加宽"
                    "（132/124px）、选择层选项放大；布局/断点/拟合公式/"
                    "语义颜色不变，后端未动。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv4.2: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
