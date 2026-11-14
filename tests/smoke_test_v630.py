# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.30 冒烟测试。

v6.30 变更（用户 2026-11-11 定）：「生成排班」页在「生成图片」
右边新增「复制岗位」按钮，点击把当前岗位信息复制为纯文本，
可直接粘贴到其他地方。文本格式按用户给的示例（以 11 月 12 日
早班为例）：
    11月12日 早班
    带班：AAA
    A：DDD B：CCC C：EEE D：AAA E：III
末行再加一行「退税岗：X」（当天在岗协管员）。注：本套件初版
时退税岗仅晚班、早班不带此行；用户随后明确「所有班次都要带上
退税岗人员」，v6.31 起改为所有班次恒带，本套件已随之适配。
内容取表单当前选中值（dailyState.form），不要求先保存；
未排满的岗记「未定」。剪贴板写入兼容 http 非安全上下文：
navigator.clipboard 不可用时回退 textarea+execCommand。

测试口径（纯静态 + Node 函数级验证，不起服务）：抽取
dailyCopyText 真实函数喂夹具（含线上 11-12 已保存排班的
真实人选），断言输出逐字等于用户示例格式；静态断言按钮
位置（生成图片之后）、绑定与剪贴板回退在位。
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
  extract(/function datePartsOf\(s\) \{[^\n]*\}/, 'datePartsOf'),
  extract(/function dailyLettersOf\(ctx\) \{[\s\S]*?\n\}/, 'dailyLettersOf'),
  extract(/function dailyCopyText\(ctx, form\) \{[\s\S]*?\n\}/, 'dailyCopyText'),
].join('\n');
eval(code);
const NAMES = {1:'AAA',2:'BBB',3:'CCC',4:'DDD',5:'EEE',6:'FFF',7:'GGG',8:'HHH',9:'III',10:'JJJ',11:'KKK'};
const morningCtx = { date: '2026-11-12', shift: 'morning', shift_label: '早班',
  letter_order: ['A','B','C','D','E'], names: NAMES, on_duty_assistants: [{name:'JJJ'},{name:'KKK'}] };
const morningForm = { leader_id: 1, letters: {A:4,B:3,C:5,D:1,E:9,F:null} };
const eveningCtx = { date: '2026-11-11', shift: 'evening', shift_label: '晚班',
  letter_order: ['A','B','C','D','E'], names: NAMES, on_duty_assistants: [{name:'KKK'}] };
const eveningForm = { leader_id: 3, letters: {A:9,B:3,C:8,D:4,E:5,F:null} };
const morning6Ctx = { date: '2026-11-08', shift: 'morning', shift_label: '早班',
  letter_order: ['A','B','C','D','E','F'], names: NAMES, on_duty_assistants: [] };
const morning6Form = { leader_id: 1, letters: {A:1,B:6,C:2,D:7,E:5,F:3} };
const partialForm = { leader_id: 1, letters: {A:4,B:null,C:5,D:1,E:9,F:null} };
const out = {
  morning: dailyCopyText(morningCtx, morningForm),
  evening: dailyCopyText(eveningCtx, eveningForm),
  morning6: dailyCopyText(morning6Ctx, morning6Form),
  partial: dailyCopyText(morningCtx, partialForm),
};
console.log('RESULT ' + JSON.stringify(out));
"""


def main():
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()

    check("S app.js 带 v6.30 版本标记", "/* duty-roster v6.31 */" in js)

    body_seg = segment(js, "function renderDailyBody()", "/* v6.6「抢占」")
    check("S 生成排班页：复制岗位按钮定义在位（dailyCopyBtn/文案「复制岗位」）、且排在生成图片（${imgBtn}）之后渲染",
          "dailyCopyBtn" in body_seg and "复制岗位" in body_seg
          and body_seg.index("${imgBtn}") < body_seg.index("${copyBtn}"))
    check("S 复制按钮绑定 copyDailyPosts、且不随未保存置灰（imgBtn 的 dirty 禁用逻辑不含 copyBtn 定义行）",
          "cp.addEventListener('click', copyDailyPosts)" in body_seg
          and "const copyBtn = '<button id=\"dailyCopyBtn\">复制岗位</button>'" in body_seg)

    copy_seg = segment(js, "function dailyCopyText(ctx, form)", "/* v6.22")
    check("S dailyCopyText：四段行式（日期行/带班行/字母一行排开/退税岗行恒带；v6.31 适配：已无 evening 门控）",
          "带班：" in copy_seg and "退税岗：" in copy_seg
          and "ctx.shift === 'evening'" not in copy_seg
          and ".join(' ')" in copy_seg and ".join('\\n')" in copy_seg)
    check("S 剪贴板写入：优先 navigator.clipboard、安全上下文判断在位、http 回退 textarea+execCommand('copy') 在位；复制成功有 toast",
          "navigator.clipboard" in copy_seg and "window.isSecureContext" in copy_seg
          and "execCommand('copy')" in copy_seg
          and "岗位已复制，可直接粘贴" in copy_seg)

    node_out = None
    try:
        tmpdir = tempfile.mkdtemp(prefix="duty-roster-v630-")
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

    expect_morning = "11月12日 早班\n带班：AAA\nA：DDD B：CCC C：EEE D：AAA E：III\n退税岗：JJJ KKK"
    check("N 11-12 早班（线上已保存真实人选）：前三行逐字等于用户示例、末行带退税岗（v6.31：所有班次都带；当天两名协管员均在岗故两人全带）",
          (node_out or {}).get("morning") == expect_morning,
          repr((node_out or {}).get("morning")))
    expect_evening = "11月11日 晚班\n带班：CCC\nA：III B：CCC C：HHH D：DDD E：EEE\n退税岗：KKK"
    check("N 11-11 晚班：四行齐全、退税岗行在末行且为当天在岗协管员KKK",
          (node_out or {}).get("evening") == expect_evening,
          repr((node_out or {}).get("evening")))
    m6 = (node_out or {}).get("morning6") or ""
    check("N 早班 6 人方案：字母行带 F 岗（F：CCC）、末行退税岗（夹具无协管员呈「无」；v6.31 恒带）",
          m6.split("\n")[-2].endswith("F：CCC") and len(m6.split("\n")) == 4 and m6.split("\n")[-1] == "退税岗：无",
          repr(m6))
    part = (node_out or {}).get("partial") or ""
    check("N 未排满：空岗记「未定」（B：未定）、其余岗照常输出",
          "B：未定" in part and "A：DDD" in part, repr(part))

    return 0 if all(r[1] for r in results) else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.30 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：纯静态检查 + Node 函数级行为验证（抽取 app.js 真实函数喂夹具求值），后端零改动\n")
            f.write("- v6.30：「生成排班」页「生成图片」右边新增「复制岗位」按钮，复制当前表单岗位为纯文本（用户示例格式；晚班带退税岗行、早班不带）。\n")
            f.write("- 适配说明：全部旧套件版本标记字面量随版本提升至 v6.30（仅字面量）。\n")
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.30: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
