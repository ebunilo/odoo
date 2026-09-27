# -*- coding: utf-8 -*-

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    dispatch_fuel_product_id = fields.Many2one(
        'product.product',
        string='Dispatch Fuel Product',
        help='Product used on dispatch vendor bills for diesel. '
             'Its expense account receives the fuel cost.',
    )
    dispatch_advance_product_id = fields.Many2one(
        'product.product',
        string='Dispatch Cash Advance Product',
        help='Product used on dispatch vendor bills for the cash advance '
             'paid to the driver. Its expense account receives the advance.',
    )
    dispatch_auto_post_bill = fields.Boolean(
        string='Auto-post Dispatch Bills',
        default=True,
    )
