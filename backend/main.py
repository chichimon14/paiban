# -*- coding: utf-8 -*-
"""
示例科室排班系统 v2 —— 后端（FastAPI + SQLite，单文件）

v2 变化：
- 科长分组显式记为 'chief'，界面显示“科长”，任何地方不再出现 null 组别。
- 数据分层：成员草稿（selections）→ 提交快照（submissions，源数据，保留一年、
  永不覆盖，退回重提生成新版本）→ 管理员最终表（final_selections）：
  管理员“调取数据”用最新提交快照重建最终表，随后可一键补满（不限是否有人已选、
  从最终表当前计数补到 Q）、手工改格、保存、提交发布（锁定）。
- 一键补满也可随时在最终表上执行（含科长在内所有人补到 Q）。
- 账号：修改密码（验旧密码）、管理员可启停账号/设管理员/重置密码；人员可增改
  （姓名、类别、分组、启用状态）。
- 历史数据：近 12 个月计划与提交记录可查询。

核心规则：
- 每月一个排班计划：应休天数 Q（管理员设置）、自选上限 S（默认 6）。
  科长可自选至 Q，其余干部与协管员自选至 S；一键补满后所有人补齐到 Q。
- 选休窗口（排班月上个月）：24 日科长先选，25 日当月先行组（A/B 按排班月奇偶轮换，
  奇数月 A 先、偶数月 B 先，管理员可覆盖），26 日另一组。管理员可设置阶段覆盖值随时开放。
- v2.2：协管员纳入 A/B 组（JJJ A 组、KKK B 组），随所在组一同开放选休
  （取代旧的“协管员按月轮流优先”）；新增每日硬约束：协管员休假 <= 1（在岗 >= 1）。
- 每日硬约束（干部部分统计 9 名干部）：休假人数 <= 4（在岗 >= 5），
  其中科领导（前 3 人）休假 <= 2（科领导在岗 >= 1）；协管员（2 人）休假 <= 1
  （在岗 >= 1）。满员的日期前端变灰、后端拒绝。
- 假期符号除“备勤 B”外均计为休假（计入配额与每日上限）。空白 = 正常上班。
- 管理员可编辑任意单元格（超限时返回警告但仍保存）、可一键补满、可发布锁定。

v2.4 变化：
- 角色三分：super（仅 admin 账号）/ admin（is_admin=1 的人员账号）/ member。
  管理台（规则、数据处理、人员与权限、历史数据）与全部管理接口仅 super 可用；
  人员管理员与普通成员共用合并排班表页，只能直接改本人行。
- 人员管理员调整他人排班走审批流：POST /api/plans/{id}/adjustments 生成
  adjustments 待审批记录（同格新申请会替代旧的 pending），草稿表不立即变化；
  super 在「日志管理」同意后才写入草稿（source='admin'），若对象已提交，
  同步为其生成一份新的提交版本快照；驳回则不改表。
- 登录日志：login_logs 记录每次登录成功/失败（含提交的用户名、IP、UA），
  super 可通过 GET /api/logs 查看待审批、调整记录与登录日志。

v2.5 变化：
- 前端入口与静态资源统一返回 Cache-Control: no-cache，避免浏览器缓存旧版
  app.js/style.css（曾导致人员管理员看不到 v2.4 的审批调整入口）。
- 新增 GET /api/me：前端进入应用时用服务端最新角色/权限覆盖 localStorage
  里的登录快照（授权变更后无需退出重登即可生效）。
- 说明：草稿改格接口的配额/每日上限一直是「仅 super 警告放行、其余角色
  （含人员管理员改本人行）超限 400 拒绝」，v2.5 冒烟测试已固化该口径；
  线上出现的「可选 12 天」为旧版前端本地未保存状态无校验所致，前端已补本地预检。

v2.6 变化（取代 v2.4 审批流）：
- 人员管理员调整他人排班不再走超管审批：与改本人行完全一致——前端本地
  暂存点选，点「保存」后经 POST /api/plans/{id}/admin-edits 整批提交，
  保存即生效（source='admin'）。整批校验任一违反则整体 400、不落表不记日志。
- adjustments 表改为「管理员修改日志」：仅实际发生变化的格子记一行
  status='applied'（含旧值→新值）；无变化的保存不留痕。旧的创建申请 /
  同意 / 驳回接口已删除（404）；启动时把遗留的 pending 申请一律置为
  'void'（已作废，从未生效过）；历史 approved/rejected/superseded 保留。
- GET /api/logs 改为两部分：{modifications（修改记录）, login_logs}。
- plan_detail 不再返回 pending_adjustments / my_adjustments。
"""
import calendar
import hashlib
import io
import json
import os
import secrets
import sqlite3
from datetime import date

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("DUTY_DB", os.path.join(BASE_DIR, "backend", "duty.db"))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
DEPT_NAME = "示例科室"

# ---------------------------------------------------------------- 符号表
# code -> (名称, 显示字符, 是否计休假)
# v6.4：轮休 X 的显示字符由「✓」(U+2713) 改为「√」(U+221A)——前者在
# macOS 系统字体下渲染成带书法尾巴的花体勾，用户要求与 Excel 原表一致
# 的朴素细勾；改显示字符一处，网格/弹层/图例/PNG/Excel 导出全部跟随。
SYMBOLS = {
    "X": ("轮休", "✓", True),
    "R": ("补休", "R", True),
    "Z": ("排正限制", "Z", True),
    "B": ("备勤", "B", False),
    "O": ("年休假", "O", True),
    "*": ("公差", "*", True),
    "△": ("病假", "△", True),
    "J": ("借调", "J", True),
    "Y": ("支援", "/", True),
    "Φ": ("探亲假（单身）", "Φ", True),
    "☆": ("探亲假（四年）", "☆", True),
    "#": ("夫妻分居", "#", True),
    "●": ("加正", "●", True),
    "D": ("丧假", "D", True),
    "E": ("婚假", "E", True),
    "F": ("法定假", "F", True),
    "N": ("看护假", "N", True),
    "S": ("产假", "S", True),
    "W": ("保健假", "W", True),
}
SYMBOL_ORDER = list(SYMBOLS.keys())

CADRE_DAILY_LEAVE_CAP = 4   # 9 名干部每日最多休 4 人 -> 在岗 >= 5
LEADER_DAILY_LEAVE_CAP = 2  # 3 名科领导每日最多休 2 人 -> 科领导在岗 >= 1
ASSISTANT_DAILY_LEAVE_CAP = 1  # 2 名协管员每日最多休 1 人 -> 协管员在岗 >= 1（v2.2）

# ---------------------------------------------------------------- 种子人员
# (姓名, 类型, 默认组, 工号) 类型: chief 科长 / deputy 副科长 / cadre 科员 / assistant 协管员
# v6.7：干部带工号（可作为登录账号，与姓名等价、密码相同）；协管员无工号（None），仍用姓名登录。
PEOPLE_SEED = [
    ("AAA", "chief", "chief", "111"),
    ("BBB", "deputy", "A", "222"),
    ("CCC", "deputy", "B", "333"),
    ("DDD", "cadre", "A", "444"),
    ("EEE", "cadre", "B", "555"),
    ("FFF", "cadre", "A", "666"),
    ("GGG", "cadre", "A", "777"),
    ("HHH", "cadre", "B", "888"),
    ("III", "cadre", "B", "999"),
    # v2.2：协管员纳入 A/B 组（JJJ A组、KKK B组），随所在组开放选休；类别仍为协管员。
    ("JJJ", "assistant", "A", None),
    ("KKK", "assistant", "B", None),
]
LEADER_KINDS = ("chief", "deputy")


def is_leader(person):
    return person["kind"] in LEADER_KINDS


def is_cadre(person):
    return person["kind"] in ("chief", "deputy", "cadre")


KIND_LABELS = {
    "chief": "科长",
    "deputy": "副科长",
    "cadre": "科员",
    "assistant": "协管员",
}


def group_label(person):
    """组别显示名：科长显示“科长”，A/B 显示“A组/B组”，其余显示“—”。永不出现 null。"""
    if person["kind"] == "chief" or person.get("grp") == "chief":
        return "科长"
    if person.get("grp") in ("A", "B"):
        return person["grp"] + "组"
    return "—"


def person_out(person):
    return {
        **person,
        "is_leader": is_leader(person),
        "is_cadre": is_cadre(person),
        "kind_label": KIND_LABELS.get(person["kind"], person["kind"]),
        "grp_label": group_label(person),
    }


# ---------------------------------------------------------------- 数据库
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def hash_pw(pw: str) -> str:
    return hashlib.sha256(("duty-roster-v1:" + pw).encode("utf-8")).hexdigest()


