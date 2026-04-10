# Copyright 2024 Camptocamp SA
# Copyright 2026 Sébastien Alix
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo.addons.odoo_repository.tests import common


class MigrationCommon(common.Common):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.module = cls._create_odoo_module("my_module")
        cls.repo_branch = cls._create_odoo_repository_branch(
            cls.odoo_repository, cls.branch
        )
        cls.repo_branch2 = cls._create_odoo_repository_branch(
            cls.odoo_repository, cls.branch2
        )
        cls.module_branch = cls._create_odoo_module_branch(
            cls.module,
            cls.branch,
            specific=False,
            repository_branch_id=cls.repo_branch.id,
            last_scanned_commit="sha",
        )
        cls.std_repository = cls.env.ref("odoo_repository.odoo_repository_odoo_odoo")
        oca_org = cls.env.ref("odoo_repository.odoo_repository_org_oca")
        cls.oca_repository = cls.env["odoo.repository"].create(
            {
                "org_id": oca_org.id,
                "name": "test-repo",
                "repo_url": "https://github.com/OCA/test-repo",
            }
        )
        cls.gen_repository = cls.env["odoo.repository"].create(
            {
                "name": "new_repo",
                "org_id": cls.odoo_repository.org_id.id,
                "repo_url": "http://example.net/new_repo",
                "specific": False,
                "to_scan": False,
            }
        )
        cls.gen_repository.addons_path_ids = cls.odoo_repository.addons_path_ids

    @classmethod
    def _simulate_migration_scan(cls, target_commit, report=None):
        """Helper method that pushes scanned migration data."""
        data = {
            "module": cls.module_branch.module_name,
            "source_version": cls.branch.name,
            "source_branch": cls.branch.name,
            "target_version": cls.branch2.name,
            "target_branch": cls.branch2.name,
            "source_commit": cls.module_branch.last_scanned_commit,
            "target_commit": target_commit,
        }
        if report is not None:
            data["report"] = report
        return cls.env["odoo.module.branch.migration"].push_scanned_data(
            cls.module_branch.id,
            data,
        )
