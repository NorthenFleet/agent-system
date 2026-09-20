from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.v2_models import Base, Notification, User
from services.memory_release_notifications import publish_memory_release_notification


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(
        User(
            username="admin",
            password_hash="not-used",
            display_name="管理员",
            role="admin",
            is_active=True,
        )
    )
    session.commit()
    return session


def test_release_failure_notification_is_fanned_out_and_deduplicated():
    session = _session()
    execution = {
        "release_id": "release-failed",
        "version": "2026.09.18.5",
        "status": "rolled_back",
        "completed_at": "2026-09-18T03:00:00+00:00",
    }

    published = publish_memory_release_notification(session, execution)
    duplicate = publish_memory_release_notification(session, execution)

    assert published["status"] == "published"
    assert published["notifications_created"] == 1
    assert duplicate["status"] == "duplicate"
    notification = session.query(Notification).one()
    assert notification.type == "alert"
    assert notification.title == "记忆系统发布已自动回滚"
    assert notification.source_id.startswith("memory-release:release-failed:rolled_back:")
    session.close()


def test_successful_release_does_not_create_notification_noise():
    session = _session()

    result = publish_memory_release_notification(
        session,
        {"release_id": "release-success", "status": "verified_noop"},
    )

    assert result["status"] == "not_applicable"
    assert session.query(Notification).count() == 0
    session.close()
