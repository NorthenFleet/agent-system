"""
数据库配置和连接管理

使用 SQLAlchemy 管理任务计划数据库连接

@author 拉斐尔 (🐢 后端开发)
@created 2026-04-16
"""

import os
from sqlalchemy import create_engine, inspect, text
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
    os.makedirs(os.path.dirname(DEFAULT_SQLITE_PATH), exist_ok=True)
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
        echo=False,
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,  # 连接前测试
        pool_size=10,  # 连接池大小
        max_overflow=20,  # 最大溢出连接数
        echo=False,  # 是否打印 SQL 日志
    )

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


def ensure_db_initialized():
    global _initialized
    if _initialized:
        return
    from models.task_plan import Base as TaskPlanBase

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
    from models.task_plan import Base as TaskPlanBase
    
    # 创建所有表
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
