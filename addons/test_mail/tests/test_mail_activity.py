# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
from freezegun import freeze_time
from unittest.mock import patch
from unittest.mock import DEFAULT

import pytz

from odoo import fields, exceptions, tests
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.test_mail.tests.common import TestMailCommon
from odoo.addons.test_mail.models.test_mail_models import MailTestActivity
from odoo.tools import mute_logger
from odoo.tests.common import Form, users


class TestActivityCommon(TestMailCommon):

    @classmethod
    def setUpClass(cls):
        super(TestActivityCommon, cls).setUpClass()
        cls.test_record = cls.env['mail.test.activity'].with_context(cls._test_context).create({'name': 'Test'})
        # reset ctx
        cls._reset_mail_context(cls.test_record)


@tests.tagged('mail_activity')
class TestActivityRights(TestActivityCommon):

    @mute_logger('odoo.addons.mail.models.mail_mail')
    def test_activity_security_user_access_other(self):
        activity = self.test_record.with_user(self.user_employee).activity_schedule(
            'test_mail.mail_act_test_todo',
            user_id=self.user_admin.id)
        self.assertTrue(activity.can_write)
        activity.write({'user_id': self.user_employee.id})

    @mute_logger('odoo.addons.mail.models.mail_mail')
    def test_activity_security_user_access_own(self):
        activity = self.test_record.with_user(self.user_employee).activity_schedule(
            'test_mail.mail_act_test_todo')
        self.assertTrue(activity.can_write)
        activity.write({'user_id': self.user_admin.id})

    @mute_logger('odoo.addons.mail.models.mail_mail')
    def test_activity_security_user_noaccess_automated(self):
        def _employee_crash(*args, **kwargs):
            """ If employee is test employee, consider he has no access on document """
            recordset = args[0]
            if recordset.env.uid == self.user_employee.id:
                raise exceptions.AccessError('Hop hop hop Ernest, please step back.')
            return DEFAULT

        with patch.object(MailTestActivity, 'check_access_rights', autospec=True, side_effect=_employee_crash):
            activity = self.test_record.activity_schedule(
                'test_mail.mail_act_test_todo',
                user_id=self.user_employee.id)

            activity2 = self.test_record.activity_schedule('test_mail.mail_act_test_todo')
            activity2.write({'user_id': self.user_employee.id})

    def test_activity_security_user_noaccess_manual(self):
        def _employee_crash(*args, **kwargs):
            """ If employee is test employee, consider he has no access on document """
            recordset = args[0]
            if recordset.env.uid == self.user_employee.id:
                raise exceptions.AccessError('Hop hop hop Ernest, please step back.')
            return DEFAULT

        test_activity = self.env['mail.activity'].with_user(self.user_admin).create({
            'activity_type_id': self.env.ref('test_mail.mail_act_test_todo').id,
            'res_model_id': self.env.ref('test_mail.model_mail_test_activity').id,
            'res_id': self.test_record.id,
            'user_id': self.user_admin.id,
            'summary': 'Summary',
        })

        # can _search activities if access to the document
        self.env['mail.activity'].with_user(self.user_employee)._search(
            [('id', '=', test_activity.id)], count=False)

        # cannot _search activities if no access to the document
        with patch.object(MailTestActivity, 'check_access_rights', autospec=True, side_effect=_employee_crash):
            with self.assertRaises(exceptions.AccessError):
                searched_activity = self.env['mail.activity'].with_user(self.user_employee)._search(
                    [('id', '=', test_activity.id)], count=False)

        # can read_group activities if access to the document
        read_group_result = self.env['mail.activity'].with_user(self.user_employee).read_group(
            [('id', '=', test_activity.id)],
            ['summary'],
            ['summary'],
        )
        self.assertEqual(1, read_group_result[0]['summary_count'])
        self.assertEqual('Summary', read_group_result[0]['summary'])

        # cannot read_group activities if no access to the document
        with patch.object(MailTestActivity, 'check_access_rights', autospec=True, side_effect=_employee_crash):
            with self.assertRaises(exceptions.AccessError):
                self.env['mail.activity'].with_user(self.user_employee).read_group(
                    [('id', '=', test_activity.id)],
                    ['summary'],
                    ['summary'],
                )

        # cannot read activities if no access to the document
        with patch.object(MailTestActivity, 'check_access_rights', autospec=True, side_effect=_employee_crash):
            with self.assertRaises(exceptions.AccessError):
                searched_activity = self.env['mail.activity'].with_user(self.user_employee).search(
                    [('id', '=', test_activity.id)])
                searched_activity.read(['summary'])

        # cannot search_read activities if no access to the document
        with patch.object(MailTestActivity, 'check_access_rights', autospec=True, side_effect=_employee_crash):
            with self.assertRaises(exceptions.AccessError):
                self.env['mail.activity'].with_user(self.user_employee).search_read(
                    [('id', '=', test_activity.id)],
                    ['summary'])

        # cannot create activities for people that cannot access record
        with patch.object(MailTestActivity, 'check_access_rights', autospec=True, side_effect=_employee_crash):
            with self.assertRaises(exceptions.UserError):
                activity = self.env['mail.activity'].create({
                    'activity_type_id': self.env.ref('test_mail.mail_act_test_todo').id,
                    'res_model_id': self.env.ref('test_mail.model_mail_test_activity').id,
                    'res_id': self.test_record.id,
                    'user_id': self.user_employee.id,
                })

        # cannot create activities if no access to the document
        with patch.object(MailTestActivity, 'check_access_rights', autospec=True, side_effect=_employee_crash):
            with self.assertRaises(exceptions.AccessError):
                activity = self.test_record.with_user(self.user_employee).activity_schedule(
                    'test_mail.mail_act_test_todo',
                    user_id=self.user_admin.id)


