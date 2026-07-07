from odoo import models, fields, api
from odoo.exceptions import ValidationError, MissingError


class JournalCashList(models.Model):
    _name = "journal.cash.list"
    _inherit = ["mail.thread"]
    _description = "Cash Transaction Details"
    _rec_name = "name"

    name = fields.Char(string="Number", readonly=True, copy=False, default="Draft")
    display_number = fields.Char(
        string="Number", compute="_compute_display_number"
    )
    date = fields.Date(
        string="Date",
        default=fields.Date.today(),
        tracking=True,
        states={"draft": [("readonly", False)]},
    )
    memo_label = fields.Char(string="Label", required=True, tracking=True, states={"draft": [("readonly", False)]})
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Cash Journal",
        domain="[('type', '=', 'cash')]",
        default=lambda self: self.env["account.journal"].search([("type", "=", "cash")], limit=1),
        tracking=True,
        readonly=True,
        states={"draft": [("readonly", False)]},
    )
    currency_id = fields.Many2one("res.currency", string="Currency", states={"draft": [("readonly", False)]})
    amount = fields.Monetary(string="Amount", currency_field="currency_id", required=True, tracking=True, states={"draft": [("readonly", False)]})
    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Journal Entry",
        readonly=True,
        copy=False,
    )
    matching_number = fields.Integer(
        string="Matching",
        readonly=True,
        copy=False,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("posted", "Posted"),
        ],
        default="draft",
        store=True,
        string="Status",
        readonly=False,
        copy=False,
        tracking=True
    )

    def action_reconcile(self):
        selected_count = len(self)

        if selected_count != 2:
            raise MissingError("You need to select exactly two rows.")

        if any(rec.state != "posted" for rec in self):
            raise ValidationError("Both transactions must be posted.")

        company = self.env.company
        exchange_journal = company.currency_exchange_journal_id
        if not exchange_journal:
            raise ValidationError("Exchange Gain or Loss Journal is not configured in Company settings.")
        transfer_account = company.transfer_account_id
        if not transfer_account:
            raise ValidationError("Internal Transfer account is not configured in Company settings.")

        transfer_lines = self.env['account.move.line'].search([
            ('move_id', 'in', self.move_id.ids),
            ('account_id', '=', transfer_account.id),
        ])

        if len(transfer_lines) != 2:
            raise ValidationError("Could not find two transfer account lines to reconcile.")

        debit_line = transfer_lines.filtered(lambda l: l.debit > 0)
        credit_line = transfer_lines.filtered(lambda l: l.credit > 0)

        debit_amount = debit_line.debit
        credit_amount = credit_line.credit

        all_lines = transfer_lines

        if debit_amount != credit_amount:
            diff = abs(debit_amount - credit_amount)

            if debit_amount > credit_amount:
                gain_loss_account = company.expense_currency_exchange_account_id
                if not gain_loss_account:
                    raise ValidationError("Loss Exchange Rate Account is not configured in Company settings.")
                adj_line_vals = [
                    (0, 0, {'account_id': gain_loss_account.id, 'debit': diff, 'name': 'Loss on currency exchange'}),
                    (0, 0, {'account_id': transfer_account.id, 'credit': diff, 'name': 'Exchange Difference'}),
                ]
            else:
                gain_loss_account = company.income_currency_exchange_account_id
                if not gain_loss_account:
                    raise ValidationError("Gain Exchange Rate Account is not configured in Company settings.")
                adj_line_vals = [
                    (0, 0, {'account_id': transfer_account.id, 'debit': diff, 'name': 'Exchange Difference'}),
                    (0, 0, {'account_id': gain_loss_account.id, 'credit': diff, 'name': 'Gain on currency exchange'}),
                ]

            adjustment_move = self.env['account.move'].create({
                'journal_id': exchange_journal.id,
                'date': fields.Date.today(),
                'ref': "Exchange diff adjustment",
                'line_ids': adj_line_vals,
            })
            adjustment_move.action_post()

            # Include the adjustment's transfer line in the reconcile
            adj_transfer_line = adjustment_move.line_ids.filtered(
                lambda l: l.account_id == transfer_account
            )
            all_lines = transfer_lines + adj_transfer_line

        all_lines.reconcile()

    def action_unreconcile(self):
        selected_count = len(self)
        if selected_count != 2:
            raise MissingError("You need to select exactly two rows.")

        if any(rec.matching_number is None for rec in self):
            raise MissingError("Both selected rows must be reconciled.")

        matching_numbers = self.mapped('matching_number')
        if len(set(matching_numbers)) != 1:
            raise MissingError("Selected rows must have the same matching number.")

        transfer_account = self.env.company.transfer_account_id
        if not transfer_account:
            raise ValidationError("Internal Transfer account is not configured in Company settings.")

        transfer_lines = self.env['account.move.line'].search([
            ('move_id', 'in', self.move_id.ids),
            ('account_id', '=', transfer_account.id),
            ('full_reconcile_id', '!=', False),
        ])

        if not transfer_lines:
            raise ValidationError("No reconciled transfer account lines found.")

        # Find any adjustment move created during reconcile (when debit != credit)
        full_reconcile = transfer_lines[0].full_reconcile_id
        original_moves = self.move_id
        adjustment_moves = full_reconcile.reconciled_line_ids.move_id - original_moves

        # Remove the reconciliation
        transfer_lines.remove_move_reconcile()

        # Delete the exchange difference adjustment move
        for adj_move in adjustment_moves:
            if adj_move.state == 'posted':
                adj_move.button_draft()
            adj_move.unlink()

        # Clear the matching number
        self.write({'matching_number': False})

    def open_reconciled_item(self):
        self.ensure_one()

        partner = self.search([
            ('matching_number', '=', self.matching_number),
            ('id', '!=', self.id)
        ])

        if not partner:
            raise ValidationError("Error opening the reconciled item record.")

        return {
            'name': "Reconciled Item",
            'type': 'ir.actions.act_window',
            'res_model': 'journal.cash.list',
            'context': {'create': False},
            'view_mode': 'form',
            'res_id': partner.id
        }

    def open_journal_entry(self):
        self.ensure_one()

        return {
            'name': 'Journal Entry',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'context': {'create': False},
            'view_mode': 'form',
            'res_id': self.move_id.id
        }

    def action_post(self):
        transfer_account = self.env.company.transfer_account_id
        if not transfer_account:
            raise ValidationError("Internal Transfer account is not configured in Company settings.")
        for rec in self:
            if rec.name == "Draft":
                journal = rec.journal_id
                if not journal.cash_transaction_sequence_id:
                    seq = self.env["ir.sequence"].create({
                        "name": f"{journal.name} - Cash Transactions",
                        "code": f"journal.cash.list.{journal.id}",
                        "prefix": f"TRAN{journal.code.upper()}/%(year)s/",
                        "padding": 5,
                        "company_id": journal.company_id.id,
                    })
                    journal.cash_transaction_sequence_id = seq
                rec.name = journal.cash_transaction_sequence_id.next_by_id()

            cash_account = rec.journal_id.default_account_id
            company = rec.journal_id.company_id
            company_currency = company.currency_id

            amount_in_iqd = rec.currency_id._convert(
                abs(rec.amount), company_currency, company, rec.date)

            def line_vals(account, debit_amt, credit_amt):
                vals = {
                    "account_id": account.id,
                    "debit": debit_amt,
                    "credit": credit_amt,
                    "name": rec.memo_label,
                }
                if rec.currency_id and rec.currency_id != company_currency:
                    vals["currency_id"] = rec.currency_id.id
                    vals["amount_currency"] = abs(rec.amount) if debit_amt else -abs(rec.amount)
                return (0, 0, vals)

            if rec.amount > 0:
                move_lines = [
                    line_vals(cash_account, amount_in_iqd, 0.0),
                    line_vals(transfer_account, 0.0, amount_in_iqd),
                ]
            else:
                move_lines = [
                    line_vals(cash_account, 0.0, amount_in_iqd),
                    line_vals(transfer_account, amount_in_iqd, 0.0),
                ]

            move = rec.move_id
            if move and move.state == "draft":
                move.write({
                    "date": rec.date,
                    "ref": rec.memo_label,
                    "line_ids": [(5, 0, 0)] + move_lines,
                })
            else:
                move = self.env["account.move"].create({
                    "journal_id": rec.journal_id.id,
                    "date": rec.date,
                    "ref": rec.memo_label,
                    "line_ids": move_lines,
                })

            move.action_post()
            rec.write({"move_id": move.id, "state": "posted"})

    def action_draft(self):
        for rec in self:
            if rec.move_id:
                rec.move_id.button_draft()
            rec.state = "draft"

    def unlink(self):
        for rec in self:
            if rec.state == "posted":
                raise ValidationError("Cannot delete a posted transaction.")
            if rec.move_id:
                if rec.move_id.state == "posted":
                    rec.move_id.button_draft()
                rec.move_id.unlink()
        return super().unlink()

    def _track_subtype(self, init_values):
        self.ensure_one()
        if "state" in init_values:
            if self.state == "posted":
                return self.env.ref("currency_transaction.mt_transaction_posted")
            elif self.state == "draft":
                return self.env.ref("currency_transaction.mt_transaction_draft")
        return super()._track_subtype(init_values)

    @api.depends("name")
    def _compute_display_number(self):
        for rec in self:
            rec.display_number = "~" if rec.name == "Draft" else rec.name

    @api.onchange("journal_id")
    def _onchange_journal_id(self):
        if self.journal_id:
            self.currency_id = self.journal_id.currency_id or self.journal_id.company_id.currency_id
        else:
            self.currency_id = False

    @api.constrains("amount")
    def _check_amount(self):
        for rec in self:
            if not rec.amount or rec.amount == 0.0:
                raise ValidationError("Amount is not to be zero.")
