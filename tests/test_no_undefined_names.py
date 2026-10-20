"""
Guards against a whole class of bug that unit tests with mocks can miss: a function that uses a
name its module never imports (a NameError that only shows up when that exact code path runs in
the real app). Every function in every module is checked against the names its module defines.
"""
import builtins
import importlib
import pkgutil
import symtable

import gamecubby_api


def _undefined_global_reads(table, module, found):
    for child in table.get_children():
        if child.get_type() == "function":
            for sym in child.get_symbols():
                if sym.is_global() and sym.is_referenced() and not sym.is_assigned():
                    name = sym.get_name()
                    if not hasattr(module, name) and not hasattr(builtins, name):
                        found.append(f"{module.__name__}.{child.get_name()}() uses undefined name '{name}'")
        _undefined_global_reads(child, module, found)


def test_no_function_uses_an_undefined_name():
    found: list[str] = []
    for info in pkgutil.walk_packages(gamecubby_api.__path__, "gamecubby_api."):
        module = importlib.import_module(info.name)
        source = open(module.__file__, encoding="utf-8").read()
        _undefined_global_reads(symtable.symtable(source, module.__file__, "exec"), module, found)
    assert found == []