@tests.tagged('mail_activity')
class TestActivityFlow(TestActivityCommon):

    def test_activity_flow_employee(self):
        with self.with_user('employee'):
            test_record = self.env['mail.test.activity'].browse(self.test_record.id)
            self.assertEqual(test_record.activity_ids, self.env['mail.activity'])

            # employee record an activity and check the deadline
            self.env['mail.activity'].create({
                'summary': 'Test Activity',
                'date_deadline': date.today() + relativedelta(days=1),
                'activity_type_id': self.env.ref('mail.mail_activity_data_email').id,
                'res_model_id': self.env['ir.model']._get(test_record._name).id,
                'res_id': test_record.id,
            })
            self.assertEqual(test_record.activity_summary, 'Test Activity')
            self.assertEqual(test_record.activity_state, 'planned')

            test_record.activity_ids.write({'date_deadline': date.today() - relativedelta(days=1)})
            test_record.invalidate_cache()  # TDE note: should not have to do it I think
            self.assertEqual(test_record.activity_state, 'overdue')

            test_record.activity_ids.write({'date_deadline': date.today()})
            test_record.invalidate_cache()  # TDE note: should not have to do it I think
            self.assertEqual(test_record.activity_state, 'today')

            # activity is done
            test_record.activity_ids.action_feedback(feedback='So much feedback')
            self.assertEqual(test_record.activity_ids, self.env['mail.activity'])
            self.assertEqual(test_record.message_ids[0].subtype_id, self.env.ref('mail.mt_activities'))

    @mute_logger('odoo.addons.mail.models.mail_mail')
    def test_activity_notify_other_user(self):
        self.user_admin.notification_type = 'email'
        rec = self.test_record.with_user(self.user_employee)
        with self.assertSinglePostNotifications(
                [{'partner': self.partner_admin, 'type': 'email'}],
                message_info={'content': 'assigned you an activity', 'subtype': 'mail.mt_note', 'message_type': 'user_notification'}):
            activity = rec.activity_schedule(
                'test_mail.mail_act_test_todo',
                user_id=self.user_admin.id)
        self.assertEqual(activity.create_uid, self.user_employee)
        self.assertEqual(activity.user_id, self.user_admin)

    def test_activity_notify_same_user(self):
        self.user_employee.notification_type = 'email'
        rec = self.test_record.with_user(self.user_employee)
        with self.assertNoNotifications():
            activity = rec.activity_schedule(
                'test_mail.mail_act_test_todo',
                user_id=self.user_employee.id)
        self.assertEqual(activity.create_uid, self.user_employee)
        self.assertEqual(activity.user_id, self.user_employee)

    @mute_logger('odoo.addons.mail.models.mail_mail')
    def test_activity_dont_notify_no_user_change(self):
        self.user_employee.notification_type = 'email'
        activity = self.test_record.activity_schedule('test_mail.mail_act_test_todo', user_id=self.user_employee.id)
        with self.assertNoNotifications():
            activity.with_user(self.user_admin).write({'user_id': self.user_employee.id})
        self.assertEqual(activity.user_id, self.user_employee)

    @mute_logger('odoo.addons.mail.models.mail_mail')
    def test_activity_summary_sync(self):
        """ Test summary from type is copied on activities if set (currently only in form-based onchange) """
        ActivityType = self.env['mail.activity.type']
        email_activity_type = ActivityType.create({
            'name': 'email',
            'summary': 'Email Summary',
        })
        call_activity_type = ActivityType.create({'name': 'call'})
        with Form(self.env['mail.activity'].with_context(default_res_model_id=self.env.ref('base.model_res_partner'))) as ActivityForm:
            ActivityForm.res_model_id = self.env.ref('base.model_res_partner')

            ActivityForm.activity_type_id = call_activity_type
            # activity summary should be empty
            self.assertEqual(ActivityForm.summary, False)

            ActivityForm.activity_type_id = email_activity_type
            # activity summary should be replaced with email's default summary
            self.assertEqual(ActivityForm.summary, email_activity_type.summary)

            ActivityForm.activity_type_id = call_activity_type
            # activity summary remains unchanged from change of activity type as call activity doesn't have default summary
            self.assertEqual(ActivityForm.summary, email_activity_type.summary)


