import importlib
import importlib.machinery
import sys


def test_init_import_error(monkeypatch):
    import kycli

    real_find_spec = importlib.machinery.PathFinder.find_spec

    def fake_find_spec(name, *args, **kwargs):
        if name == "kycli.core.storage":
            return None
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.machinery.PathFinder, "find_spec", staticmethod(fake_find_spec))
    sys.modules.pop("kycli.core.storage", None)
    importlib.reload(kycli)
    assert kycli.Kycore is None

    importlib.reload(kycli)
