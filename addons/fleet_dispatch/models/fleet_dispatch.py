# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError

# Fields that end up on the vendor bill and therefore must not change once
# the bill has been generated.
LOCKED_FIELDS = {
    'vehicle_id', 'driver_id', 'fuel_station_id', 'dispatch_date',
    'diesel_litres', 'fuel_price_per_litre', 'cash_advance', 'company_id',
}


class FleetDispatch(models.Model):
    _name = 'fleet.dispatch'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Truck Dispatch'
    _order = 'dispatch_date desc, id desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )

    # ── Vehicle & Personnel ──────────────────────────────────────────────────
    vehicle_id = fields.Many2one(
        'fleet.vehicle',
        string='Truck',
        required=True,
        tracking=True,
        index=True,
    )
    truck_plate = fields.Char(
        string='Truck No.',
        related='vehicle_id.license_plate',
        store=True,
    )
    driver_id = fields.Many2one(
        'res.partner',
        string='Driver',
        compute='_compute_driver_id',
        store=True,
        readonly=False,
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
    )

    # ── Fuelling ─────────────────────────────────────────────────────────────
    fuel_station_id = fields.Many2one(
        'res.partner',
        string='Fuel Station',
        required=True,
        tracking=True,
        help='The fuel vendor where the truck is filled up.',
    )
    dispatch_date = fields.Date(
        string='Dispatch Date',
        default=fields.Date.context_today,
        required=True,
        tracking=True,
    )
    diesel_litres = fields.Float(
        string='Diesel (Litres)',
        digits=(16, 2),
        required=True,
        tracking=True,
        help='Volume of diesel dispensed by the fuel vendor.',
    )
    fuel_price_per_litre = fields.Monetary(
        string='Price per Litre',
        currency_field='currency_id',
        tracking=True,
        help='Unit price of diesel at the fuel station.',
    )
    fuel_cost = fields.Monetary(
        string='Fuel Cost',
        currency_field='currency_id',
        compute='_compute_fuel_cost',
        store=True,
        help='Total cost of diesel (litres × price per litre).',
    )

    # ── Cash Advance ─────────────────────────────────────────────────────────
    cash_advance = fields.Monetary(
        string='Cash Advance',
        currency_field='currency_id',
        required=True,
        tracking=True,
        help='Amount of money given to the driver by the fuel vendor.',
    )
    total_reimbursable = fields.Monetary(
        string='Total Reimbursable',
        currency_field='currency_id',
        compute='_compute_total_reimbursable',
        store=True,
        help='Total amount to be reimbursed to the fuel vendor '
             '(fuel cost + cash advance).',
    )

    # ── Trip Information ─────────────────────────────────────────────────────
    origin = fields.Char(
        string='Origin',
        tracking=True,
        help='Starting point of the dispatch trip.',
    )
    destination = fields.Char(
        string='Destination',
        required=True,
        tracking=True,
        help='Delivery destination of the loaded truck.',
    )
    cargo_description = fields.Char(
        string='Cargo',
        tracking=True,
        help='Brief description of the goods being transported.',
    )
    odometer = fields.Float(
        string='Odometer at Dispatch',
        digits=(16, 2),
        help='Current odometer reading of the truck at time of dispatch.',
    )
    odometer_unit = fields.Selection(
        related='vehicle_id.odometer_unit',
        string='Unit',
        readonly=True,
    )

    # ── Status ───────────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ('draft',       'Draft'),
            ('dispatched',  'Dispatched'),
            ('returned',    'Returned'),
            ('done',        'Done'),
            ('cancelled',   'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )

    notes = fields.Text(string='Notes')

    # ── Accounting ───────────────────────────────────────────────────────────
    vendor_bill_id = fields.Many2one(
        'account.move',
        string='Vendor Bill',
        readonly=True,
        copy=False,
    )
    bill_payment_state = fields.Selection(
        related='vendor_bill_id.payment_state',
        string='Bill Payment Status',
    )

    # ── Compute Methods ───────────────────────────────────────────────────────

    @api.depends('vehicle_id')
    def _compute_driver_id(self):
        for rec in self:
            rec.driver_id = rec.vehicle_id.driver_id if rec.vehicle_id else False

    @api.depends('diesel_litres', 'fuel_price_per_litre')
    def _compute_fuel_cost(self):
        for rec in self:
            rec.fuel_cost = rec.diesel_litres * rec.fuel_price_per_litre

    @api.depends('fuel_cost', 'cash_advance')
    def _compute_total_reimbursable(self):
        for rec in self:
            rec.total_reimbursable = rec.fuel_cost + rec.cash_advance

    # ── Sequence ───────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'fleet.dispatch'
                ) or _('New')
        return super().create(vals_list)

    def write(self, vals):
        locked = LOCKED_FIELDS.intersection(vals)
        if locked and any(rec.state != 'draft' for rec in self):
            raise UserError(_(
                'Only draft dispatches can be modified. Cancel and reset the '
                'dispatch to draft to change: %(fields)s',
                fields=', '.join(self._fields[f].string for f in sorted(locked)),
            ))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_confirmed(self):
        if any(rec.state not in ('draft', 'cancelled') for rec in self):
            raise UserError(_('Only draft or cancelled dispatches can be deleted.'))

    # ── Accounting Documents ──────────────────────────────────────────────────

    def _get_dispatch_products(self):
        self.ensure_one()
        company = self.company_id
        fuel_product = company.dispatch_fuel_product_id \
            or self.env.ref('fleet_dispatch.product_dispatch_diesel', raise_if_not_found=False)
        advance_product = company.dispatch_advance_product_id \
            or self.env.ref('fleet_dispatch.product_dispatch_cash_advance', raise_if_not_found=False)
        if not fuel_product or not advance_product:
            raise UserError(_(
                'Configure the Diesel and Cash Advance products in '
                'Fleet ▸ Configuration ▸ Settings before confirming a dispatch.'
            ))
        return fuel_product, advance_product

    def _get_trip_label(self):
        self.ensure_one()
        return _(
            'Truck %(truck)s / Driver %(driver)s',
            truck=self.truck_plate or self.vehicle_id.display_name,
            driver=self.driver_id.name or _('N/A'),
        )

    def _prepare_bill_line_vals(self):
        self.ensure_one()
        fuel_product, advance_product = self._get_dispatch_products()
        trip = self._get_trip_label()
        lines = [{
            'product_id': fuel_product.id,
            'name': _(
                '%(ref)s – Diesel %(litres)s L – %(trip)s',
                ref=self.name, litres=self.diesel_litres, trip=trip,
            ),
            'quantity': self.diesel_litres,
            'product_uom_id': fuel_product.uom_id.id,
            'price_unit': self.fuel_price_per_litre,
        }]
        if not self.currency_id.is_zero(self.cash_advance):
            lines.append({
                'product_id': advance_product.id,
                'name': _(
                    '%(ref)s – Cash advance to driver – %(trip)s',
                    ref=self.name, trip=trip,
                ),
                'quantity': 1.0,
                'product_uom_id': advance_product.uom_id.id,
                'price_unit': self.cash_advance,
            })
        return lines

    def _prepare_vendor_bill_vals(self):
        self.ensure_one()
        return {
            'move_type': 'in_invoice',
            'partner_id': self.fuel_station_id.id,
            'invoice_date': self.dispatch_date,
            'date': self.dispatch_date,
            'ref': self.name,
            'invoice_origin': self.name,
            'dispatch_id': self.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'invoice_line_ids': [
                fields.Command.create(line) for line in self._prepare_bill_line_vals()
            ],
        }

    def _create_vendor_bill(self):
        """Create the fuel station's vendor bill (and post it) so the payable
        hits the ledger as soon as the dispatch is confirmed.

        Runs as superuser: fleet users confirming a dispatch do not need
        accounting rights.
        """
        for rec in self:
            if rec.vendor_bill_id:
                continue
            if rec.fuel_price_per_litre <= 0:
                raise UserError(_('Price per litre must be greater than zero.'))
            if rec.cash_advance < 0:
                raise UserError(_('Cash advance cannot be negative.'))
            company = rec.company_id
            bill = self.env['account.move'].sudo().with_company(company).create(
                rec._prepare_vendor_bill_vals()
            )
            if company.dispatch_auto_post_bill:
                bill.action_post()
            rec.vendor_bill_id = bill
            rec.message_post(body=_(
                'Vendor bill %(bill)s created for %(vendor)s.',
                bill=bill._get_html_link(),
                vendor=rec.fuel_station_id.name,
            ))

    def _cancel_vendor_documents(self):
        for rec in self:
            bill = rec.vendor_bill_id.sudo()
            if bill and bill.state == 'posted':
                if bill.payment_state not in ('not_paid', 'reversed'):
                    raise UserError(_(
                        'The vendor bill %(bill)s of dispatch %(dispatch)s is already '
                        '(partially) paid. Unreconcile the payment before cancelling.',
                        bill=bill.name, dispatch=rec.name,
                    ))
                lock_date = bill.company_id._get_user_fiscal_lock_date(bill.journal_id)
                if bill.date <= lock_date:
                    # Locked period: keep the bill and book a credit note instead.
                    bill._reverse_moves([{
                        'date': fields.Date.context_today(rec),
                        'invoice_date': fields.Date.context_today(rec),
                        'ref': _('Reversal of %s', rec.name),
                        'dispatch_id': rec.id,
                    }], cancel=True)
                else:
                    bill.button_draft()
                    bill.button_cancel()
            elif bill and bill.state == 'draft':
                bill.button_cancel()
            if bill.state == 'posted':
                rec.message_post(body=_(
                    'Vendor bill reversed by a credit note because its period is locked.'
                ))
            elif bill:
                rec.message_post(body=_('Vendor bill cancelled.'))

    def action_view_vendor_bill(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.vendor_bill_id.id,
            'view_mode': 'form',
        }

    def action_open_vendor_statement(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'fleet_dispatch.action_fleet_dispatch_vendor_statement'
        )
        action['context'] = {'default_partner_id': self.fuel_station_id.id}
        return action

    # ── State Transitions ─────────────────────────────────────────────────────

    def action_dispatch(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft dispatches can be confirmed.'))
            if rec.diesel_litres <= 0:
                raise UserError(_('Diesel litres must be greater than zero.'))
        self._create_vendor_bill()
        self.state = 'dispatched'

    def action_return(self):
        for rec in self:
            if rec.state != 'dispatched':
                raise UserError(_('Only dispatched trucks can be marked as returned.'))
            rec.state = 'returned'

    def action_done(self):
        for rec in self:
            if rec.state != 'returned':
                raise UserError(_('Only returned dispatches can be marked as done.'))
            rec.state = 'done'

    def action_cancel(self):
        for rec in self:
            if rec.state == 'done':
                raise UserError(_('A completed dispatch cannot be cancelled.'))
        self._cancel_vendor_documents()
        self.state = 'cancelled'

    def action_reset_draft(self):
        for rec in self:
            if rec.state != 'cancelled':
                raise UserError(_('Only cancelled dispatches can be reset to draft.'))
        # A fresh bill is generated on the next confirmation.
        self.write({'state': 'draft', 'vendor_bill_id': False})
