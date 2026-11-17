# Copyright 2026  Akretion (https://www.akretion.com).
# @author Sébastien Alix <sebastien.alix@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import psycopg2

from odoo.exceptions import ValidationError
from odoo.tools import mute_logger

from .common import MigrationCommon


class TestOdooModuleBranchTimeline(MigrationCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.branch4_name = str(float(cls.branch3.name) + 1)
        cls.branch4 = cls._activate_odoo_branch(cls.branch4_name)
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

    def test_next_odoo_version_module_branch_archived_timeline(self):
        """An archived timeline is not applied: the next version resolution
        falls back to the same module."""
        timeline = self._create_module_timeline(
            self.module_branch_a, self.module_b, "renamed"
        )
        self.assertEqual(
            self.module_branch_a.next_odoo_version_module_branch_id,
            self.module_branch_b,
        )
        # Archive the timeline: the resolution falls back to the same module
        # (module_a has no branch on the next versions)
        timeline.active = False
        self.assertFalse(self.module_branch_a.next_odoo_version_module_branch_id)

    def test_next_odoo_version_module_branch_draft_timeline(self):
        """A draft timeline is not applied: the next version resolution is
        unchanged until a user confirms it."""
        timeline = self._create_module_timeline(
            self.module_branch_a, self.module_b, "renamed", state="draft"
        )
        self.assertEqual(timeline.state, "draft")
        self.assertFalse(self.module_branch_a.next_odoo_version_module_branch_id)
        # Confirm the timeline: the renaming applies
        timeline.action_confirm()
        self.assertEqual(
            self.module_branch_a.next_odoo_version_module_branch_id,
            self.module_branch_b,
        )
        self.assertEqual(timeline.state, "confirmed")
        # Send the timeline back to draft: the renaming is retracted
        timeline.action_draft()
        self.assertEqual(timeline.state, "draft")
        self.assertFalse(self.module_branch_a.next_odoo_version_module_branch_id)

    def test_draft_timeline_no_migration_refresh(self):
        """Migration data are refreshed (scan reset) only once a timeline is
        confirmed: drafts have no effect on them."""
        self.odoo_repository.collect_migration_data = True
        self.env["odoo.migration.path"].create(
            {
                "source_branch_id": self.branch.id,
                "target_branch_id": self.branch2.id,
            }
        )
        self._simulate_migration_scan(
            "target_commit1",
            source=self.branch,
            target=self.branch2,
            report={"process": "migrate", "results": {}},
        )
        migration = self.module_branch.migration_ids
        self.assertEqual(migration.process, "migrate")
        # A draft timeline renaming the module does not reset the scanned data
        next_module = self.module.copy({"name": "module_draft"})
        timeline = self._create_module_timeline(
            self.module_branch, next_module, "renamed", state="draft"
        )
        self.assertEqual(migration.process, "migrate")
        self.assertEqual(migration.last_target_scanned_commit, "target_commit1")
        # Confirming the timeline resets the migration data: a new scan of
        # the renamed module is required
        timeline.action_confirm()
        self.assertEqual(migration.renamed_to_module_id, next_module)
        self.assertFalse(migration.process)
        self.assertFalse(migration.last_target_scanned_commit)
        # Sending the timeline back to draft retracts its effect
        timeline.action_draft()
        self.assertFalse(migration.renamed_to_module_id)

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
        timeline_b = self._create_module_timeline(
            self.module_branch_a, self.module_b, "renamed"
        )
        timeline_c = self._create_module_timeline(
            self.module_branch_b, self.module_c, "replaced"
        )
        timeline_d = self._create_module_timeline(
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

    def test_get_related_timelines_draft_ignored(self):
        """Draft timelines are ignored by the chain walking."""
        timeline_b = self._create_module_timeline(
            self.module_branch_a, self.module_b, "renamed"
        )
        timeline_draft = self._create_module_timeline(
            self.module_branch_b, self.module_c, "replaced", state="draft"
        )
        related_timelines = timeline_b._get_related_timelines()
        self.assertIn(timeline_b, related_timelines)
        self.assertNotIn(timeline_draft, related_timelines)

    @mute_logger("odoo.sql_db")
    def test_timeline_unicity(self):
        """Only one timeline can exist for a given module branch."""
        timeline = self._create_module_timeline(
            self.module_branch_a, self.module_b, "renamed"
        )
        # A second timeline for the same module branch is rejected
        with self.assertRaises(psycopg2.IntegrityError), self.env.cr.savepoint():
            self._create_module_timeline(self.module_branch_a, self.module_c, "renamed")
        # Archived timelines still hold the unicity slot
        timeline.active = False
        with self.assertRaises(psycopg2.IntegrityError), self.env.cr.savepoint():
            self._create_module_timeline(self.module_branch_a, self.module_c, "renamed")
        # Draft timelines also hold the unicity slot
        self._create_module_timeline(
            self.module_branch_b, self.module_c, "replaced", state="draft"
        )
        with self.assertRaises(psycopg2.IntegrityError), self.env.cr.savepoint():
            self._create_module_timeline(self.module_branch_b, self.module_d, "renamed")

    def test_next_module(self):
        """The new module is required and different from the module."""
        # The new module is required
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.env["odoo.module.branch.timeline"].create(
                {
                    "module_branch_id": self.module_branch_a.id,
                    "timeline_type": "renamed",
                }
            )
        # The new module must be different from the module
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self._create_module_timeline(self.module_branch_a, self.module_a, "renamed")
        # The new module may already exist on the same version as the module
        # (e.g. a module name reused across Odoo versions)
        self._create_module_timeline(self.module_branch_a, self.module, "renamed")
