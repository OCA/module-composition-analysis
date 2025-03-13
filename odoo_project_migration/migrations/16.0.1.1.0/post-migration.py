# Copyright 2025 Camptocamp SA
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
    _logger.info("Update '<odoo.project.module.migration>.state' field...")
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
    # Recompute migration state, especially for modules moved to another repo
    project_migs = env["odoo.project.module.migration"].search(
        [("module_migration_id", "in", mig_ids)]
    )
    env.add_to_compute(project_migs._fields["state"], project_migs)
    project_migs.modified(["state"])
