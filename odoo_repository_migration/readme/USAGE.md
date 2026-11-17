To enable this feature, the option *Collect migration data* should be
enabled on repositories (opt-in).

To record what a module became starting from a given Odoo version, you
should do it through the *Odoo Repositories / Data / Modules /
Timelines* menu.

A timeline is created as *draft*: it has no effect on the migration data
until it is confirmed. Only confirmed timelines drive the analysis; drafts
can be freely edited, confirmed ones become read-only (send them back to
draft to edit them).

Once the scheduled action ran, the migration data are available on each
module in *Migration* tab, or through the *Odoo Repositories / Data /
Modules / Migrations* menu.
