# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from collections import defaultdict

from odoo import _, api, exceptions, fields, models, modules
from odoo.addons.base.models.res_users import is_selection_groups


class Users(models.Model):
    """ Update of res.users class
        - add a preference about sending emails about notifications
        - make a new user follow itself
        - add a welcome message
        - add suggestion preference
        - if adding groups to a user, check mail.channels linked to this user
          group, and the user. This is done by overriding the write method.
    """
    _name = 'res.users'
    _inherit = ['res.users']
    _description = 'Users'

    notification_type = fields.Selection([
        ('email', 'Handle by Emails'),
        ('inbox', 'Handle in Odoo')],
        'Notification', required=True, default='email',
        help="Policy on how to handle Chatter notifications:\n"
             "- Handle by Emails: notifications are sent to your email address\n"
             "- Handle in Odoo: notifications appear in your Odoo Inbox")
    res_users_settings_ids = fields.One2many('res.users.settings', 'user_id')

    # ------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['notification_type']

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ['notification_type']

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if not values.get('login', False):
                action = self.env.ref('base.action_res_users')
                msg = _("You cannot create a new user from here.\n To create new user please go to configuration panel.")
                raise exceptions.RedirectWarning(msg, action.id, _('Go to the configuration panel'))

        users = super(Users, self).create(vals_list)

        # log a portal status change (manual tracking)
        log_portal_access = not self._context.get('mail_create_nolog') and not self._context.get('mail_notrack')
        if log_portal_access:
            for user in users:
                if user.has_group('base.group_portal'):
                    body = user._get_portal_access_update_body(True)
                    user.partner_id.message_post(
                        body=body,
                        message_type='notification',
                        subtype_xmlid='mail.mt_note'
                    )
        # Auto-subscribe to channels unless skip explicitly requested
        if not self.env.context.get('mail_channel_nosubscribe'):
            self.env['mail.channel'].search([('group_ids', 'in', users.groups_id.ids)])._subscribe_users_automatically()
        return users

    def write(self, vals):
        log_portal_access = 'groups_id' in vals and not self._context.get('mail_create_nolog') and not self._context.get('mail_notrack')
        user_portal_access_dict = {
            user.id: user.has_group('base.group_portal')
            for user in self
        } if log_portal_access else {}

        write_res = super(Users, self).write(vals)

        # log a portal status change (manual tracking)
        if log_portal_access:
            for user in self:
                user_has_group = user.has_group('base.group_portal')
                portal_access_changed = user_has_group != user_portal_access_dict[user.id]
                if portal_access_changed:
                    body = user._get_portal_access_update_body(user_has_group)
                    user.partner_id.message_post(
                        body=body,
                        message_type='notification',
                        subtype_xmlid='mail.mt_note'
                    )

        if 'active' in vals and not vals['active']:
            self._unsubscribe_from_non_public_channels()
        sel_groups = [vals[k] for k in vals if is_selection_groups(k) and vals[k]]
        if vals.get('groups_id'):
            # form: {'group_ids': [(3, 10), (3, 3), (4, 10), (4, 3)]} or {'group_ids': [(6, 0, [ids]}
            user_group_ids = [command[1] for command in vals['groups_id'] if command[0] == 4]
            user_group_ids += [id for command in vals['groups_id'] if command[0] == 6 for id in command[2]]
            self.env['mail.channel'].search([('group_ids', 'in', user_group_ids)])._subscribe_users_automatically()
        elif sel_groups:
            self.env['mail.channel'].search([('group_ids', 'in', sel_groups)])._subscribe_users_automatically()
        return write_res

    def unlink(self):
        self._unsubscribe_from_non_public_channels()
        return super().unlink()

    def _unsubscribe_from_non_public_channels(self):
        """ This method un-subscribes users from private mail channels. Main purpose of this
            method is to prevent sending internal communication to archived / deleted users.
            We do not un-subscribes users from public channels because in most common cases,
            public channels are mailing list (e-mail based) and so users should always receive
            updates from public channels until they manually un-subscribe themselves.
        """
        current_cp = self.env['mail.channel.partner'].sudo().search([
            ('partner_id', 'in', self.partner_id.ids),
        ])
        current_cp.filtered(
            lambda cp: cp.channel_id.public != 'public' and cp.channel_id.channel_type == 'channel'
        ).unlink()

    def _get_portal_access_update_body(self, access_granted):
        body = _('Portal Access Granted') if access_granted else _('Portal Access Revoked')
        if self.partner_id.email:
            return '%s (%s)' % (body, self.partner_id.email)
        return body

    # ------------------------------------------------------------
    # DISCUSS
    # ------------------------------------------------------------

    def _init_messaging(self):
        self.ensure_one()
        partner_root = self.env.ref('base.partner_root')
        values = {
            'channels': self.partner_id._get_channels_as_member().channel_info(),
            'companyName': self.env.company.name,
            'currentGuest': False,
            'current_partner': self.partner_id.mail_partner_format().get(self.partner_id),
            'current_user_id': self.id,
            'current_user_settings': self.env['res.users.settings']._find_or_create_for_user(self)._res_users_settings_format(),
            'mail_failures': [],
            'menu_id': self.env['ir.model.data']._xmlid_to_res_id('mail.menu_root_discuss'),
            'needaction_inbox_counter': self.partner_id._get_needaction_count(),
            'partner_root': partner_root.sudo().mail_partner_format().get(partner_root),
            'public_partners': list(self.env.ref('base.group_public').sudo().with_context(active_test=False).users.partner_id.mail_partner_format().values()),
            'shortcodes': self.env['mail.shortcode'].sudo().search_read([], ['source', 'substitution', 'description']),
            'starred_counter': self.env['mail.message'].search_count([('starred_partner_ids', 'in', self.partner_id.ids)]),
        }
        return values

    @api.model
    def systray_get_activities(self):
        query = """SELECT array_agg(res_id) as res_ids, m.id, count(*),
                    CASE
                        WHEN %(today)s::date - act.date_deadline::date = 0 Then 'today'
                        WHEN %(today)s::date - act.date_deadline::date > 0 Then 'overdue'
                        WHEN %(today)s::date - act.date_deadline::date < 0 Then 'planned'
                    END AS states
                FROM mail_activity AS act
                JOIN ir_model AS m ON act.res_model_id = m.id
                WHERE user_id = %(user_id)s
                GROUP BY m.id, states;
                """
        self.env.cr.execute(query, {
            'today': fields.Date.context_today(self),
            'user_id': self.env.uid,
        })
        activity_data = self.env.cr.dictfetchall()
        records_by_state_by_model = defaultdict(lambda: {"today": set(), "overdue": set(), "planned": set(), "all": set()})
        for data in activity_data:
            records_by_state_by_model[data["id"]][data["states"]] = set(data["res_ids"])
            records_by_state_by_model[data["id"]]["all"] = records_by_state_by_model[data["id"]]["all"] | set(data["res_ids"])
        user_activities = {}
        for model_id in records_by_state_by_model:
            model_dic = records_by_state_by_model[model_id]
            model = self.env["ir.model"].sudo().browse(model_id).with_prefetch(tuple(records_by_state_by_model.keys()))
            allowed_records = self.env[model.model].search([("id", "in", tuple(model_dic["all"]))])
            if not allowed_records:
                continue
            module = self.env[model.model]._original_module
            icon = module and modules.module.get_module_icon(module)
            today = len(model_dic["today"] & set(allowed_records.ids))
            overdue = len(model_dic["overdue"] & set(allowed_records.ids))
            user_activities[model.model] = {
                "name": model.name,
                "model": model.model,
                "type": "activity",
                "icon": icon,
                "total_count": today + overdue,
                "today_count": today,
                "overdue_count": overdue,
                "planned_count": len(model_dic["planned"] & set(allowed_records.ids)),
                "actions": [
                    {
                        "icon": "fa-clock-o",
                        "name": "Summary",
                    }
                ],
            }
        return list(user_activities.values())
