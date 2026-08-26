# Copyright 2026 ACSONE SA/NV (<https://acsone.eu>)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
{
    "name": "Odoo Project - Dependency Resolver",
    "summary": "Resolve the modules of a project from its dependency file.",
    "version": "18.0.1.0.0",
    "category": "Tools",
    "author": "ACSONE SA/NV, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/module-composition-analysis",
    "data": [
        "data/queue_job.xml",
        "views/odoo_project.xml",
        "views/odoo_project_module.xml",
    ],
    "installable": True,
    "depends": [
        # OCA/queue
        "queue_job",
        # OCA/module-composition-analysis
        "odoo_project",
        "odoo_repository_fork",
    ],
    "external_dependencies": {
        "python": [
            "gitpython",
            "odoo-addons-parser",
        ],
    },
    "license": "AGPL-3",
}
