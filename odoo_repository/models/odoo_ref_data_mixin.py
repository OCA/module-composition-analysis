# Copyright 2026 ACSONE SA/NV (<https://acsone.eu>)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import threading
from contextlib import contextmanager

import psycopg2.errors

from odoo import api, models


class OdooRefDataMixin(models.AbstractModel):
    """Shared helpers to safely create reference data cached by ``@tools.ormcache``."""

    _name = "odoo.ref.data.mixin"
    _description = "Odoo Ref Data Mixin"

    @contextmanager
    def _ref_data_cursor(self):
        """Yield the cursor to use for an isolated reference-data creation.

        This method is a context manager that yields a cursor to use for creating
        reference data in a separate transaction. If the current environment is in
        test mode, it yields the current cursor instead, since in test mode we
        don't want to create a new transaction.
        """
        in_test_mode = self.env.registry.in_test_mode() or getattr(
            threading.current_thread(), "testing", False
        )
        if in_test_mode:
            yield self.env.cr
        else:
            with self.pool.cursor() as new_cr:
                yield new_cr

    def _create_ref_data(self, model_name, domain, values):
        """Create a single get-or-create reference record in its own
        dedicated, immediately-committed transaction, and return its id.

        ``@tools.ormcache`` is a process-wide cache that is never invalidated
        by a SQL ROLLBACK. If a newly created record's id were cached from
        within the caller's (still uncommitted) transaction, and that
        transaction was later rolled back for an unrelated reason (e.g. a
        conflicting concurrent queue job), the cache would keep returning an
        id that no longer exists in the database. Creating and committing the
        record here, independently of the caller's transaction, guarantees
        the returned id always stays valid, whatever happens to the caller's
        job afterwards.

        A concurrent job may create the same record at the same time: the
        unique SQL constraint on the target model then raises
        ``UniqueViolation`` for the loser, which simply looks up the row the
        winner just committed.
        """
        with self._ref_data_cursor() as new_cr:
            env = api.Environment(new_cr, self.env.uid, self.env.context)
            model = env[model_name].sudo()
            try:
                with new_cr.savepoint():
                    return model.create(values).id
            except psycopg2.errors.UniqueViolation:
                return model.search(domain, limit=1).id

    def _create_ref_data_multi(self, model_name, search_field, values_list):
        """Same as ``_create_ref_data``, but for a batch of records sharing
        the same natural-key field (e.g. several new authors discovered at
        once). Each record is created individually, in its own savepoint, so
        that a conflict on one of them does not abort the creation of the
        others.
        """
        ids = []
        with self._ref_data_cursor() as new_cr:
            env = api.Environment(new_cr, self.env.uid, self.env.context)
            model = env[model_name].sudo()
            for values in values_list:
                try:
                    with new_cr.savepoint():
                        ids.append(model.create(values).id)
                except psycopg2.errors.UniqueViolation:
                    existing = model.search(
                        [(search_field, "=", values[search_field])], limit=1
                    )
                    ids.append(existing.id)
        return ids
