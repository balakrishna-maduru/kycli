try:
    from .core.storage import Kycore
except ImportError:
    # Handle the case where the .so files aren't built yet
    # or it's being imported during the build process
    try:
        from .kycore import Kycore
    except ImportError:
        Kycore = None

__all__ = ["Kycore"]
