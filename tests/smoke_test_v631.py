# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.31 冒烟测试。

v6.31 变更（用户 2026-11-11 续定）：退税岗**所有班次都要带上**
退税岗人员——推翻此前「退税岗仅晚班」口径（v6.0 起）。落地范围：
- 后端：默认排班（default_daily_assignment）与保存
  （daily_save）的 tax_ids 不再按班次门控，早班同样带入当天
  全部在岗协管员；岗位显示 _mine_shift 早班协管员按 tax_ids
  判定 status=tax，不再恒回 na。
- 前端：复制岗位文本早班同样带退税岗行；生成排班页退税岗行
  早班同样显示（文案改「退税岗（自动）」）；管理员导图、成员
  当日排班页与导图、岗位显示页与个人导图的退税岗都不再按
  班次门控，个人导图/岗位行括号内跟实际班次（退税岗（早班））。
- 线上存量：已保存的早班排班 tax_ids 为空者按当天在岗协管员
  回填（含 11-12）——该步在部署时对生产库执行，不在本测试内。

测试口径：起真实服务（临时库）走 API 验证早班默认/保存/
mine/dayview 的退税岗；静态断言前后端班次门控已清除；
Node 抽取 dailyImageCardHTML/myPostsImageCardHTML 验证早班
导图带退税岗。
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT = os.path.join(ROOT, "SMOKE_TEST.md")
PORT = 31031
BASE = f"http://127.0.0.1:{PORT}"

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), "-", name, ("| " + str(detail) if detail else ""))


def req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}


def login(name, pw):
    st, out = req("POST", "/api/login", body={"username": name, "password": pw})
    return out.get("token") if st == 200 else None


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
  extract(/function myPostsImageCardHTML\(out\) \{[\s\S]*?\n\}/, 'myPostsImageCardHTML'),
].join('\n');
eval(code);
const NAMES = {1:'AAA',2:'BBB',3:'CCC',4:'DDD',5:'EEE',6:'FFF',7:'GGG',8:'HHH',9:'III',10:'JJJ',11:'KKK'};
function slot(start, end, posts) { return { start, end, posts: posts.map(([post, letters, extra]) => Object.assign({ post, letters }, extra || {})) }; }
const morningCtx = { date: '2026-11-12', shift: 'morning', shift_label: '早班', template: [
  slot('07:00','07:45', [['审图查验岗',['B','C']],['申报岗',['D']],['挑查岗',['E']],['备勤',['A']]]),
]};
const morningSaved = { leader_id: 1, letters: {A:4,B:3,C:5,D:1,E:9}, tax_ids: [10,11] };
const mineMorning = { date: '2026-11-12', shift_label: '早班', is_self: true, viewer: { name: 'JJJ' },
  result: { status: 'tax', leader_name: 'AAA', tax_names: ['JJJ', 'KKK'] } };
