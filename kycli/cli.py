import sys
import os
import sqlite3
import shutil
from datetime import datetime, timezone
from kycli import Kycore
from kycli.config import load_config, save_config, get_workspaces
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

console = Console()

def get_help_text():
    return """
🚀 kycli — The Microsecond-Fast Key-Value Toolkit

Available commands:

  📂 Workspace Management:
  kyuse <workspace>                - Switch active workspace (Creates if new)
  kyws                             - List all workspaces
  kymv <key> <workspace>           - Move key to another workspace
  kydrop <workspace>               - Delete a workspace

  📝 Basic Operations:
  kys <key> <value> [--ttl 60] [--key "k"] - Save with optional TTL or Encryption
  kyg <key>[.path] [--key "k"]             - Get value (decrypt if key provided)
  kypatch <key> <val>                      - Patch JSON/Dict value
  kyl [pattern]                            - List keys (optional regex pattern)
  kyd <key>                                - Delete key (requires confirmation)
  kypush <key> <val> [--unique]            - Append value to a list
  kyrem <key> <val>                        - Remove value from a list

  🔍 Search & Utility:
  kyg -s <query>                   - Search for values (Full-Text Search).
  kyfo                             - Optimize Search Index
  kyshell                          - Open interactive TUI shell
  init                             - Initialize shell integration
  kyh                              - Help

  🛠️  Advanced & Recovery:
  kye <file> [format]              - Export data
  kyi <file>                       - Import data
  kyc <key> [args...]              - Execute stored command
  kyr <key>[.path]                 - Restore a deleted key
  kyrt <timestamp>                 - Point-in-Time Recovery
  kyco [days]                      - Compact DB
    kyrotate --new-key <k>           - Rotate encryption master key

  🔐 Security:
  Set `KYCLI_MASTER_KEY` env variable or use `--key "pass"` flag.
"""

def print_help():
    console.print(Panel(get_help_text(), title="[bold cyan]kycli Help[/bold cyan]", border_style="blue"))

import warnings

