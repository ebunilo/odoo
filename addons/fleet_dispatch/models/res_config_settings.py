# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    dispatch_fuel_product_id = fields.Many2one(
        related='company_id.dispatch_fuel_product_id', readonly=False,
    )
    dispatch_advance_product_id = fields.Many2one(
        related='company_id.dispatch_advance_product_id', readonly=False,
    )
    dispatch_auto_post_bill = fields.Boolean(
        related='company_id.dispatch_auto_post_bill', readonly=False,
    )
