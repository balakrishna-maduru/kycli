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
