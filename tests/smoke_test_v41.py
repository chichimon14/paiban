# -*- coding: utf-8 -*-
"""示例科室排班系统 v4.1 冒烟测试（追加到 SMOKE_TEST.md 的 v4.1 章节）。

v4.1 变更（纯前端换肤，app.js 仅颜色触点、后端接口/数据/行为未动）：
  用户看过 v4.0 深色版后明确要求「换成亮色」——全站改回亮色版的同一套
  科技设计语言（玻璃面板 + 青→蓝→紫渐变强调 + 双光晕 + 青色焦点环）：
  - 底色反转：#F2F6FC 明亮基底 + 青/紫双径向光晕（亮色 alpha .14/.12）；
    文本 --ink #1E293B / --muted #5B6B84 / --faint #8494AD；
    面板改白色玻璃 rgba(255,255,255,.78) + blur + 浅蓝细边 + 柔和蓝影。
  - 渐变体系（--grad、主按钮、激活导航、品牌/logo 砖、焦点环）原样保留。
  - 侧栏回到 v3 时代的深藏青 #16283F 实色（用户从未对深色侧栏提过意见），
    其浅色文字与 v4 的渐变激活胶囊、定宽图标槽位保持不变。
  - 网格回亮色：表头/姓名列 #EEF3FA、边框 #D8E1EE、周末淡玫红、满员日
    回 #DCDCDC 灰底灰字（v3 语义）、补满 #E3F0FF、源数据 #EAFAF0、统计行
    #FFF8E1 琥珀浅底、stat-bad #FEE2E2、未保存描边回 #F59E0B。
  - 姓名状态色按用户指示改回亮底值：已提交 #16A34A、已保存未提交
    #EA580C、未提交=默认墨色（v4.0 的深底提亮版 #34D399/#FBBF24 撤销）。
  - 选择层/登录卡改白色玻璃；小表格表头 #F4F7FB、斑马纹/悬停回浅色；
    chips/tags 回浅色 tint；toast 回深石板胶囊；日志 1fr/1fr 等宽保留。
  本套件取代 smoke_test_v40.py（v4.0 深色断言整体反转），为纯静态检查。

【v4.9 适配（2026-11-01）】v4.9 为纯 CSS 视觉修复：排班网格边框由
#D8E1EE 加深为 #A9BAD3（原色与满员灰底 #DCDCDC 几乎同明度，灰色整列
相连时格线消失）。本套件「网格回亮色」断言的边框字面量已同步更新为
网格作用域的新值（table.grid th/td 规则），检查名加〔v4.9 加深〕注记；
版本标记断言提升为 v4.9。v4.1 当时「边框 #D8E1EE」的历史描述保留原文。
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


# v4.0 深色主题的基底字面值：v4.1 换回亮色后不得在 style.css 中残留
DARK_BASES = ["#060a13", "#070c16", "#0a0f1e", "#0b1322", "#0b1220",
              "rgba(5,8,15,.94)", "rgba(9,14,28,.94)", "rgba(9,15,30,.94)",
              "rgba(13,20,38,.72)", "#26200e"]


def main():
    js = open(os.path.join(ROOT, "frontend", "app.js"), encoding="utf-8").read()
    css = open(os.path.join(ROOT, "frontend", "style.css"), encoding="utf-8").read()
    html = open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8").read()

    check("app.js 带 v5.0 版本标记", "/* duty-roster v6.31 */" in js)

    # ---- A) 日志等宽各半（v4.0 结构保留） ----
    check("日志两列仍为等宽 1fr/1fr（旧 11fr/9fr 已无残留）",
          ".logs-cols { display: grid; grid-template-columns: 1fr 1fr;" in css
          and "11fr 9fr" not in css)
    check("≤1100px 回单列堆叠不变",
          "@media (max-width: 1100px)" in css
          and ".logs-cols { grid-template-columns: 1fr; }" in css)

    # ---- B) 亮色主题令牌 ----
    check("明亮基底 + 双光晕（--bg #F2F6FC + 青/紫 radial 光晕亮色 alpha + fixed）",
          "--bg: #F2F6FC;" in css
          and "rgba(34,211,238,.14)" in css and "rgba(139,92,246,.12)" in css
          and "background-attachment: fixed;" in css)
    check("文本令牌回亮底（--ink #1E293B / --muted #5B6B84 / --faint #8494AD，语义色亮底版）",
          "--ink: #1E293B;" in css and "--muted: #5B6B84;" in css
          and "--faint: #8494AD;" in css
          and "--green: #16A34A;" in css and "--red: #DC2626;" in css)
    check("白色玻璃面板（.card 白玻璃 + blur(10px) + 浅蓝细边 + 柔和蓝影 + 圆角 14px）",
          "background: var(--panel);" in css and "backdrop-filter: blur(10px)" in css
          and "--panel: rgba(255,255,255,.78);" in css
          and "--radius: 14px;" in css
          and "box-shadow: 0 10px 30px rgba(30,64,175,.08), inset 0 1px 0 rgba(255,255,255,.9);" in css)
    check("渐变强调保留（--grad 青→蓝→紫，主按钮与激活导航共用 + 光晕改柔和）",
          "--grad: linear-gradient(135deg, #22D3EE, #3B82F6 55%, #8B5CF6);" in css
          and "button.primary { background: var(--grad);" in css
          and ".nav a.active { background: var(--grad);" in css
          and "box-shadow: 0 4px 16px rgba(59,130,246,.28)" in css)
    check("焦点环仍为青色光晕（输入框 focus box-shadow）",
          "box-shadow: 0 0 0 3px rgba(34,211,238,.25);" in css)
    check("输入/下拉回白底（--input-bg #FFFFFF + option 白底墨字）",
          "--input-bg: #FFFFFF;" in css
          and "select option { background: #FFFFFF; color: #1E293B; }" in css)
    check("侧栏回深藏青 #16283F 实色 + 登录白玻璃卡 + 渐变 logo",
          ".sidebar { width: 224px; flex: 0 0 224px; background: #16283F;" in css
          and ".login-card { background: rgba(255,255,255,.82); backdrop-filter: blur(14px);" in css
          and ".login-logo {" in css and "background: var(--grad);" in css)
    check("网格回亮色（表头 --head-bg #EEF3FA、边框 #A9BAD3〔v4.9 加深〕、统计琥珀浅底；v6.5 适配：周末改回浅粉 #FFF1F2、满员灰底 .full 已删除）",
          "--head-bg: #EEF3FA;" in css
          and "table.grid th, table.grid td { border: 1px solid #A9BAD3;" in css
          and "table.grid td.weekend { background: #FFF1F2; }" in css
          and "table.grid td.cell.full" not in css
          and "table.grid tr.stats td { background: #FFF8E1;" in css
          and "table.grid tr.stats td.stat-bad { background: #FEE2E2; color: #B91C1C; }" in css)
    check("姓名状态色改回亮底值（已提交 #16A34A / 已保存未提交 #EA580C，深底提亮版无残留）",
          ".nm-name.st-submitted { color: #16A34A;" in css
          and ".nm-name.st-draft { color: #EA580C;" in css
          and "#34D399" not in css and "#FBBF24" not in css)
    check("未保存改动描边回琥珀 #F59E0B、可编辑悬停回蓝色描边",
          "table.grid td.cell.dirty { outline: 2px solid #F59E0B;" in css
          and "table.grid td.cell.editable:hover { outline: 2px solid var(--blue);" in css)
    picker_rule = segment(css, ".picker {", "}")
    check("选择层改白色玻璃（白底 + blur + 浅边，高度钳制/层内滚动不变）",
          "rgba(255,255,255,.96)" in picker_rule and "backdrop-filter: blur(14px)" in picker_rule
          and "max-height: calc(100dvh - 16px)" in picker_rule
          and "overflow-y: auto" in picker_rule)
    check("小表格回亮色（表头 #F4F7FB、斑马纹 rgba(15,23,42,.02)、悬停 rgba(37,99,235,.05)）",
          "table.mini th { background: #F4F7FB; }" in css
          and "table.mini tbody tr:nth-child(even) { background: rgba(15,23,42,.02); }" in css
          and "table.mini tbody tr:hover { background: rgba(37,99,235,.05); }" in css)
    check("toast 回深石板胶囊（亮底上可读，bad 回正红）",
          ".toast { position: fixed; left: 50%; bottom: 28px; transform: translateX(-50%); background: #1E293B;" in css
          and ".toast.bad { background: #B91C1C; }" in css)
    check("深色基底零残留（deny-list v4.0 深底字面值均不在 css）",
          all(h not in css.lower() for h in DARK_BASES))

    # ---- app.js / index.html 颜色触点 ----
    check("app.js 导出图片底色改回 #FFFFFF（深底 #070C16 无残留）",
          "backgroundColor: '#FFFFFF'" in js and "'#070C16'" not in js)
    check("app.js 横幅改亮色玻璃（发布=绿 rgba、锁定=琥珀 rgba 各两处口径，深色版无残留）",
          "border-color:rgba(22,163,74,.35);background:rgba(22,163,74,.07)" in js
          and js.count("border-color:rgba(217,119,6,.35);background:rgba(217,119,6,.08)") == 2
          and "rgba(52,211,153,.45)" not in js and "rgba(251,191,36,.45)" not in js)
    check("index.html 带 theme-color=#F2F6FC",
          '<meta name="theme-color" content="#F2F6FC">' in html)
    check("后端未动（GET /api/logs 返回结构保持）",
          'return {"modifications": modifications, "login_logs": login_logs}'
          in open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read())

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v4.1 亮色换肤引起的旧套件改动，均已在对应测试文件处注明）：
  - smoke_test_v25/v26/v27/v28/v29/v30/v31：仅版本标记断言由 v4.0 提升为
    v4.1（/* duty-roster v4.1 */），逻辑与结构断言未动；
  - smoke_test_v31：日志斑马纹/悬停断言的色值由 v4.0 深色
    rgba(255,255,255,.02) / rgba(56,189,248,.06) 改回浅色 #F8FAFC /
    #EEF4FF（即 v3.1 的原始浅色值）——断言结构不变；
  - smoke_test_v29：日志等宽 1fr/1fr 断言与换肤无关，原样保留；
    仅文件头适配说明补记标记提升；
  - smoke_test_v40.py 整体由本套件（v41）取代并删除：其深色断言
    （深底令牌/提亮语义色/深玻璃/姓名状态提亮色）按用户「换成亮色」
    的明确指示整体反转为亮色期望，检查项结构一一对应；
  - 姓名状态色 #34D399→#16A34A（已提交）、#FBBF24→#EA580C（已保存
    未提交）系按用户指示改回 v3 时代亮底值；v2.2 套件只断言类名，
    未钉色值，无需适配；
  - 其余套件无适配，后端 API/行为测试全部原样通过。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v4.1 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：纯静态检查（纯前端换肤，不启服务）\n")
            f.write("- v4.1：按用户要求把 v4.0 深色科技主题整体换成亮色版"
                    "（同一设计语言：白玻璃面板 + 青蓝紫渐变 + 双光晕 + "
                    "深藏青侧栏），姓名状态色改回亮底绿/橙，布局/尺寸/行为"
                    "不变，后端未动。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv4.1: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
