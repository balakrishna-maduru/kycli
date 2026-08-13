import pytest

from kycli import Kycore


def test_rbac_bootstrap_key_acl_and_stats(tmp_path):
    db_path = str(tmp_path / "rbac_bootstrap.db")
    with Kycore(db_path) as kv:
        kv.set_access_key("legacy")
        status = kv.enable_rbac(access_key="legacy")
        assert status["rbac_enabled"] is True

        writer_token = kv.create_principal("writer", role="writer", access_key="legacy")
        reader_token = kv.create_principal("reader", role="reader", access_key="legacy")

        assert kv.save("public.item", "value", token="legacy") == "created"
        assert kv.getkey("public.item", token=reader_token) == "value"

        with pytest.raises(PermissionError):
            kv.save("reader.blocked", "x", token=reader_token)

        kv.grant_key_acl("writer", r"secret\..*", deny=["read"], access_key="legacy")
        kv.save("secret.one", "hidden", token="legacy")

        with pytest.raises(PermissionError):
            kv.getkey("secret.one", token=writer_token)

        assert kv.check_permission(writer_token, "read", key="public.item") is True
        assert kv.check_permission(writer_token, "read", key="secret.one") is False

        stats = kv.get_stats(token="legacy")
        assert stats["rbac_enabled"] is True
        assert stats["rbac_principal_count"] == 3


def test_rbac_enable_with_precreated_owner_and_whoami(tmp_path):
    db_path = str(tmp_path / "rbac_owner.db")
    with Kycore(db_path) as kv:
        owner_token = kv.create_principal("owner1", role="owner")
        status = kv.enable_rbac()
        assert status["rbac_enabled"] is True

        whoami = kv.whoami(token=owner_token)
        assert whoami["principal"] == "owner1"
        assert whoami["role"] == "owner"
