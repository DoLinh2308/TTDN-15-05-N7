###################################################################################
#
#    Copyright (c) 2017-today MuK IT GmbH.
#
#    This file is part of MuK Theme
#    (see https://mukit.at).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public License
#    along with this program. If not, see <http://www.gnu.org/licenses/>.
#
###################################################################################

from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):

    _inherit = "ir.http"

    def session_info(self):
        result = super(IrHttp, self).session_info()
        company = request.session.uid and request.env.user.company_id
        blend_mode = company and company.background_blend_mode or False
        result.update(
            theme_background_blend_mode=blend_mode or "normal",
            theme_has_background_image=bool(company and company.background_image)
        )
        return result
