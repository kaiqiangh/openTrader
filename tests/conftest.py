import asyncio
import inspect
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_pyfunc_call(pyfuncitem):  # type: ignore[no-untyped-def]
    """Minimal asyncio test runner fallback for environments without pytest-asyncio."""

    test_function = pyfuncitem.obj
    if not inspect.iscoroutinefunction(test_function):
        return None

    kwargs = {
        arg_name: pyfuncitem.funcargs[arg_name]
        for arg_name in pyfuncitem._fixtureinfo.argnames
        if arg_name in pyfuncitem.funcargs
    }
    asyncio.run(test_function(**kwargs))
    return True
