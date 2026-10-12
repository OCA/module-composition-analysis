# Copyright 2026 ACSONE SA/NV (<https://acsone.eu>)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import contextlib
import gc
import pathlib
import tempfile
from unittest.mock import patch

import git

from odoo.exceptions import UserError
from odoo.tools import mute_logger

from odoo.addons.odoo_project.tests.common import ProjectCommon

READ_SOURCE = (
    "odoo.addons.odoo_project_dependency_resolver.models.odoo_project."
    "OdooProject._read_dependency_source"
)


class TestResolveDependencies(ProjectCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project.write(
            {
                "repository_id": cls.odoo_repository.id,
                "dependency_management": "resolved",
            }
        )
        cls.project_module_model = cls.env["odoo.project.module"]

    def _resolve(self, content):
        with patch(READ_SOURCE, return_value=content):
            self.project._resolve_dependencies()
        self.env.flush_all()
        return self.project.project_module_ids

    def _module_versions(self):
        return {
            project_module.module_name: project_module.installed_version
            for project_module in self.project.project_module_ids
        }

    # -- mapping onto project modules --------------------------------------

    def test_resolve_creates_project_modules(self):
        modules = self._resolve(
            "odoo-addon-test1==15.0.1.0.0\nodoo-addon-test2==15.0.2.0.0\n"
        )
        self.assertEqual(len(modules), 2)
        self.assertEqual(
            self._module_versions(),
            {"test1": "15.0.1.0.0", "test2": "15.0.2.0.0"},
        )

    def test_resolve_updates_the_installed_version(self):
        """Resolving again bumps the version instead of duplicating the module."""
        self._resolve("odoo-addon-test1==15.0.1.0.0\n")
        modules = self._resolve("odoo-addon-test1==15.0.1.1.0\n")
        self.assertEqual(len(modules), 1)
        self.assertEqual(self._module_versions(), {"test1": "15.0.1.1.0"})

    def test_resolve_removes_undeclared_modules(self):
        """A module dropped from the dependency file leaves the project."""
        self._resolve("odoo-addon-test1==15.0.1.0.0\nodoo-addon-test2==15.0.2.0.0\n")
        self._resolve("odoo-addon-test1==15.0.1.0.0\n")
        self.assertEqual(list(self._module_versions()), ["test1"])
        self.assertIn("test2", self.project.resolution_log)

    def test_resolve_skips_blacklisted_modules(self):
        module = self.module_branch_model._get_module("test1")
        module.blacklisted = True
        self._resolve("odoo-addon-test1==15.0.1.0.0\nodoo-addon-test2==15.0.2.0.0\n")
        self.assertEqual(list(self._module_versions()), ["test2"])

    def test_resolve_pulls_the_missing_dependencies(self):
        """Odoo standard modules show up in no dependency file."""
        dependency = self._create_odoo_module_branch(
            self.module_branch_model._get_module("base"),
            self.branch,
            is_standard=True,
        )
        app_module = self._create_odoo_module_branch(
            self.module_branch_model._get_module("my_app"),
            self.branch,
            dependency_ids=[(4, dependency.id)],
        )
        self.project.app_module_ids = app_module
        self._resolve("odoo-addon-test1==15.0.1.0.0\n")
        self.assertEqual(sorted(self._module_versions()), ["base", "my_app", "test1"])

    def test_resolve_keeps_the_additional_modules(self):
        """An additional module is never purged, the file does not hold it."""
        app_module = self._create_odoo_module_branch(
            self.module_branch_model._get_module("my_app"), self.branch
        )
        self.project.app_module_ids = app_module
        self._resolve("odoo-addon-test1==15.0.1.0.0\n")
        self.assertIn("my_app", self._module_versions())

    # -- modules hosted by the project repository ---------------------------

    def _create_specific_module(self, name="my_specific_module"):
        """Add a module to the repository of the project."""
        repository_branch = self.env["odoo.repository.branch"].search(
            [
                ("repository_id", "=", self.odoo_repository.id),
                ("branch_id", "=", self.branch.id),
            ]
        )
        if not repository_branch:
            repository_branch = self._create_odoo_repository_branch(
                self.odoo_repository, self.branch
            )
        return self._create_odoo_module_branch(
            self.module_branch_model._get_module(name),
            self.branch,
            specific=True,
            repository_branch_id=repository_branch.id,
            version="15.0.1.0.0",
        )

    def test_resolve_adds_the_modules_of_the_project_repository(self):
        """The code of the project is shipped with it, not as a package."""
        specific_module = self._create_specific_module()
        modules = self._resolve("odoo-addon-test1==15.0.1.0.0\n")
        self.assertEqual(
            sorted(self._module_versions()), ["my_specific_module", "test1"]
        )
        # Their version is the one of the repository, nothing pins them
        project_module = modules.filtered(
            lambda m: m.module_branch_id == specific_module
        )
        self.assertEqual(project_module.installed_version, "15.0.1.0.0")
        self.assertFalse(project_module.to_upgrade)

    def test_resolve_does_not_purge_the_modules_of_the_project_repository(self):
        """Resolving twice must not drop the code of the project."""
        self._create_specific_module()
        self._resolve("odoo-addon-test1==15.0.1.0.0\n")
        self._resolve("odoo-addon-test1==15.0.1.0.0\n")
        self.assertIn("my_specific_module", self._module_versions())

    # -- modules pinned on a fork ------------------------------------------

    def _create_upstream_repository(self, with_module=True):
        org_model = self.env["odoo.repository.org"].with_context(active_test=False)
        org = org_model.search([("name", "=", "OCA")])
        if not org:
            org = org_model.create({"name": "OCA"})
        repository = self.env["odoo.repository"].create(
            {
                "org_id": org.id,
                "name": "account-invoicing",
                "repo_url": "https://github.com/OCA/account-invoicing",
                "clone_url": "https://github.com/OCA/account-invoicing.git",
                "repo_type": "github",
            }
        )
        repository_branch = self._create_odoo_repository_branch(repository, self.branch)
        module_branch = self.module_branch_model.browse()
        if with_module:
            module_branch = self._create_odoo_module_branch(
                self.module_branch_model._get_module("account_invoice_triple_discount"),
                self.branch,
                specific=False,
                repository_branch_id=repository_branch.id,
                version="15.0.1.0.0",
                # The scan of the upstream repository is authoritative on it
                last_scanned_commit="c0ffee",
            )
        return repository, module_branch

    def _create_fork(self, module_name, version, on_pull_request=False):
        """Return the ``(path, revision)`` of a fork holding `module_name`.

        With `on_pull_request` the module is added on a branch of its own, as
        a pull request does: the revision then belongs to no branch the clone
        of the fork tracks, and has to be fetched on its own.
        """
        fork_path = pathlib.Path(tempfile.mkdtemp())
        fork = git.Repo.init(fork_path)
        fork.config_writer().set_value("user", "name", "test").release()
        fork.config_writer().set_value("user", "email", "test@example.com").release()
        # Serving a bare revision is what GitHub does, but not the local default
        fork.config_writer().set_value(
            "uploadpack", "allowAnySHA1InWant", "true"
        ).release()
        self.addCleanup(fork.close)
        readme = fork_path.joinpath("README.md")
        readme.write_text("A fork\n")
        fork.index.add([str(readme)])
        fork.index.commit("Initial commit")
        default_branch = fork.active_branch.name
        if on_pull_request:
            fork.git.checkout("-b", "add-module")
        module_path = fork_path.joinpath(module_name)
        module_path.mkdir()
        manifest = module_path.joinpath("__manifest__.py")
        manifest.write_text(
            "{"
            f'"name": "Test", "version": "{version}", '
            '"license": "AGPL-3", "depends": ["base"]'
            "}"
        )
        code = module_path.joinpath("models.py")
        code.write_text(
            "from odoo import fields, models\n"
            "\n"
            "\n"
            "class Foo(models.Model):\n"
            '    _name = "foo"\n'
            "\n"
            "    name = fields.Char()\n"
        )
        fork.index.add([str(manifest), str(code)])
        commit = fork.index.commit(f"Add {module_name} {version}")
        if on_pull_request:
            fork.git.checkout(default_branch)
        return fork_path, commit.hexsha

    def test_resolve_fork_keeps_the_upstream_module(self):
        """A fork commit does not create a module of its own."""
        __, upstream_module = self._create_upstream_repository()
        content = (
            "odoo-addon-account-invoice-triple-discount @ "
            "git+https://github.com/acsone/account-invoicing.git@3e4c54b"
            "#subdirectory=setup/account_invoice_triple_discount\n"
        )
        payload = {
            "fork": True,
            "parent": {"full_name": "OCA/account-invoicing"},
            "source": {"full_name": "OCA/account-invoicing"},
        }
        github_request = (
            "odoo.addons.odoo_repository_fork.models.odoo_repository.github.request"
        )
        with patch(github_request, return_value=payload):
            modules = self._resolve(content)
        self.assertEqual(len(modules), 1)
        self.assertEqual(modules.module_branch_id, upstream_module)
        self.assertTrue(modules.is_pinned)
        self.assertEqual(
            modules.source_clone_url,
            "https://github.com/acsone/account-invoicing.git",
        )
        self.assertEqual(modules.source_ref, "3e4c54b")
        # The fork it is installed from, and through it the origin
        fork = modules.source_repository_id
        self.assertEqual(fork.display_name, "acsone/account-invoicing")
        self.assertEqual(fork.upstream_repository_id, upstream_module.repository_id)

    def test_resolve_unreadable_pin_is_reported_as_to_upgrade(self):
        """An unresolved pin must not read as an up to date module."""
        self._create_upstream_repository()
        content = (
            "odoo-addon-account-invoice-triple-discount @ "
            "git+https://github.com/acsone/account-invoicing.git@3e4c54b"
            "#subdirectory=setup/account_invoice_triple_discount\n"
        )
        with (
            patch(
                "odoo.addons.odoo_repository_fork.models.odoo_repository.github.request",
                side_effect=RuntimeError("API rate limit"),
            ),
            mute_logger("odoo.addons.odoo_repository_fork.models.odoo_repository"),
        ):
            modules = self._resolve(content)
        self.assertFalse(modules.installed_version)
        self.assertTrue(modules.to_upgrade)
        self.assertIn("account_invoice_triple_discount", self.project.resolution_log)

    # -- reading the dependency file ---------------------------------------

    def _init_clone(self, repository, content=""):
        """Create the local clone of `repository`, holding a requirements file."""
        clone_path = repository._get_local_clone_path()
        clone_path.mkdir(parents=True, exist_ok=True)
        repo = git.Repo.init(clone_path)
        repo.config_writer().set_value("user", "name", "test").release()
        repo.config_writer().set_value("user", "email", "test@example.com").release()
        self.addCleanup(repo.close)
        source = clone_path.joinpath("requirements.txt")
        source.write_text(content)
        repo.index.add([str(source)])
        commit = repo.index.commit("Add requirements")
        # The scanner clones without checking out, tracking branches only
        repo.git.update_ref(f"refs/remotes/origin/{self.branch.name}", commit.hexsha)
        return repo

    def test_read_dependency_source(self):
        """The file is read from the tracking branch, without checking it out."""
        self._init_clone(self.odoo_repository, "odoo-addon-test1==15.0.1.0.0\n")
        self.assertEqual(
            self.project._read_dependency_source(), "odoo-addon-test1==15.0.1.0.0"
        )

    def test_read_dependency_source_without_clone(self):
        with self.assertRaisesRegex(UserError, "has not been cloned"):
            self.project._read_dependency_source()

    def test_read_dependency_source_missing_file(self):
        self._init_clone(self.odoo_repository, "odoo-addon-test1==15.0.1.0.0\n")
        self.project.dependency_source_path = "does-not-exist.txt"
        with self.assertRaisesRegex(UserError, "Cannot read"):
            self.project._read_dependency_source()

    def test_read_dependency_source_without_repository(self):
        self.project.repository_id = False
        with self.assertRaisesRegex(UserError, "Define the repository"):
            self.project._read_dependency_source()

    # -- analysis of a pinned revision -------------------------------------

    def _setup_pinned(self, module_name, version, on_pull_request=False):
        """Return the `(fork, content)` of a dependency pinned on a fork."""
        upstream, __ = self._create_upstream_repository(
            with_module=module_name == "account_invoice_triple_discount"
        )
        fork_path, revision = self._create_fork(
            module_name, version, on_pull_request=on_pull_request
        )
        fork = self.env["odoo.repository"].create(
            {
                "org_id": upstream.org_id.id,
                "name": "account-invoicing-fork",
                "repo_url": f"file://{fork_path}",
                "clone_url": f"file://{fork_path}",
                "repo_type": "github",
                "to_scan": False,
                "upstream_repository_id": upstream.id,
            }
        )
        content = (
            f"odoo-addon-{module_name.replace('_', '-')} @ "
            f"git+file://{fork_path}@{revision}"
            f"#subdirectory=setup/{module_name}\n"
        )
        return fork, content

    def _resolve_pinned(self, fork, content):
        """Resolve `content`, standing in for the lookup of the fork.

        The origin of a 'file://' URL cannot be told from the URL itself, and
        that lookup is covered on its own.
        """
        with patch.object(
            self.env.registry["odoo.repository"],
            "_find_from_clone_url",
            autospec=True,
            return_value=fork,
        ):
            return self._resolve(content)

    def test_analyse_pinned_revision_reads_the_version_of_the_fork(self):
        """The version comes from the manifest at the pinned revision."""
        fork, content = self._setup_pinned(
            "account_invoice_triple_discount", "15.0.1.1.0"
        )
        modules = self._resolve_pinned(fork, content)
        # The module branch stays the one of the upstream repository
        upstream_module = modules.module_branch_id
        self.assertEqual(upstream_module.version, "15.0.1.0.0")
        modules._analyse_pinned_revision()
        self.assertEqual(modules.installed_version, "15.0.1.1.0")
        self.assertEqual(modules.analysed_ref, modules.source_ref)
        # A module the upstream repository hosts is not rewritten from a fork
        self.assertEqual(upstream_module.version, "15.0.1.0.0")

    def test_analyse_pinned_revision_of_a_module_absent_upstream(self):
        """A module living only in a pull request gets its code analysed.

        It is in no branch of any repository, so no scan ever reaches it: the
        pinned revision is the only place it can be read from.
        """
        fork, content = self._setup_pinned(
            "my_pull_request_module", "15.0.1.1.0", on_pull_request=True
        )
        modules = self._resolve_pinned(fork, content)
        module_branch = modules.module_branch_id
        # The module belongs to no repository, it exists only in the fork...
        self.assertFalse(module_branch.repository_id)
        # ... but the project module says where it is installed from
        self.assertEqual(modules.source_repository_id, fork)
        modules._analyse_pinned_revision()
        self.assertEqual(modules.installed_version, "15.0.1.1.0")
        self.assertEqual(module_branch.version, "15.0.1.1.0")
        self.assertEqual(module_branch.title, "Test")
        self.assertEqual(module_branch.license_id.name, "AGPL-3")
        self.assertEqual(module_branch.dependency_ids.mapped("module_name"), ["base"])
        self.assertTrue(module_branch.sloc_python)

    def test_analyse_pinned_revision_of_an_unknown_module(self):
        """A revision holding no such module is reported, not raised."""
        fork, content = self._setup_pinned("my_pull_request_module", "15.0.1.1.0")
        with mute_logger(
            "odoo.addons.odoo_project_dependency_resolver.models.odoo_project_module",
        ):
            modules = self._resolve_pinned(fork, content)
        modules.module_branch_id.addons_path = "does/not/exist"
        with mute_logger(
            "odoo.addons.odoo_project_dependency_resolver.lib.scanner",
            "odoo.addons.odoo_project_dependency_resolver.models.odoo_project_module",
        ):
            self.assertFalse(modules._analyse_pinned_revision())
        self.assertFalse(modules.analysed_ref)

    def test_resolve_delays_the_analysis_of_a_pinned_revision(self):
        """The analysis is a job of its own, and runs once per revision."""
        job_model = self.env["queue.job"]
        domain = [("method_name", "=", "_analyse_pinned_revision")]
        fork, content = self._setup_pinned(
            "account_invoice_triple_discount", "15.0.1.1.0"
        )
        modules = self._resolve_pinned(fork, content)
        self.assertEqual(job_model.search_count(domain), 1)
        # Once analysed, resolving the very same revision queues nothing more
        modules.analysed_ref = modules.source_ref
        job_model.search(domain).unlink()
        self._resolve_pinned(fork, content)
        self.assertEqual(job_model.search_count(domain), 0)


class TestResolveDependenciesChaining(ProjectCommon):
    """The resolution is appended to the chain of the scan jobs."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # We want to test the chaining of jobs, not the resolution itself, so
        # mute the logger of the delayable to avoid a warning on the job being
        # collected without having been delayed. The resolution itself is tested
        # elsewhere.
        # we could use 'enterClassContext(mute_logger("odoo.addons.queue_job.delay"))'
        # in Python>=3.11, where Odoo 18 runs on 3.10.
        muted = contextlib.ExitStack()
        cls.addClassCleanup(muted.close)
        muted.enter_context(mute_logger("odoo.addons.queue_job.delay"))
        cls.project.write(
            {
                "repository_id": cls.odoo_repository.id,
                "dependency_management": "resolved",
            }
        )

    def tearDown(self):
        super().tearDown()
        # A delayable warns when collected without having been delayed, which
        # is what these tests do on purpose. Collect here, while
        # the logger above is still muted, rather than after 'tearDownClass'.
        gc.collect()

    def _create_subsequent_jobs(self, data=None, version=None, repository=None):
        repository = repository or self.odoo_repository
        repository_branch = self.env["odoo.repository.branch"].search(
            [("repository_id", "=", repository.id), ("branch_id", "=", self.branch.id)]
        )
        if not repository_branch:
            repository_branch = self._create_odoo_repository_branch(
                repository, self.branch
            )
        if data is None:
            data = {
                "repo_branch_id": repository_branch.id,
                "last_fetched_commit": "c0ffee",
                "last_scanned_commit": "c0ffee",
                "addons_paths": {},
            }
        version = version or self.branch.name
        return repository._create_subsequent_jobs((version, version), [], [], data)

    def _resolution_jobs(self, jobs):
        return [
            job
            for job in jobs
            if job._job_method.__name__ == "_resolve_dependencies_job"
        ]

    def test_resolution_is_chained_after_the_scan(self):
        jobs = self._create_subsequent_jobs()
        resolution_jobs = self._resolution_jobs(jobs)
        self.assertEqual(len(resolution_jobs), 1)
        self.assertEqual(resolution_jobs[0].recordset, self.project)
        # It runs last, once the modules of the branch have been scanned
        self.assertEqual(jobs[-1], resolution_jobs[0])
        # Scanning the repository of the project is the first pass: it is the
        # one discovering the repositories the modules come from
        self.assertEqual(resolution_jobs[0]._job_kwargs, {"scan_repositories": True})

    def _create_dependency_repository(self):
        """Return a repository the modules of the project come from."""
        org_model = self.env["odoo.repository.org"].with_context(active_test=False)
        org = org_model.search([("name", "=", "OCA")]) or org_model.create(
            {"name": "OCA"}
        )
        repository = self.env["odoo.repository"].create(
            {
                "org_id": org.id,
                "name": "server-tools",
                "repo_url": "https://github.com/OCA/server-tools",
                "repo_type": "github",
            }
        )
        repository_branch = self._create_odoo_repository_branch(repository, self.branch)
        module_branch = self._create_odoo_module_branch(
            self.module_branch_model._get_module("test1"),
            self.branch,
            repository_branch_id=repository_branch.id,
        )
        self.project._get_project_module(module_branch)
        return repository

    def test_no_resolution_chained_to_a_dependency_repository(self):
        """Only the repository holding the dependency file resolves.

        Chaining one resolution per repository the modules come from would
        create as many as the project has dependencies.
        """
        repository = self._create_dependency_repository()
        jobs = self._create_subsequent_jobs(repository=repository)
        self.assertFalse(self._resolution_jobs(jobs))

    def test_second_pass_scans_the_resolved_repositories(self):
        """The first pass scans what the resolution discovered."""
        repository = self._create_dependency_repository()
        repository_model = self.env.registry["odoo.repository"]
        with patch.object(
            repository_model, "_create_scan_jobs", autospec=True, return_value=[]
        ) as create_scan_jobs:
            self.project._scan_resolved_repositories()
        create_scan_jobs.assert_called_once()
        scanned = create_scan_jobs.call_args_list[0].args[0]
        self.assertEqual(scanned, repository)
        self.assertTrue(scanned.env.context.get("strict_branches_scan"))
        self.assertEqual(
            create_scan_jobs.call_args_list[0].kwargs["branch_ids"], self.branch.ids
        )

    def test_second_pass_is_joined_after_the_scans(self):
        """One resolution waits for every scan of the group to be done."""
        self._create_dependency_repository()
        self.project._scan_resolved_repositories()
        self.env.flush_all()
        resolution = self.env["queue.job"].search(
            [("method_name", "=", "_resolve_dependencies_job")]
        )
        self.assertEqual(len(resolution), 1)
        self.assertEqual(resolution.state, "wait_dependencies")
        self.assertFalse(resolution.kwargs.get("scan_repositories"))

    def test_no_resolution_for_a_manual_project(self):
        self.project.dependency_management = "manual"
        self.assertFalse(self._resolution_jobs(self._create_subsequent_jobs()))

    def test_no_resolution_for_another_version(self):
        """A project is resolved on its own Odoo version only."""
        self.assertFalse(
            self._resolution_jobs(
                self._create_subsequent_jobs(version=self.branch2.name)
            )
        )

    def test_no_resolution_when_the_branch_does_not_exist(self):
        self.assertFalse(self._resolution_jobs(self._create_subsequent_jobs(data={})))

    def test_job_records_an_expected_failure(self):
        """An unreadable dependency file must not break the chain of jobs."""
        with mute_logger(
            "odoo.addons.odoo_project_dependency_resolver.models.odoo_project"
        ):
            self.project._resolve_dependencies_job()
        self.assertIn("has not been cloned", self.project.resolution_log)
        self.assertTrue(self.project.last_resolution_date)
