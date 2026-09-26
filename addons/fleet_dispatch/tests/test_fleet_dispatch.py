# -*- coding: utf-8 -*-

from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestFleetDispatch(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref('fleet.fleet_group_manager') \
            | cls.env.ref('purchase.group_purchase_user')
        cls.fuel_expense = cls.company_data['default_account_expense']
        cls.trip_expense = cls.fuel_expense.copy({'code': '610099', 'name': 'Trip Expenses'})
        cls.diesel = cls.env.ref('fleet_dispatch.product_dispatch_diesel')
        cls.advance = cls.env.ref('fleet_dispatch.product_dispatch_cash_advance')
        cls.diesel.property_account_expense_id = cls.fuel_expense
        cls.advance.property_account_expense_id = cls.trip_expense
        cls.env.company.write({
            'dispatch_fuel_product_id': cls.diesel.id,
            'dispatch_advance_product_id': cls.advance.id,
            'dispatch_auto_post_bill': True,
        })

        brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'MAN'})
        model = cls.env['fleet.vehicle.model'].create({'name': 'TGS', 'brand_id': brand.id})
        cls.driver = cls.env['res.partner'].create({'name': 'John Driver'})
        cls.truck = cls.env['fleet.vehicle'].create({
            'model_id': model.id,
            'license_plate': 'ABC-123-XY',
            'driver_id': cls.driver.id,
        })
        cls.station = cls.env['res.partner'].create({'name': 'Mega Fuel Station'})

    def _create_dispatch(self, **vals):
        return self.env['fleet.dispatch'].create({
            'vehicle_id': self.truck.id,
            'fuel_station_id': self.station.id,
            'dispatch_date': date(2026, 3, 10),
            'diesel_litres': 300.0,
            'fuel_price_per_litre': 800.0,
            'cash_advance': 20000.0,
            'destination': 'Kano',
            **vals,
        })

    def _pay(self, bill, amount, pay_date):
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=bill.ids,
        ).create({'amount': amount, 'payment_date': pay_date})._create_payments()

    def _statement(self, date_from=False, date_to=False):
        wizard = self.env['fleet.dispatch.vendor.statement'].create({
            'partner_id': self.station.id,
            'date_from': date_from,
            'date_to': date_to,
        })
        data = {'form': wizard.read(['date_from', 'date_to', 'journal_ids', 'target_move', 'company_id'])[0]}
        data['form']['used_context'] = wizard._build_contexts(data)
        data['form'].update(partner_id=self.station.id, result_selection='supplier')
        report = self.env['report.fleet_dispatch.report_vendor_statement']
        return report._get_statement(data['form'], self.station)

    def test_confirm_creates_po_and_posted_bill(self):
        dispatch = self._create_dispatch()
        dispatch.action_dispatch()

        order = dispatch.purchase_order_id
        bill = dispatch.vendor_bill_id
        self.assertEqual(dispatch.state, 'dispatched')
        self.assertEqual(order.state, 'purchase')
        self.assertEqual(order.origin, dispatch.name)
        self.assertEqual(order.dispatch_id, dispatch)
        self.assertEqual(len(order.order_line), 2)
        self.assertEqual(bill.state, 'posted')
        self.assertEqual(bill.ref, dispatch.name)
        self.assertEqual(bill.dispatch_id, dispatch)
        self.assertEqual(bill.invoice_date, dispatch.dispatch_date)
        self.assertEqual(bill.date, dispatch.dispatch_date)
        self.assertEqual(bill.dispatch_vehicle_id, self.truck)
        self.assertEqual(bill.dispatch_driver_id, self.driver)
        self.assertAlmostEqual(bill.amount_total, 260000.0)

        payable = bill.line_ids.filtered(lambda l: l.account_id.account_type == 'liability_payable')
        self.assertAlmostEqual(payable.credit, dispatch.total_reimbursable)
        self.assertEqual(payable.partner_id, self.station)
        fuel_line = bill.line_ids.filtered(lambda l: l.account_id == self.fuel_expense)
        advance_line = bill.line_ids.filtered(lambda l: l.account_id == self.trip_expense)
        self.assertAlmostEqual(fuel_line.debit, 240000.0)
        self.assertAlmostEqual(advance_line.debit, 20000.0)

    def test_zero_advance_single_line(self):
        dispatch = self._create_dispatch(cash_advance=0.0)
        dispatch.action_dispatch()
        self.assertEqual(len(dispatch.purchase_order_id.order_line), 1)
        self.assertAlmostEqual(dispatch.vendor_bill_id.amount_total, 240000.0)

    def test_locked_fields_after_confirm(self):
        dispatch = self._create_dispatch()
        dispatch.action_dispatch()
        with self.assertRaises(UserError):
            dispatch.diesel_litres = 10
        dispatch.notes = 'Allowed'

    def test_cancel_unpaid_cancels_documents(self):
        dispatch = self._create_dispatch()
        dispatch.action_dispatch()
        order, bill = dispatch.purchase_order_id, dispatch.vendor_bill_id
        dispatch.action_cancel()
        self.assertEqual(dispatch.state, 'cancelled')
        self.assertEqual(bill.state, 'cancel')
        self.assertEqual(order.state, 'cancel')

        dispatch.action_reset_draft()
        self.assertFalse(dispatch.purchase_order_id)
        dispatch.action_dispatch()
        self.assertNotEqual(dispatch.purchase_order_id, order)

    def test_cancel_paid_bill_blocked(self):
        dispatch = self._create_dispatch()
        dispatch.action_dispatch()
        self._pay(dispatch.vendor_bill_id, 100000.0, date(2026, 3, 15))
        with self.assertRaises(UserError):
            dispatch.action_cancel()

    def test_cancel_in_locked_period_reverses(self):
        dispatch = self._create_dispatch()
        dispatch.action_dispatch()
        bill = dispatch.vendor_bill_id
        self.env.company.fiscalyear_lock_date = date(2026, 3, 31)
        dispatch.action_cancel()
        self.assertEqual(dispatch.state, 'cancelled')
        self.assertEqual(bill.state, 'posted')
        self.assertEqual(bill.payment_state, 'reversed')
        refund = self.env['account.move'].search([('reversed_entry_id', '=', bill.id)])
        self.assertEqual(refund.dispatch_id, dispatch)

    def test_vendor_statement(self):
        before = self._create_dispatch(dispatch_date=date(2026, 2, 20), cash_advance=0.0)
        first = self._create_dispatch()
        second = self._create_dispatch(dispatch_date=date(2026, 3, 20), diesel_litres=100.0)
        (before | first | second).action_dispatch()
        self._pay(first.vendor_bill_id, 100000.0, date(2026, 3, 15))

        st = self._statement(date(2026, 3, 1), date(2026, 3, 31))
        self.assertAlmostEqual(st['opening'], -240000.0)
        self.assertEqual(len(st['lines']), 3)
        bill_lines = [l for l in st['lines'] if l['dispatch']]
        self.assertEqual([l['dispatch'] for l in bill_lines], [first.name, second.name])
        self.assertTrue(all(l['truck'] == 'ABC-123-XY' and l['driver'] == 'John Driver' for l in bill_lines))
        self.assertAlmostEqual(st['total_credit'], 260000.0 + 100000.0)
        self.assertAlmostEqual(st['total_debit'], 100000.0)
        self.assertAlmostEqual(st['closing'], -240000.0 - 360000.0 + 100000.0)
        self.assertAlmostEqual(st['lines'][-1]['balance'], st['closing'])
        self.assertEqual(st['trucks'][0][1]['trips'], 2)
        self.assertAlmostEqual(st['trucks'][0][1]['litres'], 400.0)

    def test_reports_render(self):
        dispatch = self._create_dispatch()
        dispatch.action_dispatch()
        self.env['ir.actions.report']._render_qweb_html(
            'fleet_dispatch.action_report_fleet_dispatch', dispatch.ids)

        wizard = self.env['fleet.dispatch.vendor.statement'].create({'partner_id': self.station.id})
        action = wizard.check_report()
        self.env['ir.actions.report']._render_qweb_html(
            'fleet_dispatch.action_report_vendor_statement', wizard.ids, data=action['data'])
        self.assertIn('domain', wizard.action_view_lines())