def _parse_legacy_expires_at(raw):
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(float(raw), tz=timezone.utc)
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            pass
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(s, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue
    return None

def _next_backup_path(base_path):
    if not os.path.exists(base_path):
        return base_path
    i = 1
    while True:
        candidate = f"{base_path}.{i}"
        if not os.path.exists(candidate):
            return candidate
        i += 1

def _maybe_migrate_legacy_sqlite(db_path, master_key=None):
    if not db_path or not os.path.exists(db_path):
        return False
    try:
        with open(db_path, "rb") as f:
            header = f.read(16)
    except Exception:
        return False

    if isinstance(header, str):
        header = header.encode("utf-8", errors="ignore")

    if not header.startswith(b"SQLite format 3"):
        return False

    backup_path = _next_backup_path(db_path + ".legacy.sqlite")
    try:
        shutil.copy2(db_path, backup_path)
    except Exception:
        pass

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    def _table_exists(name):
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
        return cur.fetchone() is not None

    rows = []
    if _table_exists("kvstore"):
        cur.execute("PRAGMA table_info(kvstore)")
        cols = [row[1] for row in cur.fetchall()]
        has_expires = "expires_at" in cols
        if has_expires:
            cur.execute("SELECT key, value, expires_at FROM kvstore")
            rows = cur.fetchall()
        else:
            cur.execute("SELECT key, value FROM kvstore")
            rows = [(k, v, None) for (k, v) in cur.fetchall()]

    try:
        conn.close()
    except Exception:
        pass

    # Move legacy DB out of the way so Kycore can create the new encrypted DB
    try:
        if os.path.exists(db_path):
            shutil.move(db_path, backup_path)
    except Exception:
        # If move fails, avoid destructive changes
        return False

    if Kycore is None:
        return False

    with Kycore(db_path=db_path, master_key=master_key) as kv:
        now = datetime.now(timezone.utc)
        for k, v, exp in rows:
            if k is None:
                continue
            ttl = None
            exp_dt = _parse_legacy_expires_at(exp)
            if exp_dt:
                delta = (exp_dt - now).total_seconds()
                if delta <= 0:
                    continue
                ttl = int(delta)
            kv.save(str(k).lower().strip(), v if v is not None else "", ttl=ttl)

    return True

def main():
    # Make warnings visible in CLI
    warnings.simplefilter("always", UserWarning)
    
    config = load_config()
    db_path = config.get("db_path")
    active_ws = config.get("active_workspace", "default")
    
    try:
        args = sys.argv[1:]
        full_prog = sys.argv[0]
        prog = os.path.basename(full_prog)

        if prog in ["kycli", "cli.py", "__main__.py", "python", "python3"]:
            if args:
                cmd = args[0]
                args = args[1:]
            else:
                cmd = "kyh"
        else:
            cmd = prog

        # Extract flags
        master_key = os.environ.get("KYCLI_MASTER_KEY")
        old_key = None
        new_key = None
        ttl = None
        limit = 100
        keys_only = False
        search_mode = False
        dry_run = False
        backup = False
        batch = 500
        new_args = []
        skip_next = False
        for i, arg in enumerate(args):
            if skip_next:
                skip_next = False
                continue
            if arg == "--key" and i + 1 < len(args):
                master_key = args[i+1]
                skip_next = True
            elif arg == "--old-key" and i + 1 < len(args):
                old_key = args[i+1]
                skip_next = True
            elif arg == "--new-key" and i + 1 < len(args):
                new_key = args[i+1]
                skip_next = True
            elif arg == "--ttl" and i + 1 < len(args):
                ttl = args[i+1]
                skip_next = True
            elif arg == "--limit" and i + 1 < len(args):
                try:
                    limit = int(args[i+1])
                    skip_next = True
                except:
                    new_args.append(arg)
            elif arg == "--batch" and i + 1 < len(args):
                try:
                    batch = int(args[i+1])
                    skip_next = True
                except:
                    new_args.append(arg)
            elif arg == "--keys-only":
                keys_only = True
            elif arg == "--dry-run":
                dry_run = True
            elif arg == "--backup":
                backup = True
            elif arg in ["-s", "--search", "-f", "--find"]:
                search_mode = True
            else:
                new_args.append(arg)
        args = new_args

        # Auto-migrate legacy SQLite DBs before any Kycore access
        _maybe_migrate_legacy_sqlite(db_path, master_key=master_key)

        if cmd in ["kyuse", "use"]:
            if not args:
                print(f"Current workspace: {active_ws}")
                print("Usage: kyuse <workspace_name>")
                return
            target = args[0]
            if not target.replace("_", "").replace("-", "").isalnum():
                print("Error: Invalid workspace name. Use alphanumeric characters.")
                return
            save_config({"active_workspace": target})
            # Explicitly initialize to create the file immediately
            new_config = load_config()
            new_db_path = new_config["db_path"]
            try:
                # Open and close to create
                Kycore(db_path=new_db_path).close()
            except: 
                pass # Already exists or will be created normally
            
            print(f"Switched to workspace: {target}")
            return

        if cmd in ["kyrotate", "rotate"]:
            if not new_key:
                print("Usage: kyrotate --new-key <key> [--old-key <key>] [--dry-run] [--backup] [--batch N]")
                return
            if old_key is None:
                old_key = master_key

            try:
                with Kycore(db_path=db_path, master_key=old_key) as kv:
                    count = kv.rotate_master_key(new_key, old_key=old_key, dry_run=dry_run, backup=backup, batch=batch, verify=True)
                if dry_run:
                    print(f"🧪 Dry run complete. {count} values would be re-encrypted.")
                else:
                    print(f"✅ Rotation complete. Re-encrypted {count} values.")
            except Exception as e:
                print(f"❌ Rotation failed: {e}")
            return

        if cmd in ["kyws", "workspaces"]:
            if "--current" in args or "-c" in args:
                print(active_ws)
                return

            if args:
                print(f"Computed: kyws {' '.join(args)}")
                print(f"Did you mean 'kyuse {args[0]}' to switch workspaces?")
                print("Running 'kyws' to list workspaces:")
            
            wss = get_workspaces()
            print("Workspaces:")
            for ws in wss:
                marker = "* " if ws == active_ws else "  "
                print(f"{marker}{ws}")
            return

        if cmd in ["kyshell", "shell"]:
            from kycli.tui import start_shell
            start_shell(db_path=db_path)
            return

        if cmd in ["kydrop", "drop"]:
            if not args:
                print("Usage: kydrop <workspace_name>")
                return
            
            target = args[0]
            is_active = (target == active_ws)
            
            from kycli.config import DATA_DIR
            target_db = os.path.join(DATA_DIR, f"{target}.db")
            
            if not os.path.exists(target_db):
                print(f"❌ Workspace '{target}' does not exist.")
                return
            
            msg = f"⚠️  DANGER: Are you sure you want to PERMANENTLY delete workspace '{target}'?"
            if is_active:
                msg += " (This is your ACTIVE workspace, you will be moved to 'default')"
            
            confirm = input(f"{msg} (y/N): ")
            if confirm.lower() == 'y':
                try:
                    os.remove(target_db)
                    print(f"✅ Workspace '{target}' deleted.")
                    if is_active:
                        save_config({"active_workspace": "default"})
                        print("🔄 Switched to 'default' workspace.")
                except Exception as e:
                    print(f"🔥 Error deleting workspace: {e}")
            else:
                print("❌ Aborted.")
            return


        if cmd == "init":
            shell = os.environ.get("SHELL", "/bin/bash")
            home = os.path.expanduser("~")
            rc_file = None
            if "zsh" in shell:
                rc_file = os.path.join(home, ".zshrc")
            elif "bash" in shell:
                rc_file = os.path.join(home, ".bashrc")
            
            if not rc_file:
                print("❌ Could not detect shell configuration file.")
                return

            snippet = r"""
# >>> kycli initialize >>>
ky_prompt_info() {
    local ws_file="$HOME/.kycli/workspace"
    if [ -f "$ws_file" ]; then
        local ws=$(cat "$ws_file")
        # Use cyan color for prompt if supported
        if [ -n "$ZSH_VERSION" ]; then
            echo "%F{cyan}($ws)%f "
        else
            echo "($ws) "
        fi
    elif command -v kyws >/dev/null 2>&1; then
        # Fallback to slower method if file missing
        local ws=$(kyws --current 2>/dev/null)
        if [ -n "$ws" ]; then
            if [ -n "$ZSH_VERSION" ]; then
                echo "%F{cyan}($ws)%f "
            else
                echo "($ws) "
            fi
        fi
    fi
}
if [ -n "$ZSH_VERSION" ]; then
    setopt PROMPT_SUBST
    PROMPT='$(ky_prompt_info)'"${PROMPT}"
elif [ -n "$BASH_VERSION" ]; then
    PS1='$(ky_prompt_info)'"${PS1}"
fi
# <<< kycli initialize <<<
"""
            # Check for existing
            if os.path.exists(rc_file):
                with open(rc_file, "r") as f:
                     if "# >>> kycli initialize >>>" in f.read():
                         print(f"⚠️  Already initialized in {rc_file}")
                         return
            
            try:
                with open(rc_file, "a") as f:
                    f.write(snippet)
                print(f"✅ Added shell integration to {rc_file}")
                print(f"🔄 To apply changes, run: source {rc_file}")
            except Exception as e:
                print(f"🔥 Error writing to {rc_file}: {e}")
            return

        with Kycore(db_path=db_path, master_key=master_key) as kv:
            # Move command needs special handling (inter-db)
            if cmd in ["kymv", "mv", "move"]:
                if len(args) < 2:
                    print("Usage: kymv <key> <target_workspace>")
                    return
                
                key = args[0]
                target_ws = args[1]
                
                if target_ws == active_ws:
                    print("⚠️ Source and target workspaces are the same.")
                    return

                # Get value
                val = kv.getkey(key)
                if val == "Key not found":
                    print(f"❌ Key '{key}' not found in '{active_ws}'.")
                    return
                
                # Check target DB
                from kycli.config import DATA_DIR
                target_db = os.path.join(DATA_DIR, f"{target_ws}.db")
                
                # We need a quick way to write to target without side effects
                # We can open a second Kycore instance
                print(f"📦 Moving '{key}' to '{target_ws}'...")
                
                try:
                    with Kycore(db_path=target_db, master_key=master_key) as target_kv:
                        # Check exist
                        if key in target_kv:
                            confirm = input(f"⚠️ Key '{key}' exists in '{target_ws}'. Overwrite? (y/n): ")
                            if confirm.lower() != 'y':
                                print("❌ Aborted.")
                                return
                        
                        target_kv.save(key, val)
                        # Delete from source
                        kv.delete(key)
                        print(f"✅ Moved '{key}' to '{target_ws}'.")
                except Exception as e:
                    print(f"🔥 Failed to move: {e}")
                return

            # ... Rest of commands ...
            if cmd in ["kys", "save"]:
                if len(args) < 2:
                    print("Usage: kys <key> <value>")
                    return
                
                key = args[0]
                val = " ".join(args[1:]) # Handle values with spaces if passed via kycli save
                
                if val.isdigit(): val = int(val)
                elif val.lower() == "true": val = True
                elif val.lower() == "false": val = False
                elif val.startswith("[") or val.startswith("{"):
                    import json
                    try: val = json.loads(val)
                    except: pass 
                
                # Check for existing key confirmation
                if key in kv and not ttl: # Don't confirm if TTL is explicitly set (assumes override intent)
                    if sys.stdin.isatty():
                        confirm = input(f"⚠️ Key '{key}' already exists. Overwrite? (y/n): ").strip().lower()
                        if confirm != 'y':
                            print("❌ Aborted.")
                            return
                status = kv.save(key, val, ttl=ttl)
                if status == "created":
                    print(f"✅ Saved: {key} (New) [Workspace: {active_ws}]" + (f" (Expires in {ttl}s)" if ttl else ""))
                elif status == "nochange":
                    print(f"✅ No Change: {key} already has this value.")
                else:
                    print(f"✅ Updated: {key}" + (f" (Expires in {ttl}s)" if ttl else ""))

            elif cmd in ["kypatch", "patch"]:
                if len(args) < 2:
                    print("Usage: kypatch <key_path> <value>")
                    return
                val = " ".join(args[1:])
                # Try to parse as JSON/Int/Bool
                if val.isdigit(): val = int(val)
                elif val.lower() == "true": val = True
                elif val.lower() == "false": val = False
                else:
                    import json
                    try: val = json.loads(val)
                    except: pass
                    
                status = kv.patch(args[0], val, ttl=ttl)
                if status.startswith("Error"):
                     print(f"❌ {status}")
                else:
                    print(f"✅ Patched: {args[0]}")

            elif cmd in ["kypush", "push"]:
                if len(args) < 2:
                    print("Usage: kypush <key> <value> [--unique]")
                    return
                unique = "--unique" in args
                val = args[1]
                # Try to parse as JSON
                try: val = json.loads(val)
                except: pass
                print(kv.push(args[0], val, unique=unique))

            elif cmd in ["kyrem", "remove"]:
                if len(args) < 2:
                    print("Usage: kyrem <key> <value>")
                    return
                val = args[1]
                try: val = json.loads(val)
                except: pass
                
                status = kv.remove(args[0], val, ttl=ttl)
                print(f"➖ Result: {status}")
    
            elif cmd in ["kyg", "getkey"]:
                if not args:
                    print("Usage: kyg <key> OR kyg -s <query>")
                    return
                
                if search_mode:
                    query = " ".join(args)
                    result = kv.search(query, limit=limit, keys_only=keys_only)
                    if result:
                        if keys_only:
                            print(f"🔍 Found {len(result)} keys: {', '.join(result)}")
                        else:
                            import json
                            print(json.dumps(result, indent=2))
                    else:
                        print("No matches found.")
                else:
                    result = kv.getkey(args[0])
                    if isinstance(result, (dict, list)):
                        import json
                        print(json.dumps(result, indent=2))
                    else:
                        print(result)
    
            
            elif cmd in ["kyfo", "optimize"]:
                kv.optimize_index()
                print("⚡ Search index optimized.")
    
            elif cmd in ["kyv", "history"]:
                target = args[0] if len(args) > 0 else "-h"
                history = kv.get_history(target)
                
                if not history:
                    print(f"No history found.")
                elif target == "-h":
                    print(f"📜 Full Audit History [{active_ws}]:")
                    print(f"{'Timestamp':<21} | {'Key':<15} | {'Value'}")
                    print("-" * 55)
                    for key_name, val, ts in history:
                        # Truncate value for table view
                        display_val = str(val)[:40] + "..." if len(str(val)) > 40 else str(val)
                        print(f"{ts:<21} | {key_name:<15} | {display_val}")
                else:
                    if history:
                        print(history[0][1])
    
            elif cmd in ["kyd", "delete"]:
                if len(args) != 1:
                    print("Usage: kyd <key>")
                    return
                key = args[0]
                confirm = input(f"⚠️ DANGER: To delete '{key}', please re-enter the key name: ").strip()
                if confirm != key:
                    print("❌ Confirmation failed. Aborted.")
                    return
                
                print(kv.delete(key))
                print(f"💡 Tip: If this was accidental, use 'kyr {key}' to restore it.")
    
            elif cmd in ["kyr", "restore"]:
                if len(args) < 1:
                    print("Usage: kyr <key>[.path]")
                    return
                print(kv.restore(args[0]))
    
            elif cmd in ["kyrt", "restore-to"]:
                if not args:
                    print("Usage: kyrt <timestamp> OR kyrt <key.path> --at <timestamp>")
                    return
                elif "--at" in args:
                    idx = args.index("--at")
                    key_part = " ".join(args[:idx])
                    ts_part = " ".join(args[idx+1:])
                    result = kv.restore(key_part, timestamp=ts_part)
                else:
                    ts = " ".join(args)
                    result = kv.restore_to(ts)
                print(result)

            elif cmd in ["kyco", "compact"]:
                retention = int(args[0]) if args else 15
                print(kv.compact(retention))
            elif cmd in ["kyl", "listkeys"]:
                pattern = args[0] if args else None
                keys = kv.listkeys(pattern)
                if keys:
                    print(f"🔑 Keys [{active_ws}]: {', '.join(keys)}")
                else:
                    print(f"No keys found in workspace '{active_ws}'.")
    
            elif cmd in ["kyh", "help", "--help", "-h"]:
                print_help()
            
            elif cmd in ["kye", "export"]:
                if len(args) < 1:
                    print("Usage: kye <file> [format]")
                    return
                export_path = args[0]
                export_format = args[1] if len(args) > 1 else config.get("export_format", "csv")
                kv.export_data(export_path, export_format.lower())
                print(f"📤 Exported data to {export_path} as {export_format.upper()}")
    
            elif cmd in ["kyi", "import"]:
                if len(args) != 1:
                    print("Usage: kyi <file>")
                    return
                import_path = args[0]
                if not os.path.exists(import_path):
                    print(f"❌ Error: File not found: {import_path}")
                    return
                kv.import_data(import_path)
                print(f"📥 Imported data into '{active_ws}'")
    
            elif cmd in ["kyc", "execute"]:
                if not args:
                    print("Usage: kyc <key> [args...]")
                    return
                key = args[0]
                val = kv.getkey(key, deserialize=False)
                if val == "Key not found":
                    print(f"❌ Error: Key '{key}' not found.")
                    return
                
                import subprocess
                cmd_to_run = val
                if len(args) > 1:
                    cmd_to_run = f"{val} {' '.join(args[1:])}"
                
                print(f"🚀 Executing: {cmd_to_run}")
                try:
                    subprocess.run(cmd_to_run, shell=True, check=True)
                except subprocess.CalledProcessError as e:
                    print(f"🔥 Command failed with exit code {e.returncode}")
                except Exception as e:
                    print(f"🔥 Execution Error: {e}")
    
            else:
                if cmd != "kycli":
                    print(f"❌ Invalid command: {cmd}")
                print_help()

    except ValueError as e:
        print(f"⚠️ Validation Error: {e}")
    except Exception as e:
        print(f"🔥 Unexpected Error: {e}")
        # import traceback
        # traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()