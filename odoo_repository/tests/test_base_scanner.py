# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import tempfile

from odoo.addons.odoo_repository.lib.scanner import BaseScanner

from .common import Common


class TestBaseScanner(Common):
    def _init_scanner(self, **params):
        kwargs = {
            "org": self.fork_org,
            "name": self.repo_name,
            "clone_url": self.repo_upstream_path,
            "branches": [
                self.branch1_name,
                self.branch2_name,
                self.branch3_name,
            ],
            "repositories_path": self.repositories_path,
        }
        if params:
            kwargs.update(params)
        return BaseScanner(**kwargs)

    def test_init(self):
        scanner = self._init_scanner()
        self.assertTrue(scanner.repositories_path.exists())
        self.assertEqual(scanner.path.parts[-1], self.repo_name)
        self.assertEqual(scanner.path.parts[-2], self.fork_org)
        self.assertEqual(scanner.full_name, f"{self.fork_org}/{self.repo_name}")

    def test_clone_url_github_token(self):
        # Without token
        base_clone_url = "https://github.com/OCA/test"
        scanner = self._init_scanner(repo_type="github", clone_url=base_clone_url)
        self.assertEqual(scanner.clone_url, base_clone_url)
        # With a token
        token = "test"
        scanner = self._init_scanner(
            repo_type="github", clone_url=base_clone_url, token=token
        )
        token_clone_url = f"https://oauth2:{token}@github.com/OCA/test"
        self.assertEqual(scanner.clone_url, token_clone_url)

    def test_sync(self):
        scanner = self._init_scanner(repositories_path=tempfile.mkdtemp())
        # Clone
        self.assertFalse(scanner.path.exists())
        self.assertFalse(scanner.is_cloned)
        scanner.sync()
        self.assertTrue(scanner.is_cloned)
        # Fetch once cloned
        scanner.sync()

    def test_branch_exists(self):
        scanner = self._init_scanner()
        scanner.sync()
        with scanner.repo() as repo:
            self.assertTrue(scanner._branch_exists(repo, self.branch1_name))
            self.assertTrue(scanner._branch_exists(repo, self.branch2_name))
            self.assertTrue(scanner._branch_exists(repo, self.branch3_name))

    def test_checkout_branch(self):
        scanner = self._init_scanner()
        scanner.sync()
        with scanner.repo() as repo:
            branch = self.branch2_name
            branch_sha = repo.refs[f"origin/{branch}"].object.hexsha
            self.assertNotEqual(repo.head.object.hexsha, branch_sha)
            scanner._checkout_branch(repo, branch)
            self.assertEqual(repo.head.object.hexsha, branch_sha)

    def test_get_last_fetched_commit(self):
        scanner = self._init_scanner()
        scanner.sync()
        with scanner.repo() as repo:
            branch1 = self.branch1_name
            branch2 = self.branch2_name
            branch3 = self.branch3_name
            branch1_sha = repo.refs[f"origin/{branch1}"].object.hexsha
            branch2_sha = repo.refs[f"origin/{branch2}"].object.hexsha
            branch3_sha = repo.refs[f"origin/{branch3}"].object.hexsha
            self.assertEqual(
                scanner._get_last_fetched_commit(repo, branch1), branch1_sha
            )
            self.assertEqual(
                scanner._get_last_fetched_commit(repo, branch2), branch2_sha
            )
            self.assertEqual(
                scanner._get_last_fetched_commit(repo, branch3), branch3_sha
            )

    def test_get_module_paths(self):
        scanner = self._init_scanner()
        scanner.sync()
        with scanner.repo() as repo:
            branch = self.branch1_name
            module_paths = scanner._get_module_paths(repo, ".", branch)
            self.assertEqual(len(module_paths), 1)
            self.assertEqual(module_paths[0], self.addon)

    def test_get_module_paths_updated(self):
        scanner = self._init_scanner()
        scanner.sync()
        branch = self.branch1_name
        with scanner.repo() as repo:
            initial_commit = scanner._get_last_fetched_commit(repo, branch)
            # Case where from_commit and to_commit are the same: no change detected
            module_paths = scanner._get_module_paths_updated(
                repo,
                relative_path=".",
                from_commit=initial_commit,
                to_commit=initial_commit,
                branch=branch,
            )
            self.assertFalse(module_paths)
        # Update the upstream repository with a new commit
        self._update_module_version_on_branch(branch, "1.0.1")
        # Module is now detected has updated
        scanner.sync()  # Fetch new commit from upstream repo
        with scanner.repo() as repo:
            last_commit = scanner._get_last_fetched_commit(repo, branch)
            module_paths = scanner._get_module_paths_updated(
                repo,
                relative_path=".",
                from_commit=initial_commit,
                to_commit=last_commit,
                branch=branch,
            )
            self.assertEqual(len(module_paths), 1)
            self.assertEqual(module_paths.pop(), self.addon)

    def test_filter_file_path(self):
        scanner = self._init_scanner()
        self.assertFalse(scanner._filter_file_path("fr.po"))
        self.assertTrue(scanner._filter_file_path("test.py"))

    def test_get_last_commit_of_git_tree(self):
        scanner = self._init_scanner()
        scanner.sync()
        with scanner.repo() as repo:
            branch = self.branch1_name
            remote_branch = f"origin/{branch}"
            module = self.addon
            module_tree = repo.tree(remote_branch) / module
            all_commits = [c.hexsha for c in repo.iter_commits(remote_branch)]
            commit = scanner._get_last_commit_of_git_tree(remote_branch, module_tree)
            self.assertIn(commit, all_commits)

    def test_get_commits_of_git_tree(self):
        scanner = self._init_scanner()
        scanner.sync()
        with scanner.repo() as repo:
            branch = self.branch1_name
            remote_branch = f"origin/{branch}"
            module = self.addon
            module_tree = repo.tree(remote_branch) / module
            all_commits = [c.hexsha for c in repo.iter_commits(remote_branch)]
            commits = scanner._get_commits_of_git_tree(
                from_=None, to_=remote_branch, tree=module_tree
            )
            for commit in commits:
                self.assertIn(commit, all_commits)

    def test_odoo_module(self):
        scanner = self._init_scanner()
        scanner.sync()
        with scanner.repo() as repo:
            branch = self.branch1_name
            remote_branch = f"origin/{branch}"
            module = self.addon
            module_tree = repo.tree(remote_branch) / module
            self.assertTrue(scanner._odoo_module(module_tree))

    def test_manifest_exists(self):
        scanner = self._init_scanner()
        scanner.sync()
        with scanner.repo() as repo:
            branch = self.branch1_name
            remote_branch = f"origin/{branch}"
            # Check module tree: OK
            module = self.addon
            module_tree = repo.tree(remote_branch) / module
            self.assertTrue(scanner._manifest_exists(module_tree))
            # Check repository root tree: KO
            self.assertFalse(scanner._manifest_exists(repo.tree(remote_branch)))

    def test_get_subtree(self):
        scanner = self._init_scanner()
        scanner.sync()
        with scanner.repo() as repo:
            branch = self.branch1_name
            remote_branch = f"origin/{branch}"
            module = self.addon
            # Module/folder exists: OK
            self.assertTrue(scanner._get_subtree(repo.tree(remote_branch), module))
            # Module/folder doesn't exist: KO
            self.assertFalse(scanner._get_subtree(repo.tree(remote_branch), "none"))

    def test_workaround_fs_errors(self):
        scanner = self._init_scanner(
            repositories_path=tempfile.mkdtemp(),
            workaround_fs_errors=True,
        )
        # Clone
        self.assertFalse(scanner.path.exists())
        self.assertFalse(scanner.is_cloned)
        scanner.sync()
        self.assertTrue(scanner.is_cloned)
        # Fetch once cloned
        scanner.sync()
