import logging

from openupgradelib import openupgrade as ou

from odoo.tools import sql

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    set_xml_ids_on_odoo_branch(cr)
    migrate_repository_clone_branch_id_to_repository_branch(cr)


def set_xml_ids_on_odoo_branch(cr):
    _logger.info("Add XML-ID on 'odoo.branch' 18.0...")
    query = "SELECT id FROM odoo_branch WHERE name='18.0';"
    cr.execute(query)
    row = cr.fetchone()
    if row:
        branch_id = row[0]
        ou.add_xmlid(cr, "odoo_repository", "odoo_branch_18", "odoo.branch", branch_id)


def migrate_repository_clone_branch_id_to_repository_branch(cr):
    _logger.info(
        "Migrate 'clone_branch_id' from 'odoo.repository' to 'odoo.repository.branch'..."
    )
    # Create 'odoo_repository_branch.cloned_branch'
    if not sql.column_exists(cr, "odoo_repository_branch", "cloned_branch"):
        sql.create_column(cr, "odoo_repository_branch", "cloned_branch", "varchar")
    # Migrate values from 'odoo_repository.clone_branch_id' to this new column
    query = """
        UPDATE odoo_repository_branch
        SET cloned_branch=br.name
        FROM odoo_repository repo
        JOIN odoo_branch br
            ON repo.clone_branch_id=br.id
        WHERE repo.id = odoo_repository_branch.repository_id;
    """
    cr.execute(query)
