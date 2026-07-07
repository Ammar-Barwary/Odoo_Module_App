from odoo import models, fields


class AccountJournal(models.Model):
    _inherit = "account.journal"

    cash_transaction_sequence_id = fields.Many2one("ir.sequence", string="Cash Transaction Sequence", copy=False)

    def _fill_bank_cash_dashboard_data(self, dashboard_data):
        super()._fill_bank_cash_dashboard_data(dashboard_data)

        CashList = self.env["journal.cash.list"]
        for journal in self.filtered(lambda j: j.type == "cash"):
            currency = journal.currency_id or journal.company_id.currency_id

            custom = CashList.search([
                ("journal_id", "=", journal.id),
                ("state", "=", "posted"),
            ])
            if not custom:
                continue

            # Convert each transaction's amount to the journal's currency
            company = journal.company_id
            custom_total = 0.0
            for t in custom:
                amount = abs(t.amount)
                sign = 1 if t.amount > 0 else -1
                converted = t.currency_id._convert(amount, currency, company, t.date)
                custom_total += sign * converted

            our_move_ids = custom.mapped("move_id").ids

            # Recalculate misc balance excluding our move lines
            date_limit = journal.last_statement_id.date or journal.company_id.fiscalyear_lock_date
            base_domain = [
                *self.env["account.move.line"]._check_company_domain(self.env.companies),
                ("statement_line_id", "=", False),
                ("parent_state", "=", "posted"),
                ("payment_id", "=", False),
            ]
            if our_move_ids:
                base_domain.append(("move_id", "not in", our_move_ids))

            per_journal = (
                [("account_id", "=", journal.default_account_id.id), ("date", ">", date_limit)]
                if date_limit
                else [("account_id", "=", journal.default_account_id.id)]
            )
            misc_domain = base_domain + per_journal

            misc_result = self.env["account.move.line"]._read_group(
                domain=misc_domain,
                aggregates=["amount_currency:sum", "id:count", "currency_id:recordset"],
                groupby=["account_id"],
            )
            misc_balance = 0.0
            misc_count = 0
            misc_currencies = currency
            for account, balance, count_lines, currencies in misc_result:
                if account == journal.default_account_id:
                    misc_balance = balance
                    misc_count = count_lines
                    misc_currencies = currencies
                    break

            _, dpb = self._get_direct_bank_payments().get(journal.id, (0, 0))
            new_balance = journal.current_statement_balance + dpb + custom_total

            # Empty misc_currencies means all lines are in company currency
            currency_consistent = (not misc_currencies) or misc_currencies == currency
            dashboard_data[journal.id].update({
                "account_balance": currency.format(new_balance),
                "nb_lines_bank_account_balance": True,  # <-- add this
                "nb_misc_operations": misc_count,
                "misc_class": "text-warning" if not currency_consistent else "",
                "misc_operations_balance": currency.format(misc_balance) if currency_consistent else None,
            })
