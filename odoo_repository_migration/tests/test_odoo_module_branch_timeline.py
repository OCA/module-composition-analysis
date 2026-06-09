# Copyright 2026  Akretion (https://www.akretion.com).
# @author Sébastien Alix <sebastien.alix@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from .common import MigrationCommon


class TestOdooModuleBranchTimeline(MigrationCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.branch4_name = str(float(cls.branch3.name) + 1)
        cls.branch4 = (
            cls.env["odoo.branch"]
            .with_context(active_test=False)
            .search([("name", "=", cls.branch4_name)])
        )
        if not cls.branch4:
            cls.branch4 = cls.env["odoo.branch"].create(
                {
                    "name": cls.branch4_name,
                }
            )
        cls.repo_branch4 = cls._create_odoo_repository_branch(
            cls.odoo_repository, cls.branch4
        )
        # Create modules A, B, C and D
        cls.module_a = cls.module.copy({"name": "module_a"})
        cls.module_branch_a = cls._create_odoo_module_branch(
            cls.module_a,
            cls.branch,
            specific=False,
            repository_branch_id=cls.repo_branch.id,
            last_scanned_commit="sha_a",
        )
        cls.module_b = cls.module.copy({"name": "module_b"})
        cls.module_branch_b = cls._create_odoo_module_branch(
            cls.module_b,
            cls.branch2,
            specific=False,
            repository_branch_id=cls.repo_branch2.id,
            last_scanned_commit="sha_b",
        )
        cls.module_c = cls.module.copy({"name": "module_c"})
        cls.module_branch_c = cls._create_odoo_module_branch(
            cls.module_c,
            cls.branch3,
            specific=False,
            repository_branch_id=cls.repo_branch3.id,
            last_scanned_commit="sha_c",
        )
        cls.module_d = cls.module.copy({"name": "module_d"})
        cls.module_branch_d = cls._create_odoo_module_branch(
            cls.module_d,
            cls.branch4,
            specific=False,
            repository_branch_id=cls.repo_branch4.id,
            last_scanned_commit="sha_d",
        )

    def test_get_related_timelines(self):
        """Test _get_related_timelines returns all timelines in a chain.

        Data input:
            - module A renamed/replaced to B in X+1
            - module B renamed/replaced to C in X+2
            - module C renamed/replaced to D in X+3

        Expected output:
            - Calling _get_related_timelines on any timeline should return all timelines
        """
        # Create timelines
        timeline_b = self._create_timeline(
            self.module_branch_a, self.module_b, "renamed"
        )
        timeline_c = self._create_timeline(
            self.module_branch_b, self.module_c, "replaced"
        )
        timeline_d = self._create_timeline(
            self.module_branch_c, self.module_d, "renamed"
        )
        # Test from first timeline (A -> B)
        related_timelines = timeline_b._get_related_timelines()
        self.assertIn(timeline_b, related_timelines)
        self.assertIn(timeline_c, related_timelines)
        self.assertIn(timeline_d, related_timelines)
        self.assertEqual(len(related_timelines), 3)
        # Test from second timeline (B -> C)
        related_timelines = timeline_c._get_related_timelines()
        self.assertIn(timeline_b, related_timelines)
        self.assertIn(timeline_c, related_timelines)
        self.assertIn(timeline_d, related_timelines)
        self.assertEqual(len(related_timelines), 3)
        # Test from third (and last) timeline (C -> D)
        related_timelines = timeline_d._get_related_timelines()
        self.assertIn(timeline_b, related_timelines)
        self.assertIn(timeline_c, related_timelines)
        self.assertIn(timeline_d, related_timelines)
        self.assertEqual(len(related_timelines), 3)
