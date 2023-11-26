# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo.addons.odoo_repository.utils.scanner import RepositoryScannerOdooEnv

from .common import Common


class TestRepositoryScanner(Common):
    def _init_scanner(self, **params):
        kwargs = {
            "org": self.org.name,
            "name": self.repo_name,
            "clone_url": self.repo_upstream_path,
            "branches": [self.branch.name],
            "addons_paths_data": [
                {
                    "relative_path": ".",
                    "is_standard": False,
                    "is_enterprise": False,
                    "is_community": True,
                },
            ],
            "repositories_path": self.repositories_path,
            "env": self.env,
        }
        if params:
            kwargs.update(params)
        return RepositoryScannerOdooEnv(**kwargs)

    def test_init(self):
        scanner = self._init_scanner()
        self.assertTrue(scanner.repositories_path.exists())
        self.assertEqual(scanner.path.parts[-1], self.repo_name)
        self.assertEqual(scanner.path.parts[-2], self._settings["user_org"])
        self.assertEqual(
            scanner.full_name, f"{self._settings['user_org']}/{self.repo_name}"
        )

    def test_scan(self):
        scanner = self._init_scanner()
        scanner.scan()

    def test_get_odoo_repository_id(self):
        scanner = self._init_scanner()
        repo_id = scanner._get_odoo_repository_id()
        self.assertEqual(repo_id, self.odoo_repository.id)

    def test_get_odoo_branch_id(self):
        scanner = self._init_scanner()
        repo_id = scanner._get_odoo_repository_id()
        branch_id = scanner._get_odoo_branch_id(repo_id, self.branch.name)
        self.assertEqual(branch_id, self.branch.id)

    def test_create_odoo_repository_branch(self):
        scanner = self._init_scanner()
        repo_id = scanner._get_odoo_repository_id()
        branch_id = scanner._get_odoo_branch_id(repo_id, self.branch.name)
        # The repository branch doesn't exist yet
        expected_repo_branch_id = scanner._get_odoo_repository_branch_id(
            repo_id, branch_id
        )
        self.assertFalse(expected_repo_branch_id)
        # Create it
        repo_branch_id = scanner._create_odoo_repository_branch(repo_id, branch_id)
        self.assertTrue(repo_branch_id)
        self.assertEqual(
            repo_branch_id, scanner._get_odoo_repository_branch_id(repo_id, branch_id)
        )

    def test_get_repo_last_scanned_commit(self):
        scanner = self._init_scanner()
        repo_id = scanner._get_odoo_repository_id()
        branch_id = scanner._get_odoo_branch_id(repo_id, self.branch.name)
        repo_branch_id = scanner._create_odoo_repository_branch(repo_id, branch_id)
        # Nothing has been scanned until now
        self.assertFalse(scanner._get_repo_last_scanned_commit(repo_branch_id))
        # Launch the scan and check again
        scanner.scan()
        last_fetched_commit = scanner._get_last_fetched_commit(self.branch.name)
        last_scanned_commit = scanner._get_repo_last_scanned_commit(repo_branch_id)
        self.assertEqual(last_fetched_commit, last_scanned_commit)

    def test_scan_addons_path(self):
        scanner = self._init_scanner()
        scanner._clone()
        scanner._checkout_branch(self.branch.name)
        repo_id = scanner._get_odoo_repository_id()
        branch_id = scanner._get_odoo_branch_id(repo_id, self.branch.name)
        repo_branch_id = scanner._create_odoo_repository_branch(repo_id, branch_id)
        last_fetched_commit = scanner._get_last_fetched_commit(self.branch.name)
        last_scanned_commit = scanner._get_repo_last_scanned_commit(repo_branch_id)
        # Scan the addons_path (root of the repository here)
        modules_scanned = scanner._scan_addons_path(
            scanner.addons_paths_data[0],
            self.branch.name,
            repo_branch_id,
            last_fetched_commit,
            last_scanned_commit,
        )
        module = self._settings["addon"]
        self.assertIn(module, modules_scanned)
        self.assertTrue(modules_scanned[module])

    def test_scan_module(self):
        scanner = self._init_scanner()
        scanner._clone()
        scanner._checkout_branch(self.branch.name)
        repo_id = scanner._get_odoo_repository_id()
        branch_id = scanner._get_odoo_branch_id(repo_id, self.branch.name)
        repo_branch_id = scanner._create_odoo_repository_branch(repo_id, branch_id)
        module_path = self._settings["addon"]
        remote_branch = f"origin/{self.branch.name}"
        module_tree = scanner.repo.tree(remote_branch) / module_path
        last_module_commit = scanner._get_last_commit_of_git_tree(
            remote_branch, module_tree
        )
        # Scan module
        addons_path_data = scanner.addons_paths_data[0]
        data = scanner._scan_module(
            self.branch.name,
            repo_branch_id,
            module_path,
            last_module_commit,
            addons_path_data,
        )
        self.assertTrue(data)
        self.assertTrue(data["code"])
        self.assertTrue(data["manifest"])
        self.assertEqual(data["is_standard"], addons_path_data["is_standard"])
        self.assertEqual(data["is_enterprise"], addons_path_data["is_enterprise"])
        self.assertEqual(data["is_community"], addons_path_data["is_community"])
        self.assertEqual(data["last_scanned_commit"], last_module_commit)
        self.assertIn("1.0.0", data["versions"])
        self.assertEqual(data["versions"]["1.0.0"]["commit"], last_module_commit)
        self.assertFalse(data["versions"]["1.0.0"]["migration_script"])

    def test_push_scanned_data(self):
        scanner = self._init_scanner()
        scanner._clone()
        scanner._checkout_branch(self.branch.name)
        repo_id = scanner._get_odoo_repository_id()
        branch_id = scanner._get_odoo_branch_id(repo_id, self.branch.name)
        repo_branch_id = scanner._create_odoo_repository_branch(repo_id, branch_id)
        module = self._settings["addon"]
        remote_branch = f"origin/{self.branch.name}"
        module_tree = scanner.repo.tree(remote_branch) / module
        last_module_commit = scanner._get_last_commit_of_git_tree(
            remote_branch, module_tree
        )
        addons_path_data = scanner.addons_paths_data[0]
        data = scanner._scan_module(
            self.branch.name,
            repo_branch_id,
            module,
            last_module_commit,
            addons_path_data,
        )
        # Push scanned data
        module_branch = scanner._push_scanned_data(repo_branch_id, module, data)
        self.assertEqual(module_branch.module_id.name, module)
        self.assertEqual(module_branch.repository_branch_id.id, repo_branch_id)
        self.assertRecordValues(
            module_branch,
            [
                {
                    "repository_branch_id": repo_branch_id,
                    "is_standard": addons_path_data["is_standard"],
                    "is_enterprise": addons_path_data["is_enterprise"],
                    "is_community": addons_path_data["is_community"],
                    "application": data["manifest"].get("application", False),
                    "installable": data["manifest"]["installable"],
                    "sloc_python": data["code"]["Python"],
                    "sloc_xml": data["code"]["XML"],
                    "sloc_js": data["code"]["JavaScript"],
                    "sloc_css": data["code"]["CSS"],
                    "last_scanned_commit": last_module_commit,
                }
            ],
        )

    def test_update_last_scanned_commit(self):
        scanner = self._init_scanner()
        scanner._clone()
        repo_id = scanner._get_odoo_repository_id()
        branch_id = scanner._get_odoo_branch_id(repo_id, self.branch.name)
        repo_branch_id = scanner._create_odoo_repository_branch(repo_id, branch_id)
        repo_branch = self.env["odoo.repository.branch"].browse(repo_branch_id)
        last_repo_commit = scanner._get_last_fetched_commit(self.branch.name)
        self.assertFalse(repo_branch.last_scanned_commit)
        scanner._update_last_scanned_commit(repo_branch_id, last_repo_commit)
        self.assertEqual(repo_branch.last_scanned_commit, last_repo_commit)

    def test_scan_branch(self):
        scanner = self._init_scanner()
        scanner._clone()
        repo_id = scanner._get_odoo_repository_id()
        # First scan: new commits detected
        res = scanner._scan_branch(repo_id, self.branch.name)
        self.assertTrue(res)
        # Second scan: no new commits to scan
        res = scanner._scan_branch(repo_id, self.branch.name)
        self.assertFalse(res)
