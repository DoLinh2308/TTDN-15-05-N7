# Part of Odoo. See LICENSE file for full copyright and licensing details.

import odoo.tests

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@odoo.tests.tagged('post_install_l10n', 'post_install', '-at_install')
class TestUi(AccountTestInvoicingCommon, odoo.tests.HttpCase):

    def test_01_account_tour(self):
        # Reset country and fiscal country, so that fields added by localizations are
        # hidden and non-required, and don't make the tour crash.
        # Also remove default taxes from the company and its accounts, to avoid inconsistencies
        # with empty fiscal country.
        self.env.company.write({
            'country_id': None, # Also resets account_fiscal_country_id
            'account_sale_tax_id': None,
            'account_purchase_tax_id': None,
        })
        account_with_taxes = self.env['account.account'].search([('tax_ids', '!=', False), ('company_id', '=', self.env.company.id)])
        account_with_taxes.write({
            'tax_ids': [Command.clear()],
        })
        self.start_tour("/web", 'account_tour', login="admin")
