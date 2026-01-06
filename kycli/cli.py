import sys
import os
from kycli.kycore import Kycore
from kycli.config import load_config

def print_help():
    print("""
🚀 kycli — The Microsecond-Fast Key-Value Toolkit

Available commands:
  kys <key> <value> [--ttl <sec>]  - Save key-value (optional TTL in seconds)
                                  Ex: kys session_id "data" --ttl 3600
  kyg <key>                     - Get current value (auto-deserializes JSON)
                                  Ex: kyg user
  kyf <query>                   - Full-text search (fast Google-like search)
                                  Ex: kyf "search terms"
  kyl [pattern]                 - List keys (optional regex pattern)
                                  Ex: kyl "prod_.*"
  kyd <key>                     - Delete key (requires confirmation)
                                  Ex: kyd old_token
  kyr <key>                     - Restore a deleted key from history
                                  Ex: kyr old_token
  kyv [-h]                      - View full audit history (no args or -h)
                                  Ex: kyv -h
  kyv <key>                     - View latest value from history for a specific key
                                  Ex: kyv username
  kye <file> [format]           - Export data to file (CSV or JSON)
                                  Ex: kye data.json json
  kyi <file>                    - Import data (CSV/JSON supported)
                                  Ex: kyi backup.csv
  kyc <key> [args...]           - Execute stored command (Static/Dynamic)
                                  Ex: kyc my_script
  kyshell                       - Open interactive TUI shell
  kyh                           - Help (This message)

Global Options:
  --key <master_key>            - Provide master key for encryption/decryption
  --ttl <seconds>               - Set expiration time for specific operations

💡 Tip: Use -h with any command or kyv -h for the full audit trail.
🌍 Env: Set KYCLI_DB_PATH to customize the database file location.
""")

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

        # Extract --key and --ttl from args
        master_key = os.environ.get("KYCLI_MASTER_KEY")
        ttl = None
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
    
                status = kv.save(key, val, ttl=ttl)
                if status == "created":
                    print(f"✅ Saved: {key} (New)")
                elif status == "overwritten":
                    print(f"🔄 Updated: {key}")
                else:
                    print(f"➖ No change: {key}")
    
            elif cmd in ["kyg", "getkey"]:
                if len(args) != 1:
                    print("Usage: kyg <key>")
                    return
                result = kv.getkey(args[0])
                if isinstance(result, (dict, list)):
                    import json
                    print(json.dumps(result, indent=2))
                else:
                    print(result)
    
            elif cmd in ["kyf", "search"]:
                if len(args) != 1:
                    print("Usage: kyf <query>")
                    return
                result = kv.search(args[0])
                if result:
                    import json
                    print(json.dumps(result, indent=2))
                else:
                    print("No matches found.")
    
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
                        print(f"{ts:<21} | {key_name:<15} | {val}")
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
                if len(args) != 1:
                    print("Usage: kyr <key>")
                    return
                print(kv.restore(args[0]))
    
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