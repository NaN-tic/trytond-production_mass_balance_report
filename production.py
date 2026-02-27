# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from datetime import datetime
from collections import OrderedDict
from trytond.model import fields, ModelView
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Bool, Eval, If
from trytond.wizard import Wizard, StateView, StateReport, Button
from trytond.transaction import Transaction
from trytond.modules.html_report.dominate_report import DominateReport
from trytond.url import http_host
from trytond.modules.html_report.i18n import _
from dominate.util import raw
from dominate.tags import (a, button, div, h1, i, script, strong, table, tbody,
    td, th, thead, tr)


__all__ = ['Production', 'PrintProductionMassBalanceStart',
    'PrintProductionMassBalance', 'PrintProductionMassBalanceReport']

_ZERO = 0.0


class Production(metaclass=PoolMeta):
    __name__ = 'production'


    def mass_balance_report_data(self, requested_product, direction, lot=None):
        Uom = Pool().get('product.uom')

        digits = self.unit and self.unit.digits or 2
        quantity = 0.0
        total_product = 0.0
        for move in getattr(self, 'outputs'
                if direction == 'backward' else 'inputs'):
            if move.state == 'cancelled':
                continue
            if move.product == requested_product:
                total_product += Uom.compute_qty(move.unit, move.quantity,
                    move.product.default_uom, False)
                # skip moves that same product but different lot
                if lot and lot != move.lot:
                    continue
                quantity += Uom.compute_qty(move.unit, move.quantity,
                    move.product.default_uom, False)

        moves = {}
        for move in getattr(self, 'inputs'
                if direction == 'backward' else 'outputs'):
            if move.state == 'cancelled':
                continue
            product = move.product
            mqty = Uom.compute_qty(
                move.unit, move.quantity, move.product.default_uom, False)
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

            prod = product if direction == 'backward' else requested_product
            balance_consumption = ((((qty * quantity) / total_product)
                    if total_product != 0. else 0)
                if direction == 'backward' else quantity)

            balance_plan_consumption = 0.0
            balance_difference = 0.0
            if self.bom:
                bom = self.bom
                for bm in bom.inputs:
                    if bm.product == prod:
                        bqty = Uom.compute_qty(bm.unit, bm.quantity,
                            bm.product.default_uom, False)
                        factor = bom.compute_factor(self.product, bqty,
                            self.product.default_uom)
                        balance_plan_consumption = (
                            product.default_uom.floor(
                                self.quantity * factor))
                        break

                if direction == 'backward':
                    balance_difference = round(qty - balance_plan_consumption,
                        digits)
                else:
                    balance_difference = round(
                        quantity - balance_plan_consumption, digits)
            item['balance_quantity'] = quantity
            item['balance_consumption'] += balance_consumption
            item['balance_plan_consumption'] += balance_plan_consumption
            item['balance_difference'] += balance_difference
            item['balance_quantity_uom'] = (requested_product.default_uom
                if direction == 'backward' else product.default_uom)
            item['balance_consumption_uom'] = prod.default_uom
            item['balance_plan_consumption_uom'] = prod.default_uom
            item['balance_difference_uom'] = prod.default_uom

            balance_difference_percent = ((
                    (balance_consumption - balance_plan_consumption) /
                    balance_plan_consumption) * 100
                if balance_consumption and balance_plan_consumption else 0.0)
            vals = {
                'id': self.id,
                'name': self.rec_name,
                'product': self.product,
                'uom': self.unit,
                'default_uom': product.default_uom,
                'balance_quantity': quantity,
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
        })
    to_date = fields.Date('To Date',
        domain = [
            If(Bool(Eval('from_date')) & Bool(Eval('to_date')),
                ('from_date', '<=', Eval('to_date')), ())],
        states={
            'required': Bool(Eval('from_date', False)),
        })
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
                    ])

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


