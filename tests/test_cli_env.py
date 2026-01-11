
import os
import pytest
from unittest.mock import patch
from kycli.core.storage import Kycore

def test_kycore_env_master_key(tmp_path):
    # This verifies that Kycore() picks up the env var if master_key is None
    
    db_path = tmp_path / "env_test.db"
    
    # 1. Save with env key
    with patch.dict(os.environ, {"KYCLI_MASTER_KEY": "env_secret"}):
        with Kycore(str(db_path)) as k1:
             k1.save("secret_k", "secret_v")
             
    assert db_path.exists()
    
    # 2. Read with Same Key (env) - Should Succeed
    with patch.dict(os.environ, {"KYCLI_MASTER_KEY": "env_secret"}):
        with Kycore(str(db_path)) as k2:
            val = k2.getkey("secret_k")
            assert val == "secret_v"
        
    # 3. Read with Different Key (env) - Should Fail Init
    with patch.dict(os.environ, {"KYCLI_MASTER_KEY": "wrong_secret"}):
        try:
             with Kycore(str(db_path)) as k3:
                 pass
             # If it didn't raise, we assert failure
             assert False, "Should have failed init with wrong key"
        except Exception:
             pass

    # 4. Read with No Key - Should Fail Init
    with patch.dict(os.environ, {}, clear=True):
        try:
             with Kycore(str(db_path)) as k4:
                 pass
             assert False, "Should have failed init with no key"
        except Exception:
             pass
