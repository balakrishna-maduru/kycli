import json


def coerce_value(raw, json_mode="startswith"):
    """Coerce a raw string into int/bool/JSON when applicable.

    json_mode:
      - "startswith": only parse JSON if the string starts with '{' or '['
      - "always": attempt JSON parsing for any non-int/bool string
      - "never": do not attempt JSON parsing
    """
    if not isinstance(raw, str):
        return raw

    if raw.isdigit():
        return int(raw)

    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False

    if json_mode not in ("startswith", "always", "never"):
        json_mode = "startswith"

    if json_mode == "always":
        try:
            return json.loads(raw)
        except Exception:
            return raw

    if json_mode == "startswith":
        stripped = raw.lstrip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                return json.loads(raw)
            except Exception:
                return raw

    return raw


def try_parse_json(raw):
    """Attempt JSON parsing; return original value on failure."""
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return raw
