# Copyright 2026  Akretion (https://www.akretion.com).
# @author Sébastien Alix <sebastien.alix@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from .common import Common


class TestOdooBranch(Common):
    def test_next_id_previous_id(self):
        """Test next_id and previous_id computed fields."""
        branch_model = self.env["odoo.branch"]
        branches = branch_model.search([], order="sequence", limit=3)
        first_branch, second_branch, third_branch = (
            branches[0],
            branches[1],
            branches[2],
        )
        # Test middle branch
        self.assertEqual(second_branch.previous_id, first_branch)
        self.assertEqual(second_branch.next_id, third_branch)
        # Test first branch
        self.assertFalse(first_branch.previous_id)
        self.assertEqual(first_branch.next_id, second_branch)
        # Test last branch
        branches = branch_model.search([], order="sequence DESC", limit=2)
        last_branch, ante_branch = branches[0], branches[1]
        self.assertEqual(last_branch.previous_id, ante_branch)
        self.assertFalse(last_branch.next_id)
