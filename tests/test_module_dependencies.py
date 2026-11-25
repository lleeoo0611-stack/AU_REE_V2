"""Protect the production module boundaries, including function-local imports."""

import ast
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
import unittest


PACKAGE = "au_ree_v2"
SOURCE = Path(__file__).resolve().parents[1] / "src" / PACKAGE


class ModuleDependenciesTests(unittest.TestCase):
    def test_production_imports_form_a_directed_acyclic_graph(self):
        modules = {path.stem: path for path in SOURCE.glob("*.py")}
        dependencies = {}
        for module, path in modules.items():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            targets = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    targets.update(
                        alias.name.split(".")[1] for alias in node.names
                        if alias.name.startswith(PACKAGE + ".")
                    )
                elif isinstance(node, ast.ImportFrom):
                    if node.level == 1:
                        if node.module is None:
                            targets.update(alias.name for alias in node.names)
                        else:
                            targets.add(node.module.split(".")[0])
                    elif node.level == 0 and node.module == PACKAGE:
                        targets.update(alias.name for alias in node.names)
                    elif node.level == 0 and node.module.startswith(PACKAGE + "."):
                        targets.add(node.module.split(".")[1])
            dependencies[module] = targets.intersection(modules)

        try:
            list(TopologicalSorter(dependencies).static_order())
        except CycleError as exc:
            self.fail("Circular imports: " + " -> ".join(exc.args[1]))
