import json
from unittest.mock import patch

from kycli.cli import main


def test_cli_profile_ttl_acl_and_stats(clean_home_db, capsys):
    with patch("sys.argv", ["kyprofile", "save", "dev"]):
        main()
    assert "Saved profile 'dev'" in capsys.readouterr().out

    with patch("sys.argv", ["kyprofile", "list"]):
        main()
    assert "dev" in capsys.readouterr().out

    with patch("sys.argv", ["kyprofile", "use", "dev"]):
        main()
    assert "Active profile set" in capsys.readouterr().out

    with patch("sys.argv", ["kyttl", "set", "30"]):
        main()
    assert "Default TTL set" in capsys.readouterr().out

    with patch("sys.argv", ["kyttl", "get"]):
        main()
    assert "30" in capsys.readouterr().out

    with patch("sys.argv", ["kyacl", "readonly", "status"]):
        main()
    assert "off" in capsys.readouterr().out

    with patch("sys.argv", ["kystats", "--json"]):
        main()
    payload = json.loads(capsys.readouterr().out)
    assert "workspace_type" in payload


def test_cli_queue_file_batch_and_ack_flow(clean_home_db, tmp_path, capsys):
    task_file = tmp_path / "tasks.txt"
    task_file.write_text("job1\njob2\n", encoding="utf-8")

    with patch("sys.argv", ["kyws", "create", "jobs", "--type", "queue"]):
        main()
    capsys.readouterr()
    with patch("sys.argv", ["kyuse", "jobs"]):
        main()
    capsys.readouterr()

    with patch("sys.argv", ["kypush", "--file", str(task_file)]):
        main()
    assert "Pushed 2 queued items" in capsys.readouterr().out

    with patch("sys.argv", ["kypop", "--n", "2", "--json"]):
        main()
    popped = json.loads(capsys.readouterr().out)
    assert popped == ["job1", "job2"]

    with patch("sys.argv", ["kypush", "job3"]):
        main()
    capsys.readouterr()
    with patch("sys.argv", ["kypop", "--lease", "1s", "--json"]):
        main()
    leased = json.loads(capsys.readouterr().out)
    assert leased["value"] == "job3"

    with patch("sys.argv", ["kynack", leased["receipt_id"]]):
        main()
    assert "nacked" in capsys.readouterr().out

    with patch("sys.argv", ["kypop"]):
        main()
    assert "job3" in capsys.readouterr().out


def test_cli_audit_export_backup_and_prefix_view(clean_home_db, tmp_path, capsys):
    audit_file = tmp_path / "audit.json"
    backup_file = tmp_path / "snapshot.db"

    with patch("sys.argv", ["kys", "ns.alpha", "1"]):
        main()
    capsys.readouterr()
    with patch("sys.argv", ["kys", "ns.beta", "2"]):
        main()
    capsys.readouterr()

    with patch("sys.argv", ["kyws", "view", "ns", "--json"]):
        main()
    prefix_payload = json.loads(capsys.readouterr().out)
    assert "ns.alpha" in prefix_payload

    with patch("sys.argv", ["kyaudit", "export", str(audit_file), "json"]):
        main()
    assert "Exported" in capsys.readouterr().out
    audit_payload = json.loads(audit_file.read_text(encoding="utf-8"))
    assert any(item["key"] == "ns.alpha" for item in audit_payload)

    with patch("sys.argv", ["kybackup", str(backup_file)]):
        main()
    out = capsys.readouterr().out
    assert "Backup created" in out


def test_cli_output_consistency_and_rbac_flow(clean_home_db, tmp_path, capsys):
    backup_file = tmp_path / "rbac_snapshot.db"
    audit_file = tmp_path / "rbac_audit.json"

    with patch("sys.argv", ["kyws", "create", "rbacq", "--type", "queue"]):
        main()
    capsys.readouterr()
    with patch("sys.argv", ["kyuse", "rbacq"]):
        main()
    capsys.readouterr()
    with patch("sys.argv", ["kypush", "job1"]):
        main()
    capsys.readouterr()

    with patch("sys.argv", ["kypeek", "--json"]):
        main()
    assert json.loads(capsys.readouterr().out) == "job1"

    with patch("sys.argv", ["kycount", "--json"]):
        main()
    assert json.loads(capsys.readouterr().out)["count"] == 1

    with patch("sys.argv", ["kypop", "--lease", "1s", "--json"]):
        main()
    leased = json.loads(capsys.readouterr().out)
    assert leased["value"] == "job1"

    with patch("sys.argv", ["kynack", leased["receipt_id"], "--json"]):
        main()
    assert json.loads(capsys.readouterr().out)["status"] == "nacked"

    with patch("sys.argv", ["kyuse", "default"]):
        main()
    capsys.readouterr()

    with patch("sys.argv", ["kybackup", str(backup_file), "--json"]):
        main()
    assert json.loads(capsys.readouterr().out)["backup_path"].startswith(str(backup_file))

    with patch("sys.argv", ["kyaudit", "export", str(audit_file), "json", "--json"]):
        main()
    assert json.loads(capsys.readouterr().out)["file"] == str(audit_file)

    with patch("sys.argv", ["kyacl", "key", "set", "legacy"]):
        main()
    capsys.readouterr()

    with patch("sys.argv", ["kyacl", "enable", "--access-key", "legacy", "--json"]):
        main()
    assert json.loads(capsys.readouterr().out)["rbac_enabled"] is True

    with patch("sys.argv", ["kyacl", "user", "add", "alice", "--role", "writer", "--access-key", "legacy", "--json"]):
        main()
    alice = json.loads(capsys.readouterr().out)
    assert alice["principal"] == "alice"
    alice_token = alice["token"]

    with patch("sys.argv", ["kyacl", "whoami", "--token", alice_token, "--json"]):
        main()
    whoami = json.loads(capsys.readouterr().out)
    assert whoami["principal"] == "alice"
    assert whoami["role"] == "writer"

    with patch("sys.argv", ["kys", "public.item", "value", "--token", alice_token]):
        main()
    out = capsys.readouterr().out
    assert "Saved: public.item" in out or "Updated: public.item" in out

    with patch("sys.argv", ["kyacl", "role", "grant", "alice", "writer", "--key", r"secret\..*", "--deny", "read", "--access-key", "legacy", "--json"]):
        main()
    assert json.loads(capsys.readouterr().out)["deny"] == "read"

    with patch("sys.argv", ["kys", "secret.one", "hidden", "--access-key", "legacy"]):
        main()
    capsys.readouterr()

    with patch("sys.argv", ["kyg", "secret.one", "--token", alice_token]):
        main()
    assert "Permission denied" in capsys.readouterr().out
