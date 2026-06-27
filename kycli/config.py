import os
import json
import shutil
import copy

try:
    import tomllib as toml  # type: ignore[assignment]
except ImportError:
    try:
        import tomli as toml  # type: ignore[assignment]
    except ImportError:
        toml = None

KYCLI_DIR = os.path.expanduser("~/.kycli")
DATA_DIR = os.path.join(KYCLI_DIR, "data")
CONFIG_PATH = os.path.join(KYCLI_DIR, "config.json")

DEFAULT_CONFIG = {
    "active_workspace": "default",
    "active_profile": None,
    "profiles": {},
    "export_format": "csv",
    "log_level": "INFO",
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
        
        # Write plain text workspace file for fast shell prompt access
        if "active_workspace" in current:
            ws_path = os.path.join(KYCLI_DIR, "workspace")
            with open(ws_path, "w") as f:
                f.write(current["active_workspace"])
            
    except Exception:
        pass

def load_raw_config():
    """Load config from disk without dynamic processing."""
    config = copy.deepcopy(DEFAULT_CONFIG)
    
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

def _apply_active_profile(config):
    active_profile = config.get("active_profile")
    profiles = config.get("profiles") or {}
    if not active_profile:
        return config
    profile_data = profiles.get(active_profile)
    if not isinstance(profile_data, dict):
        return config

    merged = copy.deepcopy(config)
    for key, value in profile_data.items():
        merged[key] = value
    return merged

def load_config():
    ensure_dirs()
    migrate_legacy_db()
    
    config = _apply_active_profile(load_raw_config())

    # Environment variables override config
    env_db_path = os.environ.get("KYCLI_DB_PATH")
    
    # Determine the data directory to use
    effective_data_dir = DATA_DIR

    if env_db_path:
        expanded_path = os.path.expanduser(env_db_path)
        # Check if it implies a directory or exists as one
        # If it's an existing directory OR it ends with a separator, treat as dir
        if os.path.isdir(expanded_path) or expanded_path.endswith(os.sep):
            effective_data_dir = expanded_path
            os.makedirs(effective_data_dir, exist_ok=True)
        else:
            # It's likely a file path (Legacy behavior or specific file override)
            # If it's a file, we can't support workspaces easily unless we assume it's just for the current one.
            config["db_path"] = expanded_path
            return config

    # Resolve db_path based on active workspace
    workspace = config.get("active_workspace", "default")
    safe_ws = "".join(c for c in workspace if c.isalnum() or c in ("_", "-"))
    if not safe_ws: safe_ws = "default"
    
    config["db_path"] = os.path.join(effective_data_dir, f"{safe_ws}.db")

    return config

def save_profile(name, profile_data):
    if not name or not str(name).strip():
        raise ValueError("Profile name is required")
    current = load_raw_config()
    profiles = current.get("profiles") or {}
    profiles[str(name).strip()] = dict(profile_data or {})
    save_config({"profiles": profiles})

def use_profile(name):
    current = load_raw_config()
    profiles = current.get("profiles") or {}
    if name not in profiles:
        raise ValueError(f"Unknown profile: {name}")
    save_config({"active_profile": name})

def list_profiles():
    current = load_raw_config()
    profiles = current.get("profiles") or {}
    return sorted(profiles.keys())

def get_workspaces():
    """Return list of available workspaces."""
    ensure_dirs()
    files = [f for f in os.listdir(DATA_DIR) if f.endswith(".db")]
    workspaces = set(f[:-3] for f in files)
    
    # Ensure active workspace is always listed (resolves lazy creation visibility)
    config = load_raw_config()
    active = config.get("active_workspace", "default")
    workspaces.add(active)
    
    return sorted(list(workspaces))
