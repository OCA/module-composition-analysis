# Copyright 2026 Sébastien Alix
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    remove_xmlids_from_oca_repositories(cr)


def remove_xmlids_from_oca_repositories(cr):
    """Remove XML-IDs from OCA repositories to prevent deletion during upgrade."""
    _logger.info("Removing XML-IDs from OCA repositories...")
    # First, get the OCA organization ID
    cr.execute("SELECT id FROM odoo_repository_org WHERE name = 'OCA'")
    oca_org_result = cr.fetchone()
    if not oca_org_result:
        _logger.warning("OCA organization not found in database")
        return
    oca_org_id = oca_org_result[0]
    # Get all OCA repositories that have XML-IDs
    cr.execute(
        """
            SELECT imd.id, imd.res_id
            FROM ir_model_data imd
            JOIN odoo_repository repo ON imd.res_id = repo.id
            WHERE imd.model = 'odoo.repository'
            AND repo.org_id = %s
        """,
        (oca_org_id,),
    )
    xmlid_records = cr.fetchall()
    if not xmlid_records:
        _logger.info("No OCA repositories with XML-IDs found")
        return
    # Delete the XML-IDs from ir.model.data
    xmlid_ids = [record[0] for record in xmlid_records]
    repository_ids = [record[1] for record in xmlid_records]
    cr.execute("DELETE FROM ir_model_data WHERE id = ANY(%s)", (xmlid_ids,))
    _logger.info(
        "Removed %s XML-IDs from OCA repositories (repository IDs: %s)",
        len(xmlid_ids),
        repository_ids,
    )
