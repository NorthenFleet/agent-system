"""
Shared test configuration — 设置隔离测试数据库
"""
import asyncio
import inspect
import os
import tempfile

_TEST_DB_URL = f"sqlite:///{tempfile.mktemp(suffix='_test.db')}"
os.environ["DATABASE_URL"] = _TEST_DB_URL
os.environ["DISABLE_MODULE_AUTH_FOR_TESTS"] = "true"


def pytest_pyfunc_call(pyfuncitem):
    """Run async test functions without requiring pytest-asyncio."""
    test_func = pyfuncitem.obj
    if not inspect.iscoroutinefunction(test_func):
        return None
    kwargs = {
        name: pyfuncitem.funcargs[name]
        for name in pyfuncitem._fixtureinfo.argnames
    }
    asyncio.run(test_func(**kwargs))
    return True
