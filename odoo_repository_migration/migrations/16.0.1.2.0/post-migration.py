# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    fix_migration_states(env)


def fix_migration_states(env):
    _logger.info("Plan a scan to fix '<odoo.module.branch.migration>.state' field...")
    query = """
        SELECT mig.id
        FROM odoo_module_branch_migration mig
        JOIN odoo_module_branch AS source
            ON mig.module_branch_id=source.id
        JOIN odoo_module_branch AS target
            ON mig.target_module_branch_id=target.id
        WHERE source.repository_branch_id IS NOT NULL
        AND target.repository_branch_id IS NOT NULL
        AND source.repository_id != target.repository_id;
    """
    env.cr.execute(query)
    mig_ids = [row[0] for row in env.cr.fetchall()]
    # Reset 'last_target_scanned_commit' to recompute 'migration_scan'
    if mig_ids:
        query = """
            UPDATE odoo_module_branch_migration
            SET last_target_scanned_commit=NULL
            WHERE id IN %s;
        """
        args = (tuple(mig_ids),)
        env.cr.execute(query, args)
    # Reset collected migration data on modules that shouldn't have any
    mbm_model = env["odoo.module.branch.migration"]
    migs = mbm_model.search(
        [
            ("results", "!=", False),
            ("repository_id.collect_migration_data", "=", False),
        ]
    )
    migs.results = False
    # Recompute migration state/flag, especially for modules moved to another repo
    # that won't trigger a migration scan.
    migs = mbm_model.search([("id", "in", mig_ids)])
    env.add_to_compute(migs._fields["state"], migs)
    env.add_to_compute(migs._fields["migration_scan"], migs)
    migs.modified(["state", "migration_scan"])
