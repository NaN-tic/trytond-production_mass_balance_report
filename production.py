# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import os
from datetime import datetime
from collections import OrderedDict
from trytond.model import fields, ModelView
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Bool, Eval, If
from trytond.wizard import Wizard, StateView, StateReport, Button
from trytond.transaction import Transaction
from trytond.modules.html_report.html_report import HTMLReport
from trytond.url import http_host


__all__ = ['Production', 'PrintProductionMassBalanceStart',
    'PrintProductionMassBalance', 'PrintProductionMassBalanceReport']

_ZERO = 0.0


class Production(metaclass=PoolMeta):
    __name__ = 'production'

    def mass_balance_report_data(self, requested_product, direction, lot=None):
        Uom = Pool().get('product.uom')

        digits = self.on_change_with_unit_digits()
        quantity = 0.0
        for move in getattr(self, 'outputs' if direction == 'backward' else 'inputs'):
            if move.state == 'cancelled':
                continue
            if move.product == requested_product:
                # skip moves that same product but different lot
                if lot and lot != move.lot:
                    continue
                quantity += Uom.compute_qty(move.uom, move.quantity, move.product.default_uom, False)

        moves = {}
        for move in getattr(self, 'inputs' if direction == 'backward' else 'outputs'):
            if move.state == 'cancelled':
                continue
            product = move.product
            mqty = Uom.compute_qty(
                move.uom, move.quantity, move.product.default_uom, False)
            if moves.get(product):
                moves[product] += mqty
            else:
                moves[product] = mqty

        res = {}
        for product, qty in moves.items():
            item = res.setdefault(product, {})
            item.setdefault('balance_quantity', 0.0)
            item.setdefault('balance_consumption', 0.0)
            item.setdefault('balance_plan_consumption', 0.0)
            item.setdefault('balance_difference', 0.0)
            item.setdefault('productions', [])

            if direction == 'backward':
                balance_quantity = quantity
                balance_consumption = qty
                balance_plan_consumption = balance_difference = balance_difference_percent = 0.0
                if self.bom:
                    bom = self.bom
                    for bm in bom.inputs:
                        if bm.product == product:
                            default_uom = self.product.default_uom
                            bqty = Uom.compute_qty(
                                bm.uom, bm.quantity, bm.product.default_uom, False)
                            factor = bom.compute_factor(self.product, bqty, default_uom)
                            balance_plan_consumption = default_uom.ceil(self.quantity * factor)
                            break

                    balance_difference = round(qty - balance_plan_consumption, digits)
                    if balance_consumption and balance_plan_consumption:
                        balance_difference_percent = ((balance_consumption - balance_plan_consumption) / balance_plan_consumption) * 100
                item['balance_quantity'] = balance_quantity
                item['balance_consumption'] += balance_consumption
                item['balance_plan_consumption'] += balance_plan_consumption
                item['balance_difference'] += balance_difference
                item['balance_quantity_uom'] = requested_product.default_uom
                item['balance_consumption_uom'] = product.default_uom
                item['balance_plan_consumption_uom'] = product.default_uom
                item['balance_difference_uom'] = product.default_uom
            else:
                balance_quantity = qty
                balance_consumption = quantity
                balance_plan_consumption = balance_difference = balance_difference_percent = 0.0
                if self.bom:
                    bom = self.bom
                    for bm in bom.inputs:
                        if bm.product == requested_product:
                            default_uom = self.product.default_uom
                            bqty = Uom.compute_qty(
                                bm.uom, bm.quantity, bm.product.default_uom, False)
                            factor = bom.compute_factor(self.product, bqty, default_uom)
                            balance_plan_consumption = default_uom.ceil(self.quantity * factor)
                            break

                    balance_difference = round(quantity - balance_plan_consumption, digits)
                    if balance_consumption and balance_plan_consumption:
                        balance_difference_percent = ((balance_consumption - balance_plan_consumption) / balance_plan_consumption) * 100
                item['balance_quantity'] = balance_quantity
                item['balance_consumption'] += balance_consumption
                item['balance_plan_consumption'] += balance_plan_consumption
                item['balance_difference'] += balance_difference
                item['balance_quantity_uom'] = product.default_uom
                item['balance_consumption_uom'] = requested_product.default_uom
                item['balance_plan_consumption_uom'] = requested_product.default_uom
                item['balance_difference_uom'] = requested_product.default_uom

            vals = {
                'id': self.id,
                'name': self.rec_name,
                'product': self.product,
                'uom': self.uom,
                'default_uom': product.default_uom,
                'balance_quantity': balance_quantity,
                'balance_consumption': balance_consumption,
                'balance_plan_consumption': balance_plan_consumption,
                'balance_difference': balance_difference,
                'balance_difference_percent': balance_difference_percent,
                'balance_quantity_uom': item['balance_quantity_uom'],
                'balance_consumption_uom': item['balance_consumption_uom'],
                'balance_plan_consumption_uom': item['balance_plan_consumption_uom'],
                'balance_difference_uom': item['balance_difference_uom'],
                }
            item['productions'].append(vals)

        return res


