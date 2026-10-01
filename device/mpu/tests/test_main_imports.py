"""Every name main.py imports from this package must actually exist.

main.py cannot be imported by the suite: it imports arduino.app_utils,
which only exists on the board. That is why a commit was able to ship a
main.py importing comms.lora_uplink.direct_alert_event while leaving the
definition out of the commit - the app could not start, every test passed,
and the next thing to find out would have been a field node.

So the check is made against the source rather than the import: parse the
module, and for every `from <local package> import <name>`, import the
module and look the name up. This is the same discipline as
test_rpc_contract.py reading bridge/schema.md - compare the two copies of
a contract rather than trusting that they agree.
"""

import ast
import importlib
import pathlib

import pytest

MPU_ROOT = pathlib.Path(__file__).resolve().parents[1]

# The packages this check covers. A third-party import is the dependency
# resolver's business; an intra-package one is ours, and is the kind a
# partial commit breaks.
LOCAL_PACKAGES = frozenset(
    {"bridge", "cognition", "comms", "perception", "services"}
)

# Modules the suite never imports, so nothing else would notice. main.py is
# the entry point; bench/ is excluded because it is scratch, by design.
UNIMPORTABLE_ENTRY_POINTS = ("main.py",)


def _local_from_imports(path: pathlib.Path):
    """Every (module, name, lineno) this file pulls out of a local package."""
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.level != 0:
            continue
        if node.module is None:
            continue
        if node.module.split(".")[0] not in LOCAL_PACKAGES:
            continue
        for alias in node.names:
            if alias.name != "*":
                yield node.module, alias.name, node.lineno


def _module_files():
    """Every first-party module, entry points included."""
    seen = []
    for package in sorted(LOCAL_PACKAGES):
        seen.extend(sorted((MPU_ROOT / package).rglob("*.py")))
    for entry in UNIMPORTABLE_ENTRY_POINTS:
        seen.append(MPU_ROOT / entry)
    return [p for p in seen if "__pycache__" not in p.parts]


@pytest.mark.parametrize(
    "path", _module_files(), ids=lambda p: str(p.relative_to(MPU_ROOT)).replace("\\", "/")
)
def test_every_local_import_resolves(path):
    """A from-import of a name that does not exist is an ImportError on boot."""
    missing = []
    for module_name, name, lineno in _local_from_imports(path):
        module = importlib.import_module(module_name)
        if hasattr(module, name):
            continue
        # `from services import config` imports a submodule, which is not an
        # attribute of the package until something has imported it.
        try:
            importlib.import_module(f"{module_name}.{name}")
        except ImportError:
            missing.append(f"line {lineno}: {module_name} has no {name!r}")
    assert not missing, f"{path.relative_to(MPU_ROOT)}\n" + "\n".join(missing)
