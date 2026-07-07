from odoo import api, models
from odoo.exceptions import ValidationError


class AccountFullReconcile(models.Model):
    _inherit = "account.full.reconcile"

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        for rec in recs:
            transfer_account = self.env.company.transfer_account_id
            if not transfer_account:
                raise ValidationError("Internal Transfer account is not configured in Company settings.")
            transfer_lines = rec.reconciled_line_ids.filtered(
                lambda l: l.account_id == transfer_account
            )
            if len(transfer_lines) < 2:
                continue
            cash_records = self.env['journal.cash.list'].search([
                ('move_id', 'in', transfer_lines.move_id.ids),
            ])
            if cash_records:
                seq = self.env['ir.sequence'].search([
                    ('code', '=', 'journal.cash.list.matching'),
                ], limit=1)
                if not seq:
                    seq = self.env['ir.sequence'].create({
                        'name': 'Journal Cash List Matching',
                        'code': 'journal.cash.list.matching',
                        'padding': 5,
                    })
                next_num = seq.number_next_actual
                seq.next_by_id()
                cash_records.write({'matching_number': next_num})
        return recs