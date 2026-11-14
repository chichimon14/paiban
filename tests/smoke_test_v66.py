# -*- coding: utf-8 -*-
"""示例科室排班系统 v6.6 冒烟测试（追加到 SMOKE_TEST.md 的 v6.6 章节）。

v6.6 变更（生成当日排班页改选口径，2026-11-01 用户截图反馈）：
  A–E 字母岗下拉原先把「已在其他岗的人」渲染为 disabled——五个
  岗排满后管理员点开任何下拉，想选的人全是灰的，根本改不动。
  改为「抢占」口径：
  - 字母岗选项列出全部在岗干部、不再禁用任何人（渲染层删掉
    usedBy 占用表与 option 上的 disabled）；
  - 改选已在其他岗的人时，stealLetterPost() 自动清空其原岗
    （回未定）并 toast 点名「X 已从 Y 岗移除，改排到 Z 岗」；
    选「未定」仍只是清空本岗；
  - 带班（值班科长）口径不变：可与字母岗重合，steal 只动
    letters、绝不碰 leader_id，带班改选也不触发 steal；
  - 改选后照常 renderDailyBody 全量重渲染（时段预览/历史累计/
    未保存脏标记随之刷新）；保存校验不变（五岗须排满且互不
    重复，缺岗走原「岗位未排满」提示，后端亦有同口径校验）。
  原 onDailyLetterChange 里的清岗逻辑本就存在、却因 disabled
  永远点不到——本版把两条路径收成一条（删禁用、留抢占），
  旧提示文案「原 X 岗已清空，请重新选择」随之退役。

  追加项（同版一并交付）【排班表 PNG 导出标题收口】：exportImage
  原先直接快照 #sheetWrap .card，页面标题行左区的状态文字
  （已提交/已发布…）与右区按钮（保存修改/撤销/导出 Excel/生成
  图片）全被拍进图里。改为克隆卡片后把 .sheet-title-row 换成
  纯标题——只有居中的「示例科室排班表（M月）」（如
  「示例科室排班表（11月）」），不再用页面 sheetTitle 的
  「X月可休Q天，您可勾选N天轮休」后缀，谁导出都一样；再把克隆
  节点放进离屏 holder 快照（与当日排班图片同套机制），页面
  本身不动。网格、统计行、底部符号图例照旧。

测试口径（临时库 + 临时端口 3016）：
  A) 数据链冒烟：超管建 11 月计划后，context 2026-11-02 按日
     推导早班、在岗干部 9 人、默认五岗互不重复（页面数据源
     与渲染前提未被本版动过）；
  S) 静态断言：版本标记；letterSel 段无 disabled 且全 js 无
     usedBy 残留；stealLetterPost 存在、只动 letters（段内无
     leader_id）、被 onDailyLetterChange 调用且 change 绑定
     未变；toast 新文案点名（ctx.names + 已从…岗移除/改排到）；
     旧文案退役；带班选项与带班 change 处理未被 steal 波及；
     saveDaily 校验文案（请选择带班/岗位未排满）未动；
     导出图标题（exportImage 段只组「示例科室排班表（${month}月）」、
     克隆节点换标题行后离屏快照、段内无 sheetTitle(/可休/您可
     勾选，且页面 sheetTitle 本身仍带完整后缀未被改动）。
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
PORT = 3016
BASE = f"http://127.0.0.1:{PORT}"
REPORT = os.path.join(ROOT, "SMOKE_TEST.md")

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), "-", name, ("| " + str(detail) if detail else ""))


def req(method, path, token=None, body=None, raw=False):
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
    tmpdb = os.path.join(tempfile.mkdtemp(prefix="duty-roster-v66-"), "test.db")
    proc, up = start_server(tmpdb)
    try:
        check("v6.6 服务启动", up)
        if not up:
            return 1

        # ---- A) 数据链冒烟（页面数据源未动） ----
        atok = login("admin", "admin123")
        st, plan = req("POST", "/api/plans", token=atok,
                       body={"year": 2026, "month": 11, "quota": 9, "self_limit": 6})
        check("A 建 2026 年 11 月计划成功", st in (200, 201), f"status={st}")
        st, ctx = req("GET", "/api/daily/context?date=2026-11-02", token=atok)
        dft = (ctx.get("default") or {}).get("letters") or {}
        check("A 11-02 context：按日推导早班、在岗干部 9 人、默认六岗互不重复（v6.16 适配：在岗 ≥6 人走 6 人方案 A–F；下拉数据源齐备）",
              st == 200 and ctx.get("shift") == "morning"
              and len(ctx.get("on_duty_cadre") or []) == 9
              and len(dft) == 6 and len(set(dft.values())) == 6,
              f"status={st} shift={ctx.get('shift')} cadre={len(ctx.get('on_duty_cadre') or [])} default={dft}")
        st, ctx3 = req("GET", "/api/daily/context?date=2026-11-03", token=atok)
        check("A 11-03 context：按日推导晚班（班次口径未动）",
              st == 200 and ctx3.get("shift") == "evening", f"status={st}")
    finally:
        stop_server(proc)

    # ---- S) 静态断言 ----
    fe = os.path.join(ROOT, "frontend")
    js = open(os.path.join(fe, "app.js"), encoding="utf-8").read()
    render_seg = segment(js, "function renderDailyBody()", "function stealLetterPost")
    steal_seg = segment(js, "function stealLetterPost", "function onDailyLetterChange")
    change_seg = segment(js, "function onDailyLetterChange", "async function saveDaily")
    save_seg = segment(js, "async function saveDaily", "async function dailyImage")
    letter_sel_seg = segment(render_seg, "const letterSel", "</select></label>`;")

    check("S app.js 带 v6.6 版本标记", "/* duty-roster v6.31 */" in js)
    check("S 字母岗选项不再禁用任何人：letterSel 段无 disabled、渲染不再算占用表（全 js 无 usedBy）",
          "disabled" not in letter_sel_seg and "usedBy" not in js)
    check("S 字母岗选项仍列全部在岗干部（on_duty_cadre.map 生成 option、含未定项）",
          "ctx.on_duty_cadre.map((p)" in letter_sel_seg and "— 未定 —" in letter_sel_seg)
    check("S steal 例程存在且只清字母岗：stealLetterPost 把占用者原岗置 null、段内不碰 leader_id",
          "f.letters[o] = null" in steal_seg and "leader_id" not in steal_seg
          and "return cleared" in steal_seg)
    check("S steal 已接线：onDailyLetterChange 调用 stealLetterPost，且字母 select 的 change 绑定未变",
          "stealLetterPost(letter, pid)" in change_seg
          and "addEventListener('change', () => onDailyLetterChange(L, sel.value))" in render_seg)
    check("S steal 提示点名：toast 用 ctx.names 取姓名、文案含「已从 … 岗移除，改排到 … 岗」",
          "dailyState.ctx.names" in change_seg
          and "已从 ${cleared} 岗移除，改排到 ${letter} 岗" in change_seg)
    check("S 旧清岗文案已退役（两条路径收成一条）：「原 … 岗已清空，请重新选择」不复存在",
          "岗已清空" not in js and "请重新选择" not in js)
    check("S 带班未被波及：带班选项无 disabled 逻辑、带班 change 只写 leader_id 后重渲染",
          "dailyState.form.leader_id = leaderSel.value ? Number(leaderSel.value) : null; renderDailyBody();" in render_seg
          and "stealLetterPost" not in segment(render_seg, "const leaderOpts", "const savedNote"))
    check("S 保存校验未动：saveDaily 仍拦未选带班与未排满（岗位未排满文案在）",
          "请选择带班（值班科长）" in save_seg and "岗位未排满" in save_seg)
    check("S 选「未定」只清本岗：onDailyLetterChange 对空值不触发 steal（pid 为空直接落位）",
          "const pid = val ? Number(val) : null;" in change_seg
          and "if (pid) {" in change_seg and "f.letters[letter] = pid;" in change_seg)

    # ---- S2) 排班表 PNG 导出标题收口 ----
    exp_seg = segment(js, "async function exportImage()", "function bindSheet()")
    title_fn_seg = segment(js, "function sheetTitle(plan, myLimit)", "const EXPORT_BTNS")
    check("S 导出图标题只组纯标题：含「示例科室排班表（${detail.plan.month}月）」、段内无可休/您可勾选后缀、不用页面 sheetTitle",
          "示例科室排班表（${detail.plan.month}月）" in exp_seg
          and "可休" not in exp_seg and "您可勾选" not in exp_seg
          and "sheetTitle(" not in exp_seg)
    check("S 导出快照的是收口后的克隆节点：cloneNode 克隆卡片、标题行 innerHTML 被整体换掉（左区状态/右区按钮不在图内）、快照对象为 node",
          "src.cloneNode(true)" in exp_seg
          and "node.querySelector('.sheet-title-row')" in exp_seg
          and "titleRow.innerHTML" in exp_seg
          and "html2canvas(node," in exp_seg
          and "st-left" not in exp_seg and "st-right" not in exp_seg)
    check("S 页面标题未动：sheetTitle 仍组「X月可休Q天，您可勾选N天轮休」完整标题（只收口导出图）",
          "月可休" in title_fn_seg and "您可勾选" in title_fn_seg
          and "轮休" in title_fn_seg)

    return 0 if all(r[1] for r in results) else 1


ADAPT_NOTES = """- 适配说明（v6.6 引起的旧套件改动）：
  - 全部套件（v25–v65）：仅版本标记断言由 v6.5 提升为 v6.6，其余未动；
  - 经逐套件核查，没有任何旧套件断言过字母岗选项的 disabled
    渲染（v60 文件头注记「改选冲突时清空原岗并 toast」描述的是
    handlers 里的清岗逻辑本身——该逻辑在本版以 stealLetterPost
    之名保留并真正可达，注记口径仍成立、未改）；
  - 后端零改动：context/assignments/mine 接口、保存校验（五岗
    互不重复等）全部未动，本版纯前端 app.js 两处收口（改选
    交互 + 导出图标题）；追加的导出标题项无旧套件断言过老的
    exportImage 实现（逐套件核查过），无需适配。
"""


if __name__ == "__main__":
    try:
        code = main()
    finally:
        passed = sum(1 for r in results if r[1])
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n## v6.6 冒烟测试（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n\n")
            f.write("- 环境：临时数据库 + 临时服务端口 3016（API 数据链）+ 纯静态检查（前端）\n")
            f.write("- v6.6：生成当日排班页字母岗改选改「抢占」口径——下拉不再 "
                    "disabled 任何在岗干部，改选已在其他岗的人自动清空其原岗"
                    "并 toast 点名；带班与保存校验不变。追加项：排班表 PNG "
                    "导出标题收口——克隆卡片换纯标题行后离屏快照，导出图只剩"
                    "居中「示例科室排班表（M月）」，页面标题行不动。\n")
            f.write(ADAPT_NOTES)
            f.write(f"- 结果：**{passed}/{len(results)} 项通过**\n\n")
            f.write("| # | 检查项 | 结果 | 备注 |\n|---|---|---|---|\n")
            for i, (name, ok, det) in enumerate(results, 1):
                f.write(f"| {i} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {det} |\n")
        print(f"\nv6.6: {passed}/{len(results)} passed -> appended to {REPORT}")
    sys.exit(code if 'code' in dir() else 1)
