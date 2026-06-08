# Copyright 2023 Camptocamp SA
# Copyright 2026  Akretion (https://www.akretion.com).
# @author Sébastien Alix <sebastien.alix@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
{
    "name": "Odoo Project Migration Data",
    "summary": "Analyze your Odoo project migrations.",
    "version": "18.0.1.1.0",
    "category": "Tools",
    "author": "Camptocamp, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/module-composition-analysis",
    "data": [
        "security/ir.model.access.csv",
        "views/odoo_module_branch_timeline.xml",
        "views/odoo_module_branch_migration.xml",
        "views/odoo_project.xml",
        "views/odoo_project_module_migration.xml",
        "wizards/generate_migration_data.xml",
        "wizards/export_migration_report.xml",
    ],
    "installable": True,
    "depends": [
        "odoo_project",
        "odoo_repository_migration",
    ],
    "license": "AGPL-3",
}
