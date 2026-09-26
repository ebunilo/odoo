# -*- coding: utf-8 -*-

from odoo import fields, models


class FleetVehicleModel(models.Model):
    _inherit = 'fleet.vehicle.model'

    vehicle_type = fields.Selection(
        selection_add=[('truck', 'Truck')],
        ondelete={'truck': 'set default'},
    )
