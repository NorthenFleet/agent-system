"""
TaskTemplate Repository — 任务模板表数据访问
"""
from typing import Optional
from sqlalchemy.orm import Session

from repositories.base import BaseRepository
from models.v2_models import TaskTemplate


class TaskTemplateRepository(BaseRepository[TaskTemplate]):
    def __init__(self):
        super().__init__(TaskTemplate)

    def get_by_name(self, db: Session, name: str) -> Optional[TaskTemplate]:
        return db.query(TaskTemplate).filter(TaskTemplate.name == name).first()
