# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.24 冒烟测试（追加到 SMOKE_TEST.md 的 v6.24 章节）。

v6.24 变更（用户 2026-11-03 定，附EEE 11 月 4 日早班个人图）：
v6.23 把岗位移到标题行右侧后，用户指出：最上面一行左边已经有
姓名了，右边不需要再重复「EEE的岗位：」——直接「D岗」就行。
按此逻辑：个人导图标题行右侧只留岗位本身——字母岗为蓝色大字
字母+「岗」（如 D岗），退税岗为「退税岗（晚班）」；本人与看
他人同一口径。页面本身不变（页面岗位行仍带「您的/某人的岗位」）。

测试口径（纯静态 + Node 函数级行为验证）：抽取真实函数喂三套
夹具（本人字母岗/看他人字母岗/退税岗）断言右侧裸岗位与页面
未动；静态断言版本标记。
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
const okOther = { date: '2026-11-04', shift_label: '早班', is_self: false, viewer: { name: 'EEE' },
  result: { status: 'ok', letter: 'D', leader_name: 'AAA', timeline: [
    { time: '07:00–07:45', post: '申报岗', partners: [] },
  ] } };
const okSelf = { date: '2026-11-02', shift_label: '早班', is_self: true, viewer: { name: 'CCC' },
  result: { status: 'ok', letter: 'B', leader_name: 'CCC', timeline: [
    { time: '07:00–07:45', post: '审图查验岗', partners: ['DDD'] },
  ] } };
const tax = { date: '2026-11-03', shift_label: '晚班', is_self: true, viewer: { name: 'JJJ' },
  result: { status: 'tax', leader_name: 'AAA', tax_names: ['JJJ', 'KKK'] } };
const out = {
  okOther: myPostsImageCardHTML(okOther),
  okSelf: myPostsImageCardHTML(okSelf),
  tax: myPostsImageCardHTML(tax),
};
console.log('RESULT ' + JSON.stringify(out));
"""


def main():
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()

    check("S app.js 带 v6.24 版本标记", "/* duty-roster v6.31 */" in js)
    helper_seg = segment(js, "function myPostsImageCardHTML", "async function myPostsImage()")
    page_seg = segment(js, "function myShiftCardHTML", "function myPostsHTML")
    check("S 导图纯函数不再拼「的岗位：/您的岗位：」前缀；页面 myShiftCardHTML 的岗位行文案未动（页面仍带归属前缀）",
          "岗位：" not in helper_seg and "${words.poss}岗位：" in page_seg)

    node_out = None
    try:
        tmpdir = tempfile.mkdtemp(prefix="duty-roster-v624-")
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

    o = (node_out or {}).get("okOther") or ""
    check("N 看他人（EEE实例）：标题「11月4日 早班 · EEE」、右侧直接蓝色 D+岗，无「EEE的岗位：」、无带班行",
          "11月4日 早班 · EEE" in o and "EEE的岗位" not in o
          and ">D</span>岗" in o and "带班：" not in o)
    s = (node_out or {}).get("okSelf") or ""
    check("N 本人字母岗：右侧直接蓝色 B+岗、无「您的岗位：」",
          ">B</span>岗" in s and "您的岗位" not in s)
    t = (node_out or {}).get("tax") or ""
    check("N 退税岗：右侧直接「退税岗（晚班）」、无「您的岗位：」；同岗行照旧",
          "退税岗（晚班）" in t and "您的岗位" not in t and "同岗：KKK" in t)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v6.24 引起的旧套件改动）：
  - 全部 48 个旧套件：版本标记断言字面量由 v6.23 提升为 v6.24
    （仅字面量）；
  - smoke_test_v623.py：三项 N 检查按 v6.24 改述（右侧只留岗位
    本身，检查名已注明）；
  - smoke_test_v611.py：两项 F 导图检查按 v6.24 改述（「您的
    岗位：退税岗（晚班）」→裸「退税岗（晚班）」；看他人导图不
    再含「KKK的岗位」、页面侧断言不变）；
  - smoke_test_v64.py：「岗位图片归属」断言按 v6.23/v6.24 改述
    （标题带姓名保留、poss 前缀已去掉）。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.24 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：纯静态检查 + Node 函数级行为验证（抽取 app.js 真实函数喂夹具求值），后端零改动\n")
            f.write("- v6.24：个人导图标题行右侧只留岗位本身（X岗/退税岗（晚班）），"
                    "去掉「您的/某人的岗位：」前缀。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.24: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
