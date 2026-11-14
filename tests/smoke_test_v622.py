# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.22 冒烟测试（追加到 SMOKE_TEST.md 的 v6.22 章节）。

v6.22 变更（用户 2026-11-02 定，附 11 月 2 日早班导图截图）：
管理员「生成排班」页的晚班导图改与早班同款格式——原图4 四行
文案版（带班/申报岗/审图第一组第二组/退税岗）废止，统一为：
标题「X月X日 早班/晚班」+「带班：X」+ 整张时段表（时间/岗位列
真名）；晚班在带班行下多一行「退税岗：X」。实现上把卡片 HTML
构建抽成纯函数 dailyImageCardHTML（早晚班共用）：早班列随模板
首段岗位名生成；晚班固定审图查验岗/申报岗两列，申报多段同格
合并注「（各半小时）」、带 note 的原样带出（与页面预览、成员
当日排班导图同口径）。成员当日排班导图本就是时段表格式、
岗位显示个人图为个人时间轴，均不在本次范围。

测试口径（纯静态 + Node 函数级行为验证，不起服务）：抽取
esc/datePartsOf/dailyImageCardHTML 真实函数，喂三套夹具
（早班 5 人、晚班 5 人含半小时拆分段、晚班 6 人）断言卡片
结构与关键文本；静态断言版本标记与旧文案行清除。
"""
import json
import os
import subprocess
import sys
import tempfile
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


NODE_HARNESS = r"""
const fs = require('fs');
const cfg = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const src = fs.readFileSync(cfg.appjs, 'utf8');
function extract(re, name) { const m = src.match(re); if (!m) throw new Error('extract: ' + name); return m[0]; }
const code = [
  extract(/function esc\(s\) \{[\s\S]*?\n\}/, 'esc'),
  extract(/function datePartsOf\(s\) \{[^\n]*\}/, 'datePartsOf'),
  extract(/function dailyImageCardHTML\(ctx, saved, names\) \{[\s\S]*?\n\}/, 'dailyImageCardHTML'),
].join('\n');
eval(code);
const NAMES = {1:'AAA',2:'BBB',3:'CCC',4:'DDD',5:'EEE',6:'FFF',7:'GGG',10:'JJJ',11:'KKK'};
function slot(start, end, posts) { return { start, end, posts: posts.map(([post, letters, extra]) => Object.assign({ post, letters }, extra || {})) }; }
const morningCtx = { date: '2026-11-02', shift: 'morning', shift_label: '早班', template: [
  slot('07:00','07:45', [['审图查验岗',['B','C']],['申报岗',['D']],['挑查岗',['E']],['备勤',['A']]]),
  slot('07:45','08:30', [['审图查验岗',['D','E']],['申报岗',['A']],['挑查岗',['C']],['备勤',['B']]]),
]};
const morningSaved = { leader_id: 3, letters: {A:7,B:3,C:4,D:8,E:5}, tax_ids: [] };
const eveningCtx = { date: '2026-11-03', shift: 'evening', shift_label: '晚班', template: [
  slot('14:30','15:30', [['审图查验岗',['A','B']],['申报岗',['C'],{start:'14:30',end:'15:00'}],['申报岗',['D'],{start:'15:00',end:'15:30'}]]),
  slot('16:30','17:30', [['审图查验岗',['A','B']],['申报岗',['E']]]),
  slot('21:15','22:00', [['审图查验岗',['C','D']],['申报岗',['A','B'],{note:'轮流'}]]),
]};
const eveningSaved = { leader_id: 2, letters: {A:7,B:8,C:5,D:1,E:2}, tax_ids: [10] };
const evening6Ctx = { date: '2026-11-03', shift: 'evening', shift_label: '晚班', template: [
  slot('14:30','15:30', [['审图查验岗',['A','B']],['申报岗',['E']]]),
  slot('15:30','16:30', [['审图查验岗',['C','D']],['申报岗',['F']]]),
]};
const evening6Saved = { leader_id: 2, letters: {A:2,B:4,C:3,D:7,E:5,F:1}, tax_ids: [10] };
const out = {
  morning: dailyImageCardHTML(morningCtx, morningSaved, NAMES),
  evening: dailyImageCardHTML(eveningCtx, eveningSaved, NAMES),
  evening6: dailyImageCardHTML(evening6Ctx, evening6Saved, NAMES),
};
console.log('RESULT ' + JSON.stringify(out));
"""


def main():
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()

    check("S app.js 带 v6.22 版本标记", "/* duty-roster v6.31 */" in js)
    helper_seg = segment(js, "function dailyImageCardHTML", "async function dailyImage()")
    check("S 导图卡片纯函数在位且旧图4 文案行已清除（无「第一组：/第二组：」拼行、dailyImage 改调纯函数）",
          "第一组：" not in helper_seg and "第二组：" not in helper_seg
          and "dailyImageCardHTML(ctx, saved, ctx.names || {})" in js
          and "退税岗：" in helper_seg and "审图查验岗" in helper_seg)

    node_out = None
    try:
        tmpdir = tempfile.mkdtemp(prefix="duty-roster-v622-")
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

    m = (node_out or {}).get("morning") or ""
    check("N 早班卡片保持时段表格式（标题「11月2日 早班」+带班行+四列表头+真名；v6.31 适配：所有班次都带退税岗，夹具 tax_ids=[] 时标题行呈「退税岗：无」）",
          "11月2日 早班" in m and "带班：CCC" in m
          and all(h in m for h in ("时间", "审图查验岗", "申报岗", "挑查岗", "备勤"))
          and "CCC+DDD" in m and "退税岗：无" in m)
    e = (node_out or {}).get("evening") or ""
    check("N 晚班 5 人卡片改时段表（标题「11月3日 晚班」+带班+退税岗行+两列表头；首段申报 C、D 合并一格并注「（各半小时）」、末段带「（轮流）」）",
          "11月3日 晚班" in e and "带班：BBB" in e and "退税岗：JJJ" in e
          and "EEE+AAA（各半小时）" in e and "（轮流）" in e
          and "第一组" not in e and "<table" in e)
    e6 = (node_out or {}).get("evening6") or ""
    check("N 晚班 6 人卡片为时段表（两段各呈一组审图+一名申报：首段EEE申报、次段AAA申报）",
          "11月3日 晚班" in e6 and "BBB+DDD" in e6 and "CCC+GGG" in e6
          and ">EEE<" in e6 and ">AAA<" in e6 and "退税岗：JJJ" in e6)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v6.22 引起的旧套件改动）：
  - 全部 46 个旧套件：版本标记断言字面量由 v6.21 提升为 v6.22
    （仅字面量）；
  - smoke_test_v60.py：导图分段起点改为 dailyImageCardHTML 纯
    函数；「晚班图片为图4 文案格式」断言改述为时段表格式（检查
    名已注明 v6.22 适配）；早班图片断言改以模板生成机制核对；
  - smoke_test_v620.py：S 导图双人名文案行断言随图4 版废止而
    改述（检查名已注明 v6.22 适配）；
  - smoke_test_v614.py / smoke_test_v616.py：管理员导图分段
    起点由 dailyImage 改为 dailyImageCardHTML 纯函数；v616 的
    卡片加宽字面量同步为新条件式（检查名已注明 v6.22 适配）。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.22 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：纯静态检查 + Node 函数级行为验证（抽取 app.js 真实函数喂夹具求值），后端零改动\n")
            f.write("- v6.22：晚班导图改与早班同款时段表格式（标题+带班+退税岗行+整表），"
                    "图4 四行文案版废止；卡片构建抽为纯函数 dailyImageCardHTML。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.22: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
