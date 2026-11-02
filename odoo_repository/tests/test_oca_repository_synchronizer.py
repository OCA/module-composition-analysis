# Copyright 2026 Sébastien Alix
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from unittest.mock import MagicMock, patch

from odoo import tools
from odoo.exceptions import UserError

from odoo.addons.component.tests.common import TransactionComponentCase
from odoo.addons.queue_job.exception import RetryableJobError


class TestOCARepositorySynchronizer(TransactionComponentCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, queue_job__no_delay=True))
        cls.repository_model = cls.env["odoo.repository"]
        cls.oca_org = cls.env.ref("odoo_repository.odoo_repository_org_oca")
        # Create a test repository that should be archived
        cls.test_repo = cls.repository_model.create(
            {
                "org_id": cls.oca_org.id,
                "name": "test-archive-repo",
                "repo_url": "https://github.com/OCA/test-archive-repo",
                "clone_url": "https://github.com/OCA/test-archive-repo",
                "repo_type": "github",
                "active": True,
            }
        )

    def setUp(self):
        super().setUp()
        patcher = patch(
            "odoo.addons.odoo_repository.utils.github.get_repo_info",
            return_value=None,
        )
        self.mock_get_repo_info = patcher.start()
        self.addCleanup(patcher.stop)

    def _patch_requests_get(self, mock_get):
        # Mock GitHub API response for directory listing
        mock_dir_response = MagicMock()
        mock_dir_response.json.return_value = [
            {
                "name": "test.yml",
                "download_url": (
                    "https://raw.githubusercontent.com/"
                    "OCA/repo-maintainer-conf/master/conf/repo/test.yml"
                ),
            }
        ]
        mock_dir_response.raise_for_status.return_value = None
        # Mock YAML file content
        mock_yaml_response = MagicMock()
        mock_yaml_response.text = """
            test-repo:
              branches:
                - "16.0"
              name: Test
        """
        mock_yaml_response.raise_for_status.return_value = None

        # Setup mock to return different responses based on URL
        def get_side_effect(url, **kwargs):
            if "contents/conf/repo" in url:
                return mock_dir_response
            else:
                return mock_yaml_response

        mock_get.side_effect = get_side_effect

    def _get_current_repos(self, names):
        """Return OCA configuration data for the given repository names."""
        return {
            name: {
                "name": name,
                "repo_url": f"https://github.com/OCA/{name}",
                "clone_url": f"https://github.com/OCA/{name}",
                "repo_type": "github",
            }
            for name in names
        }

    def _mock_github_repo_info(self, info_by_name):
        """Map each repository name to the GitHub API payload it should get.

        A ``KeyError`` is raised if the synchronizer queries GitHub
        about a repository which is not explicitly mapped.
        """

        def get_repo_info_side_effect(env, org, name):
            return info_by_name[name]

        self.mock_get_repo_info.side_effect = get_repo_info_side_effect

    def test_parse_oca_repo_configurations(self):
        """Test OCA repository configurations parsing.

        Only those with branches are returned.
        """
        yaml_content = """
            test-repo-no-branches:
              branches: []
              name: Test Repo
            test-repo-with-branches:
              branches:
                - "16.0"
                - "17.0"
              name: Test Repo With Branches
        """
        repo_configs = {"test.yml": yaml_content}
        mca_backend = self.env.ref("odoo_repository.mca_backend")
        with mca_backend.work_on("odoo.repository") as work:
            synchronizer = work.component(usage="oca.repository.synchronizer")
            result = synchronizer._parse_oca_repo_configurations(repo_configs)
        # Should only include repo with branches
        self.assertEqual(len(result), 1)
        self.assertNotIn("test-repo-no-branches", result)
        self.assertIn("test-repo-with-branches", result)
        repo_data = result["test-repo-with-branches"]
        self.assertEqual(repo_data["name"], "test-repo-with-branches")
        self.assertEqual(
            repo_data["repo_url"], "https://github.com/OCA/test-repo-with-branches"
        )

    def test_parse_oca_repo_configurations_default_branch(self):
        """Test OCA repository configurations parsing with default_branch filtering.

        Repositories with default_branch='master' or 'main' should be skipped.
        """
        yaml_content = """
            repo-master:
              default_branch: master
              branches:
                - "16.0"
              name: Master Branch Repo
            repo-main:
              default_branch: main
              branches:
                - "16.0"
              name: Main Branch Repo
            repo-odoo-branch:
              default_branch: 16.0
              branches:
                - "16.0"
                - "17.0"
              name: Odoo Branch Repo
            repo-no-default:
              branches:
                - "16.0"
              name: No Default Branch Repo
        """
        repo_configs = {"test.yml": yaml_content}
        mca_backend = self.env.ref("odoo_repository.mca_backend")
        with mca_backend.work_on("odoo.repository") as work:
            synchronizer = work.component(usage="oca.repository.synchronizer")
            result = synchronizer._parse_oca_repo_configurations(repo_configs)
        # Should only include repos with non-master/main default_branch
        # or no default_branch
        self.assertEqual(len(result), 2)
        self.assertNotIn("repo-master", result)
        self.assertNotIn("repo-main", result)
        self.assertIn("repo-odoo-branch", result)
        self.assertIn("repo-no-default", result)

    def test_sync_oca_repositories_archive(self):
        """Test that repositories not in current config are archived."""
        mca_backend = self.env.ref("odoo_repository.mca_backend")
        with mca_backend.work_on("odoo.repository") as work:
            synchronizer = work.component(usage="oca.repository.synchronizer")
            # Mock current repositories (empty = no repos in config)
            current_repos = {}
            stats = synchronizer._sync_oca_repositories(current_repos)
        # Check that our test repo was archived
        self.assertEqual(stats["archived"], 1)
        self.test_repo.invalidate_model()
        self.assertFalse(self.test_repo.active)
        self.assertFalse(self.test_repo.to_scan)

    def test_sync_oca_repositories_create(self):
        """Test creation of new repositories from config."""
        mca_backend = self.env.ref("odoo_repository.mca_backend")
        with mca_backend.work_on("odoo.repository") as work:
            synchronizer = work.component(usage="oca.repository.synchronizer")
            current_repos = self._get_current_repos(["new-test-repo"])
            stats = synchronizer._sync_oca_repositories(current_repos)
        self.assertEqual(stats["created"], 1)
        # Check that repository was created
        new_repo = self.repository_model.search([("name", "=", "new-test-repo")])
        self.assertTrue(new_repo.exists())
        self.assertEqual(new_repo.org_id, self.oca_org)
        self.assertEqual(new_repo.repo_url, "https://github.com/OCA/new-test-repo")
        self.assertTrue(new_repo.active)
        self.assertTrue(new_repo.to_scan)

    def test_sync_oca_repositories_update(self):
        """Test updating existing repositories."""
        mca_backend = self.env.ref("odoo_repository.mca_backend")
        with mca_backend.work_on("odoo.repository") as work:
            synchronizer = work.component(usage="oca.repository.synchronizer")
            current_repos = {
                "test-archive-repo": {
                    "name": "test-archive-repo",
                    "repo_url": "https://github.com/OCA/test-archive-repo-updated",
                    "clone_url": "https://github.com/OCA/test-archive-repo-updated",
                    "repo_type": "github",
                }
            }
            stats = synchronizer._sync_oca_repositories(current_repos)
        self.assertEqual(stats["updated"], 1)
        # Check that repository was updated
        self.test_repo.invalidate_model()
        self.assertEqual(
            self.test_repo.repo_url, "https://github.com/OCA/test-archive-repo-updated"
        )
        self.assertTrue(self.test_repo.active)
        # The repository is still declared in the OCA configuration:
        # GitHub must not have been queried about it
        self.mock_get_repo_info.assert_not_called()

    def _get_github_renamed_repo_info(self):
        """Return GitHub API payload for a repository renamed on GitHub."""
        return {
            "name": "test-renamed-repo",
            "full_name": "OCA/test-renamed-repo",
        }

    def test_sync_oca_repositories_rename(self):
        """Test that a repository renamed on GitHub is renamed locally.

        GitHub redirects the query of a renamed repository to its new
        name: the local record is renamed in place instead of being
        archived and duplicated under the new name.
        """
        self._mock_github_repo_info(
            {"test-archive-repo": self._get_github_renamed_repo_info()}
        )
        mca_backend = self.env.ref("odoo_repository.mca_backend")
        with mca_backend.work_on("odoo.repository") as work:
            synchronizer = work.component(usage="oca.repository.synchronizer")
            current_repos = self._get_current_repos(["test-renamed-repo"])
            stats = synchronizer._sync_oca_repositories(current_repos)
        self.assertEqual(stats["renamed"], 1)
        self.assertEqual(stats["created"], 0)
        self.assertEqual(stats["updated"], 0)
        self.assertEqual(stats["archived"], 0)
        self.test_repo.invalidate_model()
        # The existing record was renamed in place, not archived
        self.assertEqual(self.test_repo.name, "test-renamed-repo")
        self.assertEqual(
            self.test_repo.repo_url, "https://github.com/OCA/test-renamed-repo"
        )
        self.assertEqual(
            self.test_repo.clone_url, "https://github.com/OCA/test-renamed-repo"
        )
        self.assertTrue(self.test_repo.active)
        self.assertTrue(self.test_repo.to_scan)
        # No duplicate left under the old name
        self.assertFalse(
            self.repository_model.with_context(active_test=False).search(
                [("name", "=", "test-archive-repo")]
            )
        )

    def test_sync_oca_repositories_rename_not_in_config(self):
        """Test rename of a repository not declared (yet) in the OCA config.

        GitHub gives the new identity, but the OCA configuration remains
        authoritative for the lifecycle: the record is renamed then
        archived, and reactivated as soon as the OCA configuration
        declares its new name.
        """
        self._mock_github_repo_info(
            {"test-archive-repo": self._get_github_renamed_repo_info()}
        )
        mca_backend = self.env.ref("odoo_repository.mca_backend")
        with mca_backend.work_on("odoo.repository") as work:
            synchronizer = work.component(usage="oca.repository.synchronizer")
            # First sync: the new name is not (yet) in the OCA configuration
            stats = synchronizer._sync_oca_repositories({})
            self.assertEqual(stats["renamed"], 1)
            self.assertEqual(stats["created"], 0)
            self.assertEqual(stats["archived"], 1)
            self.test_repo.invalidate_model()
            self.assertEqual(self.test_repo.name, "test-renamed-repo")
            self.assertFalse(self.test_repo.active)
            self.assertFalse(self.test_repo.to_scan)
            # Second sync: the new name is now declared
            self.mock_get_repo_info.reset_mock()
            current_repos = self._get_current_repos(["test-renamed-repo"])
            stats = synchronizer._sync_oca_repositories(current_repos)
            self.assertEqual(stats["renamed"], 0)
            self.assertEqual(stats["created"], 0)
            self.assertEqual(stats["updated"], 1)
            self.test_repo.invalidate_model()
            self.assertTrue(self.test_repo.active)
            # The reactivation of the record must not query GitHub
            self.mock_get_repo_info.assert_not_called()

    def test_sync_oca_repositories_rename_duplicate(self):
        """Test rename when a duplicate record exists under the new name.

        GitHub guarantees both records are the same repository: the
        sync is then aborted (error raised).
        """
        self._mock_github_repo_info(
            {"test-archive-repo": self._get_github_renamed_repo_info()}
        )
        # Duplicate created by a previous sync under the new name
        duplicate = self.repository_model.create(
            {
                "org_id": self.oca_org.id,
                "name": "test-renamed-repo",
                "repo_url": "https://github.com/OCA/test-renamed-repo",
                "clone_url": "https://github.com/OCA/test-renamed-repo",
                "repo_type": "github",
            }
        )
        mca_backend = self.env.ref("odoo_repository.mca_backend")
        with mca_backend.work_on("odoo.repository") as work:
            synchronizer = work.component(usage="oca.repository.synchronizer")
            current_repos = self._get_current_repos(["test-renamed-repo"])
            with self.assertRaises(UserError):
                synchronizer._sync_oca_repositories(current_repos)
        # The duplicate is kept
        self.assertTrue(duplicate.exists())

    def test_sync_oca_repositories_transfer(self):
        """Test that a repository transferred to another organization is archived."""
        self._mock_github_repo_info(
            {
                "test-archive-repo": {
                    "name": "test-renamed-repo",
                    "full_name": "OtherOrg/test-renamed-repo",
                }
            }
        )
        mca_backend = self.env.ref("odoo_repository.mca_backend")
        with mca_backend.work_on("odoo.repository") as work:
            synchronizer = work.component(usage="oca.repository.synchronizer")
            stats = synchronizer._sync_oca_repositories({})
        self.assertEqual(stats["renamed"], 0)
        self.assertEqual(stats["archived"], 1)
        self.test_repo.invalidate_model()
        self.assertEqual(self.test_repo.name, "test-archive-repo")
        self.assertFalse(self.test_repo.active)

    def test_sync_oca_repositories_removed(self):
        """Test that a repository still existing on GitHub is archived.

        The repository was removed from the OCA configuration but not
        on GitHub: the regular archive process applies.
        """
        self._mock_github_repo_info(
            {
                "test-archive-repo": {
                    "name": "test-archive-repo",
                    "full_name": "OCA/test-archive-repo",
                }
            }
        )
        mca_backend = self.env.ref("odoo_repository.mca_backend")
        with mca_backend.work_on("odoo.repository") as work:
            synchronizer = work.component(usage="oca.repository.synchronizer")
            stats = synchronizer._sync_oca_repositories({})
        self.assertEqual(stats["renamed"], 0)
        self.assertEqual(stats["archived"], 1)
        self.test_repo.invalidate_model()
        self.assertEqual(self.test_repo.name, "test-archive-repo")
        self.assertFalse(self.test_repo.active)

    @patch("requests.get")
    def test_fetch_oca_repo_configurations(self, mock_get):
        """Test fetching repository configuration from GitHub."""
        self._patch_requests_get(mock_get)
        mca_backend = self.env.ref("odoo_repository.mca_backend")
        with mca_backend.work_on("odoo.repository") as work:
            synchronizer = work.component(usage="oca.repository.synchronizer")
            result = synchronizer._fetch_oca_repo_configurations()
        self.assertIn("test.yml", result)
        self.assertIn("test-repo:", result["test.yml"])

    @patch("requests.get")
    def test_run_oca_repository_synchronizer(self, mock_get):
        """Test running the repository synchronizer component (main entrypoint)."""
        self._patch_requests_get(mock_get)
        mca_backend = self.env.ref("odoo_repository.mca_backend")
        with mca_backend.work_on("odoo.repository") as work:
            synchronizer = work.component(usage="oca.repository.synchronizer")
            stats = synchronizer.run()
        self.assertEqual(stats["created"], 1)
        self.assertEqual(stats["updated"], 0)

    def test_run_oca_repository_synchronizer_error(self):
        """Test running the repository synchronizer component raising exception."""
        mca_backend = self.env.ref("odoo_repository.mca_backend")
        with mca_backend.work_on("odoo.repository") as work:
            synchronizer = work.component(usage="oca.repository.synchronizer")
            synchronizer.github_conf_api_url = "wrong_api_url"
            with self.assertRaises(RetryableJobError):
                with tools.mute_logger(
                    "odoo.addons.odoo_repository.components.oca_repository_synchronizer"
                ):
                    synchronizer.run()

    @patch("requests.get")
    def test_cron_sync_oca_repositories(self, mock_get):
        """Test cron method syncing OCA repositories from GitHub."""
        self._patch_requests_get(mock_get)
        result = self.repository_model.cron_sync_oca_repositories()
        self.assertTrue(result)
        test_repo = self.repository_model.search([("name", "=", "test-repo")])
        self.assertEqual(test_repo.name, "test-repo")
        self.assertEqual(
            test_repo.repo_url, test_repo.clone_url, "https://github.com/OCA/test-repo"
        )

    def test_oca_repo_blacklist_configurable(self):
        """Test that OCA repository blacklist is configurable through settings."""
        yaml_content = """
            blacklisted-repo:
              branches:
                - "16.0"
              name: Blacklisted Repo
            normal-repo:
              branches:
                - "16.0"
              name: Normal Repo
        """
        repo_configs = {"test.yml": yaml_content}
        # Test with default blacklist (should skip OCB and OpenUpgrade)
        mca_backend = self.env.ref("odoo_repository.mca_backend")
        with mca_backend.work_on("odoo.repository") as work:
            synchronizer = work.component(usage="oca.repository.synchronizer")
            # Test default blacklist
            default_blacklist = synchronizer._get_oca_repo_blacklist()
            self.assertIn("OCB", default_blacklist)
            self.assertIn("OpenUpgrade", default_blacklist)
            # Test parsing with custom blacklist (comma-separated)
            self.env["ir.config_parameter"].sudo().set_param(
                "odoo_repository.oca_repo_blacklist", "OCB,OpenUpgrade,blacklisted-repo"
            )
            custom_blacklist = synchronizer._get_oca_repo_blacklist()
            self.assertIn("OCB", custom_blacklist)
            self.assertIn("OpenUpgrade", custom_blacklist)
            self.assertIn("blacklisted-repo", custom_blacklist)
            # Test that blacklisted repo is skipped
            result = synchronizer._parse_oca_repo_configurations(repo_configs)
            self.assertNotIn("blacklisted-repo", result)
            self.assertIn("normal-repo", result)
            # Test with empty blacklist
            self.env["ir.config_parameter"].sudo().set_param(
                "odoo_repository.oca_repo_blacklist", ""
            )
            empty_blacklist = synchronizer._get_oca_repo_blacklist()
            self.assertEqual(empty_blacklist, [])
            # Test that both repos are included when blacklist is empty
            result = synchronizer._parse_oca_repo_configurations(repo_configs)
            self.assertIn("blacklisted-repo", result)
            self.assertIn("normal-repo", result)
