# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.29 冒烟测试。

v6.29 变更（用户 2026-11-11 定，附 11 月 11 日晚班导图截图）：
整日时段表类导图里，带班、退税岗不再各占一行，挪到标题行最
右边（标题左、带班/退税右、同一行）以节省图面高度，字号保持
20px。范围：管理员「生成排班」导图（dailyImageCardHTML）与
成员「当日排班」导图（dayViewImage，后者退税岗原挂在表尾、
一并上移，标题随之改左对齐与右信息同排）。岗位显示个人导图
早已是标题行右侧放岗位（v6.23/v6.24），无带班行，不动；
月排班表导图无带班/退税，不动；各页面本身不动。

测试口径（纯静态 + Node 函数级验证，不起服务）：抽取
dailyImageCardHTML 真实函数喂早/晚夹具，断言标题行（<table
之前的部分）内同时含标题、带班、（晚班）退税岗，且旧独立行
式样（line-height:1.9 的带班/退税整行 div）已清除；成员导图
为内联构建，做静态断言（flex 标题行、带班/退税表达式在位、
表尾退税行与居中标题已清除）。
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
const NAMES = {1:'AAA',2:'BBB',3:'CCC',4:'DDD',5:'EEE',6:'FFF',7:'GGG',8:'HHH',9:'III',10:'JJJ',11:'KKK'};
function slot(start, end, posts) { return { start, end, posts: posts.map(([post, letters, extra]) => Object.assign({ post, letters }, extra || {})) }; }
const morningCtx = { date: '2026-11-02', shift: 'morning', shift_label: '早班', template: [
  slot('07:00','07:45', [['审图查验岗',['B','C']],['申报岗',['D']],['挑查岗',['E']],['备勤',['A']]]),
]};
const morningSaved = { leader_id: 3, letters: {A:7,B:3,C:4,D:8,E:5}, tax_ids: [] };
const eveningCtx = { date: '2026-11-11', shift: 'evening', shift_label: '晚班', template: [
  slot('14:30','15:30', [['审图查验岗',['A','B']],['申报岗',['C'],{start:'14:30',end:'15:00'}],['申报岗',['D'],{start:'15:00',end:'15:30'}]]),
  slot('21:15','22:00', [['审图查验岗',['C','D']],['申报岗',['A','B'],{note:'轮流'}]]),
]};
const eveningSaved = { leader_id: 3, letters: {A:9,B:3,C:8,D:4,E:5}, tax_ids: [11] };
const out = {
  morning: dailyImageCardHTML(morningCtx, morningSaved, NAMES),
  evening: dailyImageCardHTML(eveningCtx, eveningSaved, NAMES),
};
console.log('RESULT ' + JSON.stringify(out));
"""


def head_of(card):
    """标题行部分 = <table> 之前的全部内容。"""
    return card.split("<table")[0] if "<table" in card else ""


def main():
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()

    check("S app.js 带 v6.29 版本标记", "/* duty-roster v6.31 */" in js)
    helper_seg = segment(js, "function dailyImageCardHTML", "async function dailyImage()")
    check("S 管理员导图：标题行 flex 左右布局（space-between）、带班/退税同排右置（margin-left 间隔）、旧独立带班/退税整行 div 已清除",
          "justify-content:space-between" in helper_seg
          and "带班：${esc(names[saved.leader_id]" in helper_seg
          and "margin-left:24px" in helper_seg and "退税岗：" in helper_seg
          and 'line-height:1.9;margin-bottom:12px;">带班' not in helper_seg
          and 'line-height:1.9;margin-bottom:12px;">退税岗' not in helper_seg)
    dv_seg = segment(js, "async function dayViewImage()", "/* ---------------- 路由")
    check("S 成员当日排班导图：同为 flex 标题行、带班/退税右置；表尾退税行（margin-top）与居中标题已清除、表格仍在标题行之后",
          "justify-content:space-between" in dv_seg
          and "带班：${esc(out.leader_name || '—')}" in dv_seg
          and "margin-left:24px" in dv_seg and "退税岗：${out.tax_names" in dv_seg
          and "margin-top:12px" not in dv_seg
          and "text-align:center;margin-bottom:10px" not in dv_seg
          and dv_seg.index("justify-content:space-between") < dv_seg.index("dayTableExportHTML(out)"))
    mine_seg = segment(js, "function myPostsImageCardHTML", "async function myPostsImage()")
    check("S 个人导图未动：仍是标题行右侧只留岗位本身（v6.24 口径）、无「带班：」字面量",
          "justify-content:space-between" in mine_seg and "带班：" not in mine_seg)

    node_out = None
    try:
        tmpdir = tempfile.mkdtemp(prefix="duty-roster-v629-")
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
    mh = head_of(m)
    check("N 早班卡片：标题行内含「11月2日 早班」与「带班：CCC」（v6.31 适配：所有班次都带退税岗，夹具 tax_ids=[] 时呈「退税岗：无」）；时段表照旧",
          "11月2日 早班" in mh and "带班：CCC" in mh and "退税岗：无" in mh
          and "CCC+DDD" in m and "<table" in m)
    e = (node_out or {}).get("evening") or ""
    eh = head_of(e)
    check("N 晚班卡片（复刻用户截图场景）：标题行内含「11月11日 晚班」「带班：CCC」「退税岗：KKK」，三者在同一行（均位于 <table> 之前）",
          "11月11日 晚班" in eh and "带班：CCC" in eh and "退税岗：KKK" in eh,
          eh.replace("\n", " ")[:160])
    check("N 晚班卡片正文照旧：首段申报合并注「（各半小时）」、末段「（轮流）」、卡内带班/退税各只出现一次（不再有独立行重复）",
          "（各半小时）" in e and "（轮流）" in e
          and e.count("带班：") == 1 and e.count("退税岗：") == 1)

    return 0 if all(r[1] for r in results) else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.29 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：纯静态检查 + Node 函数级行为验证（抽取 app.js 真实函数喂夹具求值），后端零改动\n")
            f.write("- v6.29：整日时段表类导图（管理员生成排班图 + 成员当日排班图）的带班、退税岗挪到标题行最右边，不再各占一行。\n")
            f.write("- 适配说明：全部旧套件版本标记字面量随版本提升（仅字面量）；smoke_test_v610.py 的成员导图标题断言由「居中+带班行」改述为「flex 标题行+带班右置」（检查名已注明）。\n")
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.29: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
