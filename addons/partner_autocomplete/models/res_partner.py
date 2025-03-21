# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import json
import logging
import requests
import re

from stdnum.eu.vat import check_vies

from odoo import api, fields, models, tools, _

_logger = logging.getLogger(__name__)

PARTNER_AC_TIMEOUT = 5


class ResPartner(models.Model):
    _name = 'res.partner'
    _inherit = 'res.partner'

    partner_gid = fields.Integer('Company database ID')
    additional_info = fields.Char('Additional info')

    @api.model
    def _iap_replace_location_codes(self, iap_data):
        country_code, country_name = iap_data.pop('country_code', False), iap_data.pop('country_name', False)
        state_code, state_name = iap_data.pop('state_code', False), iap_data.pop('state_name', False)

        country, state = None, None
        if country_code:
            country = self.env['res.country'].search([['code', '=ilike', country_code]])
        if not country and country_name:
            country = self.env['res.country'].search([['name', '=ilike', country_name]])

        if country:
            if state_code:
                state = self.env['res.country.state'].search([
                    ('country_id', '=', country.id), ('code', '=ilike', state_code)
                ], limit=1)
            if not state and state_name:
                state = self.env['res.country.state'].search([
                    ('country_id', '=', country.id), ('name', '=ilike', state_name)
                ], limit=1)
        else:
            _logger.info('Country code not found: %s', country_code)

        if country:
            iap_data['country_id'] = {'id': country.id, 'display_name': country.display_name}
        if state:
            iap_data['state_id'] = {'id': state.id, 'display_name': state.display_name}

        return iap_data

    @api.model
    def _iap_replace_logo(self, iap_data):
        if iap_data.get('logo'):
            try:
                iap_data['image_1920'] = base64.b64encode(
                    requests.get(iap_data['logo'], timeout=PARTNER_AC_TIMEOUT).content
                )
            except Exception:
                iap_data['image_1920'] = False
            finally:
                iap_data.pop('logo')
            # avoid keeping falsy images (may happen that a blank page is returned that leads to an incorrect image)
            if iap_data['image_1920']:
                try:
                    tools.base64_to_image(iap_data['image_1920'])
                except Exception:
                    iap_data.pop('image_1920')
        return iap_data

    @api.model
    def _format_data_company(self, iap_data):
        self._iap_replace_location_codes(iap_data)

        if iap_data.get('child_ids'):
            child_ids = []
            for child in iap_data.get('child_ids'):
                child_ids.append(self._iap_replace_location_codes(child))
            iap_data['child_ids'] = child_ids

        if iap_data.get('additional_info'):
            iap_data['additional_info'] = json.dumps(iap_data['additional_info'])

        return iap_data

    @api.model
    def autocomplete(self, query, timeout=15):
        suggestions, _ = self.env['iap.autocomplete.api']._request_partner_autocomplete('search', {
            'query': query,
        }, timeout=timeout)
        if suggestions:
            results = []
            for suggestion in suggestions:
                results.append(self._format_data_company(suggestion))
            return results
        else:
            return []

    @api.model
    def enrich_company(self, company_domain, partner_gid, vat, timeout=15):
        response, error = self.env['iap.autocomplete.api']._request_partner_autocomplete('enrich', {
            'domain': company_domain,
            'partner_gid': partner_gid,
            'vat': vat,
        }, timeout=timeout)
        if response and response.get('company_data'):
            result = self._format_data_company(response.get('company_data'))
        else:
            result = {}

        if response and response.get('credit_error'):
            result.update({
                'error': True,
                'error_message': 'Insufficient Credit'
            })
        elif error:
            result.update({
                'error': True,
                'error_message': error
            })

        return result

    @api.model
    def read_by_vat(self, vat, timeout=15):
        vies_vat_data, _ = self.env['iap.autocomplete.api']._request_partner_autocomplete('search_vat', {
            'vat': vat,
        }, timeout=timeout)
        if vies_vat_data:
            return [self._format_data_company(vies_vat_data)]
        else:
            vies_result = None
            try:
                vies_result = check_vies(vat)
            except Exception:
                _logger.exception("Failed VIES VAT check.")
            if vies_result:
                name = vies_result['name']
                if vies_result['valid'] and name != '---':
                    address = list(filter(bool, vies_result['address'].split('\n')))
                    street = address[0]
                    zip_city_record = next(filter(lambda addr: re.match(r'^\d.*', addr), address[1:]), None)
                    zip_city = zip_city_record.split(' ', 1) if zip_city_record else [None, None]
                    street2 = next((addr for addr in filter(lambda addr: addr != zip_city_record, address[1:])), None)
                    return [self._iap_replace_location_codes({
                        'name': name,
                        'vat': vat,
                        'street': street,
                        'street2': street2,
                        'city': zip_city[1],
                        'zip': zip_city[0],
                        'country_code': vies_result['countryCode'],
                        'skip_enrich': True,
                    })]
            return []

    @api.model
    def _is_company_in_europe(self, country_code):
        country = self.env['res.country'].search([('code', '=ilike', country_code)])
        if country:
            country_id = country.id
            europe = self.env.ref('base.europe')
            if not europe:
                europe = self.env["res.country.group"].search([('name', '=', 'Europe')], limit=1)
            if not europe or country_id not in europe.country_ids.ids:
                return False
        return True

    def _is_vat_syncable(self, vat):
        vat_country_code = vat[:2]
        partner_country_code = self.country_id.code if self.country_id else ''
        return self._is_company_in_europe(vat_country_code) and (partner_country_code == vat_country_code or not partner_country_code)

    def _is_synchable(self):
        already_synched = self.env['res.partner.autocomplete.sync'].search([('partner_id', '=', self.id), ('synched', '=', True)])
        return self.is_company and self.partner_gid and not already_synched

    def _update_autocomplete_data(self, vat):
        self.ensure_one()
        if vat and self._is_synchable() and self._is_vat_syncable(vat):
            self.env['res.partner.autocomplete.sync'].sudo().add_to_queue(self.id)

    @api.model_create_multi
    def create(self, vals_list):
        partners = super(ResPartner, self).create(vals_list)
        if len(vals_list) == 1:
            partners._update_autocomplete_data(vals_list[0].get('vat', False))
            if partners.additional_info:
                template_values = json.loads(partners.additional_info)
                template_values['flavor_text'] = _("Partner created by Odoo Partner Autocomplete Service")
                partners.message_post_with_view(
                    'iap_mail.enrich_company',
                    values=template_values,
                    subtype_id=self.env.ref('mail.mt_note').id,
                )
                partners.write({'additional_info': False})

        return partners

    def write(self, values):
        res = super(ResPartner, self).write(values)
        if len(self) == 1:
            self._update_autocomplete_data(values.get('vat', False))

        return res
