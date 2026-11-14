# -*- coding: utf-8 -*-
"""示例科室排班系统 v5.0 冒烟测试（追加到 SMOKE_TEST.md 的 v5.0 章节）。

v5.0 变更（纯前端：frontend/style.css picker 段 + app.js 版本标记；
后端/数据库未动）：用户用安卓手机横屏（Brave）打开排班表点格选符号时，
选择层面板占满近整屏、每个选项按钮被拉得巨大，下方选项（丧假等）
被挤到滚动区之外。根因确认：.picker 的高度由内容决定、仅被
max-height: calc(100dvh - 16px) 钳制（placePicker 只写 left/top、
从不设 height/maxHeight），而 .picker-grid 用 v2.7 的
grid-auto-rows: 1fr——面板一旦被钳到视口高，1fr 行就把钳制后的
高度等分给每一行（6 行平分近整屏高），行高随面板高度膨胀。
对策：① grid-auto-rows 改固定 54px（桌面），按钮去掉 height:100%/
min-height，靠网格默认 stretch 填满固定行——v2.7 的「按钮等高」
要求保留、实现更换，行高不再随面板高度变化；面板高度回到内容
驱动，超出 max-height 时层内滚动（原行为不变）。② 新增小屏紧凑
媒体段（max-width: 640px 或 max-height: 500px，与本表既有 640/500
断点一致）：面板宽 min(272px, 88vw)、行高 46px（仍 >=44px 可点
下限）、gap 6px、符号 17px、名称 11px、标题 14px、面板内距 10px；
选项区 6 行约 306px。③ 定位逻辑（v2.8 贴右侧/翻转/钳制）未动，
桌面宽度 min(320px, 92vw) 未动。本套件为纯静态检查（不启服务）。
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

    check("app.js 带 v5.0 版本标记", "/* duty-roster v6.31 */" in js)

    # ---- 1) 固定行高：不再 1fr 拉伸 ----
    grid_rule = segment(css, ".picker-grid {", "}")
    btn_rule = segment(css, ".picker-grid button {", "}")
    check("选项行高固定（.picker-grid 为 grid-auto-rows: 54px）",
          "grid-auto-rows: 54px" in grid_rule, grid_rule.strip()[:80])
    check("全表无 grid-auto-rows: 1fr 残留（拉伸机制已除）",
          "grid-auto-rows: 1fr" not in css)
    check("选项按钮去掉 height:100%（靠 stretch 填满固定行、保持垂直居中）",
          "height: 100%" not in btn_rule and "justify-content: center" in btn_rule)

    # ---- 2) 面板高度仍为内容驱动 + max-height 钳制；placePicker 不设高度 ----
    picker_rule = segment(css, ".picker {", "}")
    check(".picker 桌面口径未动（宽 min(320px, 92vw) + max-height 钳制 + 层内滚动）",
          "width: min(320px, 92vw)" in picker_rule
          and "max-height: calc(100dvh - 16px)" in picker_rule
          and "overflow-y: auto" in picker_rule)
    place_seg = segment(js, "function placePicker", "function openPicker")
    check("placePicker 只定位不设高（无 style.height / style.maxHeight 赋值，"
          "仍写 left/top + 右侧优先/下缘对齐）",
          "function placePicker" in js
          and "style.height" not in place_seg and "style.maxHeight" not in place_seg
          and "picker.style.left" in place_seg and "picker.style.top" in place_seg
          and "rect.right + 2" in place_seg and "rect.bottom - h" in place_seg)

    # ---- 3) 小屏紧凑媒体段 ----
    # 【v5.2 适配】小屏口径由 v5.0 的 3 列/272px/46px/名称 11px 改为
    # v5.2 的 4 列/344px/44px/名称 10.5px nowrap（见 smoke_test_v52.py），
    # 本节断言随之更新；v5.0 发布史描述保留原文。
    mq = "@media (max-width: 640px), (max-height: 500px)"
    mq_seg = segment(css, mq, ".picker-clear { margin-top: 6px; }")
    check("小屏媒体段存在（max-width: 640px 或 max-height: 500px）", mq in css)
    check("小屏面板宽度（width: min(344px, 94vw) + padding: 8px）〔v5.2 以宽换高〕",
          "width: min(344px, 94vw)" in mq_seg and "padding: 8px" in mq_seg)
    check("小屏行高紧凑（4 列 + grid-auto-rows: 40px + gap: 6px）〔v5.2 为 44px；v5.3（随 v6.0）收紧为 40px〕",
          "grid-template-columns: repeat(4, 1fr)" in mq_seg
          and "grid-auto-rows: 40px" in mq_seg and "gap: 6px" in mq_seg)
    check("小屏字号（符号 17px / 名称 10.5px nowrap / 标题 14px）〔v5.2〕",
          ".picker-grid button .sym { font-size: 17px; }" in mq_seg
          and ".picker-grid button .nm { font-size: 10.5px; white-space: nowrap; }" in mq_seg
          and ".picker-head { font-size: 14px;" in mq_seg)

    # ---- 4) 桌面基础字号未被媒体段污染（基础规则仍 17/12px） ----
    check("桌面基础字号未动（.sym 17px / .nm 12px 基础规则仍在）",
          ".picker-grid button .sym { font-size: 17px; font-weight: 700; }" in css
          and ".picker-grid button .nm { font-size: 12px; color: #5B6B84; }" in css)

    # ---- 5) 后端未动 ----
    check("后端未动（main.py 无 v5.0 标记）", "v5.0" not in backend)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v5.0 引起的旧套件改动，均已在对应测试文件处注明）：
  - 全部套件（v25–v49）：仅版本标记断言由 v4.9 提升为 v5.0（检查名同步），
    其余断言未动；
  - smoke_test_v27：「选项按钮等高」断言由 v2.7 的 1fr/height:100% 口径
    更新为 v5.0 固定行高 54px 口径（等高要求保留、实现更换），文件头加
    【v5.0 适配】说明；v2.7 发布史描述保留原文；
  - smoke_test_v28/v41/v42 的 .picker 断言（max-height/overflow/桌面宽度/
    基础字号）取首个 .picker 规则段，新媒体段位于其后、口径未变，原样通过。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v5.0 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：纯静态检查（纯前端 CSS 修复，不启服务）\n")
            f.write("- v5.0：符号选择层自适应紧缩——根因是 .picker-grid 的"
                    "grid-auto-rows: 1fr 在面板被 max-height 钳到视口高时把"
                    "钳制高度等分给每一行，手机横屏上按钮被拉得巨大（用户"
                    "截图反馈，placePicker 本身从不设高度）。改固定行高"
                    "（桌面 54px）保留 v2.7 等高要求；新增小屏媒体段"
                    "（<=640px 或高度 <=500px）：宽 min(272px, 88vw)、"
                    "行高 46px、名称 11px。桌面宽度与定位逻辑未动，"
                    "后端与数据库未触碰。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv5.0: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
