# -*- coding: utf-8 -*-

from odoo import api, fields, models


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    dispatch_count = fields.Integer(compute='_compute_dispatch_count')

    # Trucks reuse plan_to_change_car: fleet only flags cars and bikes when a
    # driver is lined up for another vehicle of the same type.
    @api.model_create_multi
    def create(self, vals_list):
        state_waiting_list = self.env.ref('fleet.fleet_vehicle_state_waiting_list', raise_if_not_found=False)
        future_drivers = {
            vals['future_driver_id'] for vals in vals_list
            if vals.get('future_driver_id') and vals.get('vehicle_type') == 'truck'
            and (not state_waiting_list or state_waiting_list.id != vals.get('state_id'))
        }
        if future_drivers:
            self.search([
                ('driver_id', 'in', list(future_drivers)),
                ('vehicle_type', '=', 'truck'),
            ]).plan_to_change_car = True
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('future_driver_id'):
            state_waiting_list = self.env.ref('fleet.fleet_vehicle_state_waiting_list', raise_if_not_found=False)
            state_new_request = self.env.ref('fleet.fleet_vehicle_state_new_request', raise_if_not_found=False)
            trucks = self.filtered(lambda vehicle: vehicle.vehicle_type == 'truck' and (
                not state_waiting_list
                or vals.get('state_id', vehicle.state_id.id) not in [state_waiting_list.id, state_new_request.id]))
            if trucks:
                self.search([
                    ('driver_id', '=', vals['future_driver_id']),
                    ('vehicle_type', '=', 'truck'),
                    ('id', 'not in', self.ids),
                ]).plan_to_change_car = True
        return super().write(vals)

    def _compute_dispatch_count(self):
        counts = dict(self.env['fleet.dispatch']._read_group(
            [('vehicle_id', 'in', self.ids)], ['vehicle_id'], ['__count'],
        ))
        for vehicle in self:
            vehicle.dispatch_count = counts.get(vehicle, 0)

    def action_view_dispatches(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('fleet_dispatch.fleet_dispatch_action')
        action['domain'] = [('vehicle_id', '=', self.id)]
        action['context'] = {'default_vehicle_id': self.id}
        return action