const out = {
  morningCard: dailyImageCardHTML(morningCtx, morningSaved, NAMES),
  mineCard: myPostsImageCardHTML(mineMorning),
};
console.log('RESULT ' + JSON.stringify(out));
"""


def main():
    fe = os.path.join(ROOT, "frontend")
    be = os.path.join(ROOT, "backend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()
    py = open(os.path.join(be, "main.py"), encoding="utf-8").read()

    check("S app.js 带 v6.31 版本标记", "/* duty-roster v6.31 */" in js)
    check("S 后端 tax_ids 班次门控已清除（全文无 if shift == \"evening\" else [] 的退税岗写法）",
          'if shift == "evening" else []' not in py
          and py.count('tax_ids = [p["id"] for p in assistants]') >= 2)
    check("S 后端 _mine_shift 早班协管员不再恒回 na（morning 门控已清除、tax 判定在 na 之前）",
          'if shift == "morning":\n            return {**base, "status": "na"}' not in py)
    check("S 前端退税岗班次门控已清除（无 ctx/out 的 evening 门控）且生成排班页文案改「退税岗（自动）」",
          "ctx.shift === 'evening'" not in js and "out.shift === 'evening'" not in js
          and "退税岗（自动）" in js and "退税岗（晚班自动）" not in js)
    check("S 岗位显示/个人导图的退税岗括号跟实际班次（label / out.shift_label 插值）、旧硬编码「退税岗（晚班）」与「早班不设退税岗」文案已清除",
          "退税岗（${esc(label)}）" in js and "退税岗（${esc(out.shift_label" in js
          and "退税岗（晚班）" not in js and "早班不设退税岗" not in js)

    node_out = None
    try:
        tmpdir = tempfile.mkdtemp(prefix="duty-roster-v631-node-")
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

    mc = (node_out or {}).get("morningCard") or ""
    check("N 管理员早班导图：标题行带「退税岗：JJJ KKK」（位于 <table> 之前）",
          "退税岗：JJJ KKK" in mc.split("<table")[0], mc.split("<table")[0][-120:])
    mp = (node_out or {}).get("mineCard") or ""
    check("N 个人导图（早班退税岗）：标题行右侧呈「退税岗（早班）」、同岗行含KKK",
          "退税岗（早班）" in mp and "同岗：KKK" in mp, mp[:120])

    # ---- 真实服务：早班退税岗全链路 ----
    tmpdb = os.path.join(tempfile.mkdtemp(prefix="duty-smoke-v631-"), "test.db")
    env = dict(os.environ, DUTY_DB=tmpdb)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--port", str(PORT)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        up = False
        for _ in range(60):
            try:
                st, _ = req("GET", "/api/health")
                if st == 200:
                    up = True
                    break
            except Exception:
                pass
            time.sleep(0.5)
        check("A v6.31 服务启动", up)
        if not up:
            return 1
        atok = login("admin", "admin123")
        gtok = login("JJJ", "123456")
        st, people = req("GET", "/api/people", token=atok)
        pid_of = {p["name"]: p["id"] for p in people}
        st, plan = req("POST", "/api/plans", token=atok,
                       body={"year": 2026, "month": 11, "quota": 9, "self_limit": 6})
        plan_id = plan["id"]
        req("PATCH", f"/api/plans/{plan_id}", token=atok, body={"phase_override": 3})

        st, c = req("GET", "/api/daily/context?date=2026-11-12", token=atok)
        check("A 早班（11-12）默认排班退税岗带入两名在岗协管员",
              st == 200 and c["shift"] == "morning"
              and c["default"]["tax_ids"] == [pid_of["JJJ"], pid_of["KKK"]],
              str(c.get("default", {}).get("tax_ids")))
        d = c["default"]
        st, out = req("POST", "/api/daily/assignments", token=atok,
                      body={"date": "2026-11-12", "leader_id": d["leader_id"],
                            "letters": d["letters"]})
        check("A 保存早班后 saved.tax_ids 为两名协管员（服务端计算）",
              st == 200 and out["saved"]["tax_ids"] == [pid_of["JJJ"], pid_of["KKK"]],
              str(out.get("saved")))
        st, mine = req("GET", "/api/daily/mine?date=2026-11-12", token=gtok)
        check("A 协管员JJJ看自己 11-12 早班：status=tax（不再 na）、tax_names 两人",
              st == 200 and mine["result"]["status"] == "tax"
              and mine["result"]["tax_names"] == ["JJJ", "KKK"],
              str(mine.get("result")))
        st, dv = req("GET", "/api/daily/dayview?date=2026-11-12", token=gtok)
        check("A 成员 dayview 11-12 早班：tax_names 两人",
              st == 200 and dv.get("tax_names") == ["JJJ", "KKK"],
              str(dv.get("tax_names")))
        # 一名协管员休假 → 早班退税岗只带另一人
        req("PUT", f"/api/plans/{plan_id}/cell", token=atok,
            body={"person_id": pid_of["JJJ"], "day": 12, "symbol": "X"})
        st, c = req("GET", "/api/daily/context?date=2026-11-12&refresh=1", token=atok)
        d = c["default"]
        st, out = req("POST", "/api/daily/assignments", token=atok,
                      body={"date": "2026-11-12", "leader_id": d["leader_id"],
                            "letters": d["letters"]})
        check("A JJJ休假后重存早班：退税岗只记KKK一人",
              st == 200 and out["saved"]["tax_ids"] == [pid_of["KKK"]],
              str(out.get("saved")))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()

    return 0 if all(r[1] for r in results) else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.31 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：纯静态检查 + Node 函数级验证 + 真实服务 API（临时库）\n")
            f.write("- v6.31：退税岗所有班次都带（用户 2026-11-11 续定，推翻仅晚班口径）——后端默认/保存/mine、前端复制/导图/岗位显示全链路去班次门控。\n")
            f.write("- 适配说明：全部旧套件版本标记字面量随版本提升至 v6.31；v60/v61/v69 的早班退税岗为空断言、v610/v69 的 evening 门控断言、v622/v629 的早班导图无退税岗断言、v630 的早班复制不带退税岗断言均已按新口径改述并在检查名注明。\n")
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.31: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
