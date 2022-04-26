
# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.

from trytond.modules.company.tests import CompanyTestMixin
from trytond.tests.test_tryton import ModuleTestCase


class ProductionMassBalanceReportTestCase(CompanyTestMixin, ModuleTestCase):
    'Test ProductionMassBalanceReport module'
    module = 'production_mass_balance_report'


del ModuleTestCase
