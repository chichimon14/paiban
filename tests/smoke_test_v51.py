# -*- coding: utf-8 -*-
"""示例科室排班系统 v5.1 冒烟测试（追加到 SMOKE_TEST.md 的 v5.1 章节）。

v5.1 变更（纯前端：frontend/app.js + style.css；后端/数据库未动）：
用户手机端需求——成员/人员管理员排班表加「只看本人」开关，开启后
网格只留日期表头 + 本人一行 + 三行在岗统计 + 本人合计，一屏可操作。
按钮形态经用户两轮定版：① 圆形图标按钮、无文字——直径 34px 圆形，
内嵌单人头像 SVG（头+肩，currentColor）；未开启普通描边，开启填充
主题渐变（--grad，青→蓝→紫）、图标变白；② 不要 title 属性（避免
手机长按弹出提示气泡），仅保留 aria-label；按钮用途改在进度卡
操作提示（hintText 可编辑态那条）里加一句说明。位置：标题行左区、
紧贴「保存」左侧（顺序：只看本人 | 保存 | 提交）；仅手机端显示
（<=760px，或横屏矮屏 <=900px 且高度 <=500px），桌面 DOM 占位保序。
实现：模块级 onlyMeMode（点选重渲染不重置）+ gridHTML 新增
onlyPersonId 纯显示过滤（行循环内跳过他人行）；统计 localDayStats /
有效网格 effectiveGridMap / 每日上限预检 checkDailyCaps 均按全员
数据计算、不引用该过滤；人员管理员已暂存的 adminEdits 不因切换丢失
（切换只翻转状态并重渲染，不触碰两张暂存表）；账号无对应人员
（mine==null）与超管合并页不渲染此按钮。行高拟合 fitGrids 本就按
DOM 实际渲染行数（tbody tr:not(.stats)）计 units、cellh 上限 54px，
过滤后自动按 1 人行拟合，无需改动。本套件为纯静态检查（不启服务）。
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

    check("app.js 带 v5.2 版本标记", "/* duty-roster v6.31 */" in js)

    # ---- 1) 状态与切换 ----
    check("模块级状态 onlyMeMode（默认 false，重渲染不重置）",
          "let onlyMeMode = false;" in js)
    bind_seg = segment(js, "function bindMemberSheet", "function viewSheetAdmin")
    check("bindMemberSheet 绑定切换（翻转状态 + renderRoute，不清暂存表）",
          "onlyMeMode = !onlyMeMode" in bind_seg
          and "draftEdits.clear()" not in segment(bind_seg, "onlyMeBtn", "saveDraftBtn")
          and "adminEdits.clear()" not in segment(bind_seg, "onlyMeBtn", "saveDraftBtn"))

    # ---- 2) 圆形图标按钮本体：SVG、无文字、无 title、aria-label 随态 ----
    btn_seg = segment(js, "function onlyMeBtnHTML", "/* ---------------- 视图：排班表")
    check("onlyMeBtnHTML 存在且含 id=onlyMeBtn 与内嵌 SVG 人像（circle+path）",
          "function onlyMeBtnHTML" in js and 'id="onlyMeBtn"' in btn_seg
          and "<svg" in btn_seg and "<circle" in btn_seg and "<path" in btn_seg)
    check("按钮无 title 属性（避免手机长按弹出提示）", "title=" not in btn_seg)
    check("按钮无可见文字标签（SVG 后直接闭合 button）",
          "</svg></button>" in btn_seg and ">只看本人<" not in btn_seg
          and ">显示全员<" not in btn_seg)
    check("aria-label / aria-pressed 随状态（只看本人 ⇄ 显示全员）",
          'aria-label="${label}"' in btn_seg and "onlyMeMode ? '显示全员' : '只看本人'" in btn_seg
          and 'aria-pressed="${onlyMeMode}"' in btn_seg
          and "only-me-btn${onlyMeMode ? ' on' : ''}" in btn_seg)

    # ---- 3) 位置与接入：左区、紧贴保存左侧；两处 gridHTML 传过滤 ----
    view_seg = segment(js, "function viewMemberSheet", "function bindMemberSheet")
    i_btn = view_seg.find("onlyMeBtnHTML() +")
    i_save = view_seg.find("saveDraftBtn")
    check("可编辑分支：按钮在左区且位于「保存」之前（只看本人 | 保存 | 提交）",
          0 <= i_btn < i_save, f"btn@{i_btn}, save@{i_save}")
    check("可编辑分支 gridHTML 传 onlyPersonId（onlyMeMode ? mine.id）",
          "onlyPersonId: onlyMeMode ? mine.id : null" in view_seg)
    check("已发布分支：按钮在已发布 chip 前（mine 存在才渲染）+ display_grid 同传过滤",
          "(mine ? onlyMeBtnHTML() : '')" in view_seg
          and "onlyPersonId: onlyMeMode && mine ? mine.id : null" in view_seg)
    check("账号无对应人员分支不渲染按钮（mine==null 段内无 onlyMeBtnHTML 调用）",
          "onlyMeBtnHTML" not in segment(view_seg, "您的账号未对应具体人员", "const locked"))

    # ---- 4) gridHTML 纯显示过滤；统计/预检不受影响 ----
    grid_seg = segment(js, "function gridHTML", "function bindGridCells")
    check("gridHTML 按 onlyPersonId 跳过他人行（行循环内 return）",
          "if (opts.onlyPersonId && person.id !== opts.onlyPersonId) return;" in grid_seg)
    check("localDayStats 不引用只看本人过滤（统计按全员数据）",
          "onlyPersonId" not in segment(js, "function localDayStats", "/* 点选时每日上限预检")
          and "onlyMeMode" not in segment(js, "function localDayStats", "/* 点选时每日上限预检"))
    check("effectiveGridMap 不引用只看本人过滤（有效网格按全员数据）",
          "onlyPersonId" not in segment(js, "function effectiveGridMap", "/* 本地每日统计")
          and "onlyMeMode" not in segment(js, "function effectiveGridMap", "/* 本地每日统计"))
    # v6.3 适配：checkDailyCaps 增加可选 gridMap/statsArr 参数（最终表改班
    # 口径），缺省仍走 localDayStats(gridMap) 的草稿全员口径——原断言钉的
    # 字面量 "localDayStats().find" 随之更新；「不受显示过滤影响」的口径
    # 改以函数段内不引用 onlyMeMode/onlyPersonId 继续钉死。
    check("checkDailyCaps 仍按 localDayStats 全员口径（预检不受显示过滤影响）",
          "localDayStats(gridMap)).find" in segment(js, "function checkDailyCaps", "/* ---------------- v2.5")
          and "onlyMeMode" not in segment(js, "function checkDailyCaps", "/* ---------------- v2.5")
          and "onlyPersonId" not in segment(js, "function checkDailyCaps", "/* ---------------- v2.5"))

    # ---- 5) 超管页无此按钮 ----
    admin_seg = segment(js, "function viewSheetAdmin", "function exportXlsx")
    check("超管合并页不含 onlyMeBtn（viewSheetAdmin 段内无引用）",
          "onlyMeBtn" not in admin_seg and "onlyPersonId" not in admin_seg)

    # ---- 6) 提示文案含圆形按钮说明（可编辑态 hint） ----
    check("进度卡操作提示含圆形按钮说明句",
          "点保存左侧的圆形人像按钮，可只看自己一行排班，再点一次恢复全员。" in view_seg)

    # ---- 7) CSS：圆形几何 + 开启态渐变 + 仅手机端显示 ----
    btn_rule = segment(css, ".only-me-btn {", "}")
    check("圆形几何（34px 直径 + border-radius: 50% + 默认隐藏）",
          "width: 34px" in btn_rule and "height: 34px" in btn_rule
          and "border-radius: 50%" in btn_rule and "display: none" in btn_rule,
          btn_rule.strip()[:90])
    check("标题行内 padding 归零（压过 .sheet-title-row button 通用内距）",
          ".sheet-title-row .only-me-btn { padding: 0; }" in css)
    on_rule = segment(css, ".only-me-btn.on {", "}")
    check("开启态填充主题渐变 + 图标变白（background: var(--grad) + color: #fff）",
          "background: var(--grad)" in on_rule and "color: #fff" in on_rule)
    mq = "@media (max-width: 760px), (max-width: 900px) and (max-height: 500px)"
    mq_seg = segment(css, mq, "}\n")
    check("仅手机端显示（<=760px 或横屏矮屏段内 display: inline-flex）",
          mq in css and ".only-me-btn { display: inline-flex; }" in mq_seg)

    # ---- 8) fitGrids 按实际渲染行数拟合（过滤后自动适配，无需改公式） ----
    fit_seg = segment(js, "function fitGrids", "let fitTimer")
    check("fitGrids 按 DOM 实际人员行数计 units 且 cellh 上限 54px（<=约56 舒适上限）",
          "tbody tr:not(.stats)" in fit_seg and "Math.min(54, cellh)" in fit_seg)

    # ---- 9) 后端未动 ----
    check("后端未动（main.py 无 v5.1 标记）", "v5.1" not in backend)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v5.1 引起的旧套件改动，均已在对应测试文件处注明）：
  - 全部套件（v25–v50）：仅版本标记断言由 v5.0 提升为 v5.1，其余断言未动；
  - 按钮形态说明：原 brief 的文字按钮方案经用户两轮改版作废——终版为
    圆形图标按钮（无文字、无 title、aria-label 保留），用途说明移入
    进度卡操作提示文案；本套件按终版断言（无 title / 含说明句）。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v5.1 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：纯静态检查（纯前端功能，不启服务）\n")
            f.write("- v5.1：成员/人员管理员排班表新增「只看本人」开关（手机端）："
                    "圆形图标按钮（34px、单人头像 SVG、无文字无 title、"
                    "aria-label 随态）位于标题行左区「保存」左侧，仅手机端"
                    "显示（<=760px 或横屏矮屏段）；开启后 gridHTML 以 "
                    "onlyPersonId 纯显示过滤只渲染本人一行（表头/三行在岗"
                    "统计/合计不变），统计与每日上限预检仍按全员数据；"
                    "模块级 onlyMeMode 跨重渲染保持，切换不触碰暂存修改；"
                    "fitGrids 按实际渲染行数拟合、行高上限 54px 自动适配。"
                    "后端与数据库未触碰。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv5.1: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
