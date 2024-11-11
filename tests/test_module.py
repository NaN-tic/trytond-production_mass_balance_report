
# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
import datetime
from decimal import Decimal
from dateutil.relativedelta import relativedelta
from trytond.pool import Pool
from trytond.transaction import Transaction
from trytond.modules.company.tests import CompanyTestMixin
from trytond.tests.test_tryton import ModuleTestCase, with_transaction
from trytond.modules.company.tests import create_company, set_company


class ProductionMassBalanceReportTestCase(CompanyTestMixin, ModuleTestCase):
    'Test ProductionMassBalanceReport module'
    module = 'production_mass_balance_report'
    extras = ['stock_lot']

    @with_transaction()
    def test_production_balance_report(self):
        'Test Production Balance REport'

        pool = Pool()

        today = datetime.date.today()
        yesterday = today - relativedelta(days=1)
        before_yesterday = yesterday - relativedelta(days=1)
        pool = Pool()

        # Create company
        company = create_company()
        with set_company(company):

            # Create product
            ProductUom = pool.get('product.uom')
            unit, = ProductUom.search([('name', '=', 'Unit')])
            ProductTemplate = pool.get('product.template')
            Product = pool.get('product.product')
            template = ProductTemplate()
            template.name = 'product'
            template.default_uom = unit
            template.type = 'goods'
            template.producible = True
            template.list_price = Decimal(30)
            template.save()
            product = Product(template=template)
            product.cost_price = Decimal(20)
            product.save()

            # Create Components
            template1 = ProductTemplate()
            template1.name = 'component 1'
            template1.default_uom = unit
            template1.type = 'goods'
            template1.list_price = Decimal(5)
            template1.save()
            component1 = Product(template=template1)
            component1.cost_price = Decimal(1)
            component1.save()
            meter, = ProductUom.search([('name', '=', 'Meter')])
            centimeter, = ProductUom.search([('name', '=', 'Centimeter')])
            template2 = ProductTemplate()
            template2.name = 'component 2'
            template2.default_uom = meter
            template2.type = 'goods'
            template2.list_price = Decimal(7)
            template2.save()
            component2 = Product(template=template2)
            component2.cost_price = Decimal(5)
            component2.save()

            # Create Bill of Material
            BOM = pool.get('production.bom')
            BOMInput = pool.get('production.bom.input')
            BOMOutput = pool.get('production.bom.output')
            bom = BOM(name='product')
            bom.save()
            input1 = BOMInput(bom=bom)
            input1.product = component1
            input1.on_change_product()
            input1.quantity = 5
            input1.save()
            input2 = BOMInput(bom=bom)
            input2.product = component2
            input2.on_change_product()
            input2.quantity = 150
            input2.unit = centimeter
            input2.save()
            output = BOMOutput(bom=bom)
            output.product = product
            output.on_change_product()
            output.quantity = 1
            output.save()
            # bom.reload()

            ProductBom = pool.get('product.product-production.bom')
            product_bom = ProductBom(bom=bom, product=product)
            product_bom.save()
            # product.reload()
            self.assertEqual(len(product.boms), 1)

            ProductionLeadTime = pool.get('production.lead_time')
            production_lead_time = ProductionLeadTime()
            production_lead_time.product = product
            production_lead_time.bom = bom
            production_lead_time.lead_time = datetime.timedelta(1)
            production_lead_time.save()

            # Create an Inventory
            Inventory = pool.get('stock.inventory')
            InventoryLine = pool.get('stock.inventory.line')
            Location = pool.get('stock.location')
            storage, = Location.search([
                ('code', '=', 'STO'),
            ])
            inventory = Inventory()
            inventory.location = storage
            inventory.save()
            inventory_line1 = InventoryLine(inventory=inventory)
            inventory_line1.product = component1
            inventory_line1.quantity = 20
            inventory_line1.save()
            inventory_line2 = InventoryLine(inventory=inventory)
            inventory_line2.product = component2
            inventory_line2.quantity = 6
            inventory_line2.save()
            # inventory.reload()
            Inventory.confirm([inventory])
            self.assertEqual(inventory.state, 'done')

            # Make a production
            Production = pool.get('production')
            production = Production()
            production.planned_date = today
            production.product = product
            production.on_change_product()
            production.bom = bom
            production.quantity = 2
            production.on_change_quantity()
            production.planned_start_date = yesterday
            production.save()

            # self.assertEqual(production.planned_start_date, yesterday)
            self.assertEqual(
                sorted([i.quantity for i in production.inputs]) == [10, 300], True)
            output, = production.outputs
            self.assertEqual(output.quantity, 2)
            self.assertEqual(production.cost, Decimal('25.0000'))
            Production.wait([production])
            self.assertEqual(production.state, 'waiting')
            # Do the production
            Production.assign_try([production])
            self.assertEqual(all(i.state == 'assigned' for i in production.inputs),
                             True)
            Production.run([production])
            self.assertEqual(all(i.state == 'done' for i in production.inputs),
                             True)
            self.assertEqual(
                len(set(i.effective_date == today for i in production.inputs)), 1)
            Production.do([production])
            output, = production.outputs
            self.assertEqual(output.state, 'done')
            self.assertEqual(output.effective_date, production.effective_date)
            self.assertEqual(output.unit_price, Decimal('12.5000'))

            res = production.mass_balance_report_data(product, direction='backward', lot=None)
            for key, value in {component1: [2.0, 10.0, 10.0, 0.0], component2: [2.0, 3.0, 3.0, 0.0]}.items():
                self.assertEqual(res[key]['balance_quantity'], value[0])
                self.assertEqual(res[key]['balance_consumption'], value[1])
                self.assertEqual(res[key]['balance_plan_consumption'], value[2])
                self.assertEqual(res[key]['balance_difference'], value[3])

            # Make a production with effective date yesterday and running the day before
            Production = pool.get('production')
            production = Production()
            production.effective_date = yesterday
            production.effective_start_date = before_yesterday
            production.product = product
            production.on_change_product()
            production.bom = bom
            production.quantity = 2
            production.on_change_quantity()
            production.save()
            Production.wait([production])
            Production.assign_try([production])
            Production.run([production])
            self.assertEqual(
                all(i.effective_date == before_yesterday
                    for i in production.inputs), True)
            Production.do([production])

            res = production.mass_balance_report_data(component1, direction='forward', lot=None)
            self.assertEqual(res[product]['balance_quantity'], 10.0)
            self.assertEqual(res[product]['balance_consumption'], 10.0)
            self.assertEqual(res[product]['balance_plan_consumption'], 10.0)
            self.assertEqual(res[product]['balance_difference'], 0.0)

            PrintProductionMassBalanceReport = Pool().get('production.mass_balance.report', type='report')
            ProductionMassBalanceReport = Pool().get('production.print_mass_balance', type='wizard')
            # with Transaction().set_context(active_model='product.product', active_id=product.id):
            with Transaction().set_context(active_model='product.product'):
                session_id, _, _ = ProductionMassBalanceReport.create()
                print_general_ledger = ProductionMassBalanceReport(session_id)
                print_general_ledger.start.product = product
                print_general_ledger.start.direction = 'backward'
                print_general_ledger.start.from_date = None
                print_general_ledger.start.to_date = None
                print_general_ledger.start.lot = None
                _, data = print_general_ledger.do_print_(None)
                oext, content, _, _ = PrintProductionMassBalanceReport.execute(ids=[product.id], data=data)
                self.assertEqual(oext, 'html')

del ModuleTestCase
