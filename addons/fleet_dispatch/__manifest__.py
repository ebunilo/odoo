# -*- coding: utf-8 -*-
{
    'name': 'Fleet Dispatch',
    'version': '1.1',
    'sequence': 186,
    'category': 'Human Resources/Fleet',
    'summary': 'Manage truck dispatches, fuel fill-ups and driver cash advances',
    'description': """
Fleet Dispatch
==============
Extends the Fleet module to record dispatch trips for trucks.

Each dispatch entry captures:
- The vehicle (truck) being dispatched
- The driver
- The fuel station (vendor)
- Litres of diesel dispensed
- Cash advance given to the driver by the fuel vendor
- Status workflow: Draft → Dispatched → Returned → Done

Confirming a dispatch raises a purchase order for the fuel station
(referencing the dispatch number) and posts the matching vendor bill, so
the vendor payable is always in the ledger. Each dispatch can be printed
as a trip sheet, and an on-demand vendor statement lists every trip
(truck number, driver) with debits, credits and running balance.
    """,
    'depends': ['fleet', 'purchase', 'accounting_pdf_reports'],
    'data': [
        'security/fleet_dispatch_security.xml',
        'security/ir.model.access.csv',
        'data/fleet_dispatch_data.xml',
        'data/product_data.xml',
        'report/fleet_dispatch_report.xml',
        'report/fleet_dispatch_templates.xml',
        'report/vendor_statement_templates.xml',
        'wizard/vendor_statement_wizard_views.xml',
        'views/fleet_dispatch_views.xml',
        'views/fleet_vehicle_views.xml',
        'views/purchase_account_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
    'author': 'Custom',
    'license': 'LGPL-3',
}
