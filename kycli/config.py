import os
import json
try:
    import tomllib as toml  # Python 3.11+
except ImportError:
    import tomli as toml

DEFAULT_CONFIG = {
    "db_path": "~/kydata.db",
    "export_format": "csv",
    "theme": {
        "key": "cyan",
        "value": "green",
        "timestamp": "dim white",
        "error": "bold red",
        "success": "bold green"
    }
}

def load_config():
    config = DEFAULT_CONFIG.copy()
    
# Check .kyclirc (TOML or JSON)
    rc_paths = [
        ".kyclirc", 
        ".kyclirc.json", 
        os.path.expanduser("~/.kyclirc"), 
        os.path.expanduser("~/.kyclirc.json")
    ]
    for path in rc_paths:
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    if path.endswith((".toml", "rc")):
                        try:
                            # Try TOML first
                            config.update(toml.load(f))
                        except Exception:
                            # Try JSON
                            f.seek(0)
                            config.update(json.load(f))
                    elif path.endswith(".json"):
                        config.update(json.load(f))
                break # Only load the first one found
            except Exception:
                pass
                
    # Environment variables override config files
    env_db_path = os.environ.get("KYCLI_DB_PATH")
    if env_db_path:
        config["db_path"] = env_db_path

    # Handle home directory expansion for db_path
    if "db_path" in config:
        config["db_path"] = os.path.expanduser(config["db_path"])
        
    return config
