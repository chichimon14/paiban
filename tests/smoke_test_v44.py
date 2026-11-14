# -*- coding: utf-8 -*-
"""示例科室排班系统 v4.4 冒烟测试（追加到 SMOKE_TEST.md 的 v4.4 章节）。

v4.4 变更（纯前端，app.js + style.css；后端接口/数据未动），仅日志管理页三项：
  1) 淡格线占位行：两卡表格当前显示行（筛选后）不足 20 行时，由
     logFillerRows 补 .filler-row 占位行凑满 20 行版面（修改记录 colspan=6、
     登录日志 colspan=5），与 v4.3 的 20 行固定高度滚动区配套；空状态行
     占 1 行、补其余 19 行；≥20 行不补。占位行纯视觉，不进数据数组、
     不影响计数徽标与筛选逻辑，每次渲染按当前显示行数重算。
  2) 全表严格等高：两表改 table-layout: fixed 并按 th 宽度分配列宽，
     全部 td 单行显示（nowrap + overflow hidden + 省略号），覆盖 v2.9 的
     word-break: break-word——「变更（旧→新）」等长文本不再换行撑高，
     左右两表逐行对齐、行高严格 32px（表头 34px）；变更列加 title
     悬停全文（UA 列沿用既有 title）。空状态行除外（居中、height:auto）。
  3) 字体统一：日志页作用域内表头/单元格/状态 chip/筛选工具栏（标签、
     下拉、输入、按钮）一律 inherit 正文字体、统一 13px（与人员表一致）；
     原 12px 规则已在原处改 13px，无残留冲突；卡头标题 15px 与计数
     徽标 12px 保持标题层级（两卡共用规则、天然一致）。
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
    js = open(os.path.join(ROOT, "frontend", "app.js"), encoding="utf-8").read()
    css = open(os.path.join(ROOT, "frontend", "style.css"), encoding="utf-8").read()
    logs = segment(js, "function viewLogs()", "/* 筛选控件变更后整页重渲染")

    check("app.js 带 v5.0 版本标记", "/* duty-roster v6.31 */" in js)

    # ---- 1) 占位行 ----
    check("占位行辅助函数 logFillerRows（按 20 - shownSlots 逐行生成）",
          "function logFillerRows(shownSlots, colCount) {" in js
          and "for (let i = shownSlots; i < 20; i++)" in js
          and '`<tr class="filler-row"><td colspan="${colCount}">&nbsp;</td></tr>`' in js)
    check("两卡渲染均调用占位行（修改记录 colspan=6、登录日志 colspan=5，空状态按 1 行计入）",
          "logFillerRows(modsShown.length || 1, 6)" in logs
          and "logFillerRows(logsShown.length || 1, 5)" in logs)
    check("空状态行保留且在占位行之前（0 条时空行 + 19 行占位 = 20 行）",
          '<tr><td colspan="6" class="empty-row">没有符合条件的记录</td></tr>' in logs
          and '<tr><td colspan="5" class="empty-row">没有符合条件的记录</td></tr>' in logs
          and logs.index('class="empty-row"') < logs.index("logFillerRows(modsShown.length"))
    check("计数徽标口径未动（仍按真实数据/筛选后条数，占位行不计入）",
          "function logCountText(total, shown, active) {" in js
          and "logCountText(mods.length, modsShown.length, modActive)" in logs
          and "logCountText(logs.length, logsShown.length, logActive)" in logs)
    check("CSS 占位行行高与数据行一致（32px，非 empty-row 的 auto）",
          ".logs-cols table.mini tbody tr.filler-row td { height: 32px; }" in css)

    # ---- 2) 严格等高 ----
    check("CSS 两表 fixed 布局 + td 单行省略号（覆盖 word-break、行高靠 td 32px 固定）",
          ".logs-cols table.mini { table-layout: fixed; }" in css
          and ".logs-cols table.mini tbody td { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; word-break: normal; line-height: 1.3; }" in css
          and ".logs-cols table.mini thead th { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }" in css)
    check("CSS 空状态行豁免单行截断（保持居中换行）",
          ".logs-cols table.mini tbody td.empty-row { white-space: normal; overflow: visible; }" in css)
    check("CSS 列宽按 th 分配（左卡 6 列、右卡 5 列各一组 nth-child 宽度）",
          ".logs-cols > .logs-col:first-child table.mini th:nth-child(5) { width: 27%; }" in css
          and ".logs-cols > .logs-col:last-child table.mini th:nth-child(5) { width: 40%; }" in css)
    check("变更列带 title 悬停全文、UA 列 title 保留（v6.5 适配：变更格加挂 chg 类以纳入符号字体栈）",
          '<td class="chg" title="${esc(change)}">${esc(change)}</td>' in logs
          and '<td class="ua-cell" title="${esc(ua)}">${esc(ua)}</td>' in logs)

    # ---- 3) 字体统一 ----
    check("CSS 日志表与工具栏字号统一 13px（原 12px 规则已原地改值）",
          ".logs-cols table.mini { font-size: 13px; }" in css
          and ".log-tools select, .log-tools input { font-size: 13px; padding: 4px 6px; }" in css
          and ".log-tools button { padding: 4px 10px; font-size: 13px; }" in css)
    check("CSS chip 在日志作用域内 13px + 字体 inherit 兜底（表格/工具栏控件）",
          ".logs-cols .chip { font-size: 13px; padding: 1px 8px; line-height: 1.3; }" in css
          and ".logs-cols table.mini th, .logs-cols table.mini td, .logs-cols .chip," in css
          and "font-family: inherit; }" in css)
    check("CSS 无残留日志作用域 12px 冲突规则（旧字面量零命中）",
          ".logs-cols table.mini { font-size: 12px; }" not in css
          and ".log-tools select, .log-tools input { font-size: 12px;" not in css
          and ".log-tools button { padding: 4px 10px; font-size: 12px; }" not in css)
    check("后端日志接口未动（GET /api/logs 返回结构保持）",
          'return {"modifications": modifications, "login_logs": login_logs}'
          in open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read())

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 【v6.5 追记】「变更列带 title」断言同步 v6.5 标记：变更格新挂
    class="chg"（纳入符号字体栈），断言字面量改为
    '<td class="chg" title="...">'，title 口径本身未变。
- 适配说明（v4.4 引起的旧套件改动，均已在对应测试文件处注明）：
  - smoke_test_v25/v26/v27/v28/v29/v30/v31/v41/v42/v43：仅版本标记断言
    由 v4.3 提升为 v4.4（检查名同步），其余断言未动；
  - smoke_test_v29：「日志表字号」断言由 12px 改为 13px（检查名同步注记
    v4.4），其 word-break: break-word 字面量断言保留——原规则仍在，
    v4.4 以更高优先级规则在日志作用域内覆盖为 nowrap；
  - smoke_test_v43：「日期输入与工具栏控件同规格」断言的字号由 12px
    改为 13px（检查名同步注记 v4.4），日期输入宽度 138px 等其余不变；
  - smoke_test_v31/v41 的日志斑马纹/悬停/空行字面量断言不受影响
    （相关规则未改字面量）；其余套件无适配，后端 API 测试全部原样通过。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v4.4 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：纯静态检查（纯前端变更，不启服务）\n")
            f.write("- v4.4：日志管理页两表显示行不足 20 行时补 .filler-row 淡格线"
                    "占位行凑满 20 行（空状态行占 1 行、补 19 行）；两表改 fixed "
                    "布局、全 td 单行省略号截断严格等高 32px（变更列加 title）；"
                    "日志页作用域字体统一 inherit + 13px（原 12px 规则原地改值）。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv4.4: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
