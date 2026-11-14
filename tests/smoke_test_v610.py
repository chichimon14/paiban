# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.10 冒烟测试（追加到 SMOKE_TEST.md 的 v6.10 章节）。

v6.10 变更（2026-11-01 用户追加反馈，纯前端呈现层、后端与 API 零改动）：
  1) 岗位显示：时段表「同岗同事」列去掉冗余前缀——列头已写明
     「同岗同事」，单元格原来渲染「同岗：CCC」，现只写同事姓名
     本身（多人仍以「、」连接，无同岗仍为「—」）。前缀同时存在于
     页面渲染（myShiftCardHTML）与个人「生成图片」（myPostsImage）
     两条路径，本次两处一并修。注意：退税岗的两行独立说明文字
     （页面 hint 与导图中的「同岗：X」）不是表格列、没有列头，
     前缀即标签本身，按本次口径保留不动。
  2) 成员「当日排班」页（v6.9）加「生成图片」：按钮位于日期控件
     行右端（margin-left:auto），仅当前显示的是已保存排班
     （status=ok）时才出现；导出走既有离屏 DOM + html2canvas
     机制（白底卡片），内容 = 居中标题「{M}月{D}日 当日排班
     （早/晚班）」+ 带班行 + 完整时段表（与页面同列同注记）+
     晚班退税岗行，不含日期控件与任何按钮；文件名沿用既有
     风格「当日排班-{日期}-{班次}.png」。导出数据取自
     dayviewState（loadDayView 成功后暂存），切日期先清空、
     杜绝串日导出。

