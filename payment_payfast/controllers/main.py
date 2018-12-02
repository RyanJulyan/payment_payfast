# -*- coding: utf-8 -*-

import json
import logging
import pprint

import requests
import werkzeug
from werkzeug import urls

from odoo import http

from odoo.addons.payment.models.payment_acquirer import ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)


class PayFastController(http.Controller):
    _notify_url = '/notify_url'
    _return_url = '/return_url'
    _cancel_url = '/cancel_url'

    @http.route('/notify_url',  type='http', website=True, auth="public", csrf=False)
    def payfast_idp(self, **post):
        """ Paypal IPN. """
        _logger.info('PAY Fast post data %s', pprint.pformat(post))  # debug
        try:
            # post = {'amount_fee': '-1177.65',
            #  'amount_gross': '51201.95',
            #  'amount_net': '50024.30',
            #  'custom_int1': '',
            #  'custom_int2': '',
            #  'custom_int3': '',
            #  'custom_int4': '',
            #  'custom_int5': '',
            #  'custom_str1': '',
            #  'custom_str2': '',
            #  'custom_str3': '',
            #  'custom_str4': '',
            #  'custom_str5': '',
            #  'email_address': '',
            #  'item_description': '',
            #  'item_name': 'YourCompany: SO037-1',
            #  'm_payment_id': 'SO036-8',
            #  'merchant_id': '10011040',
            #  'name_first': '',
            #  'name_last': '',
            #  'payment_status': 'COMPLETE',
            #  'pf_payment_id': '708444',
            #  'signature': 'a7b3eb1a24563e46974f25ab8aa666b3'}

            request.env['payment.transaction'].sudo().form_feedback(post, 'payfast')
        except ValidationError:
            _logger.exception('Unable to validate the Paypal payment')

    @http.route('/return_url', auth="public", type="http", csrf=False)
    def payfast_return(self, **post):
        """ PayFast return """
        _logger.info('Bening Paypal DPN form_feedback with post data %s', pprint.pformat(post))
        return werkzeug.utils.redirect('/payment/process')

    @http.route('/cancel_url', type='http', auth="public", csrf=False)
    def payfast_cancel(self, **post):
        """ When the user cancels its PayFast payment: GET on this route """
        _logger.info('Beginning Paypal cancel with post data %s', pprint.pformat(post))  # debug
        return werkzeug.utils.redirect('/payment/process')
