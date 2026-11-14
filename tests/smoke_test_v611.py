# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.11 冒烟测试（追加到 SMOKE_TEST.md 的 v6.11 章节）。

v6.11 变更（2026-11-01 用户追加反馈，纯前端呈现层、后端与 API 零改动）：
  岗位显示退税岗卡片：当晚只有一名协管员在退税岗时，页面卡片与
  个人「生成图片」都会渲染一行兜底说明「当天仅您一名协管员在岗」
  （看他人时为「当天仅X一名协管员在岗」）。用户明确要求这行去掉：
  无同岗时不渲染任何说明行（空段落也不留）。有同岗时的「同岗：X」
  行（页面 hint + 导图）按用户确认保留不动；卡片页脚（带班…｜
  退税岗 名单）不动。实现：两处 tax 分支改为条件渲染
  （others.length 才拼 partnerLine / partnerDiv），words.only 文案
  随之删除（words 只保留 poss/subj）。

测试口径：
  S) 静态检查：版本标记；全文件无「当天仅」；words 不再含 only
     键；两处 tax 分支的条件渲染式在位；同岗模板式仍在 2 处；
     页脚退税岗行原文未动。
  F) 函数级（Node 抽取 app.js 真实函数 esc/datePartsOf/
     myShiftCardHTML/myPostsImage，桩 document/html2canvas/toast）：
     页面与导图各跑 4 个场景——本人/他人 × 独自一人/有同岗：
     独自一人时输出无「当天仅」、无「同岗：」、页面 hint 段落只剩
     页脚 1 个；有同岗时「同岗：<对方姓名>」仍在、页面 hint 为 2 个。
