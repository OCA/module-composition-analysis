This module allows you to declare your Odoo projects with the list of installed modules.

Based on the data collected by `odoo_repository` module, it will:

- give some code stats (lines of code, and how they are spread among Odoo/OCA/your organization)
- give the list of modules available for upgrade in current Odoo version (based on module versions)
- list modules still hosted in a pending Pull Request (so not yet merged, could be considered as technical debt)
- list modules available in your project repository (if any) but not installed in your database (dead code)
