# -*- coding: utf-8 -*-

from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    dispatch_id = fields.Many2one(
        'fleet.dispatch',
        string='Dispatch',
        readonly=True,
        index='btree_not_null',
        copy=False,
    )
