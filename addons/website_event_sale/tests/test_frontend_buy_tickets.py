# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import odoo.tests

from datetime import timedelta

from odoo.addons.base.tests.common import HttpCaseWithUserDemo
from odoo.addons.website_event_sale.tests.common import TestWebsiteEventSaleCommon
from odoo.fields import Datetime


@odoo.tests.common.tagged('post_install', '-at_install')
class TestUi(HttpCaseWithUserDemo, TestWebsiteEventSaleCommon):

    def setUp(self):
        super().setUp()
        self.event_2 = self.env['event.event'].create({
            'name': 'Conference for Architects TEST',
            'user_id': self.env.ref('base.user_admin').id,
            'date_begin': (Datetime.today() + timedelta(days=5)).strftime('%Y-%m-%d 07:00:00'),
            'date_end': (Datetime.today() + timedelta(days=5)).strftime('%Y-%m-%d 16:30:00'),
            'website_published': True,
        })

        self.env['event.event.ticket'].create([{
            'name': 'Standard',
            'event_id': self.event_2.id,
            'product_id': self.env.ref('event_sale.product_product_event').id,
            'start_sale_datetime': (Datetime.today() - timedelta(days=5)).strftime('%Y-%m-%d 07:00:00'),
            'end_sale_datetime': (Datetime.today() + timedelta(90)).strftime('%Y-%m-%d'),
            'price': 1000.0,
        }, {
            'name': 'VIP',
            'event_id': self.event_2.id,
            'product_id': self.env.ref('event_sale.product_product_event').id,
            'end_sale_datetime': (Datetime.today() + timedelta(90)).strftime('%Y-%m-%d'),
            'price': 1500.0,
        }])

        self.event_3 = self.env['event.event'].create({
            'name': 'Last ticket test',
            'user_id': self.env.ref('base.user_admin').id,
            'date_begin': (Datetime.today() + timedelta(days=5)).strftime('%Y-%m-%d 07:00:00'),
            'date_end': (Datetime.today() + timedelta(days=5)).strftime('%Y-%m-%d 16:30:00'),
            'website_published': True,
        })

        self.env['event.event.ticket'].create([{
            'name': 'VIP',
            'event_id': self.event_3.id,
            'product_id': self.env.ref('event_sale.product_product_event').id,
            'end_sale_datetime': (Datetime.today() + timedelta(90)).strftime('%Y-%m-%d'),
            'price': 1500.0,
            'seats_max': 2,
        }])


        # flush event to ensure having tickets available in the tests
        self.event_2.flush()
        self.event_3.flush()

        (self.env.ref('base.partner_admin') + self.partner_demo).write({
            'street': '215 Vine St',
            'city': 'Scranton',
            'zip': '18503',
            'country_id': self.env.ref('base.us').id,
            'state_id': self.env.ref('base.state_us_39').id,
            'phone': '+1 555-555-5555',
            'email': 'admin@yourcompany.example.com',
        })

        self.env['account.journal'].create({'name': 'Cash - Test', 'type': 'cash', 'code': 'CASH - Test'})

    def test_admin(self):
        # Seen that:
        # - this test relies on demo data that are entirely in USD (pricelists)
        # - that main demo company is gelocated in US
        # - that this test awaits for hardcoded USDs amount
        # we have to force company currency as USDs only for this test
        self.cr.execute("UPDATE res_company SET currency_id = %s WHERE id = %s", [self.env.ref('base.USD').id, self.env.ref('base.main_company').id])

        self.start_tour("/", 'event_buy_tickets', login="admin")

    def test_demo(self):
        self.start_tour("/", 'event_buy_tickets', login="demo")

    def test_buy_last_ticket(self):
        self.start_tour("/", 'event_buy_last_ticket')

    def test_pricelists_different_currencies(self):
        self.start_tour("/", 'event_sale_pricelists_different_currencies')
    # TO DO - add public test with new address when convert to web.tour format.