@tests.tagged('mail_activity')
class TestActivityMixin(TestActivityCommon):

    @classmethod
    def setUpClass(cls):
        super(TestActivityMixin, cls).setUpClass()

        cls.user_utc = mail_new_test_user(
            cls.env,
            name='User UTC',
            login='User UTC',
        )
        cls.user_utc.tz = 'UTC'

        cls.user_australia = mail_new_test_user(
            cls.env,
            name='user Australia',
            login='user Australia',
        )
        cls.user_australia.tz = 'Australia/Sydney'

    @mute_logger('odoo.addons.mail.models.mail_mail')
    def test_activity_mixin(self):
        self.user_employee.tz = self.user_admin.tz
        with self.with_user('employee'):
            self.test_record = self.env['mail.test.activity'].browse(self.test_record.id)
            self.assertEqual(self.test_record.env.user, self.user_employee)

            now_utc = datetime.now(pytz.UTC)
            now_user = now_utc.astimezone(pytz.timezone(self.env.user.tz or 'UTC'))
            today_user = now_user.date()

            # Test various scheduling of activities
            act1 = self.test_record.activity_schedule(
                'test_mail.mail_act_test_todo',
                today_user + relativedelta(days=1),
                user_id=self.user_admin.id)
            self.assertEqual(act1.automated, True)

            act_type = self.env.ref('test_mail.mail_act_test_todo')
            self.assertEqual(self.test_record.activity_summary, act_type.summary)
            self.assertEqual(self.test_record.activity_state, 'planned')
            self.assertEqual(self.test_record.activity_user_id, self.user_admin)

            act2 = self.test_record.activity_schedule(
                'test_mail.mail_act_test_meeting',
                today_user + relativedelta(days=-1))
            self.assertEqual(self.test_record.activity_state, 'overdue')
            # `activity_user_id` is defined as `fields.Many2one('res.users', 'Responsible User', related='activity_ids.user_id')`
            # it therefore relies on the natural order of `activity_ids`, according to which activity comes first.
            # As we just created the activity, its not yet in the right order.
            # We force it by invalidating it so it gets fetched from database, in the right order.
            self.test_record.invalidate_cache(['activity_ids'])
            self.assertEqual(self.test_record.activity_user_id, self.user_employee)

            act3 = self.test_record.activity_schedule(
                'test_mail.mail_act_test_todo',
                today_user + relativedelta(days=3),
                user_id=self.user_employee.id)
            self.assertEqual(self.test_record.activity_state, 'overdue')
            # `activity_user_id` is defined as `fields.Many2one('res.users', 'Responsible User', related='activity_ids.user_id')`
            # it therefore relies on the natural order of `activity_ids`, according to which activity comes first.
            # As we just created the activity, its not yet in the right order.
            # We force it by invalidating it so it gets fetched from database, in the right order.
            self.test_record.invalidate_cache(['activity_ids'])
            self.assertEqual(self.test_record.activity_user_id, self.user_employee)

            self.test_record.invalidate_cache(ids=self.test_record.ids)
            self.assertEqual(self.test_record.activity_ids, act1 | act2 | act3)

            # Perform todo activities for admin
            self.test_record.activity_feedback(
                ['test_mail.mail_act_test_todo'],
                user_id=self.user_admin.id,
                feedback='Test feedback',)
            self.assertEqual(self.test_record.activity_ids, act2 | act3)

            # Reschedule all activities, should update the record state
            self.assertEqual(self.test_record.activity_state, 'overdue')
            self.test_record.activity_reschedule(
                ['test_mail.mail_act_test_meeting', 'test_mail.mail_act_test_todo'],
                date_deadline=today_user + relativedelta(days=3)
            )
            self.assertEqual(self.test_record.activity_state, 'planned')

            # Perform todo activities for remaining people
            self.test_record.activity_feedback(
                ['test_mail.mail_act_test_todo'],
                feedback='Test feedback')

            # Setting activities as done should delete them and post messages
            self.assertEqual(self.test_record.activity_ids, act2)
            self.assertEqual(len(self.test_record.message_ids), 2)
            self.assertEqual(self.test_record.message_ids.mapped('subtype_id'), self.env.ref('mail.mt_activities'))

            # Perform meeting activities
            self.test_record.activity_unlink(['test_mail.mail_act_test_meeting'])

            # Canceling activities should simply remove them
            self.assertEqual(self.test_record.activity_ids, self.env['mail.activity'])
            self.assertEqual(len(self.test_record.message_ids), 2)

    @mute_logger('odoo.addons.mail.models.mail_mail')
    def test_activity_mixin_archive(self):
        rec = self.test_record.with_user(self.user_employee)
        new_act = rec.activity_schedule(
            'test_mail.mail_act_test_todo',
            user_id=self.user_admin.id)
        self.assertEqual(rec.activity_ids, new_act)
        rec.toggle_active()
        self.assertEqual(rec.active, False)
        self.assertEqual(rec.activity_ids, self.env['mail.activity'])
        rec.toggle_active()
        self.assertEqual(rec.active, True)
        self.assertEqual(rec.activity_ids, self.env['mail.activity'])

    @mute_logger('odoo.addons.mail.models.mail_mail')
    def test_activity_mixin_reschedule_user(self):
        rec = self.test_record.with_user(self.user_employee)
        rec.activity_schedule(
            'test_mail.mail_act_test_todo',
            user_id=self.user_admin.id)
        self.assertEqual(rec.activity_ids[0].user_id, self.user_admin)

        # reschedule its own should not alter other's activities
        rec.activity_reschedule(
            ['test_mail.mail_act_test_todo'],
            user_id=self.user_employee.id,
            new_user_id=self.user_employee.id)
        self.assertEqual(rec.activity_ids[0].user_id, self.user_admin)

        rec.activity_reschedule(
            ['test_mail.mail_act_test_todo'],
            user_id=self.user_admin.id,
            new_user_id=self.user_employee.id)
        self.assertEqual(rec.activity_ids[0].user_id, self.user_employee)

    @users('employee')
    def test_feedback_w_attachments(self):
        test_record = self.env['mail.test.activity'].browse(self.test_record.ids)

        activity = self.env['mail.activity'].create({
            'activity_type_id': 1,
            'res_id': test_record.id,
            'res_model_id': self.env['ir.model']._get_id('mail.test.activity'),
            'summary': 'Test',
        })
        attachments = self.env['ir.attachment'].create([{
            'name': 'test',
            'res_name': 'test',
            'res_model': 'mail.activity',
            'res_id': activity.id,
            'datas': 'test',
        }, {
            'name': 'test2',
            'res_name': 'test',
            'res_model': 'mail.activity',
            'res_id': activity.id,
            'datas': 'testtest',
        }])

        # Checking if the attachment has been forwarded to the message
        # when marking an activity as "Done"
        activity.action_feedback()
        activity_message = test_record.message_ids[-1]
        self.assertEqual(set(activity_message.attachment_ids.ids), set(attachments.ids))
        for attachment in attachments:
            self.assertEqual(attachment.res_id, activity_message.id)
            self.assertEqual(attachment.res_model, activity_message._name)

    @users('employee')
    def test_feedback_chained_current_date(self):
        frozen_now = datetime(2021, 10, 10, 14, 30, 15)

        test_record = self.env['mail.test.activity'].browse(self.test_record.ids)
        first_activity = self.env['mail.activity'].create({
            'activity_type_id': self.env.ref('test_mail.mail_act_test_chained_1').id,
            'date_deadline': frozen_now + relativedelta(days=-2),
            'res_id': test_record.id,
            'res_model_id': self.env['ir.model']._get_id('mail.test.activity'),
            'summary': 'Test',
        })
        first_activity_id = first_activity.id

        with freeze_time(frozen_now):
            first_activity.action_feedback(feedback='Done')
        self.assertFalse(first_activity.exists())

        # check chained activity
        new_activity = test_record.activity_ids
        self.assertNotEqual(new_activity.id, first_activity_id)
        self.assertEqual(new_activity.summary, 'Take the second step.')
        self.assertEqual(new_activity.date_deadline, frozen_now.date() + relativedelta(days=10))

    @users('employee')
    def test_feedback_chained_previous(self):
        self.env.ref('test_mail.mail_act_test_chained_2').sudo().write({'delay_from': 'previous_activity'})
        frozen_now = datetime(2021, 10, 10, 14, 30, 15)

        test_record = self.env['mail.test.activity'].browse(self.test_record.ids)
        first_activity = self.env['mail.activity'].create({
            'activity_type_id': self.env.ref('test_mail.mail_act_test_chained_1').id,
            'date_deadline': frozen_now + relativedelta(days=-2),
            'res_id': test_record.id,
            'res_model_id': self.env['ir.model']._get_id('mail.test.activity'),
            'summary': 'Test',
        })
        first_activity_id = first_activity.id

        with freeze_time(frozen_now):
            first_activity.action_feedback(feedback='Done')
        self.assertFalse(first_activity.exists())

        # check chained activity
        new_activity = test_record.activity_ids
        self.assertNotEqual(new_activity.id, first_activity_id)
        self.assertEqual(new_activity.summary, 'Take the second step.')
        self.assertEqual(new_activity.date_deadline, frozen_now.date() + relativedelta(days=8),
                         'New deadline should take into account original activity deadline, not current date')

    def test_mail_activity_state(self):
        """Create 3 activity for 2 different users in 2 different timezones.

        User UTC (+0h)
        User Australia (+11h)
        Today datetime: 1/1/2020 16h

        Activity 1 & User UTC
            1/1/2020 - 16h UTC       -> The state is today

        Activity 2 & User Australia
            1/1/2020 - 16h UTC
            2/1/2020 -  1h Australia -> State is overdue

        Activity 3 & User UTC
            1/1/2020 - 23h UTC       -> The state is today
        """
        today_utc = datetime(2020, 1, 1, 16, 0, 0)

        class MockedDatetime(datetime):
            @classmethod
            def utcnow(cls):
                return today_utc

        record = self.env['mail.test.activity'].create({'name': 'Record'})

        with patch('odoo.addons.mail.models.mail_activity.datetime', MockedDatetime):
            activity_1 = self.env['mail.activity'].create({
                'summary': 'Test',
                'activity_type_id': 1,
                'res_model_id': self.env.ref('test_mail.model_mail_test_activity').id,
                'res_id': record.id,
                'date_deadline': today_utc,
                'user_id': self.user_utc.id,
            })

            activity_2 = activity_1.copy()
            activity_2.user_id = self.user_australia
            activity_3 = activity_1.copy()
            activity_3.date_deadline += relativedelta(hours=7)

            self.assertEqual(activity_1.state, 'today')
            self.assertEqual(activity_2.state, 'overdue')
            self.assertEqual(activity_3.state, 'today')

    def test_mail_activity_mixin_search_state_basic(self):
        """Test the search method on the "activity_state".

        Test all the operators and also test the case where the "activity_state" is
        different because of the timezone. There's also a tricky case for which we
        "reverse" the domain for performance purpose.
        """
        today_utc = datetime(2020, 1, 1, 16, 0, 0)

        class MockedDatetime(datetime):
            @classmethod
            def utcnow(cls):
                return today_utc

        # Create some records without activity schedule on it for testing
        self.env['mail.test.activity'].create([
            {'name': 'Record %i' % record_i}
            for record_i in range(5)
        ])

        origin_1, origin_2 = self.env['mail.test.activity'].search([], limit=2)

        with patch('odoo.addons.mail.models.mail_activity.datetime', MockedDatetime), \
            patch('odoo.addons.mail.models.mail_activity_mixin.datetime', MockedDatetime):
            origin_1_activity_1 = self.env['mail.activity'].create({
                'summary': 'Test',
                'activity_type_id': 1,
                'res_model_id': self.env.ref('test_mail.model_mail_test_activity').id,
                'res_id': origin_1.id,
                'date_deadline': today_utc,
                'user_id': self.user_utc.id,
            })

            origin_1_activity_2 = origin_1_activity_1.copy()
            origin_1_activity_2.user_id = self.user_australia
            origin_1_activity_3 = origin_1_activity_1.copy()
            origin_1_activity_3.date_deadline += relativedelta(hours=8)

            self.assertEqual(origin_1_activity_1.state, 'today')
            self.assertEqual(origin_1_activity_2.state, 'overdue')
            self.assertEqual(origin_1_activity_3.state, 'today')

            origin_2_activity_1 = self.env['mail.activity'].create({
                'summary': 'Test',
                'activity_type_id': 1,
                'res_model_id': self.env.ref('test_mail.model_mail_test_activity').id,
                'res_id': origin_2.id,
                'date_deadline': today_utc + relativedelta(hours=8),
                'user_id': self.user_utc.id,
            })

            origin_2_activity_2 = origin_2_activity_1.copy()
            origin_2_activity_2.user_id = self.user_australia
            origin_2_activity_3 = origin_2_activity_1.copy()
            origin_2_activity_3.date_deadline -= relativedelta(hours=8)
            origin_2_activity_4 = origin_2_activity_1.copy()
            origin_2_activity_4.date_deadline = datetime(2020, 1, 2, 0, 0, 0)

            self.assertEqual(origin_2_activity_1.state, 'planned')
            self.assertEqual(origin_2_activity_2.state, 'today')
            self.assertEqual(origin_2_activity_3.state, 'today')
            self.assertEqual(origin_2_activity_4.state, 'planned')

            all_activity_mixin_record = self.env['mail.test.activity'].search([])

            result = self.env['mail.test.activity'].search([('activity_state', '=', 'today')])
            self.assertTrue(len(result) > 0)
            self.assertEqual(result, all_activity_mixin_record.filtered(lambda p: p.activity_state == 'today'))

            result = self.env['mail.test.activity'].search([('activity_state', 'in', ('today', 'overdue'))])
            self.assertTrue(len(result) > 0)
            self.assertEqual(result, all_activity_mixin_record.filtered(lambda p: p.activity_state in ('today', 'overdue')))

            result = self.env['mail.test.activity'].search([('activity_state', 'not in', ('today',))])
            self.assertTrue(len(result) > 0)
            self.assertEqual(result, all_activity_mixin_record.filtered(lambda p: p.activity_state not in ('today',)))

            result = self.env['mail.test.activity'].search([('activity_state', '=', False)])
            self.assertTrue(len(result) >= 3, "There is more than 3 records without an activity schedule on it")
            self.assertEqual(result, all_activity_mixin_record.filtered(lambda p: not p.activity_state))

            result = self.env['mail.test.activity'].search([('activity_state', 'not in', ('planned', 'overdue', 'today'))])
            self.assertTrue(len(result) >= 3, "There is more than 3 records without an activity schedule on it")
            self.assertEqual(result, all_activity_mixin_record.filtered(lambda p: not p.activity_state))

            # test tricky case when the domain will be reversed in the search method
            # because of falsy value
            result = self.env['mail.test.activity'].search([('activity_state', 'not in', ('today', False))])
            self.assertTrue(len(result) > 0)
            self.assertEqual(result, all_activity_mixin_record.filtered(lambda p: p.activity_state not in ('today', False)))

            result = self.env['mail.test.activity'].search([('activity_state', 'in', ('today', False))])
            self.assertTrue(len(result) > 0)
            self.assertEqual(result, all_activity_mixin_record.filtered(lambda p: p.activity_state in ('today', False)))

    def test_mail_activity_mixin_search_state_different_day_but_close_time(self):
        """Test the case where there's less than 24 hours between the deadline and now_tz,
        but one day of difference (e.g. 23h 01/01/2020 & 1h 02/02/2020). So the state
        should be "planned" and not "today". This case was tricky to implement in SQL
        that's why it has its own test.
        """
        today_utc = datetime(2020, 1, 1, 23, 0, 0)

        class MockedDatetime(datetime):
            @classmethod
            def utcnow(cls):
                return today_utc

        # Create some records without activity schedule on it for testing
        self.env['mail.test.activity'].create([
            {'name': 'Record %i' % record_i}
            for record_i in range(5)
        ])

        origin_1 = self.env['mail.test.activity'].search([], limit=1)

        with patch('odoo.addons.mail.models.mail_activity.datetime', MockedDatetime):
            origin_1_activity_1 = self.env['mail.activity'].create({
                'summary': 'Test',
                'activity_type_id': 1,
                'res_model_id': self.env.ref('test_mail.model_mail_test_activity').id,
                'res_id': origin_1.id,
                'date_deadline': today_utc + relativedelta(hours=2),
                'user_id': self.user_utc.id,
            })

            self.assertEqual(origin_1_activity_1.state, 'planned')
            result = self.env['mail.test.activity'].search([('activity_state', '=', 'today')])
            self.assertNotIn(origin_1, result, 'The activity state miss calculated during the search')

    @mute_logger('odoo.addons.mail.models.mail_mail')
    def test_my_activity_flow_employee(self):
        Activity = self.env['mail.activity']
        date_today = date.today()
        Activity.create({
            'activity_type_id': self.env.ref('test_mail.mail_act_test_todo').id,
            'date_deadline': date_today,
            'res_model_id': self.env.ref('test_mail.model_mail_test_activity').id,
            'res_id': self.test_record.id,
            'user_id': self.user_admin.id,
        })
        Activity.create({
            'activity_type_id': self.env.ref('test_mail.mail_act_test_call').id,
            'date_deadline': date_today + relativedelta(days=1),
            'res_model_id': self.env.ref('test_mail.model_mail_test_activity').id,
            'res_id': self.test_record.id,
            'user_id': self.user_employee.id,
        })

        test_record_1 = self.env['mail.test.activity'].with_context(self._test_context).create({'name': 'Test 1'})
        Activity.create({
            'activity_type_id': self.env.ref('test_mail.mail_act_test_todo').id,
            'date_deadline': date_today,
            'res_model_id': self.env.ref('test_mail.model_mail_test_activity').id,
            'res_id': test_record_1.id,
            'user_id': self.user_employee.id,
        })
        with self.with_user('employee'):
            record = self.env['mail.test.activity'].search([('my_activity_date_deadline', '=', date_today)])
            self.assertEqual(test_record_1, record)


