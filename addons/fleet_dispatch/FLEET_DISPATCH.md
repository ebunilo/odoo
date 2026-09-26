# Fleet Dispatch

`fleet_dispatch` extends Odoo 19 Fleet to run a trucking operation. It records each **dispatch** (a truck sent on a trip after filling up at a fuel station) and turns it straight into accounting documents. It also adds **Truck** as a vehicle type.

For every dispatch the module:

- records the truck, driver, trip, diesel dispensed and the cash advance the fuel station gave the driver;
- on confirmation, raises a **purchase order** for the fuel station and a **vendor bill**, so the amount owed to the station is in the ledger straight away;
- prints a **dispatch document** (trip sheet) with signature blocks;
- gives each fuel station an on-demand **vendor statement** with opening balance, bills, payments, running balance, and the truck and driver on every trip.

| | |
| --- | --- |
| Technical name | `fleet_dispatch` |
| Version | 1.1 |
| Category | Human Resources/Fleet |
| Depends on | `fleet`, `purchase`, `accounting_pdf_reports` |
| License | LGPL-3 |

`accounting_pdf_reports` is part of the Odoo Mates accounting suite (`om_account_accountant`) in `addons/`. The vendor statement reuses its partner-report wizard and its `account.move.line._query_get()` helper.

---

## 1. Truck vehicle type

Standard Fleet only has two vehicle types, **Car** and **Bike**. This module adds **Truck** as a third.

- **Where:** `vehicle_type` on the vehicle model (Fleet ▸ Configuration ▸ Models). Each vehicle takes its type from its model.
- **Screens:** trucks show everything Fleet shows for cars:
  - odometer field and Odometer smart button;
  - registration and cancellation dates;
  - seats, doors and trailer hitch;
  - Engine section: fuel type, transmission, power;
  - Make Vehicle Available.

  On the model form, the Model and Engine sections are shown too.
- **Search:** the vehicle search has a **Trucks** filter. The **Available** and **Planned for Change** filters include trucks.
- **Driver changes:** when a truck gets a *future driver*, that driver's current truck is flagged "planned for change", the same way Fleet does for cars. **Accept Driver Change** then moves the driver across. Trucks reuse the car flag, `plan_to_change_car`.
- **Reporting:** the Fleet cost analysis report (`fleet.vehicle.cost.report`) groups trucks under their own type.
- **Uninstalling:** Odoo sets models of type Truck back to **Car**, so no data is lost.

The vehicle form also gets a **Dispatches** smart button that lists that truck's dispatches.

---

## 2. Configuration

**Fleet ▸ Configuration ▸ Settings ▸ Dispatch Accounting** (stored per company):

| Setting | Field | Purpose |
| --- | --- | --- |
| Dispatch Products – Fuel | `dispatch_fuel_product_id` | Product used for the diesel line. Its expense account receives the fuel cost. |
| Dispatch Products – Cash Advance | `dispatch_advance_product_id` | Product used for the cash-advance line. Its expense account receives the advance. |
| Auto-post Dispatch Bills | `dispatch_auto_post_bill` (default on) | Posts the vendor bill as soon as the dispatch is confirmed. When off, the bill stays in draft for an accountant to review. |

**Default data** (created once, `noupdate`):

| Record | Details |
| --- | --- |
| Product **Diesel** (`DISP-DIESEL`) | Service, unit Litre, billed on ordered quantities, no taxes |
| Product **Driver Cash Advance** (`DISP-ADVANCE`) | Service, billed on ordered quantities, no taxes |
| Sequence `fleet.dispatch` | References like `DISP/2026/00001` |

If a company hasn't chosen products in Settings, these defaults are used.

**Before the first dispatch, set:**

1. **Expense accounts** on both products, or on their product category:
   - **Diesel:** a *Fuel Expense* account.
   - **Driver Cash Advance:** a *Trip Expenses* account.
2. **The fuel station** as a vendor contact.
3. **A warehouse for the company.** The Purchase app needs a receipt operation type to create a purchase order. The two products are services, so no receipt is actually generated.

---

## 3. The dispatch record (`fleet.dispatch`)

**Menu:** Fleet ▸ Fleet ▸ **Dispatches**. It opens filtered on *Dispatched* and offers list, kanban, form, graph and pivot views.

