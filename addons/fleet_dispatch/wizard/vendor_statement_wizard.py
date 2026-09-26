# -*- coding: utf-8 -*-

from odoo import api, fields, models


class FleetDispatchVendorStatement(models.TransientModel):
    _name = 'fleet.dispatch.vendor.statement'
    _inherit = 'account.common.partner.report'
    _description = 'Fuel Vendor Statement'

    partner_id = fields.Many2one(
        'res.partner',
        string='Fuel Station',
        required=True,
    )
    result_selection = fields.Selection(default='supplier')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if (
            'partner_id' in fields_list
            and not res.get('partner_id')
            and self.env.context.get('active_model') == 'res.partner'
        ):
            res['partner_id'] = self.env.context.get('active_id')
        return res

    def _print_report(self, data):
        data['form'].update({
            'partner_id': self.partner_id.id,
            'result_selection': self.result_selection,
        })
        return self.env.ref('fleet_dispatch.action_report_vendor_statement') \
            .with_context(landscape=True).report_action(self, data=data)

    def action_view_lines(self):
        self.ensure_one()
        domain = [
            ('partner_id', '=', self.partner_id.id),
            ('account_id.account_type', 'in', self._get_account_types()),
            ('company_id', '=', self.company_id.id),
            ('journal_id', 'in', self.journal_ids.ids),
            ('parent_state', '=', 'posted') if self.target_move == 'posted'
            else ('parent_state', '!=', 'cancel'),
        ]
        if self.date_from:
            domain.append(('date', '>=', self.date_from))
        if self.date_to:
            domain.append(('date', '<=', self.date_to))
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Statement lines: %s', self.partner_id.display_name),
            'res_model': 'account.move.line',
            'view_mode': 'list',
            'views': [(self.env.ref('fleet_dispatch.view_move_line_list_vendor_statement').id, 'list')],
            'domain': domain,
            'context': {'create': False},
        }

    def _get_account_types(self):
        return {
            'supplier': ['liability_payable'],
            'customer': ['asset_receivable'],
        }.get(self.result_selection, ['asset_receivable', 'liability_payable'])
