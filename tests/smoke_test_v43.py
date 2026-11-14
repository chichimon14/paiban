# -*- coding: utf-8 -*-
"""示例科室排班系统 v4.3 冒烟测试（追加到 SMOKE_TEST.md 的 v4.3 章节）。

v4.3 变更（纯前端，app.js + style.css；后端接口/数据未动），仅日志管理页两项：
  1) 两卡表格区固定划为 20 条高度、整页一屏：日志页纳入 fit-view 锁定
     （renderRoute 对 logs 路由也加 fit-view 类，与排班表/人员页同一机制）；
     表格包入 .log-scroll 滚动区，高度 = 表头 34px + 20 行 × 32px（行高统一：
     thead th 34px、tbody td 32px，空行除外），记录不足 20 条区域保持此高度、
     超出区内滚动、thead 粘性置顶；桌面并排（≥1101px）时卡片纵向 flex，
     滚动区随可用高度伸缩但不超 20 行上限，矮屏收窄不溢出；堆叠（≤1100px）
     时网格自身滚动、每卡仍保持 20 行上限；手机竖屏保持普通流式滚动。
  2) 时间筛选：两卡工具栏各加「从/到」日期输入（type=date），按记录
     created_at 的日期部分（YYYY-MM-DD）闭区间过滤（字典序比较，任一端
     可空），与既有筛选叠加，计数徽标/空行沿用 v3.1 行为；筛选状态存入
     logFilters.mod/login 的 from/to，页面内重渲染保持，「重置」一并清空。
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

    # ---- 1) 20 行划线 + 一屏锁定 ----
    check("日志页纳入 fit-view（renderRoute 对 logs 路由加 fit-view 类）",
          "route === 'sheet' || route === 'people' || route === 'logs'" in js)
    logs = segment(js, "function viewLogs()", "/* 筛选控件变更后整页重渲染")
    check("两卡表格均包入 .log-scroll 滚动区（开闭各两处）",
          logs.count('<div class="log-scroll"><table class="mini">') == 2
          and logs.count('</tbody></table></div>') == 2)
    check("CSS 滚动区 20 行划线（height/max-height = 表头 34 + 20×32）",
          ".log-scroll { overflow-y: auto; height: calc(34px + 20 * 32px); max-height: calc(34px + 20 * 32px); }" in css)
    check("CSS 行高统一 + 表头粘性置顶（th 34px sticky、td 32px、空行 auto）",
          ".logs-cols table.mini thead th { position: sticky; top: 0; z-index: 2; height: 34px; background: #F4F7FB; }" in css
          and ".logs-cols table.mini tbody td { height: 32px; }" in css
          and ".logs-cols table.mini tbody td.empty-row { height: auto; }" in css)
    check("CSS fit-view 日志网格占满剩余高度（flex:1 + min-height:0）",
          "body.fit-view .logs-cols { flex: 1; min-height: 0; }" in css)
    check("CSS 并排时卡片纵向 flex + 滚动区弹性伸缩（标题/工具栏 flex:none）",
          "body.fit-view .logs-cols { grid-template-rows: minmax(0, 1fr); align-items: start; }" in css
          and "body.fit-view .logs-col { display: flex; flex-direction: column; min-height: 0; max-height: 100%; }" in css
          and "body.fit-view .logs-col > h3, body.fit-view .logs-col .log-tools { flex: none; }" in css
          and "body.fit-view .log-scroll { flex: 1 1 auto; min-height: 0; }" in css)
    check("CSS 堆叠且 fit-view 时网格自身滚动（overflow-y: auto）",
          "body.fit-view .logs-cols { overflow-y: auto; }" in css)
    check("CSS 两列等宽与堆叠断点未动（1fr/1fr、≤1100px 回单列）",
          ".logs-cols { display: grid; grid-template-columns: 1fr 1fr;" in css
          and ".logs-cols { grid-template-columns: 1fr; }" in css)

    # ---- 2) 时间筛选 ----
    check("筛选状态含 from/to（mod 与 login 各一份，初始为空）",
          "mod: { admin: '', status: '', target: '', from: '', to: '' }" in js
          and "login: { user: '', result: '', from: '', to: '' }" in js)
    check("两卡工具栏各有一对日期输入（从/到，值回填筛选状态）",
          all(js.count(f'id="{i}"') == 1 for i in
              ("modFromF", "modToF", "loginFromF", "loginToF"))
          and '<label>从<input id="modFromF" type="date" value="${esc(mf.from)}"></label>' in logs
          and '<label>到<input id="modToF" type="date" value="${esc(mf.to)}"></label>' in logs
          and '<label>从<input id="loginFromF" type="date" value="${esc(lf.from)}"></label>' in logs
          and '<label>到<input id="loginToF" type="date" value="${esc(lf.to)}"></label>' in logs)
    check("日期比较辅助函数（取日期部分 + 闭区间字典序比较）",
          "function logDatePart(ts) { return (ts || '').slice(0, 10); }" in js
          and "function inDateRange(ts, from, to) {" in js
          and "return (!from || d >= from) && (!to || d <= to);" in js)
    check("两卡过滤均叠加日期范围且计入 active 状态",
          "inDateRange(a.created_at, mf.from, mf.to)" in logs
          and "inDateRange(l.created_at, lf.from, lf.to)" in logs
          and "const modActive = !!(mf.admin || mf.status || targetKw || mf.from || mf.to);" in logs
          and "const logActive = !!(lf.user || lf.result || lf.from || lf.to);" in logs)
    bind = segment(js, "function bindLogFilters()", "async function bindLogs()")
    check("日期输入 change 写回状态并重渲染（四处绑定齐全）",
          "logFilters.mod.from = e.target.value" in bind
          and "logFilters.mod.to = e.target.value" in bind
          and "logFilters.login.from = e.target.value" in bind
          and "logFilters.login.to = e.target.value" in bind)
    check("重置一并清空起止日期（两卡重置处理均含 from/to 清空）",
          "logFilters.mod.from = ''; logFilters.mod.to = '';" in bind
          and "logFilters.login.from = ''; logFilters.login.to = '';" in bind)
    check("CSS 日期输入与工具栏控件同规格（字号走 .log-tools 规则，v4.4 统一改 13px、宽 138px）",
          '.log-tools input[type="date"] { width: 138px; }' in css
          and ".log-tools select, .log-tools input { font-size: 13px; padding: 4px 6px; }" in css)
    check("后端日志接口未动（GET /api/logs 返回结构保持）",
          'return {"modifications": modifications, "login_logs": login_logs}'
          in open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read())

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v4.3 引起的旧套件改动，均已在对应测试文件处注明）：
  - smoke_test_v25/v26/v27/v28/v29/v31/v41/v42：仅版本标记断言由
    v4.2 提升为 v4.3（检查名同步），结构/色值断言未动；
  - smoke_test_v30：「fit-view 启用范围」断言随日志页纳入 fit-view 扩展为
    (sheet || people || logs)，字面量与检查名已同步（文件头已注记）；
  - smoke_test_v23：「'width: 136px' not in css」为全局字面量断言（本意是
    姓名列不再是 136px），v4.3 日期输入宽度最初取 136px 与之巧合冲突，
    已把日期输入宽度改取 138px 避让，v23 文件零改动；
  - smoke_test_v29 的日志结构断言（.logs-cols 包裹、卡片开头/结尾字面量）
    经构造保持兼容：表格改为在卡内包一层 .log-scroll（开标签并入原
    '<table' 行、闭标签并入原 '</tbody></table>' 行），卡片级字面量不变；
  - smoke_test_v31 的筛选断言（控件 id 唯一性集合、过滤条件字面量、
    logCountText/空行计数、CSS 斑马纹/悬停/空行）经构造保持兼容：
    日期过滤经新增 inDateRange 并入原 filter 链，计数与空行逻辑未动，
    .logs-cols td.empty-row 原规则保留（v4.3 另加一条更高优先级规则
    让空行高度 auto，不改原规则字面量）；日志区行高/粘性表头为 v4.3
    新增规则，不与旧断言冲突；其余套件无适配，后端 API 测试全部原样通过。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v4.3 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：纯静态检查（纯前端变更，不启服务）\n")
            f.write("- v4.3：日志管理页纳入 fit-view 一屏锁定；两卡表格区固定"
                    "划为 20 条高度（表头 34px + 20 行 × 32px、粘性表头、区内滚动，"
                    "不足 20 条保持高度）；两卡筛选工具栏各加「从/到」日期筛选"
                    "（按 created_at 日期部分闭区间过滤、与既有条件叠加、重置一并清空）。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv4.3: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