def init_db():
    conn = db()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            kind TEXT NOT NULL,
            grp TEXT,
            sort_order INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            work_id TEXT,
            can_view_others INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            person_id INTEGER,
            is_admin INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            quota INTEGER NOT NULL,
            self_limit INTEGER NOT NULL,
            first_group TEXT NOT NULL,
            phase_override INTEGER,
            published INTEGER NOT NULL DEFAULT 0,
            final_saved_at TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(year, month)
        );
        CREATE TABLE IF NOT EXISTS selections (
            plan_id INTEGER NOT NULL,
            person_id INTEGER NOT NULL,
            day INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'self',
            PRIMARY KEY (plan_id, person_id, day)
        );
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY,
            plan_id INTEGER NOT NULL,
            person_id INTEGER NOT NULL,
            data_json TEXT NOT NULL,
            submitted_at TEXT DEFAULT (datetime('now','localtime')),
            returned INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS final_selections (
            plan_id INTEGER NOT NULL,
            person_id INTEGER NOT NULL,
            day INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'source',
            PRIMARY KEY (plan_id, person_id, day)
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS adjustments (
            id INTEGER PRIMARY KEY,
            plan_id INTEGER NOT NULL,
            admin_user_id INTEGER NOT NULL,
            admin_name TEXT NOT NULL,
            target_person_id INTEGER NOT NULL,
            day INTEGER NOT NULL,
            symbol TEXT,
            old_symbol TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            decided_by TEXT,
            decided_at TEXT
        );
        CREATE TABLE IF NOT EXISTS login_logs (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            user_id INTEGER,
            success INTEGER NOT NULL DEFAULT 0,
            ip TEXT,
            user_agent TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS daily_assignments (
            id INTEGER PRIMARY KEY,
            plan_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            shift TEXT NOT NULL,
            leader_id INTEGER,
            letters TEXT NOT NULL DEFAULT '{}',
            tax_ids TEXT NOT NULL DEFAULT '[]',
            created_by INTEGER,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(plan_id, date, shift)
        );
        """
    )
    # ---- v1 -> v2 迁移（已存在的旧库补列/修正数据）
    def _cols(table):
        return [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]

    if "active" not in _cols("people"):
        cur.execute("ALTER TABLE people ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
    if "active" not in _cols("users"):
        cur.execute("ALTER TABLE users ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
    if "final_saved_at" not in _cols("plans"):
        cur.execute("ALTER TABLE plans ADD COLUMN final_saved_at TEXT")
    # v6.7 迁移：人员加工号列（可作登录账号）；工号非空时唯一（部分唯一
    # 索引：NULL/空串不参与唯一性，协管员无工号不受影响）。幂等执行。
    if "work_id" not in _cols("people"):
        cur.execute("ALTER TABLE people ADD COLUMN work_id TEXT")
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_people_work_id"
        " ON people(work_id) WHERE work_id IS NOT NULL AND work_id <> ''"
    )
    # v6.13 迁移：人员加「可查看他人岗位」授权列——岗位显示（/api/daily/mine）
    # 选人查看他人的个人授权开关，默认 0=无权；超管在「人员与权限」表逐人
    # 开关（随行保存 PUT）。仅放大岗位显示一处，不影响任何其他权限。幂等执行。
    if "can_view_others" not in _cols("people"):
        cur.execute("ALTER TABLE people ADD COLUMN can_view_others INTEGER NOT NULL DEFAULT 0")
    # 科长组别：旧库中为 NULL，统一为 'chief'（界面显示“科长”）
    cur.execute("UPDATE people SET grp='chief' WHERE kind='chief' AND (grp IS NULL OR grp='')")
    # v2.2 迁移：协管员纳入 A/B 组——仅当组别未设置时填充（JJJ A 组、KKK B 组），
    # 不覆盖管理员后续的人工调整。每次启动幂等执行。
    cur.execute("UPDATE people SET grp='A' WHERE name='JJJ' AND kind='assistant' "
                "AND (grp IS NULL OR grp='')")
    cur.execute("UPDATE people SET grp='B' WHERE name='KKK' AND kind='assistant' "
                "AND (grp IS NULL OR grp='')")
    # v2.6 迁移：审批流已撤销——遗留的 pending 调整申请从未对草稿生效过，
    # 启动时一律作废（status='void'），仅在日志中以「已作废（未生效）」留痕。
    cur.execute("UPDATE adjustments SET status='void' WHERE status='pending'")
    # v2.7 迁移：符号改名——☆「探父母假(四年一次)」→「探亲假（四年）」、
    # Φ「探父母假(单身)」→「探亲假（单身）」。符号名以代码中的 SYMBOLS 为准、
    # 现行库不落库存储；此处仅兜底处理个别带 symbols 表的旧库，每次启动幂等执行。
    if cur.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='symbols'"
    ).fetchone()[0]:
        cur.execute("UPDATE symbols SET name='探亲假（四年）' WHERE code='☆'")
        cur.execute("UPDATE symbols SET name='探亲假（单身）' WHERE code='Φ'")
    if cur.execute("SELECT COUNT(*) FROM people").fetchone()[0] == 0:
        for i, (name, kind, grp, work_id) in enumerate(PEOPLE_SEED, start=1):
            cur.execute(
                "INSERT INTO people (id, name, kind, grp, sort_order, work_id) VALUES (?,?,?,?,?,?)",
                (i, name, kind, grp, i, work_id),
            )
            cur.execute(
                "INSERT INTO users (username, password_hash, display_name, person_id, is_admin)"
                " VALUES (?,?,?,?,?)",
                (name, hash_pw("123456"), name, i, 1 if kind == "chief" else 0),
            )
        cur.execute(
            "INSERT INTO users (username, password_hash, display_name, person_id, is_admin)"
            " VALUES (?,?,?,?,?)",
            ("admin", hash_pw("admin123"), "系统管理员", None, 1),
        )
    conn.commit()
    conn.close()


def get_people(conn, include_inactive=False):
    sql = "SELECT * FROM people"
    if not include_inactive:
        sql += " WHERE active=1"
    sql += " ORDER BY sort_order"
    rows = conn.execute(sql).fetchall()
    people = []
    for r in rows:
        p = dict(r)
        p["active"] = bool(p.get("active", 1))
        p["can_view_others"] = bool(p.get("can_view_others", 0))
        people.append(p)
    return people


def get_person(conn, person_id):
    row = conn.execute("SELECT * FROM people WHERE id=?", (person_id,)).fetchone()
    if not row:
        return None
    p = dict(row)
    p["can_view_others"] = bool(p.get("can_view_others", 0))
    return p


def user_can_view_others(conn, user):
    """v6.13：查看他人岗位的资格——admin/super 角色，或本人被超管在
    「人员与权限」里单独授予 can_view_others（首批授予两名协管员）。
    仅作用于岗位显示（/api/daily/mine 的 person_id 选人查看），不放大
    任何其他权限：当日排班编辑、最终表修改、管理台仍按角色校验。"""
    if user["role"] in ("admin", "super"):
        return True
    pid = user.get("person_id")
    if not pid:
        return False
    row = conn.execute(
        "SELECT can_view_others FROM people WHERE id=?", (pid,)
    ).fetchone()
    return bool(row and row[0])


def get_plan(conn, plan_id):
    row = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
    if not row:
        raise HTTPException(404, "排班计划不存在")
    return dict(row)


# ---------------------------------------------------------------- 阶段/窗口
def window_dates(plan):
    """选休窗口日期（排班月的上一个月 24/25/26 日）。"""
    y, m = plan["year"], plan["month"]
    wy, wm = (y - 1, 12) if m == 1 else (y, m - 1)
    return {
        "chief": date(wy, wm, 24).isoformat(),
        "first": date(wy, wm, 25).isoformat(),
        "second": date(wy, wm, 26).isoformat(),
    }


def date_phase(plan):
    y, m = plan["year"], plan["month"]
    wy, wm = (y - 1, 12) if m == 1 else (y, m - 1)
    today = date.today()
    if today >= date(wy, wm, 26):
        return 3
    if today >= date(wy, wm, 25):
        return 2
    if today >= date(wy, wm, 24):
        return 1
    return 0


def effective_phase(plan):
    if plan.get("phase_override") is not None:
        return plan["phase_override"]
    return date_phase(plan)


def default_first_group(year, month):
    return "A" if month % 2 == 1 else "B"


def first_assistant_id(plan, people):
    """当月先行组内的协管员 id（v2.2 起协管员随所在组开放，不再单独轮换优先）。

    保留该字段仅作兼容（计划载荷/旧测试引用）；找不到时返回第一位协管员。
    """
    assistants = [p for p in people if p["kind"] == "assistant"]
    for p in assistants:
        if p.get("grp") == plan["first_group"]:
            return p["id"]
    return assistants[0]["id"] if assistants else None


def can_pick_now(person, plan, people):
    """该成员当前阶段是否已开放选休。"""
    phase = effective_phase(plan)
    if person["kind"] == "chief":
        return phase >= 1
    # 干部与协管员都按组别开放：先行组 phase>=2，另一组 phase>=3
    return phase >= (2 if person.get("grp") == plan["first_group"] else 3)


# ---------------------------------------------------------------- 统计
def load_selections(conn, plan_id):
    rows = conn.execute(
        "SELECT person_id, day, symbol, source FROM selections WHERE plan_id=?",
        (plan_id,),
    ).fetchall()
    grid = {}
    for r in rows:
        grid.setdefault(r["person_id"], {})[r["day"]] = {
            "symbol": r["symbol"],
            "source": r["source"],
        }
    return grid


def load_final_selections(conn, plan_id):
    rows = conn.execute(
        "SELECT person_id, day, symbol, source FROM final_selections WHERE plan_id=?",
        (plan_id,),
    ).fetchall()
    grid = {}
    for r in rows:
        grid.setdefault(r["person_id"], {})[r["day"]] = {
            "symbol": r["symbol"],
            "source": r["source"],
        }
    return grid


def latest_submissions(conn, plan_id):
    """每人最新一份未被退回的提交快照：{person_id: {submitted_at, data:{day:symbol}}}。"""
    import json as _json

    rows = conn.execute(
        "SELECT * FROM submissions WHERE plan_id=? AND returned=0 ORDER BY id",
        (plan_id,),
    ).fetchall()
    latest = {}
    for r in rows:
        latest[r["person_id"]] = {
            "id": r["id"],
            "submitted_at": r["submitted_at"],
            "data": {int(k): v for k, v in _json.loads(r["data_json"]).items()},
        }
    return latest


def load_source_grid(conn, plan_id):
    """源数据汇总表：由各人最新提交快照拼成（未提交者为空行）。"""
    grid = {}
    for pid, sub in latest_submissions(conn, plan_id).items():
        grid[pid] = {
            d: {"symbol": sym, "source": "submitted"} for d, sym in sub["data"].items()
        }
    return grid


def submission_status(conn, plan_id, people):
    """每人的提交状态：none 未提交 / submitted 已提交（锁定）/ returned 已退回可重提。"""
    rows = conn.execute(
        "SELECT * FROM submissions WHERE plan_id=? ORDER BY id", (plan_id,)
    ).fetchall()
    by_person = {}
    for r in rows:
        by_person.setdefault(r["person_id"], []).append(dict(r))
    out = {}
    for p in people:
        subs = by_person.get(p["id"], [])
        active = [s for s in subs if not s["returned"]]
        if active:
            last = active[-1]
            out[p["id"]] = {
                "status": "submitted",
                "submitted_at": last["submitted_at"],
                "versions": len(subs),
            }
        elif subs:
            out[p["id"]] = {
                "status": "returned",
                "submitted_at": subs[-1]["submitted_at"],
                "versions": len(subs),
            }
        else:
            out[p["id"]] = {"status": "none", "submitted_at": None, "versions": 0}
    return out


def counts_as_leave(symbol):
    return SYMBOLS[symbol][2]


def person_leave_count(grid, person_id):
    return sum(
        1 for c in grid.get(person_id, {}).values() if counts_as_leave(c["symbol"])
    )


def counts_toward_cap(symbol):
    """v4.7：个人自选上限只统计轮休（符号 X）。

    用户定：「逻辑是只限定轮休勾选6天，其他假期都可以勾」——补休/年休假/
    病假/公差等其余计休符号不再占自选名额，可自由勾选、保存、提交；
    仅每日在岗硬上限（干部/科领导/协管员）仍按全部计休符号统计（见
    counts_as_leave / day_stats，口径未动）。
    """
    return symbol == "X"


def person_cap_count(grid, person_id):
    """某人当前计入个人自选上限的格数（仅轮休 X）。"""
    return sum(
        1 for c in grid.get(person_id, {}).values()
        if counts_toward_cap(c["symbol"])
    )


def day_stats(grid, people, days_in_month):
    by_id = {p["id"]: p for p in people}
    n_cadre = sum(1 for p in people if is_cadre(p))
    n_leader = sum(1 for p in people if is_leader(p))
    n_assistant = sum(1 for p in people if p["kind"] == "assistant")
    stats = []
    for d in range(1, days_in_month + 1):
        cadre_leave = leader_leave = total_leave = assistant_leave = 0
        for pid, cells in grid.items():
            cell = cells.get(d)
            if cell and counts_as_leave(cell["symbol"]):
                total_leave += 1
                if is_cadre(by_id[pid]):
                    cadre_leave += 1
                    if is_leader(by_id[pid]):
                        leader_leave += 1
                if by_id[pid]["kind"] == "assistant":
                    assistant_leave += 1
        stats.append(
            {
                "day": d,
                "cadre_leave": cadre_leave,
                "leader_leave": leader_leave,
                "assistant_leave": assistant_leave,
                "cadre_on_duty": n_cadre - cadre_leave,
                "leader_on_duty": n_leader - leader_leave,
                "assistant_on_duty": n_assistant - assistant_leave,
                "assistant_full": assistant_leave >= ASSISTANT_DAILY_LEAVE_CAP,
                "total_on_duty": len(people) - total_leave,
                "full": cadre_leave >= CADRE_DAILY_LEAVE_CAP
                or leader_leave >= LEADER_DAILY_LEAVE_CAP,
            }
        )
    return stats


# ---------------------------------------------------------------- 应用
app = FastAPI(title="示例科室排班系统", version="2.0")


@app.middleware("http")
async def _no_cache_frontend(request, call_next):
    """v2.5：入口页与 /static/* 一律 no-cache —— 浏览器每次都向服务端校验新版，
    避免启发式缓存让用户停留在旧版 app.js/style.css（仍允许 ETag/Last-Modified
    协商缓存，未变更时返回 304，流量开销可忽略）。"""
    resp = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.on_event("startup")
def _startup():
    init_db()


def current_user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "未登录")
    token = authorization[7:]
    conn = db()
    row = conn.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token=?",
        (token,),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(401, "登录已失效，请重新登录")
    user = dict(row)
    user["is_admin"] = bool(user["is_admin"])
    user["role"] = user_role(user)
    return user


def user_role(user):
    """三级角色：super = admin 账号本身；admin = is_admin 的人员账号；member = 其余。"""
    if user["username"] == "admin":
        return "super"
    return "admin" if user["is_admin"] else "member"


def require_admin(user):
    if not user["is_admin"]:
        raise HTTPException(403, "需要管理员权限")


def require_super(user):
    if user["role"] != "super":
        raise HTTPException(403, "需要超级管理员权限")


class LoginIn(BaseModel):
    username: str
    password: str


@app.get("/api/health")
def health():
    return {"ok": True}


def _log_login(conn, username, user_id, success, request):
    """记录一次登录尝试（成功/失败都记）：IP 优先取 X-Forwarded-For 首值。"""
    ip = None
    ua = None
    if request is not None:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            ip = xff.split(",")[0].strip() or None
        if not ip and request.client:
            ip = request.client.host
        ua = request.headers.get("user-agent")
    conn.execute(
        "INSERT INTO login_logs (username, user_id, success, ip, user_agent)"
        " VALUES (?,?,?,?,?)",
        (username, user_id, 1 if success else 0, ip, ua),
    )
    conn.commit()


@app.post("/api/login")
def login(body: LoginIn, request: Request):
    uname = body.username.strip()
    conn = db()
    # v6.7：登录标识二选一——账号名（姓名/admin）或人员工号（people.work_id），
    # 密码校验不变。工号为空（NULL/''）的人员永不经工号命中；姓名命中优先。
    row = conn.execute(
        "SELECT u.* FROM users u LEFT JOIN people p ON p.id = u.person_id"
        " WHERE u.username=? OR (p.work_id IS NOT NULL AND p.work_id <> '' AND p.work_id=?)"
        " ORDER BY (u.username=?) DESC",
        (uname, uname, uname),
    ).fetchone()
    if not row or row["password_hash"] != hash_pw(body.password):
        _log_login(conn, uname, row["id"] if row else None, False, request)
        conn.close()
        raise HTTPException(401, "用户名或密码错误")
    if not row["active"]:
        _log_login(conn, uname, row["id"], False, request)
        conn.close()
        raise HTTPException(403, "该账号已停用，请联系管理员")
    token = secrets.token_hex(24)
    conn.execute(
        "INSERT INTO sessions (token, user_id) VALUES (?,?)", (token, row["id"])
    )
    _log_login(conn, uname, row["id"], True, request)
    role = user_role(dict(row))
    can_view = user_can_view_others(
        conn, {"role": role, "person_id": row["person_id"]})
    conn.commit()
    conn.close()
    return {
        "token": token,
        "username": row["username"],
        "display_name": row["display_name"],
        "person_id": row["person_id"],
        "is_admin": bool(row["is_admin"]),
        "role": role,
        "can_view_others": can_view,
    }


@app.get("/api/me")
def me_info(user=Depends(current_user)):
    """v2.5：返回当前账号的最新身份信息（字段与登录响应一致，不含 token）。
    前端进入应用时调用它刷新本地缓存的角色快照：管理员授权被增删后，
    老会话刷新页面即可按新角色渲染，无需退出重登。
    v6.13：附带 can_view_others（岗位显示看他人授权，实时查人员表）——
    超管在人员与权限表开关后，老会话刷新即按新授权渲染选人框。"""
    conn = db()
    can_view = user_can_view_others(conn, user)
    conn.close()
    return {
        "username": user["username"],
        "display_name": user["display_name"],
        "person_id": user["person_id"],
        "is_admin": user["is_admin"],
        "role": user["role"],
        "can_view_others": can_view,
    }


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str


@app.post("/api/change-password")
def change_password(body: ChangePasswordIn, user=Depends(current_user)):
    if len(body.new_password) < 4:
        raise HTTPException(400, "新密码至少 4 位")
    conn = db()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
    if not row or row["password_hash"] != hash_pw(body.old_password):
        conn.close()
        raise HTTPException(400, "旧密码不正确")
    conn.execute(
        "UPDATE users SET password_hash=? WHERE id=?",
        (hash_pw(body.new_password), user["id"]),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/users")
def list_users(user=Depends(current_user)):
    require_super(user)
    conn = db()
    rows = conn.execute(
        "SELECT u.*, p.name AS person_name, p.kind AS person_kind"
        " FROM users u LEFT JOIN people p ON p.id = u.person_id ORDER BY u.id"
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d.pop("password_hash", None)
        d["is_admin"] = bool(d["is_admin"])
        d["active"] = bool(d["active"])
        out.append(d)
    return out


class UserPatch(BaseModel):
    is_admin: bool | None = None
    active: bool | None = None
    reset_password: bool = False


@app.patch("/api/users/{user_id}")
def patch_user(user_id: int, body: UserPatch, user=Depends(current_user)):
    require_super(user)
    conn = db()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "账号不存在")
    target = dict(row)
    if target["username"] == "admin" and (body.active is False or body.is_admin is False):
        conn.close()
        raise HTTPException(400, "超级管理员账号不可停用或取消管理员")
    if target["id"] == user["id"] and body.active is False:
        conn.close()
        raise HTTPException(400, "不能停用自己的账号")
    sets, params = [], []
    if body.is_admin is not None:
        sets.append("is_admin=?")
        params.append(1 if body.is_admin else 0)
    if body.active is not None:
        sets.append("active=?")
        params.append(1 if body.active else 0)
    if body.reset_password:
        initial = "admin123" if target["username"] == "admin" else "123456"
        sets.append("password_hash=?")
        params.append(hash_pw(initial))
    if sets:
        params.append(user_id)
        conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id=?", params)
        conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/symbols")
def symbols():
    return [
        {"code": c, "name": SYMBOLS[c][0], "display": SYMBOLS[c][1],
         "counts_leave": SYMBOLS[c][2]}
        for c in SYMBOL_ORDER
    ]


@app.get("/api/people")
def list_people(user=Depends(current_user)):
    conn = db()
    people = get_people(conn, include_inactive=True)
    conn.close()
    if not user["is_admin"]:
        people = [p for p in people if p["active"]]
    return [person_out(p) for p in people]


class PersonIn(BaseModel):
    name: str | None = None
    kind: str | None = None
    grp: str | None = None
    active: bool | None = None
    work_id: str | None = None
    can_view_others: bool | None = None


def _norm_work_id(raw):
    """工号归一化：去空白；空串一律存 NULL（无工号），保证空值永不参与登录匹配/唯一性。"""
    if raw is None:
        return None
    wid = str(raw).strip()
    return wid or None


def _check_work_id_free(conn, work_id, exclude_person_id=None):
    """工号非空时必须全员唯一（与部分唯一索引双保险，给前端明确报错）。"""
    if not work_id:
        return
    row = conn.execute(
        "SELECT id FROM people WHERE work_id=?", (work_id,)
    ).fetchone()
    if row and row["id"] != exclude_person_id:
        raise HTTPException(400, f"工号 {work_id} 已被其他人员使用")


def _validate_person(kind, grp):
    if kind not in KIND_LABELS:
        raise HTTPException(400, "人员类别不合法（科长/副科长/科员/协管员）")
    if kind == "chief":
        return "chief"
    if kind in ("deputy", "cadre"):
        if grp not in ("A", "B"):
            raise HTTPException(400, "副科长/科员必须属于 A 组或 B 组")
        return grp
    # 协管员（v2.2）：可属于 A 组或 B 组（随所在组开放选休）；未指定时为空
    if grp in ("A", "B"):
        return grp
    if grp in (None, ""):
        return None
    raise HTTPException(400, "协管员组别只能是 A 组或 B 组")


@app.post("/api/people")
def create_person(body: PersonIn, user=Depends(current_user)):
    require_super(user)
    if not body.name or not body.name.strip():
        raise HTTPException(400, "姓名不能为空")
    if body.kind is None:
        raise HTTPException(400, "请选择人员类别")
    grp = _validate_person(body.kind, body.grp)
    name = body.name.strip()
    work_id = _norm_work_id(body.work_id)
    conn = db()
    try:
        _check_work_id_free(conn, work_id)
        nxt = conn.execute(
            "SELECT COALESCE(MAX(sort_order),0)+1 AS n FROM people"
        ).fetchone()["n"]
        cur = conn.execute(
            "INSERT INTO people (name, kind, grp, sort_order, active, work_id) VALUES (?,?,?,?,1,?)",
            (name, body.kind, grp, nxt, work_id),
        )
        person_id = cur.lastrowid
        conn.execute(
            "INSERT INTO users (username, password_hash, display_name, person_id, is_admin, active)"
            " VALUES (?,?,?,?,0,1)",
            (name, hash_pw("123456"), name, person_id),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(400, f"人员或账号“{name}”已存在")
    conn.close()
    return {"id": person_id}


@app.put("/api/people/{person_id}")
def update_person(person_id: int, body: PersonIn, user=Depends(current_user)):
    require_super(user)
    conn = db()
    person = get_person(conn, person_id)
    if not person:
        conn.close()
        raise HTTPException(404, "人员不存在")
    kind = body.kind if body.kind is not None else person["kind"]
    grp_in = body.grp if body.grp is not None else person["grp"]
    grp = _validate_person(kind, grp_in)
    sets, params = ["kind=?", "grp=?"], [kind, grp]
    if body.work_id is not None:
        # v6.7：工号随行保存（人员与权限表）；传空串 = 清除工号（存 NULL）
        work_id = _norm_work_id(body.work_id)
        _check_work_id_free(conn, work_id, exclude_person_id=person_id)
        sets.append("work_id=?")
        params.append(work_id)
    if body.can_view_others is not None:
        # v6.13：岗位显示「看他人岗位」授权随行保存（人员与权限表勾选）
        sets.append("can_view_others=?")
        params.append(1 if body.can_view_others else 0)
    if body.name is not None and body.name.strip():
        sets.append("name=?")
        params.append(body.name.strip())
    if body.active is not None:
        sets.append("active=?")
        params.append(1 if body.active else 0)
    params.append(person_id)
    try:
        conn.execute(f"UPDATE people SET {', '.join(sets)} WHERE id=?", params)
        if body.name is not None and body.name.strip():
            conn.execute(
                "UPDATE users SET username=?, display_name=? WHERE person_id=?",
                (body.name.strip(), body.name.strip(), person_id),
            )
        if body.active is not None:
            conn.execute(
                "UPDATE users SET active=? WHERE person_id=?",
                (1 if body.active else 0, person_id),
            )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(400, "姓名与已有人员/账号冲突")
    conn.close()
    return {"ok": True}


class PlanIn(BaseModel):
    year: int
    month: int
    quota: int = 9
    self_limit: int = 6
    first_group: str | None = None


@app.get("/api/plans")
def list_plans(user=Depends(current_user)):
    conn = db()
    rows = conn.execute("SELECT * FROM plans ORDER BY year DESC, month DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/plans")
def create_plan(body: PlanIn, user=Depends(current_user)):
    require_super(user)
    if not (1 <= body.month <= 12):
        raise HTTPException(400, "月份不合法")
    if body.quota < 0 or body.self_limit < 0 or body.self_limit > body.quota:
        raise HTTPException(400, "应休天数/自选上限不合法")
    fg = body.first_group or default_first_group(body.year, body.month)
    if fg not in ("A", "B"):
        raise HTTPException(400, "先行组只能是 A 或 B")
    conn = db()
    try:
        cur = conn.execute(
            "INSERT INTO plans (year, month, quota, self_limit, first_group)"
            " VALUES (?,?,?,?,?)",
            (body.year, body.month, body.quota, body.self_limit, fg),
        )
        conn.commit()
        plan_id = cur.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(400, f"{body.year}年{body.month}月的排班计划已存在")
    conn.close()
    return {"id": plan_id}


def _grid_out(grid):
    return {
        str(pid): {
            str(d): {"symbol": c["symbol"], "source": c["source"]}
            for d, c in cells.items()
        }
        for pid, cells in grid.items()
    }


def plan_detail(conn, plan, user):
    people = get_people(conn)
    grid = load_selections(conn, plan["id"])          # 成员草稿
    final_grid = load_final_selections(conn, plan["id"])  # 管理员最终表
    source_grid = load_source_grid(conn, plan["id"])      # 提交源数据汇总
    subs = submission_status(conn, plan["id"], people)
    dim = calendar.monthrange(plan["year"], plan["month"])[1]
    final_exists = bool(final_grid)
    if final_exists:
        display_grid, display_kind = final_grid, "final"
    elif source_grid:
        display_grid, display_kind = source_grid, "source"
    else:
        display_grid, display_kind = grid, "draft"
    people_out = []
    for p in people:
        limit = plan["quota"] if p["kind"] == "chief" else plan["self_limit"]
        st = subs[p["id"]]
        people_out.append(
            {
                **person_out(p),
                "selected_leave": person_leave_count(grid, p["id"]),
                "draft_leave": person_leave_count(grid, p["id"]),
                "final_leave": person_leave_count(final_grid, p["id"]),
                "display_leave": person_leave_count(display_grid, p["id"]),
                "select_limit": limit,
                "submission_status": st["status"],
                "submitted_at": st["submitted_at"],
                "submission_versions": st["versions"],
                "can_pick": (not plan["published"])
                and st["status"] != "submitted"
                and (user["role"] == "super" or can_pick_now(p, plan, people)),
            }
        )
    # v2.6：审批流已撤销，plan_detail 不再返回 pending_adjustments / my_adjustments
    plan_out = {
        **plan,
        "published": bool(plan["published"]),
        "days_in_month": dim,
        "effective_phase": effective_phase(plan),
        "window": window_dates(plan),
        "first_assistant_id": first_assistant_id(plan, people),
        "final_exists": final_exists,
        "display_kind": display_kind,
        "export_kind": display_kind,
    }
    return {
        "plan": plan_out,
        "people": people_out,
        "grid": _grid_out(grid),
        "final_grid": _grid_out(final_grid),
        "source_grid": _grid_out(source_grid),
        "display_grid": _grid_out(display_grid),
        "display_kind": display_kind,
        "day_stats": day_stats(grid, people, dim),
        "final_day_stats": day_stats(final_grid, people, dim),
        "source_day_stats": day_stats(source_grid, people, dim),
        "display_day_stats": day_stats(display_grid, people, dim),
        "submissions": {str(k): v for k, v in subs.items()},
        "my_person_id": user["person_id"],
        "is_admin": user["is_admin"],
        "role": user["role"],
    }


@app.get("/api/plans/{plan_id}")
def get_plan_detail(plan_id: int, user=Depends(current_user)):
    conn = db()
    plan = get_plan(conn, plan_id)
    out = plan_detail(conn, plan, user)
    conn.close()
    return out


class PlanPatch(BaseModel):
    quota: int | None = None
    self_limit: int | None = None
    first_group: str | None = None
    phase_override: int | None = None
    clear_phase_override: bool = False


@app.patch("/api/plans/{plan_id}")
def patch_plan(plan_id: int, body: PlanPatch, user=Depends(current_user)):
    require_super(user)
    conn = db()
    plan = get_plan(conn, plan_id)
    quota = body.quota if body.quota is not None else plan["quota"]
    self_limit = body.self_limit if body.self_limit is not None else plan["self_limit"]
    if quota < 0 or self_limit < 0 or self_limit > quota:
        conn.close()
        raise HTTPException(400, "应休天数/自选上限不合法")
    fg = body.first_group or plan["first_group"]
    if fg not in ("A", "B"):
        conn.close()
        raise HTTPException(400, "先行组只能是 A 或 B")
    phase_override = plan["phase_override"]
    if body.clear_phase_override:
        phase_override = None
    elif body.phase_override is not None:
        if body.phase_override not in (0, 1, 2, 3):
            conn.close()
            raise HTTPException(400, "阶段覆盖值只能是 0-3")
        phase_override = body.phase_override
    conn.execute(
        "UPDATE plans SET quota=?, self_limit=?, first_group=?, phase_override=?"
        " WHERE id=?",
        (quota, self_limit, fg, phase_override, plan_id),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


class CellIn(BaseModel):
    person_id: int
    day: int
    symbol: str | None = None  # None = 清除（正常上班）


@app.put("/api/plans/{plan_id}/cell")
def set_cell(plan_id: int, body: CellIn, user=Depends(current_user)):
    conn = db()
    plan = get_plan(conn, plan_id)
    people = get_people(conn)
    person = get_person(conn, body.person_id)
    if not person:
        conn.close()
        raise HTTPException(404, "人员不存在")
    dim = calendar.monthrange(plan["year"], plan["month"])[1]
    if not (1 <= body.day <= dim):
        conn.close()
        raise HTTPException(400, "日期不合法")
    if body.symbol is not None and body.symbol not in SYMBOLS:
        conn.close()
        raise HTTPException(400, "符号不合法")

    # v2.4/v2.6：仅超级管理员可直接修改任意人的草稿（超限时警告仍保存）；
    # 人员管理员与普通成员一样只能直接改本人行，改他人行走批量接口
    # POST /api/plans/{id}/admin-edits（保存即生效，不再走审批）。
    admin = user["role"] == "super"
    if not admin:
        if user["person_id"] != body.person_id:
            conn.close()
            if user["role"] == "admin":
                raise HTTPException(
                    403, "调整他人排班请在排班表中点选后点「保存」生效（批量接口），"
                         "不能逐格直存")
            raise HTTPException(403, "只能修改自己的排班")
        if plan["published"]:
            conn.close()
            raise HTTPException(403, "排班已发布锁定")
        subs = submission_status(conn, plan_id, people)
        if subs[body.person_id]["status"] == "submitted":
            conn.close()
            raise HTTPException(403, "您已提交本月选班，等待管理员退回后才能修改")
        if not can_pick_now(person, plan, people):
            conn.close()
            raise HTTPException(403, "您所在的组别尚未开放选休")

    grid = load_selections(conn, plan_id)
    warnings = []
    if body.symbol is not None and counts_as_leave(body.symbol):
        cur_cell = grid.get(body.person_id, {}).get(body.day)
        cur_counts = bool(cur_cell and counts_as_leave(cur_cell["symbol"]))
        # v4.7：个人自选上限只统计轮休 X——仅新符号为 X 时才校验配额
        # （原格已是 X 时替换不重复计数；X 改成其他符号即释放一个名额；
        # 其他假期符号完全不占名额）。下方每日上限仍按全部计休符号校验，
        # cur_counts 保持计休口径供每日上限扣减使用。
        if counts_toward_cap(body.symbol):
            cur_cap = bool(cur_cell and counts_toward_cap(cur_cell["symbol"]))
            my_count = person_cap_count(grid, body.person_id) - (1 if cur_cap else 0)
            limit = plan["quota"] if person["kind"] == "chief" else plan["self_limit"]
            if my_count + 1 > limit:
                msg = f"轮休已勾满自选上限 {limit} 天（其他假期仍可勾选）"
                if not admin:
                    conn.close()
                    raise HTTPException(400, msg)
                warnings.append(msg)
        # 每日上限校验
        if is_cadre(person):
            stats = {s["day"]: s for s in day_stats(grid, people, dim)}
            st = stats[body.day]
            cadre_leave = st["cadre_leave"] - (1 if cur_counts else 0)
            if cadre_leave + 1 > CADRE_DAILY_LEAVE_CAP:
                msg = f"{body.day}日干部休假已满 {CADRE_DAILY_LEAVE_CAP} 人（需保证至少5名干部在岗）"
                if not admin:
                    conn.close()
                    raise HTTPException(400, msg)
                warnings.append(msg)
            if is_leader(person):
                leader_leave = st["leader_leave"] - (1 if cur_counts else 0)
                if leader_leave + 1 > LEADER_DAILY_LEAVE_CAP:
                    msg = f"{body.day}日科领导休假已满 {LEADER_DAILY_LEAVE_CAP} 人（需保证至少1名科领导在岗）"
                    if not admin:
                        conn.close()
                        raise HTTPException(400, msg)
                    warnings.append(msg)
        # 协管员每日上限校验（v2.2）：另一名协管员当日已休假则不可再休
        if person["kind"] == "assistant":
            other_leave = 0
            for q in people:
                if q["kind"] == "assistant" and q["id"] != person["id"]:
                    oc = grid.get(q["id"], {}).get(body.day)
                    if oc and counts_as_leave(oc["symbol"]):
                        other_leave += 1
            if other_leave >= ASSISTANT_DAILY_LEAVE_CAP:
                msg = f"该日另一名协管员已休假，需保证每天至少1名协管员在岗（{body.day}日）"
                if not admin:
                    conn.close()
                    raise HTTPException(400, msg)
                warnings.append(msg)

    if body.symbol is None:
        conn.execute(
            "DELETE FROM selections WHERE plan_id=? AND person_id=? AND day=?",
            (plan_id, body.person_id, body.day),
        )
    else:
        conn.execute(
            "INSERT INTO selections (plan_id, person_id, day, symbol, source)"
            " VALUES (?,?,?,?,?)"
            " ON CONFLICT(plan_id, person_id, day) DO UPDATE SET symbol=excluded.symbol,"
            " source=excluded.source",
            (plan_id, body.person_id, body.day, body.symbol,
             "admin" if admin and user["person_id"] != body.person_id else "self"),
        )
    conn.commit()
    out = plan_detail(conn, get_plan(conn, plan_id), user)
    conn.close()
    out["warnings"] = warnings
    return out


# ------------------------------------------------------- 管理员改他人行（v2.6）
def _leave_limit(plan, person):
    return plan["quota"] if person["kind"] == "chief" else plan["self_limit"]


def _check_batch_caps(plan, people, work, edits, by_id):
    """v4.8：校验整批修改套用后的「最终状态」是否违反硬约束（草稿层口径）。

    取代 v2.6–v4.7 的逐格复检 _check_cell_caps。旧实现边套用边逐格校验，
    每格都按「只套用了本批前若干格」的中间网格判定：同一天处于每日上限
    时，若批次里「加一格休假」的编辑排在「清掉一格休假」之前，加格那一步
    会按中间状态误判超限、整批 400，尽管最终状态完全合法——保存成败
    取决于管理员的点选顺序（用户实测：同日先勾后清被误报「N日干部休假
    已满4人」）。现改为整批先全部套用到工作网格 work，再统一校验：
    - 个人上限：每位被改对象按最终整行只统计轮休 X（v4.7 口径不变），
      按对象在 edits 中首次出现的顺序检查；
    - 每日上限：每个被改日期按最终全员计数（干部/科领导/协管员，仍按
      全部计休符号统计），按日期升序、同一天内干部 -> 科领导 -> 协管员。
    任一违反返回首个错误消息（文案与此前一致），否则返回 None。
    协管员文案由旧逐格口径的「另一名协管员已休假」规范为与干部/科领导
    一致的「N日协管员休假已满 1 人（需保证至少1名协管员在岗）」
    （最终状态下两名协管员同日休假时旧文案语义不成立）。
    """
    dim = calendar.monthrange(plan["year"], plan["month"])[1]
    seen = []
    for e in edits:
        if e.person_id not in seen:
            seen.append(e.person_id)
    for pid in seen:
        person = by_id[pid]
        limit = _leave_limit(plan, person)
        if person_cap_count(work, pid) > limit:
            return f"{person['name']} 调整后轮休将超过自选上限 {limit} 天"
    days = sorted({e.day for e in edits})
    return _daily_cap_error(people, work, days, dim)


def _daily_cap_error(people, work, days, dim):
    """按整批套用后的最终状态校验每日硬上限（全部计休符号口径）。

    v6.3 从 _check_batch_caps 抽出共用：草稿层管理员批量（admin-edits，
    另有个人上限校验）与最终层批量（final/edits，无个人上限）共用同一
    「最终状态」每日校验与同一文案——干部 <=4、科领导 <=2、协管员 <=1，
    按日期升序、同一天内干部 -> 科领导 -> 协管员，返回首个错误或 None。
    """
    if not days:
        return None
    stats = {s["day"]: s for s in day_stats(work, people, dim)}
    for d in days:
        st = stats[d]
        if st["cadre_leave"] > CADRE_DAILY_LEAVE_CAP:
            return (f"{d}日干部休假已满 {CADRE_DAILY_LEAVE_CAP} 人"
                    "（需保证至少5名干部在岗）")
        if st["leader_leave"] > LEADER_DAILY_LEAVE_CAP:
            return (f"{d}日科领导休假已满 {LEADER_DAILY_LEAVE_CAP} 人"
                    "（需保证至少1名科领导在岗）")
        if st["assistant_leave"] > ASSISTANT_DAILY_LEAVE_CAP:
            return (f"{d}日协管员休假已满 {ASSISTANT_DAILY_LEAVE_CAP} 人"
                    "（需保证至少1名协管员在岗）")
    return None


class AdminEditItem(BaseModel):
    person_id: int
    day: int
    symbol: str | None = None  # None = 清除该格（正常上班）


class AdminEditsIn(BaseModel):
    edits: list[AdminEditItem]


@app.post("/api/plans/{plan_id}/admin-edits")
def admin_batch_edits(plan_id: int, body: AdminEditsIn, user=Depends(current_user)):
    """v2.6：人员管理员批量修改他人草稿——保存即生效，取代 v2.4 审批流。

    前端把点选先本地暂存，点「保存」时把他人行修改整批提交到这里（本人行仍走
    PUT /cell 草稿流）。整批校验（任一违反 -> 整体 400，不落表、不记日志）：
    计划未发布；对象均为在职的他人；日期/符号合法；每日硬上限（干部 <=4、
    科领导 <=2、协管员 <=1）；每位对象改后轮休（X）数 <= 其上限（科长=Q，
    其余=S；v4.7 起个人上限只统计轮休，其他假期不占名额）。
    v4.8：硬约束校验改为对「整批套用后的最终状态」统一进行（_check_batch_caps）；
    此前边套用边逐格复检，同日「先加后减」的批次会被中间状态误判超限，
    最终状态合法也被整批拒绝（保存成败取决于点选顺序），已修复。
    成功：落表 source='admin'；仅对实际发生变化的格向 adjustments 表（现作
    管理员修改日志）插一行 status='applied'（含旧值），无变化的格静默生效、
    不留痕；对象已提交时按更新后的完整草稿为其生成新提交版本（旧版保留）。
    """
    import json as _json

    if user["role"] != "admin":
        raise HTTPException(403, "仅人员管理员可批量调整他人排班")
    conn = db()
    plan = get_plan(conn, plan_id)
    if plan["published"]:
        conn.close()
        raise HTTPException(400, "排班已发布，无法再调整")
    people = get_people(conn)
    by_id = {p["id"]: p for p in people}
    dim = calendar.monthrange(plan["year"], plan["month"])[1]
    grid = load_selections(conn, plan_id)
    # 工作网格：深拷贝当前草稿，先整批套用本批修改（此时不写库、不校验），
    # 再由 _check_batch_caps 对最终状态统一校验硬约束（v4.8）
    work = {pid: dict(cells) for pid, cells in grid.items()}
    for e in body.edits:
        target = by_id.get(e.person_id)
        if target is None:
            conn.close()
            raise HTTPException(400, "调整对象不存在或已停用")
        if e.person_id == user["person_id"]:
            conn.close()
            raise HTTPException(400, "修改本人排班请直接编辑本人行并保存草稿")
        if not (1 <= e.day <= dim):
            conn.close()
            raise HTTPException(400, "日期不合法")
        if e.symbol is not None and e.symbol not in SYMBOLS:
            conn.close()
            raise HTTPException(400, "符号不合法")
        if e.symbol is None:
            work.get(e.person_id, {}).pop(e.day, None)
        else:
            work.setdefault(e.person_id, {})[e.day] = {
                "symbol": e.symbol, "source": "admin"}
    err = _check_batch_caps(plan, people, work, body.edits, by_id)
    if err:
        conn.close()
        raise HTTPException(400, err)
    # 净变化（与批前草稿比）：按首次出现顺序收集发生变化的格子
    changed = []
    seen = set()
    for e in body.edits:
        key = (e.person_id, e.day)
        if key in seen:
            continue
        seen.add(key)
        old_cell = grid.get(e.person_id, {}).get(e.day)
        old_symbol = old_cell["symbol"] if old_cell else None
        new_cell = work.get(e.person_id, {}).get(e.day)
        new_symbol = new_cell["symbol"] if new_cell else None
        if old_symbol != new_symbol:
            changed.append((e.person_id, e.day, old_symbol, new_symbol))
    for pid_, day_, _old, new_symbol in changed:
        if new_symbol is None:
            conn.execute(
                "DELETE FROM selections WHERE plan_id=? AND person_id=? AND day=?",
                (plan_id, pid_, day_),
            )
        else:
            conn.execute(
                "INSERT INTO selections (plan_id, person_id, day, symbol, source)"
                " VALUES (?,?,?,?,'admin')"
                " ON CONFLICT(plan_id, person_id, day) DO UPDATE SET"
                " symbol=excluded.symbol, source=excluded.source",
                (plan_id, pid_, day_, new_symbol),
            )
        conn.execute(
            "INSERT INTO adjustments"
            " (plan_id, admin_user_id, admin_name, target_person_id, day, symbol,"
            " old_symbol, status)"
            " VALUES (?,?,?,?,?,?,?,'applied')",
            (plan_id, user["id"], user["display_name"], pid_, day_,
             new_symbol, _old),
        )
    conn.commit()
    # 净变化涉及的对象若已提交：以改后的完整草稿生成新提交版本（旧版保留），
    # 使源数据汇总与「已提交」状态保持一致（与 v2.4 同意路径同口径）。
    regenerated = []
    touched = {pid_ for pid_, _d, _o, _n in changed}
    if touched:
        subs = submission_status(conn, plan_id, people)
        grid2 = load_selections(conn, plan_id)
        for pid_ in sorted(touched):
            if subs.get(pid_, {}).get("status") == "submitted":
                mine = grid2.get(pid_, {})
                data = {str(d): c["symbol"] for d, c in sorted(mine.items())}
                conn.execute(
                    "INSERT INTO submissions (plan_id, person_id, data_json)"
                    " VALUES (?,?,?)",
                    (plan_id, pid_, _json.dumps(data, ensure_ascii=False)),
                )
                regenerated.append(by_id[pid_]["name"])
        if regenerated:
            conn.commit()
    conn.close()
    return {"ok": True, "applied": len(changed), "logged": len(changed),
            "regenerated_submissions": regenerated}


# ---------------------------------------------------------------- 自动补满
def month_weeks(year, month, dim):
    """自然周（周一至周日）分组：返回 {day: week_key} 与 [week_key...]。"""
    from datetime import timedelta

    day_week = {}
    weeks = []
    for d in range(1, dim + 1):
        dt = date(year, month, d)
        monday = dt - timedelta(days=dt.weekday())
        key = monday.isoformat()
        day_week[d] = key
        if key not in weeks:
            weeks.append(key)
    return day_week, weeks


def solve_completion_cp_sat(plan, people, grid):
    """用 OR-Tools CP-SAT 补满。返回 (assignments {pid: [days]}, None) 或 (None, error)。"""
    from ortools.sat.python import cp_model

    dim = calendar.monthrange(plan["year"], plan["month"])[1]
    quota = plan["quota"]
    by_id = {p["id"]: p for p in people}
    day_week, weeks = month_weeks(plan["year"], plan["month"], dim)

    need = {}
    for p in people:
        r = quota - person_leave_count(grid, p["id"])
        if r < 0:
            return None, f"{p['name']} 已选休假 {person_leave_count(grid, p['id'])} 天，超过应休 {quota} 天，请管理员先调整"
        need[p["id"]] = r

    stats = {s["day"]: s for s in day_stats(grid, people, dim)}
    model = cp_model.CpModel()
    x = {}
    for p in people:
        pid = p["id"]
        for d in range(1, dim + 1):
            if d not in grid.get(pid, {}):  # 只填空白格
                x[(pid, d)] = model.NewBoolVar(f"x_{pid}_{d}")
    for p in people:
        pid = p["id"]
        vars_ = [x[(pid, d)] for d in range(1, dim + 1) if (pid, d) in x]
        model.Add(sum(vars_) == need[pid])

    cadre = [p for p in people if is_cadre(p)]
    leaders = [p for p in cadre if is_leader(p)]
    assistants = [p for p in people if p["kind"] == "assistant"]
    for d in range(1, dim + 1):
        cap_c = CADRE_DAILY_LEAVE_CAP - stats[d]["cadre_leave"]
        model.Add(sum(x[(p["id"], d)] for p in cadre if (p["id"], d) in x) <= cap_c)
        cap_l = LEADER_DAILY_LEAVE_CAP - stats[d]["leader_leave"]
        model.Add(sum(x[(p["id"], d)] for p in leaders if (p["id"], d) in x) <= cap_l)
        # v2.2：协管员每日休假 <= 1（保证每天至少 1 名协管员在岗）
        cap_a = ASSISTANT_DAILY_LEAVE_CAP - stats[d]["assistant_leave"]
        model.Add(sum(x[(p["id"], d)] for p in assistants if (p["id"], d) in x)
                  <= max(0, cap_a))

    # 软约束：每人每自然周总休假尽量 <= 2 天（超出计罚）；并倾向于把补休放到当天较空的日期
    penalties = []
    for p in people:
        pid = p["id"]
        existing_week = {}
        for d, cell in grid.get(pid, {}).items():
            if counts_as_leave(cell["symbol"]):
                existing_week[day_week[d]] = existing_week.get(day_week[d], 0) + 1
        for w in weeks:
            days_w = [d for d in range(1, dim + 1) if day_week[d] == w]
            vars_w = [x[(pid, d)] for d in days_w if (pid, d) in x]
            if not vars_w:
                continue
            excess = model.NewIntVar(0, 7, f"excess_{pid}_{w}")
            model.Add(
                sum(vars_w) + existing_week.get(w, 0) - 2 <= excess
            )
            penalties.append(100 * excess)
    spread = []
    for (pid, d), var in x.items():
        if is_cadre(by_id[pid]):
            spread.append(stats[d]["cadre_leave"] * var)
    model.Minimize(sum(penalties) + sum(spread))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0
    solver.parameters.num_search_workers = 4
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        # 先定位是否为协管员约束卡死（v2.2）
        _a_assign, a_ok = solve_assistants_flow(plan, people, grid, need)
        if not a_ok:
            return None, (
                "无法补满：协管员每日至少1人在岗的约束下名额不足"
                "（两名协管员每天最多休 1 人），请管理员先人工调整部分选休。"
            )
        full_days = [d for d in range(1, dim + 1)
                     if CADRE_DAILY_LEAVE_CAP - stats[d]["cadre_leave"] <= 0]
        need_cadre = sum(need[p["id"]] for p in cadre)
        cap_total = sum(CADRE_DAILY_LEAVE_CAP - stats[d]["cadre_leave"]
                        for d in range(1, dim + 1))
        return None, (
            f"无法补满：干部还需补 {need_cadre} 天，但每日在岗约束下仅剩 {cap_total} 个可休名额；"
            f"已满员日期：{full_days if full_days else '无'}。请管理员先人工调整部分选休。"
        )
    assignments = {}
    for (pid, d), var in x.items():
        if solver.Value(var):
            assignments.setdefault(pid, []).append(d)
    return assignments, None


class _Dinic:
    def __init__(self, n):
        self.n = n
        self.graph = [[] for _ in range(n)]

    def add_edge(self, fr, to, cap):
        fwd = [to, cap, None]
        rev = [fr, 0, fwd]
        fwd[2] = rev
        self.graph[fr].append(fwd)
        self.graph[to].append(rev)

    def _bfs(self, s, t):
        from collections import deque

        self.level = [-1] * self.n
        self.level[s] = 0
        q = deque([s])
        while q:
            v = q.popleft()
            for to, cap, _ in self.graph[v]:
                if cap > 0 and self.level[to] < 0:
                    self.level[to] = self.level[v] + 1
                    q.append(to)
        return self.level[t] >= 0

    def _dfs(self, v, t, f):
        if v == t:
            return f
        for i in range(self.it[v], len(self.graph[v])):
            self.it[v] = i
            to, cap, rev = self.graph[v][i]
            if cap > 0 and self.level[to] == self.level[v] + 1:
                ret = self._dfs(to, t, min(f, cap))
                if ret:
                    self.graph[v][i][1] -= ret
                    rev[1] += ret
                    return ret
        return 0

    def max_flow(self, s, t):
        flow = 0
        while self._bfs(s, t):
            self.it = [0] * self.n
            while True:
                pushed = self._dfs(s, t, 10 ** 9)
                if not pushed:
                    break
                flow += pushed
        return flow


def solve_assistants_flow(plan, people, grid, need):
    """协管员补满子问题（最大流）：每人补 need[pid] 天、只能填空白格、
    每日协管员休假总数 <= ASSISTANT_DAILY_LEAVE_CAP（保证每天至少 1 名协管员在岗）。

    返回 (assignments {pid: [days]}, True)；无解时返回 (None, False)。
    供兜底求解器实际补满、以及 CP-SAT 无解时定位是否为协管员约束卡死。
    """
    dim = calendar.monthrange(plan["year"], plan["month"])[1]
    assistants = [p for p in people if p["kind"] == "assistant"]
    if not assistants:
        return {}, True
    stats = {s["day"]: s for s in day_stats(grid, people, dim)}

    idx = {}
    nxt = [0]

    def node(key):
        if key not in idx:
            idx[key] = nxt[0]
            nxt[0] += 1
        return idx[key]

    SRC = node("src")
    SNK = node("snk")
    for p in assistants:
        node(("p", p["id"]))
    for d in range(1, dim + 1):
        node(("d", d))
    dinic = _Dinic(nxt[0])
    total = 0
    for p in assistants:
        pid = p["id"]
        dinic.add_edge(SRC, node(("p", pid)), need[pid])
        total += need[pid]
        for d in range(1, dim + 1):
            if d not in grid.get(pid, {}):  # 只填空白格
                dinic.add_edge(node(("p", pid)), node(("d", d)), 1)
    for d in range(1, dim + 1):
        cap = ASSISTANT_DAILY_LEAVE_CAP - stats[d]["assistant_leave"]
        if cap > 0:
            dinic.add_edge(node(("d", d)), SNK, cap)
    if dinic.max_flow(SRC, SNK) < total:
        return None, False
    inv = {v: k for k, v in idx.items()}
    assignments = {}
    for p in assistants:
        pid = p["id"]
        days = []
        for to, cap, _rev in dinic.graph[node(("p", pid))]:
            key = inv.get(to)
            if isinstance(key, tuple) and key[0] == "d" and cap == 0:
                days.append(key[1])
        assignments[pid] = sorted(days)
    if any(len(assignments.get(p["id"], [])) != need[p["id"]] for p in assistants):
        return None, False
    return assignments, True


def solve_completion_flow(plan, people, grid):
    """兜底求解器：最大流（干部）+ 最大流（协管员，每日休假 <= 1）。约束与 CP-SAT 一致。"""
    dim = calendar.monthrange(plan["year"], plan["month"])[1]
    quota = plan["quota"]
    day_week, weeks = month_weeks(plan["year"], plan["month"], dim)
    stats = {s["day"]: s for s in day_stats(grid, people, dim)}

    need = {}
    for p in people:
        r = quota - person_leave_count(grid, p["id"])
        if r < 0:
            return None, f"{p['name']} 已选休假超过应休 {quota} 天，请管理员先调整"
        need[p["id"]] = r

    cadre = [p for p in people if is_cadre(p)]
    leaders_ids = {p["id"] for p in cadre if is_leader(p)}

    def try_flow(week_cap):
        # 节点编号
        idx = {}
        nxt = [0]

        def node(key):
            if key not in idx:
                idx[key] = nxt[0]
                nxt[0] += 1
            return idx[key]

        SRC = node("src")
        SNK = node("snk")
        for p in cadre:
            node(("p", p["id"]))
            for w in weeks:
                node(("pw", p["id"], w))
            for d in range(1, dim + 1):
                node(("d", d))
                node(("ld", d))
        dinic = _Dinic(nxt[0])
        for p in cadre:
            pid = p["id"]
            dinic.add_edge(SRC, node(("p", pid)), need[pid])
            existing_week = {}
            for d, cell in grid.get(pid, {}).items():
                if counts_as_leave(cell["symbol"]):
                    existing_week[day_week[d]] = existing_week.get(day_week[d], 0) + 1
            caps = {w: max(0, week_cap - existing_week.get(w, 0)) for w in weeks}
            if sum(caps.values()) < need[pid]:
                caps = {w: 7 for w in weeks}
            for w in weeks:
                dinic.add_edge(node(("p", pid)), node(("pw", pid, w)), caps[w])
                days_w = [d for d in range(1, dim + 1) if day_week[d] == w]
                for d in days_w:
                    if d in grid.get(pid, {}):
                        continue
                    if pid in leaders_ids:
                        dinic.add_edge(node(("pw", pid, w)), node(("ld", d)), 1)
                    else:
                        dinic.add_edge(node(("pw", pid, w)), node(("d", d)), 1)
        for d in range(1, dim + 1):
            dinic.add_edge(node(("ld", d)), node(("d", d)),
                           LEADER_DAILY_LEAVE_CAP - stats[d]["leader_leave"])
            dinic.add_edge(node(("d", d)), SNK,
                           CADRE_DAILY_LEAVE_CAP - stats[d]["cadre_leave"])
        total_need = sum(need[p["id"]] for p in cadre)
        flow = dinic.max_flow(SRC, SNK)
        if flow < total_need:
            return None
        # 读回被用满的 pw->day 边（剩余容量 0 且原始容量 1）
        assignments = {}
        inv = {v: k for k, v in idx.items()}
        for p in cadre:
            pid = p["id"]
            for w in weeks:
                u = node(("pw", pid, w))
                for to, cap, _rev in dinic.graph[u]:
                    key = inv.get(to)
                    if isinstance(key, tuple) and key[0] in ("d", "ld") and cap == 0:
                        assignments.setdefault(pid, []).append(key[1])
        for pid in assignments:
            assignments[pid] = sorted(set(assignments[pid]))
        if any(len(assignments.get(p["id"], [])) != need[p["id"]] for p in cadre):
            return None
        return assignments

    assignments = None
    for week_cap in (2, 3, 7):
        assignments = try_flow(week_cap)
        if assignments is not None:
            break
    if assignments is None:
        full_days = [d for d in range(1, dim + 1)
                     if CADRE_DAILY_LEAVE_CAP - stats[d]["cadre_leave"] <= 0]
        return None, (
            f"无法补满：每日在岗约束下干部名额不足；已满员日期："
            f"{full_days if full_days else '无'}。请管理员先人工调整部分选休。"
        )

    # 协管员：独立最大流补齐（每日协管员休假 <= 1，与干部子问题互不影响）
    asst_assign, asst_ok = solve_assistants_flow(plan, people, grid, need)
    if not asst_ok:
        return None, (
            "无法补满：协管员每日至少1人在岗的约束下名额不足"
            "（两名协管员每天最多休 1 人），请管理员先人工调整部分选休。"
        )
    for pid, days in asst_assign.items():
        assignments[pid] = days
    return assignments, None


def solve_completion(plan, people, grid):
    """优先 CP-SAT；不可用时走最大流兜底。返回 (assignments, error, solver_name)。"""
    try:
        assignments, err = solve_completion_cp_sat(plan, people, grid)
        return assignments, err, "ortools-cp-sat"
    except Exception:
        assignments, err = solve_completion_flow(plan, people, grid)
        return assignments, err, "maxflow-fallback"


@app.post("/api/plans/{plan_id}/autocomplete")
def autocomplete(plan_id: int, user=Depends(current_user)):
    require_super(user)
    conn = db()
    plan = get_plan(conn, plan_id)
    people = get_people(conn)
    grid = load_selections(conn, plan_id)
    assignments, err, solver_name = solve_completion(plan, people, grid)
    if err:
        conn.close()
        raise HTTPException(400, err)
    filled = 0
    for pid, days in (assignments or {}).items():
        for d in days:
            conn.execute(
                "INSERT INTO selections (plan_id, person_id, day, symbol, source)"
                " VALUES (?,?,?,'X','auto')",
                (plan_id, pid, d),
            )
            filled += 1
    conn.commit()
    out = plan_detail(conn, get_plan(conn, plan_id), user)
    conn.close()
    out["autocomplete"] = {"filled": filled, "solver": solver_name}
    return out


@app.post("/api/plans/{plan_id}/publish")
def publish(plan_id: int, user=Depends(current_user)):
    require_super(user)
    conn = db()
    get_plan(conn, plan_id)
    conn.execute("UPDATE plans SET published=1 WHERE id=?", (plan_id,))
    conn.commit()
    conn.close()
    return {"ok": True, "published": True}


@app.post("/api/plans/{plan_id}/unpublish")
def unpublish(plan_id: int, user=Depends(current_user)):
    require_super(user)
    conn = db()
    get_plan(conn, plan_id)
    conn.execute("UPDATE plans SET published=0 WHERE id=?", (plan_id,))
    conn.commit()
    conn.close()
    return {"ok": True, "published": False}


# ---------------------------------------------------------------- 提交/源数据/最终表
@app.post("/api/plans/{plan_id}/submit")
def submit_plan(plan_id: int, user=Depends(current_user)):
    """成员提交：把当前草稿快照为源数据（带时间戳、锁定本人编辑）。"""
    import json as _json

    if user["person_id"] is None:
        raise HTTPException(400, "管理员账号没有可提交的个人选班")
    conn = db()
    plan = get_plan(conn, plan_id)
    if plan["published"]:
        conn.close()
        raise HTTPException(403, "排班已发布，无法提交")
    people = get_people(conn)
    subs = submission_status(conn, plan_id, people)
    if subs[user["person_id"]]["status"] == "submitted":
        conn.close()
        raise HTTPException(400, "您已经提交过了，如需修改请联系管理员退回")
    grid = load_selections(conn, plan_id)
    mine = grid.get(user["person_id"], {})
    data = {str(d): c["symbol"] for d, c in sorted(mine.items())}
    cur = conn.execute(
        "INSERT INTO submissions (plan_id, person_id, data_json) VALUES (?,?,?)",
        (plan_id, user["person_id"], _json.dumps(data, ensure_ascii=False)),
    )
    conn.commit()
    row = conn.execute(
        "SELECT submitted_at FROM submissions WHERE id=?", (cur.lastrowid,)
    ).fetchone()
    conn.close()
    return {"ok": True, "submitted_at": row["submitted_at"], "days": len(data)}


@app.post("/api/plans/{plan_id}/return/{person_id}")
def return_submission(plan_id: int, person_id: int, user=Depends(current_user)):
    """管理员退回某人的提交：解锁其编辑，之后重提会生成新版本（旧版本保留）。"""
    require_super(user)
    conn = db()
    get_plan(conn, plan_id)
    cur = conn.execute(
        "UPDATE submissions SET returned=1 WHERE plan_id=? AND person_id=? AND returned=0",
        (plan_id, person_id),
    )
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(400, "该成员尚无有效提交可退回")
    return {"ok": True}


@app.get("/api/plans/{plan_id}/submissions")
def list_submissions(plan_id: int, user=Depends(current_user)):
    """提交版本历史（管理员）：源数据保留一年，全部版本可查。"""
    require_super(user)
    import json as _json

    conn = db()
    get_plan(conn, plan_id)
    rows = conn.execute(
        "SELECT s.*, p.name AS person_name FROM submissions s"
        " JOIN people p ON p.id = s.person_id WHERE s.plan_id=? ORDER BY s.id",
        (plan_id,),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["returned"] = bool(d["returned"])
        d["data"] = _json.loads(d.pop("data_json"))
        out.append(d)
    return out


@app.post("/api/plans/{plan_id}/pull-source")
def pull_source(plan_id: int, user=Depends(current_user)):
    """调取数据：用所有人最新提交快照重建管理员最终表（未提交者为空行）。"""
    require_super(user)
    conn = db()
    plan = get_plan(conn, plan_id)
    if plan["published"]:
        conn.close()
        raise HTTPException(400, "计划已发布，请先取消发布再调取数据")
    latest = latest_submissions(conn, plan_id)
    conn.execute("DELETE FROM final_selections WHERE plan_id=?", (plan_id,))
    n = 0
    for pid, sub in latest.items():
        for d, sym in sub["data"].items():
            conn.execute(
                "INSERT INTO final_selections (plan_id, person_id, day, symbol, source)"
                " VALUES (?,?,?,?, 'source')",
                (plan_id, pid, d, sym),
            )
            n += 1
    conn.execute("UPDATE plans SET final_saved_at=NULL WHERE id=?", (plan_id,))
    conn.commit()
    out = plan_detail(conn, get_plan(conn, plan_id), user)
    conn.close()
    out["pulled"] = {"members": len(latest), "cells": n}
    return out


def _check_final_editable(plan):
    if plan["published"]:
        raise HTTPException(400, "计划已发布，最终表已锁定（可先取消发布）")


@app.put("/api/plans/{plan_id}/final/cell")
def set_final_cell(plan_id: int, body: CellIn, user=Depends(current_user)):
    require_super(user)
    conn = db()
    plan = get_plan(conn, plan_id)
    _check_final_editable(plan)
    people = get_people(conn)
    person = get_person(conn, body.person_id)
    if not person:
        conn.close()
        raise HTTPException(404, "人员不存在")
    dim = calendar.monthrange(plan["year"], plan["month"])[1]
    if not (1 <= body.day <= dim):
        conn.close()
        raise HTTPException(400, "日期不合法")
    if body.symbol is not None and body.symbol not in SYMBOLS:
        conn.close()
        raise HTTPException(400, "符号不合法")
    grid = load_final_selections(conn, plan_id)
    warnings = []
    if body.symbol is not None and counts_as_leave(body.symbol):
        cur_cell = grid.get(body.person_id, {}).get(body.day)
        cur_counts = bool(cur_cell and counts_as_leave(cur_cell["symbol"]))
        if is_cadre(person):
            stats = {s["day"]: s for s in day_stats(grid, people, dim)}
            st = stats[body.day]
            if st["cadre_leave"] - (1 if cur_counts else 0) + 1 > CADRE_DAILY_LEAVE_CAP:
                warnings.append(
                    f"{body.day}日干部休假将超过 {CADRE_DAILY_LEAVE_CAP} 人（在岗不足5人）")
            if is_leader(person) and (
                st["leader_leave"] - (1 if cur_counts else 0) + 1 > LEADER_DAILY_LEAVE_CAP
            ):
                warnings.append(
                    f"{body.day}日科领导休假将超过 {LEADER_DAILY_LEAVE_CAP} 人（无科领导在岗）")
        if person["kind"] == "assistant":
            other_leave = 0
            for q in people:
                if q["kind"] == "assistant" and q["id"] != person["id"]:
                    oc = grid.get(q["id"], {}).get(body.day)
                    if oc and counts_as_leave(oc["symbol"]):
                        other_leave += 1
            if other_leave >= ASSISTANT_DAILY_LEAVE_CAP:
                warnings.append(
                    f"{body.day}日另一名协管员已休假（协管员在岗将不足1人）")
        total = person_leave_count(grid, body.person_id) - (1 if cur_counts else 0) + 1
        if total > plan["quota"]:
            warnings.append(f"{person['name']} 休假将超过应休 {plan['quota']} 天")
    if body.symbol is None:
        conn.execute(
            "DELETE FROM final_selections WHERE plan_id=? AND person_id=? AND day=?",
            (plan_id, body.person_id, body.day),
        )
    else:
        conn.execute(
            "INSERT INTO final_selections (plan_id, person_id, day, symbol, source)"
            " VALUES (?,?,?,?, 'admin')"
            " ON CONFLICT(plan_id, person_id, day) DO UPDATE SET symbol=excluded.symbol,"
            " source=excluded.source",
            (plan_id, body.person_id, body.day, body.symbol),
        )
    conn.commit()
    out = plan_detail(conn, get_plan(conn, plan_id), user)
    conn.close()
    out["warnings"] = warnings
    return out


@app.post("/api/plans/{plan_id}/final/autocomplete")
def final_autocomplete(plan_id: int, user=Depends(current_user)):
    """最终表一键补满：不限是否有人已选，从最终表当前计数起把所有人补到 Q。"""
    require_super(user)
    conn = db()
    plan = get_plan(conn, plan_id)
    _check_final_editable(plan)
    people = get_people(conn)
    grid = load_final_selections(conn, plan_id)
    assignments, err, solver_name = solve_completion(plan, people, grid)
    if err:
        conn.close()
        raise HTTPException(400, err)
    filled = 0
    for pid, days in (assignments or {}).items():
        for d in days:
            conn.execute(
                "INSERT INTO final_selections (plan_id, person_id, day, symbol, source)"
                " VALUES (?,?,?,'X','auto')",
                (plan_id, pid, d),
            )
            filled += 1
    conn.commit()
    out = plan_detail(conn, get_plan(conn, plan_id), user)
    conn.close()
    out["autocomplete"] = {"filled": filled, "solver": solver_name}
    return out


@app.post("/api/plans/{plan_id}/final/save")
def final_save(plan_id: int, user=Depends(current_user)):
    """保存最终表（各处编辑本已实时落库，此操作落保存时间戳作为确认点）。"""
    require_super(user)
    conn = db()
    get_plan(conn, plan_id)
    conn.execute(
        "UPDATE plans SET final_saved_at=datetime('now','localtime') WHERE id=?",
        (plan_id,),
    )
    conn.commit()
    row = conn.execute(
        "SELECT final_saved_at FROM plans WHERE id=?", (plan_id,)
    ).fetchone()
    conn.close()
    return {"ok": True, "final_saved_at": row["final_saved_at"]}


@app.post("/api/plans/{plan_id}/final/edits")
def final_batch_edits(plan_id: int, body: AdminEditsIn, user=Depends(current_user)):
    """v6.3：最终表批量修改（super + 人员管理员）——已发布也可改、保存即生效。

    背景：最终表原写路径只有超管逐格 PUT /final/cell，且
    _check_final_editable 在计划已发布时直接锁定——人员管理员打开
    已发布排班表只能看不能改（CCC实测反馈）。用户 2026-11-01 明确：
    月排班即使已发布，管理员也应能随时修改并保存。本接口与草稿层
    admin-edits 同构：前端点选本地暂存（橙色描边），点「保存修改」
    整批提交；整批先全部套用到工作网格，再对「最终状态」统一校验
    每日硬上限（与 _check_batch_caps 的每日部分同口径、共用
    _daily_cap_error：干部 <=4、科领导 <=2、协管员 <=1）——同日把
    一格休假从甲挪给乙（净零）不会被中间状态误拒（v4.8 同型问题）。
    最终层不适用个人自选上限（既有口径），个人应休 Q 也不在此校验
    （旧逐格路径对超 Q 仅警告）。任一违反 -> 整体 400、不落表、
    不记日志。成功：净变化落 final_selections（source='admin'），
    逐格向 adjustments 记一行 status='applied'（操作者为当前用户），
    并刷新 final_saved_at；计划保持原发布状态不变。当日排班的在岗
    判定实时读最终表（_display_grid_for），修改自动生效。
    无净变化的批次（含空批次、同值重提）直接返回 applied=0——不落
    库、不记日志、不刷新 final_saved_at。
    与旧 PUT /final/cell 的差异：旧路径为超管发布前逐格编辑，硬约束
    只警告不拒绝、发布后锁定，保留不动（v2.x 既有测试口径）；本批
    量路径是发布后整批保存口径，硬约束按最终状态强制校验。
    """
    if user["role"] not in ("admin", "super"):
        raise HTTPException(403, "仅管理员可修改最终排班表")
    conn = db()
    plan = get_plan(conn, plan_id)
    people = get_people(conn)
    by_id = {p["id"]: p for p in people}
    dim = calendar.monthrange(plan["year"], plan["month"])[1]
    grid = load_final_selections(conn, plan_id)
    # 工作网格：深拷贝当前最终表，先整批套用（不写库、不校验），
    # 再由 _daily_cap_error 对最终状态统一校验每日硬上限（v4.8 口径）
    work = {pid: dict(cells) for pid, cells in grid.items()}
    for e in body.edits:
        target = by_id.get(e.person_id)
        if target is None:
            conn.close()
            raise HTTPException(400, "调整对象不存在或已停用")
        if not (1 <= e.day <= dim):
            conn.close()
            raise HTTPException(400, "日期不合法")
        if e.symbol is not None and e.symbol not in SYMBOLS:
            conn.close()
            raise HTTPException(400, "符号不合法")
        if e.symbol is None:
            work.get(e.person_id, {}).pop(e.day, None)
        else:
            work.setdefault(e.person_id, {})[e.day] = {
                "symbol": e.symbol, "source": "admin"}
    err = _daily_cap_error(people, work, sorted({e.day for e in body.edits}), dim)
    if err:
        conn.close()
        raise HTTPException(400, err)
    # 净变化（与批前最终表比）：按首次出现顺序收集发生变化的格子
    changed = []
    seen = set()
    for e in body.edits:
        key = (e.person_id, e.day)
        if key in seen:
            continue
        seen.add(key)
        old_cell = grid.get(e.person_id, {}).get(e.day)
        old_symbol = old_cell["symbol"] if old_cell else None
        new_cell = work.get(e.person_id, {}).get(e.day)
        new_symbol = new_cell["symbol"] if new_cell else None
        if old_symbol != new_symbol:
            changed.append((e.person_id, e.day, old_symbol, new_symbol))
    for pid_, day_, _old, new_symbol in changed:
        if new_symbol is None:
            conn.execute(
                "DELETE FROM final_selections WHERE plan_id=? AND person_id=? AND day=?",
                (plan_id, pid_, day_),
            )
        else:
            conn.execute(
                "INSERT INTO final_selections (plan_id, person_id, day, symbol, source)"
                " VALUES (?,?,?,?,'admin')"
                " ON CONFLICT(plan_id, person_id, day) DO UPDATE SET"
                " symbol=excluded.symbol, source=excluded.source",
                (plan_id, pid_, day_, new_symbol),
            )
        conn.execute(
            "INSERT INTO adjustments"
            " (plan_id, admin_user_id, admin_name, target_person_id, day, symbol,"
            " old_symbol, status)"
            " VALUES (?,?,?,?,?,?,?,'applied')",
            (plan_id, user["id"], user["display_name"], pid_, day_,
             new_symbol, _old),
        )
    if changed:
        conn.execute(
            "UPDATE plans SET final_saved_at=datetime('now','localtime') WHERE id=?",
            (plan_id,),
        )
        conn.commit()
    conn.close()
    return {"ok": True, "applied": len(changed), "logged": len(changed)}


@app.get("/api/history")
def history(user=Depends(current_user)):
    """历史数据：近 12 个月内创建的计划及其提交情况（源数据保留一年）。"""
    require_super(user)
    conn = db()
    rows = conn.execute(
        "SELECT * FROM plans WHERE created_at >= datetime('now','localtime','-12 months')"
        " ORDER BY year DESC, month DESC"
    ).fetchall()
    out = []
    for r in rows:
        plan = dict(r)
        plan["published"] = bool(plan["published"])
        people = get_people(conn)
        subs = submission_status(conn, plan["id"], people)
        final = load_final_selections(conn, plan["id"])
        plan["final_exists"] = bool(final)
        plan["submitted_members"] = sum(
            1 for s in subs.values() if s["status"] == "submitted")
        plan["total_members"] = len(people)
        out.append(plan)
    conn.close()
    return out


@app.get("/api/logs")
def get_logs(user=Depends(current_user)):
    """日志管理（仅超管，v2.6）：管理员修改记录（最近200）+ 登录日志（最近200）。

    修改记录即 adjustments 表全部行：applied=v2.6 保存即生效的修改；
    approved/rejected/superseded=v2.4 审批流历史；void=v2.6 作废的遗留
    pending（从未生效）。按创建时间倒序（同刻以 id 倒序）。
    """
    require_super(user)
    conn = db()

    def adj_out(r):
        return {
            "id": r["id"],
            "plan_id": r["plan_id"],
            "year": r["year"],
            "month": r["month"],
            "plan_label": f"{r['year']}年{r['month']}月",
            "admin_name": r["admin_name"],
            "target_person_id": r["target_person_id"],
            "target_name": r["target_name"],
            "day": r["day"],
            "symbol": r["symbol"],
            "old_symbol": r["old_symbol"],
            "status": r["status"],
            "created_at": r["created_at"],
            "decided_by": r["decided_by"],
            "decided_at": r["decided_at"],
        }

    base = (
        "SELECT a.*, pl.year AS year, pl.month AS month, p.name AS target_name"
        " FROM adjustments a JOIN plans pl ON pl.id = a.plan_id"
        " JOIN people p ON p.id = a.target_person_id"
    )
    modifications = [
        adj_out(r)
        for r in conn.execute(
            base + " ORDER BY a.created_at DESC, a.id DESC LIMIT 200"
        ).fetchall()
    ]
    login_logs = []
    for r in conn.execute(
        "SELECT * FROM login_logs ORDER BY id DESC LIMIT 200"
    ).fetchall():
        d = dict(r)
        d["success"] = bool(d["success"])
        login_logs.append(d)
    conn.close()
    return {"modifications": modifications, "login_logs": login_logs}


# ---------------------------------------------------------------- Excel 导出
@app.get("/api/plans/{plan_id}/export.xlsx")
def export_xlsx(plan_id: int, user=Depends(current_user)):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    conn = db()
    plan = get_plan(conn, plan_id)
    people = get_people(conn)
    # 导出数据源：最终表优先，其次提交源数据汇总，再次成员草稿
    grid = load_final_selections(conn, plan_id)
    grid_source = "final"
    if not grid:
        grid = load_source_grid(conn, plan_id)
        grid_source = "source"
    if not grid:
        grid = load_selections(conn, plan_id)
        grid_source = "draft"
    conn.close()

    year, month, quota = plan["year"], plan["month"], plan["quota"]
    dim = calendar.monthrange(year, month)[1]
    stats = day_stats(grid, people, dim)
    weekday_names = ["一", "二", "三", "四", "五", "六", "日"]

    wb = Workbook()
    ws = wb.active
    ws.title = f"{month}月排班"
    total_col = 2 + dim + 1  # A 类别, B 姓名, C.. 日期, 最后 合计

    thin = Side(style="thin", color="999999")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # 标题
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_col)
    c = ws.cell(row=1, column=1, value=f"{DEPT_NAME}排班表（{month}月可休{quota}天）")
    c.font = Font(size=16, bold=True)
    c.alignment = center
    ws.row_dimensions[1].height = 28
    # 规则说明
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=total_col)
    c = ws.cell(
        row=2, column=1,
        value="每日至少5名干部在岗，其中至少1名科领导在岗；协管员每日至少1人在岗。空白为正常上班，其余符号为各类假期。",
    )
    c.font = Font(size=10)
    c.alignment = center

    # 表头：日期行 + 星期行
    for col, label in ((1, "类别"), (2, "姓名")):
        cell = ws.cell(row=3, column=col, value=label)
        cell.font = Font(bold=True)
        cell.alignment = center
        cell.border = border
        ws.cell(row=4, column=col).border = border
    for d in range(1, dim + 1):
        col = 2 + d
        cell = ws.cell(row=3, column=col, value=d)
        cell.font = Font(bold=True)
        cell.alignment = center
        cell.border = border
        wd = date(year, month, d).weekday()
        cell2 = ws.cell(row=4, column=col, value=weekday_names[wd])
        cell2.alignment = center
        cell2.border = border
        if wd >= 5:
            fill = PatternFill("solid", fgColor="FDECEC")
            cell.fill = fill
            cell2.fill = fill
    cell = ws.cell(row=3, column=total_col, value="合计")
    cell.font = Font(bold=True)
    cell.alignment = center
    cell.border = border
    ws.cell(row=4, column=total_col).border = border

    # 人员行（按 科领导 / 干部 / 协管员 分组）
    groups = [("科领导", [p for p in people if is_leader(p)]),
              ("干部", [p for p in people if is_cadre(p) and not is_leader(p)]),
              ("协管员", [p for p in people if p["kind"] == "assistant"])]
    row = 5
    group_fill = PatternFill("solid", fgColor="EEF3FA")
    for gname, members in groups:
        start = row
        for p in members:
            ws.cell(row=row, column=2, value=p["name"]).alignment = center
            ws.cell(row=row, column=2).border = border
            for d in range(1, dim + 1):
                cell = ws.cell(row=row, column=2 + d)
                item = grid.get(p["id"], {}).get(d)
                if item:
                    cell.value = SYMBOLS[item["symbol"]][1]
                cell.alignment = center
                cell.border = border
                if date(year, month, d).weekday() >= 5:
                    cell.fill = PatternFill("solid", fgColor="F7F7F7")
            tot = ws.cell(row=row, column=total_col,
                          value=person_leave_count(grid, p["id"]))
            tot.alignment = center
            tot.border = border
            row += 1
        ws.merge_cells(start_row=start, start_column=1, end_row=row - 1, end_column=1)
        gc = ws.cell(row=start, column=1, value=gname)
        gc.alignment = center
        gc.font = Font(bold=True)
        gc.fill = group_fill
        for r in range(start, row):
            ws.cell(row=r, column=1).border = border
            ws.cell(row=r, column=1).fill = group_fill

    # 底部统计行（第三行“协管员在岗人数”为 v2.2 新增，<1 时红色标出）
    stat_rows = (
        ("每日在岗人数", "total_on_duty", lambda v: v <= 5, "FFF3CD"),
        ("干部在岗人数", "cadre_on_duty", lambda v: v <= 5, "FFF3CD"),
        ("协管员在岗人数", "assistant_on_duty", lambda v: v < 1, "F8D7DA"),
    )
    for label, key, warn, warn_color in stat_rows:
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
        lc = ws.cell(row=row, column=1, value=label)
        lc.font = Font(bold=True)
        lc.alignment = center
        lc.border = border
        ws.cell(row=row, column=2).border = border
        for s in stats:
            cell = ws.cell(row=row, column=2 + s["day"], value=s[key])
            cell.alignment = center
            cell.border = border
            if warn(s[key]):
                cell.fill = PatternFill("solid", fgColor=warn_color)
        ws.cell(row=row, column=total_col).border = border
        row += 1

    # 图例脚注
    legend = "、".join(
        f"{SYMBOLS[c][0]}{SYMBOLS[c][1]}" for c in SYMBOL_ORDER
    )
    ws.merge_cells(start_row=row + 1, start_column=1, end_row=row + 1,
                   end_column=total_col)
    fc = ws.cell(row=row + 1, column=1,
                 value=f"图例：空白=正常上班；{legend}。")
    fc.font = Font(size=9)
    fc.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)

    ws.column_dimensions["A"].width = 9
    ws.column_dimensions["B"].width = 11
    for d in range(1, dim + 1):
        ws.column_dimensions[get_column_letter(2 + d)].width = 3.4
    ws.column_dimensions[get_column_letter(total_col)].width = 7
    ws.freeze_panes = "C5"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    from urllib.parse import quote

    filename = quote(f"{DEPT_NAME}排班表-{year}年{month}月.xlsx")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "X-Grid-Source": grid_source,
        },
    )


# ---------------------------------------------------------------- 当日排班（v6.0）
# 在月度选休排班之上，按日期给当天上班的干部排具体岗位：
# 5 名干部映射到字母 A–E，套入固定的早/晚班轮转模板；另含值班科长
# （带班）与退税岗（协管员，所有班次，v6.31 起）。默认排班按「全员历史累计」均衡生成
# （见 default_daily_assignment），管理员可在页面上调整后保存确认。
# v6.1：班次不再人工选——由日期按锚点逐日轮替推导（见 shift_for_date）；
# 默认排班另经搭配修正（v6.1「一科领导带一干部」）。
# v6.2：默认排班优化升级为单一词典序目标（见 _optimize_daily_default）：
# 第 1 时段科领导在岗（必须）> 第 1 时段科领导在审图查验岗（尽量）>
# 审图混编得分（v6.1 口径）。
# v6.16：早班新增 6 人方案（用户 2026-11-02 提供图）：当天在岗干部
# ≥6 人且尚无已保存排班时，默认排班改排 A–F 六个字母、套 6 人模板
# （6 班次×75 分钟：审图 2/申报 1/挑查 1/备勤 2，每人恰
# 2 审图+1 申报+1 挑查+2 备勤）；在岗恰 5 人仍用原 5 人模板。
# 已保存的 A–E 五人排班保持原样（模板按已保存字母判定，仍可再保存），
# 晚班不受影响、仍为 A–E。
LETTER_ORDER = ["A", "B", "C", "D", "E"]
LETTER_ORDER6 = ["A", "B", "C", "D", "E", "F"]
ALL_LETTERS = ["A", "B", "C", "D", "E", "F"]
# 当日模板中的休息位岗位名（第 1 时段「在岗」判定要排除它；
# 5 人与 6 人模板的休息位都叫「备勤」，「挑查岗」是在岗岗、不排除）
REST_POSTS = {"备勤"}
SHIFT_LABELS = {"morning": "早班", "evening": "晚班"}
# 字母填充优先级：早班 A 最抢手、E 次之（A→E→B→C→D）；晚班无偏好（A→E 依次）
# 6 人早班按 A→F 依次填充（v6.26：恰 6 人时 B 先钉给带班，余下字母
# 仍按此序；各字母时长均衡性由模板格局本身保证，见 _M6_PATTERNS 注释）。
DAILY_PRIORITY = {"morning": ["A", "E", "B", "C", "D"],
                  "morning6": ["A", "B", "C", "D", "E", "F"],
                  "evening": ["A", "B", "C", "D", "E"],
                  "evening6": ["A", "B", "C", "D", "E", "F"]}

# 班次按日轮替（v6.1，用户定口径）：全科早/晚班逐日交替，不再人工选。
# 锚点 2026-11-02 = 早班，2026-11-03 = 晚班，向前向后无限交替
# （2026-11-01 往前推一日正好是晚班，与用户提供的 11 月 1 日晚班示例吻合）。
SHIFT_ANCHOR = date(2026, 11, 2)


def shift_for_date(d):
    """某日的班次：与锚点相差偶数天为早班、奇数天为晚班。
    Python 的 % 对负数取模结果非负，锚点之前的日期同样正确交替。"""
    return "morning" if (d - SHIFT_ANCHOR).days % 2 == 0 else "evening"


def _dpost(name, letters, note=None, start=None, end=None):
    d = {"post": name, "letters": list(letters)}
    if note:
        d["note"] = note
    if start:
        d["start"] = start
    if end:
        d["end"] = end
    return d


def _dslot(start, end, *posts):
    return {"start": start, "end": end, "posts": list(posts)}


# 早班模板（图3）：45 分钟一轮、10 个时段；5 种岗位格局周期为 5、重复两遍。
# 每时段：审图查验岗 2 人 / 申报岗 1 人 / 挑查岗 1 人 / 备勤 1 人。
# v6.14：当日排班内的轮换休息位改称「备勤」（原称「轮休」）——仅当日
# 模块口径，月排班的轮休符号 X 不受影响。
_M_PATTERNS = [
    (["B", "C"], "D", "E", "A"),
    (["D", "E"], "A", "C", "B"),
    (["A", "B"], "E", "D", "C"),
    (["C", "E"], "B", "A", "D"),
    (["A", "D"], "C", "B", "E"),
]
# 早班 5 人模板 v2 格局（v6.25，用户 2026-11-03 定）：在旧格局基础上
# 优化轮转——旧格局里 C/D/E 三人的两个轻岗（挑查/备勤）相邻或首尾
# 相接，另一侧出现连上 3 班（审图+申报）；新格局把每人的两个轻岗在
# 5 班周期内彻底拆开、互不相邻，于是所有人最多连上 2 班之后必然
# 轮到一班挑查或备勤。总量与公平性不变：每人每 5 班仍是审图 2、
# 申报 1、挑查 1、备勤 1（全天 4/2/2/2），五人的岗位序列为同一节奏
# 错开相位；审图组合 5 组互不重复、无人同岗连排。早餐（7:00–9:00）
# 与中餐（11:00–13:00）窗口内每人至少有一班轻岗可去吃饭。
# 格局（审图对, 申报, 挑查, 备勤）：
#   第1班 B+E / C / D / A；第2班 A+C / D / E / B；
#   第3班 B+D / E / A / C；第4班 C+E / A / B / D；
#   第5班 A+D / B / C / E。
_M_PATTERNS_V2 = [
    (["B", "E"], "C", "D", "A"),
    (["A", "C"], "D", "E", "B"),
    (["B", "D"], "E", "A", "C"),
    (["C", "E"], "A", "B", "D"),
    (["A", "D"], "B", "C", "E"),
]
_M_TIMES = [
    ("07:00", "07:45"), ("07:45", "08:30"), ("08:30", "09:15"),
    ("09:15", "10:00"), ("10:00", "10:45"), ("10:45", "11:30"),
    ("11:30", "12:15"), ("12:15", "13:00"), ("13:00", "13:45"),
    ("13:45", "14:30"),
]
MORNING_SLOTS = [
    _dslot(s, e,
           _dpost("审图查验岗", pat[0]),
           _dpost("申报岗", [pat[1]]),
           _dpost("挑查岗", [pat[2]]),
           _dpost("备勤", [pat[3]]))
    for (s, e), pat in zip(_M_TIMES, [_M_PATTERNS[i % 5] for i in range(10)])
]
MORNING_SLOTS_V2 = [
    _dslot(s, e,
           _dpost("审图查验岗", pat[0]),
           _dpost("申报岗", [pat[1]]),
           _dpost("挑查岗", [pat[2]]),
           _dpost("备勤", [pat[3]]))
    for (s, e), pat in zip(_M_TIMES, [_M_PATTERNS_V2[i % 5] for i in range(10)])
]

# 早班 5 人新模板的生效日期（v6.25，用户 2026-11-03 定）：2026-11-05
# 起（含）的早班用 MORNING_SLOTS_V2，此前的早班仍用旧 MORNING_SLOTS
# ——5 日之前的当日排班已经生成，不因模板更换而改变（默认生成与
# 已保存排班的解析显示都按日期取模板，保证旧日期原样呈现）。
MORNING_V2_FROM = date(2026, 11, 5)


def _morning_slots_for(on_date=None):
    """按日期取早班 5 人模板：on_date（date 对象或 'YYYY-MM-DD'
    字符串）≥ MORNING_V2_FROM 用新模板，否则（或未给日期时）旧模板。"""
    if on_date is None:
        return MORNING_SLOTS
    if isinstance(on_date, str):
        try:
            on_date = date.fromisoformat(on_date.strip())
        except ValueError:
            return MORNING_SLOTS
    return MORNING_SLOTS_V2 if on_date >= MORNING_V2_FROM else MORNING_SLOTS

# 早班 6 人模板（v6.26，用户 2026-11-07 定稿，取代 v6.16 的
# 6 班×75 分钟轮转格局）：固定分组——A–D 固定查验岗（审图 2 人/班）、
# E/F 固定申报岗（1 人/班）；时段：07:00–07:45、07:45–08:30 各
# 45 分钟，其余 1 小时一班至 14:30（共 8 班）；挑查岗：8:30–10:30
# （第 3、4 班）由 E/F 中不当申报者担任，其余时段由 A–D 兼顾
# （用户口径：非窗口挑查几乎等同备勤，公平按轻岗合并计）。
# B 固定为值班科长位（默认生成时带班恒持 B，见
# default_daily_assignment 的 v6.26 钉住逻辑）；第 1 班审图固定
# A+B（用户追加指定）。v6.27（用户 2026-11-07 晚追加）：重岗不
# 连排——上过查验岗（审图）或申报岗的人，下一班必须接挑查岗或
# 备勤岗（即审图/申报不得连班）；窗口挑查人员不变（第 3 班 E、
# 第 4 班 F）。此约束下审图与申报的骨架被锁死为两组交替：
# 审图 (A+B) 与 (C+D) 逐班轮换、申报 F/E 逐班轮换，全员整天
# 重岗与轻岗交替。格局（审图对, 申报, 挑查, 备勤对）：
#   第1班 07:00–07:45  A+B / F / D / C+E
#   第2班 07:45–08:30  C+D / E / B / A+F
#   第3班 08:30–09:30  A+B / F / E / C+D
#   第4班 09:30–10:30  C+D / E / F / A+B
#   第5班 10:30–11:30  A+B / F / D / C+E
#   第6班 11:30–12:30  C+D / E / B / A+F
#   第7班 12:30–13:30  A+B / F / C / D+E
#   第8班 13:30–14:30  C+D / E / A / B+F
# 公平验算（分钟）：A–D 审图各 225（完全一致）、非窗口挑查+备勤
# 各 225；E、F 申报各 225、窗口挑查各 60、备勤各 165（两人对称）。
# 结构上 E/F 在岗合计 285 分，比 A–D 多 60 分（窗口两小时申报组
# 两人都在岗、查验组有 2 人备勤），为固定分组本身所带、用户知悉。
# 岗位名与 5 人模板一致（审图查验/申报/挑查/备勤，v6.17 口径）。
_M6_PATTERNS = [
    (["A", "B"], "F", "D", ["C", "E"]),
    (["C", "D"], "E", "B", ["A", "F"]),
    (["A", "B"], "F", "E", ["C", "D"]),
    (["C", "D"], "E", "F", ["A", "B"]),
    (["A", "B"], "F", "D", ["C", "E"]),
    (["C", "D"], "E", "B", ["A", "F"]),
    (["A", "B"], "F", "C", ["D", "E"]),
    (["C", "D"], "E", "A", ["B", "F"]),
]
_M6_TIMES = [
    ("07:00", "07:45"), ("07:45", "08:30"), ("08:30", "09:30"),
    ("09:30", "10:30"), ("10:30", "11:30"), ("11:30", "12:30"),
    ("12:30", "13:30"), ("13:30", "14:30"),
]
MORNING6_SLOTS = [
    _dslot(s, e,
           _dpost("审图查验岗", pat[0]),
           _dpost("申报岗", [pat[1]]),
           _dpost("挑查岗", [pat[2]]),
           _dpost("备勤", pat[3]))
    for (s, e), pat in zip(_M6_TIMES, _M6_PATTERNS)
]

# 晚班模板（图2）：审图查验岗 A+B 与 C+D 两组轮换；申报岗在部分时段由
# 两组各半小时轮值（拆成两个半小时子段），其余时段表格为空白——即 E 岗
# 全程值守；最后一段申报岗由 A+B 轮流（不拆分、整段一条并注「轮流」）。
EVENING_SLOTS = [
    _dslot("14:30", "15:30",
           _dpost("审图查验岗", ["A", "B"]),
           _dpost("申报岗", ["C"], start="14:30", end="15:00"),
           _dpost("申报岗", ["D"], start="15:00", end="15:30")),
    _dslot("15:30", "16:30",
           _dpost("审图查验岗", ["C", "D"]),
           _dpost("申报岗", ["A"], start="15:30", end="16:00"),
           _dpost("申报岗", ["B"], start="16:00", end="16:30")),
    _dslot("16:30", "17:30",
           _dpost("审图查验岗", ["A", "B"]),
           _dpost("申报岗", ["E"])),
    _dslot("17:30", "18:30",
           _dpost("审图查验岗", ["C", "D"]),
           _dpost("申报岗", ["E"])),
    _dslot("18:30", "19:30",
           _dpost("审图查验岗", ["A", "B"]),
           _dpost("申报岗", ["C"], start="18:30", end="19:00"),
           _dpost("申报岗", ["D"], start="19:00", end="19:30")),
    _dslot("19:30", "20:30",
           _dpost("审图查验岗", ["C", "D"]),
           _dpost("申报岗", ["E"])),
    _dslot("20:30", "21:15",
           _dpost("审图查验岗", ["A", "B"]),
           _dpost("申报岗", ["E"])),
    _dslot("21:15", "22:00",
           _dpost("审图查验岗", ["C", "D"]),
           _dpost("申报岗", ["A", "B"], note="轮流")),
]

# 晚班 6 人模板（v6.20，用户 2026-11-02 定）：在岗干部 ≥6 人的晚班
# 改用固定岗结构，不再 A–E 交叉轮转顶岗——审图查验岗 4 人分两组
# （第一组 A+B、第二组 C+D，两组按现有晚班 8 个时段逐段交替上岗，
# 各组只管审图）、申报岗 2 人（E/F 按时段交替、全程只管申报）。
# 时段沿用晚班既有 8 段（14:30–22:00）。字母含义与 5 人晚班完全
# 不同：A/B=第一组、C/D=第二组、E/F=申报岗。用户给的实例
# （2026-11-03 晚班）：带班BBB（兼第一组）、申报岗DDD+
# AAA、第一组BBB+EEE、第二组CCC+GGG、退税岗JJJ。
EVENING6_SLOTS = [
    _dslot("14:30", "15:30",
           _dpost("审图查验岗", ["A", "B"]),
           _dpost("申报岗", ["E"])),
    _dslot("15:30", "16:30",
           _dpost("审图查验岗", ["C", "D"]),
           _dpost("申报岗", ["F"])),
    _dslot("16:30", "17:30",
           _dpost("审图查验岗", ["A", "B"]),
           _dpost("申报岗", ["E"])),
    _dslot("17:30", "18:30",
           _dpost("审图查验岗", ["C", "D"]),
           _dpost("申报岗", ["F"])),
    _dslot("18:30", "19:30",
           _dpost("审图查验岗", ["A", "B"]),
           _dpost("申报岗", ["E"])),
    _dslot("19:30", "20:30",
           _dpost("审图查验岗", ["C", "D"]),
           _dpost("申报岗", ["F"])),
    _dslot("20:30", "21:15",
           _dpost("审图查验岗", ["A", "B"]),
           _dpost("申报岗", ["E"])),
    _dslot("21:15", "22:00",
           _dpost("审图查验岗", ["C", "D"]),
           _dpost("申报岗", ["F"])),
]

DAILY_TEMPLATES = {"morning": MORNING_SLOTS, "evening": EVENING_SLOTS}


def _daily_variant(shift, letters=None, cadre_count=None, on_date=None):
    """某班次当日排班的模板变体（v6.16）：返回 (模板, 字母序, 变体名)。
    6 人变体（早班 "morning6"、晚班 "evening6"，均 A–F）的判定
    优先级：已保存/待解析的字母含 F → 6 人；否则按当天在岗干部
    数 ≥6 → 6 人；其余为 5 人变体（早班 "morning"、晚班 "evening"，
    均 A–E）。晚班 6 人变体为 v6.20 新增（固定岗结构，见
    EVENING6_SLOTS 注释）。
    v6.25：早班 5 人模板按日期分界——on_date ≥ 2026-11-05 用新模板
    MORNING_SLOTS_V2、此前用旧 MORNING_SLOTS（见 _morning_slots_for）；
    变体名仍为 "morning"，前端无需区分。"""
    if shift == "morning":
        if letters and "F" in letters:
            return MORNING6_SLOTS, LETTER_ORDER6, "morning6"
        if cadre_count is not None and cadre_count >= 6:
            return MORNING6_SLOTS, LETTER_ORDER6, "morning6"
        return _morning_slots_for(on_date), LETTER_ORDER, "morning"
    if letters and "F" in letters:
        return EVENING6_SLOTS, LETTER_ORDER6, "evening6"
    if cadre_count is not None and cadre_count >= 6:
        return EVENING6_SLOTS, LETTER_ORDER6, "evening6"
    return EVENING_SLOTS, LETTER_ORDER, "evening"


def _shift_letters(shift):
    """某班次历史统计要覆盖的字母：两班次均含 F（6 人排班会产生
    F 记录，与 5 人记录同入本班次历史一并均衡；晚班 F 自 v6.20
    起计入）。"""
    return LETTER_ORDER6


def _parse_daily_date(s):
    """'YYYY-MM-DD' -> (date 对象, 年, 月, 日)；格式不合法抛 400。"""
    from datetime import date as _dcls

    try:
        d = _dcls.fromisoformat((s or "").strip())
    except (ValueError, AttributeError):
        raise HTTPException(400, "日期不合法（应为 YYYY-MM-DD）")
    return d, d.year, d.month, d.day


def _plan_for_month(conn, year, month):
    row = conn.execute(
        "SELECT * FROM plans WHERE year=? AND month=?", (year, month)
    ).fetchone()
    return dict(row) if row else None


def _display_grid_for(conn, plan):
    """与 plan_detail 相同的展示层级：最终表 > 提交源数据汇总 > 草稿。"""
    final_grid = load_final_selections(conn, plan["id"])
    if final_grid:
        return final_grid, "final"
    source_grid = load_source_grid(conn, plan["id"])
    if source_grid:
        return source_grid, "source"
    return load_selections(conn, plan["id"]), "draft"


def _on_duty(conn, plan, day):
    """某日上班/休假名单（按展示网格判定：有计休符号=休假；备勤 B=在岗；
    无任何数据=全员在岗）。返回 (people, grid, kind, 在岗干部, 在岗科领导,
    在岗协管员, 休假人员)。"""
    people = get_people(conn)
    grid, kind = _display_grid_for(conn, plan)

    def is_off(p):
        cell = grid.get(p["id"], {}).get(day)
        return bool(cell and counts_as_leave(cell["symbol"]))

    cadre = [p for p in people if is_cadre(p) and not is_off(p)]
    leaders = [p for p in cadre if is_leader(p)]
    assistants = [p for p in people if p["kind"] == "assistant" and not is_off(p)]
    off = [p for p in people if is_off(p)]
    return people, grid, kind, cadre, leaders, assistants, off


def _daily_saved(conn, plan_id, datestr, shift):
    row = conn.execute(
        "SELECT * FROM daily_assignments WHERE plan_id=? AND date=? AND shift=?",
        (plan_id, datestr, shift),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    return {
        "shift": d["shift"],
        "leader_id": d["leader_id"],
        "letters": json.loads(d["letters"] or "{}"),
        "tax_ids": json.loads(d["tax_ids"] or "[]"),
        "created_by": d["created_by"],
        "created_at": d["created_at"],
        "updated_at": d["updated_at"],
    }


def _daily_history(conn, shift):
    """全员历史累计（该班次全部已保存的当日排班）：
    {person_id: {A:n, ..., total:n}}。两班次均覆盖 A–F（6 人排班
    的 F 与 5 人排班的 A–E 同入本班次历史一并均衡；晚班自
    v6.20 起）。"""
    order = _shift_letters(shift)
    stats = {}
    rows = conn.execute(
        "SELECT letters FROM daily_assignments WHERE shift=?", (shift,)
    ).fetchall()
    for r in rows:
        for letter, pid in json.loads(r["letters"] or "{}").items():
            s = stats.setdefault(
                pid, {L: 0 for L in order} | {"total": 0})
            if letter in order:
                s[letter] += 1
                s["total"] += 1
    return stats


def _daily_leader_counts(conn):
    """各科领导历史带班次数（仅晚班已保存排班）：{person_id: n}。
    v6.20 晚班 6 人方案的带班轮流口径据此取「带班次数最少者」
    （同数按名单顺序），使三位科领导轮流带晚班。"""
    rows = conn.execute(
        "SELECT leader_id, COUNT(*) AS n FROM daily_assignments"
        " WHERE shift='evening' AND leader_id IS NOT NULL"
        " GROUP BY leader_id").fetchall()
    return {r["leader_id"]: r["n"] for r in rows}


def _daily_pairs(shift, template=None):
    """审图查验岗的字母对（去重、按模板出现顺序）：晚班固定为
    (A,B)/(C,D)；早班 5 人取 10 个时段里出现过的不同审图对：
    (B,C)/(D,E)/(A,B)/(C,E)/(A,D)；早班 6 人（v6.16）取 6 班次的
    (A,B)/(D,E)/(B,C)/(E,F)/(C,A)/(F,D)。template 缺省用该班次的
    基础模板（早班=5 人），6 人变体由调用方传入 MORNING6_SLOTS。
    v6.25 早班 5 人新模板的审图对为 (B,E)/(A,C)/(B,D)/(C,E)/(A,D)，
    经 template 参数随日期模板流入，推导口径不变。"""
    pairs = []
    for slot in (template if template is not None
                 else DAILY_TEMPLATES[shift]):
        for post in slot["posts"]:
            if post["post"] == "审图查验岗" and len(post["letters"]) == 2:
                pr = (post["letters"][0], post["letters"][1])
                if pr not in pairs:
                    pairs.append(pr)
    return pairs


def _mixed_pair_score(letters, pairs, leader_ids):
    """混编得分：审图对中恰好一名为科领导（另一名为普通干部）的对数。
    用户口径「尽量一科领导带一干部」的可量化形式，得分越高越符合。"""
    n = 0
    for a, b in pairs:
        pa, pb = letters.get(a), letters.get(b)
        if pa is None or pb is None:
            continue
        if (pa in leader_ids) != (pb in leader_ids):
            n += 1
    return n


def _slot1_letter_sets(shift, template=None):
    """第 1 个时间段的字母集合（由模板首段推导，不手抄）：
    working = 首段除休息位「备勤」（5 人与 6 人模板同名）外
    所有岗位的字母（第 1 时段实际在岗的字母）；shen = 首段审图查验
    岗的字母。「挑查岗」是在岗岗、不算休息位，不排除。
    早班 5 人首段：审图 B/C、申报 D、挑查 E、备勤 A
      → working {B,C,D,E}、shen {B,C}（A 在第 1 时段为备勤位）；
    早班 5 人新模板首段（v6.25，2026-11-05 起）：审图 B/E、申报 C、
      挑查 D、备勤 A → working {B,C,D,E}、shen {B,E}（备勤位仍为 A）；
    早班 6 人首段（v6.27）：审图 A/B、申报 F、挑查 D、备勤 C/E
      → working {A,B,D,F}、shen {A,B}（C/E 在第 1 班次备勤）；
    晚班首段：审图 A/B、申报 C/D（各半小时）
      → working {A,B,C,D}、shen {A,B}（E 在第 1 时段无岗位）；
    晚班 6 人首段（v6.20）：审图 A/B、申报 E
      → working {A,B,E}、shen {A,B}（C/D/F 为第二组/申报轮换位，
      第 1 时段无岗位）。晚班 6 人默认排班不经本优化，本推导仅
      供结构一致性。"""
    slot = (template if template is not None
            else DAILY_TEMPLATES[shift])[0]
    working, shen = set(), set()
    for post in slot["posts"]:
        if post["post"] == "备勤":
            continue
        working.update(post["letters"])
        if post["post"] == "审图查验岗":
            shen.update(post["letters"])
    return working, shen


def _daily_objective(shift, letters, pairs, leader_ids, slot1_working,
                     slot1_shen):
    """默认排班的优化目标（v6.2，词典序三元组、越大越好）：
    1) 第 1 时段有科领导在岗（用户口径「必须」：第 1 时段的在岗字母里
       至少一名科领导——早班备勤位 A、晚班无岗的 E 不算在岗）；
    2) 第 1 时段有科领导在审图查验岗（用户口径「尽量」）；
    3) 审图混编得分（v6.1「一科领导带一干部」口径，见 _mixed_pair_score）。"""
    def has_leader(letter_set):
        return any(letters.get(L) in leader_ids for L in letter_set)

    return (
        1 if has_leader(slot1_working) else 0,
        1 if has_leader(slot1_shen) else 0,
        _mixed_pair_score(letters, pairs, leader_ids),
    )


def _optimize_daily_default(shift, letters, cadre, leaders, history,
                            template=None, letter_order=None,
                            pinned_letters=frozenset()):
    """默认排班的确定性优化（v6.2；在 v6.1 搭配修正之上扩展）。
    v6.26：pinned_letters 中的字母不参与互换与班替（早班 6 人恰
    6 人时 B 钉给带班，见 default_daily_assignment）。

    用户定口径：无论早晚班，第 1 个时间段必须有科领导在岗、且尽量
    排在审图查验岗；同时延续 v6.1「审图查验岗尽量一科领导带一干部」。
    三者合成为词典序目标（见 _daily_objective）：第 1 时段在岗 >
    第 1 时段审图 > 混编得分；同目标值时取「公平性代价」最小者
    （代价 = 字母发生变化的人各自新字母的历史次数之和，班替换人时
    离岗者按 0 计，与 v6.1 同口径），再同则取枚举顺序最先者。

    主流程的历史均衡贪心保持不变，本优化在其结果之上做确定性爬山：
    候选动作 (a) 两名已排人员互换字母（按字母 A→E 两两枚举）；
    (b) 班替——用一名未排的在岗科领导替换一名已排的非科领导
    （按字母 A→E、候选人按名单顺序枚举），仅在以下情形枚举：
    已排人员中无科领导（为满足目标 1 必须换人），或 v6.1 情形
    （已排科领导 <2 人且当天在岗科领导 ≥2 人）。每轮在能提升目标
    三元组的候选里取 (目标最高, 代价最低, 枚举顺序最先) 者执行，
    随后重新评估，最多 6 轮；无候选能提升时停止。
    当天无科领导在岗时整段跳过（默认排班与纯贪心完全一致）。
    当目标 1、2 已满足时，本优化退化为 v6.1 的搭配修正（只继续
    提升混编得分）。属默认生成口径，管理员仍可任意改动、保存
    校验不涉及本优化。
    """
    if not leaders or len(letters) < 2:
        return letters
    leader_ids = {p["id"] for p in leaders}
    if letter_order is None:
        letter_order = LETTER_ORDER6 if "F" in letters else LETTER_ORDER
    pairs = _daily_pairs(shift, template)
    slot1_working, slot1_shen = _slot1_letter_sets(shift, template)

    def hist(pid, letter):
        return history.get(pid, {}).get(letter, 0)

    def objective(ls):
        return _daily_objective(shift, ls, pairs, leader_ids,
                                slot1_working, slot1_shen)

    letters = dict(letters)
    for _ in range(6):
        cur = objective(letters)
        crew = set(letters.values())
        crew_leader_n = sum(1 for pid in crew if pid in leader_ids)
        allow_bench = crew_leader_n == 0 or (
            crew_leader_n < 2 and len(leaders) >= 2)
        candidates = []  # (objective, damage, order, new_letters)
        order = 0
        keys = [L for L in letter_order
                if L in letters and L not in pinned_letters]
        # (a) 已排人员互换字母
        for i, l1 in enumerate(keys):
            for l2 in keys[i + 1:]:
                trial = dict(letters)
                trial[l1], trial[l2] = trial[l2], trial[l1]
                dmg = hist(trial[l1], l1) + hist(trial[l2], l2)
                candidates.append((objective(trial), dmg, order, trial))
                order += 1
        # (b) 未排科领导换入（情形见 docstring；换入者恒为科领导）
        if allow_bench:
            bench = [p for p in cadre
                     if p["id"] in leader_ids and p["id"] not in crew]
            for L in keys:
                if letters[L] in leader_ids:
                    continue
                for bp in bench:
                    trial = dict(letters)
                    trial[L] = bp["id"]
                    candidates.append(
                        (objective(trial), hist(bp["id"], L), order, trial))
                    order += 1
        improving = [c for c in candidates if c[0] > cur]
        if not improving:
            break
        improving.sort(key=lambda c: (tuple(-v for v in c[0]), c[1], c[2]))
        letters = improving[0][3]
    return letters


def _default_evening6(cadre, leaders, history, leader_counts):
    """晚班 6 人方案的默认排班（v6.20，用户 2026-11-02 定）：
    返回 (letters, leader_id)。

    结构（固定岗、不交叉顶岗）：审图第一组 A（组长）+B、第二组
    C（组长）+D、申报岗 E+F。默认人选口径：
    - 带班不再默认取最高职务者，改为三位科领导**轮流**：在当晚
      在岗科领导中取历史晚班带班次数最少者（同数按名单顺序）；
    - 带班兼任审图第一组组长（A）——恰 6 人在岗时如此（用户实例
      即带班BBB在第一组）；在岗 ≥7 人时带班**不参与字母排班**
      （只任带班，与早班 v6.19 同口径），第一组组长改由池内其余
      科领导按历史均衡担任；
    - 审图尽量「一科领导带一干部」：两组组长优先由科领导担任，
      组员为干部；第三位科领导（若在岗且未任组长/带班）去申报岗
      F 位（用户实例：科长AAA在申报岗、与干部DDD搭档，
      申报名单干部在前、科领导在后）；
    - 干部填位按本班次历史均衡：取 (该字母历史次数, 总次数,
      名单顺序) 最小者，与全系统默认口径一致；
    - 当天无科领导在岗时带班为空缺、各岗全由干部按历史填。
    只约束默认排班生成，管理员手动改排与保存校验不拦截。"""
    leader_id = None
    if leaders:
        leader_id = min(
            leaders,
            key=lambda p: (leader_counts.get(p["id"], 0),
                           p["sort_order"]))["id"]
    pool = list(cadre)
    if len(cadre) >= 7 and leader_id is not None:
        pool = [p for p in cadre if p["id"] != leader_id]
    leader_ids = {p["id"] for p in leaders}
    remaining = list(pool)

    def _key(letter):
        def k(p):
            h = history.get(p["id"], {})
            return (h.get(letter, 0), h.get("total", 0), p["sort_order"])
        return k

    def take_leader(letter, prefer_id=None):
        cands = [p for p in remaining if p["id"] in leader_ids]
        if not cands:
            return None
        pick = None
        if prefer_id is not None:
            pick = next((p for p in cands if p["id"] == prefer_id), None)
        if pick is None:
            pick = min(cands, key=_key(letter))
        remaining.remove(pick)
        return pick["id"]

    def take_cadre(letter):
        cands = [p for p in remaining if p["id"] not in leader_ids]
        if not cands:
            return None
        pick = min(cands, key=_key(letter))
        remaining.remove(pick)
        return pick["id"]

    def take_any(letter):
        if not remaining:
            return None
        pick = min(remaining, key=_key(letter))
        remaining.remove(pick)
        return pick["id"]

    letters = {}
    # A：第一组组长——带班本人（恰 6 人时带班在池内）优先，
    # 否则池内科领导，再否则干部按历史。
    a = take_leader("A", prefer_id=leader_id) or take_any("A")
    if a is not None:
        letters["A"] = a
    # C：第二组组长——同上（带班已占用/不在池内时自然轮到下一位）。
    c = take_leader("C") or take_any("C")
    if c is not None:
        letters["C"] = c
    # B/D：两组组员——干部优先按历史（保证混编），无干部时任意。
    for letter in ("B", "D"):
        v = take_cadre(letter) or take_any(letter)
        if v is not None:
            letters[letter] = v
    # E：申报岗第一位——干部优先（用户实例干部在前）。
    e = take_cadre("E") or take_any("E")
    if e is not None:
        letters["E"] = e
    # F：申报岗第二位——余下科领导优先（第三位科领导在此），
    # 否则任意余下人员按历史。
    f = take_leader("F") or take_any("F")
    if f is not None:
        letters["F"] = f
    return letters, leader_id


def default_daily_assignment(shift, cadre, leaders, assistants, history,
                             leader_counts=None, on_date=None):
    """按全员历史累计均衡生成默认排班（用户定口径：纳入全员数据，
    足够长的时间内所有人的各字母岗次数趋近相同，而非简单的次日顺延）。

    按字母优先级逐个填充（早班 A→E→B→C→D，晚班 A→B→C→D→E）：
    每个字母在「当天在岗且尚未分到字母」的干部中，取
    (该字母历史次数, 该班次字母总次数, 名单顺序) 最小者。
    生成后再经 _optimize_daily_default 做词典序优化（v6.2：第 1
    时段科领导在岗 > 第 1 时段科领导在审图查验岗 > v6.1 的「一科
    领导带一干部」混编得分；当天有科领导在岗时即生效）。
    值班科长默认当天在岗的最高职务者（科长优先、同级按名单顺序）；
    退税岗为当天全部在岗协管员，自动带入、无需人工选（v6.31 起所有班次都带，此前仅晚班）。
    v6.16：早班在岗干部 ≥6 人时改排 A–F 六字母（6 人模板、优先级
    A→F），在岗恰 5 人（或更少）仍排 A–E；晚班恒 A–E。
    v6.19：早班在岗 ≥7 人时仍套 6 人模板，但**值班科长不参与字母
    排班**（用户 2026-11-02 定）：默认带班（当天在岗最高职务者）
    只任带班、不占 A–F 任一字母，六个字母在其余在岗干部中按历史
    均衡分配（优化器的班替候选同样不含值班科长，不会被换回）。
    在岗恰 6 人时值班科长仍参与（否则只剩 5 人排不满 6 岗）。
    v6.20：晚班在岗 ≥6 人改走 _default_evening6 的固定岗结构
    （审图两组+申报 2 人、带班三位科领导轮流、≥7 人时带班不
    参与字母排班），不经通用贪心与 _optimize_daily_default
    （其词典序目标与交叉顶岗的旧晚班结构绑定）；晚班在岗 ≤5 人
    与早班各情形仍走通用口径。带班轮流仅用于晚班 6 人方案，
    早班与 5 人晚班的默认带班仍为最高职务者。
    同此前各条默认生成规则一样：只约束默认排班，管理员手动改排
    与保存校验不拦截。
    v6.25：早班 5 人模板按 on_date 分界取新旧（见 _morning_slots_for），
    优化器的审图对与第 1 时段字母集合随所取模板推导、口径不变——
    新模板首段为审图 B/E、申报 C、挑查 D、备勤 A，故第 1 时段在岗
    字母 {B,C,D,E}、审图字母 {B,E}（备勤位仍为 A）。
    v6.26：早班 6 人模板换用固定分组新格局（A–D 查验、E/F 申报、
    窗口挑查归 E/F，8 班时段，见 _M6_PATTERNS 注释）；恰 6 人时
    B 固定为值班科长位：带班先钉 B（优化器以 pinned_letters 保护、
    不换走），其余字母照旧贪心+优化。第 1 时段审图 {A,B} 含 B，
    故带班恒满足「第 1 时段科领导在审图」的目标。≥7 人仍按
    v6.19（带班不占字母），B 由其余干部按历史均衡取得。
    """
    template, letter_order, variant = _daily_variant(
        shift, cadre_count=len(cadre), on_date=on_date)
    if variant == "evening6":
        letters, leader_id = _default_evening6(
            cadre, leaders, history, leader_counts or {})
        tax_ids = [p["id"] for p in assistants]
        return {"leader_id": leader_id, "letters": letters,
                "tax_ids": tax_ids}
    leader_id = leaders[0]["id"] if leaders else None
    pool = list(cadre)
    if variant == "morning6" and leader_id is not None and len(cadre) >= 7:
        pool = [p for p in cadre if p["id"] != leader_id]
    remaining = list(pool)
    letters = {}
    pinned = frozenset()
    if variant == "morning6" and leader_id is not None and len(cadre) == 6:
        # v6.26：B 固定值班科长位（用户 2026-11-07 定）——恰 6 人时
        # 带班（当天在岗最高职务者）先钉住 B，其余字母再按优先级
        # 历史均衡填充；优化器不得把 B 换走（pinned_letters）。
        # ≥7 人时带班本就不占字母（v6.19），不适用本钉住。
        letters["B"] = leader_id
        remaining = [p for p in remaining if p["id"] != leader_id]
        pinned = frozenset({"B"})
    for letter in DAILY_PRIORITY[variant]:
        if letter in letters:
            continue
        if not remaining:
            break

        def _key(p):
            h = history.get(p["id"], {})
            return (h.get(letter, 0), h.get("total", 0), p["sort_order"])

        pick = min(remaining, key=_key)
        letters[letter] = pick["id"]
        remaining.remove(pick)
    letters = _optimize_daily_default(shift, letters, pool, leaders, history,
                                      template=template,
                                      letter_order=letter_order,
                                      pinned_letters=pinned)
    # v6.31（用户 2026-11-11 定）：退税岗所有班次都带——不再分早晚班，
    # 早班默认排班同样带入当天全部在岗协管员（此前仅晚班）。
    tax_ids = [p["id"] for p in assistants]
    return {"leader_id": leader_id, "letters": letters, "tax_ids": tax_ids}


def resolve_daily_slots(shift, letters, by_id, template=None, on_date=None):
    """把字母排班套入模板，解析为带真名的时段表（管理员预览/前端渲染共用）。
    template 缺省时按字母判定变体（v6.16：含 F 用早班 6 人模板）。
    v6.25：早班 5 人模板按 on_date 分界取新旧——已保存排班的解析
    必须传当日日期，保证 2026-11-05 之前的旧排班按旧模板原样呈现。"""
    if template is None:
        template = _daily_variant(shift, letters=letters, on_date=on_date)[0]
    out = []
    for slot in template:
        posts = []
        for post in slot["posts"]:
            people = []
            for L in post["letters"]:
                pid = letters.get(L)
                if pid is not None and pid in by_id:
                    people.append({"letter": L, "person_id": pid,
                                   "name": by_id[pid]["name"]})
            posts.append({
                "name": post["post"],
                "note": post.get("note"),
                "start": post.get("start", slot["start"]),
                "end": post.get("end", slot["end"]),
                "people": people,
            })
        out.append({
            "start": slot["start"], "end": slot["end"],
            "time": f"{slot['start']}–{slot['end']}",
            "posts": posts,
        })
    return out


def person_daily_timeline(shift, letters, by_id, person_id, on_date=None):
    """某人在某班次的个人时间轴：[{time, post, partners, note}]。
    同岗同事只在真正同时在岗时给出（审图查验岗的另一人）；申报岗
    各半小时拆分是各自独立值守（partners 空）；晚班最后一段 A+B
    「轮流」不拆时间，整段一条、note 为「与{name}轮流」。
    v6.25：早班 5 人模板按 on_date 分界取新旧（同 resolve_daily_slots）。"""
    inv = {pid: L for L, pid in letters.items()}
    letter = inv.get(person_id)
    if letter is None:
        return None
    entries = []
    template = _daily_variant(shift, letters=letters, on_date=on_date)[0]
    for slot in template:
        for post in slot["posts"]:
            if letter not in post["letters"]:
                continue
            start = post.get("start", slot["start"])
            end = post.get("end", slot["end"])
            others = [by_id[letters[L]]["name"] for L in post["letters"]
                      if L != letter and letters.get(L) in by_id]
            note = None
            partners = []
            if post.get("note") == "轮流":
                note = f"与{'、'.join(others)}轮流" if others else "轮流"
            elif post["post"] == "审图查验岗":
                partners = others
            entries.append({
                "time": f"{start}–{end}",
                "post": post["post"],
                "partners": partners,
                "note": note,
            })
    return entries


def _require_daily_admin(user):
    if user["role"] not in ("super", "admin"):
        raise HTTPException(403, "仅管理员可生成当日排班")


@app.get("/api/daily/context")
def daily_context(date: str, shift: str = None, refresh: int = 0,
                  user=Depends(current_user)):
    """生成当日排班页的上下文：某日的在岗名单、历史累计、
    已保存排班（若有）、按历史均衡算出的默认排班、模板与预览。
    班次由日期按轮替锚点推导（v6.1）；旧客户端传来的 shift 参数
    一律忽略，不作校验。
    v6.28「刷新人数」（用户 2026-11-11 定）：refresh=1 时忽略已保存
    排班对模板变体/字母序/预览的牵引，改按**最新排班表**的当天在岗
    干部数重新判定变体，并以默认排班作预览——月表把某天由 6 人改
    成 5 人（或反之）后，已保存的旧人数方案不会再把页面锁死在旧
    字母数上。已保存记录本身不删除、不改动，响应仍带 saved，
    是否采用刷新结果由管理员确认后点「保存排班」决定。"""
    _require_daily_admin(user)
    _d, y, m, day = _parse_daily_date(date)
    shift = shift_for_date(_d)
    conn = db()
    plan = _plan_for_month(conn, y, m)
    if not plan:
        conn.close()
        raise HTTPException(404, f"{y}年{m}月尚无排班计划，无法生成当日排班")
    people, _grid, kind, cadre, leaders, assistants, off = _on_duty(
        conn, plan, day)
    by_id = {p["id"]: p for p in people}
    history = _daily_history(conn, shift)
    saved = _daily_saved(conn, plan["id"], date, shift)
    default = default_daily_assignment(
        shift, cadre, leaders, assistants, history,
        leader_counts=_daily_leader_counts(conn), on_date=_d)
    init_letters = saved["letters"] if saved else default["letters"]
    # v6.16：模板与字母序按初始排班判定——有已保存排班时随其字母
    # （历史 A–E 五人排班仍套 5 人模板），无保存时随默认排班
    # （早班在岗 ≥6 人为 A–F 6 人模板）。
    # v6.25：早班 5 人模板再按日期分界（on_date=_d）取新旧，已保存的
    # 旧日期排班按旧模板解析、新日期排班按新模板解析。
    # v6.28：refresh=1（「刷新人数」）时改按最新在岗干部数判定变体、
    # 预览随默认排班，让月表改动后的人数能覆盖已保存的旧方案。
    if refresh:
        init_letters = default["letters"]
        template, letter_order, variant = _daily_variant(
            shift, cadre_count=len(cadre), on_date=_d)
    else:
        template, letter_order, variant = _daily_variant(
            shift, letters=init_letters, on_date=_d)
    hist_order = _shift_letters(shift)
    out = {
        "plan": {"id": plan["id"], "year": y, "month": m,
                 "published": bool(plan["published"])},
        "date": date, "day": day, "shift": shift,
        "shift_label": SHIFT_LABELS[shift],
        "variant": variant,
        "letter_order": letter_order,
        "refresh": bool(refresh),
        "display_kind": kind,
        "on_duty_cadre": [person_out(p) for p in cadre],
        "on_duty_leaders": [person_out(p) for p in leaders],
        "on_duty_assistants": [person_out(p) for p in assistants],
        "off_duty": [person_out(p) for p in off],
        "names": {str(p["id"]): p["name"] for p in people},
        "history_stats": {
            str(p["id"]): history.get(
                p["id"], {L: 0 for L in hist_order} | {"total": 0})
            for p in cadre
        },
        "saved": saved,
        "default": default,
        "template": template,
        "preview": resolve_daily_slots(shift, init_letters, by_id,
                                       template=template),
    }
    conn.close()
    return out


class DailySaveIn(BaseModel):
    date: str
    shift: str | None = None  # v6.1：班次由日期推导，此字段仅兼容旧客户端，忽略
    leader_id: int | None = None
    letters: dict = {}


@app.post("/api/daily/assignments")
def daily_save(body: DailySaveIn, user=Depends(current_user)):
    """保存（upsert）某日的当日排班：值班科长 + 字母岗；
    班次由日期按轮替锚点推导（v6.1，客户端传来的 shift 一律忽略）；
    退税岗由服务端按当天在岗协管员自动计算（所有班次，v6.31 起；
    此前仅晚班）。
    v6.16：字母集合校验——接受 A–E（5 人，兼容历史排班再保存）
    或 A–F（6 人方案），其余组合一律 400；v6.20 起晚班同口径
    （晚班 6 人方案亦为 A–F）。"""
    _require_daily_admin(user)
    _d, y, m, day = _parse_daily_date(body.date)
    shift = shift_for_date(_d)
    conn = db()
    plan = _plan_for_month(conn, y, m)
    if not plan:
        conn.close()
        raise HTTPException(404, f"{y}年{m}月尚无排班计划，无法保存当日排班")
    _people, _grid, _kind, cadre, leaders, assistants, _off = _on_duty(
        conn, plan, day)
    leader_ids = {p["id"] for p in leaders}
    if leaders:
        if body.leader_id is None:
            conn.close()
            raise HTTPException(400, "请选择值班科长")
        if body.leader_id not in leader_ids:
            conn.close()
            raise HTTPException(400, "值班科长必须是当天在岗的科领导")
    letters = {}
    try:
        letters = {str(k): int(v) for k, v in (body.letters or {}).items()}
    except (TypeError, ValueError):
        conn.close()
        raise HTTPException(400, "岗位数据不合法")
    if set(letters.keys()) == set(LETTER_ORDER6):
        letter_order = LETTER_ORDER6
    elif set(letters.keys()) == set(LETTER_ORDER):
        letter_order = LETTER_ORDER
    else:
        conn.close()
        raise HTTPException(
            400, "岗位必须排满 A、B、C、D、E 五个字母"
            "（6 人方案为 A、B、C、D、E、F 六个字母）")
    if len(set(letters.values())) != len(letter_order):
        conn.close()
        raise HTTPException(400, "同一人不能同时占两个岗位")
    cadre_ids = {p["id"] for p in cadre}
    by_id = {p["id"]: p for p in _people}
    for L in letter_order:
        pid = letters[L]
        if pid not in by_id:
            conn.close()
            raise HTTPException(400, "排岗人员不存在")
        if pid not in cadre_ids:
            conn.close()
            raise HTTPException(
                400, f"{by_id[pid]['name']} 当天休假或不属于干部，不能排岗")
    # v6.31：退税岗所有班次都带（见 default_daily_assignment 同口径）。
    tax_ids = [p["id"] for p in assistants]
    conn.execute(
        "INSERT INTO daily_assignments (plan_id, date, shift, leader_id,"
        " letters, tax_ids, created_by) VALUES (?,?,?,?,?,?,?)"
        " ON CONFLICT(plan_id, date, shift) DO UPDATE SET"
        " leader_id=excluded.leader_id, letters=excluded.letters,"
        " tax_ids=excluded.tax_ids,"
        " updated_at=datetime('now','localtime')",
        (plan["id"], body.date, shift, body.leader_id,
         json.dumps(letters, ensure_ascii=False),
         json.dumps(tax_ids), user["id"]),
    )
    conn.commit()
    saved = _daily_saved(conn, plan["id"], body.date, shift)
    conn.close()
    return {"ok": True, "saved": saved}


def _mine_shift(conn, plan, datestr, day, shift, viewer, grid, by_id):
    """岗位显示：某班次下查看者本人的状态与（干部的）个人时间轴。"""
    saved = _daily_saved(conn, plan["id"], datestr, shift)
    if not saved:
        return {"shift": shift, "status": "none"}
    letters = {L: pid for L, pid in saved["letters"].items()}
    leader = by_id.get(saved["leader_id"])
    crew = [{"letter": L, "person_id": letters[L],
             "name": by_id[letters[L]]["name"]}
            for L in ALL_LETTERS if L in letters and letters[L] in by_id]
    tax_names = [by_id[pid]["name"] for pid in saved["tax_ids"]
                 if pid in by_id]
    base = {"shift": shift, "leader_name": leader["name"] if leader else None,
            "crew": crew, "tax_names": tax_names}
    cell = grid.get(viewer["id"], {}).get(day)
    if cell and counts_as_leave(cell["symbol"]):
        return {**base, "status": "off"}
    if viewer["kind"] == "assistant":
        # v6.31：退税岗所有班次都带——早班协管员同样按 saved.tax_ids
        # 判定退税岗，不再恒回 na；不在名单（旧保存/异常）才回 na。
        if viewer["id"] in saved["tax_ids"]:
            return {**base, "status": "tax"}
        return {**base, "status": "na"}
    timeline = person_daily_timeline(shift, letters, by_id, viewer["id"],
                                     on_date=datestr)
    if timeline is not None:
        inv = {pid: L for L, pid in letters.items()}
        return {**base, "status": "ok", "letter": inv[viewer["id"]],
                "timeline": timeline}
    return {**base, "status": "notassigned"}


@app.get("/api/daily/mine")
def daily_mine(date: str, person_id: int = None, user=Depends(current_user)):
    """岗位显示：某人某日的岗位（班次按日期轮替推导，v6.1 起每日只有
    一个班次，返回单班次结构 result）。
    v6.4：可选 person_id 查看他人岗位——仅 admin/super 可用，成员传
    他人 id 返回 403（本人 id 或不传均可）。响应 viewer 指被查看的人，
    另带 view_person 与 is_self 供前端区分「您的岗位 / 某人的岗位」。
    v6.13：查看他人放宽为「admin/super 角色，或本人被授予
    can_view_others」（首批两名协管员）——user_can_view_others 判定；
    无资格者仍是 403，但文案改为如实表述「您没有查看他人岗位的
    权限」（旧文案「只有管理员…」已不准确：被授权成员同样可看）。
    超管账号无对应人员：不传 person_id 时默认名单第一人（选人查看）。
    账号无对应人员且名单为空时返回 has_person=False 的空态（不报错）。
    v6.21：响应带 on_duty_people——该日**在岗**人员名单（干部+
    协管员、按名单顺序，以展示网格的计休符号判定），供前端选人框
    只列当天上班的人（用户 2026-11-02 定：休假者不应出现在选人
    框里）；无计划月份返回空列表。接口本身仍允许查询休假者本人
    状态（off），过滤只发生在选人框层面。"""
    _d, y, m, day = _parse_daily_date(date)
    shift = shift_for_date(_d)
    head = {"date": date, "shift": shift, "shift_label": SHIFT_LABELS[shift]}
    conn = db()
    target_id = person_id if person_id is not None else user["person_id"]
    if target_id is not None and target_id != user["person_id"]:
        if not user_can_view_others(conn, user):
            conn.close()
            raise HTTPException(403, "您没有查看他人岗位的权限")
    if target_id is None:
        people0 = get_people(conn)
        if not people0:
            conn.close()
            return {**head, "has_person": False, "viewer": None,
                    "view_person": None, "is_self": False,
                    "plan": None, "on_duty_people": [],
                    "result": {"shift": shift, "status": "noplan"}}
        target_id = people0[0]["id"]
    viewer = get_person(conn, target_id)
    if viewer is None:
        conn.close()
        raise HTTPException(404, "人员不存在")
    is_self = target_id == user["person_id"]
    plan = _plan_for_month(conn, y, m)
    if not plan:
        conn.close()
        return {**head, "has_person": True,
                "viewer": person_out(viewer),
                "view_person": person_out(viewer), "is_self": is_self,
                "plan": None, "on_duty_people": [],
                "result": {"shift": shift, "status": "noplan"}}
    grid, _kind = _display_grid_for(conn, plan)
    people = get_people(conn)
    by_id = {p["id"]: p for p in people}

    def _is_off(pid):
        c = grid.get(pid, {}).get(day)
        return bool(c and counts_as_leave(c["symbol"]))

    on_duty_people = [person_out(p) for p in people if not _is_off(p["id"])]
    cell = grid.get(viewer["id"], {}).get(day)
    off_symbol = None
    if cell and counts_as_leave(cell["symbol"]):
        off_symbol = SYMBOLS[cell["symbol"]][1]
    out = {
        **head, "has_person": True,
        "viewer": person_out(viewer),
        "view_person": person_out(viewer), "is_self": is_self,
        "plan": {"id": plan["id"], "year": y, "month": m},
        "on_duty_people": on_duty_people,
        "off_symbol": off_symbol,
        "result": _mine_shift(conn, plan, date, day, shift, viewer, grid,
                              by_id),
    }
    conn.close()
    return out


@app.get("/api/daily/dayview")
def daily_dayview(date: str, user=Depends(current_user)):
    """当日排班整表（成员只读，v6.9）：某日全科当日排班——带班、
    字母岗真名（早班 6 人方案含 F，v6.16）、退税岗（所有班次），以及套模板
    解析出的时段预览表（与管理员页预览同源 resolve_daily_slots，
    模板按已保存字母判定变体）。
    任何登录账号（普通成员/协管员/管理员/超管）都可查，与本人当天
    是否在岗无关；只反映**已保存**的排班：未保存返回 status=none
    （绝不把默认排班当正式结果返回），当月无计划返回 noplan。
    全程只读、无写入。"""
    _d, y, m, day = _parse_daily_date(date)
    shift = shift_for_date(_d)
    head = {"date": date, "shift": shift, "shift_label": SHIFT_LABELS[shift]}
    conn = db()
    plan = _plan_for_month(conn, y, m)
    if not plan:
        conn.close()
        return {**head, "status": "noplan", "plan": None}
    plan_info = {"id": plan["id"], "year": y, "month": m}
    saved = _daily_saved(conn, plan["id"], date, shift)
    if not saved:
        conn.close()
        return {**head, "status": "none", "plan": plan_info}
    people = get_people(conn)
    by_id = {p["id"]: p for p in people}
    letters = {L: pid for L, pid in saved["letters"].items()}
    crew = [{"letter": L, "person_id": letters[L],
             "name": by_id[letters[L]]["name"]}
            for L in ALL_LETTERS if L in letters and letters[L] in by_id]
    leader = by_id.get(saved["leader_id"])
    _tmpl, _order, _variant = _daily_variant(shift, letters=letters,
                                             on_date=_d)
    out = {
        **head, "status": "ok", "plan": plan_info,
        "variant": _variant, "letter_order": _order,
        "leader_name": leader["name"] if leader else None,
        "letters": {c["letter"]: c["name"] for c in crew},
        "crew": crew,
        "tax_names": [by_id[pid]["name"] for pid in saved["tax_ids"]
                      if pid in by_id],
        "preview": resolve_daily_slots(shift, letters, by_id, on_date=_d),
    }
    conn.close()
    return out


# ---------------------------------------------------------------- 静态前端
@app.get("/")
def index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
