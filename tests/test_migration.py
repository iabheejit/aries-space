import os
import subprocess

import pytest
from sqlalchemy import CheckConstraint, UniqueConstraint

from services.api.aries_api.models import Dataset


def test_dataset_constraints_are_named_and_complete():
    constraints = {constraint.name: constraint for constraint in Dataset.__table__.constraints}

    assert isinstance(constraints["ck_datasets_subject"], CheckConstraint)
    assert isinstance(constraints["uq_datasets_source_external_id"], UniqueConstraint)
    assert isinstance(constraints["uq_datasets_object_key"], UniqueConstraint)
    assert {column.name for column in constraints["uq_datasets_source_external_id"].columns} == {
        "source",
        "external_id",
    }


@pytest.mark.skipif(
    "TEST_DATABASE_URL" not in os.environ,
    reason="isolated PostgreSQL migration URL not configured",
)
def test_migration_round_trip():
    environment = {**os.environ, "DATABASE_URL": os.environ["TEST_DATABASE_URL"]}
    for command in (("upgrade", "head"), ("downgrade", "base"), ("upgrade", "head")):
        subprocess.run(
            [os.sys.executable, "-m", "alembic", *command],
            check=True,
            env=environment,
            timeout=30,
        )