# -*- coding: utf-8 -*-
"""示例科室排班系统 v3.0 冒烟测试（追加到 SMOKE_TEST.md 的 v3.0 章节）。

v3.0 变更（纯前端，app.js + style.css；后端接口/数据未动），共五项：
  1) 超管三页合一：主页 / 数据管理 / 排班表合并为单个「排班表」页——超管侧栏
     「排班」组只剩一项、登录落地页改为排班表、旧链接（home/process/pick）
     统一重定向；合并页 = 瘦身状态/操作条 + 一张网格（有最终表→最终表可编辑，
     无最终表→源数据/草稿汇总只读，标题行短标签标明当前层）。
  2) 网格上方压缩为一条瘦身条（.super-bar）：左一行小字状态，右工作流按钮，
     不再有大卡片 + 四项纵向铺开的状态区。
  3) 删除长篇说明文字（工作流说明句、新增人员表单下注释、人员页表尾说明、
     规则设置选休窗口说明、历史数据两处说明），保留短状态/标签/确认框/toast。
  4) 人员与权限页一屏自适应：fit-view 锁高 + .people-fit 纵向骨架，标题去重
     （删表格卡内重复 h3），新增表单压成一行，表格卡占满剩余高度、内部滚动兜底。
  5) 侧栏对齐：导航项改 icon/label 拆分渲染，图标走 .nav-ico 定宽槽位
     （inline-flex / 22px / 居中 / flex:none），各组文字起始列统一。
本套件为纯静态检查（不启服务）。

【v4.3 适配】「fit-view 启用范围」断言随日志页纳入 fit-view 而扩展：
toggle 条件由 (sheet || people) 改为 (sheet || people || logs)，断言
字面量与检查名已同步更新；其余断言未动。
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

    check("app.js 带当前版本标记（v4.7，标记随版本提升）", "/* duty-roster v6.31 */" in js)

    # ---- 1) 超管三页合一 ----
    nav = segment(js, "const NAV = [", "];")
    check("超管「排班」组核心为「排班表」（无 home/process/pick 项；v6.0 起同组另有「生成当日排班」daily，细查见 v6.0 套件）",
          "{ route: 'sheet', icon: '📋', label: '排班表' }" in nav
          and "{ route: 'home'" not in nav and "{ route: 'process'" not in nav
          and "'pick'" not in nav)
    check("超管「管理/账号」组保持不变（rules/people/history/logs/password）",
          all(s in nav for s in ("{ route: 'rules'", "{ route: 'people'", "{ route: 'history'",
                                 "{ route: 'logs'", "{ route: 'password'")))
    check("原主页/数据管理视图与路由均已移除（viewHome/viewProcess/VIEWS 项）",
          "function viewHome()" not in js and "function viewProcess()" not in js
          and "home: { render:" not in js and "process: { render:" not in js)
    check("超管登录落地页为合并排班表（#/sheet）",
          "if (!location.hash) location.hash = '#/sheet';" in js)
    check("超管旧链接统一重定向（pick/home/process → sheet；v6.4 适配：guard 不再含 myposts，超管可用岗位显示）",
          "if (myRole() === 'super' && (route === 'pick' || route === 'home' || route === 'process')) route = 'sheet';" in js)
    merged = segment(js, "function viewSheetAdmin", "function exportXlsx")
    check("合并页网格分层口径（最终表→final_grid 可编辑；无最终表→display_grid 只读）",
          "detail.display_kind === 'final'" in merged and "detail.final_grid" in merged
          and "detail.display_grid" in merged and "editableMode: p.published ? null : 'final'" in merged)
    check("合并页标题行带当前层短标签 + 标题 + 导出按钮",
          "kindName" in merged and "sheetTitleRow(" in merged and "EXPORT_BTNS" in merged
          and "'提交源数据汇总'" in merged and "'成员草稿汇总'" in merged)
    check("工作流按钮齐全且全文件只出现一次（调取/补满/保存/发布/退回控件）",
          all(js.count(f'id="{i}"') == 1 for i in
              ("pullBtn", "finalAutoBtn", "finalSaveBtn", "finalPublishBtn", "returnSel"))
          and 'id="unpublishBtn"' in merged and 'id="returnBtn"' in merged)
    check("超管排班表绑定导出 + 工作流（bindSheet 内按 super 调 bindProcess）",
          "if (me && myRole() === 'super') bindProcess();" in js)

    # ---- 2) 瘦身条（v3.1 适配：独立瘦身条已删除，状态与按钮并入标题行） ----
    check("瘦身条已并入标题行（v3.1：无独立 .super-bar 卡片，状态小字入左区）",
          'class="card slim super-bar"' not in js and 'sb-actions' not in js
          and 'class="sb-status"' in merged)
    check("状态改为一行小字（已提交 N/总 · 最终表 · 已保存/未保存 · 已发布/未发布）",
          "已提交 ${submitted.length}/${detail.people.length} 人 · 最终表" in merged
          and "'未保存'" in merged and "'未发布'" in merged)
    check("CSS 瘦身条规则已删、状态小字改标题行内 12px 省略样式（v3.1）",
          ".super-bar {" not in css
          and ".sb-status { font-size: 12px; color: var(--muted); white-space: nowrap; overflow: hidden;" in css)
    check("原数据管理大卡片结构已消失（kv 四项状态区/页内 h3 标题）",
          "<b>提交进度</b>" not in js and "<b>保存状态</b>" not in js
          and "<h3>数据管理 · " not in js)

    # ---- 3) 删除长篇说明 ----
    check("工作流说明句已删除（调取数据 = 用全员最新提交…）",
          "调取数据 = 用全员最新提交的源数据重建最终表" not in js
          and "一键补满不限是否已有人选" not in js)
    check("新增人员表单下注释已删除（科长组别自动为…）",
          "科长组别自动为「科长」" not in js and "其账号也无法登录" not in js)
    check("人员页表尾说明已删除（每行点「保存」一次写入…）",
          "每行点「保存」一次写入该行全部字段" not in js)
    check("规则设置选休窗口说明已删除（选休窗口：上月 24 日…）",
          "选休窗口：上月 24 日科长先选" not in js)
    check("历史数据两处说明已删除（源数据保留一年/查看排班表指引）",
          "成员提交的源数据带时间戳保留一年" not in js
          and "查看该计划的排班表：在顶部计划下拉中选中它" not in js)
    check("功能性短提示保留（成员进度卡管理员一行提示仍在）",
          "您是管理员：可点击他人行调整排班，与改自己一样点「保存」后生效，修改会记录在日志中。" in js)

    # ---- 4) 人员与权限一屏自适应 ----
    check("人员页骨架为 .people-fit 且标题只出现一次（表格卡重复 h3 已删）",
          '<div class="people-fit"><h2 class="section-title">人员与权限</h2>' in js
          and js.count("人员与权限</h2>") == 1 and "<h3>人员与权限</h3>" not in js)
    check("fit-view 启用范围含人员页（sheet || people；v4.3 起另含 logs 日志页）",
          "document.body.classList.toggle('fit-view', route === 'sheet' || route === 'people' || route === 'logs');" in js)
    check("新增表单/表格卡类名就位（people-add-card / people-table-card）",
          'class="card people-add-card"' in js and 'class="card people-table-card"' in js)
    check("CSS 一屏骨架（.people-fit 纵向 flex + 表格卡 flex 占高内部滚动 + 行高压缩）",
          ".people-fit { flex: 1; min-height: 0; display: flex; flex-direction: column; }" in css
          and ".people-table-card { flex: 1; min-height: 0; overflow: auto;" in css
          and ".people-table-card table.mini th, .people-table-card table.mini td { padding: 3px 6px; }" in css)
    check("CSS 新增表单桌面单行（nowrap）、窄屏回可换行",
          ".people-add-card .form-grid { flex-wrap: nowrap; }" in css
          and ".people-add-card .form-grid { flex-wrap: wrap; }" in css)

    # ---- 5) 侧栏对齐 ----
    check("CSS 图标定宽槽位（.nav-ico：inline-flex / 22px / 居中 / flex:none）",
          ".nav-ico { display: inline-flex; width: 22px; justify-content: center; flex: none; }" in css)
    check("CSS 导航链接改 flex 对齐（主导航 + 底部账号区）",
          ".nav a { color: #cbd5e1; text-decoration: none; padding: 9px 12px; border-radius: 8px; font-size: 14px; display: flex; align-items: center; gap: 8px; }" in css
          and ".foot-nav a { color: #cbd5e1; text-decoration: none; padding: 9px 12px; border-radius: 8px; font-size: 14px; display: flex; align-items: center; gap: 8px; }" in css)
    check("导航渲染走 nav-ico 槽位（超管 NAV 渲染 + 成员分支）",
          'a.innerHTML = `<span class="nav-ico">${item.icon}</span><span>${item.label}</span>`;' in js
          and "a.innerHTML = '<span class=\"nav-ico\">📋</span><span>排班表</span>';" in js
          and "pw.innerHTML = '<span class=\"nav-ico\">🔑</span><span>修改密码</span>';" in js)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v3.0 结构调整引起的旧套件改动，均已在对应测试文件头注明）：
  - smoke_test_v25/v26/v27/v28：仅版本标记断言由 v2.9 提升为 v3.0；
  - smoke_test_v29：A 组断言按三页合一改写（「排班」组仅剩 sheet、NAV 改
    icon/label 拆分、旧链接重定向 sheet、viewProcess 已删除）；B 组取段范围
    由 viewProcess 改为 viewSheetAdmin；C 组标题断言去掉前导引号
    （h2 外包 .people-fit）；版本标记提升为 v3.0；
  - 其余套件（v1/v2/v2.2/v2.3/v2.4）无适配，后端 API 测试全部原样通过。
- v3.1 追加适配：版本标记断言提升为 v3.1；本文件「瘦身条结构」「CSS 瘦身条
  单行 flex」两项断言按 v3.1 改写——独立 .super-bar 已删，状态小字并入网格
  标题行左区、工作流按钮与导出按钮同在右区。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v3.0 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：纯静态检查（纯前端变更，不启服务）\n")
            f.write("- v3.0：超管主页/数据管理/排班表三页合一为「排班表」（瘦身状态条 + "
                    "分层网格）；删除各页长篇说明文字；人员与权限页一屏自适应；"
                    "侧栏导航图标定宽槽位对齐。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv3.0: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
