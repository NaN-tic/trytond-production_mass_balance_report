# This file is part production_mass_balance_report module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
import unittest
from trytond.tests.test_tryton import ModuleTestCase
from trytond.tests.test_tryton import suite as test_suite


class ProductionMassBalanceReportTestCase(ModuleTestCase):
    'Test Production Mass Balance Report module'
    module = 'production_mass_balance_report'


def suite():
    suite = test_suite()
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
            ProductionMassBalanceReportTestCase))
    return suite
