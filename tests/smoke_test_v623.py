# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.23 冒烟测试（追加到 SMOKE_TEST.md 的 v6.23 章节）。

v6.23 变更（用户 2026-11-03 定，附CCC 11 月 2 日早班个人岗位图）：
岗位显示「生成图片」的版式两点调整——①图片里去掉带班人员（原
标题下「带班：X」整行删除）；②岗位移到最上面、放在标题行姓名的
右边：标题行左侧「X月X日 班次 · 姓名」、右侧「您的/某人的岗位：
X岗」（字母蓝色大字保持；退税岗同式显示「退税岗（晚班）」）。
其下内容不变：字母岗时段表（时间/岗位/同岗同事）、退税岗同岗
说明行（v6.11 口径）。页面本身不改（页脚带班行仍在）。实现上
把卡片构建抽成纯函数 myPostsImageCardHTML，myPostsImage 只负责
离屏截图与下载。

测试口径（纯静态 + Node 函数级行为验证）：抽取真实函数喂四套
夹具（本人字母岗 / 看他人字母岗 / 退税岗独自一人 / 退税岗有
同岗）断言：无「带班：」、岗位文案位于姓名之后（标题行右侧）、
表格与同岗行照旧；静态断言页面页脚带班行未被误删。
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
  extract(/function myPostsImageCardHTML\(out\) \{[\s\S]*?\n\}/, 'myPostsImageCardHTML'),
].join('\n');
eval(code);
const okSelf = { date: '2026-11-02', shift_label: '早班', is_self: true, viewer: { name: 'CCC' },
  result: { status: 'ok', letter: 'B', leader_name: 'CCC', timeline: [
    { time: '07:00–07:45', post: '审图查验岗', partners: ['DDD'] },
    { time: '07:45–08:30', post: '备勤', partners: [] },
  ] } };
const okOther = { date: '2026-11-02', shift_label: '早班', is_self: false, viewer: { name: 'FFF' },
  result: { status: 'ok', letter: 'C', leader_name: 'CCC', timeline: [
    { time: '07:00–07:45', post: '审图查验岗', partners: ['CCC'] },
  ] } };
const taxLone = { date: '2026-11-03', shift_label: '晚班', is_self: true, viewer: { name: 'JJJ' },
  result: { status: 'tax', leader_name: 'AAA', tax_names: ['JJJ'] } };
const taxTwo = { date: '2026-11-03', shift_label: '晚班', is_self: true, viewer: { name: 'JJJ' },
  result: { status: 'tax', leader_name: 'AAA', tax_names: ['JJJ', 'KKK'] } };
const out = {
  okSelf: myPostsImageCardHTML(okSelf),
  okOther: myPostsImageCardHTML(okOther),
  taxLone: myPostsImageCardHTML(taxLone),
  taxTwo: myPostsImageCardHTML(taxTwo),
};
console.log('RESULT ' + JSON.stringify(out));
"""


def main():
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()

    check("S app.js 带 v6.23 版本标记", "/* duty-roster v6.31 */" in js)
    helper_seg = segment(js, "function myPostsImageCardHTML", "async function myPostsImage()")
    card_func_seg = segment(js, "function myShiftCardHTML", "function myPostsHTML")
    check("S 个人导图纯函数在位、无带班行字面量、标题行为左右布局（flex + space-between）；页面岗位卡页脚带班行未动",
          "带班：" not in helper_seg and "display:flex" in helper_seg
          and "justify-content:space-between" in helper_seg
          and "带班：${esc(e.leader_name || '—')}" in card_func_seg
          and "myPostsImageCardHTML(out)" in js)

    node_out = None
    try:
        tmpdir = tempfile.mkdtemp(prefix="duty-roster-v623-")
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

    s = (node_out or {}).get("okSelf") or ""
    check("N 本人字母岗：无带班行；标题含「11月2日 早班 · CCC」、岗位本身在姓名之后（标题行右侧；v6.24 适配：右侧只留岗位本身、无「您的岗位：」）；时段表与同岗同事照旧",
          "带班：" not in s and "11月2日 早班 · CCC" in s
          and "您的岗位：" not in s and "</span>岗" in s
          and s.index("</span>岗") > s.index("CCC")
          and "同岗同事" in s and "DDD" in s and "备勤" in s)
    o = (node_out or {}).get("okOther") or ""
    check("N 看他人字母岗：右侧只留岗位本身（蓝色字母+岗）在姓名之后、无「FFF的岗位：」、无带班行（v6.24 适配）",
          "带班：" not in o and "FFF的岗位：" not in o
          and o.index("</span>岗") > o.index("· FFF"))
    tl = (node_out or {}).get("taxLone") or ""
    tt = (node_out or {}).get("taxTwo") or ""
    check("N 退税岗：标题行右侧只留「退税岗（晚班）」、无带班行、无「您的岗位：」；独自一人无同岗行、有同岗时「同岗：KKK」照旧在卡内（v6.24 适配）",
          "退税岗（晚班）" in tl and "您的岗位：" not in tl and "带班：" not in tl and "同岗：" not in tl
          and "同岗：KKK" in tt and "带班：" not in tt)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v6.23 引起的旧套件改动）：
  - 全部 47 个旧套件：版本标记断言字面量由 v6.22 提升为 v6.23
    （仅字面量）；
  - smoke_test_v611.py：导图分段起点改为 myPostsImageCardHTML
    纯函数、Node 抽取清单加该函数；tax 分支条件渲染断言改述；
    「F 导图·独自一人」中「带班：AAA 在图内」断言按 v6.23
    新口径翻转（导图已去带班行、页面侧断言不变）；
  - smoke_test_v610.py：个人导图分段起点同样改为纯函数。
- 后续适配（v6.24，同日）：本套件三项 N 检查的岗位文案期望已按
  v6.24 改述——标题行右侧只留岗位本身（字母岗为蓝色字母+「岗」、
  退税岗为「退税岗（晚班）」），不再含「您的岗位：/某人的岗位：」
  （检查名均已注明 v6.24 适配）。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.23 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：纯静态检查 + Node 函数级行为验证（抽取 app.js 真实函数喂夹具求值），后端零改动\n")
            f.write("- v6.23：岗位显示个人导图去带班行、岗位上移至标题行姓名右侧；"
                    "卡片构建抽为纯函数 myPostsImageCardHTML。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.23: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
