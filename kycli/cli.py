import sys
import os
from kycli.kycore import Kycore

def print_help():
    print("""
Available commands:
  kys <key> <value>             - Save key-value
  kyg <key>                     - Get value by key
  kyl                           - List keys
  kyd <key>                     - Delete key
  kye <file> [format]           - Export data to file (default CSV; JSON if specified)
  kyi <file>                    - Import data (auto-detect CSV/JSON by file extension)
  kyh                           - Help
""")

def main():
    kv = Kycore()
    args = sys.argv[1:]
    prog = os.path.basename(sys.argv[0])

    if prog in ["kys", "save"] and len(args) == 2:
        kv.save(args[0], args[1])
        print(f"Saved: {args[0]}")

    elif prog in ["kyg", "getkey"] and len(args) == 1:
        print(kv.getkey(args[0]))

    elif prog in ["kyd", "delete"] and len(args) == 1:
        print(kv.delete(args[0]))

    elif prog in ["kyl", "listkeys"]:
        pattern = args[0] if args else None
        keys = kv.listkeys(pattern)
        print("Keys:", ", ".join(keys))

    elif prog in ["kyh", "help"]:
        print_help()
    
    elif prog in ["kye", "export"] and len(args) >= 1:
        export_path = args[0]
        export_format = args[1] if len(args) > 1 else "csv"
        kv.export_data(export_path, export_format.lower())
        print(f"Exported data to {export_path} as {export_format.upper()}")

    elif prog in ["kyi", "import"] and len(args) == 1:
        import_path = args[0]
        kv.import_data(import_path)
        print(f"Imported data from {import_path}")

    else:
        print("Invalid command or arguments.")
        print_help()