测试口径（纯静态检查，前端文件）：
  S) 版本标记；Item 1 两条路径的 partners 单元格均已去前缀
     （裸姓名连接式各出现一次、空态仍为「—」），全文件带前缀的
     拼接只剩退税岗独立标签行 2 处；Item 2 按钮在位（控件行右端、
     初始隐藏）、绑定在位、loadDayView 门控（status=ok 才显示、
     切日期先清状态）、dayViewImage 状态兜底与导出内容（标题
     组法/带班/整表/晚班退税行/文件名/离屏机制），且导出函数
     不引用任何日期控件 id（控件不进图）。
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

    check("S app.js 带 v6.10 版本标记", "/* duty-roster v6.31 */" in js)

    # ---- Item 1：同岗同事列去前缀 ----
    post_seg = segment(js, "function myShiftCardHTML", "function myPostsHTML")
    img_seg = segment(js, "function myPostsImageCardHTML", "/* -------- 成员：当日排班")
    bare = "t.partners && t.partners.length ? t.partners.map(esc).join('、') : '—'"
    check("S 页面时段表同岗同事单元格只写姓名（无「同岗：」前缀、多人「、」连、空态「—」）",
          bare in post_seg and "'同岗：' + t.partners" not in post_seg)
    check("S 个人导图时段表同岗同事单元格同样只写姓名（与页面同口径；v6.23 适配：分段起点改 myPostsImageCardHTML 纯函数）",
          bare in img_seg and "'同岗：' + t.partners" not in img_seg)
    check("S 裸姓名连接式在页面与导图各出现且仅出现一次（两条路径全覆盖）",
          js.count(bare) == 2, f"count={js.count(bare)}")
    # v6.11 适配：退税岗同岗行改走模板字面量且仅在有同岗时渲染，
    # 旧的引号拼接式（'同岗：' + others…）已退役，本断言随之改钉模板式。
    check("S 带「同岗：」渲染仅剩退税岗同岗行 2 处（页面 hint + 导图，v6.11 模板式、仅有同岗时出现）",
          js.count("同岗：${others.map(esc).join('、')}") == 2
          and "'同岗：' + others" not in js,
          f"count={js.count('同岗：')}")

    # ---- Item 2：当日排班生成图片 ----
    view_seg = segment(js, "function viewDayView()", "function bindDayView()")
    bind_seg = segment(js, "function bindDayView()", "async function loadDayView()")
    load_seg = segment(js, "async function loadDayView()", "function dayTableHTML")
    exp_seg = segment(js, "async function dayViewImage()", "/* ---------------- 路由")
    check("S 生成图片按钮已离开日期控件行（v6.12 适配：移入时段预览标题行，位置断言见 v6.12 套件；v6.15 适配：回跳按钮改 dvToday）",
          'id="dvImgBtn"' not in view_seg
          and 'id="dvToday"' in view_seg and 'id="dvDate"' in view_seg)
    check("S 按钮绑定在位（dvImgBtn → dayViewImage；v6.12 适配：由 bindDayView 改到 loadDayView 渲染后补绑）",
          "const im = $('dvImgBtn'); if (im) im.addEventListener('click', dayViewImage);" in load_seg
          and "dvImgBtn" not in bind_seg)
    check("S loadDayView 门控：切日期先清 dayviewState（v6.12 适配：按钮随 dayViewHTML 标题行渲染、仅 ok 分支出现，不再显隐切换）",
          "dayviewState = null;" in load_seg and "dayviewState = out;" in load_seg
          and "ib.style.display" not in load_seg
          and load_seg.index("dayviewState = null;") < load_seg.index("dayviewState = out;"))
    check("S dayViewImage 状态兜底：非 ok 状态不导出（函数内再校验一次）",
          "if (!out || out.status !== 'ok')" in exp_seg and "dayviewState" in exp_seg)
    check("S 导出标题组法「{M}月{D}日 当日排班（班次）」+ 带班在位（v6.29 适配：标题行改 flex 左右布局、带班/退税挪到标题行最右边，不再居中标题+独立带班行）",
          "${p.m}月${p.d}日 当日排班（${esc(out.shift_label || '')}）" in exp_seg
          and "justify-content:space-between" in exp_seg
          and "带班：${esc(out.leader_name || '—')}" in exp_seg)
    tbl_seg = segment(js, "function dayTableExportHTML", "async function dayViewImage()")
    check("S 导出含完整时段表（dayTableExportHTML 晚班三列、注记口径同页面）（v6.16 适配：早班列改随 preview 首段岗位名生成（out.preview[0].posts），不再硬编码挑查/备勤列名）",
          "dayTableExportHTML(out)" in exp_seg
          and "审图查验岗" in tbl_seg and "申报岗" in tbl_seg
          and "out.preview[0].posts" in tbl_seg
          and "（各半小时）" in tbl_seg)
    check("S 导出含退税岗行（名单「、」连、无人写「无」；v6.31 适配：所有班次都带、不再 evening 门控）",
          "out.shift === 'evening'" not in exp_seg and "退税岗：${out.tax_names" in exp_seg
          and "join('、') : '无'}" in exp_seg)
    check("S 导出机制与文件名：离屏 holder + html2canvas 白底、「当日排班-{日期}-{班次}.png」",
          "position:fixed;left:-10000px" in exp_seg and "html2canvas" in exp_seg
          and "backgroundColor: '#FFFFFF'" in exp_seg
          and "`当日排班-${out.date}-${out.shift_label || ''}.png`" in exp_seg)
    check("S 导出内容不含日期控件与按钮（控件 id 在导出函数中零出现；v6.15 适配：回跳按钮 id 改 dvToday）",
          "dvDate" not in exp_seg and "dvPrev" not in exp_seg
          and "dvNext" not in exp_seg and "dvToday" not in exp_seg
          and "dvTomorrow" not in exp_seg
          and "dvImgBtn" not in exp_seg)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v6.10 引起的旧套件改动）：
  - 全部旧套件：版本标记断言由 v6.9 提升为 v6.10（仅标记字面量）；
  - smoke_test_v69.py「当日排班视图纯只读」断言适配（v6.10 起
    dayview 新增生成图片，原断言中“无生成图片”与裸词“保存”两项
    已不成立）：改为钉无编辑控件——段内无 <select、无保存接口
    /api/daily/assignments、无 person_id，检查名已注明 v6.10 适配；
    图片按钮的 status=ok 门控断言由本套件（v6.10）负责；
  - v64/v65/v68 的岗位图片断言（mpImgBtn 接线、myPostsImage 段
    内归属文案）逐项核查：本次只删 partners 单元格的前缀拼接、
    未动按钮与绑定语句，断言原样成立；
  - 后端零改动：mine/dayview 响应结构不变，v68/v69 的数据断言
    不受影响。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.10 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：纯静态检查（前端文件）——本次为呈现层改动，后端与 API 零改动\n")
            f.write("- v6.10：①岗位显示时段表「同岗同事」列去掉「同岗：」前缀（页面 + 个人导图两条路径），"
                    "退税岗独立标签行保留；②成员「当日排班」页加「生成图片」（仅已保存排班显示，"
                    "导出标题/带班/整表/晚班退税岗，不含页面控件）。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.10: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
