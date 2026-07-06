"""Finance persistence and source synchronization."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("FINANCE_DB_PATH", str(BASE_DIR / "data" / "finance.db"))).expanduser()
DEFAULT_ROOT = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/Obsidian Vault/11-财务库-Finance"
DEFAULT_EXPENSE_DIR = DEFAULT_ROOT / "03-支出记录"
DEFAULT_SOUNDWAVE_MEMORY = Path.home() / ".openclaw/workspace/agents/soundwave/workspace/memory/short-term/2026-07-05.md"
DEFAULT_BUDGET_PROJECT_NAME = "基于轻量化大模型的无人集群分布时决策机制研究"
DEFAULT_BUDGET_PROJECT_KEY = "lightweight-llm-uav-swarm-decision"
DEFAULT_BUDGET_AMOUNT = 1_000_000.0
DEFAULT_BUDGET_PROJECTS = (
    {
        "project_key": DEFAULT_BUDGET_PROJECT_KEY,
        "name": DEFAULT_BUDGET_PROJECT_NAME,
        "budget_amount": DEFAULT_BUDGET_AMOUNT,
    },
    {
        "project_key": "surface-fleet-manual-wargame",
        "name": "水面舰艇编队战术手工兵棋",
        "budget_amount": 200_000.0,
    },
    {
        "project_key": "large-scale-uav-swarm-task-planning",
        "name": "大规模无人机群任务规划",
        "budget_amount": 50_000.0,
    },
)
DEFAULT_BUDGET_CATEGORIES = ("差旅费", "设备费", "会议费", "外协费", "管理费", "材料费", "劳务费", "其他")
MONEY_RE = re.compile(r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?")
MISSING_VALUES = {"", "none", "null", "n/a", "na", "nan", "未注明", "无"}
FINANCE_TABLES = {
    "budget_projects": "finance_budget_projects",
    "budget_categories": "finance_budget_categories",
    "reimbursements": "finance_reimbursements",
    "reimbursement_items": "finance_reimbursement_items",
    "invoice_sources": "finance_invoice_sources",
    "approval_events": "finance_approval_events",
    "batches": "finance_batches",
    "projects": "finance_projects",
    "items": "finance_items",
    "expenses": "finance_expenses",
    "enrichment": "finance_enrichment_suggestions",
    "audit": "finance_audit_logs",
}
TABLE_ORDERING = {
    "finance_budget_projects": "updated_at DESC, id DESC",
    "finance_budget_categories": "project_key ASC, id ASC",
    "finance_reimbursements": "submitted_at DESC, updated_at DESC, id DESC",
    "finance_reimbursement_items": "reimbursement_key ASC, id ASC",
    "finance_invoice_sources": "created_at DESC, id DESC",
    "finance_approval_events": "created_at DESC, id DESC",
    "finance_batches": "updated_at DESC, id DESC",
    "finance_projects": "updated_at DESC, id DESC",
    "finance_items": "id ASC",
    "finance_expenses": "expense_date DESC, id DESC",
    "finance_enrichment_suggestions": "confidence DESC, updated_at DESC, id DESC",
    "finance_audit_logs": "id DESC",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _money(value: Any) -> float:
    match = MONEY_RE.search(str(value or ""))
    return round(float(match.group(0).replace(",", "")), 2) if match else 0.0


def _clean_text(value: Any) -> str:
    raw = str(value or "").strip()
    return "" if raw.lower() in MISSING_VALUES else raw


def _date(value: Any) -> str:
    raw = _clean_text(value)
    if not raw:
        return ""
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(raw[:10], fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return raw


def _month(value: str) -> str:
    return value[:7] if len(value) >= 7 else "未注明"


def _parse_frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    values: dict[str, Any] = {}
    current_key: str | None = None
    for raw in text[3:end].splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("  - ") and current_key:
            values.setdefault(current_key, []).append(line[4:].strip())
            continue
        if ":" not in line and "：" not in line:
            continue
        sep = "：" if "：" in line and (":" not in line or line.index("：") < line.index(":")) else ":"
        key, value = line.split(sep, 1)
        current_key = key.strip()
        values[current_key] = value.strip() if value.strip() else []
    return values


def _finance_root() -> Path:
    return Path(os.getenv("FINANCE_VAULT_ROOT", str(DEFAULT_ROOT))).expanduser()


def _expense_dir() -> Path:
    return Path(os.getenv("FINANCE_EXPENSE_DIR", str(DEFAULT_EXPENSE_DIR))).expanduser()


def _soundwave_memory() -> Path:
    return Path(os.getenv("OPENCLAW_FINANCE_MEMORY", str(DEFAULT_SOUNDWAVE_MEMORY))).expanduser()


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


class FinanceService:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS finance_budget_projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_key TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    budget_amount REAL NOT NULL DEFAULT 0,
                    allocated_amount REAL NOT NULL DEFAULT 0,
                    spent_amount REAL NOT NULL DEFAULT 0,
                    remaining_amount REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    source TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS finance_budget_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_key TEXT NOT NULL,
                    category TEXT NOT NULL,
                    budget_amount REAL NOT NULL DEFAULT 0,
                    spent_amount REAL NOT NULL DEFAULT 0,
                    remaining_amount REAL NOT NULL DEFAULT 0,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(project_key, category)
                );
                CREATE TABLE IF NOT EXISTS finance_reimbursements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reimbursement_key TEXT UNIQUE NOT NULL,
                    batch_key TEXT,
                    title TEXT NOT NULL,
                    project_key TEXT,
                    source_agent TEXT,
                    source_path TEXT,
                    total_amount REAL NOT NULL DEFAULT 0,
                    item_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'draft',
                    submitted_at TEXT,
                    confirmed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    raw_json TEXT
                );
                CREATE TABLE IF NOT EXISTS finance_reimbursement_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reimbursement_key TEXT NOT NULL,
                    item_key TEXT NOT NULL,
                    project_key TEXT,
                    budget_category TEXT,
                    vendor TEXT,
                    invoice_no TEXT,
                    source_type TEXT,
                    source_ref TEXT,
                    expense_date TEXT,
                    amount REAL NOT NULL DEFAULT 0,
                    note TEXT,
                    status TEXT NOT NULL DEFAULT 'confirmed',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(reimbursement_key, item_key)
                );
                CREATE TABLE IF NOT EXISTS finance_invoice_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_key TEXT UNIQUE NOT NULL,
                    reimbursement_key TEXT NOT NULL,
                    item_key TEXT,
                    source_type TEXT NOT NULL,
                    source_ref TEXT,
                    file_path TEXT,
                    email_id TEXT,
                    scan_path TEXT,
                    status TEXT NOT NULL DEFAULT 'linked',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS finance_approval_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reimbursement_key TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT,
                    from_status TEXT,
                    to_status TEXT,
                    comment TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS finance_batches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_key TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    source_agent TEXT,
                    source_path TEXT,
                    total_amount REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'confirmed',
                    confirmed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    raw_json TEXT
                );
                CREATE TABLE IF NOT EXISTS finance_projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_key TEXT NOT NULL,
                    project_key TEXT NOT NULL,
                    name TEXT NOT NULL,
                    amount REAL NOT NULL DEFAULT 0,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(batch_key, project_key)
                );
                CREATE TABLE IF NOT EXISTS finance_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_key TEXT NOT NULL,
                    item_key TEXT NOT NULL,
                    project_key TEXT,
                    vendor TEXT,
                    invoice_no TEXT,
                    expense_date TEXT,
                    category TEXT,
                    amount REAL NOT NULL DEFAULT 0,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(batch_key, item_key)
                );
                CREATE TABLE IF NOT EXISTS finance_expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    expense_key TEXT UNIQUE NOT NULL,
                    invoice_id TEXT,
                    project_name TEXT,
                    project_code TEXT,
                    expense_date TEXT,
                    month TEXT,
                    amount REAL NOT NULL DEFAULT 0,
                    amount_label TEXT,
                    category TEXT,
                    handler TEXT,
                    archived_at TEXT,
                    source TEXT,
                    source_path TEXT,
                    mtime REAL,
                    data_quality TEXT NOT NULL DEFAULT 'unknown',
                    quality_issues TEXT,
                    needs_review INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS finance_audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    source TEXT,
                    target_key TEXT,
                    detail_json TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS finance_enrichment_suggestions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    expense_key TEXT NOT NULL,
                    field_name TEXT NOT NULL,
                    current_value TEXT,
                    suggested_value TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0,
                    reason TEXT,
                    source TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    raw_json TEXT,
                    UNIQUE(expense_key, field_name, suggested_value)
                );
                """
            )
            self._ensure_column(conn, "finance_expenses", "data_quality", "TEXT NOT NULL DEFAULT 'unknown'")
            self._ensure_column(conn, "finance_expenses", "quality_issues", "TEXT")
            self._ensure_column(conn, "finance_expenses", "needs_review", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "finance_reimbursements", "batch_key", "TEXT")
            self._ensure_column(conn, "finance_reimbursements", "project_key", "TEXT")
            self._ensure_column(conn, "finance_reimbursements", "source_agent", "TEXT")
            self._ensure_column(conn, "finance_reimbursements", "total_amount", "REAL NOT NULL DEFAULT 0")
            self._ensure_column(conn, "finance_reimbursements", "item_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "finance_reimbursements", "confirmed_at", "TEXT")
            self._ensure_column(conn, "finance_reimbursements", "raw_json", "TEXT")
            self._ensure_budget_seed(conn)

    def sync_sources(self, record_audit: bool = True) -> dict[str, Any]:
        self.ensure_schema()
        result = {
            "soundwave": self.sync_soundwave(),
            "obsidian": self.sync_obsidian(),
            "synced_at": _now(),
        }
        if record_audit:
            self.record_audit("sync_sources", "finance_service", "all", result)
        return result

    def schema_summary(self) -> dict[str, Any]:
        self.ensure_schema()
        self.sync_sources(record_audit=False)
        tables = []
        with self.connect() as conn:
            for public_name, table_name in FINANCE_TABLES.items():
                columns = self._all(conn, f"PRAGMA table_info({table_name})")
                row_count = self._scalar(conn, f"SELECT COUNT(*) FROM {table_name}")
                tables.append({
                    "name": public_name,
                    "table": table_name,
                    "rows": int(row_count or 0),
                    "columns": [
                        {
                            "name": column["name"],
                            "type": column["type"],
                            "required": bool(column["notnull"]),
                            "primary_key": bool(column["pk"]),
                        }
                        for column in columns
                    ],
                })
        return {
            "status": "ready",
            "source": str(self.db_path),
            "tables": tables,
            "generated_at": _now(),
        }

    def table_records(self, table_key: str, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        self.ensure_schema()
        self.sync_sources(record_audit=False)
        table_name = FINANCE_TABLES.get(table_key)
        if table_name is None:
            return {
                "status": "error",
                "message": f"Unknown finance table: {table_key}",
                "available_tables": sorted(FINANCE_TABLES.keys()),
            }
        order_by = TABLE_ORDERING[table_name]
        with self.connect() as conn:
            total = self._scalar(conn, f"SELECT COUNT(*) FROM {table_name}")
            rows = self._all(conn, f"SELECT * FROM {table_name} ORDER BY {order_by} LIMIT ? OFFSET ?", (limit, offset))
        return {
            "status": "ready",
            "source": str(self.db_path),
            "name": table_key,
            "table": table_name,
            "limit": limit,
            "offset": offset,
            "total": int(total or 0),
            "rows": rows,
            "generated_at": _now(),
        }

    def budget_report(self) -> dict[str, Any]:
        self.ensure_schema()
        self.sync_sources(record_audit=False)
        self.refresh_budget_spending()
        with self.connect() as conn:
            projects = self._all(
                conn,
                """
                SELECT *
                FROM finance_budget_projects
                ORDER BY updated_at DESC, id DESC
                """,
            )
            categories = self._all(
                conn,
                """
                SELECT *
                FROM finance_budget_categories
                ORDER BY project_key ASC, id ASC
                """,
            )
        total_budget = round(sum(float(project.get("budget_amount") or 0) for project in projects), 2)
        total_spent = round(sum(float(project.get("spent_amount") or 0) for project in projects), 2)
        return {
            "status": "ready",
            "source": str(self.db_path),
            "summary": {
                "projects": len(projects),
                "budget_amount": total_budget,
                "spent_amount": total_spent,
                "remaining_amount": round(total_budget - total_spent, 2),
                "execution_percent": round((total_spent / total_budget) * 100, 2) if total_budget else 0,
            },
            "projects": projects,
            "categories": categories,
            "generated_at": _now(),
        }

    def refresh_budget_spending(self) -> None:
        with self.connect() as conn:
            item_rows = self._all(
                conn,
                "SELECT vendor, note, amount FROM finance_items WHERE batch_key=?",
                ("soundwave-2026-07-05",),
            )
            spent_by_category = {category: 0.0 for category in DEFAULT_BUDGET_CATEGORIES}
            for row in item_rows:
                category = self._classify_budget_category(f"{row.get('note') or ''} {row.get('vendor') or ''}")
                spent_by_category[category] = round(spent_by_category.get(category, 0.0) + float(row.get("amount") or 0), 2)

            total_spent = round(sum(spent_by_category.values()), 2)
            now = _now()
            for project in DEFAULT_BUDGET_PROJECTS:
                project_key = project["project_key"]
                budget_amount = float(project["budget_amount"])
                project_spent = total_spent if project_key == DEFAULT_BUDGET_PROJECT_KEY else 0.0
                conn.execute(
                    """
                    UPDATE finance_budget_projects
                    SET spent_amount=?, remaining_amount=?, updated_at=?
                    WHERE project_key=?
                    """,
                    (project_spent, round(budget_amount - project_spent, 2), now, project_key),
                )
                for category in DEFAULT_BUDGET_CATEGORIES:
                    spent = spent_by_category.get(category, 0.0) if project_key == DEFAULT_BUDGET_PROJECT_KEY else 0.0
                    conn.execute(
                        """
                        INSERT INTO finance_budget_categories(
                          project_key, category, budget_amount, spent_amount, remaining_amount, note, created_at, updated_at
                        )
                        VALUES(?,?,?,?,?,?,?,?)
                        ON CONFLICT(project_key, category) DO UPDATE SET
                          spent_amount=excluded.spent_amount,
                          remaining_amount=excluded.remaining_amount,
                          updated_at=excluded.updated_at
                        """,
                        (
                            project_key,
                            category,
                            0.0,
                            spent,
                            0.0,
                            "预算额度待编制",
                            now,
                            now,
                        ),
                    )

    def quality_report(self, limit: int = 100) -> dict[str, Any]:
        self.ensure_schema()
        self.sync_sources(record_audit=False)
        with self.connect() as conn:
            issue_rows = self._all(
                conn,
                """
                SELECT value AS issue, COUNT(*) AS count
                FROM finance_expenses, json_each(COALESCE(NULLIF(quality_issues, ''), '[]'))
                GROUP BY value
                ORDER BY count DESC, value
                """,
            )
            review_rows = self._all(
                conn,
                """
                SELECT expense_key, project_name, expense_date, amount, category, data_quality, quality_issues, source_path
                FROM finance_expenses
                WHERE needs_review=1
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            )
            totals = {
                "records": self._scalar(conn, "SELECT COUNT(*) FROM finance_expenses"),
                "complete": self._scalar(conn, "SELECT COUNT(*) FROM finance_expenses WHERE needs_review=0"),
                "needs_review": self._scalar(conn, "SELECT COUNT(*) FROM finance_expenses WHERE needs_review=1"),
                "missing_amount": self._scalar(conn, "SELECT COUNT(*) FROM finance_expenses WHERE quality_issues LIKE '%missing_amount%'"),
                "missing_date": self._scalar(conn, "SELECT COUNT(*) FROM finance_expenses WHERE quality_issues LIKE '%missing_date%'"),
            }
        return {
            "status": "ready",
            "source": str(self.db_path),
            "summary": {key: int(value or 0) for key, value in totals.items()},
            "issues": issue_rows,
            "records": review_rows,
            "generated_at": _now(),
        }

    def run_enrichment(self, limit: int = 100) -> dict[str, Any]:
        self.ensure_schema()
        self.sync_sources(record_audit=False)
        now = _now()
        created = 0
        scanned = 0
        with self.connect() as conn:
            rows = self._all(
                conn,
                """
                SELECT *
                FROM finance_expenses
                WHERE needs_review=1
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            )
            for row in rows:
                scanned += 1
                conn.execute(
                    "DELETE FROM finance_enrichment_suggestions WHERE expense_key=? AND status='pending'",
                    (row["expense_key"],),
                )
                for suggestion in self._build_enrichment_suggestions(row):
                    result = conn.execute(
                        """
                        INSERT INTO finance_enrichment_suggestions(
                          expense_key, field_name, current_value, suggested_value, confidence,
                          reason, source, status, created_at, updated_at, raw_json
                        )
                        VALUES(?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(expense_key, field_name, suggested_value) DO UPDATE SET
                          current_value=excluded.current_value,
                          confidence=excluded.confidence,
                          reason=excluded.reason,
                          source=excluded.source,
                          status=CASE
                            WHEN finance_enrichment_suggestions.status='applied' THEN 'applied'
                            ELSE 'pending'
                          END,
                          updated_at=excluded.updated_at,
                          raw_json=excluded.raw_json
                        """,
                        (
                            row["expense_key"],
                            suggestion["field_name"],
                            str(suggestion.get("current_value") or ""),
                            str(suggestion["suggested_value"]),
                            float(suggestion["confidence"]),
                            suggestion["reason"],
                            suggestion["source"],
                            "pending",
                            now,
                            now,
                            json.dumps(suggestion, ensure_ascii=False),
                        ),
                    )
                    if result.rowcount:
                        created += 1
        result = {
            "status": "ready",
            "scanned": scanned,
            "suggestions_upserted": created,
            "generated_at": now,
        }
        self.record_audit("run_enrichment", "finance_service", "finance_enrichment_suggestions", result)
        return result

    def enrichment_report(self, limit: int = 100) -> dict[str, Any]:
        self.ensure_schema()
        with self.connect() as conn:
            summary = {
                "suggestions": self._scalar(conn, "SELECT COUNT(*) FROM finance_enrichment_suggestions"),
                "pending": self._scalar(conn, "SELECT COUNT(*) FROM finance_enrichment_suggestions WHERE status='pending'"),
                "applied": self._scalar(conn, "SELECT COUNT(*) FROM finance_enrichment_suggestions WHERE status='applied'"),
                "high_confidence": self._scalar(conn, "SELECT COUNT(*) FROM finance_enrichment_suggestions WHERE status='pending' AND confidence>=0.7"),
            }
            field_rows = self._all(
                conn,
                """
                SELECT field_name AS field, COUNT(*) AS count, ROUND(AVG(confidence), 2) AS avg_confidence
                FROM finance_enrichment_suggestions
                WHERE status='pending'
                GROUP BY field_name
                ORDER BY count DESC, field_name
                """,
            )
            rows = self._all(
                conn,
                """
                SELECT s.*, e.project_name, e.amount, e.expense_date, e.category, e.source_path
                FROM finance_enrichment_suggestions s
                LEFT JOIN finance_expenses e ON e.expense_key=s.expense_key
                ORDER BY s.status='pending' DESC, s.confidence DESC, s.updated_at DESC, s.id DESC
                LIMIT ?
                """,
                (limit,),
            )
        return {
            "status": "ready",
            "source": str(self.db_path),
            "summary": {key: int(value or 0) for key, value in summary.items()},
            "fields": field_rows,
            "suggestions": rows,
            "generated_at": _now(),
        }

    def sync_soundwave(self) -> dict[str, Any]:
        path = _soundwave_memory()
        if not path.exists():
            return {"status": "missing", "source": str(path)}
        text = path.read_text(encoding="utf-8", errors="ignore")
        total_match = re.search(r"(?:合计|总计)[:：]\s*([0-9,.]+)\s*元", text)
        total = _money(total_match.group(1)) if total_match else 0.0
        batch_key = "soundwave-2026-07-05"
        now = _now()

        projects = []
        for line in text.splitlines():
            match = re.search(r"-\s*项目[一二三四五六七八九十]+[（(]([^）)]+)[）)][:：]\s*([0-9,.]+)\s*元", line)
            if match:
                name = match.group(1).strip()
                projects.append({"key": self._slug(name), "name": name, "amount": _money(match.group(2))})

        items = []
        in_split_section = False
        for line in text.splitlines():
            if line.startswith("## 报销项目拆分"):
                in_split_section = True
                continue
            if in_split_section and line.startswith("## "):
                break
            if not in_split_section or not line.startswith("| #"):
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) >= 4 and cells[0] != "#":
                items.append({
                    "key": cells[0],
                    "invoice": cells[0],
                    "vendor": cells[1],
                    "amount": _money(cells[2]),
                    "note": cells[3],
                })

        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO finance_batches(batch_key,title,source_agent,source_path,total_amount,status,confirmed_at,created_at,updated_at,raw_json)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(batch_key) DO UPDATE SET
                  total_amount=excluded.total_amount,
                  source_path=excluded.source_path,
                  updated_at=excluded.updated_at,
                  raw_json=excluded.raw_json
                """,
                (
                    batch_key,
                    "2026-07 发票报销拆分",
                    "soundwave",
                    str(path),
                    total,
                    "confirmed",
                    "2026-07-06" if "2026-07-06" in text else now,
                    now,
                    now,
                    json.dumps({"projects": projects, "items": items}, ensure_ascii=False),
                ),
            )
            for project in projects:
                conn.execute(
                    """
                    INSERT INTO finance_projects(batch_key,project_key,name,amount,note,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(batch_key,project_key) DO UPDATE SET
                      name=excluded.name, amount=excluded.amount, updated_at=excluded.updated_at
                    """,
                    (batch_key, project["key"], project["name"], project["amount"], "", now, now),
                )
            for item in items:
                budget_category = self._classify_budget_category(f"{item['note']} {item['vendor']}")
                conn.execute(
                    """
                    INSERT INTO finance_items(batch_key,item_key,project_key,vendor,invoice_no,expense_date,category,amount,note,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(batch_key,item_key) DO UPDATE SET
                      vendor=excluded.vendor, amount=excluded.amount, note=excluded.note, updated_at=excluded.updated_at
                    """,
                    (batch_key, item["key"], DEFAULT_BUDGET_PROJECT_KEY, item["vendor"], item["invoice"], "", budget_category, item["amount"], item["note"], now, now),
                )
            self._upsert_reimbursement_from_batch(conn, batch_key, path, total, projects, items, now)
        return {"status": "synced", "source": str(path), "batch_key": batch_key, "projects": len(projects), "items": len(items), "total_amount": total}

    def sync_obsidian(self) -> dict[str, Any]:
        root = _finance_root()
        expense_dir = _expense_dir()
        if not expense_dir.exists():
            return {"status": "missing", "source": str(expense_dir)}
        count = 0
        now = _now()
        with self.connect() as conn:
            for path in expense_dir.glob("*.md"):
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                meta = _parse_frontmatter(text)
                expense_key = str(meta.get("支出单号") or meta.get("发票 ID") or path.stem).strip()
                if not expense_key:
                    continue
                raw_date = meta.get("支出日期") or meta.get("开票日期")
                raw_amount = meta.get("支出金额")
                expense_date = _date(raw_date)
                amount = _money(raw_amount)
                project_name = _clean_text(meta.get("项目名称")) or "未归属项目"
                category = _clean_text(meta.get("支出类型")) or "未分类"
                quality_issues = self._expense_quality_issues(
                    expense_date=expense_date,
                    amount=amount,
                    raw_amount=raw_amount,
                    project_name=project_name,
                    category=category,
                )
                needs_review = 1 if quality_issues else 0
                data_quality = "needs_review" if quality_issues else "complete"
                conn.execute(
                    """
                    INSERT INTO finance_expenses(expense_key,invoice_id,project_name,project_code,expense_date,month,amount,amount_label,category,handler,archived_at,source,source_path,mtime,data_quality,quality_issues,needs_review,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(expense_key) DO UPDATE SET
                      invoice_id=excluded.invoice_id,
                      project_name=excluded.project_name,
                      project_code=excluded.project_code,
                      expense_date=excluded.expense_date,
                      month=excluded.month,
                      amount=excluded.amount,
                      amount_label=excluded.amount_label,
                      category=excluded.category,
                      handler=excluded.handler,
                      archived_at=excluded.archived_at,
                      source_path=excluded.source_path,
                      mtime=excluded.mtime,
                      data_quality=excluded.data_quality,
                      quality_issues=excluded.quality_issues,
                      needs_review=excluded.needs_review,
                      updated_at=excluded.updated_at
                    """,
                    (
                        expense_key,
                        _clean_text(meta.get("发票 ID")) or expense_key,
                        project_name,
                        _clean_text(meta.get("项目编号")),
                        expense_date,
                        _month(expense_date),
                        amount,
                        str(meta.get("支出金额") or f"¥ {amount:.2f}").strip(),
                        category,
                        _clean_text(meta.get("经办人")),
                        _clean_text(meta.get("归档时间")),
                        "Obsidian 财务库 / 感知器归档",
                        _relative(path, root),
                        path.stat().st_mtime,
                        data_quality,
                        json.dumps(quality_issues, ensure_ascii=False),
                        needs_review,
                        now,
                        now,
                    ),
                )
                count += 1
        return {"status": "synced", "source": str(expense_dir), "records": count}

    def summary(self, limit: int = 120) -> dict[str, Any]:
        self.sync_sources(record_audit=False)
        self.refresh_budget_spending()
        with self.connect() as conn:
            batch = self._one(conn, "SELECT * FROM finance_batches WHERE batch_key=? ORDER BY updated_at DESC", ("soundwave-2026-07-05",))
            projects = self._all(conn, "SELECT name, amount, 1 AS count FROM finance_projects WHERE batch_key=? ORDER BY amount DESC", ("soundwave-2026-07-05",))
            items = self._all(conn, "SELECT item_key AS invoice, vendor, amount, note FROM finance_items WHERE batch_key=? ORDER BY id", ("soundwave-2026-07-05",))
            records = self._all(
                conn,
                """
                SELECT
                  expense_key AS id,
                  invoice_id,
                  project_name,
                  project_code,
                  expense_date AS date,
                  month,
                  amount,
                  amount_label,
                  category,
                  handler,
                  archived_at,
                  source,
                  source_path AS path,
                  data_quality,
                  quality_issues,
                  needs_review
                FROM finance_expenses
                ORDER BY expense_date DESC, expense_key DESC
                LIMIT ?
                """,
                (limit,),
            )
            project_groups = self._all(conn, "SELECT project_name AS name, COUNT(*) AS count, ROUND(SUM(amount),2) AS amount FROM finance_expenses GROUP BY project_name ORDER BY amount DESC")
            category_groups = self._all(conn, "SELECT category AS name, COUNT(*) AS count, ROUND(SUM(amount),2) AS amount FROM finance_expenses GROUP BY category ORDER BY amount DESC")
            month_groups = self._all(conn, "SELECT month AS name, COUNT(*) AS count, ROUND(SUM(amount),2) AS amount FROM finance_expenses GROUP BY month ORDER BY name DESC")
            obsidian_total = self._scalar(conn, "SELECT ROUND(COALESCE(SUM(amount),0),2) FROM finance_expenses")
            record_count = self._scalar(conn, "SELECT COUNT(*) FROM finance_expenses")
            category_count = self._scalar(conn, "SELECT COUNT(DISTINCT category) FROM finance_expenses")
            project_count = self._scalar(conn, "SELECT COUNT(DISTINCT COALESCE(project_code, project_name)) FROM finance_expenses")
            quality = {
                "complete": self._scalar(conn, "SELECT COUNT(*) FROM finance_expenses WHERE needs_review=0"),
                "needs_review": self._scalar(conn, "SELECT COUNT(*) FROM finance_expenses WHERE needs_review=1"),
                "missing_amount": self._scalar(conn, "SELECT COUNT(*) FROM finance_expenses WHERE quality_issues LIKE '%missing_amount%'"),
                "missing_date": self._scalar(conn, "SELECT COUNT(*) FROM finance_expenses WHERE quality_issues LIKE '%missing_date%'"),
            }
            budget_projects = self._all(conn, "SELECT * FROM finance_budget_projects ORDER BY updated_at DESC, id DESC")
            budget_categories = self._all(conn, "SELECT * FROM finance_budget_categories ORDER BY project_key ASC, id ASC")
            reimbursements = self._all(
                conn,
                """
                SELECT r.*, p.name AS project_name
                FROM finance_reimbursements r
                LEFT JOIN finance_budget_projects p ON p.project_key=r.project_key
                WHERE r.total_amount > 0 OR r.reimbursement_key LIKE 'REIM-%'
                ORDER BY r.submitted_at DESC, r.updated_at DESC, r.id DESC
                """,
            )
            reimbursement_items = self._all(conn, "SELECT * FROM finance_reimbursement_items ORDER BY reimbursement_key ASC, id ASC")
            invoice_sources = self._all(conn, "SELECT * FROM finance_invoice_sources ORDER BY reimbursement_key ASC, id ASC")
            approval_events = self._all(conn, "SELECT * FROM finance_approval_events ORDER BY reimbursement_key ASC, created_at ASC, id ASC")

        active_total = float(batch["total_amount"] if batch else obsidian_total or 0)
        budget_amount = round(sum(float(project.get("budget_amount") or 0) for project in budget_projects), 2)
        budget_spent = round(sum(float(project.get("spent_amount") or 0) for project in budget_projects), 2)
        return {
            "status": "ready",
            "source": str(self.db_path),
            "generated_at": _now(),
            "openclaw": {
                "agent": "soundwave",
                "agent_label": "声波",
                "source": batch["source_path"] if batch else str(_soundwave_memory()),
                "total_amount": active_total,
                "projects": projects,
                "items": items,
                "updated_at": batch["confirmed_at"] if batch else "",
            } if batch else None,
            "summary": {
                "records": int(record_count or 0),
                "total_amount": round(active_total, 2),
                "obsidian_total_amount": float(obsidian_total or 0),
                "projects": int(project_count or 0),
                "categories": int(category_count or 0),
                "latest_amount": round(sum(float(project.get("amount") or 0) for project in projects), 2),
                "data_quality": {key: int(value or 0) for key, value in quality.items()},
            },
            "latest_reimbursements": records[:2],
            "projects": project_groups,
            "categories": category_groups,
            "monthly": month_groups,
            "records": records,
            "budget": {
                "summary": {
                    "projects": len(budget_projects),
                    "budget_amount": budget_amount,
                    "spent_amount": budget_spent,
                    "remaining_amount": round(budget_amount - budget_spent, 2),
                    "execution_percent": round((budget_spent / budget_amount) * 100, 2) if budget_amount else 0,
                },
                "projects": budget_projects,
                "categories": budget_categories,
            },
            "reimbursements": {
                "summary": {
                    "reimbursements": len(reimbursements),
                    "items": len(reimbursement_items),
                    "total_amount": round(sum(float(row.get("total_amount") or 0) for row in reimbursements), 2),
                    "confirmed": sum(1 for row in reimbursements if row.get("status") == "confirmed"),
                },
                "records": reimbursements,
                "items": reimbursement_items,
                "sources": invoice_sources,
                "events": approval_events,
            },
        }

    def record_audit(self, action: str, source: str, target_key: str, detail: Any) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO finance_audit_logs(action,source,target_key,detail_json,created_at) VALUES(?,?,?,?,?)",
                (action, source, target_key, json.dumps(detail, ensure_ascii=False), _now()),
            )

    def reimbursements_report(self, limit: int = 100) -> dict[str, Any]:
        self.ensure_schema()
        self.sync_sources(record_audit=False)
        with self.connect() as conn:
            reimbursements = self._all(
                conn,
                """
                SELECT r.*, p.name AS project_name
                FROM finance_reimbursements r
                LEFT JOIN finance_budget_projects p ON p.project_key=r.project_key
                WHERE r.total_amount > 0 OR r.reimbursement_key LIKE 'REIM-%'
                ORDER BY r.submitted_at DESC, r.updated_at DESC, r.id DESC
                LIMIT ?
                """,
                (limit,),
            )
            items = self._all(
                conn,
                """
                SELECT *
                FROM finance_reimbursement_items
                ORDER BY reimbursement_key ASC, id ASC
                """,
            )
            sources = self._all(
                conn,
                """
                SELECT *
                FROM finance_invoice_sources
                ORDER BY reimbursement_key ASC, id ASC
                """,
            )
            events = self._all(
                conn,
                """
                SELECT *
                FROM finance_approval_events
                ORDER BY reimbursement_key ASC, created_at ASC, id ASC
                """,
            )
        summary = {
            "reimbursements": len(reimbursements),
            "items": len(items),
            "total_amount": round(sum(float(row.get("total_amount") or 0) for row in reimbursements), 2),
            "confirmed": sum(1 for row in reimbursements if row.get("status") == "confirmed"),
            "pending": sum(1 for row in reimbursements if row.get("status") not in {"confirmed", "paid", "archived"}),
        }
        return {
            "status": "ready",
            "source": str(self.db_path),
            "summary": summary,
            "reimbursements": reimbursements,
            "items": items,
            "sources": sources,
            "events": events,
            "generated_at": _now(),
        }

    def _upsert_reimbursement_from_batch(
        self,
        conn: sqlite3.Connection,
        batch_key: str,
        source_path: Path,
        total: float,
        projects: list[dict[str, Any]],
        items: list[dict[str, Any]],
        now: str,
    ) -> None:
        reimbursement_key = self._reimbursement_key_for_batch(conn, batch_key)
        raw = {"batch_key": batch_key, "projects": projects, "items": items}
        conn.execute(
            """
            INSERT INTO finance_reimbursements(
              reimbursement_key,batch_key,title,project_key,source_agent,source_path,total_amount,item_count,status,
              submitted_at,confirmed_at,created_at,updated_at,raw_json
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(reimbursement_key) DO UPDATE SET
              batch_key=excluded.batch_key,
              title=excluded.title,
              project_key=excluded.project_key,
              source_agent=excluded.source_agent,
              source_path=excluded.source_path,
              total_amount=excluded.total_amount,
              item_count=excluded.item_count,
              status=excluded.status,
              submitted_at=excluded.submitted_at,
              confirmed_at=excluded.confirmed_at,
              updated_at=excluded.updated_at,
              raw_json=excluded.raw_json
            """,
            (
                reimbursement_key,
                batch_key,
                "2026-07 发票报销单",
                DEFAULT_BUDGET_PROJECT_KEY,
                "soundwave",
                str(source_path),
                total,
                len(items),
                "confirmed",
                "2026-07-06",
                "2026-07-06",
                now,
                now,
                json.dumps(raw, ensure_ascii=False),
            ),
        )
        for item in items:
            budget_category = self._classify_budget_category(f"{item['note']} {item['vendor']}")
            conn.execute(
                """
                INSERT INTO finance_reimbursement_items(
                  reimbursement_key,item_key,project_key,budget_category,vendor,invoice_no,source_type,source_ref,
                  expense_date,amount,note,status,created_at,updated_at
                )
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(reimbursement_key,item_key) DO UPDATE SET
                  project_key=excluded.project_key,
                  budget_category=excluded.budget_category,
                  vendor=excluded.vendor,
                  invoice_no=excluded.invoice_no,
                  source_type=excluded.source_type,
                  source_ref=excluded.source_ref,
                  amount=excluded.amount,
                  note=excluded.note,
                  status=excluded.status,
                  updated_at=excluded.updated_at
                """,
                (
                    reimbursement_key,
                    item["key"],
                    DEFAULT_BUDGET_PROJECT_KEY,
                    budget_category,
                    item["vendor"],
                    item["invoice"],
                    "soundwave",
                    str(source_path),
                    "",
                    item["amount"],
                    item["note"],
                    "confirmed",
                    now,
                    now,
                ),
            )
            source_key = f"{reimbursement_key}:{item['key']}:soundwave"
            conn.execute(
                """
                INSERT INTO finance_invoice_sources(
                  source_key,reimbursement_key,item_key,source_type,source_ref,file_path,email_id,scan_path,status,created_at,updated_at
                )
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(source_key) DO UPDATE SET
                  source_ref=excluded.source_ref,
                  file_path=excluded.file_path,
                  status=excluded.status,
                  updated_at=excluded.updated_at
                """,
                (
                    source_key,
                    reimbursement_key,
                    item["key"],
                    "soundwave_memory",
                    str(source_path),
                    str(source_path),
                    "",
                    "",
                    "linked",
                    now,
                    now,
                ),
            )
        conn.execute(
            """
            INSERT INTO finance_approval_events(reimbursement_key,event_type,actor,from_status,to_status,comment,created_at)
            SELECT ?,?,?,?,?,?,?
            WHERE NOT EXISTS (
              SELECT 1 FROM finance_approval_events WHERE reimbursement_key=? AND event_type='confirmed' AND actor='soundwave'
            )
            """,
            (
                reimbursement_key,
                "confirmed",
                "soundwave",
                "draft",
                "confirmed",
                "声波智能体根据发票拆分确认报销单",
                now,
                reimbursement_key,
            ),
        )

    @staticmethod
    def _reimbursement_key_for_batch(conn: sqlite3.Connection, batch_key: str) -> str:
        existing = conn.execute(
            "SELECT reimbursement_key FROM finance_reimbursements WHERE batch_key=? AND reimbursement_key LIKE 'REIM-%' LIMIT 1",
            (batch_key,),
        ).fetchone()
        if existing:
            return existing["reimbursement_key"]
        date_match = re.search(r"(20\d{2})-(\d{2})-(\d{2})", batch_key)
        year = date_match.group(1) if date_match else datetime.now().strftime("%Y")
        month = date_match.group(2) if date_match else datetime.now().strftime("%m")
        prefix = f"REIM-{year}-{month}-"
        count = conn.execute(
            "SELECT COUNT(*) FROM finance_reimbursements WHERE reimbursement_key LIKE ?",
            (f"{prefix}%",),
        ).fetchone()[0]
        return f"{prefix}{count + 1:03d}"

    def _build_enrichment_suggestions(self, row: dict[str, Any]) -> list[dict[str, Any]]:
        issues = set(json.loads(row.get("quality_issues") or "[]"))
        text = self._expense_source_text(row.get("source_path") or "")
        inference_text = self._inference_text(text)
        suggestions: list[dict[str, Any]] = []

        if "missing_date" in issues:
            date_candidates = [
                _date(match)
                for match in re.findall(r"(?:20\d{2})[./-]\d{1,2}[./-]\d{1,2}", inference_text)
            ]
            date_candidates = [candidate for candidate in date_candidates if candidate]
            if date_candidates:
                suggestions.append(self._suggestion(
                    row,
                    "expense_date",
                    date_candidates[0],
                    0.78,
                    "从原始归档正文中的日期字段提取",
                    "obsidian_markdown",
                ))
            elif row.get("archived_at"):
                suggestions.append(self._suggestion(
                    row,
                    "expense_date",
                    str(row["archived_at"])[:10],
                    0.35,
                    "源支出日期缺失，仅使用归档日期作为低置信度占位",
                    "archive_timestamp",
                ))

        if "missing_amount" in issues:
            amounts = [
                _money(match)
                for match in re.findall(r"(?:¥|￥|金额|合计|总计)?\s*[-+]?\d+(?:,\d{3})*(?:\.\d{1,2})", inference_text)
            ]
            amounts = [amount for amount in amounts if amount > 0]
            if amounts:
                suggestions.append(self._suggestion(
                    row,
                    "amount",
                    max(amounts),
                    0.72,
                    "从原始归档正文中的非零金额提取",
                    "obsidian_markdown",
                ))

        category = self._infer_category(inference_text)
        if "generic_category" in issues and category:
            suggestions.append(self._suggestion(
                row,
                "category",
                category["value"],
                category["confidence"],
                category["reason"],
                "keyword_classifier",
            ))

        if "generic_project" in issues:
            project = self._infer_project(row, text)
            if project:
                suggestions.append(self._suggestion(
                    row,
                    "project_name",
                    project["value"],
                    project["confidence"],
                    project["reason"],
                    project["source"],
                ))

        return suggestions

    def _expense_source_text(self, source_path: str) -> str:
        if not source_path:
            return ""
        path = _finance_root() / source_path
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

    @staticmethod
    def _inference_text(text: str) -> str:
        ignored_markers = (
            "归档时间",
            "来源：邮箱自动归档",
            "差旅详情",
            "启程时间",
            "抵达时间",
            "出发地点",
            "到达地点",
            "交通方式",
            "航班/车次",
            "字段 | 内容",
            "-----",
            "发票类型",
            "关联文档",
            "项目预算",
            "执行看板",
        )
        useful_lines = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line or any(marker in line for marker in ignored_markers):
                continue
            if re.search(r"\|\s*(None|N/A|na|null)\s*\|?$", line, re.IGNORECASE):
                continue
            useful_lines.append(line)
        return "\n".join(useful_lines)

    @staticmethod
    def _suggestion(
        row: dict[str, Any],
        field_name: str,
        suggested_value: Any,
        confidence: float,
        reason: str,
        source: str,
    ) -> dict[str, Any]:
        return {
            "field_name": field_name,
            "current_value": row.get(field_name),
            "suggested_value": suggested_value,
            "confidence": round(confidence, 2),
            "reason": reason,
            "source": source,
        }

    @staticmethod
    def _infer_category(text: str) -> dict[str, Any] | None:
        checks = [
            ("设备采购", ("设备", "采购", "北京奥思研工", "智能科技"), 0.82),
            ("酒店住宿", ("酒店", "住宿", "宾馆"), 0.82),
            ("交通费", ("打车", "高德", "出租", "网约车", "滴滴"), 0.8),
            ("会议费", ("会议", "会务", "注册费"), 0.8),
            ("差旅费", ("机票", "火车票", "高铁票"), 0.76),
        ]
        for value, keywords, confidence in checks:
            if any(keyword in text for keyword in keywords):
                return {
                    "value": value,
                    "confidence": confidence,
                    "reason": f"根据关键词匹配推断为{value}",
                }
        return None

    @staticmethod
    def _infer_project(row: dict[str, Any], text: str) -> dict[str, Any] | None:
        project_code = _clean_text(row.get("project_code"))
        budget_match = re.search(r"\[\[../02-项目预算/([^|\]]+)", text)
        if budget_match:
            value = budget_match.group(1).replace("-预算表", "").strip()
            if value:
                return {
                    "value": value,
                    "confidence": 0.62,
                    "reason": "从 Obsidian 关联项目预算链接提取",
                    "source": "obsidian_wikilink",
                }
        if project_code:
            return {
                "value": f"{project_code} 预算项目",
                "confidence": 0.45,
                "reason": "项目名称为泛化占位，使用项目编号生成低置信度候选",
                "source": "project_code",
            }
        return None

    @staticmethod
    def _slug(value: str) -> str:
        cleaned = re.sub(r"\s+", "-", value.strip().lower())
        return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff_-]+", "", cleaned) or "project"

    @staticmethod
    def _all(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]

    @staticmethod
    def _one(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _scalar(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> Any:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else None

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
        if column_name not in columns:
            try:
                conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise

    @staticmethod
    def _ensure_budget_seed(conn: sqlite3.Connection) -> None:
        now = _now()
        for project in DEFAULT_BUDGET_PROJECTS:
            conn.execute(
                """
                INSERT INTO finance_budget_projects(
                  project_key, name, budget_amount, allocated_amount, spent_amount, remaining_amount,
                  status, source, created_at, updated_at
                )
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(project_key) DO UPDATE SET
                  name=excluded.name,
                  budget_amount=excluded.budget_amount,
                  remaining_amount=excluded.budget_amount - finance_budget_projects.spent_amount,
                  status=excluded.status,
                  source=excluded.source,
                  updated_at=excluded.updated_at
                """,
                (
                    project["project_key"],
                    project["name"],
                    float(project["budget_amount"]),
                    0.0,
                    0.0,
                    float(project["budget_amount"]),
                    "active",
                    "manual_seed",
                    now,
                    now,
                ),
            )
            for category in DEFAULT_BUDGET_CATEGORIES:
                conn.execute(
                    """
                    INSERT INTO finance_budget_categories(
                      project_key, category, budget_amount, spent_amount, remaining_amount, note, created_at, updated_at
                    )
                    VALUES(?,?,?,?,?,?,?,?)
                    ON CONFLICT(project_key, category) DO NOTHING
                    """,
                    (
                        project["project_key"],
                        category,
                        0.0,
                        0.0,
                        0.0,
                        "预算额度待编制",
                        now,
                        now,
                    ),
                )

    @staticmethod
    def _classify_budget_category(value: str) -> str:
        text = str(value or "")
        if re.search(r"设备|采购|奥思研工|智能科技", text):
            return "设备费"
        if re.search(r"会议|会务|注册", text):
            return "会议费"
        if re.search(r"酒店|住宿|打车|高德|交通|差旅|机票|高铁|火车", text):
            return "差旅费"
        if re.search(r"外协|委托|服务", text):
            return "外协费"
        if "管理" in text:
            return "管理费"
        if re.search(r"材料|耗材", text):
            return "材料费"
        if re.search(r"劳务|专家|咨询", text):
            return "劳务费"
        return "其他"

    @staticmethod
    def _expense_quality_issues(
        *,
        expense_date: str,
        amount: float,
        raw_amount: Any,
        project_name: str,
        category: str,
    ) -> list[str]:
        issues: list[str] = []
        if not expense_date:
            issues.append("missing_date")
        if amount <= 0:
            issues.append("missing_amount")
        if not _clean_text(raw_amount):
            issues.append("missing_amount_source")
        if project_name in {"感知器归档项目", "未归属项目"}:
            issues.append("generic_project")
        if category in {"其他费用", "未分类"}:
            issues.append("generic_category")
        return issues


finance_service = FinanceService()
