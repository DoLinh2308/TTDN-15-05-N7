# coding: utf-8
# Copyright 2016 Vauxoo (https://www.vauxoo.com) <info@vauxoo.com>
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import re
from odoo import models, api, fields, _


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    def _prepare_liquidity_account_vals(self, company, code, vals):
        # OVERRIDE
        account_vals = super()._prepare_liquidity_account_vals(company, code, vals)

        if company.account_fiscal_country_id.code == 'MX':
            # When preparing the values to use when creating the default debit and credit accounts of a
            # liquidity journal, set the correct tags for the mexican localization.
            account_vals.setdefault('tag_ids', [])
            account_vals['tag_ids'] += [(4, tag_id) for tag_id in self.env['account.account'].mx_search_tags(code).ids]

        return account_vals


class AccountAccount(models.Model):
    _inherit = 'account.account'

    @api.model
    def mx_search_tags(self, code):
        account_tag = self.env['account.account.tag']
        #search if the code is compliant with the regexp we have for tags auto-assignation
        re_res = re.search(
            '^(?P<first>[1-8][0-9][0-9])[,.]'
            '(?P<second>[0-9][0-9])[,.]'
            '(?P<third>[0-9]{2,3})$', code)
        if not re_res:
            return account_tag

        #get the elements of that code divided with separation declared in the regexp
        account = re_res.groups()
        return account_tag.search([
            ('name', '=like', "%s.%s%%" % (account[0], account[1])),
            ('color', '=', 4)], limit=1)

    @api.onchange('code')
    def _onchange_code(self):
        if self.company_id.country_id.code == "MX" and self.code:
            tags = self.mx_search_tags(self.code)
            self.tag_ids = tags


class AccountAccountTag(models.Model):
    _inherit = 'account.account.tag'

    nature = fields.Selection([
        ('D', 'Debitable Account'), ('A', 'Creditable Account')],
        help='Used in Mexican report of electronic accounting (account nature).')
