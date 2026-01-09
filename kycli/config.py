import os
import json
import shutil

try:
    import tomllib as toml  # Python 3.11+
except ImportError:
    try:
        import tomli as toml
    except ImportError:
        toml = None

KYCLI_DIR = os.path.expanduser("~/.kycli")
DATA_DIR = os.path.join(KYCLI_DIR, "data")
CONFIG_PATH = os.path.join(KYCLI_DIR, "config.json")

DEFAULT_CONFIG = {
    "active_workspace": "default",
    "export_format": "csv",
    "theme": {
        "key": "cyan",
        "value": "green",
        "timestamp": "dim white",
        "error": "bold red",
        "success": "bold green"
    }
}

def ensure_dirs():
    """Ensure .kycli and .kycli/data exist."""
    os.makedirs(DATA_DIR, exist_ok=True)

def migrate_legacy_db():
    """Move legacy ~/kydata.db to ~/.kycli/data/default.db if it exists and default.db doesn't."""
    legacy_path = os.path.expanduser("~/kydata.db")
    default_db_path = os.path.join(DATA_DIR, "default.db")
    
    if os.path.exists(legacy_path) and not os.path.exists(default_db_path):
        try:
            ensure_dirs()
            shutil.move(legacy_path, default_db_path)
            # print(f"📦 Migrated legacy database to {default_db_path}")
        except Exception:
            pass

def save_config(updates):
    """Update and save configuration to ~/.kycli/config.json."""
    ensure_dirs()
    current = load_raw_config()
    current.update(updates)
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(current, f, indent=4)
    except Exception:
        pass

def load_raw_config():
    """Load config from disk without dynamic processing."""
    config = DEFAULT_CONFIG.copy()
    
    # Check ~/.kycli/config.json (New standard)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                config.update(json.load(f))
        except Exception:
            pass
            
    # Legacy .kyclirc checking (fallback)
    rc_paths = [".kyclirc", ".kyclirc.json", os.path.expanduser("~/.kyclirc"), os.path.expanduser("~/.kyclirc.json")]
    for path in rc_paths:
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    if path.endswith(".json"):
                        config.update(json.load(f))
                    elif toml:
                        config.update(toml.load(f))
            except: pass
            break
            
    return config

def load_config():
    ensure_dirs()
    migrate_legacy_db()
    
    config = load_raw_config()

    # Environment variables override config
    env_db_path = os.environ.get("KYCLI_DB_PATH")
    if env_db_path:
        config["db_path"] = os.path.expanduser(env_db_path)
    else:
        # Resolve db_path based on active workspace
        workspace = config.get("active_workspace", "default")
        safe_ws = "".join(c for c in workspace if c.isalnum() or c in ("_", "-"))
        if not safe_ws: safe_ws = "default"
        config["db_path"] = os.path.join(DATA_DIR, f"{safe_ws}.db")

    return config

def get_workspaces():
    """Return list of available workspaces."""
    ensure_dirs()
    files = [f for f in os.listdir(DATA_DIR) if f.endswith(".db")]
    return sorted([f[:-3] for f in files])
