import sys
import os
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
  kys <key> <value> [--ttl <sec>]  - Save key-value (optional TTL in seconds)
  kyg <key>[.path]                 - Get value, sub-key, or list index.
  kyg -s <query>                   - Search for values (Full-Text Search).

  kypush <key> <val> [--unique]    - Append value to a list
  kyrem <key> <val>                - Remove value from a list

  kyuse <workspace>                - Switch active workspace (Creates if new)
  kyws                             - List all workspaces
  kymv <key> <workspace>           - Move key to another workspace

  kyl [pattern]                    - List keys (optional regex pattern)
  kyd <key>                        - Delete key (requires confirmation)
  kyr <key>[.path]                 - Restore a deleted key
  kyv [-h|key]                     - View audit history

  kye <file> [format]              - Export data
  kyi <file>                       - Import data
  kyc <key> [args...]              - Execute stored command
  kyrt <timestamp>                 - Point-in-Time Recovery
  kyco [days]                      - Compact DB

  kyshell                          - Open interactive TUI shell
  kyh                              - Help

🔐 Encryption & Security:
  Set `KYCLI_MASTER_KEY` env variable or use `--key "pass"` flag.
"""

def print_help():
    console.print(Panel(get_help_text(), title="[bold cyan]kycli Help[/bold cyan]", border_style="blue"))

import warnings

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
        ttl = None
        limit = 100
        keys_only = False
        search_mode = False
        new_args = []
        skip_next = False
        for i, arg in enumerate(args):
            if skip_next:
                skip_next = False
                continue
            if arg == "--key" and i + 1 < len(args):
                master_key = args[i+1]
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
            elif arg == "--keys-only":
                keys_only = True
            elif arg in ["-s", "--search", "-f", "--find"]:
                search_mode = True
            else:
                new_args.append(arg)
        args = new_args

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

        if cmd in ["kyws", "workspaces"]:
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