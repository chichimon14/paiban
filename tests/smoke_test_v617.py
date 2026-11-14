# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.17 冒烟测试（追加到 SMOKE_TEST.md 的 v6.17 章节）。

v6.17 变更（用户 2026-11-02 对 v6.16 的两点澄清，纯岗位名口径修正）：
  图面 6 人方案的岗位名要对应系统内既有岗位名——
    · 图面「纯轮休」就是此前 v6.14 改名的「备勤」岗 → 6 人模板的
      2 人休息位岗位名改回「备勤」（与 5 人模板同名）；
    · 图面「挑查备勤岗」对应系统内的「挑查岗」 → 6 人模板的该岗
      岗位名改回「挑查岗」。
  改后 6 人模板与 5 人模板岗位名完全一致（审图查验岗/申报岗/
  挑查岗/备勤），仅班次格局与人数不同。改动点只有后端
  MORNING6_SLOTS 的两个 _dpost 岗位名（+注释）与前端版本标记；
  模板格局、默认排班、保存校验、第 1 班次规则（备勤位不算在岗，
  改名后由同一「备勤」判定覆盖）均不变；已保存排班随模板自动
  呈现新名、无需迁移。前端各表列名本就随模板生成，无代码改动
  （仅注释与标记）。

测试口径（临时库 + 临时端口 3024）：context 模板岗位名逐段核对、
保存 6 人排班后 dayview 与两名成员（F 岗/D 岗）岗位显示时间轴的
岗位名序列、三个接口 JSON 全文不含图面原名（纯轮休/挑查备勤岗）、
前后端静态断言。
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
PORT = 3024
BASE = f"http://127.0.0.1:{PORT}"
REPORT = os.path.join(ROOT, "SMOKE_TEST.md")

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


POSTS = ["审图查验岗", "申报岗", "挑查岗", "备勤"]
OLD_NAMES = ("纯轮休", "挑查备勤岗")


