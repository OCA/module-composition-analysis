# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
{
    "name": "Odoo Repository Migration Data",
    "summary": "Collect modules migration data for Odoo Repositories.",
    "version": "16.0.1.0.0",
    "category": "Tools",
    "author": "Camptocamp, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/TODO",
    "data": [
        "security/ir.model.access.csv",
        "data/queue_job.xml",
        "views/odoo_migration_path.xml",
        "views/odoo_module_branch.xml",
        "views/odoo_module_branch_migration.xml",
        "views/odoo_repository.xml",
    ],
    "installable": True,
    "depends": [
        "odoo_repository",
    ],
    "external_dependencies": {
        "python": [
            "oca-port",
        ],
    },
    "license": "AGPL-3",
    "post_init_hook": "update_oca_repositories",
}
