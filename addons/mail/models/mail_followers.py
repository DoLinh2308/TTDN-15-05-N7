# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from collections import defaultdict
import itertools

from odoo import api, fields, models, Command


class Followers(models.Model):
    """ mail_followers holds the data related to the follow mechanism inside
    Odoo. Partners can choose to follow documents (records) of any kind
    that inherits from mail.thread. Following documents allow to receive
    notifications for new messages. A subscription is characterized by:

    :param: res_model: model of the followed objects
    :param: res_id: ID of resource (may be 0 for every objects)
    """
    _name = 'mail.followers'
    _rec_name = 'partner_id'
    _log_access = False
    _description = 'Document Followers'

    # Note. There is no integrity check on model names for performance reasons.
    # However, followers of unlinked models are deleted by models themselves
    # (see 'ir.model' inheritance).
    res_model = fields.Char(
        'Related Document Model Name', required=True, index=True)
    res_id = fields.Many2oneReference(
        'Related Document ID', index=True, help='Id of the followed resource', model_field='res_model')
    partner_id = fields.Many2one(
        'res.partner', string='Related Partner', index=True, ondelete='cascade', required=True, domain=[('type', '!=', 'private')])
    subtype_ids = fields.Many2many(
        'mail.message.subtype', string='Subtype',
        help="Message subtypes followed, meaning subtypes that will be pushed onto the user's Wall.")
    name = fields.Char('Name', related='partner_id.name')
    email = fields.Char('Email', related='partner_id.email')
    is_active = fields.Boolean('Is Active', related='partner_id.active')

    def _invalidate_documents(self, vals_list=None):
        """ Invalidate the cache of the documents followed by ``self``.

        Modifying followers change access rights to individual documents. As the
        cache may contain accessible/inaccessible data, one has to refresh it.
        """
        to_invalidate = defaultdict(list)
        for record in (vals_list or [{'res_model': rec.res_model, 'res_id': rec.res_id} for rec in self]):
            if record.get('res_id'):
                to_invalidate[record.get('res_model')].append(record.get('res_id'))

    @api.model_create_multi
    def create(self, vals_list):
        res = super(Followers, self).create(vals_list)
        res._invalidate_documents(vals_list)
        return res

    def write(self, vals):
        if 'res_model' in vals or 'res_id' in vals:
            self._invalidate_documents()
        res = super(Followers, self).write(vals)
        if any(x in vals for x in ['res_model', 'res_id', 'partner_id']):
            self._invalidate_documents()
        return res

    def unlink(self):
        self._invalidate_documents()
        return super(Followers, self).unlink()

    _sql_constraints = [
        ('mail_followers_res_partner_res_model_id_uniq', 'unique(res_model,res_id,partner_id)', 'Error, a partner cannot follow twice the same object.'),
    ]

    # --------------------------------------------------
    # Private tools methods to fetch followers data
    # --------------------------------------------------

    def _get_recipient_data(self, records, message_type, subtype_id, pids=None):
        """ Private method allowing to fetch recipients data based on a subtype.
        Purpose of this method is to fetch all data necessary to notify recipients
        in a single query. It fetches data from

         * followers (partners and channels) of records that follow the given
           subtype if records and subtype are set;
         * partners if pids is given;

        :param records: fetch data from followers of records that follow subtype_id;
        :param message_type: mail.message.message_type in order to allow custom behavior depending on it (SMS for example);
        :param subtype_id: mail.message.subtype to check against followers;
        :param pids: additional set of partner IDs from which to fetch recipient data;

        :return: list of recipient data which is a tuple containing
          partner ID ,
          active value (always True for channels),
          share status of partner,
          notification status of partner or channel (email or inbox),
          user groups of partner,
        """
        self.env['mail.followers'].flush(['partner_id', 'subtype_ids'])
        self.env['mail.message.subtype'].flush(['internal'])
        self.env['res.users'].flush(['notification_type', 'active', 'partner_id', 'groups_id'])
        self.env['res.partner'].flush(['active', 'partner_share'])
        self.env['res.groups'].flush(['users'])
        if records and subtype_id:
            query = """
SELECT DISTINCT ON (pid) * FROM (
    WITH sub_followers AS (
        SELECT fol.partner_id,
               coalesce(subtype.internal, false) as internal
          FROM mail_followers fol
          JOIN mail_followers_mail_message_subtype_rel subrel ON subrel.mail_followers_id = fol.id
          JOIN mail_message_subtype subtype ON subtype.id = subrel.mail_message_subtype_id
         WHERE subrel.mail_message_subtype_id = %s
           AND fol.res_model = %s
           AND fol.res_id IN %s

     UNION ALL

        SELECT id,
               FALSE
          FROM res_partner
         WHERE id=ANY(%s)
    )
    SELECT partner.id as pid,
           partner.active as active,
           partner.partner_share as pshare,
           users.notification_type AS notif,
           array_agg(groups_rel.gid) AS groups
      FROM res_partner partner
 LEFT JOIN res_users users ON users.partner_id = partner.id
                          AND users.active
 LEFT JOIN res_groups_users_rel groups_rel ON groups_rel.uid = users.id
      JOIN sub_followers ON sub_followers.partner_id = partner.id
                        AND (NOT sub_followers.internal OR partner.partner_share IS NOT TRUE)
        GROUP BY partner.id,
                 users.notification_type
) AS x
ORDER BY pid, notif
"""
            params = [subtype_id, records._name, tuple(records.ids), list(pids) or []]
            self.env.cr.execute(query, tuple(params))
            res = self.env.cr.fetchall()
        elif pids:
            params = []
            query_pid = """
SELECT partner.id as pid,
    partner.active as active, partner.partner_share as pshare,
    users.notification_type AS notif,
    array_agg(groups_rel.gid) FILTER (WHERE groups_rel.gid IS NOT NULL) AS groups
FROM res_partner partner
    LEFT JOIN res_users users ON users.partner_id = partner.id AND users.active
    LEFT JOIN res_groups_users_rel groups_rel ON groups_rel.uid = users.id
WHERE partner.id IN %s
GROUP BY partner.id, users.notification_type"""
            params.append(tuple(pids))
            query = 'SELECT DISTINCT ON (pid) * FROM (%s) AS x ORDER BY pid, notif' % query_pid
            self.env.cr.execute(query, tuple(params))
            res = self.env.cr.fetchall()
        else:
            res = []
        return res

    def _get_subscription_data(self, doc_data, pids, include_pshare=False, include_active=False):
        """ Private method allowing to fetch follower data from several documents of a given model.
        Followers can be filtered given partner IDs and channel IDs.

        :param doc_data: list of pair (res_model, res_ids) that are the documents from which we
          want to have subscription data;
        :param pids: optional partner to filter; if None take all, otherwise limitate to pids
        :param include_pshare: optional join in partner to fetch their share status
        :param include_active: optional join in partner to fetch their active flag

        :return: list of followers data which is a list of tuples containing
          follower ID,
          document ID,
          partner ID,
          followed subtype IDs,
          share status of partner (returned only if include_pshare is True)
          active flag status of partner (returned only if include_active is True)
        """
        self.env['mail.followers'].flush(['partner_id', 'res_id', 'res_model', 'subtype_ids'])
        self.env['res.partner'].flush(['active', 'partner_share'])
        # base query: fetch followers of given documents
        where_clause = ' OR '.join(['fol.res_model = %s AND fol.res_id IN %s'] * len(doc_data))
        where_params = list(itertools.chain.from_iterable((rm, tuple(rids)) for rm, rids in doc_data))

        # additional: filter on optional pids
        sub_where = []
        if pids:
            sub_where += ["fol.partner_id IN %s"]
            where_params.append(tuple(pids))
        elif pids is not None:
            sub_where += ["fol.partner_id IS NULL"]
        if sub_where:
            where_clause += "AND (%s)" % " OR ".join(sub_where)

        query = """
SELECT fol.id, fol.res_id, fol.partner_id, array_agg(subtype.id)%s%s
FROM mail_followers fol
%s
LEFT JOIN mail_followers_mail_message_subtype_rel fol_rel ON fol_rel.mail_followers_id = fol.id
LEFT JOIN mail_message_subtype subtype ON subtype.id = fol_rel.mail_message_subtype_id
WHERE %s
GROUP BY fol.id%s%s""" % (
            ', partner.partner_share' if include_pshare else '',
            ', partner.active' if include_active else '',
            'LEFT JOIN res_partner partner ON partner.id = fol.partner_id' if (include_pshare or include_active) else '',
            where_clause,
            ', partner.partner_share' if include_pshare else '',
            ', partner.active' if include_active else ''
        )
        self.env.cr.execute(query, tuple(where_params))
        return self.env.cr.fetchall()

    # --------------------------------------------------
    # Private tools methods to generate new subscription
    # --------------------------------------------------

    def _insert_followers(self, res_model, res_ids,
                          partner_ids, subtypes=None,
                          customer_ids=None, check_existing=True, existing_policy='skip'):
        """ Main internal method allowing to create or update followers for documents, given a
        res_model and the document res_ids. This method does not handle access rights. This is the
        role of the caller to ensure there is no security breach.

        :param subtypes: see ``_add_followers``. If not given, default ones are computed.
        :param customer_ids: see ``_add_default_followers``
        :param check_existing: see ``_add_followers``;
        :param existing_policy: see ``_add_followers``;
        """
        sudo_self = self.sudo().with_context(default_partner_id=False)
        if not subtypes:  # no subtypes -> default computation, no force, skip existing
            new, upd = self._add_default_followers(
                res_model, res_ids, partner_ids,
                customer_ids=customer_ids,
                check_existing=check_existing,
                existing_policy=existing_policy)
        else:
            new, upd = self._add_followers(
                res_model, res_ids,
                partner_ids, subtypes,
                check_existing=check_existing,
                existing_policy=existing_policy)
        if new:
            sudo_self.create([
                dict(values, res_id=res_id)
                for res_id, values_list in new.items()
                for values in values_list
            ])
        for fol_id, values in upd.items():
            sudo_self.browse(fol_id).write(values)

    def _add_default_followers(self, res_model, res_ids, partner_ids, customer_ids=None,
                               check_existing=True, existing_policy='skip'):
        """ Shortcut to ``_add_followers`` that computes default subtypes. Existing
        followers are skipped as their subscription is considered as more important
        compared to new default subscription.

        :param customer_ids: optional list of partner ids that are customers. It is used if computing
         default subtype is necessary and allow to avoid the check of partners being customers (no
         user or share user). It is just a matter of saving queries if the info is already known;
        :param check_existing: see ``_add_followers``;
        :param existing_policy: see ``_add_followers``;

        :return: see ``_add_followers``
        """
        if not partner_ids:
            return dict(), dict()

        default, _, external = self.env['mail.message.subtype'].default_subtypes(res_model)
        if partner_ids and customer_ids is None:
            customer_ids = self.env['res.partner'].sudo().search([('id', 'in', partner_ids), ('partner_share', '=', True)]).ids

        p_stypes = dict((pid, external.ids if pid in customer_ids else default.ids) for pid in partner_ids)

        return self._add_followers(res_model, res_ids, partner_ids, p_stypes, check_existing=check_existing, existing_policy=existing_policy)

    def _add_followers(self, res_model, res_ids, partner_ids, subtypes,
                       check_existing=False, existing_policy='skip'):
        """ Internal method that generates values to insert or update followers. Callers have to
        handle the result, for example by making a valid ORM command, inserting or updating directly
        follower records, ... This method returns two main data

         * first one is a dict which keys are res_ids. Value is a list of dict of values valid for
           creating new followers for the related res_id;
         * second one is a dict which keys are follower ids. Value is a dict of values valid for
           updating the related follower record;

        :param subtypes: optional subtypes for new partner followers. This
          is a dict whose keys are partner IDs and value subtype IDs for that
          partner.
        :param channel_subtypes: optional subtypes for new channel followers. This
          is a dict whose keys are channel IDs and value subtype IDs for that
          channel.
        :param check_existing: if True, check for existing followers for given
          documents and handle them according to existing_policy parameter.
          Setting to False allows to save some computation if caller is sure
          there are no conflict for followers;
        :param existing policy: if check_existing, tells what to do with already
          existing followers:

          * skip: simply skip existing followers, do not touch them;
          * force: update existing with given subtypes only;
          * replace: replace existing with new subtypes (like force without old / new follower);
          * update: gives an update dict allowing to add missing subtypes (no subtype removal);
        """
        _res_ids = res_ids or [0]
        data_fols, doc_pids = dict(), dict((i, set()) for i in _res_ids)

        if check_existing and res_ids:
            for fid, rid, pid, sids in self._get_subscription_data([(res_model, res_ids)], partner_ids or None):
                if existing_policy != 'force':
                    if pid:
                        doc_pids[rid].add(pid)
                data_fols[fid] = (rid, pid, sids)

            if existing_policy == 'force':
                self.sudo().browse(data_fols.keys()).unlink()

        new, update = dict(), dict()
        for res_id in _res_ids:
            for partner_id in set(partner_ids or []):
                if partner_id not in doc_pids[res_id]:
                    new.setdefault(res_id, list()).append({
                        'res_model': res_model,
                        'partner_id': partner_id,
                        'subtype_ids': [Command.set(subtypes[partner_id])],
                    })
                elif existing_policy in ('replace', 'update'):
                    fol_id, sids = next(((key, val[2]) for key, val in data_fols.items() if val[0] == res_id and val[1] == partner_id), (False, []))
                    new_sids = set(subtypes[partner_id]) - set(sids)
                    old_sids = set(sids) - set(subtypes[partner_id])
                    update_cmd = []
                    if fol_id and new_sids:
                        update_cmd += [Command.link(sid) for sid in new_sids]
                    if fol_id and old_sids and existing_policy == 'replace':
                        update_cmd += [Command.unlink(sid) for sid in old_sids]
                    if update_cmd:
                        update[fol_id] = {'subtype_ids': update_cmd}

        return new, update
