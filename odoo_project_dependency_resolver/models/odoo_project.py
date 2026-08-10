# Copyright 2026 ACSONE SA/NV (<https://acsone.eu>)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging

import git

from odoo import _, fields, models
from odoo.exceptions import UserError

from odoo.addons.queue_job.delay import group
from odoo.addons.queue_job.job import identity_exact

_logger = logging.getLogger(__name__)


class OdooProject(models.Model):
    _inherit = "odoo.project"

    dependency_management = fields.Selection(
        selection=[("manual", "Manual"), ("resolved", "Resolved")],
        default="manual",
        required=True,
        help=(
            "Manual: the list of modules is maintained by hand.\n"
            "Resolved: it is rebuilt from a dependency file of the repository "
            "every time the project is scanned."
        ),
    )
    dependency_resolver = fields.Selection(
        selection=[("requirements_txt", "requirements.txt")],
        default="requirements_txt",
        help="Format of the dependency file to read.",
    )
    dependency_source_path = fields.Char(
        default="requirements.txt",
        help="Path of the dependency file, relative to the root of the repository.",
    )
    app_module_ids = fields.Many2many(
        comodel_name="odoo.module.branch",
        relation="odoo_project_app_module_rel",
        column1="odoo_project_id",
        column2="module_branch_id",
        string="Additional Modules",
        help=(
            "Modules installed from somewhere the dependency file does not "
            "reach, Odoo Enterprise typically. The modules hosted by the "
            "project repository are added on their own, and Odoo standard "
            "modules are pulled from the dependency graph: neither of them "
            "has to be declared here."
        ),
    )
    last_resolution_date = fields.Datetime(readonly=True)
    resolution_log = fields.Text(
        readonly=True,
        help="What the last resolution could not do, and what it had to guess.",
    )

    def action_scan(self, force=False):
        # Resolved projects are scanned in two passes:
        # 1) the project repository is scanned first so the dependency file is read
        #    from a fresh clone, and
        # 2) the dependencies are resolved, then their originating repositories are
        #    scanned to complete the dependency graph.
        # Other projects keep the standard super() flow.
        # For resolved projects, we trigger the repository scan directly here because
        # the repository override of _create_subsequent_jobs schedules dependency
        # resolution as a follow-up job of the repository scan.
        resolved = self.filtered(lambda p: p.dependency_management == "resolved")
        res = super(OdooProject, self - resolved).action_scan(force=force)
        for project in resolved:
            if not project.repository_id:
                raise UserError(
                    _("Define the repository of project %s to resolve its modules.")
                    % project.name
                )
            project.repository_id.action_scan(force=force, raise_exc=True)
        return res

    def action_resolve_dependencies(self):
        """Rebuild the list of modules from the dependency file of the project."""
        for project in self:
            project._resolve_dependencies()
        return True

    def _create_job_resolve_dependencies(self, scan_repositories=False):
        """Return the job resolving the modules of this project."""
        self.ensure_one()
        delayable = self.delayable(
            description=f"Resolve the modules of {self.display_name}",
            identity_key=identity_exact,
        )
        return delayable._resolve_dependencies_job(scan_repositories=scan_repositories)

    def _resolve_dependencies_job(self, scan_repositories=False):
        """Resolve the project dependencies from a job.

        Record expected resolution errors on the project instead of failing the job.
        """
        self.ensure_one()
        try:
            self._resolve_dependencies()
        except UserError as exc:
            _logger.warning(
                "Cannot resolve the modules of %s: %s", self.display_name, exc
            )
            self.sudo().write(
                {
                    "last_resolution_date": fields.Datetime.now(),
                    "resolution_log": str(exc),
                }
            )
            return True
        if scan_repositories:
            self._scan_resolved_repositories()
        return True

    def _scan_resolved_repositories(self):
        """
        Second pass: scan the repositories discovered from the resolved dependencies.
        """
        self.ensure_one()
        repositories = self._get_repositories_to_scan() - self.repository_id
        branches = self._get_branches_to_scan()
        if not repositories or not branches:
            return False
        # NOTE: the scan stays incremental whether the first pass was forced or
        # not. Forcing the scan of a project is about the project, not about
        # re-collecting the whole history of every repository it depends on.
        scan_jobs = repositories.with_context(
            strict_branches_scan=True
        )._create_scan_jobs(branch_ids=branches.ids, raise_exc=False)
        if not scan_jobs:
            return False
        group(*scan_jobs).on_done(self._create_job_resolve_dependencies()).delay()
        return True

    def _resolve_dependencies(self):
        """Refresh the modules of this project from its dependency file."""
        self.ensure_one()
        content = self._read_dependency_source()
        log = []
        backend = self.env.ref("odoo_repository.mca_backend")
        usage = f"project.dependency.resolver.{self.dependency_resolver}"
        with backend.work_on(self._name) as work:
            dependencies = work.component(usage=usage).resolve(content)
        project_modules = self.env["odoo.project.module"]
        for dependency in dependencies:
            project_modules |= self._apply_resolved_dependency(dependency, log)
        project_modules |= self._resolve_undeclared_modules(log)
        project_modules |= self._resolve_missing_dependencies(project_modules, log)
        self._remove_unresolved_modules(project_modules, log)
        self.sudo().write(
            {
                "last_resolution_date": fields.Datetime.now(),
                "resolution_log": "\n".join(log),
            }
        )
        return project_modules

    def _read_dependency_source(self):
        """Return the content of the dependency file of this project."""
        self.ensure_one()
        if not self.repository_id:
            raise UserError(
                _("Define the repository of project %s to resolve its modules.")
                % self.name
            )
        clone_path = self.repository_id._get_local_clone_path()
        if not clone_path.joinpath(".git").exists():
            raise UserError(
                _("Repository %s has not been cloned yet, scan it first.")
                % self.repository_id.display_name
            )
        branch = self.repository_branch_id.cloned_branch or self.odoo_version_id.name
        revision = f"remotes/origin/{branch}:{self.dependency_source_path}"
        # NOTE: read the file straight from the object database. Checking the
        # branch out would fight with the scan jobs, which check branches out
        # in this very clone.
        try:
            with git.Repo(clone_path) as repo:
                return repo.git.show(revision)
        except git.exc.GitError as exc:
            raise UserError(
                _("Cannot read %(revision)s in %(repository)s: %(error)s")
                % {
                    "revision": revision,
                    "repository": self.repository_id.display_name,
                    "error": exc,
                }
            ) from exc

    def _apply_resolved_dependency(self, dependency, log):
        """Turn a resolved dependency into a module of this project."""
        self.ensure_one()
        module = self.env["odoo.module.branch"]._get_module(dependency.module_name)
        if module.blacklisted:
            return self.env["odoo.project.module"]
        source, upstream = self._get_dependency_repositories(dependency, log)
        module_branch = self._get_module_branch(module, repository=upstream)
        project_module = self._get_project_module(module_branch, dependency.version)
        project_module.sudo().write(
            {
                "source_repository_id": source.id,
                "source_clone_url": dependency.clone_url,
                "source_ref": dependency.ref,
                "source_subdirectory": dependency.subdirectory,
            }
        )
        # A pinned revision is read from its own repository, which has to be
        # cloned first: too long to be done here, one dependency among
        # hundreds, and worth retrying on its own when the network fails.
        if dependency.is_pinned and project_module.analysed_ref != dependency.ref:
            project_module._create_job_analyse_pinned_revision().delay()
        return project_module

    def _get_dependency_repositories(self, dependency, log):
        """Return the source and upstream repositories of a resolved dependency."""
        self.ensure_one()
        empty = self.env["odoo.repository"]
        if not dependency.clone_url:
            return (empty, None)
        repository = empty._find_from_clone_url(dependency.clone_url)
        if not repository:
            log.append(
                _("%(module)s: unknown origin for %(url)s")
                % {"module": dependency.module_name, "url": dependency.clone_url}
            )
            return (empty, None)
        return (repository, repository.upstream_repository_id or repository)

    def _resolve_undeclared_modules(self, log):
        """
        Return modules not declared in the dependency file but belonging to the project.
        """
        self.ensure_one()
        hosted_modules = self.repository_branch_id.module_ids
        resolved = self.env["odoo.project.module"]
        for module_branch in hosted_modules | self.app_module_ids:
            resolved |= self._get_project_module(module_branch, module_branch.version)
        if hosted_modules:
            log.append(
                _("Added %s module(s) hosted by the project repository.")
                % len(hosted_modules)
            )
        return resolved

    def _resolve_missing_dependencies(self, project_modules, log):
        """Return the missing dependencies of the resolved modules.

        Odoo standard modules are shipped with Odoo itself, so they show up in
        no dependency file: they are pulled from the dependency graph.
        """
        self.ensure_one()
        module_branches = project_modules.module_branch_id
        missing = module_branches._get_recursive_dependencies() - module_branches
        resolved = self.env["odoo.project.module"]
        for module_branch in missing:
            resolved |= self._get_project_module(module_branch, module_branch.version)
        if missing:
            log.append(
                _("Added %s module(s) pulled from the dependency graph.") % len(missing)
            )
        return resolved

    def _remove_unresolved_modules(self, project_modules, log):
        """Drop the modules of this project that are no longer declared."""
        self.ensure_one()
        outdated = self.project_module_ids - project_modules
        if not outdated:
            return self.env["odoo.project.module"]
        log.append(
            _("Removed %(count)s module(s) no longer declared: %(modules)s")
            % {
                "count": len(outdated),
                "modules": ", ".join(sorted(outdated.mapped("module_name"))),
            }
        )
        outdated.sudo().unlink()
        return outdated
