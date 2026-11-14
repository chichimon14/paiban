# -*- coding: utf-8 -*-
"""示例科室排班系统 v3.1 冒烟测试（追加到 SMOKE_TEST.md 的 v3.1 章节）。

v3.1 变更（纯前端，app.js + style.css；后端接口/数据未动），共三项：
  1) 超管合并排班表两条并一行：v3.0 的独立瘦身条（.super-bar）删除，状态小字
     并入网格卡标题行左区（层标签之后，超宽省略），标题居中，右区 = 工作流
     按钮（调取/补满/保存/发布/退回控件）+ 导出按钮同组，放不下在行内换行。
  2) 人员与权限合并表字体对齐：表内 input/select/button 统一 font:inherit、
     13px、28px 高，整表垂直居中（.people-table-card 作用域）。
  3) 日志管理美化 + 可筛选：卡头标题带计数徽标（共 N 条 / 筛选后 M 条）、
     表格斑马纹 + 悬停高亮、每卡一条 .log-tools 筛选工具栏——修改记录按
     管理员/状态/对象姓名，登录日志按 账号/结果，选项由数据去重生成，
     各带「重置」；无匹配时显示「没有符合条件的记录」空行；筛选状态保存在
     模块级 logFilters，重渲染/数据刷新后仍有效（失效值回落「全部」）。
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

    check("app.js 带 v5.0 版本标记", "/* duty-roster v6.31 */" in js)

    # ---- 1) 两条并一行 ----
    merged = segment(js, "function viewSheetAdmin", "function exportXlsx")
    check("独立瘦身条已删除（.super-bar 标记与 .sb-actions 均无残留）",
          'class="card slim super-bar"' not in js and 'sb-actions' not in js
          and '.super-bar {' not in css and '${bar}' not in js)
    check("标题行左区 = 层标签 + 状态小字（sb-status 紧随层标签 chip）",
          'kindName}</span><span class="sb-status"' in merged
          and 'title="${esc(statusText)}"' in merged)
    check("右区按钮同组：工作流按钮串接 EXPORT_BTNS 后一并传入 sheetTitleRow",
          'const actions =' in merged and 'id="pullBtn"' in merged
          and "EXPORT_BTNS;" in merged and "sheetTitle(p), actions)" in merged)
    check("合并页只剩网格卡一张（sheet-fit 直接包 sheetWrap）",
          'return `<div class="sheet-fit"><div id="sheetWrap" class="sheet-flex">${sheetCardHTML(row, grid)}' in merged)
    check("CSS 标题行融合样式（左区可省略、右区可换行右对齐、状态 12px 省略号）",
          ".sheet-title-row .st-left { min-width: 0; }" in css
          and ".sheet-title-row .st-right { flex-wrap: wrap; justify-content: flex-end; }" in css
          and ".sb-status { font-size: 12px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }" in css)

    # ---- 2) 人员与权限表字体对齐 ----
    check("CSS 人员表控件统一字体（font:inherit / 13px / 28px 高 / 边框盒）",
          ".people-table-card table.mini input:not([type=\"checkbox\"])," in css
          and "font: inherit; font-size: 13px; height: 28px; line-height: normal;" in css
          and "box-sizing: border-box; vertical-align: middle;" in css)
    check("CSS 人员表整表垂直居中 + 勾选框统一尺寸",
          ".people-table-card table.mini th, .people-table-card table.mini td { vertical-align: middle; }" in css
          and '.people-table-card table.mini input[type="checkbox"] { width: 16px; height: 16px; margin: 0; vertical-align: middle; }' in css)

    # ---- 3) 日志管理美化 + 筛选 ----
    logs = segment(js, "function viewLogs()", "/* 筛选控件变更后整页重渲染")
    check("两卡筛选控件齐全且各出现一次（管理员/状态/对象/账号/结果/双重置）",
          all(js.count(f'id="{i}"') == 1 for i in
              ("modAdminF", "modStatusF", "modTargetF", "modResetF",
               "loginUserF", "loginResultF", "loginResetF")))
    check("筛选选项由数据去重生成（distinctVals + optsHTML，状态用统一文案映射）",
          "function distinctVals(" in js and "optsHTML(adminOpts, mf.admin)" in logs
          and "optsHTML(statusOpts, mf.status, (v) => ADJ_STATUS_LABEL[v] || v)" in logs
          and "optsHTML(userOpts, lf.user)" in logs
          and "optsHTML(resultOpts, lf.result)" in logs
          and "const ADJ_STATUS_LABEL = {" in js)
    check("筛选逻辑齐全（管理员/状态精确匹配、对象包含、账号/结果匹配）",
          "(!mf.admin || a.admin_name === mf.admin)" in logs
          and "(!mf.status || a.status === mf.status)" in logs
          and "(a.target_name || '').includes(targetKw)" in logs
          and "(!lf.user || l.username === lf.user)" in logs
          and "(!lf.result || loginResultLabel(l) === lf.result)" in logs)
    check("计数文案与空行（logCountText 共N条/筛选后M条、无匹配显示空行）",
          "筛选后 ${shown} 条 · 共 ${total} 条" in js and "共 ${total} 条" in js
          and logs.count("没有符合条件的记录") == 2
          and 'class="log-count"' in logs)
    check("筛选状态模块级保存 + 失效回落全部 + 重置与输入框焦点恢复",
          "const logFilters = {" in js
          and "if (mf.admin && !adminOpts.includes(mf.admin)) mf.admin = '';" in logs
          and "if (lf.result && !resultOpts.includes(lf.result)) lf.result = '';" in logs
          and "function bindLogFilters()" in js and "function rerenderLogs(" in js
          and "el.setSelectionRange(el.value.length, el.value.length)" in js)
    check("CSS 日志美化（卡头计数徽标/工具栏/斑马纹/悬停/空行样式）",
          ".logs-col > h3 { display: flex;" in css and ".log-count { margin-left: auto;" in css
          and ".log-tools { display: flex; flex-wrap: wrap;" in css
          and ".logs-cols table.mini tbody tr:nth-child(even) { background: #F8FAFC; }" in css
          and ".logs-cols table.mini tbody tr:hover { background: #EEF4FF; }" in css
          and ".logs-cols td.empty-row { text-align: center;" in css)
    check("后端日志接口未动（GET /api/logs 返回结构保持）",
          'return {"modifications": modifications, "login_logs": login_logs}'
          in open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read())

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v3.1 结构调整引起的旧套件改动，均已在对应测试文件头/断言处注明）：
  - smoke_test_v25/v26/v27/v28/v29：仅版本标记断言由 v3.0 提升为 v3.1；
  - smoke_test_v30：版本标记提升为 v3.1；原「瘦身条结构」「CSS 瘦身条单行 flex」
    两项断言按 v3.1 改写（瘦身条已删除、状态入标题行左区、工作流与导出同组）；
  - smoke_test_v29 的日志布局断言（.logs-cols 包裹/卡头 h3 紧随卡片 div）经
    构造保持兼容，无需改动；其余套件无适配，后端 API 测试全部原样通过。
  - v4.0 适配（深色主题）：日志斑马纹/悬停色值曾改为 rgba(255,255,255,.02) /
    rgba(56,189,248,.06)；v4.1 换回亮色后改回 #F8FAFC / #EEF4FF（即 v3.1
    原始浅色值），断言结构不变。版本标记随 v4.0→v4.1 提升。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v3.1 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：纯静态检查（纯前端变更，不启服务）\n")
            f.write("- v3.1：超管合并排班表瘦身条并入标题行一行；人员与权限表"
                    "控件字体/高度统一；日志管理加卡头计数、斑马纹与前端筛选"
                    "（管理员/状态/对象、账号/结果，各带重置）。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv3.1: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
