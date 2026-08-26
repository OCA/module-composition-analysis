A module is not always installed from the repository it belongs to. Freezing
one built from unmerged pull requests is commonly done by pinning a revision
of a fork, and that fork is nowhere in Odoo MCA: its ancestry has to be asked
to GitHub over and over, and nothing holds the credentials a private one needs
to be read.

This module registers a fork as a repository of its own, pointing at the one
it originates from.
