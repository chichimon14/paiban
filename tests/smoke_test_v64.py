# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.4 冒烟测试（追加到 SMOKE_TEST.md 的 v6.4 章节）。

v6.4 变更（用户 2026-11-01 两图反馈四项 + 追加一项，共五项）：
  1)【符号】轮休显示字符由「✓」(U+2713) 改为「√」(U+221A)：v6.3 只换
     字体未达预期（Mac 上 ✓ 仍带花体尾），用户参照其 Excel 原表的朴素
     细勾。后端 SYMBOLS 一处修改，网格/弹层/图例/PNG/Excel 导出全部
     跟随；v6.3 的符号字体栈规则保留不动。
  2)【网格列色】干部在岗 ≥6 的日子整列天蓝 #D9ECFF（表头/人员格/
     统计行整列，人手宽裕一目了然）；已排满的日子不再给空格压灰底
     （.full 规则整条删除、gridHTML 不再挂 full 类，点选预检与后端
     校验不变）；周六日列底色由淡玫红改淡蓝灰 #F2F7FC，整体清爽；
     同一天既是周末又宽裕时天蓝优先（colClsOf 先判 surplus）。
  3)【岗位显示】「您的岗位」字母重复呈现（渐变徽章 B +「B 岗」文字）
     改为只呈现一次：大号加粗强调色字母 +「岗」（.post-big）。
  4)【岗位显示】新增「生成图片」：本人当天确有岗位（status ok/tax）
     时显示按钮，离屏 DOM + html2canvas 生成 PNG（标题 月日+班次、
     带班、您的岗位、时段表/同岗说明，与页面所见一致）；其余状态
     （休假/未生成/未排岗）不显示按钮。
  5)【岗位显示·选人】选人框仅管理员/超管可见：可查看任一人的岗位
     并导出其图片（导出渲染当前查看的人、标题带姓名）。后端
     GET /api/daily/mine 增加可选 person_id：传他人 id 须 admin/super
     角色，成员传他人 id 返回 403；响应带 view_person/is_self，前端
     文案随之切换「您的岗位/某人的岗位」。超管侧栏新增岗位显示入口，
     超管无对应人员时后端默认名单第一人、选人框默认第一人；管理员
     选人框默认本人。

测试口径（临时库 + 临时端口 3014）：
  A) 符号 API（v6.5 适配：X 显示改回「✓」、全表无「√」）；
  B) 列色数据口径：超管建 2026-11 计划并写最终表——1 日（周日）4 名
     干部休 → 干部在岗 5（周末、非宽裕）；2 日（周一）4 名干部休 →
     在岗 5（平日、非宽裕）；3 日（周二）无人休 → 在岗 9（宽裕）；
     7 日（周六）3 名干部休 → 在岗 6（周末+宽裕，天蓝优先的数据侧）；
     发布后由计划详情 final_day_stats 断言上述在岗数与宽裕日集合；
  C) Excel 导出（v6.5 适配：单元格与图例均为「✓」、「轮休✓」，全文无「√」）；
  D) 岗位图片数据链：保存 11-03（晚班）默认当日排班后，字母岗成员
     mine 返回 status=ok + letter + 非空 timeline + leader_name，
     协管员JJJ mine 返回 status=tax（图片按钮的两类可见状态均有
     数据支撑）；未持岗干部 mine 状态非 ok/tax（按钮不显示口径）；
  E) 选人权限：成员传他人 person_id → 403、传本人 id → 200 且
     is_self、 不传 → 本人数据不变；管理员（CCC）传他人 id → 对方
     的 ok 状态与 letter、is_self=False，不传 → 本人视图；超管不传
     person_id → 名单第一人视图（非错误），传JJJ id → tax 状态；
  S) 静态断言：app.js 版本标记、后端 X 定义（v6.5 适配为「✓」）、
     app.js 无「✓」硬编码、gridHTML 列色逻辑（v6.5 适配：周末
     weekend / 干部行 cadre-blue / 不再挂 full 类）、岗位行字母只
     出现一次且无 letter-badge、mpImgBtn（v6.5 适配：移入岗位行
     .post-line）+ myPostsImage、选人框（mpPerson / canPickPerson /
     NAV 超管含 myposts / 路由不再重定向超管 myposts /
     loadMyPosts 传 person_id / 后端 403 文案与 view_person
     字段）、CSS 列色（v6.5 适配：#FFF1F2 / cadre-blue / .post-big /
     无 .full 灰底规则 / 无旧玫红与淡蓝灰 / 选人 select 同高规则）。
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 3014
BASE = f"http://127.0.0.1:{PORT}"
REPORT = os.path.join(ROOT, "SMOKE_TEST.md")

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), "-", name, ("| " + str(detail) if detail else ""))


