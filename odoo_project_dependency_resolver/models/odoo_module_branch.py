# Copyright 2026 ACSONE SA/NV (<https://acsone.eu>)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import models


class OdooModuleBranch(models.Model):
    _inherit = "odoo.module.branch"

    def _update_from_pinned_revision(self, data):
        """Fill this module branch with a module analysed at a pinned revision.

        Meant for a module living in a pull request alone: it is in no branch
        of any repository, so no scan ever reaches it and nothing else ever
        fills it.
        """
        self.ensure_one()
        values = self._prepare_pinned_revision_values(data)
        if values:
            self.sudo().write(values)
        return True

    def _prepare_pinned_revision_values(self, data):
        """Return the values a module analysed at a pinned revision carries.

        Only what the revision itself holds: what its manifest declares, and
        what the analysis of its code counted. What a scan knows on top of
        that, which repository hosts the module and the history of its
        versions, a revision cannot tell.
        """
        values = {}
        manifest = data.get("manifest") or {}
        if manifest:
            # The dependencies are looked up from this very module branch: the
            # revision knows of no repository branch, and a module living in a
            # pull request alone belongs to no repository at all.
            values.update(
                self._prepare_manifest_values(
                    manifest, self.branch_id, self.repository_id
                )
            )
        code = data.get("code") or {}
        if code:
            values.update(self._prepare_code_analysis_values(code))
        if values:
            values["removed"] = False
        return values
