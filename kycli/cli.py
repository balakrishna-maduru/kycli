import sys
import os
import pickle
from kycli.kycore import Kycore

DATA_FILE = "kvdata.pkl"

def load_data(kv):
    import os
    if os.path.exists(kv.data_path) and os.path.getsize(kv.data_path) > 0:
        with open(kv.data_path, "rb") as f:
            store_data = pickle.load(f)
        kv.load_store(store_data)

def save_data(kv):
    with open(DATA_FILE, "wb") as f:
        pickle.dump(kv.store, f)

def print_help():
    print("""
Available commands:
  kys <key> <value>     - Save key-value
  kyg <key>             - Get value by key
  kyl                   - List keys
  kyd <key>             - Delete key
  kyh                   - Help
""")

def main():
    kv = Kycore()
    load_data(kv)

    args = sys.argv[1:]
    prog = os.path.basename(sys.argv[0])

    if prog in ["kys", "save"] and len(args) == 2:
        kv.save(args[0], args[1])
        save_data(kv)
        print(f"Saved: {args[0]}")

    elif prog in ["kyg", "getkey"] and len(args) == 1:
        print(kv.getkey(args[0]))

    elif prog in ["kyd", "delete"] and len(args) == 1:
        print(kv.delete(args[0]))
        save_data(kv)

    elif prog in ["kyl", "listkeys"]:
        print("Keys:", ", ".join(kv.listkeys()))

    elif prog in ["kyh", "help"]:
        print_help()

    else:
        print("Invalid command or arguments.")
        print_help()