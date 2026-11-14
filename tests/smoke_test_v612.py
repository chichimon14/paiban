# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.12 冒烟测试（追加到 SMOKE_TEST.md 的 v6.12 章节）。

v6.12 变更（2026-11-01 用户追加反馈，纯前端布局移动、后端与 API
零改动）：成员「当日排班」页（v6.9）的「生成图片」按钮（v6.10 加）
原来位于日期控件行右端（margin-left:auto 推到最右），现移到
「时段预览（早/晚班）」标题同一行、紧贴标题文字右侧——与岗位
显示卡片的 .post-line 排布同款（flex 行、垂直居中、h4 去外边距）。

实现口径：
  - 按钮不再由页面骨架 viewDayView 渲染，而是随 dayViewHTML 的
    ok 分支渲染进标题行；noplan/none 两条早退分支在标题行之前
    返回，按钮天然只在已保存排班（status=ok）时出现，加载中
    （dayviewBody 被替换为「正在加载…」）时按钮随旧内容一并消失
    ——v6.10 的可见性门控语义不变，只是不再靠 display 显隐切换；
  - 点击绑定改按 loadMyPosts/mpImgBtn 同款模式：loadDayView 在
    body.innerHTML = dayViewHTML(out) 之后补绑一次；innerHTML
    每次整段替换，旧按钮连同旧监听一并销毁，不会重复出现、
    不会叠加监听（全文件按钮标记与绑定语句各仅一处）；
  - dayviewState 的切日期先清（防串日导出）与 dayViewImage 内
    的 status 兜底校验原样保留；导出内容/文件名/机制零改动；
  - 管理员「生成当日排班」编辑页的 dailyImgBtn 不在本次范围，
    原样不动。

测试口径（纯静态检查，前端文件）：
  S) 版本标记；按钮已离开日期控件行且控件本身完整；按钮标记
     位于 dayViewHTML 的 post-line 标题行内、紧随 h4 标题之后，
     且位于 noplan/none 早退分支之后（仅 ok 分支可达）；按钮
     标记与绑定语句全文件各仅一处（不重复/不叠加）；绑定位于
     loadDayView 渲染语句之后、bindDayView 已无该绑定；门控
     （切日期先清状态）与 dayViewImage 兜底仍在；管理员编辑页
     的 dailyImgBtn 原样在位。
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
    i = text.index(start)
    return text[i:text.index(end, i)]


