# coding: utf-8

import json
import logging

import dateutil.parser
import pytz
from werkzeug import urls

from odoo import api, fields, models, _
from odoo.addons.payment.models.payment_acquirer import ValidationError
from odoo.addons.payment_payfast.controllers.main import PayFastController
from odoo.tools.float_utils import float_compare


# from payfast.forms import PayFastForm

_logger = logging.getLogger(__name__)


class AcquirerPayfast(models.Model):
    _inherit = 'payment.acquirer'

    payfast_merchant_id = fields.Char('Merchant ID')
    payfast_merchant_key = fields.Char('Merchant KEY')
    payfast_merchant_url = fields.Char('Merchant URL')

    provider = fields.Selection(selection_add=[('payfast', 'PayFast')])

    def _get_feature_support(self):
        """Get advanced feature support by provider.

        Each provider should add its technical in the corresponding
        key for the following features:
            * fees: support payment fees computations
            * authorize: support authorizing payment (separates
                         authorization and capture)
            * tokenize: support saving payment data in a payment.tokenize
                        object
        """
        res = super(AcquirerPayfast, self)._get_feature_support()
        res['fees'].append('payfast')
        return res

    @api.model
    def _get_payfast_urls(self, environment):
        """ Paypal URLS """
        return self.payfast_merchant_url

    @api.multi
    def payfast_compute_fees(self, amount, currency_id, country_id):
        """ Compute paypal fees.

            :param float amount: the amount to pay
            :param integer country_id: an ID of a res.country, or None. This is
                                       the customer's country, to be compared to
                                       the acquirer company country.
            :return float fees: computed fees
        """
        if not self.fees_active:
            return 0.0
        country = self.env['res.country'].browse(country_id)
        if country and self.company_id.country_id.id == country.id:
            percentage = self.fees_dom_var
            fixed = self.fees_dom_fixed
        else:
            percentage = self.fees_int_var
            fixed = self.fees_int_fixed
        fees = (percentage / 100.0 * amount + fixed) / (1 - percentage / 100.0)
        return fees

    @api.multi
    def payfast_form_generate_values(self, values):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')

        payfast_tx_values = dict(values)
        payfast_tx_values.update({
            'm_payment_id': values['reference'],
            'merchant_id': self.payfast_merchant_id,
            "merchant_key": self.payfast_merchant_key,
            'item_name': '%s: %s' % (self.company_id.name, values['reference']),
            'item_number': values['reference'],
            'amount': values['amount'],
            'currency_code': values['currency'] and values['currency'].name or '',
            'address1': values.get('partner_address'),
            'city': values.get('partner_city'),
            'country': values.get('partner_country') and values.get('partner_country').code or '',
            'state': values.get('partner_state') and (values.get('partner_state').code or values.get('partner_state').name) or '',
            'email': values.get('partner_email'),
            'zip_code': values.get('partner_zip'),
            'first_name': values.get('partner_first_name'),
            'last_name': values.get('partner_last_name'),
            'return_url': urls.url_join(base_url, PayFastController._return_url),
            'notify_url': urls.url_join(base_url, PayFastController._notify_url),
            'cancel_url': urls.url_join(base_url, PayFastController._cancel_url)
        })
        return payfast_tx_values


    @api.multi
    def payfast_get_form_action_url(self):
        return self._get_payfast_urls(self.environment)


class TxPayFast(models.Model):
    _inherit = 'payment.transaction'

    # paypal_txn_type = fields.Char('Transaction type')

    # --------------------------------------------------
    # FORM RELATED METHODS
    # --------------------------------------------------

    @api.model
    def _payfast_form_get_tx_from_data(self, data):
        """

        :param data:
        :return:
        """
        reference, txn_id = data.get('m_payment_id'), data.get('txn_id','test')
        if not reference or not txn_id:
            error_msg = _('PayFast: received data with missing reference (%s) or txn_id (%s)') % (reference, txn_id)
            _logger.info(error_msg)
            raise ValidationError(error_msg)
        #
        # # find tx -> @TDENOTE use txn_id ?
        txs = self.env['payment.transaction'].search([('reference', '=', reference)])
        if not txs or len(txs) > 1:
            error_msg = 'PayFast: received data for reference %s' % (reference)
            if not txs:
                error_msg += '; no order found'
            else:
                error_msg += '; multiple order found'
            _logger.info(error_msg)
            raise ValidationError(error_msg)
        return txs[0]

    @api.multi
    def _payfast_form_get_invalid_parameters(self, data):
        invalid_parameters = []
        _logger.info('Received a notification from Paypal with IPN version %s', data.get('notify_version'))
        if data.get('test_ipn'):
            _logger.warning(
                'Received a notification from Paypal using sandbox'
            ),

        return invalid_parameters

    @api.multi
    def _payfast_form_validate(self, data):
        status = data.get('payment_status')
        res = {
            'acquirer_reference': data.get('pf_payment_id'),
            # 'fees': data.get('amount_fee'),
        }
        if status in ['COMPLETE', 'Processed']:
            _logger.info('Validated Paypal payment for tx %s: set as done' % (self.reference))
            try:
                # dateutil and pytz don't recognize abbreviations PDT/PST
                tzinfos = {
                    'PST': -8 * 3600,
                    'PDT': -7 * 3600,
                }
                date = dateutil.parser.parse(data.get('payment_date'), tzinfos=tzinfos).astimezone(pytz.utc)
            except:
                date = fields.Datetime.now()
            res.update(date=date)
            self._set_transaction_done()
            return self.write(res)
        elif status in ['Pending', 'Expired']:
            _logger.info('Received notification for Paypal payment %s: set as pending' % (self.reference))
            res.update(state_message=data.get('pending_reason', ''))
            self._set_transaction_pending()
            return self.write(res)
        else:
            error = 'Received unrecognized status for Paypal payment %s: %s, set as error' % (self.reference, status)
            _logger.info(error)
            res.update(state_message=error)
            self._set_transaction_cancel()
            return self.write(res)
