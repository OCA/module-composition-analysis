# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo.exceptions import ValidationError

from .common import Common


class TestOdooModuleBranch(Common):
    def test_constraint_generic_depends_on_specific(self):
        generic_mod = self._create_odoo_module("generic_mod")
        generic_mod_branch = self._create_odoo_module_branch(
            generic_mod, self.branch, specific=False
        )
        specific_mod = self._create_odoo_module("specific_mod")
        specific_mod_branch = self._create_odoo_module_branch(
            specific_mod, self.branch, specific=True
        )
        with self.assertRaises(ValidationError):
            generic_mod_branch.dependency_ids = specific_mod_branch

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

    def test_find(self):
        mb_model = self.env["odoo.module.branch"]
        mod = self._create_odoo_module("my_module")
        repo = self.odoo_repository
        repo2 = self.odoo_repository.copy({"name": "Repo2"})
        # Find orphaned module
        mod_orphaned = mb_model._create_orphaned_module_branch(self.branch, mod)
        self.assertEqual(mb_model._find(self.branch, mod, repo), mod_orphaned)
        # Find generic module
        repo_branch = self._create_odoo_repository_branch(repo, self.branch)
        mod_generic = self._create_odoo_module_branch(
            mod,
            self.branch,
            specific=False,
            repository_branch_id=repo_branch.id,
        )
        self.assertEqual(mb_model._find(self.branch, mod, repo), mod_generic)
        # Find module in current repository
        repo2_branch = self._create_odoo_repository_branch(repo2, self.branch)
        mod_in_repo2 = self._create_odoo_module_branch(
            mod,
            self.branch,
            repository_branch_id=repo2_branch.id,
        )
        self.assertEqual(mb_model._find(self.branch, mod, repo2), mod_in_repo2)
        # While we have 3 modules (hosted in different repos or orphaned)
        self.assertEqual(len(mod.module_branch_ids), 3)