def main():
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()

    check("S app.js 带 v6.12 版本标记", "/* duty-roster v6.31 */" in js)

    view_seg = segment(js, "function viewDayView()", "function bindDayView()")
    bind_seg = segment(js, "function bindDayView()", "async function loadDayView()")
    load_seg = segment(js, "async function loadDayView()", "function dayTableHTML")
    html_seg = segment(js, "function dayViewHTML(out)", "async function dayViewImage()")
    exp_seg = segment(js, "async function dayViewImage()", "/* ---------------- 路由")

    # ---- 按钮离开日期控件行 ----
    check("S 按钮已不在日期控件行、日期控件本身完整（前一天/日期/后一天/回到今天）（v6.15 适配：回跳按钮改 dvToday/回到今天）",
          'id="dvImgBtn"' not in view_seg
          and 'id="dvPrev"' in view_seg and 'id="dvDate"' in view_seg
          and 'id="dvNext"' in view_seg and 'id="dvToday"' in view_seg)

    # ---- 按钮位于时段预览标题行 ----
    row = ('<div class="post-line"><h4 style="margin:0">时段预览（${esc(out.shift_label || \'\')}）</h4>'
           '<button id="dvImgBtn">生成图片</button></div>')
    check("S 按钮标记位于「时段预览」标题行内（.post-line flex 行、紧贴 h4 标题右侧）",
          row in html_seg
          and html_seg.index('时段预览（') < html_seg.index('id="dvImgBtn"'))
    check("S 按钮仅在 ok 分支可达（位于 noplan/none 两条早退分支之后渲染）",
          html_seg.index('id="dvImgBtn"') > html_seg.index("status === 'noplan'")
          and html_seg.index('id="dvImgBtn"') > html_seg.index("status === 'none'")
          and html_seg.index('id="dvImgBtn"') > html_seg.index("当日排班尚未生成"))
    check("S 按钮标记全文件仅一处（重复渲染不会堆出多个按钮）",
          js.count('id="dvImgBtn"') == 1, f"count={js.count('id=\"dvImgBtn\"')}")

    # ---- 绑定：渲染后补绑、仅一处、不叠加 ----
    bind_stmt = "const im = $('dvImgBtn'); if (im) im.addEventListener('click', dayViewImage);"
    check("S 绑定已随渲染走（loadDayView 在 innerHTML 渲染后补绑、bindDayView 不再含该绑定）",
          bind_stmt in load_seg and "dvImgBtn" not in bind_seg
          and load_seg.index("body.innerHTML = dayViewHTML(out);") < load_seg.index(bind_stmt))
    bind_count = js.count("addEventListener('click', dayViewImage)")
    check("S 绑定语句全文件仅一处（监听不叠加）",
          bind_count == 1, f"count={bind_count}")

    # ---- 门控与导出兜底不变 ----
    check("S loadDayView 门控不变：切日期先清 dayviewState、数据回来后才赋值",
          "dayviewState = null;" in load_seg and "dayviewState = out;" in load_seg
          and load_seg.index("dayviewState = null;") < load_seg.index("dayviewState = out;")
          and "ib.style.display" not in load_seg)
    check("S dayViewImage 状态兜底与导出内容不变（非 ok 不导出、导出段无按钮标记）",
          "if (!out || out.status !== 'ok')" in exp_seg
          and "dvImgBtn" not in exp_seg
          and "dayTableExportHTML(out)" in exp_seg)

    # ---- 管理员编辑页不受影响 ----
    check("S 管理员「生成当日排班」页的图片按钮原样不动（dailyImgBtn 仍在编辑页渲染路径）",
          '<button id="dailyImgBtn" ' in js and "dailyImgBtn" not in html_seg
          and "dailyImgBtn" not in load_seg)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v6.12 引起的旧套件改动）：
  - 全部旧套件：版本标记断言由 v6.11 提升为 v6.12（仅标记字面量）；
  - smoke_test_v610.py 三项断言适配（按钮位置/绑定/门控）：
    ①「按钮位于日期控件行右端且初始隐藏」改为钉按钮已离开控件
    行、控件本身完整；②「按钮绑定在位」改为钉绑定已由
    bindDayView 移到 loadDayView 渲染后补绑（同一语句字面量，
    改查 load 段且 bind 段无 dvImgBtn）；③「loadDayView 门控」
    改为钉先清 dayviewState 的顺序与显隐切换语句（ib.style.display）
    退役——门控改由 dayViewHTML 渲染分支天然保证（仅 ok 分支
    渲染标题行与按钮），本套件（v6.12）另有「按钮仅在 ok 分支
    可达」的结构断言兜住；检查名均已注明 v6.12 适配；
  - smoke_test_v69.py 逐项核查：其 dayview 段断言（无编辑控件、
    日期控件在位、空态文案、带班/退税行）不引用 dvImgBtn，
    本次移动后原样成立；
  - 后端零改动：dayview 响应结构不变，v69 的数据断言不受影响。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.12 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：纯静态检查（前端文件）——本次为呈现层布局移动，后端与 API 零改动\n")
            f.write("- v6.12：成员「当日排班」页「生成图片」按钮由日期控件行右端移入「时段预览」"
                    "标题行右侧（随 dayViewHTML 的 ok 分支渲染、.post-line flex 排布），"
                    "绑定改随 loadDayView 渲染后补绑；门控与导出内容不变，管理员编辑页不受影响。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.12: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
