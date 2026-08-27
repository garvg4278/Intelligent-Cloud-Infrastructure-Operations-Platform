"""initial schema

Revision ID: 8f3a1c2e9b40
Revises:
Create Date: 2026-08-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f3a1c2e9b40'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('environments',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('environment_type', sa.Enum('staging', 'production', name='environmenttype', native_enum=False, length=32), nullable=False),
    sa.Column('status', sa.Enum('pending', 'provisioning_infra', 'configuring_nodes', 'ready', 'provision_failed', 'destroying', 'destroyed', 'destroy_failed', name='environmentstatus', native_enum=False, length=32), nullable=False),
    sa.Column('cluster_name', sa.String(length=255), nullable=True),
    sa.Column('error_message', sa.String(length=2000), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_environments_environment_type'), 'environments', ['environment_type'], unique=False)
    op.create_index(op.f('ix_environments_name'), 'environments', ['name'], unique=True)
    op.create_index(op.f('ix_environments_status'), 'environments', ['status'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_environments_status'), table_name='environments')
    op.drop_index(op.f('ix_environments_name'), table_name='environments')
    op.drop_index(op.f('ix_environments_environment_type'), table_name='environments')
    op.drop_table('environments')
    # ### end Alembic commands ###
