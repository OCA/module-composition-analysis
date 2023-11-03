# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
{
    "name": "Odoo Project",
    "summary": "Analyze your Odoo projects code bases.",
    "version": "16.0.1.0.0",
    "category": "Tools",
    "author": "Camptocamp, Odoo Community Association (OCA)",
    "website": "https://github.com/camptocamp/odoo-repository",
    "data": [
        "security/ir.model.access.csv",
        "views/menu.xml",
        "views/odoo_module_branch.xml",
        "views/odoo_project.xml",
        "views/odoo_project_module.xml",
        "wizards/odoo_project_import_modules.xml",
    ],
    "installable": True,
    "depends": [
        "odoo_repository",
    ],
    "license": "AGPL-3",
}