| Section | Field | Notes |
| --- | --- | --- |
| Header | `name` Reference | Assigned from the sequence on creation |
| Vehicle & Driver | `vehicle_id` Truck | Required |
| | `truck_plate` Truck No. | The vehicle's plate. Stored, so it can be searched and grouped. |
| | `driver_id` Driver | Defaults to the truck's current driver. Can be changed. |
| | `dispatch_date` | Required, defaults to today. Also used as the bill date. |
| | `company_id` | Required, defaults to the current company |
| Trip | `origin`, `destination` (required), `cargo_description` | |
| | `odometer` + unit | Reading at dispatch, for the trip sheet. It doesn't write to the vehicle's odometer log. |
| Fuelling | `fuel_station_id` | The vendor. Required. |
| | `diesel_litres` | Required, must be > 0 to confirm |
| | `fuel_price_per_litre` | Must be > 0 to confirm |
| | `fuel_cost` | = litres × price (computed) |
| Cash Advance | `cash_advance` | Money the station gave the driver. Required, must be ≥ 0. |
| | `total_reimbursable` | = fuel cost + cash advance. This is what the dispatch owes the station. |
| Accounting | `purchase_order_id`, `vendor_bill_id` | Filled in on confirmation. Shown as smart buttons. |
| | `bill_payment_state` | The bill's payment status. A green **Paid** ribbon shows when it's paid. |
| | `notes` | Free text |

Dispatches have chatter: messages, activities, and change tracking on the key fields.

### Workflow

```text
Draft ──Confirm Dispatch──▶ Dispatched ──Mark as Returned──▶ Returned ──Mark as Done──▶ Done
  ▲                            │                               │
  └──Reset to Draft── Cancelled ◀──────────Cancel──────────────┘
```

| Button | From | What happens |
| --- | --- | --- |
| **Confirm Dispatch** | Draft | Checks litres > 0, price > 0 and advance ≥ 0. Creates the PO and bill (see §4), then sets *Dispatched*. |
| **Mark as Returned** | Dispatched | The truck is back. |
| **Mark as Done** | Returned | Trip closed. A done dispatch can't be cancelled. |
| **Cancel** | Draft, Dispatched, Returned | Cancels or reverses the accounting documents (see §4), then sets *Cancelled*. |
| **Reset to Draft** | Cancelled | Clears the PO and bill links. The next confirmation creates new documents. |
| **Print** | Any state except Draft | Dispatch document PDF (see §5) |
| **Vendor Statement** | Any | Opens the statement wizard for this dispatch's fuel station |

**Editing and deleting**

- **Locked fields:** once a dispatch leaves Draft, these can't change: truck, driver, fuel station, date, litres, price per litre, cash advance and company. The dispatch therefore always matches its posted bill. To correct one, cancel it, reset it to draft, edit it and confirm again.
- **Always editable:** trip details (origin, destination, cargo, odometer) and notes.
- **Deleting:** only Draft or Cancelled dispatches can be deleted.

---

## 4. Accounting

### On confirmation

For each dispatch, in the same transaction:

1. **Purchase order** to the fuel station:
   - **Settings:** vendor reference and source document = the dispatch number, order date = the dispatch date, and a `dispatch_id` link back.
   - **Lines:**

     | Line | Product | Qty × Price | Description |
     |---|---|---|---|
     | Diesel | Fuel product | litres × price/L | `DISP/2026/00012 – Diesel 300 L – Truck BZR 143XC / Driver John Aninwene` |
     | Cash advance | Advance product | 1 × advance | `DISP/2026/00012 – Cash advance to driver – Truck … / Driver …`. Skipped if the advance is 0. |
2. **The PO is confirmed**, and a **vendor bill** is created from it. The bill takes the dispatch date as invoice and accounting date, and the dispatch number as reference. It's linked to the dispatch.
3. **The bill is posted** if *Auto-post Dispatch Bills* is on.
4. A chatter message links the PO and the bill.

This runs as superuser, so a fleet user can confirm dispatches without any purchase or accounting rights.

**Resulting journal entry** (example: 300 L × 800 plus a 20,000 advance):

| Account | Debit | Credit |
| --- | ---: | ---: |
| Fuel Expense (Diesel product) | 240,000 | |
| Trip Expenses (Cash Advance product) | 20,000 | |
| Accounts Payable – fuel station | | 260,000 |

Paying the station with the standard **Register Payment** on the bill books *Dr Payable / Cr Bank*. That appears as a debit on the vendor statement.

### On cancellation

