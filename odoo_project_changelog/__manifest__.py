# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
{
    "name": "Odoo Project - Changelogs",
    "summary": "Generate Changelogs from repositories for installed modules.",
    "version": "16.0.1.0.1",
    "category": "Tools",
    "author": "Camptocamp, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/module-composition-analysis",
    "data": [
        "security/ir.model.access.csv",
        "data/queue_job.xml",
        "views/odoo_project.xml",
        "report/ir_actions_report.xml",
        "report/odoo_project_changelog.xml",
    ],
    "installable": True,
    "depends": [
        "odoo_project",
    ],
    "license": "AGPL-3",
}
