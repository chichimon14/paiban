# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.21 冒烟测试（追加到 SMOKE_TEST.md 的 v6.21 章节）。

v6.21 变更（用户 2026-11-02 反馈，附岗位显示截图）：岗位显示页
的「人员」选人框原来列全员名单（含当天休假的人），应**只列当天
上班的人**。落地：/api/daily/mine 响应新增 on_duty_people（该日
在岗人员：干部+协管员、名单顺序、按展示网格计休符号判定；无
计划月份为空列表）；前端选人框不再一次性拉 /api/people 全员，
改由每次加载岗位显示时按 on_duty_people 同步生成选项；当前
选中者当天休假时自动落到本人（在岗时）或名单第一人并重查
一次。接口本身仍可查休假者状态（off），过滤只在选人框层面；
选人资格口径（v6.13）不变。

测试口径（临时库 + 临时端口 3027）：11-03 置 4 人休假后 mine
的 on_duty_people 恰为其余 7 人且顺序为名单序；全员在岗日
（11-04 早班）为 11 人全名单；无计划月份（12 月）为空列表；
休假者本人 mine 仍 200 且 result.status=off；前端静态（选人框
同步逻辑在位、bindMyPosts 不再拉 /api/people 全员名单）。
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
PORT = 3027
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


def main():
    tmpdb = os.path.join(tempfile.mkdtemp(prefix="duty-smoke-v621-"), "test.db")
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
        check("v6.21 服务启动", up)
        if not up:
            return 1

        atok = login("admin", "admin123")
        lw = login("CCC", "123456")
        st, people = req("GET", "/api/people", token=atok)
        pid_of = {p["name"]: p["id"] for p in people}
        ALL = [p["name"] for p in people]

        st, plan = req("POST", "/api/plans", token=atok,
                       body={"year": 2026, "month": 11, "quota": 9, "self_limit": 6})
        plan_id = plan["id"]
        req("PATCH", f"/api/plans/{plan_id}", token=atok, body={"phase_override": 3})
        for n in ("FFF", "HHH", "III", "KKK"):
            req("PUT", f"/api/plans/{plan_id}/cell", token=atok,
                body={"person_id": pid_of[n], "day": 3, "symbol": "X"})

        st, mine = req("GET", "/api/daily/mine?date=2026-11-03", token=lw)
        onduty = [p["name"] for p in mine.get("on_duty_people") or []]
        check("A 11-03 mine 带 on_duty_people：恰为当天在岗 7 人（干部 6+协管员JJJ）、名单顺序、休假 4 人不在内",
              st == 200 and onduty == ["AAA", "BBB", "CCC", "DDD",
                                        "EEE", "GGG", "JJJ"],
              str(onduty))
        st, mine4 = req("GET", "/api/daily/mine?date=2026-11-04", token=lw)
        onduty4 = [p["name"] for p in mine4.get("on_duty_people") or []]
        check("B 11-04 无人休假：on_duty_people 为全员 11 人名单",
              st == 200 and onduty4 == ALL, str(onduty4))
        st, mine12 = req("GET", "/api/daily/mine?date=2026-12-03", token=lw)
        check("C 12 月无计划：on_duty_people 为空列表、result.status=noplan",
              st == 200 and mine12.get("on_duty_people") == []
              and mine12["result"]["status"] == "noplan",
              str(mine12.get("on_duty_people")))
        st, c03 = req("GET", "/api/daily/context?date=2026-11-03", token=atok)
        d03 = c03["default"]
        req("POST", "/api/daily/assignments", token=atok,
            body={"date": "2026-11-03", "leader_id": d03["leader_id"],
                  "letters": d03["letters"]})
        lx = login("FFF", "123456")
        st, mine_lx = req("GET", "/api/daily/mine?date=2026-11-03", token=lx)
        check("D 接口层不拦截：休假者FFF本人查 11-03（已保存排班）仍 200、result.status=off（过滤只在选人框）",
              st == 200 and mine_lx["result"]["status"] == "off",
              str(mine_lx["result"]["status"]))
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
    bind_seg = segment(js, "function bindMyPosts()", "async function loadMyPosts()")
    load_seg = segment(js, "async function loadMyPosts()", "function myShiftCardHTML(")
    check("S app.js 带 v6.21 版本标记", "/* duty-roster v6.31 */" in js)
    check("S bindMyPosts 不再拉 /api/people 全员名单填充选人框",
          "/api/people" not in bind_seg)
    check("S loadMyPosts 按 on_duty_people 同步选人框（选项生成+选中失效自动落位）",
          "out.on_duty_people" in load_seg
          and "list.some((p) => p.id === mypostsPersonId)" in load_seg
          and "mypostsPickerFix" in load_seg)
    check("S 后端 mine 含 on_duty_people 计算（_is_off 判定+person_out 名单）",
          '"on_duty_people": on_duty_people' in backend
          and "on_duty_people = [person_out(p) for p in people if not _is_off(p[\"id\"])]" in backend)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v6.21 引起的旧套件改动）：全部 45 个旧套件仅
  版本标记断言字面量 v6.20→v6.21；mine 响应新增字段为向后兼容
  追加，选人接线相关静态断言（mpPerson/canPickPerson/person_id
  守卫）均未触及。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.21 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：临时数据库 + 临时服务端口 3027（API 行为）+ 纯静态检查（前端/后端）\n")
            f.write("- v6.21：岗位显示选人框只列当天上班的人——mine 响应新增 "
                    "on_duty_people，前端按其同步生成选项、选中者休假时自动落位。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.21: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
