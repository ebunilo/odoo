# -*- coding: utf-8 -*-

from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTruckVehicleType(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'Mercedes-Benz Trucks'})
        cls.truck_model = cls.env['fleet.vehicle.model'].create({
            'name': 'Actros MP2',
            'brand_id': brand.id,
            'vehicle_type': 'truck',
        })
        cls.driver = cls.env['res.partner'].create({'name': 'Truck Driver'})
        cls.next_driver = cls.env['res.partner'].create({'name': 'Next Truck Driver'})
        cls.registered = cls.env.ref('fleet.fleet_vehicle_state_registered')

    def _create_truck(self, plate, **vals):
        return self.env['fleet.vehicle'].create({
            'model_id': self.truck_model.id,
            'license_plate': plate,
            'state_id': self.registered.id,
            **vals,
        })

    def test_truck_vehicle_and_odometer(self):
        truck = self._create_truck('BZR 143XC', driver_id=self.driver.id, odometer=534422.6)
        self.assertEqual(truck.vehicle_type, 'truck')
        self.assertEqual(truck.odometer, 534422.6)
        self.assertEqual(self.env['fleet.vehicle'].search_count([('vehicle_type', '=', 'truck'), ('id', '=', truck.id)]), 1)

    def test_future_driver_flags_their_current_truck(self):
        current = self._create_truck('ABB 894XA', driver_id=self.next_driver.id)
        other = self._create_truck('ETU 892XA', driver_id=self.driver.id)
        other.future_driver_id = self.next_driver
        self.assertTrue(current.plan_to_change_car)

        other.action_accept_driver_change()
        self.assertEqual(other.driver_id, self.next_driver)
        self.assertFalse(current.driver_id)
        self.assertFalse(current.plan_to_change_car)

    def test_form_shows_car_fields_for_trucks(self):
        truck = self._create_truck('UMG 126XC')
        with Form(truck) as form:
            form.odometer = 1000.0
            form.seats = 2
        self.assertEqual(truck.odometer, 1000.0)
        self.assertEqual(truck.seats, 2)