def req(method, path, token=(None), body=None, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            payload = resp.read()
            return resp.status, (payload if raw else json.loads(payload or b"{}"))
    except urllib.error.HTTPError as e:
        payload = e.read()
        if raw:
            return e.code, payload
        try:
            return e.code, json.loads(payload or b"{}")
        except Exception:
            return e.code, {}


def login(name, pw):
    st, out = req("POST", "/api/login", body={"username": name, "password": pw})
    return out.get("token") if st == 200 else None


def start_server(dbpath):
    env = dict(os.environ, DUTY_DB=dbpath)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--port", str(PORT)],
        cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(60):
        try:
            st, _ = req("GET", "/api/health")
            if st == 200:
                return proc, True
        except Exception:
            pass
        time.sleep(0.5)
    return proc, False


def stop_server(proc):
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()
    except Exception:
        pass


def segment(text, start_marker, end_marker):
    a = text.index(start_marker)
    b = text.index(end_marker, a)
    return text[a:b]


def main():
    tmpdb = os.path.join(tempfile.mkdtemp(prefix="duty-roster-v64-"), "test.db")
    proc, up = start_server(tmpdb)
    try:
        check("v6.4 服务启动", up)
        if not up:
            return 1

        # ---- A) 符号 API ----
        st, syms = req("GET", "/api/symbols")
        by_code = {s["code"]: s for s in syms} if st == 200 else {}
        check("A 轮休 X 显示字符为「✓」(U+2713)（v6.5 适配：用户指定用回 ✓）、名称仍「轮休」、计休不变",
              by_code.get("X", {}).get("display") == "✓"
              and by_code.get("X", {}).get("name") == "轮休"
              and by_code.get("X", {}).get("counts_leave") is True,
              f"X={by_code.get('X')}")
        check("A 符号表全量无「√」显示字符（v6.5 适配）",
              st == 200 and all(s.get("display") != "√" for s in syms))

        atok = login("admin", "admin123")            # super
        st, people = req("GET", "/api/people", token=atok)
        pid_of = {p["name"]: p["id"] for p in people}

        st, plan = req("POST", "/api/plans", token=atok,
                       body={"year": 2026, "month": 11, "quota": 9, "self_limit": 6})
        plan_id = plan["id"] if st in (200, 201) else None
        check("建 2026 年 11 月计划成功", plan_id is not None, f"status={st}")

        # ---- B) 列色数据口径（最终表 + 发布） ----
        def fcell(name, day, sym):
            return req("PUT", f"/api/plans/{plan_id}/final/cell", token=atok,
                       body={"person_id": pid_of[name], "day": day, "symbol": sym})

        ok = True
        for n in ("DDD", "EEE", "FFF", "GGG"):
            ok = ok and fcell(n, 1, "X")[0] == 200   # 1 日（周日）：干部休 4 → 在岗 5
            ok = ok and fcell(n, 2, "X")[0] == 200   # 2 日（周一）：干部休 4 → 在岗 5
        for n in ("DDD", "EEE", "FFF"):
            ok = ok and fcell(n, 7, "X")[0] == 200   # 7 日（周六）：干部休 3 → 在岗 6
        check("B 超管逐格写最终表（1/2/7 日轮休）", ok)
        req("POST", f"/api/plans/{plan_id}/final/save", token=atok)
        req("POST", f"/api/plans/{plan_id}/publish", token=atok)
        st, det = req("GET", f"/api/plans/{plan_id}", token=atok)
        stats = {s["day"]: s for s in det["final_day_stats"]} if st == 200 else {}
        check("B 计划已发布、final_day_stats 可用",
              st == 200 and det["plan"]["published"] is True and len(stats) == 30)
        check("B 干部在岗：1 日=5（周末非宽裕）、2 日=5（平日非宽裕）、3 日=9（宽裕）、7 日=6（周末+宽裕）",
              stats.get(1, {}).get("cadre_on_duty") == 5
              and stats.get(2, {}).get("cadre_on_duty") == 5
              and stats.get(3, {}).get("cadre_on_duty") == 9
              and stats.get(7, {}).get("cadre_on_duty") == 6,
              f"d1={stats.get(1)}, d7={stats.get(7)}")
        surplus = {d for d, s in stats.items() if s["cadre_on_duty"] >= 6}
        weekends = {d for d in range(1, 31) if date(2026, 11, d).weekday() >= 5}
        check("B 宽裕日集合口径自洽：7 日（周六）在宽裕集、1 日（周日）不在、3 日（周二）在",
              7 in surplus and 1 not in surplus and 3 in surplus
              and 1 in weekends and 7 in weekends and 2 not in weekends and 3 not in weekends,
              f"surplus={sorted(surplus)}")

        # ---- C) Excel 导出 ----
        st, blob = req("GET", f"/api/plans/{plan_id}/export.xlsx", token=atok, raw=True)
        xml_text = ""
        if st == 200:
            zf = zipfile.ZipFile(io.BytesIO(blob))
            xml_text = "\n".join(
                zf.read(n).decode("utf-8", "replace")
                for n in zf.namelist() if n.endswith(".xml"))
        check("C Excel 导出含「✓」与图例「轮休✓」、全文无「√」（v6.5 适配）",
              st == 200 and "✓" in xml_text and "轮休✓" in xml_text
              and "√" not in xml_text,
              f"status={st}, xml_len={len(xml_text)}")

        # ---- D) 岗位图片数据链（11-03 晚班默认排班） ----
        st, ctx = req("GET", "/api/daily/context?date=2026-11-03", token=atok)
        dft = ctx.get("default") if st == 200 else None
        check("D 11-03（晚班）context 有默认排班（v6.20 适配：在岗 9 人走晚班 6 人方案、默认含 A–F 六岗）",
              st == 200 and ctx.get("shift") == "evening" and dft is not None
              and dft.get("leader_id") and len([v for v in dft["letters"].values() if v]) == 6,
              f"shift={ctx.get('shift') if st == 200 else st}")
        st, saved = req("POST", "/api/daily/assignments", token=atok,
                        body={"date": "2026-11-03", "leader_id": dft["leader_id"],
                              "letters": dft["letters"]})
        check("D 保存 11-03 默认当日排班成功", st == 200, f"status={st}")
        names = ctx.get("names") or {}
        holder_letter = next(L for L, v in dft["letters"].items() if v)
        holder_name = names[str(dft["letters"][holder_letter])]
        htok = login(holder_name, "123456")
        st, mine = req("GET", "/api/daily/mine?date=2026-11-03", token=htok)
        res = mine.get("result") or {}
        check("D 字母岗成员 mine：status=ok、letter 与所保存一致、timeline 非空、带班名齐备（图片数据齐备）",
              st == 200 and res.get("status") == "ok"
              and res.get("letter") == holder_letter
              and len(res.get("timeline") or []) > 0
              and bool(res.get("leader_name")),
              f"holder={holder_name} letter={holder_letter} res_status={res.get('status')}")
        gtok = login("JJJ", "123456")
        st, mine_g = req("GET", "/api/daily/mine?date=2026-11-03", token=gtok)
        res_g = mine_g.get("result") or {}
        check("D 协管员JJJ mine：status=tax 且 tax_names 含本人（退税岗图片数据齐备）",
              st == 200 and res_g.get("status") == "tax"
              and "JJJ" in (res_g.get("tax_names") or []),
              f"res={res_g.get('status')}")
        letter_ids = {v for v in dft["letters"].values() if v}
        bench = [p["name"] for p in ctx["on_duty_cadre"] if p["id"] not in letter_ids]
        btok = login(bench[0], "123456")
        st, mine_b = req("GET", "/api/daily/mine?date=2026-11-03", token=btok)
        res_b = mine_b.get("result") or {}
        check("D 未持岗干部 mine：状态非 ok/tax（图片按钮不显示口径）",
              st == 200 and res_b.get("status") not in ("ok", "tax"),
              f"bench={bench[0]} status={res_b.get('status')}")

        # ---- E) 选人权限（成员 403 / 管理员看他人 / 超管默认第一人） ----
        st, users = req("GET", "/api/users", token=atok)
        lw_user = [u for u in users if u["username"] == "CCC"][0]
        req("PATCH", f"/api/users/{lw_user['id']}", token=atok, body={"is_admin": True})
        ltok = login("CCC", "123456")
        st, me_lw = req("GET", "/api/me", token=ltok)
        check("E 前置：CCC role=admin", st == 200 and me_lw.get("role") == "admin",
              str(me_lw.get("role")))
        mtok = login("HHH", "123456")
        st, out403 = req("GET", f"/api/daily/mine?date=2026-11-03&person_id={pid_of['AAA']}",
                         token=mtok)
        check("E 成员传他人 person_id → 403",
              st == 403, f"status={st} out={out403}")
        st, mine_self = req("GET", f"/api/daily/mine?date=2026-11-03&person_id={pid_of['HHH']}",
                            token=mtok)
        check("E 成员传本人 person_id → 200 且 is_self=True、viewer 为本人",
              st == 200 and mine_self.get("is_self") is True
              and (mine_self.get("view_person") or {}).get("id") == pid_of["HHH"],
              f"status={st}")
        st, mine_own = req("GET", "/api/daily/mine?date=2026-11-03", token=mtok)
        check("E 成员不传参 → 本人数据（口径不变）",
              st == 200 and (mine_own.get("viewer") or {}).get("id") == pid_of["HHH"]
              and mine_own.get("is_self") is True)
        holder_id = dft["letters"][holder_letter]
        st, mine_admin = req("GET", f"/api/daily/mine?date=2026-11-03&person_id={holder_id}",
                             token=ltok)
        res_a = mine_admin.get("result") or {}
        check("E 管理员看他人：viewer=对方、is_self=False、状态与 letter 随对方",
              st == 200 and (mine_admin.get("view_person") or {}).get("id") == holder_id
              and mine_admin.get("is_self") is False
              and res_a.get("status") == "ok" and res_a.get("letter") == holder_letter,
              f"holder={holder_name} status={st}")
        st, mine_aown = req("GET", "/api/daily/mine?date=2026-11-03", token=ltok)
        check("E 管理员不传参 → 本人视图（is_self=True）",
              st == 200 and (mine_aown.get("viewer") or {}).get("id") == pid_of["CCC"]
              and mine_aown.get("is_self") is True)
        first_active = [p for p in people if p.get("active")][0]
        st, mine_super = req("GET", "/api/daily/mine?date=2026-11-03", token=atok)
        check("E 超管不传 person_id → 默认名单第一人视图（200、非错误）",
              st == 200 and (mine_super.get("view_person") or {}).get("id") == first_active["id"]
              and mine_super.get("is_self") is False,
              f"first={first_active['name']} status={st}")
        st, mine_sg = req("GET", f"/api/daily/mine?date=2026-11-03&person_id={pid_of['JJJ']}",
                          token=atok)
        res_sg = mine_sg.get("result") or {}
        check("E 超管传JJJ id → tax 状态（选人查看协管员）",
              st == 200 and res_sg.get("status") == "tax"
              and mine_sg.get("is_self") is False,
              f"status={st} res={res_sg.get('status')}")
    finally:
        stop_server(proc)

    # ---- S) 静态断言 ----
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()
    css = open(os.path.join(fe, "style.css"), encoding="utf-8").read()
    backend = open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read()
    css64 = css.split("/* ================= v6.4")[1] if "/* ================= v6.4" in css else ""
    grid_seg = segment(js, "function gridHTML", "function bindGridCells")
    post_seg = segment(js, "function myShiftCardHTML", "function myPostsHTML")
    img_seg = segment(js, "function myPostsImage", "---------------- 路由")

    check("S app.js 带 v6.4 版本标记", "/* duty-roster v6.31 */" in js)
    check("S 后端轮休 X 定义为「✓」（v6.5 适配）", '"X": ("轮休", "✓", True)' in backend)
    check("S app.js 无硬编码「✓」（轮休显示一律走后端 display）", "✓" not in js)
    check("S gridHTML 列色逻辑（v6.5 适配：colClsOf 只判周末 weekend、天蓝只落干部行 cadre-blue 格）",
          "colClsOf" in grid_seg and "'weekend'" in grid_seg
          and 'class="${cc}"' in grid_seg
          and "'cadre-blue'" in grid_seg and "key === 'cadre_on_duty'" in grid_seg
          and "surplus" not in grid_seg)
    check("S gridHTML 不再挂 full 类（满员灰底已取消，校验逻辑不在本函数内）",
          "push('full')" not in grid_seg and "stats[d].full" not in grid_seg)
    check("S 岗位行字母只呈现一次（post_seg 中 e.letter 仅 1 处）且全文无 letter-badge",
          post_seg.count("e.letter") == 1 and "letter-badge" not in js
          and '${words.poss}岗位：<span class="post-big">' in post_seg)
    check("S 岗位图片接线（v6.5 适配：按钮移入岗位行 .post-line；myPostsImage 状态兜底不变）",
          "mpImgBtn" in js and "function myPostsImage" in js
          and "post-line" in post_seg and "mpImgBtn" in post_seg
          and "e.status !== 'ok' && e.status !== 'tax'" in js
          and "我的岗位" in js)
    check("S 选人接线：mpPerson + canPickPerson + 超管 NAV 含 myposts + 路由不再重定向超管 myposts + loadMyPosts 传 person_id（v6.8 适配：经 pid 守卫变量附加）",
          "mpPerson" in js and "canPickPerson" in js
          and "{ route: 'myposts'" in js
          and "(route === 'pick' || route === 'home' || route === 'process')" in js
          and "&person_id=${pid}" in js)
    check("S 选人后端：daily_mine 含 person_id 参数、403 文案与 view_person/is_self 字段（v6.13 适配：403 文案改为「您没有查看他人岗位的权限」，判定改走 user_can_view_others）",
          "def daily_mine" in backend and "person_id: int = None" in backend
          and "您没有查看他人岗位的权限" in backend
          and "user_can_view_others" in backend
          and '"view_person"' in backend and '"is_self"' in backend)
    check("S 岗位图片归属：导出标题带被查看人姓名（v6.23 适配：卡片构建抽至 myPostsImageCardHTML；v6.24 适配：标题行右侧只留岗位本身、原「${poss}岗位：」前缀已按用户要求去掉）",
          "esc(vname)" in img_seg and "${poss}岗位" not in img_seg)
    check("S CSS 列色（v6.5 适配：周末浅粉 #FFF1F2、天蓝只落 tr.stats td.cadre-blue、整列天蓝规则已撤下；选人 select 同高）",
          "#FFF1F2" in css64 and "tr.stats td.cadre-blue { background: #D9ECFF; }" in css64
          and "th.surplus" not in css and "td.cell.surplus" not in css
          and "#F2F7FC" not in css and "td.cell.weekend" in css64
          and ".daily-controls > label select" in css64)
    check("S CSS：.full 灰底规则已删除、无旧玫红周末底色残留",
          "table.grid td.cell.full" not in css and "background: #DCDCDC" not in css
          and "rgba(244,63,94,.05)" not in css)
    check("S CSS v6.4：.post-big 岗位字母样式（大号加粗强调色）",
          ".post-big" in css64 and "font-weight: 800" in css64)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v6.4 引起的旧套件改动）：
  - 【v6.5 追记】本套件中与 v6.5 冲突的断言已按 v6.5 口径改写：
    符号 A/C/S 改回「✓」；列色 S 改查周末 weekend + 干部行
    cadre-blue（整列天蓝断言撤下）；CSS S 改查 #FFF1F2 与
    tr.stats td.cadre-blue、断言整列天蓝规则与 #F2F7FC 不存在；
    岗位图片接线 S 改查按钮移入 .post-line。B/D/E 数据口径未动。
  - 全部套件（v25–v63）：仅版本标记断言由 v6.3 提升为 v6.4，其余未动；
  - smoke_test_v27.py 中带 symbols 表旧库的种子行仍写作 '✓'——那是
    模拟历史旧库的夹具数据（旧库当年落库的显示字符）、非现行断言，
    迁移断言只查符号名，按原样保留；
  - v6.3 的符号字体栈规则（PingFang/YaHei）保留不动：v6.4 改的是显示
    字符本身（✓→√），两者叠加后 Mac/Windows 均为朴素细勾；
  - smoke_test_v60.py / smoke_test_v61.py：超管岗位显示口径适配 v6.4——\n    超管 mine 由 has_person=false 空态改为默认第一人视图、NAV 新增 myposts、\n    路由 guard 不再回落，三处断言按新口径改写（成员/管理员口径未动）；\n  - smoke_test_v48.py / smoke_test_v49.py：满员灰底相关断言适配 v6.4——\n    改为断言 .full 规则/挂类不存在、点选预检口径不变，周末底色改查 #F2F7FC；\n  - smoke_test_v41.py：网格亮色断言适配 v6.4——周末底色改查 #F2F7FC、\n    「满员灰底 #DCDCDC」子断言改为断言 .full 规则不存在；\n  - smoke_test_v29.py / smoke_test_v30.py：超管路由 guard 断言适配 v6.4——\n    guard 不再含 myposts（超管新增岗位显示选人页），断言改查新 guard 行；\n  - 后端口径除 X 显示字符与 mine 选人扩展外无变化：符号 code/名称/
    计休属性不变，历史数据无需迁移（selections 存的是 code）；
  - mine 接口向后兼容：不带 person_id 时成员/管理员行为与 v6.1–v6.3
    完全一致（超管由原 has_person=False 空态改为默认第一人视图，
    与选人框默认口径一致）。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.4 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：临时数据库 + 临时服务端口 3014（API 行为）+ 纯静态检查（前端）\n")
            f.write("- v6.4：轮休显示字符 ✓→√（后端 SYMBOLS 一处）；网格整列着色"
                    "（干部在岗 ≥6 天蓝 #D9ECFF、周末淡蓝灰 #F2F7FC、宽裕优先；"
                    "满员灰底 .full 删除）；岗位显示字母去重（.post-big 单呈现）；"
                    "岗位显示新增本人当日排班「生成图片」（ok/tax 状态才显示）；"
                    "岗位显示选人查看（仅管理员/超管，mine 加 person_id + 403 "
                    "兜底，超管侧栏新增岗位显示）。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.4: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
