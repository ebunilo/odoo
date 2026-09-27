# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import api, models, _
from odoo.exceptions import UserError


class ReportVendorStatement(models.AbstractModel):
    _name = 'report.fleet_dispatch.report_vendor_statement'
    _description = 'Fuel Vendor Statement Report'

    ACCOUNT_TYPES = {
        'supplier': ('liability_payable',),
        'customer': ('asset_receivable',),
        'customer_supplier': ('asset_receivable', 'liability_payable'),
    }

    def _get_move_lines(self, form, partner, initial_bal=False):
        """Return the partner's move lines on the selected accounts, filtered
        with accounting_pdf_reports' ``_query_get`` (dates, journals, target
        moves, company). ``initial_bal`` returns the lines before date_from."""
        context = dict(form.get('used_context', {}))
        if initial_bal:
            if not form.get('date_from'):
                return self.env['account.move.line']
            context.update(initial_bal=True, strict_range=True, date_to=False)
        MoveLine = self.env['account.move.line'].with_context(context)
        self.env.flush_all()
        tables, where_clause, where_params = MoveLine._query_get()
        account_types = self.ACCOUNT_TYPES[form.get('result_selection') or 'supplier']
        self.env.cr.execute(f"""
            SELECT "account_move_line".id
              FROM {tables}
              JOIN account_account acc ON acc.id = "account_move_line".account_id
             WHERE {where_clause}
               AND "account_move_line".partner_id = %s
               AND acc.account_type IN %s
          ORDER BY "account_move_line".date, "account_move_line".move_id, "account_move_line".id
        """, where_params + [partner.id, account_types])
        return self.env['account.move.line'].browse(r[0] for r in self.env.cr.fetchall())

    def _get_statement(self, form, partner):
        # Payables are booked on the commercial partner, so a station that is
        # a branch contact is reported under its parent company.
        partner = partner.commercial_partner_id
        opening = sum(l.debit - l.credit for l in self._get_move_lines(form, partner, initial_bal=True))
        balance = opening
        lines = []
        trucks = defaultdict(lambda: {'trips': 0, 'litres': 0.0, 'fuel': 0.0, 'advance': 0.0})
        seen_dispatches = set()
        for aml in self._get_move_lines(form, partner):
            balance += aml.debit - aml.credit
            dispatch = aml.move_id.dispatch_id
            lines.append({
                'date': aml.date,
                'move_name': aml.move_id.name,
                'journal': aml.journal_id.code,
                'ref': aml.move_id.ref or '',
                'label': aml.name or '',
                'dispatch': dispatch.name or '',
                'truck': dispatch.truck_plate or dispatch.vehicle_id.display_name or '',
                'driver': dispatch.driver_id.name or '',
                'destination': dispatch.destination or '',
                'debit': aml.debit,
                'credit': aml.credit,
                'balance': balance,
            })
            # Summarise each trip once, from its original bill only.
            if dispatch and dispatch.id not in seen_dispatches and aml.move_id == dispatch.vendor_bill_id:
                seen_dispatches.add(dispatch.id)
                key = dispatch.truck_plate or dispatch.vehicle_id.display_name
                trucks[key]['trips'] += 1
                trucks[key]['litres'] += dispatch.diesel_litres
                trucks[key]['fuel'] += dispatch.fuel_cost
                trucks[key]['advance'] += dispatch.cash_advance
        return {
            'partner': partner,
            'opening': opening,
            'lines': lines,
            'total_debit': sum(l['debit'] for l in lines),
            'total_credit': sum(l['credit'] for l in lines),
            'closing': balance,
            'trucks': sorted(trucks.items()),
        }

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data or not data.get('form'):
            raise UserError(_('Form content is missing, this report cannot be printed.'))
        form = data['form']
        partner = self.env['res.partner'].browse(form['partner_id']).commercial_partner_id
        company = self.env['res.company'].browse(form['company_id'][0])
        return {
            'doc_ids': partner.ids,
            'doc_model': 'res.partner',
            'docs': partner,
            'data': data,
            'company': company,
            'currency': company.currency_id,
            'statement': self._get_statement(form, partner),
        }
