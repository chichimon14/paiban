# -*- coding: utf-8 -*-
"""示例科室排班系统 v2.3 冒烟测试（静态检查 + 一屏拟合数学验证，追加到 SMOKE_TEST.md）。

v2.3 为纯布局改版（无 API/规则变化），覆盖：
- 桌面一屏自适应：排班表页 fit-view 锁高 + fitGrids() 按可用高度计算 --cellh；
- 保存/提交/导出/生成图片按钮并入排班表标题行，成员页独立工具条卡片已删除；
- 姓名列宽 136px（v2.3 时），两字名与三字名等宽（.nm-eq 固定 3em + 两端对齐）；
  【v2.6 适配】姓名列为让职务/组别标签单行已加宽：桌面 176px、641~900px
  112px、<=640px 104px，下方相关断言与宽度核算已同步更新（见各检查项备注）；
  【v4.2 适配】可读性放大（标签 11px、姓名 13px@移动端）后移动端姓名列再
  加宽：641~900px 132px、<=640px 124px（桌面仍 176px），符号字号钳制与
  弹层宽度断言同步更新（见各检查项备注）；
- 移动端适配：<=900px 顶栏塌缩；641~900px（平板/手机横屏）fixed 布局整宽平分一屏；
  <=640px 竖屏整宽平分会让日期列只剩约 6px（符号比列宽还宽、不可读），故竖屏保留
  适度横向滚动（日期列 22px、类别/姓名列 sticky）；横屏矮屏再加极致紧凑整页一屏。

拟合公式（与 frontend/app.js fitGrids 及 style.css 高度公式严格对应）：
  表格总高 = 表头(mul*cellh + const) + 人员行*cellh + 统计行*(0.45*cellh + 8) + 边框冗余
  桌面：mul=0.5, const=18，钳制 [26, 54]；横屏 compact：mul=0.3, const=10，钳制 [18, 54]。
  运行时 fitGrids 直接量取 flex 容器的真实可用高度，下面的 chrome 常量仅为离线模型估算。
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


def segment(js, start_marker, end_marker):
    a = js.index(start_marker)
    b = js.index(end_marker, a)
    return js[a:b]


def main():
    js = open(os.path.join(ROOT, "frontend", "app.js"), encoding="utf-8").read()
    css = open(os.path.join(ROOT, "frontend", "style.css"), encoding="utf-8").read()
    html = open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8").read()

    member = segment(js, "function viewMemberSheet", "function bindMemberSheet")
    admin_sheet = segment(js, "function viewSheetAdmin", "function exportXlsx")

    # ---------- 标题行按钮合并 ----------
    check("成员页已删除独立工具条卡片（无旧 toolbar 卡片结构）",
          '<div class="card"><div class="toolbar-row"' not in member)
    check("成员页标题行含保存/提交/导出/生成图片四个按钮",
          all(s in member for s in ('sheetTitleRow', 'id="saveDraftBtn"', 'id="submitBtn"', 'EXPORT_BTNS'))
          and 'sheet-title-row' in js and 'id="expXlsx"' in js and 'id="expImg"' in js)
    # v2.5 适配：用户要求删除网格下方全部图例，sheetCardHTML 的图例区（sheet-legend）
    # 已整体移除，故此处只断言进度卡瘦身与排班表卡片结构仍在。
    check("成员页进度卡已瘦身（card slim progress-card）且排班表卡片结构在（图例区已按 v2.5 删除）",
          'card slim progress-card' in member and 'sheetCardHTML' in member)
    check("管理员排班表导出按钮并入标题行（无独立 toolbar 卡）",
          'sheetTitleRow' in admin_sheet and 'toolbar-row' not in admin_sheet
          and 'EXPORT_BTNS' in admin_sheet)

    # ---------- 姓名列紧凑 + 等宽 ----------
    check("网格姓名使用等宽类 nm-eq（app.js）", 'nm-name nm-eq' in js)
    check("nm-eq 等宽实现（3em + 两端对齐，姓名色类共存）",
          '.nm-eq' in css and 'width: 3em' in css and 'text-align-last: justify' in css)
    # v2.6 适配：姓名列为标签单行由 136px 加宽到 176px（原断言为 v2.3 的 136px）
    check("姓名列宽 176px（v2.6 为标签单行加宽，原 v2.3 为 136px）",
          'width: 176px' in css and 'width: 136px' not in css)

    # ---------- 一屏自适应机制 ----------
    check("--cellh 自适应机制（CSS 变量 + fitGrids 写入 + var 消费）",
          '--cellh: 54px' in css and 'var(--cellh' in css
          and 'function fitGrids' in js and "setProperty('--cellh'" in js)
    check("排班表页一屏锁高（fit-view + 100dvh + resize 监听）",
          'fit-view' in js and 'fit-view' in css and '100dvh' in css
          and "addEventListener('resize', scheduleFit)" in js)
    # v4.2 适配：符号字号钳制由 13~18px 抬到 14~19px（可读性），高度公式不变
    check("单元格/表头/统计行高度公式与拟合模型一致",
          'calc(var(--cellh, 54px) * 0.5 + 18px)' in css
          and 'calc(var(--cellh, 54px) * 0.45 + 8px)' in css
          and 'clamp(14px, calc(var(--cellh, 54px) * 0.34), 19px)' in css)

    # ---------- 移动端适配 ----------
    check("viewport meta 存在", 'name="viewport"' in html and 'width=device-width' in html)
    check("<=900px 顶栏塌缩；641~900px 月历 fixed 整宽平分",
          '@media (max-width: 900px)' in css and 'flex-direction: row' in css
          and '@media (max-width: 900px) and (min-width: 641px)' in css
          and 'table-layout: fixed' in css)
    # v2.6 适配：<=640px 姓名列为标签单行由 84px 加宽到 104px；
    # v4.2 适配：标签/姓名放大后进一步加宽到 124px
    check("<=640px 竖屏规则（星期隐藏、姓名列 124px sticky、保留横向滚动保底）",
          '@media (max-width: 640px)' in css and 'min-width: 124px' in css)
    check("横屏矮屏 compact 规则（进度卡隐藏、图例隐藏、进度转标题行）",
          '@media (max-width: 900px) and (max-height: 500px)' in css
          and '.progress-card { display: none; }' in css
          and '.st-progress { display: inline; }' in css)
    # v4.2 适配：弹层为容纳放大的选项文字由 300px 放宽到 320px（钳制规则不变）
    check("符号弹层与登录卡移动端宽度（92vw / 视口减边距）",
          'min(320px, 92vw)' in css and 'min(360px, calc(100vw - 32px))' in css)

    # ---------- 拟合数学：桌面成员页 ----------
    # chrome 模型（fit-view 桌面）：主区上距16 + 计划栏(内距16+内容30+下距10)
    # + 进度卡(约80) + 表卡内距32 + 标题行(30+下距10) + 图例(约54) + 主区下距12 ≈ 290
    def grid_total(cellh, mul, const, persons=11, stats=3):
        return (mul * cellh + const) + persons * cellh + stats * (0.45 * cellh + 8) + (1 + persons + stats + 1)

    def fit(avail, mul, const, lo, hi=54.0):
        units = mul + 11 + 3 * 0.45
        fixed = const + 3 * 8 + (1 + 11 + 3 + 1)
        return max(lo, min(hi, (avail - fixed) / units))

    chrome_desktop = 290
    ok_all, detail = True, []
    for vh in (700, 768, 900, 1040):
        avail = vh - chrome_desktop
        cellh = fit(avail, 0.5, 18, 26)
        total = grid_total(cellh, 0.5, 18)
        ok = 26 <= cellh <= 54 and total <= avail + 0.6 and chrome_desktop + total <= vh + 0.6
        ok_all = ok_all and ok
        detail.append(f"{vh}h→cellh {cellh:.1f} 总高 {chrome_desktop + total:.0f}<={vh}")
    check("桌面一屏拟合（700/768/900/1040 高度下 cellh 在 [26,54] 且整页不超视口）",
          ok_all, "；".join(detail))

    # ---------- 拟合数学：手机横屏 850x390 ----------
    # chrome 模型（compact）：顶栏约30 + 主区内距12 + 计划栏约34 + 表卡内距8 + 标题行约28 ≈ 112
    chrome_land = 112
    avail = 390 - chrome_land
    cellh = fit(avail, 0.3, 10, 18)
    total = grid_total(cellh, 0.3, 10)
    check("手机横屏 390 高一屏拟合（cellh>=18 且整页不超视口）",
          cellh >= 18 and chrome_land + total <= 390 + 0.6,
          f"avail={avail} cellh={cellh:.1f} 总高 {chrome_land + total:.0f}<=390")

    # ---------- 宽度核算：横屏整宽平分 / 竖屏滚动保底 ----------
    # 横屏 850px（641~900 规则）：姓名 132 + 合计 30，边框约 34（v2.5 起无类别列，
    # v2.6 姓名列加宽到 112px；v4.2 可读性再加宽到 132px），内容宽 = 850 - 主区
    # 内距 16 - 卡片内距 24 = 810 → 日期列约 20px，可读且不滚动。
    day_w_land = (810 - (132 + 30) - 34) / 30
    check("横屏 850px 整宽平分 30 天（日期列约 20px 可读）",
          day_w_land >= 15, f"日期列约 {day_w_land:.1f}px")
    # 竖屏 390px 若整宽平分日期列仅约 6px（符号 11px 比列宽还宽，不可读），
    # 故 <=640px 不用 fixed 布局：日期列保持基础 min-width 22px、横向滚动、姓名列 sticky。
    check("竖屏保底：日期列 min-width 22px 且无 fixed 布局强制（<=640 规则不含 table-layout）",
          'min-width: 22px' in css
          and 'table-layout: fixed' not in css.split('@media (max-width: 640px)')[1].split('@media')[0],
          "竖屏横向滚动查看，类别/姓名列固定左侧")

    return 0 if all(r[1] for r in results) else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v2.3 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：静态检查（frontend/app.js、style.css、index.html）+ 一屏拟合数学模型验证，无 API 变更\n")
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv2.3: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
