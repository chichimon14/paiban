# -*- coding: utf-8 -*-
"""示例科室排班系统 v2.9 冒烟测试（追加到 SMOKE_TEST.md 的 v2.9 章节）。

v2.9 变更（纯前端，app.js + style.css；后端接口/数据未动），共四项：
  A) 超管侧栏重组：「我的选班」从超管导航移除，其位置（「排班」组第二项）
     由原「管理」组的数据处理填入并改名「数据管理」；超管 #/pick 重定向主页；
     成员/人员管理员界面不变。
  B) 数据管理页删除「成员提交情况」整表及其下方说明（提交状态看网格姓名
     颜色）；唯一功能「退回提交」压缩为工作流按钮区一行小控件（下拉只列
     已提交成员「姓名 · 提交时间」+ 退回按钮，二次确认，无人提交时不显示）。
  C) 「人员与权限」页两张表（人员列表 + 账号权限）合并为一张：列为
     姓名|类别|组别|角色|启用|密码|操作；行「保存」串行调用人员 PUT +
     账号 PATCH，任一失败明确 toast；启用合并为一个勾选（驱动两边同一值）；
     admin 账号保留表末尾特殊行（角色/启用不可改，重置保留，无保存按钮）。
  D) 「日志管理」页两板块改左右并排（.logs-cols 网格 1fr/1fr，表格字号
     略小、UA 列收紧截断），≤1100px 回上下单列。
本套件为纯静态检查（不启服务）。

【v3.0 适配】v3.0 超管三页合一（主页/数据管理/排班表 → 单个「排班表」）后：
  - A 组断言改写：超管「排班」组只剩 sheet 一项；NAV 改为 icon/label 拆分
    （定宽图标槽位）；超管旧链接 pick/home/process 统一重定向 sheet；
    原数据管理页视图（viewProcess）已删除，工作流并入 viewSheetAdmin。
  - B 组断言的取段范围由 viewProcess 改为 viewSheetAdmin（退回控件随工作流
    迁入合并页），断言内容不变。
  - C 组「页面只剩一个标题」断言去掉前导引号（v3.0 起 h2 外包 .people-fit）。
  - 版本标记断言提升为 v4.0；v4.1 亮色换肤后随之提升为 v4.1（日志等宽
    1fr/1fr 断言不受换肤影响，原样保留）；v4.2 可读性调整后随之提升为 v4.2。
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

    # ---- A) 超管侧栏重组（断言已按 v3.0 三页合一改写，见文件头适配说明） ----
    nav = segment(js, "const NAV = [", "];")
    i_duty = nav.index("{ section: '排班' }")
    i_sheet = nav.index("{ route: 'sheet'")
    i_mgmt = nav.index("{ section: '管理'")
    check("【v3.0 改写·v6.0 注】超管「排班」组核心仍为「排班表」(sheet)（主页/数据管理/我的选班均已并入；v6.0 起同组新增「生成当日排班」daily，细查见 v6.0 套件）",
          i_duty < i_sheet < i_mgmt and "{ route: 'home'" not in nav
          and "{ route: 'process'" not in nav and "'pick'" not in nav and "我的选班" not in nav)
    check("【v3.0 改写】NAV 的 sheet 项为 icon/label 拆分（📋 图标槽位 + 排班表）",
          "{ route: 'sheet', icon: '📋', label: '排班表' }" in nav)
    check("「管理」组仍含 rules/people/history/logs 四项",
          all(s in nav for s in ("'rules'", "'people'", "'history'", "'logs'")))
    check("【v3.0 改写·v6.4 适配】超管旧链接（pick/home/process）统一重定向合并排班表（guard 已加；v6.4 起 guard 不再含 myposts——超管新增岗位显示选人页）",
          "if (myRole() === 'super' && (route === 'pick' || route === 'home' || route === 'process')) route = 'sheet';" in js)
    check("【v3.0 改写】原数据管理页视图已删除（无 viewProcess、无页内大标题）",
          "function viewProcess()" not in js and "<h3>数据管理 · " not in js
          and "🧩 数据管理" not in js)
    check("【v3.0 改写】我的选班页给超管的指引文案已同步为「排班表」",
          "请到「排班表」编辑最终表，或用本人账号登录" in js)
    check("成员/人员管理员导航骨架未变（简化分支仍以排班表 + 修改密码打底，v3.0 改走 nav-ico 槽位渲染；v6.0 在其后追加岗位显示/生成当日排班，细查见 v6.0 套件）",
          "if (myRole() !== 'super')" in js and "a.href = '#/sheet';" in js
          and "a.innerHTML = '<span class=\"nav-ico\">📋</span><span>排班表</span>';" in js)

    # ---- B) 数据管理页：删「成员提交情况」表 + 退回控件 ----
    # 【v3.0 适配】工作流（含退回控件）已随合并迁入 viewSheetAdmin，取段范围随之调整，断言内容不变。
    proc = segment(js, "function viewSheetAdmin", "function exportXlsx")
    check("「成员提交情况」表已删除（标题/旧行内退回按钮/表下说明均不存在）",
          "<h3>成员提交情况</h3>" not in js and "data-return" not in js
          and "重新提交会生成新版本；所有历史版本" not in js)
    check("退回控件已进工作流按钮区（returnSel 下拉 + 退回提交按钮）",
          'id="returnSel"' in proc and 'id="returnBtn"' in proc and "退回提交" in proc)
    check("退回下拉只列已提交成员且为「姓名 · 提交时间」格式",
          "submitted.map((x)" in proc and "${esc(x.name)} · ${esc(x.submitted_at || '')}" in proc)
    check("无人已提交时退回控件不渲染（submitted.length 条件）",
          "submitted.length ? `" in proc and 'class="inline-ctl"' in proc)
    bind = segment(js, "function bindProcess()", "/* ----------------")
    check("退回按钮绑定：二次确认 + 调既有退回接口 + 成功后刷新",
          "confirm(" in bind and "/return/${sel.value}" in bind
          and "await loadDetail(detail.plan.id);" in bind)
    check("退回控件样式 .inline-ctl 已加（inline-flex 一行小控件）",
          ".inline-ctl { display: inline-flex;" in css)

    # ---- C) 人员与权限合并表 ----
    check("页面只剩一个标题「人员与权限」（人员设置/权限设置大标题取消）",
          "<h2 class=\"section-title\">人员与权限</h2>" in js
          and 'section-title">人员设置<' not in js and 'section-title">权限设置<' not in js)
    check("合并表表头为 姓名|类别|组别|角色|启用|密码|操作（v6.7 适配：姓名后加「工号」列；v6.13 适配：角色后加「可看他人岗位」列）",
          "<th>姓名</th><th>工号</th><th>类别</th><th>组别</th><th>角色</th><th>可看他人岗位</th><th>启用</th><th>密码</th><th>操作</th>" in js)
    check("旧两张表结构已清除（人员列表/账号权限/登录名/对应人员列/旧绑定 id）",
          all(s not in js for s in ("<h3>人员列表</h3>", "<h3>账号权限</h3>",
                                    "<th>登录名</th>", "<th>对应人员</th>",
                                    "data-psave", "data-usave", "data-ureset",
                                    "peopleSection", "permsSection")))
    check("行保存 data-rowsave 串行调用人员 PUT + 账号 PATCH",
          "data-rowsave" in js and "api('PUT', '/api/people/' + pid" in js
          and "api('PATCH', '/api/users/' + uid" in js)
    check("行保存任一失败有明确 toast（人员失败/账号失败分开报错）",
          "人员信息保存失败：" in js and "人员信息已保存，但账号设置保存失败：" in js)
    check("角色下拉沿用 ur-<uid>（管理员/普通成员两档）",
          '<select id="ur-${u.id}">' in js and ">管理员</option>" in js and ">普通成员</option>" in js)
    check("启用合并为单个 pa 勾选且同一值写入两个接口",
          'id="pa-${p.id}" type="checkbox"' in js and "active,\n        });" in js
          and "is_admin: $('ur-' + uid).value === '1', active," in js)
    check("admin 特殊行保留在表末尾（登录名文本/超级管理员/启用禁用/重置保留/无保存）",
          "adminUser" in js and "<td>超级管理员</td>" in js
          and '<input type="checkbox" checked disabled>' in js
          and 'data-reset="${adminUser.id}"' in js)
    check("密码重置改为 data-reset 且保留二次确认 + reset_password 调用",
          'data-reset="${u.id}"' in js and "confirm('确认重置该账号密码为初始密码？')" in js
          and "reset_password: true" in js)
    check("新增人员表单保留（addPersonBtn + POST /api/people，新增后重渲染）",
          'id="addPersonBtn"' in js and "api('POST', '/api/people'" in js)

    # ---- D) 日志管理两列布局 ----
    logs = segment(js, "function viewLogs()", "async function bindLogs()")
    check("日志页两板块已包入 .logs-cols 且各带 logs-col 类",
          "'<div class=\"logs-cols\"><div class=\"card logs-col\">" in logs
          and "'<div class=\"card logs-col\"><h3>🔐 登录日志" in logs
          and "html += '</div></div>';" in logs)
    check("CSS 两列网格（v4.0 改等宽 1fr/1fr、顶部对齐、卡片去底边距）",
          ".logs-cols { display: grid; grid-template-columns: 1fr 1fr;" in css
          and ".logs-cols .card { margin-bottom: 0; }" in css)
    check("CSS 日志表字号（v4.4 统一改 13px）+ 单元格可换行（原规则保留、v4.4 在日志作用域内以 nowrap 覆盖）+ UA 列收紧截断",
          ".logs-cols table.mini { font-size: 13px; }" in css
          and ".logs-cols table.mini td { word-break: break-word; }" in css
          and ".logs-cols .ua-cell { max-width: 170px; }" in css
          and ".ua-cell { max-width: 280px;" in css)
    check("CSS ≤1100px 回单列（媒体查询 + grid-template-columns: 1fr）",
          "@media (max-width: 1100px)" in css
          and ".logs-cols { grid-template-columns: 1fr; }" in css)

    return 0 if all(r[1] for r in results) else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v2.9 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：纯静态检查（纯前端变更，不启服务）\n")
            f.write("- v2.9：超管侧栏重组（我的选班移除、数据处理改名数据管理并移入「排班」组）；"
                    "数据管理页删「成员提交情况」表、退回提交压缩为按钮区小控件；"
                    "人员与权限两表合并一行一人、行保存串行双接口；日志管理两板块左右并排（≤1100px 回单列）。\n")
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv2.9: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