@tests.tagged('mail_activity')
class TestORM(TestActivityCommon):
    """Test for read_progress_bar"""

    def test_week_grouping(self):
        """The labels associated to each record in read_progress_bar should match
        the ones from read_group, even in edge cases like en_US locale on sundays
        """
        MailTestActivityCtx = self.env['mail.test.activity'].with_context({"lang": "en_US"})

        # Don't mistake fields date and date_deadline:
        # * date is just a random value
        # * date_deadline defines activity_state
        self.env['mail.test.activity'].create({
            'date': '2021-05-02',
            'name': "Yesterday, all my troubles seemed so far away",
        }).activity_schedule(
            'test_mail.mail_act_test_todo',
            summary="Make another test super asap (yesterday)",
            date_deadline=fields.Date.context_today(MailTestActivityCtx) - timedelta(days=7),
        )
        self.env['mail.test.activity'].create({
            'date': '2021-05-09',
            'name': "Things we said today",
        }).activity_schedule(
            'test_mail.mail_act_test_todo',
            summary="Make another test asap",
            date_deadline=fields.Date.context_today(MailTestActivityCtx),
        )
        self.env['mail.test.activity'].create({
            'date': '2021-05-16',
            'name': "Tomorrow Never Knows",
        }).activity_schedule(
            'test_mail.mail_act_test_todo',
            summary="Make a test tomorrow",
            date_deadline=fields.Date.context_today(MailTestActivityCtx) + timedelta(days=7),
        )

        domain = [('date', "!=", False)]
        groupby = "date:week"
        progress_bar = {
            'field': 'activity_state',
            'colors': {
                "overdue": 'danger',
                "today": 'warning',
                "planned": 'success',
            }
        }

        # call read_group to compute group names
        groups = MailTestActivityCtx.read_group(domain, fields=['date'], groupby=[groupby])
        progressbars = MailTestActivityCtx.read_progress_bar(domain, group_by=groupby, progress_bar=progress_bar)
        self.assertEqual(len(groups), 3)
        self.assertEqual(len(progressbars), 3)

        # format the read_progress_bar result to get a dictionary under this
        # format: {activity_state: group_name}; the original format
        # (after read_progress_bar) is {group_name: {activity_state: count}}
        pg_groups = {
            next(state for state, count in data.items() if count): group_name
            for group_name, data in progressbars.items()
        }

        self.assertEqual(groups[0][groupby], pg_groups["overdue"])
        self.assertEqual(groups[1][groupby], pg_groups["today"])
        self.assertEqual(groups[2][groupby], pg_groups["planned"])
