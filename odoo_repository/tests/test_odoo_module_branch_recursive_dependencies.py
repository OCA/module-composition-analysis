# Copyright 2026 Sébastien Alix
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from .common import Common


class TestOdooModuleBranchRecursiveDependencies(Common):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create modules
        cls.mod_base = cls._create_odoo_module("base")
        cls.mod_a = cls._create_odoo_module("module_a")
        cls.mod_b = cls._create_odoo_module("module_b")
        cls.mod_c = cls._create_odoo_module("module_c")
        cls.mod_d = cls._create_odoo_module("module_d")
        cls.mod_e = cls._create_odoo_module("module_e")
        # Create module branches
        cls.mod_base_branch = cls._create_odoo_module_branch(
            cls.mod_base, cls.branch, is_standard=True
        )
        cls.mod_a_branch = cls._create_odoo_module_branch(cls.mod_a, cls.branch)
        cls.mod_b_branch = cls._create_odoo_module_branch(cls.mod_b, cls.branch)
        cls.mod_c_branch = cls._create_odoo_module_branch(cls.mod_c, cls.branch)
        cls.mod_d_branch = cls._create_odoo_module_branch(cls.mod_d, cls.branch)
        cls.mod_e_branch = cls._create_odoo_module_branch(cls.mod_e, cls.branch)

    def test_get_recursive_dependencies_simple(self):
        """Test _get_recursive_dependencies with a simple dependency chain."""
        self.mod_a_branch.dependency_ids = self.mod_base_branch
        self.mod_b_branch.dependency_ids = self.mod_a_branch
        self.mod_c_branch.dependency_ids = self.mod_b_branch
        # Test recursive dependencies for module_c
        deps = self.mod_c_branch._get_recursive_dependencies()
        self.assertIn(self.mod_base_branch, deps)
        self.assertIn(self.mod_a_branch, deps)
        self.assertIn(self.mod_b_branch, deps)
        self.assertEqual(len(deps), 3)  # base, module_a, module_b

    def test_get_recursive_dependencies_with_domain(self):
        """Test _get_recursive_dependencies with domain filtering."""
        # Create organization
        org_oca = self.env.ref("odoo_repository.odoo_repository_org_oca")
        org_other = self.env["odoo.repository.org"].create({"name": "Other"})
        # Create repositories
        repo_oca = self.env["odoo.repository"].create(
            {
                "org_id": org_oca.id,
                "name": "repo_oca",
                "repo_url": "https://github.com/OCA/repo_oca",
                "clone_url": "https://github.com/OCA/repo_oca",
                "repo_type": "github",
            }
        )
        repo_other = self.env["odoo.repository"].create(
            {
                "org_id": org_other.id,
                "name": "repo_other",
                "repo_url": "https://github.com/Other/repo_other",
                "clone_url": "https://github.com/Other/repo_other",
                "repo_type": "github",
            }
        )
        # Create modules
        mod_oca = self._create_odoo_module("module_oca")
        mod_other = self._create_odoo_module("module_other")
        mod_mixed = self._create_odoo_module("module_mixed")
        # Create repository branches
        repo_oca_branch = self._create_odoo_repository_branch(repo_oca, self.branch)
        repo_other_branch = self._create_odoo_repository_branch(repo_other, self.branch)
        # Create module branches
        mod_oca_branch = self._create_odoo_module_branch(
            mod_oca,
            self.branch,
            repository_branch_id=repo_oca_branch.id,
            dependency_ids=[(4, self.mod_base_branch.id)],
        )
        mod_other_branch = self._create_odoo_module_branch(
            mod_other,
            self.branch,
            repository_branch_id=repo_other_branch.id,
            dependency_ids=[(4, self.mod_base_branch.id)],
        )
        mod_mixed_branch = self._create_odoo_module_branch(
            mod_mixed,
            self.branch,
            repository_branch_id=repo_oca_branch.id,
            dependency_ids=[(4, mod_oca_branch.id), (4, mod_other_branch.id)],
        )
        # Test recursive dependencies with OCA filter
        deps = mod_mixed_branch._get_recursive_dependencies(
            [("org_id", "=", org_oca.id)]
        )
        self.assertIn(mod_oca_branch, deps)
        self.assertNotIn(mod_other_branch, deps)  # filtered out
        # base has no org, so it's filtered out by the domain
        self.assertNotIn(self.mod_base_branch, deps)
        self.assertEqual(len(deps), 1)  # only module_oca

    def test_get_recursive_dependencies_circular_1(self):
        """Test _get_recursive_dependencies handles circular dependencies (1)."""
        # Create module branches with circular dependencies
        # base
        # ├── a ─┐
        # ├── b  │
        # ├── c  │
        # └── d <┘
        self.mod_a_branch.dependency_ids = self.mod_base_branch
        self.mod_b_branch.dependency_ids = self.mod_a_branch
        self.mod_c_branch.dependency_ids = self.mod_b_branch
        self.mod_d_branch.dependency_ids = self.mod_c_branch
        # Create circular dependency: mod_a -> mod_d
        self.mod_a_branch.dependency_ids |= self.mod_d_branch
        # Test recursive dependencies - should not infinite loop
        deps = self.mod_b_branch._get_recursive_dependencies()
        self.assertIn(self.mod_base_branch, deps)
        self.assertIn(self.mod_a_branch, deps)
        self.assertIn(self.mod_b_branch, deps)
        self.assertIn(self.mod_c_branch, deps)
        self.assertIn(self.mod_d_branch, deps)
        # Check that we get the expected dependencies
        # We expect base, a, b, c, d (mod_b is part from its own dependencies)
        self.assertEqual(len(deps), 5)

    def test_get_recursive_dependencies_circular_2(self):
        """Test _get_recursive_dependencies handles circular dependencies (2)."""
        # Create module branches with circular dependencies
        # base
        # ├── a ─┐
        # ├── b  │
        # ├── c <┘
        # └── d
        self.mod_a_branch.dependency_ids = self.mod_base_branch
        self.mod_b_branch.dependency_ids = self.mod_a_branch
        self.mod_c_branch.dependency_ids = self.mod_b_branch
        self.mod_d_branch.dependency_ids = self.mod_c_branch
        # Create circular dependency: mod_a -> mod_d
        self.mod_a_branch.dependency_ids |= self.mod_c_branch
        # Test recursive dependencies - should not infinite loop
        deps = self.mod_d_branch._get_recursive_dependencies()
        self.assertIn(self.mod_base_branch, deps)
        self.assertIn(self.mod_a_branch, deps)
        self.assertIn(self.mod_b_branch, deps)
        self.assertIn(self.mod_c_branch, deps)
        self.assertNotIn(self.mod_d_branch, deps)
        # Check that we get the expected dependencies
        # We expect base, a, b, c (mod_d is excluded from its own dependencies)
        self.assertEqual(len(deps), 4)

    def test_get_recursive_dependencies_complex_tree(self):
        """Test _get_recursive_dependencies with complex dependency tree."""
        # Create module branches with complex dependencies:
        # base
        # ├── a
        # │   ├── c
        # │   └── d
        # └── b
        #     └── e
        self.mod_a_branch.dependency_ids = self.mod_base_branch
        self.mod_b_branch.dependency_ids = self.mod_base_branch
        self.mod_c_branch.dependency_ids = self.mod_a_branch
        self.mod_d_branch.dependency_ids = self.mod_a_branch
        self.mod_e_branch.dependency_ids = self.mod_b_branch
        # Test from module_c
        deps_c = self.mod_c_branch._get_recursive_dependencies()
        self.assertIn(self.mod_base_branch, deps_c)
        self.assertIn(self.mod_a_branch, deps_c)
        self.assertNotIn(self.mod_b_branch, deps_c)
        self.assertNotIn(self.mod_c_branch, deps_c)
        self.assertNotIn(self.mod_d_branch, deps_c)
        self.assertNotIn(self.mod_e_branch, deps_c)
        self.assertEqual(len(deps_c), 2)  # base, module_a
        # Test from module_e
        deps_e = self.mod_e_branch._get_recursive_dependencies()
        self.assertIn(self.mod_base_branch, deps_e)
        self.assertIn(self.mod_b_branch, deps_e)
        self.assertNotIn(self.mod_a_branch, deps_e)
        self.assertNotIn(self.mod_c_branch, deps_e)
        self.assertNotIn(self.mod_d_branch, deps_e)
        self.assertEqual(len(deps_e), 2)  # base, module_b

    def test_get_recursive_dependencies_empty(self):
        """Test _get_recursive_dependencies with no dependencies."""
        # Create module with no dependencies
        mod_alone = self._create_odoo_module("module_alone")
        mod_alone_branch = self._create_odoo_module_branch(mod_alone, self.branch)
        # Test recursive dependencies
        deps = mod_alone_branch._get_recursive_dependencies()
        self.assertEqual(len(deps), 0)

    def test_get_recursive_dependencies_self_exclusion(self):
        """Test that _get_recursive_dependencies excludes self."""
        # Create modules
        mod_self = self._create_odoo_module("module_self")
        # Create module branches
        mod_self_branch = self._create_odoo_module_branch(
            mod_self, self.branch, dependency_ids=[(4, self.mod_base_branch.id)]
        )
        # Test recursive dependencies - self should not be included
        deps = mod_self_branch._get_recursive_dependencies()
        self.assertIn(self.mod_base_branch, deps)
        self.assertNotIn(mod_self_branch, deps)
        self.assertEqual(len(deps), 1)
