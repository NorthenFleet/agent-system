from sqlalchemy.orm import configure_mappers
from sqlalchemy import create_engine

from models.task_plan import Base, DevelopmentPlan, Task


def test_task_plan_relationships_disambiguate_multiple_foreign_keys():
    configure_mappers()

    task_plan_fk = {column.name for column in Task.plans.property.local_remote_pairs[0]}
    active_plan_fk = {column.name for column in Task.active_plan.property.local_remote_pairs[0]}
    plan_task_fk = {column.name for column in DevelopmentPlan.task.property.local_remote_pairs[0]}

    assert task_plan_fk == {"id", "task_id"}
    assert active_plan_fk == {"active_plan_id", "id"}
    assert plan_task_fk == {"task_id", "id"}


def test_task_plan_models_create_on_sqlite():
    engine = create_engine("sqlite:///:memory:")

    Base.metadata.create_all(bind=engine)

    table_names = set(Base.metadata.tables)
    assert {"tasks", "plans", "plan_steps", "task_plans"}.issubset(table_names)
