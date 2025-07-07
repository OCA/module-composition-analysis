import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    set_manual_branches_on_odoo_repository(cr)


def set_manual_branches_on_odoo_repository(cr):
    _logger.info("Set 'manual_branches = True' on specific repositories...")
    query = """
        UPDATE odoo_repository
        SET manual_branches = true
        WHERE specific = true;
    """
    cr.execute(query)
