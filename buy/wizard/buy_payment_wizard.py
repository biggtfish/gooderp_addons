# -*- coding: utf-8 -*-

from datetime import date
from odoo import models, fields, api
from odoo.exceptions import UserError


class buy_payment_wizard(models.TransientModel):
    _name = 'buy.payment.wizard'
    _description = u'采购付款一览表向导'

    @api.model
    def _default_date_start(self):
        return self.env.user.company_id.start_date

    @api.model
    def _default_date_end(self):
        return date.today()

    date_start = fields.Date(u'开始日期', default=_default_date_start,
                             help=u'报表汇总的开始日期，默认为公司启用日期')
    date_end = fields.Date(u'结束日期', default=_default_date_end,
                             help=u'报表汇总的结束日期，默认为当前日期')
    s_category_id = fields.Many2one('core.category', u'供应商类别',
                             help=u'按指定供应商类别进行统计')
    partner_id = fields.Many2one('partner', u'供应商',
                             help=u'按指定供应商进行统计')
    order_id = fields.Many2one('buy.receipt', u'采购单号',
                             help=u'按指定采购单号进行统计')
    warehouse_dest_id = fields.Many2one('warehouse', u'仓库',
                             help=u'按指定仓库进行统计')

    def _get_domain(self):
        '''返回wizard界面上条件'''
        cond = [('date', '>=', self.date_start),
                ('date', '<=', self.date_end),
                ('state', '=', 'done')]
        if self.s_category_id:
            cond.append(
                ('partner_id.s_category_id', '=', self.s_category_id.id)
            )
        if self.partner_id:
            cond.append(('partner_id', '=', self.partner_id.id))
        if self.order_id:
            cond.append(('id', '=', self.order_id.id))
        if self.warehouse_dest_id:
            cond += ['|',('buy_move_id.warehouse_dest_id', '=', self.warehouse_dest_id.id),
                     ('buy_move_id.warehouse_id', '=', self.warehouse_dest_id.id)]
        return cond

    def _compute_payment(self, receipt):
        '''计算该入库单的已付款和应付款余额'''
        payment = 0
        for order in self.env['money.order'].search(
                    [('state', '=', 'done')], order='name'):
            for source in order.source_ids:
                if source.name.name == receipt.name:
                    payment += source.this_reconcile
        return payment

    def _compute_payment_rate(self, payment, amount):
        '''计算付款率'''
        payment_rate = amount != 0 and (payment / amount) * 100 or 0.0
        return payment_rate

    def _prepare_buy_payment(self, receipt):
        '''对于传入的入库单，为创建采购付款一览表准备数据'''
        self.ensure_one()
        factor = not receipt.is_return and 1 or -1 # 如果是退货则金额均取反
        purchase_amount = factor * (receipt.discount_amount + receipt.amount)
        discount_amount = factor * receipt.discount_amount
        amount = factor * receipt.amount
        order_type = receipt.is_return and u'采购退回' or u'普通采购'
        warehouse = receipt.is_return and receipt.warehouse_id or receipt.warehouse_dest_id
        # 计算该入库单的已付款
        payment = self._compute_payment(receipt)
        return {
            'partner_id': receipt.partner_id.id,
            'type': order_type,
            'date': receipt.date,
            'warehouse_dest_id': warehouse.id,
            'order_name': receipt.name,
            'purchase_amount': purchase_amount,
            'discount_amount': discount_amount,
            'amount': amount,
            'payment': payment,
            'balance': amount - payment,
            'payment_rate': self._compute_payment_rate(payment, amount),
            'note': receipt.note,
        }

    @api.multi
    def button_ok(self):
        res = []
        if self.date_end < self.date_start:
            raise UserError(u'开始日期不能大于结束日期！')

        receipt_obj = self.env['buy.receipt']
        count = sum_payment_rate = 0    # 行数及所有行的付款率之和
        for receipt in receipt_obj.search(self._get_domain(), order='partner_id,date'):
            # 用查找到的入库单信息来创建一览表
            line = self.env['buy.payment'].create(self._prepare_buy_payment(receipt))
            res.append(line.id)
            count += 1
            sum_payment_rate += line.payment_rate

        # 创建一览表的平均付款率行
        payment_rate = count != 0 and sum_payment_rate / count or 0
        line_total = self.env['buy.payment'].create({
            'order_name': u'平均付款率',
            'payment_rate': payment_rate,
        })
        res.append(line_total.id)
        return {
            'name': u'采购付款一览表',
            'view_mode': 'tree',
            'res_model': 'buy.payment',
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', res)],
            'limit': 65535,
        }
