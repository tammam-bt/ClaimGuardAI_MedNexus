"""Importing this package registers every rule module automatically.

Drop in r007.py with an @rule("R007") function and it registers itself. There
is no central list to edit, so two people adding two rules never conflict.
Modules starting with an underscore (e.g. _template.py) are skipped.
"""
import importlib
import pkgutil

for _finder, _name, _ispkg in pkgutil.iter_modules(__path__):
    if not _name.startswith("_"):
        importlib.import_module(f"{__name__}.{_name}")
