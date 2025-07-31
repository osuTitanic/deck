
import importlib

def setup() -> None:
    try:
        pytracy = importlib.import_module('pytracy')
        pytracy.enable_tracing(True)
    except ImportError:
        pass
