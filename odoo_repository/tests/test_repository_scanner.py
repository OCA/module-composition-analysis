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
            "version": self.branch.name,
            "branch": self.branch.name,
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
        self.assertEqual(scanner.path.parts[-2], self.fork_org)
        self.assertEqual(scanner.full_name, f"{self.fork_org}/{self.repo_name}")

    def test_sync(self):
        scanner = self._init_scanner()
        scanner.sync()

    def test_get_odoo_repository_id(self):
        scanner = self._init_scanner()
        repo_id = scanner._get_odoo_repository_id()
        self.assertEqual(repo_id, self.odoo_repository.id)

    def test_get_odoo_branch_id(self):
        scanner = self._init_scanner()
        branch_id = scanner._get_odoo_branch_id(self.branch.name)
        self.assertEqual(branch_id, self.branch.id)

    def test_create_odoo_repository_branch(self):
        scanner = self._init_scanner()
        repo_id = scanner._get_odoo_repository_id()
        branch_id = scanner._get_odoo_branch_id(self.branch.name)
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
        branch_id = scanner._get_odoo_branch_id(self.branch.name)
        repo_branch_id = scanner._create_odoo_repository_branch(repo_id, branch_id)
        repo_branch = self.env["odoo.repository.branch"].browse(repo_branch_id)
        # Nothing has been scanned until now
        self.assertFalse(scanner._get_repo_last_scanned_commit(repo_branch_id))
        # Clone/fetch the repo
        scanner.sync()
        with scanner.repo() as repo:
            last_fetched_commit = scanner._get_last_fetched_commit(
                repo, self.branch.name
            )
            # Simulate the end of scan
            repo_branch.last_scanned_commit = last_fetched_commit
            # Check again
            last_scanned_commit = scanner._get_repo_last_scanned_commit(repo_branch_id)
            self.assertEqual(last_fetched_commit, last_scanned_commit)

    def test_detect_modules_to_scan(self):
        scanner = self._init_scanner()
        scanner._clone()
        repo_id = scanner._get_odoo_repository_id()
        with scanner.repo() as repo:
            res = scanner._detect_modules_to_scan(repo, repo_id)
            self.assertTrue(res)
            self.assertIn("my_module", res["addons_paths"]["."]["modules_to_scan"])

    def test_detect_modules_to_scan_in_addons_path(self):
        scanner = self._init_scanner()
        scanner._clone()
        with scanner.repo() as repo:
            scanner._checkout_branch(repo, self.branch.name)
            repo_id = scanner._get_odoo_repository_id()
            branch_id = scanner._get_odoo_branch_id(self.branch.name)
            repo_branch_id = scanner._create_odoo_repository_branch(repo_id, branch_id)
            last_fetched_commit = scanner._get_last_fetched_commit(
                repo, self.branch.name
            )
            last_scanned_commit = scanner._get_repo_last_scanned_commit(repo_branch_id)
            # Scan the addons_path (root of the repository here)
            modules_to_scan = scanner._detect_modules_to_scan_in_addons_path(
                repo,
                scanner.addons_paths_data[0]["relative_path"],
                repo_branch_id,
                last_fetched_commit,
                last_scanned_commit,
            )
        module = self.addon
        self.assertIn(module, modules_to_scan)

    def test_scan_module(self):
        scanner = self._init_scanner()
        scanner._clone()
        with scanner.repo() as repo:
            scanner._checkout_branch(repo, self.branch.name)
            repo_id = scanner._get_odoo_repository_id()
            branch_id = scanner._get_odoo_branch_id(self.branch.name)
            repo_branch_id = scanner._create_odoo_repository_branch(repo_id, branch_id)
            module_path = self.addon
            remote_branch = f"origin/{self.branch.name}"
            module_tree = repo.tree(remote_branch) / module_path
            last_module_commit = scanner._get_last_commit_of_git_tree(
                remote_branch, module_tree
            )
            # Scan module
            specs = scanner.addons_paths_data[0]
            data = scanner._scan_module(
                repo,
                repo_branch_id,
                module_path,
                last_module_commit,
                specs,
            )
        self.assertTrue(data)
        self.assertTrue(data["code"])
        self.assertTrue(data["manifest"])
        self.assertEqual(data["is_standard"], specs["is_standard"])
        self.assertEqual(data["is_enterprise"], specs["is_enterprise"])
        self.assertEqual(data["is_community"], specs["is_community"])
        self.assertEqual(data["last_scanned_commit"], last_module_commit)
        self.assertIn("1.0.0", data["versions"])
        self.assertEqual(data["versions"]["1.0.0"]["commit"], last_module_commit)
        self.assertFalse(data["versions"]["1.0.0"]["migration_script"])

    def test_push_scanned_data(self):
        scanner = self._init_scanner()
        scanner._clone()
        with scanner.repo() as repo:
            scanner._checkout_branch(repo, self.branch.name)
            repo_id = scanner._get_odoo_repository_id()
            branch_id = scanner._get_odoo_branch_id(self.branch.name)
            repo_branch_id = scanner._create_odoo_repository_branch(repo_id, branch_id)
            module = self.addon
            remote_branch = f"origin/{self.branch.name}"
            module_tree = repo.tree(remote_branch) / module
            last_module_commit = scanner._get_last_commit_of_git_tree(
                remote_branch, module_tree
            )
            specs = scanner.addons_paths_data[0]
            data = scanner._scan_module(
                repo,
                repo_branch_id,
                module,
                last_module_commit,
                specs,
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
                    "is_standard": specs["is_standard"],
                    "is_enterprise": specs["is_enterprise"],
                    "is_community": specs["is_community"],
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
        branch_id = scanner._get_odoo_branch_id(self.branch.name)
        repo_branch_id = scanner._create_odoo_repository_branch(repo_id, branch_id)
        repo_branch = self.env["odoo.repository.branch"].browse(repo_branch_id)
        with scanner.repo() as repo:
            last_repo_commit = scanner._get_last_fetched_commit(repo, self.branch.name)
            self.assertFalse(repo_branch.last_scanned_commit)
            scanner._update_last_scanned_commit(repo_branch_id, last_repo_commit)
            self.assertEqual(repo_branch.last_scanned_commit, last_repo_commit)

    def test_workaround_fs_errors(self):
        scanner = self._init_scanner(workaround_fs_errors=True)
        scanner.sync()
