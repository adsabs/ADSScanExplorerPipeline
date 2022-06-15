"""Added status columns

Revision ID: 35b8136d4902
Revises: d7c87e120935
Create Date: 2022-06-15 13:57:39.155644

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '35b8136d4902'
down_revision = 'd7c87e120935'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('journal_volume', sa.Column('db_done', sa.Boolean(), nullable=True))
    op.add_column('journal_volume', sa.Column('db_uploaded', sa.Boolean(), nullable=True))
    op.add_column('journal_volume', sa.Column('bucket_uploaded', sa.Boolean(), nullable=True))
    op.add_column('journal_volume', sa.Column('ocr_uploaded', sa.Boolean(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('journal_volume', 'ocr_uploaded')
    op.drop_column('journal_volume', 'bucket_uploaded')
    op.drop_column('journal_volume', 'db_uploaded')
    op.drop_column('journal_volume', 'db_done')
    # ### end Alembic commands ###