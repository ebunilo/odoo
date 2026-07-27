# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


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

    # ── State Transitions ─────────────────────────────────────────────────────

    def action_dispatch(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft dispatches can be confirmed.'))
            if rec.diesel_litres <= 0:
                raise UserError(_('Diesel litres must be greater than zero.'))
            rec.state = 'dispatched'

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
            rec.state = 'cancelled'

    def action_reset_draft(self):
        for rec in self:
            if rec.state != 'cancelled':
                raise UserError(_('Only cancelled dispatches can be reset to draft.'))
            rec.state = 'draft'
