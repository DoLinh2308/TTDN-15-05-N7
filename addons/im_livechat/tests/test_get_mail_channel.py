# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.addons.im_livechat.tests.common import TestImLivechatCommon


class TestGetMailChannel(TestImLivechatCommon):
    def test_get_mail_channel(self):
        """For a livechat with 5 available operators, we open 5 channels 5 times (25 channels total).
        For every 5 channels opening, we check that all operators were assigned.
        """

        for i in range(5):
            mail_channels = self._open_livechat_mail_channel()
            channel_operators = [channel_info['operator_pid'] for channel_info in mail_channels]
            channel_operator_ids = [channel_operator[0] for channel_operator in channel_operators]
            self.assertTrue(all(partner_id in channel_operator_ids for partner_id in self.operators.mapped('partner_id').ids))

    def test_channel_get_livechat_visitor_info(self):
        belgium = self.env.ref('base.be')
        public_user = self.env.ref('base.public_user')
        test_user = self.env['res.users'].create({'name': 'Roger', 'login': 'roger', 'country_id': belgium.id})

        # ensure visitor info are correct with anonymous
        operator = self.operators[0]
        channel_info = self.livechat_channel.with_user(public_user)._open_livechat_mail_channel(anonymous_name='Visitor 22', previous_operator_id=operator.partner_id.id, country_id=belgium.id)
        visitor_info = channel_info['livechat_visitor']
        self.assertFalse(visitor_info['id'])
        self.assertEqual(visitor_info['name'], "Visitor 22")
        self.assertEqual(visitor_info['country'], (20, "Belgium"))

        # ensure member info are hidden (in particular email and real name when livechat username is present)
        self.assertEqual(sorted(channel_info['members'], key=lambda m: m['id']), sorted([{
            'active': True,
            'email': False,
            'id': operator.partner_id.id,
            'im_status': False,
            'livechat_username': 'Michel Operator',
            'name': 'Michel Operator',
        }, {
            'active': False,
            'email': False,
            'id': public_user.partner_id.id,
            'im_status': False,
            'livechat_username': False,
            'name': 'Public user',
        }], key=lambda m: m['id']))

        # ensure visitor info are correct with real user
        channel_info = self.livechat_channel.with_user(test_user)._open_livechat_mail_channel(anonymous_name='whatever', user_id=test_user.id)
        visitor_info = channel_info['livechat_visitor']
        self.assertEqual(visitor_info['id'], test_user.partner_id.id)
        self.assertEqual(visitor_info['name'], "Roger")
        self.assertEqual(visitor_info['country'], (20, "Belgium"))

        # ensure visitor info are correct when operator is testing himself
        operator = self.operators[0]
        channel_info = self.livechat_channel.with_user(operator)._open_livechat_mail_channel(anonymous_name='whatever', previous_operator_id=operator.partner_id.id, user_id=operator.id)
        self.assertEqual(channel_info['operator_pid'], (operator.partner_id.id, "Michel Operator"))
        visitor_info = channel_info['livechat_visitor']
        self.assertEqual(visitor_info['id'], operator.partner_id.id)
        self.assertEqual(visitor_info['name'], "Michel")
        self.assertFalse(visitor_info['country'])

    def _open_livechat_mail_channel(self):
        mail_channels = []

        for i in range(5):
            mail_channel = self.livechat_channel._open_livechat_mail_channel('Anonymous')
            mail_channels.append(mail_channel)
            # send a message to mark this channel as 'active'
            self.env['mail.channel'].browse(mail_channel['id']).message_post(body='cc')

        return mail_channels

    def test_channel_not_pinned_for_operator_before_first_message(self):
        public_user = self.env.ref('base.public_user')
        channel_info = self.livechat_channel.with_user(public_user)._open_livechat_mail_channel(anonymous_name='whatever')
        operator_channel_partner = self.env['mail.channel.partner'].search([('channel_id', '=', channel_info['id']), ('partner_id', 'in', self.operators.partner_id.ids)])
        self.assertEqual(len(operator_channel_partner), 1, "operator should be member of channel")
        self.assertFalse(operator_channel_partner.is_pinned, "channel should not be pinned for operator initially")
        self.env['mail.channel'].browse(channel_info['id']).message_post(body='cc')
        self.assertTrue(operator_channel_partner.is_pinned, "channel should be pinned for operator after visitor sent a message")
        self.assertIn(channel_info['id'], operator_channel_partner.partner_id._get_channels_as_member().ids, "channel should be fetched by operator on new page")

    def test_operator_livechat_username(self):
        """Ensures the operator livechat_username is returned by `_channel_fetch_message`, which is
        the method called by the public route displaying chat history."""
        public_user = self.env.ref('base.public_user')
        operator = self.operators[0]
        operator.write({
            'email': 'michel@example.com',
            'livechat_username': 'Michel at your service',
        })
        channel_info = self.livechat_channel.with_user(public_user)._open_livechat_mail_channel(anonymous_name='whatever')
        channel = self.env['mail.channel'].browse(channel_info['id'])
        channel.with_user(operator).message_post(body='Hello', message_type='comment', subtype_xmlid='mail.mt_comment')
        message_formats = channel.with_user(public_user)._channel_fetch_message()
        self.assertEqual(len(message_formats), 1)
        self.assertEqual(message_formats[0]['author_id'][0], operator.partner_id.id)
        self.assertEqual(message_formats[0]['author_id'][1], operator.livechat_username)
        self.assertEqual(message_formats[0]['author_id'][2], operator.livechat_username)
        self.assertFalse(message_formats[0].get('email_from'), "should not send email_from to livechat user")
