import sys
import os
from kycli.kycore import Kycore
from kycli.config import load_config

def get_help_text():
    return """
🚀 kycli — The Microsecond-Fast Key-Value Toolkit

Available commands:
  kys <key> <value> [--ttl <sec>]  - Save key-value (optional TTL in seconds)
                                  Supports nested JSON paths (atomic patching).
                                  Ex: kys user.profile.age 25
                                  Ex: kys user '{"name": "balu"}' --ttl 1d

  kyg <key>[.path] or <key>[index] - Get current value or sub-key/index
                                  Supports dot-notation and list slicing.
                                  Ex: kyg user.name
                                  Ex: kyg logs[0:5]

  kypush <key> <val> [--unique]  - Append value to a list (optionally unique)
  kyrem <key> <val>               - Remove value from a list

  kyf <query> [--limit <n>] [--keys-only]
                                  - Full-text search (fast Google-like search)

  kyfo                            - Optimize FTS5 search index (performance)

  kyl [pattern]                 - List keys (optional regex pattern)

  kyd <key>                     - Delete key (requires confirmation)

  kyr <key>[.path]              - Restore a deleted key or specific sub-path
                                  Ex: kyr my_secret --key "password"

  kyv [-h]                      - View full audit history (no args or -h)

  kyv <key>                     - View latest value from history for a specific key

  kye <file> [format]           - Export data to file (CSV or JSON, default CSV)

  kyi <file>                    - Import data (CSV/JSON supported)

  kyc <key> [args...]           - Execute stored command (Static/Dynamic)

  kyrt <timestamp>              - Point-in-Time Recovery (reconstruct state)

  kyco [days]                   - Compact DB (Cleanup old history/archive)

  kyshell                       - Open interactive TUI shell
  kyh                           - Help (This message)

🔐 Encryption & Security:
  Provide a master key to enable AES-256-GCM encryption/decryption at rest.
  When encryption is enabled, data is stored as ciphertext and only readable with the correct key.

  - Via Global Flag:      `kycli ... --key "your_secret_passphrase"`
  - Via Env Variable:     `export KYCLI_MASTER_KEY="your_secret_passphrase"` (Recommended)

  Examples:
    - Save encrypted:      `kys sensitive_token "99-xyz" --key "my-pass"`
    - Get encrypted:       `kyg sensitive_token --key "my-pass"`
    - Restore encrypted:   `kyr sensitive_token` (Ciphertext is restored, key still required to view)

💡 Tip: Use `kyv -h` for the full audit trail.
🌍 Env: Set `KYCLI_DB_PATH` to customize the database file location.
"""

def print_help():
    print(get_help_text())

import warnings

def main():
    # Make warnings visible in CLI
    warnings.simplefilter("always", UserWarning)
    
    config = load_config()
    db_path = config.get("db_path")
    
    try:
        args = sys.argv[1:]
        # Get the filename only
        full_prog = sys.argv[0]
        prog = os.path.basename(full_prog)

        # Handle 'kycli <cmd>' or when run via 'python -m kycli.cli' or generic entry points
        if prog in ["kycli", "cli.py", "__main__.py", "python", "python3"]:
            if args:
                cmd = args[0]
                args = args[1:]
            else:
                cmd = "kyh" # Default to help if no args
        else:
            cmd = prog

        # Extract --key, --ttl, --limit, --keys-only from args
        master_key = os.environ.get("KYCLI_MASTER_KEY")
        ttl = None
        limit = 100
        keys_only = False
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
            else:
                new_args.append(arg)
        args = new_args

        if cmd in ["kyshell", "shell"]:
            from kycli.tui import start_shell
            start_shell(db_path=db_path)
            return


        with Kycore(db_path=db_path, master_key=master_key) as kv:
            if cmd in ["kys", "save"]:
                if len(args) < 2:
                    print("Usage: kys <key> <value>")
                    return
                
                key = args[0]
                val = " ".join(args[1:]) # Handle values with spaces if passed via kycli save
                
                # Attempt to parse as JSON if it looks like a complex type
                if (val.startswith("{") and val.endswith("}")) or (val.startswith("[") and val.endswith("]")):
                    try:
                        import json
                        val = json.loads(val)
                    except:
                        pass

                existing = kv.getkey(key, deserialize=False)
                
                # If key exists and is not a regex result (dict), ask for confirmation
                if existing != "Key not found" and not isinstance(existing, dict):
                    if existing == str(val) if not isinstance(val, (dict, list)) else json.dumps(val) == existing:
                         print(f"➖ No change: {key} (Value is identical)")
                         return
                    
                    choice = input(f"⚠️ Key '{key}' already exists. Overwrite? (y/n): ").lower().strip()
                    if choice != 'y':
                        print("❌ Aborted.")
                        return
    
                status = kv.patch(key, val, ttl=ttl) if "." in key or "[" in key else kv.save(key, val, ttl=ttl)
                if status == "created":
                    print(f"✅ Saved: {key} (New)")
                elif status == "overwritten":
                    print(f"🔄 Updated: {key}")
                elif status == "nochange":
                    print(f"➖ No change: {key} (Value is identical)")
                else:
                    print(f"➖ Result: {status}")
    
            elif cmd in ["kyg", "getkey"]:
                if len(args) != 1:
                    print("Usage: kyg <key>[.path] or <key>[index]")
                    return
                
                result = kv.getkey(args[0])
                
                if isinstance(result, (dict, list)):
                    import json
                    print(json.dumps(result, indent=2))
                else:
                    print(result)
    
            elif cmd in ["kyf", "search"]:
                if not args:
                    print("Usage: kyf <query>")
                    return
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
            
            elif cmd in ["kyfo", "optimize"]:
                kv.optimize_index()
                print("⚡ Search index optimized.")
    
            elif cmd in ["kyv", "history"]:
                target = args[0] if len(args) > 0 else "-h"
                history = kv.get_history(target)
                
                if not history:
                    print(f"No history found.")
                elif target == "-h":
                    print("📜 Full Audit History (All Keys):")
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
                print(kv.remove(args[0], val))
    
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
                    print(f"🔑 Keys: {', '.join(keys)}")
                else:
                    print("No keys found.")
    
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
                print(f"📥 Imported data from {import_path}")
    
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