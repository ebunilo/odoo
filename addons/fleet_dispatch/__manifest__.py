# -*- coding: utf-8 -*-
{
    'name': 'Fleet Dispatch',
    'version': '1.0',
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

This gives the company a clear record of every fuelling stop so that
the fuel vendor can be reimbursed accurately.
    """,
    'depends': ['fleet'],
    'data': [
        'security/ir.model.access.csv',
        'views/fleet_dispatch_views.xml',
    ],
    'installable': True,
    'application': False,
    'author': 'Custom',
    'license': 'LGPL-3',
}
