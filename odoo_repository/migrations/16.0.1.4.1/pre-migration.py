import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    delete_duplicated_module_versions(cr)


def delete_duplicated_module_versions(cr):
    _logger.info("Delete duplicated module versions...")
    query = """
        DELETE FROM odoo_module_branch_version mbv
        WHERE EXISTS(
            SELECT 1
            FROM (
                SELECT
                    id,
                    module_branch_id,
                    name,
                    manifest_value,
                    ROW_NUMBER() OVER (
                        PARTITION BY module_branch_id, name, manifest_value
                        ORDER BY create_date
                    ) rn
                FROM odoo_module_branch_version
            ) t
            where t.rn > 1 and t.id = mbv.id
        )
        RETURNING mbv.id;
    """
    cr.execute(query)
    rows = cr.fetchall()
    _logger.info("%s duplicated module versions deleted.", len(rows))
