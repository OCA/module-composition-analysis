# Copyright 2026 Sébastien Alix
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.addons.odoo_repository.utils.module import adapt_version

from .common import Common

COMMIT_1 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
COMMIT_2 = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


class TestOdooModuleBranchVersion(Common):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.version_model = cls.env["odoo.module.branch.version"]
        # Odoo branches ordered by sequence: '18.0' < '19.0' < '20.0'
        cls.branch_older = cls._activate_odoo_branch("18.0")
        cls.branch_current = cls._activate_odoo_branch("19.0")
        cls.branch_newer = cls._activate_odoo_branch("20.0")
        # Module and module branches (one per Odoo branch)
        cls.module = cls._create_odoo_module("my_module")
        cls.module_branch_older = cls._create_odoo_module_branch(
            cls.module, cls.branch_older
        )
        cls.module_branch_current = cls._create_odoo_module_branch(
            cls.module, cls.branch_current
        )
        cls.module_branch_newer = cls._create_odoo_module_branch(
            cls.module, cls.branch_newer
        )
        # Repository branches
        cls.repo_branch_older = cls._create_odoo_repository_branch(
            cls.odoo_repository, cls.branch_older
        )
        cls.repo_branch_current = cls._create_odoo_repository_branch(
            cls.odoo_repository, cls.branch_current
        )
        cls.repo_branch_newer = cls._create_odoo_repository_branch(
            cls.odoo_repository, cls.branch_newer
        )

    def _create_version(self, module_branch, manifest_value, commit=False, **values):
        vals = {
            "module_branch_id": module_branch.id,
            "name": adapt_version(module_branch.branch_id.name, manifest_value),
            "manifest_value": manifest_value,
            "commit": commit,
        }
        vals.update(values)
        return self.version_model.create(vals)

    def _scan_versions(self, module_branch, repo_branch, versions):
        """Simulate a scan pushing `versions` data on `module_branch`."""
        version_ids = module_branch._prepare_module_branch_version_ids_values(
            repo_branch, module_branch, self.module, versions
        )
        # Apply the commands as '_create_or_update' would do
        module_branch.write({"version_ids": version_ids})
        self.env.flush_all()
        return version_ids

    # New version

    def test_scan_new_version(self):
        """A version never scanned before is created on the module branch.

        Example:
            - scanning '19.0' finds the version '1.0.0' introduced by the
              commit C, and no version record exists for 'my_module' on this
              branch;
            - a version record bound to the commit C is created for '19.0'.
        """
        versions = {"1.0.0": {"commit": COMMIT_1, "migration_script": False}}
        self._scan_versions(
            self.module_branch_current, self.repo_branch_current, versions
        )
        version = self.module_branch_current.version_ids
        self.assertEqual(len(version), 1)
        self.assertEqual(version.manifest_value, "1.0.0")
        self.assertEqual(version.name, "19.0.1.0.0")
        self.assertEqual(version.commit, COMMIT_1)
        self.assertFalse(version.has_migration_script)

    def test_scan_same_version_twice(self):
        """Scanning again a version already known on the branch updates it.

        Example:
            - the version '1.0.0' of 'my_module' has already been scanned on
              the '19.0' branch (introduced by the commit C);
            - scanning '19.0' again finds the same version introduced by the
              same commit: the existing version record is updated (e.g. its
              'has_migration_script' value), no duplicate is created.
        """
        self._create_version(self.module_branch_current, "1.0.0", commit=COMMIT_1)
        versions = {"1.0.0": {"commit": COMMIT_1, "migration_script": True}}
        self._scan_versions(
            self.module_branch_current, self.repo_branch_current, versions
        )
        version = self.module_branch_current.version_ids
        self.assertEqual(len(version), 1)
        self.assertEqual(version.commit, COMMIT_1)
        self.assertTrue(version.has_migration_script)

    # Version already imported for a previous Odoo release

    def test_scan_version_from_previous_odoo_release(self):
        """A version imported on an older branch is also created, w/o commit.

        The commit that introduced the version is bound to the older branch
        only, as the current branch inherited this version from it.

        Example:
            - the version '0.1' of 'my_module' has been introduced by the
              commit C on the '18.0' branch;
            - the '19.0' branch has been forked from '18.0', so the commit C
              is also part of its history;
            - scanning '19.0' finds the version '0.1' introduced by C, but as
              C is older than the fork, the version record created for '19.0'
              holds no commit: C remains bound to the '18.0' version record.
        """
        self._create_version(self.module_branch_older, "0.1", commit=COMMIT_1)
        versions = {"0.1": {"commit": COMMIT_1, "migration_script": True}}
        self._scan_versions(
            self.module_branch_current, self.repo_branch_current, versions
        )
        version = self.module_branch_current.version_ids
        self.assertEqual(len(version), 1)
        self.assertEqual(version.name, "19.0.0.1")
        self.assertEqual(version.manifest_value, "0.1")
        self.assertFalse(version.commit)
        self.assertTrue(version.has_migration_script)
        # The version of the older branch is untouched
        older_version = self.module_branch_older.version_ids
        self.assertEqual(len(older_version), 1)
        self.assertEqual(older_version.commit, COMMIT_1)

    def test_scan_version_from_previous_odoo_release_with_placeholder(self):
        """A version imported on an older branch updates the local placeholder.

        The placeholder has been created by a scan done without version
        history (no commit known at that time).

        Example:
            - the version '0.1' of 'my_module' has been introduced by the
              commit C on the '18.0' branch;
            - a first scan of the '19.0' branch (done without version
              history) created a version record for '0.1' without commit;
            - scanning '19.0' again finds the version '0.1' introduced by C:
              the placeholder is updated (e.g. its 'has_migration_script' value
              is refreshed) but still holds no commit, as C belongs to the
              '18.0' version record.
        """
        self._create_version(self.module_branch_older, "0.1", commit=COMMIT_1)
        placeholder = self._create_version(self.module_branch_current, "0.1")
        versions = {"0.1": {"commit": COMMIT_1, "migration_script": True}}
        self._scan_versions(
            self.module_branch_current, self.repo_branch_current, versions
        )
        self.assertEqual(self.module_branch_current.version_ids, placeholder)
        self.assertFalse(placeholder.commit)
        self.assertTrue(placeholder.has_migration_script)
        # The version of the older branch is untouched
        self.assertEqual(self.module_branch_older.version_ids.commit, COMMIT_1)

    # Version already imported through a newer Odoo release

    def test_scan_version_imported_on_newer_branch(self):
        """A version imported on a newer branch is created with its commit.

        The commit that introduced the version belongs to the current branch
        (the oldest one holding this version): the version record of the
        newer branch is kept, but its commit is reset.

        Example:
            - the version '0.1' of 'my_module' has been introduced by the
              commit C, and bound to the '20.0' version record (this branch
              has been scanned first);
            - scanning '19.0' finds the version '0.1' introduced by C: as
              '19.0' is older than '20.0', the commit belongs to it;
            - a version record bound to C is created for '19.0', and the
              commit of the '20.0' version record is reset (the record is
              kept).
        """
        newer_version = self._create_version(
            self.module_branch_newer, "0.1", commit=COMMIT_1
        )
        versions = {"0.1": {"commit": COMMIT_1, "migration_script": False}}
        self._scan_versions(
            self.module_branch_current, self.repo_branch_current, versions
        )
        version = self.module_branch_current.version_ids
        self.assertEqual(len(version), 1)
        self.assertEqual(version.name, "19.0.0.1")
        self.assertEqual(version.manifest_value, "0.1")
        self.assertEqual(version.commit, COMMIT_1)
        # The version imported on the newer branch is kept, without commit
        self.assertTrue(newer_version.exists())
        self.assertEqual(newer_version.module_branch_id, self.module_branch_newer)
        self.assertFalse(newer_version.commit)

    def test_scan_version_imported_on_newer_branch_with_placeholder(self):
        """A version imported on a newer branch updates the local placeholder.

        This is the corner case that used to raise a 'duplicate key value
        violates unique constraint' error, as the version record of the newer
        branch was moved to the current module branch instead of being merged
        into the existing placeholder.

        Example:
            - the version '0.1' of 'my_module' has been introduced by the
              commit C, and bound to the '20.0' version record;
            - a first scan of the '19.0' branch (done without version
              history) created a version record for '0.1' without commit;
            - scanning '19.0' finds the version '0.1' introduced by C: the
              placeholder is updated with the commit C, and the commit of the
              '20.0' version record is reset (the record is kept);
            - scanning '19.0' again (e.g. a forced re-scan) finds nothing
              left to reset: the version records are left unchanged.
        """
        newer_version = self._create_version(
            self.module_branch_newer, "0.1", commit=COMMIT_1
        )
        placeholder = self._create_version(self.module_branch_current, "0.1")
        versions = {"0.1": {"commit": COMMIT_1, "migration_script": True}}
        self._scan_versions(
            self.module_branch_current, self.repo_branch_current, versions
        )
        # The placeholder has been updated with the scanned data
        self.assertEqual(self.module_branch_current.version_ids, placeholder)
        self.assertEqual(placeholder.commit, COMMIT_1)
        self.assertTrue(placeholder.has_migration_script)
        # The version imported on the newer branch is kept, without commit
        self.assertTrue(newer_version.exists())
        self.assertFalse(newer_version.commit)
        # Scanning the same data again doesn't change anything
        self._scan_versions(
            self.module_branch_current, self.repo_branch_current, versions
        )
        self.assertEqual(self.module_branch_current.version_ids, placeholder)
        self.assertEqual(placeholder.commit, COMMIT_1)
        self.assertTrue(placeholder.has_migration_script)
        self.assertTrue(newer_version.exists())
        self.assertFalse(newer_version.commit)

    def test_scan_version_imported_on_newer_branch_with_same_commit(self):
        """The version of the current branch wins over the newer branch's one.

        The existing version lookup returns the record of the newest branch
        first: the commit must be reset on this record, not on the one of the
        current branch.

        Example:
            - the version '0.1' of 'my_module' has been introduced by the
              commit C, and bound to both the '19.0' and '20.0' version
              records;
            - scanning '19.0' finds the version '0.1' introduced by C: the
              lookup returns the '20.0' record first (newest branch first),
              so its commit is reset, while the '19.0' record keeps C.
        """
        newer_version = self._create_version(
            self.module_branch_newer, "0.1", commit=COMMIT_1
        )
        current_version = self._create_version(
            self.module_branch_current, "0.1", commit=COMMIT_1
        )
        versions = {"0.1": {"commit": COMMIT_1, "migration_script": False}}
        self._scan_versions(
            self.module_branch_current, self.repo_branch_current, versions
        )
        self.assertEqual(self.module_branch_current.version_ids, current_version)
        self.assertEqual(current_version.commit, COMMIT_1)
        self.assertTrue(newer_version.exists())
        self.assertFalse(newer_version.commit)

    def test_scan_version_imported_on_newer_branch_keeps_migration_script(self):
        """The 'has_migration_script' value of the newer branch is kept.

        This value is specific to each branch (the scanner looks for the
        migration script folder in the branch itself), so resetting the
        commit must not reset it.

        Example:
            - the version '0.1' of 'my_module' has been introduced by the
              commit C, and bound to the '20.0' version record, which has a
              migration script;
            - scanning '19.0' finds the version '0.1' introduced by C: the
              '19.0' version record is created without migration script, and
              the '20.0' record is kept with its commit reset but its
              migration script flag untouched.
        """
        newer_version = self._create_version(
            self.module_branch_newer,
            "0.1",
            commit=COMMIT_1,
            has_migration_script=True,
        )
        versions = {"0.1": {"commit": COMMIT_1, "migration_script": False}}
        self._scan_versions(
            self.module_branch_current, self.repo_branch_current, versions
        )
        # The current branch knows the version without migration script
        self.assertFalse(self.module_branch_current.version_ids.has_migration_script)
        # The newer branch keeps its own migration script flag
        self.assertTrue(newer_version.has_migration_script)
        self.assertFalse(newer_version.commit)

    # Version belonging to another Odoo release

    def test_scan_version_of_other_odoo_release(self):
        """A version belonging to another Odoo release is skipped.

        Example:
            - the scan of the '19.0' branch returns the versions '18.0.1.0'
              and '20.0.1.0' (e.g. found in the history of another branch);
            - as they belong to the '18.0' and '20.0' Odoo releases, no
              version record is created for the '19.0' branch.
        """
        versions = {
            "18.0.1.0": {"commit": COMMIT_1, "migration_script": False},
            "20.0.1.0": {"commit": COMMIT_2, "migration_script": False},
        }
        version_ids = self._scan_versions(
            self.module_branch_current, self.repo_branch_current, versions
        )
        self.assertFalse(version_ids)
        self.assertFalse(self.module_branch_current.version_ids)

    # Versions history imported from a previous Odoo release

    def test_scan_versions_history_from_previous_release(self):
        """A mix of inherited and new versions is imported in one scan.

        Example:
            - the version '0.1' of 'my_module' has been introduced by the
              commit C on the '18.0' branch;
            - scanning '19.0' finds the versions '0.1' introduced by C
              (inherited from '18.0'), and '1.0.0' introduced by the commit D
              (specific to '19.0');
            - two version records are created for '19.0': '0.1' without
              commit, and '1.0.0' bound to the commit D with its migration
              script.
        """
        self._create_version(self.module_branch_older, "0.1", commit=COMMIT_1)
        versions = {
            "0.1": {"commit": COMMIT_1, "migration_script": False},
            "1.0.0": {"commit": COMMIT_2, "migration_script": True},
        }
        self._scan_versions(
            self.module_branch_current, self.repo_branch_current, versions
        )
        versions_rows = self.module_branch_current.version_ids
        self.assertEqual(len(versions_rows), 2)
        version_01 = versions_rows.filtered(lambda v: v.manifest_value == "0.1")
        self.assertEqual(version_01.name, "19.0.0.1")
        self.assertFalse(version_01.commit)
        version_100 = versions_rows.filtered(lambda v: v.manifest_value == "1.0.0")
        self.assertEqual(version_100.name, "19.0.1.0.0")
        self.assertEqual(version_100.commit, COMMIT_2)
        self.assertTrue(version_100.has_migration_script)
