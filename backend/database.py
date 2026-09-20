"""
数据库配置和连接管理

使用 SQLAlchemy 管理任务计划数据库连接

@author 拉斐尔 (🐢 后端开发)
@created 2026-04-16
"""

import logging
import os
import time
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DEFAULT_SQLITE_PATH = os.path.join(os.path.dirname(__file__), "data", "dashboard_v2.db")

# 从环境变量读取数据库连接配置；未配置时使用本地 SQLite，保证看板自包含可运行。
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{DEFAULT_SQLITE_PATH}"
)

# 创建数据库引擎
if DATABASE_URL.startswith("sqlite"):
    configured_path = make_url(DATABASE_URL).database
    if configured_path and configured_path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(configured_path)), exist_ok=True)
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False, "timeout": 30},
        pool_pre_ping=True,
        echo=False,
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,  # 连接前测试
        pool_size=10,  # 连接池大小
        max_overflow=20,  # 最大溢出连接数
        pool_timeout=int(os.getenv("DATABASE_POOL_TIMEOUT", "30")),
        pool_recycle=int(os.getenv("DATABASE_POOL_RECYCLE", "1800")),
        echo=False,  # 是否打印 SQL 日志
    )


logger = logging.getLogger("database.performance")
SLOW_QUERY_SECONDS = float(os.getenv("DATABASE_SLOW_QUERY_SECONDS", "0.5"))


@event.listens_for(engine, "connect")
def _configure_connection(dbapi_connection, _connection_record):
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
        finally:
            cursor.close()


@event.listens_for(engine, "before_cursor_execute")
def _query_started(_conn, _cursor, _statement, _parameters, context, _executemany):
    context._query_started_at = time.monotonic()


@event.listens_for(engine, "after_cursor_execute")
def _query_finished(_conn, _cursor, statement, _parameters, context, _executemany):
    elapsed = time.monotonic() - getattr(context, "_query_started_at", time.monotonic())
    if elapsed >= SLOW_QUERY_SECONDS:
        # Never log parameters: finance queries may contain invoice or account data.
        logger.warning("slow query duration=%.3fs operation=%s", elapsed, statement.lstrip().split(None, 1)[0][:16])

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建基类
Base = declarative_base()

_initialized = False


def ensure_v2_schema_compatibility():
    """Keep the existing SQLite store compatible with the current v2 ORM models."""
    if not DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)
    if "agents" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("agents")}
    statements = []
    if "agent_id" not in columns:
        statements.append("ALTER TABLE agents ADD COLUMN agent_id VARCHAR(64)")
    if "capabilities" not in columns:
        statements.append("ALTER TABLE agents ADD COLUMN capabilities JSON DEFAULT '[]'")
    if "model_name" not in columns:
        statements.append("ALTER TABLE agents ADD COLUMN model_name VARCHAR(128)")
    if "current_task" not in columns:
        statements.append("ALTER TABLE agents ADD COLUMN current_task VARCHAR(500)")
    if "avatar_url" not in columns:
        statements.append("ALTER TABLE agents ADD COLUMN avatar_url VARCHAR(500)")
    if "last_heartbeat" not in columns:
        statements.append("ALTER TABLE agents ADD COLUMN last_heartbeat DATETIME")
    if "last_heartbeat_at" not in columns:
        statements.append("ALTER TABLE agents ADD COLUMN last_heartbeat_at DATETIME")

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
        refreshed_columns = columns | {
            statement.split(" ADD COLUMN ", 1)[1].split(" ", 1)[0]
            for statement in statements
            if " ADD COLUMN " in statement
        }
        if "agent_id" in refreshed_columns:
            conn.execute(text("UPDATE agents SET agent_id = name WHERE agent_id IS NULL OR agent_id = ''"))
        if "last_heartbeat_at" in columns and "last_heartbeat" not in columns:
            conn.execute(text(
                "UPDATE agents SET last_heartbeat = last_heartbeat_at "
                "WHERE last_heartbeat IS NULL AND last_heartbeat_at IS NOT NULL"
            ))
        if "last_heartbeat" in columns and "last_heartbeat_at" not in columns:
            conn.execute(text(
                "UPDATE agents SET last_heartbeat_at = last_heartbeat "
                "WHERE last_heartbeat_at IS NULL AND last_heartbeat IS NOT NULL"
            ))