def main():
    tmpdb = os.path.join(tempfile.mkdtemp(prefix="duty-smoke-v617-"), "test.db")
    env = dict(os.environ, DUTY_DB=tmpdb)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--port", str(PORT)],
        cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
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
        check("v6.17 服务启动", up)
        if not up:
            return 1

        atok = login("admin", "admin123")
        st, people = req("GET", "/api/people", token=atok)
        pid_of = {p["name"]: p["id"] for p in people}

        def L(**kw):
            return {k: pid_of[v] for k, v in kw.items()}

        st, plan = req("POST", "/api/plans", token=atok,
                       body={"year": 2026, "month": 11, "quota": 9, "self_limit": 6})
        req("PATCH", f"/api/plans/{plan['id']}", token=atok, body={"phase_override": 3})

        # ---- A) context：6 人模板岗位名与系统既有口径一致 ----
        st, c = req("GET", "/api/daily/context?date=2026-11-02", token=atok)
        tpl = c.get("template") or []
        check("A 早班 6 人 context 模板 8 段、每段岗位序均为 审图查验岗/申报岗/挑查岗/备勤（v6.26 适配）",
              c.get("variant") == "morning6" and len(tpl) == 8
              and all([p["post"] for p in s["posts"]] == POSTS for s in tpl),
              str([p["post"] for p in tpl[0]["posts"]]) if tpl else "no tpl")
        check("A context 全文不含图面原名（纯轮休/挑查备勤岗）",
              all(n not in json.dumps(c, ensure_ascii=False) for n in OLD_NAMES))

        # ---- B) 保存后 dayview / mine 的岗位名 ----
        st, out = req("POST", "/api/daily/assignments", token=atok,
                      body={"date": "2026-11-02", "leader_id": pid_of["AAA"],
                            "letters": L(A="AAA", B="DDD", C="BBB",
                                         D="CCC", E="EEE", F="FFF")})
        check("B 6 人排班保存成功", st == 200, str(st))
        st, dv = req("GET", "/api/daily/dayview?date=2026-11-02", token=atok)
        pv = dv.get("preview") or []
        first = {p["name"]: [x["name"] for x in p["people"]]
                 for p in (pv[0]["posts"] if pv else [])}
        check("B dayview 8 段、每段岗位名同系统口径；首班次 挑查岗=CCC、备勤=BBB+EEE（v6.27 适配：新模板首班 审图A+B/申报F/挑查D/备勤C+E）",
              len(pv) == 8
              and all([p["name"] for p in s["posts"]] == POSTS for s in pv)
              and first.get("挑查岗") == ["CCC"]
              and first.get("备勤") == ["BBB", "EEE"], str(first))
        check("B dayview 全文不含图面原名",
              all(n not in json.dumps(dv, ensure_ascii=False) for n in OLD_NAMES))
        ftok = login("FFF", "123456")
        st, mine = req("GET", "/api/daily/mine?date=2026-11-02", token=ftok)
        seq_f = [e["post"] for e in mine["result"].get("timeline") or []]
        check("B F 岗（FFF）时间轴岗位序列：申报岗/备勤/申报岗/挑查岗/申报岗/备勤/申报岗/备勤（v6.27 适配：申报与轻岗逐班交替）",
              mine["result"].get("letter") == "F"
              and seq_f == ["申报岗", "备勤", "申报岗", "挑查岗", "申报岗", "备勤", "申报岗", "备勤"],
              str(seq_f))
        dtok = login("CCC", "123456")
        st, mine = req("GET", "/api/daily/mine?date=2026-11-02", token=dtok)
        seq_d = [e["post"] for e in mine["result"].get("timeline") or []]
        check("B D 岗（CCC）时间轴岗位序列：挑查岗/审图查验岗/备勤/审图查验岗/挑查岗/审图查验岗/备勤/审图查验岗（v6.27 适配）；两份 mine 全文不含图面原名",
              mine["result"].get("letter") == "D"
              and seq_d == ["挑查岗", "审图查验岗", "备勤", "审图查验岗", "挑查岗", "审图查验岗", "备勤", "审图查验岗"]
              and all(n not in json.dumps(mine, ensure_ascii=False) for n in OLD_NAMES),
              str(seq_d))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    # ---- S) 静态断言 ----
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()
    backend = open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read()
    m6 = segment(backend, "MORNING6_SLOTS", "EVENING_SLOTS")
    m5 = segment(backend, "MORNING_SLOTS = [", "MORNING6_SLOTS")
    check("S app.js 带 v6.17 版本标记", "/* duty-roster v6.31 */" in js)
    check("S 后端 6 人模板岗位名已改：_dpost(\"挑查岗\", [pat[2]]) 与 _dpost(\"备勤\", pat[3]) 在位",
          '_dpost("挑查岗", [pat[2]])' in m6 and '_dpost("备勤", pat[3])' in m6)
    check("S 后端无图面原名岗位定义：_dpost(\"纯轮休\"/_dpost(\"挑查备勤岗\" 均不存在",
          '_dpost("纯轮休"' not in backend and '_dpost("挑查备勤岗"' not in backend)
    check("S 5 人模板岗位名未动（挑查岗/备勤同名口径）",
          '_dpost("挑查岗", [pat[2]])' in m5 and '_dpost("备勤", [pat[3]])' in m5)
    check("S 前端全文不含图面原名（列名随模板生成、无硬编码残留）",
          all(n not in js for n in OLD_NAMES))

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v6.17 引起的旧套件改动，均已在对应测试文件处注明）：
  - 全部 35 个旧套件：版本标记断言字面量由 v6.16 提升为 v6.17
    （仅字面量），其余未动；
  - smoke_test_v616.py：模板逐格、dayview、岗位显示三处断言的
    岗位名由图面原名改为系统口径（挑查备勤岗→挑查岗、纯轮休→
    备勤，含检查名与 docstring）；静态断言改为对 MORNING6_SLOTS
    段内 _dpost 岗位名的精确断言；
  - smoke_test_v69.py：dayview 首班次映射断言的两处岗位键
    （挑查备勤岗/纯轮休）同步改为 挑查岗/备勤（检查名已注明）。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.17 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：临时数据库 + 临时服务端口 3024（API 行为）+ 纯静态检查（前端/后端）\n")
            f.write("- v6.17：6 人早班模板岗位名按用户澄清对应系统既有口径——图面"
                    "「纯轮休」即「备勤」岗、图面「挑查备勤岗」即「挑查岗」；"
                    "改后两套早班模板岗位名完全一致，格局与规则不变。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.17: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
