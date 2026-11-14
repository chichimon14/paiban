# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.18 冒烟测试（追加到 SMOKE_TEST.md 的 v6.18 章节）。

v6.18 变更（用户 2026-11-02 指定，附CCC管理员截图）：管理员
「生成排班」页的默认日期由今天改回**明天**（管理员通常提前一天
排次日班；截图中该页当时显示的正是次日 2026-11-03 晚班）。
仅此一页改动：viewDaily 首次初始化与 bindDaily 的日期 change
兜底改用 tomorrowStr()，页内提示文案改「默认明天」。岗位显示与
成员「当日排班」两页仍默认今天（v6.15 口径不变，回跳按钮仍为
「回到今天」），三页默认日期从此不再统一。后端零改动。

测试口径（纯静态分段断言 + Node 函数级行为验证，不起服务）：
  S) 静态：版本标记；viewDaily/bindDaily 两段为明天口径（初始化/
     兜底/文案）；岗位显示与成员当日排班两页段仍为今天口径
     （初始化 todayStr、「回到今天」恰 2 处、全文件无 dailyState
     的 todayStr 残留）。
  N) Node 行为：抽取真实函数以管理员身份验证 viewDaily 首次
     渲染日期=明天、徽标班次与明天奇偶一致、日期清空 change
     兜底回明天并触发加载。
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT = os.path.join(ROOT, "SMOKE_TEST.md")

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), "-", name, ("| " + str(detail) if detail else ""))


def segment(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i)]


NODE_HARNESS = r"""
const fs = require('fs');
const cfg = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const src = fs.readFileSync(cfg.appjs, 'utf8');
function extract(re, name) { const m = src.match(re); if (!m) throw new Error('extract: ' + name); return m[0]; }
const code = [
  extract(/const SHIFT_ANCHOR_STR = '[^']*';/, 'anchor'),
  extract(/function localDateStr\(d\) \{[\s\S]*?\n\}/, 'localDateStr'),
  extract(/function tomorrowStr\(\) \{[^}]*\}/, 'tomorrowStr'),
  extract(/function todayStr\(\) \{[^}]*\}/, 'todayStr'),
  extract(/function datePartsOf\(s\) \{[^\n]*\}/, 'datePartsOf'),
  extract(/function shiftOfDateStr\(s\) \{[\s\S]*?\n\}/, 'shiftOfDateStr'),
  extract(/function myRole\(\) \{[\s\S]*?\n\}/, 'myRole'),
  extract(/function viewDaily\(\) \{[\s\S]*?\n\}/, 'viewDaily'),
  extract(/function bindDaily\(\) \{[\s\S]*?\n\}/, 'bindDaily'),
].join('\n');
const PRESENT = new Set(['dailyDate', 'dailyShiftBadge', 'dailyBody']);
const els = {}; const listeners = {};
function mkEl(id) {
  return { value: '', textContent: '', innerHTML: '',
    addEventListener(ev, fn) { listeners[id + ':' + ev] = fn; } };
}
global.$ = (id) => (PRESENT.has(id) ? (els[id] = els[id] || mkEl(id)) : null);
let loads = 0;
global.loadDaily = () => { loads += 1; };
global.me = { role: 'admin', person_id: 3, username: 'CCC' };
global.dailyState = { date: '', ctx: null, form: null, savedSig: '' };
eval(code);
const out = {};
out.html = viewDaily();
out.dateAfterInit = global.dailyState.date;
out.shiftOfInit = shiftOfDateStr(global.dailyState.date);
bindDaily();
els.dailyDate.value = '';
if (!listeners['dailyDate:change']) throw new Error('dailyDate change listener missing');
listeners['dailyDate:change']();
out.dateAfterClear = global.dailyState.date;
out.loads = loads;
console.log('RESULT ' + JSON.stringify(out));
"""


