import importlib
import sys
from contextlib import contextmanager
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

SERVICE_MODULE_NAMES = {
    "cluster",
    "engine",
    "hash_ring",
    "main",
    "replicator",
    "router",
    "state",
}


@contextmanager
def service_import_context(service_name: str):
    app_dir = REPO_ROOT / service_name / "app"
    previous_path = list(sys.path)
    previous_modules = {
        name: sys.modules[name]
        for name in SERVICE_MODULE_NAMES
        if name in sys.modules
    }

    for name in SERVICE_MODULE_NAMES:
        sys.modules.pop(name, None)

    sys.path.insert(0, str(app_dir))
    try:
        yield
    finally:
        for name in SERVICE_MODULE_NAMES:
            sys.modules.pop(name, None)
        sys.modules.update(previous_modules)
        sys.path[:] = previous_path


def import_service_module(service_name: str, module_name: str):
    with service_import_context(service_name):
        return importlib.import_module(module_name)