"""
import json
import os
import shutil
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


NODE_SRC = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
function extract(re, name) { const m = src.match(re); if (!m) throw new Error('extract: ' + name); return m[0]; }
const code = [
  extract(/function esc\(s\) \{[\s\S]*?\n\}/, 'esc'),
  extract(/function datePartsOf\(s\) \{[^\n]*\}/, 'datePartsOf'),
  extract(/function myShiftCardHTML\(label, e, selfName, words\) \{[\s\S]*?\n\}/, 'myShiftCardHTML'),
  extract(/function myPostsImageCardHTML\(out\) \{[\s\S]*?\n\}/, 'myPostsImageCardHTML'),
  extract(/async function myPostsImage\(\) \{[\s\S]*?\n\}/, 'myPostsImage'),
].join('\n');
let captured = null;
const document = {
  createElement(tag) {
    return { style: {}, innerHTML: '', firstElementChild: {}, remove() {}, click() {}, href: '', download: '' };
  },
  body: { appendChild(el) { captured = el.innerHTML; } },
};
async function html2canvas() { return { toDataURL() { return 'data:image/png;base64,AAAA'; } }; }
function toast() {}
let mypostsState = null;
eval(code);
const out = {};
const wordsSelf = { poss: '您的', subj: '您' };
const wordsOther = { poss: 'KKK的', subj: 'KKK' };
function taxE(tax_names) { return { status: 'tax', leader_name: 'AAA', crew: [], tax_names }; }
out.page_lone_self = myShiftCardHTML('晚班', taxE(['JJJ']), 'JJJ', wordsSelf);
out.page_two_self = myShiftCardHTML('晚班', taxE(['JJJ', 'KKK']), 'JJJ', wordsSelf);
out.page_lone_other = myShiftCardHTML('晚班', taxE(['KKK']), 'KKK', wordsOther);
out.page_two_other = myShiftCardHTML('晚班', taxE(['KKK', 'JJJ']), 'KKK', wordsOther);
async function img(state) { captured = null; mypostsState = state; await myPostsImage(); return captured; }
(async () => {
  const base = { date: '2026-11-03', shift_label: '晚班' };
  out.img_lone_self = await img({ ...base, is_self: true, viewer: { name: 'JJJ' }, result: taxE(['JJJ']) });
  out.img_two_self = await img({ ...base, is_self: true, viewer: { name: 'JJJ' }, result: taxE(['JJJ', 'KKK']) });
  out.img_lone_other = await img({ ...base, is_self: false, viewer: { name: 'KKK' }, result: taxE(['KKK']) });
  out.img_two_other = await img({ ...base, is_self: false, viewer: { name: 'KKK' }, result: taxE(['KKK', 'JJJ']) });
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""


def main():
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()

    check("S app.js 带 v6.11 版本标记", "/* duty-roster v6.31 */" in js)
    check("S app.js 全文无「当天仅」（兜底说明文案已彻底删除）", "当天仅" not in js)

    posts_seg = segment(js, "function myPostsHTML", "async function myPostsImage")
    check("S myPostsHTML 的 words 不再含 only 键（文案已删、只留 poss/subj）",
          "only:" not in posts_seg and "poss:" in posts_seg and "subj:" in posts_seg)

    card_seg = segment(js, "function myShiftCardHTML", "function myPostsHTML")
    img_seg = segment(js, "function myPostsImageCardHTML", "/* -------- 成员：当日排班")
    check("S 页面 tax 分支条件渲染（partnerLine 仅 others 非空时拼入）",
          "const partnerLine = others.length ?" in card_seg and "${partnerLine}" in card_seg)
    check("S 导图 tax 分支条件渲染（同岗行仅 others 非空时拼入 bodyHTML；v6.23 适配：卡片构建抽至纯函数 myPostsImageCardHTML）",
          "if (others.length) bodyHTML" in img_seg and "同岗：${others.map(esc).join('、')}" in img_seg)
    check("S 同岗模板式仍在页面与导图各一处（有同岗时的「同岗：X」保留）",
          js.count("同岗：${others.map(esc).join('、')}") == 2,
          f"count={js.count('同岗：')}")
    check("S 页脚退税岗行原文未动（带班…｜退税岗 <名单>）",
          "｜ 退税岗 ${e.tax_names.map(esc).join(' ')}" in card_seg)

    # ---- F) 函数级渲染（Node 抽取真实函数） ----
    node = shutil.which("node")
    check("F Node 可用（前端函数级回归）", bool(node))
    if node:
        with tempfile.TemporaryDirectory(prefix="duty-roster-v611-") as td:
            js_path = os.path.join(td, "render.js")
            with open(js_path, "w", encoding="utf-8") as f:
                f.write(NODE_SRC)
            run = subprocess.run([node, js_path, os.path.join(fe, "app.js")],
                                 capture_output=True, text=True, timeout=60)
            check("F Node 渲染脚本执行成功", run.returncode == 0,
                  (run.stderr or "")[:200])
            if run.returncode == 0:
                out = json.loads(run.stdout)
                pl = out["page_lone_self"]
                check("F 页面·独自一人：无「当天仅」、无「同岗：」、退税岗行与页脚仍在",
                      "当天仅" not in pl and "同岗：" not in pl
                      and "退税岗（晚班）" in pl and "带班：AAA" in pl
                      and "退税岗 JJJ" in pl)
                check("F 页面·独自一人：hint 段落只剩页脚 1 个（无空说明段）",
                      pl.count('<p class="hint">') == 1,
                      f"count={pl.count('<p class=' + chr(34) + 'hint' + chr(34) + '>')}")
                pt = out["page_two_self"]
                check("F 页面·有同岗：「同岗：KKK」仍在、无「当天仅」、hint 共 2 个",
                      "同岗：KKK" in pt and "当天仅" not in pt
                      and pt.count('<p class="hint">') == 2)
                po = out["page_lone_other"]
                check("F 页面·看他人独自一人：无「当天仅」、无「同岗：」、归属文案在位",
                      "当天仅" not in po and "同岗：" not in po
                      and "KKK的岗位" in po)
                pto = out["page_two_other"]
                check("F 页面·看他人有同岗：「同岗：JJJ」仍在、无「当天仅」",
                      "同岗：JJJ" in pto and "当天仅" not in pto)

                il = out["img_lone_self"]
                check("F 导图·独自一人：已生成卡片且无「当天仅」、无「同岗：」（v6.23 适配：导图已去带班行；v6.24 适配：标题行右侧只留「退税岗（晚班）」、不再带「您的岗位：」）",
                      bool(il) and "当天仅" not in il and "同岗：" not in il
                      and "退税岗（晚班）" in il and "您的岗位：" not in il and "带班：" not in il)
                it = out["img_two_self"]
                check("F 导图·有同岗：「同岗：KKK」仍在、无「当天仅」",
                      bool(it) and "同岗：KKK" in it and "当天仅" not in it)
                io = out["img_lone_other"]
                check("F 导图·看他人独自一人：无「当天仅」、无「同岗：」（v6.24 适配：导图标题行只留姓名+岗位本身，「KKK的岗位」短语仅页面保留）",
                      bool(io) and "当天仅" not in io and "同岗：" not in io
                      and "· KKK" in io and "KKK的岗位" not in io)
                ito = out["img_two_other"]
                check("F 导图·看他人有同岗：「同岗：JJJ」仍在、无「当天仅」",
                      bool(ito) and "同岗：JJJ" in ito and "当天仅" not in ito)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v6.11 引起的旧套件改动）：
  - 全部旧套件：版本标记断言由 v6.10 提升为 v6.11（仅标记字面量，
    共 30 个文件）；
  - smoke_test_v610.py「带前缀拼接仅剩退税岗独立标签行 2 处」断言
    适配：v6.11 起退税岗同岗行改走模板字面量（同岗：${…}）且仅在
    有同岗时渲染，旧引号拼接式（'同岗：' + others…）已退役——断言
    改为钉模板式恰出现 2 次、旧式消失，检查名已注明 v6.11 适配；
  - words.only 删除后，逐项核查引用面：app.js 内仅原 tax 分支一处
    使用、已随条件渲染摘除；无其他套件钉过该文案（「当天仅」在旧
    套件中零命中），其余断言原样成立；
  - 后端零改动：mine 响应结构不变，v64/v65/v68 的岗位显示数据
    断言不受影响。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.11 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：静态检查 + Node 函数级渲染（抽取 app.js 真实函数）——本次为呈现层改动，后端与 API 零改动\n")
            f.write("- v6.11：岗位显示退税岗卡片去掉单人兜底说明行（页面 + 个人导图两处）："
                    "无同岗协管员时不再渲染「当天仅…一名协管员在岗」，有同岗时的「同岗：X」行与卡片页脚保留不动。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.11: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
