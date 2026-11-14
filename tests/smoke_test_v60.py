# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.0 冒烟测试（追加到 SMOKE_TEST.md 的 v6.0 章节）。

v6.0 变更（后端 backend/main.py + 前端 app.js/style.css）：
  A) 新增「当日排班」子系统：在月度选休排班之上，按日期+班次给当天
     上班的 9 名干部排具体岗位——5 人映射字母 A–E 套入固定轮转模板
     （早班 10 时段×45 分钟：审图 2/申报/挑查/轮休，字母格局周期 5；
     晚班 8 时段：审图 A+B 与 C+D 两组轮换、申报部分时段两组各半小时、
     空白时段 E 全程、末段 A+B 轮流），另含带班（值班科长，默认当天
     在岗最高职务者）与晚班退税岗（当天在岗协管员全部，自动带入）。
  B) 默认排班按「全员历史累计」均衡生成（用户定口径：纳入全员数据、
     足够长的时间内所有人的各字母岗次数趋近相同，而非次日顺延）：
     历史 = 全部已保存 daily_assignments 按 (班次, 人, 字母) 计数；
     按字母优先级逐个贪心填充——早班 A→E→B→C→D（A 最抢手、E 次之），
     晚班 A→B→C→D→E（无偏好）；每字母取 (该字母历史次数, 该班次总
     次数, 名单顺序) 最小者。在岗判定与排班表展示网格同源（最终表 >
     提交源数据汇总 > 草稿；计休符号=休假，备勤 B=在岗，无数据=全员
     在岗）。新表 daily_assignments（UNIQUE(plan_id, date, shift)，
     upsert 保存；退税岗由服务端按当天在岗协管员自动计算）。
  C) 接口：GET /api/daily/context（date+shift；超管/人员管理员；
     返回在岗名单、历史累计、已保存/默认排班、模板字母结构、预览）、
     POST /api/daily/assignments（校验：带班须为在岗科领导、字母须
     A–E 五个互不重复且均为当天在岗干部）、GET /api/daily/mine
     （本人某日早/晚两班岗位：字母+个人时间轴/退税岗/休假/未排等状态；
     无对应人员账号返回空态）。
  D) 前端两页：管理员「生成当日排班」（#/daily；超管侧栏「排班」组 +
     人员管理员成员式侧栏，普通成员无）——日期（默认今天；v6.0 当时为默认明天，v6.15 改）+早/晚班
     切换、带班下拉、A–E 五个下拉（选人互斥：占用者在其余下拉禁用，
     改选冲突时清空原岗并 toast）、在岗名单旁附本班次历史累计、
     晚班退税岗自动行、模板实时预览、保存/按轮换重置默认/生成图片
     （与已保存一致才可点；晚班按图4 文案四行、早班按图3 时段表，
     均走 html2canvas 白底卡片导出 PNG）；成员「岗位显示」(#/myposts；
     单起左侧目录项，排班表之后；有对应人员者都有，超管无）——日期
     前后翻页，早/晚两卡显示本人字母岗时间轴（含同时段同岗同事；
     申报各半小时为独立值守、末段轮流整段一条）、协管员晚班退税岗、
     休假/未生成/未排入等状态，只读。
  E) 附带 v5.3 弹层收紧（仅 style.css）：现有小屏段
     (@media (max-width: 640px), (max-height: 500px)) 行高 44px→40px
     （4 列不变）；其后新增 @media (max-height: 500px) 横屏矮屏段：
     面板 min(400px, 94vw)、5 列、行高 38px、gap 5px、符号 15px、
     名称 10px nowrap、面板内距 6px、标题 13px、清除按钮 30px/12px，
     整层约 250px。桌面规则与 placePicker 定位逻辑未动。

【v6.1 适配（2026-11-01）】班次改为按日期轮替推导（锚点 2026-11-02
= 早班），context 不再传 shift、mine 改单班次 result 结构；本套件场景
日期已按奇偶全部对齐到目标班次（早班用偶数偏移日、晚班用奇数偏移
日），mine 断言改读 result；另因 v6.1 默认排班新增「一科领导带一
干部」搭配修正，A 节晚班零历史默认与 B 节次日早班默认的确切人选
随修正结果更新（断言处已注明）。save() 仍保留 shift 形参仅作场景
标注，请求体不再发送（服务端按日期推导）。

