"""add columns

Revision ID: c30c4300c987
Revises: 67018bbed12a
Create Date: 2024-06-01 20:31:59.672688

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c30c4300c987'
down_revision = '67018bbed12a'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('appointments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('_createdDate', sa.DateTime(), nullable=False))
        batch_op.add_column(sa.Column('_updatedDate', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('_owner', sa.String(length=100), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('appointments', schema=None) as batch_op:
        batch_op.drop_column('_owner')
        batch_op.drop_column('_updatedDate')
        batch_op.drop_column('_createdDate')

    # ### end Alembic commands ###