| Bill state | Result |
| --- | --- |
| **Paid or partly paid** | Cancellation is refused. Unreconcile the payment first. |
| **Posted, open period** | Bill reset to draft and cancelled. PO cancelled. |
| **Posted, locked period** (date on or before the user's fiscal lock date, e.g. set by `om_fiscal_year`) | Bill kept and reversed by a credit note dated today, with reference "Reversal of DISP/…". The PO stays confirmed for audit. |
| **Draft** (auto-post off) | Bill cancelled. PO cancelled. |

Each outcome is noted in the chatter.

### Links on accounting records

- **Purchase order:** a **Dispatch** field under *Other Information*.
- **Vendor bill / journal entry:** **Dispatch**, **Truck** and **Driver** in the header. The truck and driver are stored, so bills can be grouped by them.
- **Journal items:** related **Dispatch**, **Truck No.** and **Driver** fields, used by the statement's *View Lines* list.

---

## 5. Printouts

### Dispatch Document (trip sheet)

- **Opened from:** the **Print** button or the Print menu on a dispatch.
- **Layout:** the company's external layout (letterhead). The file is named `Dispatch - DISP-2026-00012.pdf`.
- **Contents:**
  - dispatch number, date and status;
  - PO number and vendor bill number;
  - truck, plate, driver, odometer and company;
  - trip: origin, destination, cargo;
  - fuelling: station, litres, price per litre, fuel cost;
  - cash advance and total reimbursable;
  - notes;
  - signature blocks for **Dispatcher**, **Driver** (with name) and **Fuel Station Attendant**.

### Fuel Vendor Statement

A statement of account for one fuel station, printed landscape on the company letterhead. It's meant to be sent to the vendor or used to reconcile with them.

**Opened from:**

- Fleet ▸ Reporting ▸ **Fuel Vendor Statement**;
- Accounting ▸ Reporting ▸ Partner Reports ▸ **Fuel Vendor Statement**;
- the **Fuel Statement** button on a vendor's contact form (vendors only);
- the **Vendor Statement** button on a dispatch.

The contact form and dispatch buttons fill in the station for you.

**Wizard options:** fuel station (required), company, journals, date from/to, and target moves (posted only or all). It's based on `accounting_pdf_reports`' partner report, so the filters behave like the standard Partner Ledger.

**Contents:**

- **Header:** vendor name and address, period, target moves.
- **Opening balance:** all payable lines for the station dated before *Date from*.
- **One row per payable journal item in the period:** date, entry, dispatch no., truck no., driver, description, debit, credit, running balance. Payments and other entries leave the dispatch columns empty.
- **Totals:** debit, credit, and closing balance.
- **Trips per Truck:** trips, diesel litres, fuel cost, cash advance and total per truck. Each dispatch is counted once, from its original bill.

The balance is *debit − credit*, so **a negative balance is the amount owed to the vendor**.

**View Lines** opens the same journal items as a list, with dispatch, truck and driver columns and debit/credit/balance totals, ready to export to Excel.

---

## 6. Reporting

- **Fleet ▸ Reporting ▸ Dispatch Analysis** (fleet managers): graph and pivot views, grouped by vehicle by default. Measures include litres, fuel cost, cash advance and total reimbursable.
- **Dispatch list totals:** litres, cash advance, fuel cost and total reimbursable. Optional columns: plate, PO, bill and payment status.
- **Search filters:** Draft, Dispatched, Returned, Done; *Unpaid Bills*, *Paid Bills*; *Today*, *This Month*.
- **Group by:** vehicle, driver, fuel station, month, status.

---

## 7. Security

| Group | `fleet.dispatch` | Vendor statement |
| --- | --- | --- |
| Fleet / Officer (`fleet.fleet_group_user`) | read, write, create | full |
| Fleet / Administrator (`fleet.fleet_group_manager`) | read, write, create, delete | – |
| Accounting / Billing (`account.group_account_invoice`) | read | full |

- **Multi-company:** a record rule limits dispatches to the user's allowed companies.
- **Menu visibility:** the Fuel Vendor Statement menus and the contact-form button are for billing users. Dispatch Analysis is for fleet managers.

---

## 8. Technical reference

```text
fleet_dispatch/
├── __manifest__.py
├── data/
│   ├── fleet_dispatch_data.xml        dispatch sequence (noupdate)
│   └── product_data.xml               Diesel and Driver Cash Advance products (noupdate)
├── models/
│   ├── fleet_dispatch.py              fleet.dispatch: fields, workflow, PO/bill creation and cancellation
│   ├── fleet_vehicle.py               dispatch_count, action_view_dispatches, truck driver-change flags
│   ├── fleet_vehicle_model.py         vehicle_type += truck
│   ├── purchase_order.py              purchase.order.dispatch_id
│   ├── account_move.py                account.move dispatch/truck/driver; account.move.line related fields
│   ├── res_company.py                 dispatch products, auto-post flag
│   └── res_config_settings.py         settings fields
├── report/
│   ├── fleet_dispatch_report.xml      report actions (dispatch document, vendor statement)
│   ├── fleet_dispatch_templates.xml   dispatch document QWeb
│   ├── vendor_statement_report.py     report.fleet_dispatch.report_vendor_statement
│   ├── vendor_statement_templates.xml vendor statement QWeb
│   └── fleet_vehicle_cost_report.py   vehicle_type += truck on the Fleet cost report
├── wizard/
│   ├── vendor_statement_wizard.py     fleet.dispatch.vendor.statement (inherits account.common.partner.report)
│   └── vendor_statement_wizard_views.xml  wizard form, action, menus
├── views/
│   ├── fleet_dispatch_views.xml       form, list, kanban, search, pivot, graph, actions, menus
│   ├── fleet_vehicle_views.xml        truck visibility on vehicle/model forms, Trucks filter
│   ├── purchase_account_views.xml     PO/bill links, statement line list, partner and vehicle buttons
│   └── res_config_settings_views.xml  Dispatch Accounting settings block
├── security/
│   ├── ir.model.access.csv
│   └── fleet_dispatch_security.xml    multi-company rule
└── tests/
    ├── test_fleet_dispatch.py         dispatch accounting, cancellation, statement, reports
    └── test_truck_vehicle_type.py     truck type, odometer, driver change, form visibility
```

**Extension points on `fleet.dispatch`:**

- `_prepare_purchase_order_vals()` and `_prepare_po_line_vals()`: change the PO or add lines, such as tolls.
- `_get_dispatch_products()`: choose products per dispatch.
- `_create_vendor_documents()` and `_cancel_vendor_documents()`: the accounting logic.

---

## 9. Install, upgrade and test

The live database is **`dev`**. The local server runs on port 8069 and serves every database, so test runs need a different `--http-port`.

```bash
# Install / upgrade (restart the running server afterwards so it loads the new code)
.venv/bin/python odoo-bin -d dev -u fleet_dispatch --stop-after-init --http-port 8199

# Run the module's tests on the test database
.venv/bin/python odoo-bin -d fleet_dispatch_test -u fleet_dispatch \
    --test-tags /fleet_dispatch --stop-after-init --http-port 8199
```

**What the tests cover:**

- Accounting:
  - PO and posted bill created on confirmation, with correct amounts and references;
  - a zero advance gives a single line;
  - fields are locked after confirmation;
  - cancelling an unpaid dispatch cancels its documents;
  - cancelling a paid dispatch is blocked;
  - cancelling in a locked period creates a reversal.
- Vendor statement: opening, running and closing balances, truck and driver on every line.
- PDFs: both render without errors.
- Truck type:
  - a truck saves with its odometer;
  - the driver-change flow works for trucks;
  - the truck form lets you edit the odometer and seats.

**Manual check:**

1. Create a dispatch (300 L × 800 + 20,000 advance) and confirm it.
2. Open the PO and bill smart buttons. The journal items should be Dr Fuel 240,000, Dr Trip Expenses 20,000, Cr Payable 260,000.
3. Print the dispatch document.
4. Register a partial payment, then run the Fuel Vendor Statement. It should show the bill as a credit, the payment as a debit, the right running balance, and the truck and driver on the trip line.

---

## 10. Loading fleet data

`fleet.xlsx` in the repository root holds the company's 29 trucks from *DRIVER'S TRUCK DETAILS*. Import it through each menu's **⚙ ▸ Import records**, one sheet at a time, in this order:

| Sheet | Import into |
| --- | --- |
| 1 Manufacturers | Fleet ▸ Configuration ▸ Manufacturers |
| 2 Models | Fleet ▸ Configuration ▸ Models (type **Truck**, so this module must be installed first) |
| 3 Tags | Contacts ▸ Configuration ▸ Contact Tags (Driver, Employee) |
| 4 Drivers | Contacts |
| 5 Vehicles | Fleet ▸ Vehicles (status **Registered**) |

Records are matched by name, so no external IDs are needed. **`dev` already contains this data. Don't import it there again, or every record will be duplicated.**
