# -*- coding: utf-8 -*-
"""示例科室排班系统 v2.8 冒烟测试（追加到 SMOKE_TEST.md 的 v2.8 章节）。

v2.8 变更（单点、纯前端）：符号选择层改贴锚点格右侧弹出（用户看 v2.7 截图
反馈：弹层左上角应落在选中格子的右上角/右下角，更美观）。placePicker 重写为：
  1) 水平优先右侧 left = rect.right + 2；放不下翻左侧 left = rect.left - w - 2；
     两侧都不行（窄屏）才钳制回视口 [M, vw-w-M] 兜底；
  2) 垂直优先上缘对齐 top = rect.top；下方超出改下缘对齐 top = rect.bottom - h；
     再越界钳制到距顶 M，配合 .picker 的 max-height + overflow-y:auto 层内滚动
     保证全部选项可达（v2.7 的可达性保障不变）。
本套件为纯静态检查（不启服务）：新定位算法的四条分支与钳制都在代码中、
版本标记 v2.8、openPicker 调用方式不变、.picker 滚动兜底 CSS 仍在。

【v2.9 适配（2026-10-31）】v2.9 不触及选择层定位，仅版本标记断言提升为 v2.9。
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

    seg = segment(js, "function placePicker", "function openPicker")
    check("placePicker 存在且 openPicker 仍传入锚点格矩形",
          "function placePicker" in js
          and "placePicker(picker, anchor.getBoundingClientRect())" in js)
    check("水平优先右侧：left = rect.right + 2",
          "let left = rect.right + 2;" in seg)
    check("右侧放不下翻左侧：left = rect.left - w - 2（溢出判定 left + w > vw - M）",
          "left = rect.left - w - 2;" in seg and "left + w > vw - M" in seg)
    check("两侧都不行才钳制回视口：Math.min(rect.right + 2, vw - w - M) + Math.max(M, …)",
          "Math.min(rect.right + 2, vw - w - M)" in seg and "Math.max(M," in seg)
    check("垂直优先上缘对齐：top = rect.top",
          "let top = rect.top;" in seg)
    check("下方超出改下缘对齐：top = rect.bottom - h（判定 top + h > vh - M）",
          "top = rect.bottom - h;" in seg and "top + h > vh - M" in seg)
    check("下缘对齐仍越界则钳制到距顶 M：if (top < M) top = M",
          "if (top < M) top = M;" in seg)
    check("旧 v2.7 正下方定位已移除（无 rect.bottom + 2 / rect.top - h - 2）",
          "rect.bottom + 2" not in seg and "rect.top - h" not in seg)

    picker_rule = segment(css, ".picker {", "}")
    check(".picker 滚动兜底不变（position:fixed + max-height: calc(100dvh - 16px) + overflow-y: auto）",
          "position: fixed" in picker_rule
          and "max-height: calc(100dvh - 16px)" in picker_rule
          and "overflow-y: auto" in picker_rule)

    return 0 if all(r[1] for r in results) else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v2.8 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：纯静态检查（纯前端变更，不启服务）\n")
            f.write("- v2.8：placePicker 改为贴锚点格右侧弹出——水平右侧优先/翻左侧/窄屏钳制，"
                    "垂直上缘对齐/下缘对齐/钳制到顶；.picker 层内滚动兜底不变。\n")
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv2.8: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
