"""add provenance fields and drop is_native

Revision ID: bb0578b8cd5b
Revises: 254f6bea39e6
Create Date: 2026-09-28 20:17:52.350395

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bb0578b8cd5b'
down_revision = '254f6bea39e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add the new columns first
    op.add_column('plants', sa.Column('provenance_status', sa.String(), nullable=True, server_default='native'))
    op.add_column('plants', sa.Column('provenance_notes', sa.String(), nullable=True))

    # 2. Populate provenance_status based on existing is_native values
    op.execute(
        """
        UPDATE plants 
        SET provenance_status = CASE 
            WHEN is_native = 1 THEN 'native' 
            ELSE 'non_native_benign' 
        END
        WHERE is_native IS NOT NULL
        """
    )

    # 3. Use batch_alter_table to safely drop the old is_native column in SQLite
    with op.batch_alter_table('plants', schema=None) as batch_op:
        batch_op.drop_column('is_native')

def downgrade() -> None:
    # 1. Re-add is_native column
    op.add_column('plants', sa.Column('is_native', sa.Boolean(), nullable=True, server_default=sa.text('1')))

    # 2. Re-populate is_native from provenance_status
    op.execute(
        """
        UPDATE plants 
        SET is_native = CASE 
            WHEN provenance_status = 'native' THEN 1 
            ELSE 0 
        END
        """
    )

    # 3. Batch drop the new columns
    with op.batch_alter_table('plants', schema=None) as batch_op:
        batch_op.drop_column('provenance_notes')
        batch_op.drop_column('provenance_status')