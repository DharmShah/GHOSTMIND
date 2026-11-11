"""MCP Ecosystem and Universal OAuth Tables

Revision ID: 7a89fbc3012d
Revises: 58beee286a5b
Create Date: 2026-11-11 15:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '7a89fbc3012d'
down_revision: Union[str, Sequence[str], None] = '58beee286a5b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # integration_credentials
    op.create_table(
        'integration_credentials',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('service_name', sa.String(100), nullable=False),
        sa.Column('server_id', sa.String(100), nullable=True),
        sa.Column('encrypted_access_token', sa.Text(), nullable=True),
        sa.Column('encrypted_refresh_token', sa.Text(), nullable=True),
        sa.Column('encrypted_client_secret', sa.Text(), nullable=True),
        sa.Column('granted_scopes', sa.Text(), nullable=True),
        sa.Column('token_expiry', sa.DateTime(timezone=True), nullable=True),
        sa.Column('connection_status', sa.String(50), nullable=False, server_default='connected'),
        sa.Column('account_identifier', sa.String(255), nullable=True),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # mcp_server_configs
    op.create_table(
        'mcp_server_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('transport', sa.String(50), nullable=False, server_default='stdio'),
        sa.Column('command', sa.String(255), nullable=True),
        sa.Column('args_json', sa.Text(), nullable=True),
        sa.Column('env_json', sa.Text(), nullable=True),
        sa.Column('url', sa.String(512), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='installed'),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('tools_cache_json', sa.Text(), nullable=True),
        sa.Column('last_connected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # pending_actions
    op.create_table(
        'pending_actions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('conversations.id', ondelete='SET NULL'), nullable=True),
        sa.Column('server_name', sa.String(100), nullable=False),
        sa.Column('tool_name', sa.String(100), nullable=False),
        sa.Column('action_type', sa.String(50), nullable=False, server_default='write'),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('parameters_json', sa.Text(), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('result_json', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('pending_actions')
    op.drop_table('mcp_server_configs')
    op.drop_table('integration_credentials')