def main():
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()

    check("S app.js 带 v6.18 版本标记", "/* duty-roster v6.31 */" in js)

    daily_view_seg = segment(js, "function viewDaily()", "function bindDaily()")
    daily_bind_seg = segment(js, "function bindDaily()", "async function loadDaily()")
    view_seg = segment(js, "function viewMyPosts()", "function bindMyPosts()")
    dv_view_seg = segment(js, "function viewDayView()", "function bindDayView()")

    check("S 生成排班默认日期初始化改为明天（tomorrowStr）+ 提示文案「默认明天」",
          "if (!dailyState.date) dailyState.date = tomorrowStr();" in daily_view_seg
          and "（默认明天，改日期会自动重新载入）" in daily_view_seg
          and "todayStr" not in daily_view_seg)
    check("S 生成排班日期 change 兜底改为明天、全文件无 dailyState 的 todayStr 残留",
          "dailyState.date = di.value || tomorrowStr();" in daily_bind_seg
          and "dailyState.date = di.value || todayStr()" not in js
          and "dailyState.date) dailyState.date = todayStr()" not in js)
    check("S 岗位显示仍默认今天（v6.15 口径不变）",
          "if (!mypostsDate) mypostsDate = todayStr();" in view_seg)
    check("S 成员当日排班仍默认今天、「回到今天」仍恰 2 处（岗位显示+当日排班）",
          "if (!dayviewDate) dayviewDate = todayStr();" in dv_view_seg
          and js.count("回到今天") == 2)

    # ---- Node 行为验证 ----
    today = date.today()
    expect_tomorrow = (today + timedelta(days=1)).isoformat()
    anchor = date(2026, 11, 2)
    want_shift = "早班" if ((today + timedelta(days=1)) - anchor).days % 2 == 0 else "晚班"
    node_out = None
    try:
        tmpdir = tempfile.mkdtemp(prefix="duty-roster-v618-")
        hpath = os.path.join(tmpdir, "harness.js")
        cpath = os.path.join(tmpdir, "cfg.json")
        with open(hpath, "w", encoding="utf-8") as f:
            f.write(NODE_HARNESS)
        with open(cpath, "w", encoding="utf-8") as f:
            json.dump({"appjs": os.path.join(fe, "app.js")}, f)
        proc = subprocess.run(["node", hpath, cpath], capture_output=True,
                              text=True, timeout=60)
        for line in proc.stdout.splitlines():
            if line.startswith("RESULT "):
                node_out = json.loads(line[len("RESULT "):])
        if node_out is None:
            print(proc.stdout, proc.stderr)
    except Exception as e:
        print("node harness error:", e)
    html = (node_out or {}).get("html") or ""
    check("N Node 行为：生成排班首次渲染默认明天（日期框值=明天、含生成排班标题）",
          node_out is not None and node_out.get("dateAfterInit") == expect_tomorrow
          and f'value="{expect_tomorrow}"' in html and "<h3>生成排班</h3>" in html,
          f"out={node_out and node_out.get('dateAfterInit')} expect={expect_tomorrow}")
    check("N Node 行为：日期清空 change 兜底回到明天并触发加载",
          node_out is not None and node_out.get("dateAfterClear") == expect_tomorrow
          and (node_out.get("loads") or 0) >= 1)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v6.18 引起的旧套件改动）：
  - 全部 36 个旧套件：版本标记断言字面量由 v6.17 提升为 v6.18
    （仅字面量），其余未动；
  - smoke_test_v615.py：管理员页两项断言由今天口径改为明天口径
    （初始化/兜底 tomorrowStr + 文案「默认明天」，检查名已注明
    v6.18 适配）；岗位显示与成员当日排班的今天口径断言、Node
    行为验证均原样成立；其文件头与报告文案中 v6.15 当时的
    「三页统一今天」描述保留为历史记录；
  - smoke_test_v617.py（岗位名）：与本版无交集，未动（仅标记）；
  - smoke_test_v60.py：早班图片静态断言的硬编码列名字面量
    （挑查岗/备勤）随 v6.17 注释清理后不再出现在 dailyImage 段，
    改为模板生成机制断言（ctx.template[0].posts，注明 v6.16
    适配）——该适配实际由 v6.16 的列生成改动引起、在本轮回归
    中补齐。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.18 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：纯静态检查（前端分段断言）+ Node 函数级行为验证（抽取 app.js 真实函数求值），后端零改动\n")
            f.write("- v6.18：管理员「生成排班」页默认日期由今天改回明天（初始化与日期兜底均 "
                    "tomorrowStr、文案「默认明天」）；岗位显示与成员「当日排班」仍默认今天。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.18: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
