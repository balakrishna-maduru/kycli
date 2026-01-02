import os
import pytest
from kycli.kycore import Kycore

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_kydata.db"
    return str(db_file)

@pytest.fixture
def kv_store(temp_db):
    return Kycore(db_path=temp_db)
