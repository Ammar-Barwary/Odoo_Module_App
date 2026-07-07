from odoo import models

class AccountMove(models.Model):
    _inherit = "account.move"

    def _compute_journal_id(self):
        cash_moves = self.filtered(lambda m: m.journal_id.type == 'cash')
        other_moves = self - cash_moves
        if other_moves:
            super(AccountMove, other_moves)._compute_journal_id()