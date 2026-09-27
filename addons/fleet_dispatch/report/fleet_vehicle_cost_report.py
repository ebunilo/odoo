# -*- coding: utf-8 -*-

from odoo import fields, models


class FleetVehicleCostReport(models.Model):
    _inherit = 'fleet.vehicle.cost.report'

    vehicle_type = fields.Selection(selection_add=[('truck', 'Truck')])
