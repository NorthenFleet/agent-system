"""Add the persistent dual-pane writing workbench.

Revision ID: 20260808_writing_workbench_v2
Revises: 20260808_invoice_batch_ingestion
"""

from alembic import op
import sqlalchemy as sa


revision = "20260808_writing_workbench_v2"
down_revision = "20260808_invoice_batch_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("writing_ai_jobs", sa.Column("conversation_id", sa.String(64), nullable=False, server_default=""))
    op.add_column("writing_ai_jobs", sa.Column("request_message_id", sa.String(64), nullable=False, server_default=""))
    op.add_column("writing_ai_jobs", sa.Column("response_message_id", sa.String(64), nullable=False, server_default=""))
    op.create_index("ix_writing_ai_jobs_conversation_id", "writing_ai_jobs", ["conversation_id"])

    op.create_table(
        "writing_workspace_preferences",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("owner_user_id", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("preference_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "owner_user_id", name="uq_writing_workspace_preference_owner"),
    )
    op.create_index("ix_writing_workspace_preferences_project_id", "writing_workspace_preferences", ["project_id"])
    op.create_index("ix_writing_workspace_preferences_owner_user_id", "writing_workspace_preferences", ["owner_user_id"])

    op.create_table(
        "writing_ai_conversations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("owner_user_id", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False, server_default="ultra-magnus"),
        sa.Column("title", sa.String(200), nullable=False, server_default="协作会话"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_writing_ai_conversations_project_id", "writing_ai_conversations", ["project_id"])
    op.create_index("ix_writing_ai_conversations_owner_user_id", "writing_ai_conversations", ["owner_user_id"])
    op.create_index("ix_writing_ai_conversations_status", "writing_ai_conversations", ["status"])

    op.create_table(
        "writing_ai_messages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("conversation_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("target_context", sa.JSON(), nullable=False),
        sa.Column("job_kind", sa.String(24), nullable=False, server_default=""),
        sa.Column("job_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("proposal_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="completed"),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("client_message_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["writing_ai_conversations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("conversation_id", "client_message_id", name="uq_writing_ai_message_client_id"),
    )
    op.create_index("ix_writing_ai_messages_conversation_id", "writing_ai_messages", ["conversation_id"])
    op.create_index("ix_writing_ai_messages_project_id", "writing_ai_messages", ["project_id"])
    op.create_index("ix_writing_ai_messages_job_id", "writing_ai_messages", ["job_id"])
    op.create_index("ix_writing_ai_messages_status", "writing_ai_messages", ["status"])

    op.create_table(
        "presentation_ai_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("document_id", sa.String(64), nullable=False),
        sa.Column("slide", sa.Integer(), nullable=False),
        sa.Column("client_request_id", sa.String(96), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False, server_default="presentation-editor"),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("draft", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("proposal", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("requested_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("conversation_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("request_message_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("response_message_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "document_id", "client_request_id", name="uq_presentation_ai_job_client_request"),
    )
    op.create_index("ix_presentation_ai_jobs_project_id", "presentation_ai_jobs", ["project_id"])
    op.create_index("ix_presentation_ai_jobs_document_id", "presentation_ai_jobs", ["document_id"])
    op.create_index("ix_presentation_ai_jobs_status", "presentation_ai_jobs", ["status"])
    op.create_index("ix_presentation_ai_jobs_conversation_id", "presentation_ai_jobs", ["conversation_id"])


def downgrade() -> None:
    op.drop_table("presentation_ai_jobs")
    op.drop_table("writing_ai_messages")
    op.drop_table("writing_ai_conversations")
    op.drop_table("writing_workspace_preferences")
    op.drop_index("ix_writing_ai_jobs_conversation_id", table_name="writing_ai_jobs")
    op.drop_column("writing_ai_jobs", "response_message_id")
    op.drop_column("writing_ai_jobs", "request_message_id")
    op.drop_column("writing_ai_jobs", "conversation_id")
