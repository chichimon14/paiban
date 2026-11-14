# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.15 冒烟测试（追加到 SMOKE_TEST.md 的 v6.15 章节）。

v6.15 变更（用户 2026-11-02 要求，同日扩围）：三个日期页的默认日期
由明天统一改为今天，回跳按钮由「回到明天」统一改为「回到今天」：
  - 新增 todayStr() 辅助函数（localDateStr(new Date())）；
  - 「岗位显示」：viewMyPosts 首次初始化 mypostsDate 改用 todayStr()
    （登录/退出经 resetMyPostsState 清空后，同样由该初始化回到
    今天）；按钮 id mpTomorrow→mpToday、点击处理与日期 change 兜底
    均改跳今天；
  - 成员「当日排班」（dayview）：dayviewDate 初始化、change 兜底、
    按钮（id dvTomorrow→dvToday、文案「回到今天」及点击处理）同改；
  - 管理员「生成当日排班」（viewDaily）：dailyState.date 初始化与
    change 兜底改用 todayStr()，页内提示文案「默认排下一天」改为
    「默认今天」（该页本无回跳按钮）。
改后全文件不再有任何 tomorrowStr() 调用点（函数定义保留）、无
「回到明天」字面。后端零改动。

测试口径（纯静态分段断言 + Node 函数级行为验证，不起服务）：
  S) 静态：版本标记、todayStr 定义；三页各自 view/bind 段的初始化/
     按钮/处理/兜底字面量均为今天口径，且三页段内均无 tomorrowStr、
     无 mpTomorrow/dvTomorrow、无「回到明天」；全文件计数兜底
     （回到今天恰 2 处=两页按钮、回到明天 0 处）；resetMyPostsState
     仍清空 mypostsDate。
  N) Node 行为：抽取 localDateStr/tomorrowStr/todayStr/datePartsOf/
     shiftDateStr/myRole/canPickPerson/viewMyPosts/bindMyPosts 真实函数，
     以成员身份（无选人框）验证：todayStr()=今天、tomorrowStr()=明天；
     首次渲染日期框=今天且含「回到今天」按钮；点击「回到今天」后
     mypostsDate 与日期框均跳回今天并触发加载；日期清空 change 兜底
     回到今天。
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
  extract(/function localDateStr\(d\) \{[\s\S]*?\n\}/, 'localDateStr'),
  extract(/function tomorrowStr\(\) \{[^}]*\}/, 'tomorrowStr'),
  extract(/function todayStr\(\) \{[^}]*\}/, 'todayStr'),
  extract(/function datePartsOf\(s\) \{[^\n]*\}/, 'datePartsOf'),
  extract(/function shiftDateStr\(s, delta\) \{[^}]*\}/, 'shiftDateStr'),
  extract(/function myRole\(\) \{[\s\S]*?\n\}/, 'myRole'),
  extract(/function canPickPerson\(\) \{[^}]*\}/, 'canPickPerson'),
  extract(/function viewMyPosts\(\) \{[\s\S]*?\n\}/, 'viewMyPosts'),
  extract(/function bindMyPosts\(\) \{[\s\S]*?\n\}/, 'bindMyPosts'),
].join('\n');
/* 成员视图里实际存在的元素（无选人框 mpPerson，与真实 DOM 一致） */
const PRESENT = new Set(['mpPrev', 'mpDate', 'mpNext', 'mpToday', 'mypostsBody']);
const els = {}; const listeners = {};
function mkEl(id) {
  return { value: '', innerHTML: '',
    addEventListener(ev, fn) { listeners[id + ':' + ev] = fn; } };
}
global.$ = (id) => (PRESENT.has(id) ? (els[id] = els[id] || mkEl(id)) : null);
let loads = 0;
global.loadMyPosts = () => { loads += 1; };
global.api = async () => [];
global.me = { role: 'member', person_id: 42, username: '测试成员' };
eval(code);
const out = { today: todayStr(), tomorrow: tomorrowStr() };
/* 1) 首次打开：mypostsDate 为空 → 视图初始化为今天 */
global.mypostsDate = ''; global.mypostsState = null; global.mypostsPersonId = null;
out.html = viewMyPosts();
out.dateAfterInit = global.mypostsDate;
/* 2) 点「回到今天」：先把日期拨到旧日子，绑定后点击 */
global.mypostsDate = '2020-01-01';
bindMyPosts();
if (!listeners['mpToday:click']) throw new Error('mpToday click listener missing');
listeners['mpToday:click']();
out.dateAfterTodayBtn = global.mypostsDate;
out.inputAfterTodayBtn = els.mpDate.value;
out.loadsAfterTodayBtn = loads;
/* 3) 日期框清空后 change：兜底应回到今天 */
els.mpDate.value = '';
if (!listeners['mpDate:change']) throw new Error('mpDate change listener missing');
listeners['mpDate:change']();
out.dateAfterClear = global.mypostsDate;
console.log('RESULT ' + JSON.stringify(out));
"""


def main():
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()

    check("S app.js 带 v6.15 版本标记", "/* duty-roster v6.31 */" in js)

    view_seg = segment(js, "function viewMyPosts()", "function bindMyPosts()")
    bind_seg = segment(js, "function bindMyPosts()", "async function loadMyPosts()")
    dv_view_seg = segment(js, "function viewDayView()", "function bindDayView()")
    dv_bind_seg = segment(js, "function bindDayView()", "async function loadDayView()")
    daily_view_seg = segment(js, "function viewDaily()", "function bindDaily()")
    daily_bind_seg = segment(js, "function bindDaily()", "async function loadDaily()")

    # ---- 岗位显示：改到今天 ----
    check("S todayStr 辅助函数在位（localDateStr(new Date())）",
          "function todayStr() { return localDateStr(new Date()); }" in js)
    check("S viewMyPosts 默认日期初始化改为今天",
          "if (!mypostsDate) mypostsDate = todayStr();" in view_seg)
    check("S viewMyPosts 按钮为「回到今天」（id=mpToday）",
          '<button id="mpToday">回到今天</button>' in view_seg)
    check("S viewMyPosts 段无明天残留（无 tomorrowStr / mpTomorrow / 回到明天）",
          "tomorrowStr" not in view_seg and "mpTomorrow" not in view_seg
          and "回到明天" not in view_seg)
    check("S bindMyPosts「回到今天」点击处理在位（设 todayStr 并回填日期框）",
          "const tm = $('mpToday'); if (tm) tm.addEventListener('click', () => "
          "{ mypostsDate = todayStr(); if (di) di.value = mypostsDate; loadMyPosts(); });" in bind_seg)
    check("S bindMyPosts 日期 change 兜底改为今天",
          "mypostsDate = di.value || todayStr();" in bind_seg)
    check("S bindMyPosts 段无明天残留（无 tomorrowStr / mpTomorrow）",
          "tomorrowStr" not in bind_seg and "mpTomorrow" not in bind_seg)
    check("S 全文件无明天残留：mpTomorrow/dvTomorrow 零出现、「回到明天」0 处、「回到今天」恰 2 处（岗位显示+当日排班两页按钮）",
          "mpTomorrow" not in js and "dvTomorrow" not in js
          and js.count("回到明天") == 0 and js.count("回到今天") == 2,
          f"回到今天={js.count('回到今天')} 回到明天={js.count('回到明天')}")
    check("S resetMyPostsState 仍清空 mypostsDate（退出/登录后由视图以今天重新初始化）",
          "function resetMyPostsState() { mypostsDate = '';" in js)

    # ---- 成员「当日排班」页：同改今天 ----
    check("S 当日排班页默认日期初始化改为今天 + 按钮为「回到今天」（id=dvToday）",
          "if (!dayviewDate) dayviewDate = todayStr();" in dv_view_seg
          and '<button id="dvToday">回到今天</button>' in dv_view_seg)
    check("S 当日排班页绑定同改：「回到今天」点击设今天 + 日期 change 兜底今天",
          "const tm = $('dvToday'); if (tm) tm.addEventListener('click', () => "
          "{ dayviewDate = todayStr(); if (di) di.value = dayviewDate; loadDayView(); });" in dv_bind_seg
          and "dayviewDate = di.value || todayStr();" in dv_bind_seg)
    check("S 当日排班页两段无明天残留（无 tomorrowStr / dvTomorrow / 回到明天）",
          "tomorrowStr" not in dv_view_seg and "tomorrowStr" not in dv_bind_seg
          and "dvTomorrow" not in dv_view_seg and "dvTomorrow" not in dv_bind_seg
          and "回到明天" not in dv_view_seg and "回到明天" not in dv_bind_seg)

    # ---- 管理员「生成排班」：v6.15 当时同改今天；v6.18 已单独改回明天
    # （适配说明见 v6.18 套件；本套件对该页只保留 v6.15 当时的结构断言
    # 之外的现行断言：仍为单处初始化 + change 兜底，函数为 tomorrowStr） ----
    check("S 生成排班默认日期初始化为明天 + 提示文案为「默认明天」（v6.18 适配，原 v6.15 为默认今天）",
          "if (!dailyState.date) dailyState.date = tomorrowStr();" in daily_view_seg
          and "（默认明天，改日期会自动重新载入）" in daily_view_seg
          and "默认排下一天" not in daily_view_seg)
    check("S 生成排班日期 change 兜底为明天（v6.18 适配）",
          "dailyState.date = di.value || tomorrowStr();" in daily_bind_seg)

    # ---- Node 行为验证 ----
    today = date.today()
    expect_today = today.isoformat()
    expect_tomorrow = (today + timedelta(days=1)).isoformat()
    node_out = None
    try:
        tmpdir = tempfile.mkdtemp(prefix="duty-roster-v615-")
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
    check("N Node 行为：todayStr()=今天、tomorrowStr()=明天（辅助函数真实求值）",
          node_out is not None and node_out.get("today") == expect_today
          and node_out.get("tomorrow") == expect_tomorrow,
          f"out={node_out and (node_out.get('today'), node_out.get('tomorrow'))} expect=({expect_today},{expect_tomorrow})")
    html = (node_out or {}).get("html") or ""
    check("N Node 行为：岗位显示首次渲染默认今天（日期框值=今天、含「回到今天」按钮、无「回到明天」）",
          node_out is not None and node_out.get("dateAfterInit") == expect_today
          and f'value="{expect_today}"' in html and 'id="mpToday"' in html
          and "回到今天" in html and "回到明天" not in html)
    check("N Node 行为：点击「回到今天」后 mypostsDate 与日期框均跳回今天并触发加载",
          node_out is not None and node_out.get("dateAfterTodayBtn") == expect_today
          and node_out.get("inputAfterTodayBtn") == expect_today
          and (node_out.get("loadsAfterTodayBtn") or 0) >= 1)
    check("N Node 行为：日期框清空 change 兜底回到今天（非明天）",
          node_out is not None and node_out.get("dateAfterClear") == expect_today)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v6.15 引起的旧套件改动）：
  - 全部 34 个旧套件：版本标记断言字面量由 v6.14 提升为 v6.15
    （仅字面量），其余未动；
  - 岗位显示侧逐项核查：v68、v613 的 Node 夹具均显式预置
    mypostsDate 后再调 loadMyPosts，不依赖 viewMyPosts 的默认
    值，原样成立；
  - 同日扩围（dayview + 管理员编辑页同改）引起的适配：
    · smoke_test_v69.py：dayview 段断言 dayviewDate =
      tomorrowStr() 改为 todayStr()（检查名注明 v6.15 适配）；
      文件头 docstring「日期控件同岗位显示（默认明天）」改写
      为默认今天口径；
    · smoke_test_v612.py：dayview 控件行完整性断言中
      dvTomorrow 改 dvToday、检查名「回到明天」改「回到今天」
      （注明 v6.15 适配）；
    · smoke_test_v610.py：控件在位断言 dvTomorrow 改 dvToday；
      导出无控件断言补 dvToday 不出现（dvTomorrow 字面保留，
      改名后自然零出现）；
    · smoke_test_v60.py：文件头 docstring 中管理员编辑页
      「日期（默认明天）」改注为默认今天（v6.15 改）；
  - 后端零改动：mine/dayview/context 接口与日期默认值无关，
    默认日期纯前端行为。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.15 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：纯静态检查（前端分段断言）+ Node 函数级行为验证（抽取 app.js 真实函数求值），后端零改动\n")
            f.write("- v6.15：三个日期页默认日期由明天统一改为今天（新增 todayStr()）："
                    "「岗位显示」（初始化/按钮 id mpTomorrow→mpToday/点击与日期兜底均跳今天）、"
                    "成员「当日排班」（dayviewDate 初始化/兜底/按钮 dvTomorrow→dvToday 同改）、"
                    "管理员「生成当日排班」（dailyState 初始化与兜底改今天、提示文案改「默认今天」）；"
                    "全文件无「回到明天」与 tomorrowStr() 调用点。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.15: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
