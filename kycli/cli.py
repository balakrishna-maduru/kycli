import sys
import os
from kycli.kycore import Kycore

def print_help():
    print("""
Available commands:
  kys <key> <value>             - Save key-value (asks before overwriting)
  kyg <key>                     - Get current value by key
  kyl [pattern]                 - List keys (optional regex pattern)
  kyd <key>                     - Delete key
  kyv [-h]                      - View full audit history (no args or -h)
  kyv <key>                     - View latest value from history for a specific key
  kye <file> [format]           - Export data to file (default CSV; JSON if specified)
  kyi <file>                    - Import data (CSV/JSON supported)
  kyh                           - Help
""")

def main():
    try:
        with Kycore() as kv:
            args = sys.argv[1:]
            prog = os.path.basename(sys.argv[0])

            if prog in ["kys", "save"]:
                if len(args) != 2:
                    print("Usage: kys <key> <value>")
                    return
                
                key, val = args[0], args[1]
                existing = kv.getkey(key)
                
                # If key exists and is not a regex result (dict), ask for confirmation
                if existing != "Key not found" and not isinstance(existing, dict):
                    if existing == val:
                        print(f"➖ No change: {key} (Value is identical)")
                        return
                    
                    choice = input(f"⚠️ Key '{key}' already exists. Overwrite? (y/n): ").lower().strip()
                    if choice != 'y':
                        print("❌ Aborted.")
                        return
    
                status = kv.save(key, val)
                if status == "created":
                    print(f"✅ Saved: {key} (New)")
                elif status == "overwritten":
                    print(f"🔄 Updated: {key}")
                else:
                    print(f"➖ No change: {key}")
    
            elif prog in ["kyg", "getkey"]:
                if len(args) != 1:
                    print("Usage: kyg <key>")
                    return
                result = kv.getkey(args[0])
                print(result)
    
            elif prog in ["kyv", "history"]:
                # Default to all history if no key is provided
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
                    # Return only the current (latest) value
                    if history:
                        print(history[0][1])
    
            elif prog in ["kyd", "delete"]:
                if len(args) != 1:
                    print("Usage: kyd <key>")
                    return
                print(kv.delete(args[0]))
    
            elif prog in ["kyl", "listkeys"]:
                pattern = args[0] if args else None
                keys = kv.listkeys(pattern)
                if keys:
                    print(f"🔑 Keys: {', '.join(keys)}")
                else:
                    print("No keys found.")
    
            elif prog in ["kyh", "help"]:
                print_help()
            
            elif prog in ["kye", "export"]:
                if len(args) < 1:
                    print("Usage: kye <file> [format]")
                    return
                export_path = args[0]
                export_format = args[1] if len(args) > 1 else "csv"
                kv.export_data(export_path, export_format.lower())
                print(f"📤 Exported data to {export_path} as {export_format.upper()}")
    
            elif prog in ["kyi", "import"]:
                if len(args) != 1:
                    print("Usage: kyi <file>")
                    return
                import_path = args[0]
                if not os.path.exists(import_path):
                    print(f"❌ Error: File not found: {import_path}")
                    return
                kv.import_data(import_path)
                print(f"📥 Imported data from {import_path}")
    
            else:
                print("❌ Invalid command.")
                print_help()

    except ValueError as e:
        print(f"⚠️ Validation Error: {e}")
    except Exception as e:
        print(f"🔥 Unexpected Error: {e}")
        sys.exit(1)