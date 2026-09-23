# Copyright 2026 ACSONE SA/NV (<https://acsone.eu>)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging

from odoo import _, api, fields, models, tools
from odoo.exceptions import ValidationError

from odoo.addons.odoo_repository.utils import github

_logger = logging.getLogger(__name__)


class OdooRepository(models.Model):
    _inherit = "odoo.repository"

    upstream_repository_id = fields.Many2one(
        comodel_name="odoo.repository",
        string="Fork Of",
        ondelete="cascade",
        index=True,
        help=(
            "Repository this one is a fork of. A fork hosts the very same "
            "modules, so it is never scanned: its modules are those of the "
            "repository it originates from. It is registered to document where "
            "a project installs them from, and to hold the credentials needed "
            "to read it."
        ),
    )
    fork_ids = fields.One2many(
        comodel_name="odoo.repository",
        inverse_name="upstream_repository_id",
        string="Forks",
    )

    @api.constrains("upstream_repository_id", "to_scan")
    def _check_fork_not_scanned(self):
        for rec in self:
            if rec.upstream_repository_id and rec.to_scan:
                raise ValidationError(
                    _(
                        "Repository %(fork)s cannot be scanned, it is a fork of "
                        "%(upstream)s and hosts the very same modules. Scanning "
                        "it would make the module of a dependency ambiguous for "
                        "every project."
                    )
                    % {
                        "fork": rec.display_name,
                        "upstream": rec.upstream_repository_id.display_name,
                    }
                )

    @api.constrains("upstream_repository_id")
    def _check_upstream_repository_cycle(self):
        if self._has_cycle("upstream_repository_id"):
            raise ValidationError(_("A repository cannot be a fork of itself."))

    @api.model
    @tools.ormcache("org", "name")
    def _fetch_github_fork_parents(self, org, name):
        """Return the ancestors of a forked GitHub repository.

        The result is a tuple of ``org/name`` strings, from the direct parent
        to the root of the fork chain, empty if the repository is not a fork.
        """
        data = github.request(self.env, f"repos/{org}/{name}")
        if not data.get("fork"):
            return ()
        full_names = (
            (data.get("parent") or {}).get("full_name"),
            (data.get("source") or {}).get("full_name"),
        )
        # dict.fromkeys() deduplicates while keeping the parent first, as both
        # entries are equal as soon as the fork chain has a single level.
        return tuple(dict.fromkeys(filter(None, full_names)))

    @api.model
    def _find_from_clone_url(self, clone_url):
        """Return the repository a clone URL points at, fork or not.

        Lookup order:
            1. the repository matching the URL itself
            2. for a GitHub fork whose origin is known, the fork itself, which
               is registered on the fly to document where the modules are
               installed from and to hold the credentials reading it needs

        Returns an empty recordset when the origin cannot be told, letting the
        caller fall back to its own heuristics.
        """
        host, org, name = self._parse_clone_url(clone_url)
        if not org:
            return self.browse()
        repository = self._find_from_org_and_name(org, name)
        if repository:
            return repository
        if host not in ("github.com", "www.github.com"):
            # Only GitHub exposes the fork ancestry through its API
            return self.browse()
        try:
            full_names = self._fetch_github_fork_parents(org, name)
        except RuntimeError:
            # Do not let a GitHub outage or rate limit break the caller. The
            # failure is not cached, so the next call will try again.
            _logger.warning(
                "Unable to get the fork ancestry of %s", clone_url, exc_info=True
            )
            return self.browse()
        for full_name in full_names:
            parent_org, __, parent_name = full_name.rpartition("/")
            upstream = self._find_from_org_and_name(parent_org, parent_name)
            if upstream:
                return self._create_fork(host, org, name, clone_url, upstream)
        return self.browse()

    @api.model
    def _create_fork(self, host, org, name, clone_url, upstream):
        """Register the fork of `upstream` hosted at `host`, as `org`/`name`."""
        org_record = self.env["odoo.repository.org"].search([("name", "=", org)])
        if not org_record:
            org_record = self.env["odoo.repository.org"].sudo().create({"name": org})
        _logger.info(
            "Registering %s/%s as a fork of %s", org, name, upstream.display_name
        )
        return (
            self.sudo()
            .create(
                {
                    "org_id": org_record.id,
                    "name": name,
                    "repo_url": f"https://{host}/{org}/{name}",
                    "clone_url": clone_url,
                    # A fork is hosted next to the repository it originates
                    # from, whose ancestry is what told us it is one.
                    "repo_type": upstream.repo_type,
                    "to_scan": False,
                    "upstream_repository_id": upstream.id,
                }
            )
            .with_env(self.env)
        )

    @api.model
    def _find_upstream_repository(self, clone_url):
        """Return the repository the modules of a clone URL belong to.

        The modules of a fork are those of the repository it originates from:
        a fork is never scanned, so it hosts none of its own.
        """
        repository = self._find_from_clone_url(clone_url)
        return repository.upstream_repository_id or repository
