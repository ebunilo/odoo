# -*- coding: utf-8 -*-

from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    dispatch_id = fields.Many2one(
        'fleet.dispatch',
        string='Dispatch',
        readonly=True,
        index='btree_not_null',
        copy=False,
    )
    dispatch_vehicle_id = fields.Many2one(
        related='dispatch_id.vehicle_id',
        string='Dispatch Truck',
        store=True,
    )
    dispatch_driver_id = fields.Many2one(
        related='dispatch_id.driver_id',
        string='Dispatch Driver',
        store=True,
    )


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    dispatch_id = fields.Many2one(related='move_id.dispatch_id', string='Dispatch')
    dispatch_truck_plate = fields.Char(related='move_id.dispatch_id.truck_plate', string='Truck No.')
    dispatch_driver_id = fields.Many2one(related='move_id.dispatch_driver_id', string='Driver')