class PrintProductionMassBalanceStart(ModelView):
    'Print Production Mass Balance Start'
    __name__ = 'production.mass_balance.start'
    product = fields.Many2One('product.product', 'Product', required=True)
    from_date = fields.Date('From Date',
        domain = [
            If(Bool(Eval('from_date')) & Bool(Eval('to_date')),
                ('from_date', '<=', Eval('to_date')), ())],
        states={
            'required': Bool(Eval('to_date', False)),
        }, depends=['to_date'])
    to_date = fields.Date('To Date',
        domain = [
            If(Bool(Eval('from_date')) & Bool(Eval('to_date')),
                ('from_date', '<=', Eval('to_date')), ())],
        states={
            'required': Bool(Eval('from_date', False)),
        }, depends=['from_date'])
    direction = fields.Selection([
        ('backward', 'Backward'),
        ('forward', 'Forward'),
        ], 'Direction', required=True)

    @classmethod
    def __setup__(cls):
        super(PrintProductionMassBalanceStart, cls).__setup__()
        try:
            Lot = Pool().get('stock.lot')
        except:
            Lot = None
        if Lot:
            cls.lot = fields.Many2One('stock.lot', 'Lot',
                domain=[
                    ('product', '=', Eval('product')),
                    ],
                depends=['product'])

    @staticmethod
    def default_direction():
        return 'backward'


class PrintProductionMassBalance(Wizard):
    'Print Production Mass Balance'
    __name__ = 'production.print_mass_balance'
    start = StateView('production.mass_balance.start',
        'production_mass_balance_report.print_production_mass_balance_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Print', 'print_', 'tryton-print', default=True),
            ])
    print_ = StateReport('production.mass_balance.report')

    def default_start(self, fields):
        context = Transaction().context

        res = {}
        if context.get('active_model'):
            Model = Pool().get(context['active_model'])
            id = Transaction().context['active_id']
            if Model.__name__ == 'product.template':
                template = Model(id)
                if template.products:
                    res['product'] = template.products[0].id
            elif Model.__name__ == 'product.product':
                res['product'] = id
            elif Model.__name__ == 'stock.lot':
                lot = Model(id)
                res['lot'] = lot.id
                res['product'] = lot.product.id
        return res

    def do_print_(self, action):
        context = Transaction().context
        data = {
            'direction': self.start.direction,
            'from_date': self.start.from_date,
            'to_date': self.start.to_date,
            'product': self.start.product.id,
            'model': context.get('active_model'),
            'ids': context.get('active_ids') or [],
            }
        try:
            Lot = Pool().get('stock.lot')
        except:
            Lot = None
        if Lot:
            data['lot'] = self.start.lot.id if self.start.lot else None
        return action, data


class PrintProductionMassBalanceReport(HTMLReport):
    __name__ = 'production.mass_balance.report'

    @classmethod
    def get_context(cls, records, data):
        pool = Pool()
        Company = pool.get('company.company')
        t_context = Transaction().context

        context = super().get_context(records, data)
        context['company'] = Company(t_context['company'])
        return context

    @classmethod
    def prepare(cls, data):
        pool = Pool()
        Product = pool.get('product.product')
        Company = pool.get('company.company')
        Production = pool.get('production')

        try:
            Lot = pool.get('stock.lot')
        except:
            Lot = None

        t_context = Transaction().context
        company_id = t_context.get('company')
        from_date = data.get('from_date') or datetime.min.date()
        to_date = data.get('to_date') or datetime.max.date()

        requested_product = Product(data['product'])
        direction = data['direction']
        lot = Lot(data['lot']) if data.get('lot') else None

        parameters = {}
        parameters['direction'] = direction
        parameters['from_date'] = from_date
        parameters['to_date'] = to_date
        parameters['show_date'] = bool(data.get('from_date'))
        parameters['requested_product'] = requested_product
        parameters['lot'] = Lot(data['lot']) if data.get('lot') else None
        parameters['base_url'] = '%s/#%s' % (http_host(),
            Transaction().database.name)
        parameters['company'] = Company(company_id)

        records = OrderedDict()

        if direction == 'backward':
            domain = [
                    ('outputs.product', '=', requested_product),
                    ('outputs.effective_date', '>=', from_date),
                    ('outputs.effective_date', '<=', to_date),
                    ('outputs.state', '=', 'done'),
                    ('company', '=', company_id),
                    ]
            if lot:
                domain += [('outputs.lot', '=', lot)]
        else:
            domain = [
                    ('inputs.product', '=', requested_product),
                    ('inputs.effective_date', '>=', from_date),
                    ('inputs.effective_date', '<=', to_date),
                    ('inputs.state', '=', 'done'),
                    ('company', '=', company_id),
                    ]
            if lot:
                domain += [('inputs.lot', '=', lot)]

        productions = Production.search(domain)

        records = {}
        for production in productions:
            res = production.mass_balance_report_data(requested_product,
                    direction, lot)

            for key, values in res.items():
                if not records.get(key):
                    records.setdefault(key, {})
                for k, v in values.items():
                    if k.endswith('_uom'):
                        records[key][k] = v
                    elif k in records[key]:
                        records[key][k] += v
                    else:
                        records[key][k] = v
        return records, parameters

    @classmethod
    def execute(cls, ids, data):
        context = Transaction().context
        context['report_lang'] = Transaction().language
        context['report_translations'] = os.path.join(
            os.path.dirname(__file__), 'report', 'translations')

        with Transaction().set_context(**context):
            records, parameters = cls.prepare(data)
            return super(PrintProductionMassBalanceReport, cls).execute(ids, {
                    'name': 'production.mass_balance.report',
                    'model': data['model'],
                    'records': records,
                    'parameters': parameters,
                    'output_format': 'html',
                    'report_options': {
                        'now': datetime.now(),
                        }
                    })
