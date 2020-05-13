# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from . import production


def register():
    Pool.register(
        production.Production,
        production.PrintProductionMassBalanceStart,
        module='production_mass_balance_report', type_='model')
    Pool.register(
        production.PrintProductionMassBalance,
        module='production_mass_balance_report', type_='wizard')
    Pool.register(
        production.PrintProductionMassBalanceSReport,
        module='production_mass_balance_report', type_='report')
