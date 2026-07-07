from odoo import api, models


class CashTransactionReport(models.AbstractModel):
    _name = 'report.currency_transaction.report_journal_cash_list'
    _description = 'Cash Transaction Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['journal.cash.list'].browse(docids)
        company = self.env.company
        company_currency = company.currency_id
        transfer_account = company.transfer_account_id

        reconciliation_pairs = []
        processed = self.env['journal.cash.list']

        for doc in docs:
            if doc in processed:
                continue

            if doc.matching_number:
                partner = self.env['journal.cash.list'].search([
                    ('matching_number', '=', doc.matching_number),
                    ('id', '!=', doc.id),
                ], limit=1)
                if partner:
                    side_a = self._prepare_side(doc, company_currency, transfer_account)
                    side_b = self._prepare_side(partner, company_currency, transfer_account)
                    gain_loss = self._compute_gain_loss(side_a, side_b)
                    reconciliation_pairs.append({
                        'side_a': side_a,
                        'side_b': side_b,
                        'matching_number': doc.matching_number,
                        'gain_loss': gain_loss,
                    })
                    processed |= doc + partner
                    continue

            reconciliation_pairs.append({
                'side_a': self._prepare_side(doc, company_currency, transfer_account),
                'side_b': False,
                'matching_number': False,
                'gain_loss': False,
            })
            processed |= doc

        return {
            'doc_ids': docids,
            'doc_model': 'journal.cash.list',
            'docs': docs,
            'reconciliation_pairs': reconciliation_pairs,
            'company_currency': company_currency,
        }

    def _prepare_side(self, record, company_currency, transfer_account):
        transfer_line = False
        company_amount = 0.0
        amount_currency = 0.0
        line_currency = False
        has_foreign_currency = False
        exchange_rate = False

        if record.move_id:
            transfer_line = self.env['account.move.line'].search([
                ('move_id', '=', record.move_id.id),
                ('account_id', '=', transfer_account.id),
            ], limit=1)

        if transfer_line:
            company_amount = transfer_line.debit or transfer_line.credit
            amount_currency = abs(transfer_line.amount_currency) if transfer_line.amount_currency else 0.0
            line_currency = transfer_line.currency_id or company_currency
            has_foreign_currency = line_currency != company_currency
            if has_foreign_currency and amount_currency:
                exchange_rate = round(company_amount / amount_currency, 6)
        else:
            line_currency = record.currency_id
            amount_currency = abs(record.amount) if record.amount else 0.0
            has_foreign_currency = record.currency_id != company_currency
            if has_foreign_currency and amount_currency:
                exchange_rate = round(company_amount / amount_currency, 6) if company_amount else False

        return {
            'record': record,
            'transfer_line': transfer_line,
            'company_amount': company_amount,
            'original_amount': abs(record.amount) if record.amount else 0.0,
            'record_currency': record.currency_id,
            'amount_currency': amount_currency,
            'line_currency': line_currency,
            'has_foreign_currency': has_foreign_currency,
            'exchange_rate': exchange_rate,
            'is_debit_side': bool(transfer_line and transfer_line.debit > 0),
        }

    def _compute_gain_loss(self, side_a, side_b):
        if side_a['is_debit_side']:
            debit_amount = side_a['company_amount']
            credit_amount = side_b['company_amount']
        else:
            debit_amount = side_b['company_amount']
            credit_amount = side_a['company_amount']

        if debit_amount == credit_amount:
            return {'type': False, 'amount': 0.0, 'rate': False}

        diff = abs(debit_amount - credit_amount)
        gl_type = 'loss' if debit_amount > credit_amount else 'gain'

        rate_side = side_a if side_a['has_foreign_currency'] else side_b
        return {
            'type': gl_type,
            'amount': diff,
            'rate': rate_side['exchange_rate'],
            'foreign_currency': rate_side['record_currency'].name if rate_side['record_currency'] else '',
        }
