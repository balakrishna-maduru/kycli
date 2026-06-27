import json
import time

from kycli import Kycore


def test_workspace_ttl_acl_and_prefix(tmp_path, monkeypatch):
    db_path = str(tmp_path / "roadmap_core.db")
    with Kycore(db_path) as kv:
        kv.set_default_ttl("1s")
        assert kv.get_default_ttl() == 1

        kv.save("alpha.one", "value")
        assert kv.getkey("alpha.one") == "value"
        prefix = kv.view_prefix("alpha")
        assert prefix["alpha.one"] == "value"

        kv.set_read_only(True)
        try:
            kv.save("blocked", "x")
            assert False, "expected read-only failure"
        except PermissionError:
            pass
        kv.set_read_only(False)

        kv.set_access_key("secret")
        monkeypatch.delenv("KYCLI_ACCESS_KEY", raising=False)
        try:
            kv.save("blocked2", "x")
            assert False, "expected access-key failure"
        except PermissionError:
            pass
        monkeypatch.setenv("KYCLI_ACCESS_KEY", "secret")
        kv.save("allowed", "ok")
        assert kv.getkey("allowed") == "ok"


def test_queue_delay_lease_ack_nack_and_stats(tmp_path):
    db_path = str(tmp_path / "roadmap_queue.db")
    with Kycore(db_path) as kv:
        kv.set_type("queue")
        kv.push("later", ttl="1s")
        assert kv.peek() is None
        time.sleep(1.2)
        assert kv.peek() == "later"

        kv.push("lease-me")
        leased = kv.pop(lease="1s")
        assert isinstance(leased, dict)
        assert leased["value"] == "later"
        assert kv.ack(leased["receipt_id"]) == "acked"

        leased2 = kv.pop(lease="1s")
        assert leased2["value"] == "lease-me"
        assert kv.nack(leased2["receipt_id"], delay="1s") == "nacked"
        assert kv.pop() is None
        time.sleep(1.2)
        assert kv.pop() == "lease-me"

        stats = kv.get_stats()
        assert stats["workspace_type"] == "queue"
        assert "queue_depth" in stats


def test_backup_restore_and_audit_export(tmp_path):
    db_path = str(tmp_path / "roadmap_backup.db")
    backup_path = str(tmp_path / "snapshot.db")
    audit_path = str(tmp_path / "audit.json")

    with Kycore(db_path) as kv:
        kv.save("key1", {"a": 1})
        kv.save("key2", "v2")
        count = kv.export_audit(audit_path, fmt="json")
        assert count >= 2
        exported = json.loads(open(audit_path, "r", encoding="utf-8").read())
        assert any(item["key"] == "key1" for item in exported)

        created = kv.backup(backup_path)
        assert created.startswith(backup_path)
        kv.save("key1", "changed")
        kv.restore_backup(created)
        assert kv.getkey("key1") == {"a": 1}


def test_large_value_compression_roundtrip(tmp_path):
    db_path = str(tmp_path / "compressed.db")
    payload = "x" * 5000
    with Kycore(db_path) as kv:
        kv.save("blob", payload)
        assert kv.getkey("blob") == payload
        raw = kv.getkey("blob", deserialize=False)
        assert raw == payload