class PrintProductionMassBalanceReport(DominateReport):
    __name__ = 'production.mass_balance.report'

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
    def _draw_table(cls, key, productions, parameters):
        render = cls.render
        details_table = table(cls='table collapse multi-collapse', id=key)
        with details_table:
            with thead():
                with tr():
                    th(_('Production'), scope='col')
                    th(_('Quantity'), scope='col')
                    th(_('Consumption'), scope='col')
                    th(_('Plan Consumption'), scope='col')
                    th(_('Difference'), scope='col')
                    th(_('% DIFF'), scope='col')
            with tbody():
                for production in productions:
                    with tr():
                        with td(width='50%'):
                            a(production['name'],
                                href='%s/model/production/%s;name="%s"' % (
                                    parameters['base_url'],
                                    production['id'],
                                    production['name']))
                        td('%s %s' % (
                            render(production['balance_quantity'], digits=4),
                            production['balance_quantity_uom'].symbol),
                            width='10%')
                        td('%s %s' % (
                            render(production['balance_consumption'], digits=4),
                            production['balance_consumption_uom'].symbol),
                            width='10%')
                        td('%s %s' % (
                            render(production['balance_plan_consumption'],
                                digits=4),
                            production['balance_plan_consumption_uom'].symbol),
                            width='10%')
                        td('%s %s' % (
                            render(production['balance_difference'], digits=4),
                            production['balance_difference_uom'].symbol),
                            width='10%')
                        td('%s %%' % render(
                            production['balance_difference_percent']),
                            width='10%')
        return details_table

    @classmethod
    def css(cls, action, data, records):
        return "\n".join([
            "@import url('https://stackpath.bootstrapcdn.com/bootstrap/4.3.1/css/bootstrap.min.css');",
            "@import url('https://use.fontawesome.com/releases/v5.7.0/css/all.css');",
            ])

    @classmethod
    def title(cls, action, data, records):
        return _('Mass Balance')

    @classmethod
    def body(cls, action, data, records):
        parameters = data['parameters']
        render = cls.render
        wrapper = div()
        with wrapper:
            with table(cls='table'):
                with tbody():
                    with tr():
                        with td():
                            h1(_('Mass Balance'))
                        with td(align='right'):
                            company = parameters['company']
                            a(company.rec_name,
                                href=parameters['base_url'],
                                alt=company.rec_name)
                            button(_('Expand All'),
                                type='button',
                                cls='btn tn-outline-light btn-sm',
                                onclick='expand()')
                    with tr():
                        with td(colspan='2'):
                            strong(_('Efficiency Product Type:'))
                            raw(' %s' % (
                                _('Backward')
                                if parameters['direction'] == 'backward'
                                else _('Forward')))
                    with tr():
                        with td():
                            strong(_('Product:'))
                            raw(' %s' % parameters['requested_product'].rec_name)
                        with td():
                            if parameters.get('lot'):
                                strong(_('Lot:'))
                                raw(' %s' % parameters['lot'].number)
                    with tr():
                        with td(colspan='2'):
                            strong(_('Quantity:'))
                            raw(' %s' % _(
                                'quantity produced including all outgoing moves in production'))
                            raw('<br>')
                            strong(_('Consumption:'))
                            raw(' %s' % _(
                                'amount of product consumed per production'))
                            raw('<br>')
                            strong(_('Plan Consumption:'))
                            raw(' %s' % _(
                                "calculated consumption out of production's quantity field (initial production quantity)"))
                    if parameters.get('show_date'):
                        with tr():
                            with td():
                                strong(_('From Date:'))
                                raw(' %s' % render(parameters['from_date']))
                            with td():
                                strong(_('To Date:'))
                                raw(' %s' % render(parameters['to_date']))
                    with tr():
                        with td(colspan='2'):
                            with table(cls='table', id='detail'):
                                with thead():
                                    with tr():
                                        th(_('Product'), scope='col', width='50%')
                                        th(_('Quantity'), scope='col', width='10%')
                                        th(_('Consumption'), scope='col', width='10%')
                                        th(_('Plan Consumption'), scope='col', width='10%')
                                        th(_('Difference'), scope='col', width='10%')
                                        th(_('% DIFF'), scope='col', width='10%')
                                with tbody():
                                    for product, values in data['records'].items():
                                        key = 'product-%s' % product.id
                                        with tr():
                                            with td(width='50%'):
                                                with a(href='#%s' % key,
                                                    cls='',
                                                    **{
                                                        'data-toggle': 'collapse',
                                                        'role': 'button',
                                                        'aria-expanded': 'false',
                                                        'aria-controls': key,
                                                    }):
                                                    i(cls='fas fa-angle-double-right')
                                                    raw(' %s' % product.rec_name)
                                            td('%s %s' % (
                                                render(values['balance_quantity'],
                                                    digits=4),
                                                values['balance_quantity_uom'].symbol),
                                                width='10%')
                                            td('%s %s' % (
                                                render(values['balance_consumption'],
                                                    digits=4),
                                                values['balance_consumption_uom'].symbol),
                                                width='10%')
                                            td('%s %s' % (
                                                render(values['balance_plan_consumption'],
                                                    digits=4),
                                                values['balance_plan_consumption_uom'].symbol),
                                                width='10%')
                                            td('%s %s' % (
                                                render(values['balance_difference'],
                                                    digits=4),
                                                values['balance_difference_uom'].symbol),
                                                width='10%')
                                            plan = values['balance_plan_consumption']
                                            if plan:
                                                percent = ((values['balance_consumption']
                                                    - plan) / plan) * 100
                                            else:
                                                percent = 0.0
                                            td('%s %%' % render(percent, digits=2),
                                                width='10%')
                                        with tr():
                                            with td(colspan='6') as detail_cell:
                                                detail_cell.add(cls._draw_table(
                                                    key,
                                                    values['productions'],
                                                    parameters))
            script(src='https://code.jquery.com/jquery-3.3.1.slim.min.js',
                integrity='sha384-q8i/X+965DzO0rT7abK41JStQIAqVgRVzpbzo5smXKp4YfRvH+8abtTE1Pi6jizo',
                crossorigin='anonymous')
            script(src='https://cdnjs.cloudflare.com/ajax/libs/popper.js/1.14.7/umd/popper.min.js',
                integrity='sha384-UO2eT0CpHqdSJQ6hJty5KVphtPhzWj9WO1clHTMGa3JDZwrnQq4sF86dIHNDz0W1',
                crossorigin='anonymous')
            script(src='https://stackpath.bootstrapcdn.com/bootstrap/4.3.1/js/bootstrap.min.js',
                integrity='sha384-JjSmVgyd0p3pXB1rRibZUAYoIIy6OrQ6VrjIEaFf/nJGzIxFDsf4x0xIM+B07jRM',
                crossorigin='anonymous')
            script(raw("""
function expand() {
  $('.collapse').collapse('show');
}
"""), type='text/javascript', charset='utf-8')
        return wrapper

    @classmethod
    def execute(cls, ids, data):
        records, parameters = cls.prepare(data)
        return super().execute(ids, {
            'name': 'production.mass_balance.report',
            'model': data['model'],
            'records': records,
            'parameters': parameters,
            'output_format': 'html',
            'report_options': {
                'now': datetime.now(),
                }
            })