def ensure_task_table_ownership_compatibility(target_engine=None):
    """Separate the legacy planning aggregate from the canonical task ledger.

    Older SQLite boot order allowed ``models.task_plan.Task`` to create a
    structurally incompatible table named ``tasks`` before the V2 ledger.  The
    migration is lossless: the old table and any incompatible dependent audit
    tables are renamed, after which V2 metadata can create its canonical tables.
    """

    selected_engine = target_engine or engine
    if selected_engine.dialect.name != "sqlite":
        return False
    inspector = inspect(selected_engine)
    tables = set(inspector.get_table_names())
    legacy_dependents = {
        "legacy_incompatible_task_history",
        "legacy_incompatible_task_comments",
    }
    with selected_engine.begin() as conn:
        for table_name in sorted(legacy_dependents & tables):
            indexes = conn.execute(
                text(f'PRAGMA index_list("{table_name}")')
            ).fetchall()
            for index in indexes:
                index_name = str(index[1])
                if index_name.startswith("sqlite_autoindex"):
                    continue
                safe_name = index_name.replace('"', '""')
                conn.execute(text(f'DROP INDEX IF EXISTS "{safe_name}"'))
    if "tasks" not in tables:
        return False
    columns = {column["name"] for column in inspector.get_columns("tasks")}
    if "task_id" in columns:
        return False
    if "active_plan_id" not in columns:
        raise RuntimeError(
            "tasks table is neither the canonical ledger nor the known legacy plan schema"
        )
    if "legacy_plan_tasks" in tables:
        raise RuntimeError(
            "cannot migrate legacy tasks: legacy_plan_tasks already exists"
        )

    with selected_engine.begin() as conn:
        conn.execute(text("ALTER TABLE tasks RENAME TO legacy_plan_tasks"))
        for dependent in ("task_history", "task_comments"):
            if dependent not in tables:
                continue
            target = f"legacy_incompatible_{dependent}"
            if target in tables:
                raise RuntimeError(f"cannot preserve {dependent}: {target} already exists")
            conn.execute(text(f"ALTER TABLE {dependent} RENAME TO {target}"))
            indexes = conn.execute(text(f'PRAGMA index_list("{target}")')).fetchall()
            for index in indexes:
                index_name = str(index[1])
                if index_name.startswith("sqlite_autoindex"):
                    continue
                safe_name = index_name.replace('"', '""')
                conn.execute(text(f'DROP INDEX IF EXISTS "{safe_name}"'))
    logger.warning(
        "migrated legacy planning tasks to legacy_plan_tasks; canonical tasks will be recreated"
    )
    return True


def ensure_db_initialized():
    global _initialized
    if _initialized:
        return
    if DATABASE_URL.startswith("sqlite"):
        # SQLite remains a self-contained development/test option. Production
        # PostgreSQL schemas are owned exclusively by Alembic.
        from models import v2_models  # noqa: F401 - register V2 metadata
        from models.task_plan import Base as TaskPlanBase
        from models import writing_collaboration  # noqa: F401

        ensure_task_table_ownership_compatibility()
        Base.metadata.create_all(bind=engine)
        TaskPlanBase.metadata.create_all(bind=engine)
        ensure_v2_schema_compatibility()
    _initialized = True


def get_db():
    """
    获取数据库会话的依赖注入函数
    
    用法:
        @app.get("/example")
        def example(db: Session = Depends(get_db)):
            ...
    """
    ensure_db_initialized()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    初始化数据库，创建所有表
    
    注意：生产环境应使用 Alembic 进行数据库迁移
    """
    from models import v2_models  # noqa: F401 - register V2 metadata
    from models.task_plan import Base as TaskPlanBase
    from models import writing_collaboration  # noqa: F401
    
    # 创建所有表
    if DATABASE_URL.startswith("sqlite"):
        ensure_task_table_ownership_compatibility()
        Base.metadata.create_all(bind=engine)
        TaskPlanBase.metadata.create_all(bind=engine)
    ensure_v2_schema_compatibility()
    print("数据库表已创建")


if __name__ == "__main__":
    # 测试数据库连接
    try:
        connection = engine.connect()
        print("数据库连接成功!")
        connection.close()
        
        # 初始化数据库
        init_db()
        
    except Exception as e:
        print(f"数据库连接失败：{e}")
