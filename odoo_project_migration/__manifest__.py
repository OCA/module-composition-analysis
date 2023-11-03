# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
{
    "name": "Odoo Project Migration Data",
    "summary": "Analyze your Odoo project migrations.",
    "version": "16.0.1.0.0",
    "category": "Tools",
    "author": "Camptocamp, Odoo Community Association (OCA)",
    "website": "https://github.com/camptocamp/odoo-repository",
    "data": [
        "security/ir.model.access.csv",
        "views/odoo_project.xml",
        "views/odoo_project_module_migration.xml",
        "wizards/generate_migration_data.xml",
        "wizards/create_migration_report.xml",
    ],
    "installable": True,
    "depends": [
        "odoo_project",
        "odoo_repository_migration",
    ],
    "license": "AGPL-3",
}
