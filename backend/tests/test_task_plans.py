"""
Task-Plan API 测试

单元测试和集成测试验证任务与开发计划的从属关系

@author 拉斐尔 (🐢 后端开发)
@created 2026-04-16
"""

import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from database import get_db
from models.task_plan import Base, Task, DevelopmentPlan, TaskStatusEnum, TaskPriorityEnum, PlanStatusEnum

# ============================================================================
# 测试配置
# ============================================================================

# 创建测试数据库
SQLALCHEMY_DATABASE_URL = "postgresql://test_user:test_password@localhost/test_db"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建测试客户端
@pytest.fixture
def client():
    """创建测试客户端"""
    # 创建所有表
    Base.metadata.create_all(bind=engine)
    
    def override_get_db():
        try:
            db = TestingSessionLocal()
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
    
    # 清理测试数据
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    """创建数据库会话"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# 单元测试 - 任务管理
# ============================================================================

class TestTaskManagement:
    """任务管理 API 测试"""
    
    def test_create_task(self, client):
        """测试创建任务"""
        response = client.post('/api/v1/tasks', json={
            'title': '测试任务',
            'assignee': '拉斐尔',
            'description': '这是一个测试任务',
            'priority': 'high',
            'deadline': '2026-04-20T18:00:00Z',
            'tags': ['测试', '后端'],
        })
        
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert 'data' in data
        assert data['data']['title'] == '测试任务'
        assert data['data']['assignee'] == '拉斐尔'
        assert data['data']['priority'] == 'high'
        assert data['data']['status'] == 'pending'
        assert 'id' in data['data']
    
    def test_create_task_minimal(self, client):
        """测试创建最小化任务"""
        response = client.post('/api/v1/tasks', json={
            'title': '最小化任务',
            'assignee': '测试员',
        })
        
        assert response.status_code == 201
        data = response.json()
        assert data['data']['title'] == '最小化任务'
        assert data['data']['priority'] == 'normal'
        assert data['data']['status'] == 'pending'
    
    def test_create_task_invalid_priority(self, client):
        """测试创建任务 - 无效优先级"""
        response = client.post('/api/v1/tasks', json={
            'title': '测试任务',
            'assignee': '拉斐尔',
            'priority': 'invalid_priority',
        })
        
        assert response.status_code == 400
    
    def test_get_task(self, client, db):
        """测试获取任务详情"""
        # 创建测试任务
        task = Task(
            id='20260416-TEST',
            title='测试任务',
            assignee='拉斐尔',
            creator='测试员',
            priority=TaskPriorityEnum.NORMAL,
        )
        db.add(task)
        db.commit()
        
        response = client.get('/api/v1/tasks/20260416-TEST')
        
        assert response.status_code == 200
        data = response.json()
        assert data['data']['id'] == '20260416-TEST'
        assert data['data']['title'] == '测试任务'
    
    def test_get_task_not_found(self, client):
        """测试获取不存在的任务"""
        response = client.get('/api/v1/tasks/nonexistent')
        
        assert response.status_code == 404
    
    def test_update_task(self, client, db):
        """测试更新任务"""
        # 创建测试任务
        task = Task(
            id='20260416-TEST2',
            title='原任务标题',
            assignee='拉斐尔',
            creator='测试员',
            priority=TaskPriorityEnum.NORMAL,
            status=TaskStatusEnum.PENDING,
        )
        db.add(task)
        db.commit()
        
        response = client.put('/api/v1/tasks/20260416-TEST2', json={
            'title': '更新后的标题',
            'status': 'in_progress',
            'progress': 50,
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data['data']['title'] == '更新后的标题'
        assert data['data']['status'] == 'in_progress'
        assert data['data']['progress'] == 50
    
    def test_update_task_invalid_status_transition(self, client, db):
        """测试更新任务 - 无效状态转换"""
        # 创建已完成的任务
        task = Task(
            id='20260416-TEST3',
            title='已完成任务',
            assignee='拉斐尔',
            creator='测试员',
            priority=TaskPriorityEnum.NORMAL,
            status=TaskStatusEnum.COMPLETED,
        )
        db.add(task)
        db.commit()
        
        response = client.put('/api/v1/tasks/20260416-TEST3', json={
            'status': 'pending',
        })
        
        assert response.status_code == 400
    
    def test_delete_task(self, client, db):
        """测试删除任务"""
        # 创建测试任务
        task = Task(
            id='20260416-TEST4',
            title='待删除任务',
            assignee='拉斐尔',
            creator='测试员',
        )
        db.add(task)
        db.commit()
        
        response = client.delete('/api/v1/tasks/20260416-TEST4')
        
        assert response.status_code == 204
        
        # 验证任务已删除
        assert db.query(Task).filter(Task.id == '20260416-TEST4').first() is None
    
    def test_list_tasks(self, client, db):
        """测试查询任务列表"""
        # 创建多个测试任务
        for i in range(5):
            task = Task(
                id=f'20260416-TEST{i}',
                title=f'测试任务{i}',
                assignee='拉斐尔',
                creator='测试员',
                priority=TaskPriorityEnum.NORMAL,
            )
            db.add(task)
        db.commit()
        
        response = client.get('/api/v1/tasks?limit=3&offset=0')
        
        assert response.status_code == 200
        data = response.json()
        assert len(data['data']['tasks']) == 3
        assert data['data']['pagination']['total'] == 5
        assert data['data']['pagination']['has_more'] is True
    
    def test_list_tasks_filter_by_status(self, client, db):
        """测试按状态过滤任务"""
        # 创建不同状态的任务
        task1 = Task(id='20260416-A', title='任务 A', assignee='拉斐尔', creator='测试员', status=TaskStatusEnum.PENDING)
        task2 = Task(id='20260416-B', title='任务 B', assignee='拉斐尔', creator='测试员', status=TaskStatusEnum.IN_PROGRESS)
        task3 = Task(id='20260416-C', title='任务 C', assignee='拉斐尔', creator='测试员', status=TaskStatusEnum.IN_PROGRESS)
        db.add_all([task1, task2, task3])
        db.commit()
        
        response = client.get('/api/v1/tasks?status=in_progress')
        
        assert response.status_code == 200
        data = response.json()
        assert len(data['data']['tasks']) == 2


# ============================================================================
# 单元测试 - 开发计划管理
# ============================================================================

class TestPlanManagement:
    """开发计划管理 API 测试"""
    
    def test_create_plan(self, client, db):
        """测试创建开发计划"""
        # 先创建任务
        task = Task(
            id='20260416-PLAN-TEST',
            title='测试任务',
            assignee='拉斐尔',
            creator='测试员',
        )
        db.add(task)
        db.commit()
        
        response = client.post('/api/v1/plans', json={
            'task_id': '20260416-PLAN-TEST',
            'title': '测试计划',
            'type': 'backend',
            'steps': [
                {'index': 0, 'name': '需求分析', 'estimatedHours': 2},
                {'index': 1, 'name': '实现', 'estimatedHours': 8},
            ],
        })
        
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['data']['task_id'] == '20260416-PLAN-TEST'
        assert data['data']['type'] == 'backend'
        assert data['data']['status'] == 'pending_review'
        assert data['data']['estimated_total_hours'] == 10
    
    def test_create_plan_task_not_found(self, client):
        """测试创建计划 - 任务不存在"""
        response = client.post('/api/v1/plans', json={
            'task_id': 'nonexistent',
            'title': '测试计划',
            'type': 'backend',
        })
        
        assert response.status_code == 404
    
    def test_create_plan_invalid_type(self, client, db):
        """测试创建计划 - 无效类型"""
        task = Task(id='20260416-PLAN-TEST2', title='测试任务', assignee='拉斐尔', creator='测试员')
        db.add(task)
        db.commit()
        
        response = client.post('/api/v1/plans', json={
            'task_id': '20260416-PLAN-TEST2',
            'title': '测试计划',
            'type': 'invalid_type',
        })
        
        assert response.status_code == 400
    
    def test_get_plan(self, client, db):
        """测试获取计划详情"""
        # 创建任务和计划
        task = Task(id='20260416-PLAN-TEST3', title='测试任务', assignee='拉斐尔', creator='测试员')
        plan = DevelopmentPlan(
            id='plan_test_001',
            task_id='20260416-PLAN-TEST3',
            title='测试计划',
            type=PlanTypeEnum.BACKEND,
            creator='测试员',
        )
        db.add_all([task, plan])
        db.commit()
        
        response = client.get('/api/v1/plans/plan_test_001')
        
        assert response.status_code == 200
        data = response.json()
        assert data['data']['id'] == 'plan_test_001'
        assert data['data']['title'] == '测试计划'
    
    def test_get_plan_not_found(self, client):
        """测试获取不存在的计划"""
        response = client.get('/api/v1/plans/nonexistent')
        
        assert response.status_code == 404
    
    def test_update_plan(self, client, db):
        """测试更新计划"""
        task = Task(id='20260416-PLAN-TEST4', title='测试任务', assignee='拉斐尔', creator='测试员')
        plan = DevelopmentPlan(
            id='plan_test_002',
            task_id='20260416-PLAN-TEST4',
            title='原计划标题',
            type=PlanTypeEnum.BACKEND,
            status=PlanStatusEnum.DRAFT,
            creator='测试员',
        )
        db.add_all([task, plan])
        db.commit()
        
        response = client.put('/api/v1/plans/plan_test_002', json={
            'title': '更新后的标题',
            'status': 'pending_review',
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data['data']['title'] == '更新后的标题'
        assert data['data']['status'] == 'pending_review'
    
    def test_update_plan_invalid_status_transition(self, client, db):
        """测试更新计划 - 无效状态转换"""
        task = Task(id='20260416-PLAN-TEST5', title='测试任务', assignee='拉斐尔', creator='测试员')
        plan = DevelopmentPlan(
            id='plan_test_003',
            task_id='20260416-PLAN-TEST5',
            title='测试计划',
            type=PlanTypeEnum.BACKEND,
            status=PlanStatusEnum.COMPLETED,
            creator='测试员',
        )
        db.add_all([task, plan])
        db.commit()
        
        response = client.put('/api/v1/plans/plan_test_003', json={
            'status': 'pending_review',
        })
        
        assert response.status_code == 400
    
    def test_delete_plan(self, client, db):
        """测试删除计划"""
        task = Task(id='20260416-PLAN-TEST6', title='测试任务', assignee='拉斐尔', creator='测试员')
        plan = DevelopmentPlan(
            id='plan_test_004',
            task_id='20260416-PLAN-TEST6',
            title='待删除计划',
            type=PlanTypeEnum.BACKEND,
            creator='测试员',
        )
        db.add_all([task, plan])
        db.commit()
        
        response = client.delete('/api/v1/plans/plan_test_004')
        
        assert response.status_code == 204
    
    def test_list_plans(self, client, db):
        """测试查询计划列表"""
        task = Task(id='20260416-PLAN-TEST7', title='测试任务', assignee='拉斐尔', creator='测试员')
        db.add(task)
        
        for i in range(5):
            plan = DevelopmentPlan(
                id=f'plan_test_{i:03d}',
                task_id='20260416-PLAN-TEST7',
                title=f'测试计划{i}',
                type=PlanTypeEnum.BACKEND,
                creator='测试员',
            )
            db.add(plan)
        db.commit()
        
        response = client.get('/api/v1/plans?task_id=20260416-PLAN-TEST7&limit=3')
        
        assert response.status_code == 200
        data = response.json()
        assert len(data['data']['plans']) == 3
        assert data['data']['pagination']['total'] == 5


# ============================================================================
# 集成测试 - 从属关系
# ============================================================================

class TestTaskPlanRelation:
    """任务 - 计划从属关系集成测试"""
    
    def test_get_task_with_plans(self, client, db):
        """测试获取任务及其关联计划"""
        # 创建任务
        task = Task(
            id='20260416-REL-TEST',
            title='测试任务',
            assignee='拉斐尔',
            creator='测试员',
        )
        db.add(task)
        
        # 创建多个计划
        for i in range(3):
            plan = DevelopmentPlan(
                id=f'plan_rel_{i:03d}',
                task_id='20260416-REL-TEST',
                title=f'测试计划{i}',
                type=PlanTypeEnum.BACKEND,
                version=i+1,
                creator='测试员',
            )
            db.add(plan)
        
        db.commit()
        
        response = client.get('/api/v1/tasks/20260416-REL-TEST?include_plans=true')
        
        assert response.status_code == 200
        data = response.json()
        assert len(data['data']['plans']) == 3
    
    def test_get_task_plans(self, client, db):
        """测试获取任务的所有计划"""
        task = Task(id='20260416-REL-TEST2', title='测试任务', assignee='拉斐尔', creator='测试员')
        db.add(task)
        
        plan1 = DevelopmentPlan(id='plan_rel_a', task_id='20260416-REL-TEST2', title='计划 A', type=PlanTypeEnum.BACKEND, creator='测试员', status=PlanStatusEnum.DRAFT)
        plan2 = DevelopmentPlan(id='plan_rel_b', task_id='20260416-REL-TEST2', title='计划 B', type=PlanTypeEnum.BACKEND, creator='测试员', status=PlanStatusEnum.APPROVED)
        db.add_all([plan1, plan2])
        db.commit()
        
        response = client.get('/api/v1/tasks/20260416-REL-TEST2/plans')
        
        assert response.status_code == 200
        data = response.json()
        assert data['data']['total'] == 2
        assert len(data['data']['plans']) == 2
    
    def test_create_task_plan(self, client, db):
        """测试为任务创建新计划"""
        task = Task(id='20260416-REL-TEST3', title='测试任务', assignee='拉斐尔', creator='测试员')
        db.add(task)
        db.commit()
        
        response = client.post('/api/v1/tasks/20260416-REL-TEST3/plans', json={
            'title': '新创建的计划',
            'type': 'backend',
            'steps': [{'index': 0, 'name': '步骤 1', 'estimatedHours': 5}],
        })
        
        assert response.status_code == 201
        data = response.json()
        assert data['data']['task_id'] == '20260416-REL-TEST3'
        assert data['data']['title'] == '新创建的计划'
    
    def test_set_active_plan(self, client, db):
        """测试激活计划"""
        # 创建任务和计划
        task = Task(id='20260416-REL-TEST4', title='测试任务', assignee='拉斐尔', creator='测试员')
        plan = DevelopmentPlan(
            id='plan_rel_active',
            task_id='20260416-REL-TEST4',
            title='测试计划',
            type=PlanTypeEnum.BACKEND,
            status=PlanStatusEnum.APPROVED,
            creator='测试员',
        )
        db.add_all([task, plan])
        db.commit()
        
        response = client.post('/api/v1/tasks/20260416-REL-TEST4/active_plan?plan_id=plan_rel_active')
        
        assert response.status_code == 200
        data = response.json()
        assert data['data']['active_plan_id'] == 'plan_rel_active'
        
        # 验证任务已更新
        db.refresh(task)
        assert task.active_plan_id == 'plan_rel_active'
    
    def test_set_active_plan_not_approved(self, client, db):
        """测试激活未通过审核的计划"""
        task = Task(id='20260416-REL-TEST5', title='测试任务', assignee='拉斐尔', creator='测试员')
        plan = DevelopmentPlan(
            id='plan_rel_not_approved',
            task_id='20260416-REL-TEST5',
            title='测试计划',
            type=PlanTypeEnum.BACKEND,
            status=PlanStatusEnum.DRAFT,  # 未审核状态
            creator='测试员',
        )
        db.add_all([task, plan])
        db.commit()
        
        response = client.post('/api/v1/tasks/20260416-REL-TEST5/active_plan?plan_id=plan_rel_not_approved')
        
        assert response.status_code == 400
    
    def test_review_plan_approve(self, client, db):
        """测试审核计划 - 通过"""
        task = Task(id='20260416-REL-TEST6', title='测试任务', assignee='拉斐尔', creator='测试员')
        plan = DevelopmentPlan(
            id='plan_rel_review',
            task_id='20260416-REL-TEST6',
            title='测试计划',
            type=PlanTypeEnum.BACKEND,
            status=PlanStatusEnum.PENDING_REVIEW,
            creator='测试员',
        )
        db.add_all([task, plan])
        db.commit()
        
        response = client.post('/api/v1/plans/plan_rel_review/review?approved=true&comment=通过审核')
        
        assert response.status_code == 200
        data = response.json()
        assert data['data']['status'] == 'approved'
        assert data['data']['review_comment'] == '通过审核'
        
        db.refresh(plan)
        assert plan.status == PlanStatusEnum.APPROVED
    
    def test_review_plan_reject(self, client, db):
        """测试审核计划 - 拒绝"""
        task = Task(id='20260416-REL-TEST7', title='测试任务', assignee='拉斐尔', creator='测试员')
        plan = DevelopmentPlan(
            id='plan_rel_reject',
            task_id='20260416-REL-TEST7',
            title='测试计划',
            type=PlanTypeEnum.BACKEND,
            status=PlanStatusEnum.PENDING_REVIEW,
            creator='测试员',
        )
        db.add_all([task, plan])
        db.commit()
        
        response = client.post('/api/v1/plans/plan_rel_reject/review?approved=false&rejection_reason=方案不完整')
        
        assert response.status_code == 200
        data = response.json()
        assert data['data']['status'] == 'rejected'
        assert data['data']['rejection_reason'] == '方案不完整'
    
    def test_get_plan_progress(self, client, db):
        """测试获取计划进度"""
        task = Task(id='20260416-REL-TEST8', title='测试任务', assignee='拉斐尔', creator='测试员')
        plan = DevelopmentPlan(
            id='plan_rel_progress',
            task_id='20260416-REL-TEST8',
            title='测试计划',
            type=PlanTypeEnum.BACKEND,
            creator='测试员',
            steps=[
                {'index': 0, 'name': '步骤 1', 'status': 'completed', 'estimatedHours': 2},
                {'index': 1, 'name': '步骤 2', 'status': 'in_progress', 'estimatedHours': 3},
                {'index': 2, 'name': '步骤 3', 'status': 'pending', 'estimatedHours': 5},
            ],
            estimated_total_hours=10,
        )
        db.add_all([task, plan])
        db.commit()
        
        response = client.get('/api/v1/plans/plan_rel_progress/progress')
        
        assert response.status_code == 200
        data = response.json()
        assert data['data']['total_steps'] == 3
        assert data['data']['completed_steps'] == 1
        assert data['data']['progress_percentage'] == 33.33
        assert data['data']['current_step_index'] == 1
        assert data['data']['estimated_remaining_hours'] == 8
    
    def test_execute_plan_step(self, client, db):
        """测试执行计划步骤"""
        task = Task(id='20260416-REL-TEST9', title='测试任务', assignee='拉斐尔', creator='测试员')
        plan = DevelopmentPlan(
            id='plan_rel_step',
            task_id='20260416-REL-TEST9',
            title='测试计划',
            type=PlanTypeEnum.BACKEND,
            creator='测试员',
            steps=[
                {'index': 0, 'name': '步骤 1', 'status': 'pending', 'estimatedHours': 2},
            ],
        )
        db.add_all([task, plan])
        db.commit()
        
        response = client.post('/api/v1/plans/plan_rel_step/steps/0/execute', json={
            'status': 'completed',
            'output': '步骤 1 已完成',
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data['data']['status'] == 'completed'
        assert data['data']['output'] == '步骤 1 已完成'
        
        db.refresh(plan)
        assert plan.steps[0]['status'] == 'completed'


# ============================================================================
# 错误处理测试
# ============================================================================

class TestErrorHandling:
    """错误处理测试"""
    
    def test_task_not_found(self, client):
        """测试任务不存在错误"""
        response = client.get('/api/v1/tasks/nonexistent')
        assert response.status_code == 404
        data = response.json()
        assert 'detail' in data
    
    def test_plan_not_found(self, client):
        """测试计划不存在错误"""
        response = client.get('/api/v1/plans/nonexistent')
        assert response.status_code == 404
    
    def test_invalid_parameter(self, client):
        """测试无效参数错误"""
        response = client.get('/api/v1/tasks?status=invalid_status')
        assert response.status_code == 400
    
    def test_validation_error(self, client):
        """测试验证错误"""
        response = client.post('/api/v1/tasks', json={
            # 缺少必填字段
            'assignee': '拉斐尔',
        })
        assert response.status_code == 422  # FastAPI 验证错误


# ============================================================================
# 运行测试
# ============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
