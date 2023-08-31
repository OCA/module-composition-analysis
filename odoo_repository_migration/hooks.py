# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, SUPERUSER_ID


def update_oca_repositories(cr, registry):
    """Configure OCA repositories to collect migration data."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    org = env["odoo.repository.org"].search([("name", "=", "OCA")])
    if org:
        repositories = env["odoo.repository"].with_context(
            active_test=False).search([("org_id", "=", org.id)])
        repositories.write({"collect_migration_data": True})
