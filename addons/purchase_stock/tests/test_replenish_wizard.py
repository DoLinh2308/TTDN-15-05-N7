# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo.addons.stock.tests.common import TestStockCommon


class TestReplenishWizard(TestStockCommon):
    def setUp(self):
        super(TestReplenishWizard, self).setUp()
        self.vendor = self.env['res.partner'].create(dict(name='The Replenisher'))
        self.product1_price = 500

        # Create a supplier info witch the previous vendor
        self.supplierinfo = self.env['product.supplierinfo'].create({
            'name': self.vendor.id,
            'price': self.product1_price,
        })

        # Create a product with the 'buy' route and
        # the 'supplierinfo' prevously created
        self.product1 = self.env['product.product'].create({
            'name': 'product a',
            'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id,
            'seller_ids': [(4, self.supplierinfo.id, 0)],
            'route_ids': [(4, self.env.ref('purchase_stock.route_warehouse0_buy').id, 0)],
        })

        # Additional Values required by the replenish wizard
        self.uom_unit = self.env.ref('uom.product_uom_unit')
        self.wh = self.env['stock.warehouse'].search([('company_id', '=', self.env.user.id)], limit=1)

    def test_replenish_buy_1(self):
        """ Set a quantity to replenish via the "Buy" route and check if
        a purchase order is created with the correct values
        """
        self.product_uom_qty = 42

        replenish_wizard = self.env['product.replenish'].create({
            'product_id': self.product1.id,
            'product_tmpl_id': self.product1.product_tmpl_id.id,
            'product_uom_id': self.uom_unit.id,
            'quantity': self.product_uom_qty,
            'warehouse_id': self.wh.id,
        })
        replenish_wizard.launch_replenishment()
        last_po_id = self.env['purchase.order'].search([
            ('origin', 'ilike', '%Manual Replenishment%'),
            ('partner_id', '=', self.vendor.id)
        ])[-1]
        self.assertTrue(last_po_id, 'Purchase Order not found')
        order_line = last_po_id.order_line.search([('product_id', '=', self.product1.id)])
        self.assertTrue(order_line, 'The product is not in the Purchase Order')
        self.assertEqual(order_line.product_qty, self.product_uom_qty, 'Quantities does not match')
        self.assertEqual(order_line.price_unit, self.product1_price, 'Prices does not match')

    def test_chose_supplier_1(self):
        """ Choose supplier based on the ordered quantity and minimum price

        replenish 10

        1)seq1 vendor1 140 min qty 1
        2)seq2 vendor1 100  min qty 10
        -> 2) should be chosen
        """
        product_to_buy = self.env['product.product'].create({
            'name': "Furniture Service",
            'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id,
            'route_ids': [(4, self.env.ref('purchase_stock.route_warehouse0_buy').id, 0)],
        })
        vendor1 = self.env['res.partner'].create({'name': 'vendor1', 'email': 'from.test@example.com'})

        supplierinfo1 = self.env['product.supplierinfo'].create({
            'product_tmpl_id': product_to_buy.product_tmpl_id.id,
            'name': vendor1.id,
            'min_qty': 1,
            'price': 140,
            'sequence': 1,
        })
        supplierinfo2 = self.env['product.supplierinfo'].create({
            'product_tmpl_id': product_to_buy.product_tmpl_id.id,
            'name': vendor1.id,
            'min_qty': 10,
            'price': 100,
            'sequence': 2,
        })

        replenish_wizard = self.env['product.replenish'].create({
            'product_id': product_to_buy.id,
            'product_tmpl_id': product_to_buy.product_tmpl_id.id,
            'product_uom_id': self.uom_unit.id,
            'quantity': 10,
            'warehouse_id': self.wh.id,
        })
        replenish_wizard.launch_replenishment()
        last_po_id = self.env['purchase.order'].search([
            ('origin', 'ilike', '%Manual Replenishment%'),
        ])[-1]
        self.assertEqual(last_po_id.partner_id, vendor1)
        self.assertEqual(last_po_id.order_line.price_unit, 100)

    def test_chose_supplier_2(self):
        """ Choose supplier based on the ordered quantity and minimum price

        replenish 10

        1)seq1 vendor1 140 min qty 1
        2)seq2 vendor2 90  min qty 10
        3)seq3 vendor1 100 min qty 10
        -> 3) should be chosen
        """
        product_to_buy = self.env['product.product'].create({
            'name': "Furniture Service",
            'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id,
            'route_ids': [(4, self.env.ref('purchase_stock.route_warehouse0_buy').id, 0)],
        })
        vendor1 = self.env['res.partner'].create({'name': 'vendor1', 'email': 'from.test@example.com'})
        vendor2 = self.env['res.partner'].create({'name': 'vendor2', 'email': 'from.test2@example.com'})

        supplierinfo1 = self.env['product.supplierinfo'].create({
            'product_tmpl_id': product_to_buy.product_tmpl_id.id,
            'name': vendor1.id,
            'min_qty': 1,
            'price': 140,
            'sequence': 1,
        })
        supplierinfo2 = self.env['product.supplierinfo'].create({
            'product_tmpl_id': product_to_buy.product_tmpl_id.id,
            'name': vendor2.id,
            'min_qty': 10,
            'price': 90,
            'sequence': 2,
        })
        supplierinfo3 = self.env['product.supplierinfo'].create({
            'product_tmpl_id': product_to_buy.product_tmpl_id.id,
            'name': vendor1.id,
            'min_qty': 10,
            'price': 100,
            'sequence': 3,
        })

        replenish_wizard = self.env['product.replenish'].create({
            'product_id': product_to_buy.id,
            'product_tmpl_id': product_to_buy.product_tmpl_id.id,
            'product_uom_id': self.uom_unit.id,
            'quantity': 10,
            'warehouse_id': self.wh.id,
        })
        replenish_wizard.launch_replenishment()
        last_po_id = self.env['purchase.order'].search([
            ('origin', 'ilike', '%Manual Replenishment%'),
        ])[-1]
        self.assertEqual(last_po_id.partner_id, vendor1)
        self.assertEqual(last_po_id.order_line.price_unit, 100)

    def test_chose_supplier_3(self):
        """ Choose supplier based on the ordered quantity and minimum price

        replenish 10

        1)seq2 vendor1 50
        2)seq1 vendor2 50
        -> 2) should be chosen
        """
        product_to_buy = self.env['product.product'].create({
            'name': "Furniture Service",
            'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id,
            'route_ids': [(4, self.env.ref('purchase_stock.route_warehouse0_buy').id, 0)],
        })
        vendor1 = self.env['res.partner'].create({'name': 'vendor1', 'email': 'from.test@example.com'})
        vendor2 = self.env['res.partner'].create({'name': 'vendor2', 'email': 'from.test2@example.com'})

        supplierinfo1 = self.env['product.supplierinfo'].create({
            'product_tmpl_id': product_to_buy.product_tmpl_id.id,
            'name': vendor1.id,
            'price': 50,
            'sequence': 2,
        })
        supplierinfo2 = self.env['product.supplierinfo'].create({
            'product_tmpl_id': product_to_buy.product_tmpl_id.id,
            'name': vendor2.id,
            'price': 50,
            'sequence': 1,
        })

        replenish_wizard = self.env['product.replenish'].create({
            'product_id': product_to_buy.id,
            'product_tmpl_id': product_to_buy.product_tmpl_id.id,
            'product_uom_id': self.uom_unit.id,
            'quantity': 10,
            'warehouse_id': self.wh.id,
        })
        replenish_wizard.launch_replenishment()
        last_po_id = self.env['purchase.order'].search([
            ('origin', 'ilike', '%Manual Replenishment%'),
        ])[-1]
        self.assertEqual(last_po_id.partner_id, vendor2)

    def test_chose_supplier_4(self):
        """ Choose supplier based on the ordered quantity and minimum price

        replenish 10

        1)seq1 vendor1 100 min qty 2
        2)seq2 vendor1 60 min qty 10
        2)seq3 vendor1 80 min qty 5
        -> 2) should be chosen
        """
        product_to_buy = self.env['product.product'].create({
            'name': "Furniture Service",
            'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id,
            'route_ids': [(4, self.env.ref('purchase_stock.route_warehouse0_buy').id, 0)],
        })
        vendor1 = self.env['res.partner'].create({'name': 'vendor1', 'email': 'from.test@example.com'})
        supplierinfo1 = self.env['product.supplierinfo'].create({
            'name': vendor1.id,
            'price': 100,
            'product_tmpl_id': product_to_buy.product_tmpl_id.id,
            'min_qty': 2
        })
        supplierinfo2 = self.env['product.supplierinfo'].create({
            'name': vendor1.id,
            'price': 60,
            'product_tmpl_id': product_to_buy.product_tmpl_id.id,
            'min_qty': 10
        })
        supplierinfo3 = self.env['product.supplierinfo'].create({
            'name': vendor1.id,
            'price': 80,
            'product_tmpl_id': product_to_buy.product_tmpl_id.id,
            'min_qty': 5
        })
        replenish_wizard = self.env['product.replenish'].create({
            'product_id': product_to_buy.id,
            'product_tmpl_id': product_to_buy.product_tmpl_id.id,
            'product_uom_id': self.uom_unit.id,
            'quantity': 10,
            'warehouse_id': self.wh.id,
        })
        replenish_wizard.launch_replenishment()
        last_po_id = self.env['purchase.order'].search([
            ('origin', 'ilike', '%Manual Replenishment%'),
        ])[-1]

        self.assertEqual(last_po_id.partner_id, vendor1)
        self.assertEqual(last_po_id.order_line.price_unit, 60)

    def test_unit_price_expired_price_list(self):
        vendor = self.env['res.partner'].create({
            'name': 'Contact',
            'type': 'contact',
        })
        product = self.env['product.product'].create({
            'name': 'Product',
            'standard_price': 60,
            'seller_ids': [(0, 0, {
                'name': vendor.id,
                'price': 1.0,
                'date_end': '2019-01-01',
            })]
        })

        replenish_wizard = self.env['product.replenish'].create({
            'product_id': product.id,
            'product_tmpl_id': product.product_tmpl_id.id,
            'product_uom_id': self.uom_unit.id,
            'quantity': 1,
            'warehouse_id': self.wh.id,
        })
        replenish_wizard.launch_replenishment()
        last_po_id = self.env['purchase.order'].search([
            ('origin', 'ilike', '%Manual Replenishment%'),
        ])[-1]

        self.assertEqual(last_po_id.partner_id, vendor)
        self.assertEqual(last_po_id.order_line.price_unit, 60)