测试口径（临时库 + 临时端口 3010）：零历史默认按优先级+名单顺序；
保存一班后次日默认按历史最少者轮换（确定性场景断言确切人选）；
退税岗双人在岗全带入/一人在岗只带一人/早班恒空；校验与权限
（成员 403、管理员与超管 200、重复字母/带班非科领导/带班或排岗
人员当天休假均 400）；重复保存 upsert 不重复计历史；岗位显示
时间轴（早班 A 岗 10 段含轮休与审图同岗、晚班 E 岗四段申报、
晚班 C 岗申报半小时独立段）、休假状态、无计划月份与无人员账号
空态；前端静态断言（导航按角色、路由 guard、图片文案、v5.3 段）。
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
PORT = 3010
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
    i = text.find(start)
    if i < 0:
        return ""
    j = text.find(end, i + len(start))
    return text[i:] if j < 0 else text[i:j + len(end)]


def main():
    tmpdb = os.path.join(tempfile.mkdtemp(prefix="duty-smoke-v60-"), "test.db")
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
        check("v6.0 服务启动", up)
        if not up:
            return 1

        atok = login("admin", "admin123")
        st, users = req("GET", "/api/users", token=atok)
        lw_user = [u for u in users if u["username"] == "CCC"][0]
        req("PATCH", f"/api/users/{lw_user['id']}", token=atok, body={"is_admin": True})
        ltok = login("CCC", "123456")   # 人员管理员
        xtok = login("FFF", "123456")   # 普通成员（干部）
        btok = login("KKK", "123456")  # 普通成员（协管员）
        mtok = login("BBB", "123456")  # 副科长（本人有管理员，此处只用 mine）
        st, people = req("GET", "/api/people", token=atok)
        P = {p["name"]: p for p in people}
        pid_of = {n: P[n]["id"] for n in P}

        st, plan = req("POST", "/api/plans", token=atok,
                       body={"year": 2026, "month": 11, "quota": 9, "self_limit": 6})
        plan_id = plan["id"]
        req("PATCH", f"/api/plans/{plan_id}", token=atok, body={"phase_override": 3})

        def ctx(date, token=atok):
            # v6.1：班次由服务端按日期推导，context 不再传 shift
            return req("GET", f"/api/daily/context?date={date}", token=token)

        def save(date, shift, leader, letters, token=atok):
            # v6.1：shift 形参仅作场景标注（日期奇偶须与目标班次对齐），
            # 请求体不再发送 shift，服务端按日期推导
            return req("POST", "/api/daily/assignments", token=token,
                       body={"date": date, "leader_id": leader,
                             "letters": letters})

        def L(**kw):
            return {k: pid_of[v] for k, v in kw.items()}

        # ---- A) 零历史默认：优先级 + 名单顺序 ----
        st, c = ctx("2026-11-02")
        d = c["default"]
        check("上下文 200 且零历史早班默认（v6.16 适配：在岗 9 人走 6 人方案；v6.19 适配：值班科长AAA不参与字母排班；v6.27 适配：新模板第 1 时段在岗集 {A,B,D,F} 与审图对 (A,B)/(C,D) 变化、优化落点随之变：A DDD/B CCC/C BBB/D EEE/E FFF/F GGG；v6.1 该日推导为早班）",
              st == 200 and c["shift"] == "morning"
              and d["letters"] == L(A="DDD", B="CCC", C="BBB", D="EEE", E="FFF", F="GGG"),
              str(d["letters"]))
        check("早班默认带班为科长AAA、无已保存、在岗干部 9 人/协管员 2 人（v6.31 适配：退税岗所有班次都带，早班默认同样带入两名协管员）",
              d["leader_id"] == pid_of["AAA"] and c["saved"] is None
              and d["tax_ids"] == [pid_of["JJJ"], pid_of["KKK"]] and len(c["on_duty_cadre"]) == 9
              and len(c["on_duty_assistants"]) == 2)
        st, c = ctx("2026-11-03")
        d = c["default"]
        check("零历史晚班默认（v6.20 适配：在岗 9 人走晚班 6 人固定岗结构——带班轮流首位AAA不占字母、A BBB/B DDD/C CCC/D EEE/E FFF/F GGG；原 v6.1 搭配修正口径只适用于 5 人晚班）",
              c["shift"] == "evening" and c["variant"] == "evening6"
              and d["leader_id"] == pid_of["AAA"]
              and d["letters"] == L(A="BBB", B="DDD", C="CCC", D="EEE", E="FFF", F="GGG"),
              str(d["letters"]))
        check("晚班默认退税岗带入两名在岗协管员；模板 8 时段且首段审图 A+B/申报 E、次段审图 C+D/申报 F（v6.20 适配：6 人模板固定岗，不再 C/D 半小时拆分顶申报）",
              d["tax_ids"] == [pid_of["JJJ"], pid_of["KKK"]]
              and len(c["template"]) == 8
              and [p["letters"] for p in c["template"][0]["posts"]] == [["A", "B"], ["E"]]
              and [p["letters"] for p in c["template"][1]["posts"]] == [["C", "D"], ["F"]])

        # ---- B) 历史均衡：保存后次日默认轮换到历史最少者 ----
        st, out = save("2026-11-02", "morning", pid_of["BBB"],
                       L(A="FFF", B="AAA", C="BBB", D="CCC", E="DDD"))
        check("超管保存早班成功（v6.31 适配：早班保存同样带入退税岗两名协管员）",
              st == 200 and out["saved"]["tax_ids"] == [pid_of["JJJ"], pid_of["KKK"]] and out["saved"]["leader_id"] == pid_of["BBB"])
        st, c = ctx("2026-11-04")
        check("次日早班默认按历史均衡 + 优化（v6.16 适配：6 人方案 A–F；v6.19 适配：值班科长AAA不参与字母排班；v6.26 适配：新模板第 1 时段在岗集与审图对变化、优化落点随之变：A BBB/B GGG/C CCC/D III/E EEE/F HHH）",
              c["default"]["letters"] == L(A="BBB", B="GGG", C="CCC", D="III", E="EEE", F="HHH"),
              str(c["default"]["letters"]))
        hs = c["history_stats"][str(pid_of["FFF"])]
        check("历史累计按（班次,人,字母）计数（FFF早班 A=1、total=1）",
              hs["A"] == 1 and hs["total"] == 1, str(hs))

        # ---- C) 晚班均衡与退税岗（双人在岗） ----
        st, out = save("2026-11-03", "evening", pid_of["AAA"],
                       L(A="GGG", B="HHH", C="AAA", D="EEE", E="BBB"))
        check("晚班保存后退税岗自动带入两名协管员（服务端计算）",
              st == 200 and out["saved"]["tax_ids"] == [pid_of["JJJ"], pid_of["KKK"]])
        st, c = ctx("2026-11-05")
        check("次日晚班默认 A 轮换给历史最少者CCC（昨日得 A 的GGG A 次数已为 1；v6.1 搭配修正不改动 A）",
              c["default"]["letters"]["A"] == pid_of["CCC"], str(c["default"]["letters"]))

        # ---- D) 退税岗：一名协管员休假时只带另一人 ----
        req("PUT", f"/api/plans/{plan_id}/cell", token=atok,
            body={"person_id": pid_of["KKK"], "day": 5, "symbol": "X"})
        st, c = ctx("2026-11-05")
        check("KKK休假日：晚班在岗协管员仅JJJ、默认退税岗只带她一人",
              [p["name"] for p in c["on_duty_assistants"]] == ["JJJ"]
              and c["default"]["tax_ids"] == [pid_of["JJJ"]])
        st, c = ctx("2026-11-06")
        check("次日早班（v6.1 按日轮替推导）默认退税岗（v6.31 适配：所有班次都带；KKK仅 5 日休假、6 日两名协管员均在岗）",
              c["shift"] == "morning" and c["default"]["tax_ids"] == [pid_of["JJJ"], pid_of["KKK"]])
        st, out = save("2026-11-05", "evening", pid_of["AAA"],
                       L(A="AAA", B="BBB", C="CCC", D="DDD", E="EEE"))
        check("保存该日晚班后退税岗只记JJJ一人",
              st == 200 and out["saved"]["tax_ids"] == [pid_of["JJJ"]])

        # ---- E) 校验与权限 ----
        body6 = {"date": "2026-11-06", "shift": "evening", "leader_id": pid_of["AAA"],
                 "letters": L(A="AAA", B="BBB", C="CCC", D="DDD", E="EEE")}
        st, _ = req("POST", "/api/daily/assignments", token=xtok, body=body6)
        check("普通成员保存当日排班 → 403", st == 403, str(st))
        st, _ = ctx("2026-11-06", token=xtok)
        check("普通成员读排班上下文 → 403", st == 403, str(st))
        st, _ = ctx("2026-11-06", token=ltok)
        check("人员管理员可读排班上下文 → 200", st == 200, str(st))
        st, out = save("2026-11-06", "evening", pid_of["AAA"],
                       {"A": pid_of["AAA"], "B": pid_of["AAA"], "C": pid_of["CCC"],
                        "D": pid_of["DDD"], "E": pid_of["EEE"]})
        check("同一人占两个字母 → 400", st == 400, str(st))
        st, out = save("2026-11-06", "evening", pid_of["AAA"],
                       L(A="AAA", B="BBB", C="CCC", D="DDD"))
        check("字母未排满 A–E → 400", st == 400, str(st))
        st, out = save("2026-11-06", "evening", pid_of["DDD"],
                       L(A="AAA", B="BBB", C="CCC", D="EEE", E="FFF"))
        check("带班不是科领导（科员DDD）→ 400", st == 400, str(st))
        req("PUT", f"/api/plans/{plan_id}/cell", token=atok,
            body={"person_id": pid_of["BBB"], "day": 6, "symbol": "X"})
        st, out = save("2026-11-06", "morning", pid_of["BBB"],
                       L(A="AAA", B="CCC", C="DDD", D="EEE", E="FFF"))
        check("带班当天休假（BBB 6 日休）→ 400", st == 400, str(st))
        st, out = save("2026-11-06", "morning", pid_of["AAA"],
                       L(A="AAA", B="CCC", C="DDD", D="EEE", E="BBB"))
        check("排岗人员当天休假（BBB占 E）→ 400", st == 400, str(st))
        st, out = req("POST", "/api/daily/assignments", token=ltok,
                      body={"date": "2026-11-06", "shift": "evening",
                            "leader_id": pid_of["AAA"],
                            "letters": L(A="AAA", B="CCC", C="DDD", D="EEE", E="FFF")})
        check("人员管理员保存当日排班 → 200", st == 200, str(st))

        # ---- F) upsert：同日同班次重复保存只记最新、历史不重复计 ----
        save("2026-11-08", "morning", pid_of["AAA"],
             L(A="AAA", B="BBB", C="CCC", D="DDD", E="EEE"))
        save("2026-11-08", "morning", pid_of["BBB"],
             L(A="BBB", B="AAA", C="CCC", D="DDD", E="EEE"))
        st, c = ctx("2026-11-08")
        hs1 = c["history_stats"][str(pid_of["AAA"])]
        hs2 = c["history_stats"][str(pid_of["BBB"])]
        check("重复保存为原地更新（已保存 A 变为BBB、带班变为BBB）",
              c["saved"]["letters"]["A"] == pid_of["BBB"]
              and c["saved"]["leader_id"] == pid_of["BBB"])
        check("历史不重复计：AAA早班 A=1（来自 11-06 人员管理员保存——v6.1 按日推导为早班入账；本日改排覆盖的不重复计）、B=2（11-02 与 11-08 各一次）；BBB A=1",
              hs1["A"] == 1 and hs1["B"] == 2 and hs2["A"] == 1,
              f"{hs1} / {hs2}")

        # ---- G) 岗位显示（mine；v6.1 单班次 result 结构） ----
        save("2026-11-08", "morning", pid_of["AAA"],
             L(A="AAA", B="BBB", C="CCC", D="DDD", E="EEE"))
        save("2026-11-09", "evening", pid_of["AAA"],
             L(A="GGG", B="HHH", C="AAA", D="EEE", E="BBB"))
        ctok = login("AAA", "123456")
        st, mine = req("GET", "/api/daily/mine?date=2026-11-08", token=ctok)
        mo = mine["result"]
        tl = {e["time"]: e for e in mo["timeline"]}
        check("本人早班为 A 岗且时间轴 10 段（首段 07:00–07:45 备勤；v6.14 适配：当日休息位原称轮休；v6.1 mine 为单班次 result）",
              mine["shift"] == "morning" and mo["status"] == "ok" and mo["letter"] == "A"
              and len(mo["timeline"]) == 10
              and mo["timeline"][0]["post"] == "备勤" and mo["timeline"][0]["time"] == "07:00–07:45")
        # v6.25 适配：11-08 在新模板分界（11-05）之后，A 岗时段随新
        # 模板——08:30–09:15 由旧模板的审图（与 B 同岗）变为挑查岗；
        # 审图同岗断言改钉 07:45–08:30（新模板审图 A+C、同岗为
        # C 岗CCC）。
        check("早班 A 岗 07:45–08:30 审图查验岗同岗同事为 C 岗CCC；08:30–09:15 为挑查岗（v6.25 新模板）",
              tl["07:45–08:30"]["post"] == "审图查验岗" and tl["07:45–08:30"]["partners"] == ["CCC"]
              and tl["08:30–09:15"]["post"] == "挑查岗",
              str(tl.get("08:30–09:15")))
        st, mine = req("GET", "/api/daily/mine?date=2026-11-09", token=ctok)
        ev = mine["result"]
        check("本人晚班为 C 岗：首段申报 14:30–15:00 为独立半小时段（无同岗同事）",
              mine["shift"] == "evening" and ev["status"] == "ok" and ev["letter"] == "C"
              and any(e["time"] == "14:30–15:00" and e["post"] == "申报岗" and e["partners"] == []
                      for e in ev["timeline"]))
        st, mine = req("GET", "/api/daily/mine?date=2026-11-09", token=mtok)
        ev = mine["result"]
        check("晚班 E 岗（BBB）时间轴恰为四段申报（16:30/17:30/19:30/20:30 起）",
              ev["status"] == "ok" and ev["letter"] == "E"
              and [e["time"] for e in ev["timeline"]] ==
                  ["16:30–17:30", "17:30–18:30", "19:30–20:30", "20:30–21:15"]
              and all(e["post"] == "申报岗" for e in ev["timeline"]),
              str([e["time"] for e in ev["timeline"]]))
        st, mine = req("GET", "/api/daily/mine?date=2026-11-09", token=btok)
        tax_ok = mine["result"]["status"] == "tax" \
            and set(mine["result"]["tax_names"]) == {"JJJ", "KKK"}
        st, mine = req("GET", "/api/daily/mine?date=2026-11-08", token=btok)
        check("协管员KKK：晚班为退税岗（两人都在名单）、早班同样为退税岗（v6.31 适配：所有班次都带，不再 na）",
              tax_ok and mine["result"]["status"] == "tax"
              and set(mine["result"]["tax_names"]) == {"JJJ", "KKK"})
        st, mine_m = req("GET", "/api/daily/mine?date=2026-11-08", token=xtok)
        st, mine_e = req("GET", "/api/daily/mine?date=2026-11-09", token=xtok)
        check("在岗但未排入 A–E 的干部（FFF）早晚两日均为 notassigned",
              mine_m["result"]["status"] == "notassigned"
              and mine_e["result"]["status"] == "notassigned")
        save("2026-11-10", "morning", pid_of["AAA"],
             L(A="FFF", B="AAA", C="BBB", D="CCC", E="DDD"))
        req("PUT", f"/api/plans/{plan_id}/cell", token=atok,
            body={"person_id": pid_of["FFF"], "day": 10, "symbol": "X"})
        st, mine = req("GET", "/api/daily/mine?date=2026-11-10", token=xtok)
        check("排岗后改为休假：岗位显示为 off（您当天休假）且 off_symbol 带出",
              mine["result"]["status"] == "off" and bool(mine["off_symbol"]))
        st, mine = req("GET", "/api/daily/mine?date=2027-03-01", token=xtok)
        check("无计划月份：岗位显示返回 plan=null 且 result 为 noplan 空态",
              mine["plan"] is None and mine["result"]["status"] == "noplan")
        st, mine = req("GET", "/api/daily/mine?date=2026-11-08", token=atok)
        check("v6.4 适配：超管账号无对应人员时岗位显示默认名单第一人视图（has_person=true、viewer=AAA、is_self=false，不再是空态）",
              st == 200 and mine["has_person"] is True
              and (mine.get("view_person") or {}).get("name") == "AAA"
              and mine.get("is_self") is False)
        st, _ = ctx("2027-03-01")
        check("无计划月份读排班上下文 → 404", st == 404, str(st))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    # ---- H) 前端静态断言 ----
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()
    css = open(os.path.join(fe, "style.css"), encoding="utf-8").read()
    backend = open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read()

    check("app.js 带 v6.3 版本标记", "/* duty-roster v6.31 */" in js)
    nav = segment(js, "const NAV = [", "];")
    check("超管侧栏「排班」组：排班表之后新增「生成排班」（daily；v6.16 适配：原名「生成当日排班」改名）；v6.4 适配：NAV 新增岗位显示（myposts，超管靠选人使用）",
          nav.index("{ route: 'sheet'") < nav.index("{ route: 'daily', icon: '🗓', label: '生成排班' }")
          and "{ route: 'myposts', icon: '🧭', label: '岗位显示' }" in nav)
    navfn = segment(js, "function renderNav()", "function currentRoute()")
    check("成员式侧栏：岗位显示（#/myposts，有对应人员才加）+ 生成当日排班（#/daily，仅 myRole()==='admin' 才加）",
          "m.href = '#/myposts';" in navfn and "me.person_id" in navfn
          and "d.href = '#/daily';" in navfn and "if (myRole() === 'admin')" in navfn
          and "<span>岗位显示</span>" in navfn and "<span>生成排班</span>" in navfn)
    check("路由 guard：成员可用 sheet/password/myposts，人员管理员另含 daily；v6.4 适配：超管 myposts 不再回落 sheet（guard 已去掉 myposts）；v6.9 适配：成员白名单新增 dayview（当日排班只读页）",
          "['sheet', 'password', 'myposts', 'daily']" in js
          and "['sheet', 'password', 'myposts', 'dayview']" in js
          and "(route === 'pick' || route === 'home' || route === 'process')) route = 'sheet';" in js)
    check("两页视图与函数齐全（viewDaily/bindDaily/loadDaily/renderDailyBody/dailyPreviewHTML/saveDaily/dailyImage + viewMyPosts/bindMyPosts/loadMyPosts/myPostsHTML）",
          "daily: { render: viewDaily, bind: bindDaily }" in js
          and "myposts: { render: viewMyPosts, bind: bindMyPosts }" in js
          and all(f"function {f}" in js or f"async function {f}" in js for f in
                  ("viewDaily", "bindDaily", "loadDaily", "renderDailyBody", "dailyPreviewHTML",
                   "saveDaily", "dailyImage", "viewMyPosts", "bindMyPosts", "loadMyPosts", "myPostsHTML")))
    img = segment(js, "function dailyImageCardHTML", "/* -------- 成员：岗位显示")
    check("晚班图片与早班同为时段表格式（v6.22 适配：原图4 四行文案版已废止——标题+带班+退税岗行+时间/审图查验岗/申报岗整表、无「第一组/第二组」文案行）",
          all(s in img for s in ("带班：", "退税岗：", "审图查验岗", "申报岗"))
          and "第一组：" not in img and "第二组：" not in img
          and "html2canvas" in img)
    check("早班图片为图3 时段表（带班行 + 时段表）（v6.14 适配：原「轮休」表头改称备勤；v6.16 适配：表头列改随模板首段岗位名生成 ctx.template[0].posts，不再硬编码列名）",
          "ctx.template[0].posts" in img and "ctx.template.map" in img)
    check("生成图片与已保存状态挂钩（dailySig 比对、未保存改动时按钮 disabled + 先保存提示）",
          "dailySig(f) !== dailyState.savedSig" in js and "先点「保存排班」再生成图片" in js)
    check("后端含当日排班表与三接口（daily_assignments / context / assignments / mine）",
          "CREATE TABLE IF NOT EXISTS daily_assignments" in backend
          and '"/api/daily/context"' in backend and '"/api/daily/assignments"' in backend
          and '"/api/daily/mine"' in backend
          and "DAILY_PRIORITY" in backend)
    # v5.3 弹层收紧（随 v6.0 交付）
    land = segment(css, "@media (max-height: 500px)", "/* toast */")
    check("v5.3 横屏矮屏段存在且数值到位（面板 min(400px, 94vw)/内距 6px、5 列、行高 38px、gap 5px）",
          bool(land) and ".picker { width: min(400px, 94vw); padding: 6px; }" in land
          and "grid-template-columns: repeat(5, 1fr)" in land
          and "grid-auto-rows: 38px" in land and "gap: 5px" in land)
    check("v5.3 矮屏段字号与清除按钮（符号 15px、名称 10px nowrap、标题 13px、清除 30px/12px）",
          ".picker-grid button .sym { font-size: 15px; }" in land
          and ".picker-grid button .nm { font-size: 10px; white-space: nowrap; }" in land
          and ".picker-head { font-size: 13px;" in land
          and ".picker-clear { height: 30px; font-size: 12px;" in land)
    check("v6.0 页面样式就位（.seg-toggle / .daily-table / .letter-badge）",
          ".seg-toggle {" in css and ".daily-table {" in css and ".letter-badge {" in css)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v6.0 引起的旧套件改动，均已在对应测试文件处注明）：
  - 全部套件（v25–v52）：仅版本标记断言由 v5.2 提升为 v6.0，其余断言未动；
  - smoke_test_v29/v30：超管重定向 guard 断言字符串更新（v6.0 起 guard
    另含 myposts：超管无对应人员、岗位显示回落排班表）；「排班」组与
    成员导航两项检查改名注明 v6.0 构成（排班组新增 daily、成员侧栏
    追加岗位显示/人员管理员加生成当日排班），断言本体（home/process/
    pick 不在 NAV、排班表字面量渲染）未动；
  - smoke_test_v50/v52：小屏弹层段行高断言由 44px 改为 40px（v5.3
    随 v6.0 收紧），v52 旧值残留断言追加 44px；v50/v52 发布史描述
    保留原文。
- v5.3 说明：本版附带交付（仅 style.css）——用户反馈最新版手机勾选
  弹层仍太大、不好点：小屏段行高 44→40px，并新增横屏矮屏
  (@media (max-height: 500px)) 段（5 列/38px/min(400px, 94vw) 等，
  整层约 250px）；桌面规则与定位逻辑未动，断言在本套件 H 组。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.0 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：临时数据库 + 临时服务端口 3010（API 行为）+ 纯静态检查（前端）\n")
            f.write("- v6.0：新增当日排班子系统——按日期+班次给在岗干部排 A–E 字母岗"
                    "（早/晚班固定模板）+ 带班 + 晚班退税岗；默认排班按全员历史累计"
                    "均衡（早班优先级 A→E→B→C→D、晚班 A→E 依次）；管理员页"
                    "「生成当日排班」（含按图4/图3 生成图片）+ 成员页「岗位显示」"
                    "（单起左侧目录）；附带 v5.3 弹层小屏再收紧。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.0: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
