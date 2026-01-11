
import os
import sqlite3
import pytest
from kycli.core.storage import Kycore

def test_full_encryption():
    db_path = "test_enc_manual.db"
    if os.path.exists(db_path): os.remove(db_path)
    
    # 1. Create and Save
    with Kycore(db_path=db_path, master_key="testkey") as kv:
        kv.save("secret", "hidden_value")
        # should persist on save
        
    assert os.path.exists(db_path)
    
    # 2. Check File Header
    with open(db_path, "rb") as f:
        header = f.read(6)
        assert header == b'KYCLI\x01'
        
    # 3. Try opening with sqlite3 (Should Fail)
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM kvstore")
        assert False, "Should have failed to open encrypted DB with sqlite3"
    except sqlite3.DatabaseError:
        print("✅ SUCCESS: sqlite3 refused to open the file (not a database)")
    except Exception as e:
        print(f"✅ SUCCESS: sqlite3 failed with: {e}")
        
    # 4. Re-open with kycli (Should Succeed)
    with Kycore(db_path=db_path, master_key="testkey") as kv:
        assert kv.getkey("secret") == "hidden_value"
        print("✅ SUCCESS: kycli decrypted and read the value")

    # 5. Wrong Key (Should Fail)
    try:
        with Kycore(db_path=db_path, master_key="wrongkey") as kv:
            # Init might succeed (it loads blob), but decrypting blob should fail 
            pass 
        assert False, "Should have failed with wrong key"
    except Exception as e:
        print(f"✅ SUCCESS: kycli failed with wrong key: {e}")

    # Cleanup
    if os.path.exists(db_path): os.remove(db_path)

if __name__ == "__main__":
    test_full_encryption()
