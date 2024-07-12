# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from .common import Common


class TestOdooModuleDependencyLevel(Common):
    def _create_odoo_module(self, name):
        return self.env["odoo.module"].create({"name": name})

    def _create_odoo_module_branch(self, module, branch, **values):
        vals = {
            "module_id": module.id,
            "branch_id": branch.id,
        }
        vals.update(values)
        return self.env["odoo.module.branch"].create(vals)

    def test_dependency_level(self):
        # base module in the dependencies tree
        mod_base = self._create_odoo_module("base")
        mod_base_branch = self._create_odoo_module_branch(
            mod_base, self.branch, is_standard=True
        )
        self.assertEqual(mod_base_branch.global_dependency_level, 1)
        self.assertEqual(mod_base_branch.non_std_dependency_level, 0)
        # add a standard module depending on the base one
        mod_std = self._create_odoo_module("std")
        mod_std_branch = self._create_odoo_module_branch(
            mod_std,
            self.branch,
            is_standard=True,
            dependency_ids=[(4, mod_base_branch.id)],
        )
        self.assertEqual(mod_std_branch.global_dependency_level, 2)
        self.assertEqual(mod_std_branch.non_std_dependency_level, 0)
        # add a non-standard module depending on the std one
        mod_non_std = self._create_odoo_module("non_std")
        mod_non_std_branch = self._create_odoo_module_branch(
            mod_non_std,
            self.branch,
            is_standard=False,
            dependency_ids=[(4, mod_std_branch.id)],
        )
        self.assertEqual(mod_non_std_branch.global_dependency_level, 3)
        self.assertEqual(mod_non_std_branch.non_std_dependency_level, 1)
        # add another one depending on base module
        mod_non_std2 = self._create_odoo_module("non_std2")
        mod_non_std2_branch = self._create_odoo_module_branch(
            mod_non_std2,
            self.branch,
            is_standard=False,
            dependency_ids=[(4, mod_base_branch.id)],
        )
        self.assertEqual(mod_non_std2_branch.global_dependency_level, 2)
        self.assertEqual(mod_non_std2_branch.non_std_dependency_level, 1)
        # add another one depending on non-std module
        mod_non_std3 = self._create_odoo_module("non_std3")
        mod_non_std3_branch = self._create_odoo_module_branch(
            mod_non_std3,
            self.branch,
            is_standard=False,
            dependency_ids=[(4, mod_non_std_branch.id)],
        )
        self.assertEqual(mod_non_std3_branch.global_dependency_level, 4)
        self.assertEqual(mod_non_std3_branch.non_std_dependency_level, 2)
