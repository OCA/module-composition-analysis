import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    update_odoo_module_branch_specific(env)


def update_odoo_module_branch_specific(env):
    _logger.info("Update '<odoo.module.branch>.specific' field...")
    repos = env["odoo.repository"].with_context(active_test=False).search([])
    for repo in repos:
        modules = repo.branch_ids.module_ids
        modules.write({"specific": repo.specific})
        # Dependencies of generic modules should be aligned (to update orphaned
        # dependencies if any, don't care about filtering here, updating
        # thousands of records at once is OK)
        if not repo.specific:
            orphaned_deps = modules._get_recursive_dependencies()
            orphaned_deps.write({"specific": False})
