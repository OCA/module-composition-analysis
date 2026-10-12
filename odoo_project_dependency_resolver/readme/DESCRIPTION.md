Projects usually pin the exact version of every module they install in a
dependency file, such as the `requirements.txt` produced by pip. Maintaining
the very same list a second time by hand in Odoo MCA is tedious and drifts
away from reality as soon as a dependency is bumped.

This module reads that file straight from the repository of the project and
rebuilds its modules from it, every time the project is scanned.
