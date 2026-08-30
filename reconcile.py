import json
import csv

import config


def inr(paise):
    return f"₹{paise/100:.2f}"


def run_reconciliation(transactions_file=None, settlements_file=None, orders_file=None):
    """
    Run reconciliation and return results dict.
    results = {
        'matched': [ ... ],
        'flags': [ ... ]
    }
    Defaults to config.py paths if not explicitly provided (e.g. by an upload route).
    """
    transactions_file = transactions_file or config.TRANSACTIONS_FILE
    settlements_file = settlements_file or config.SETTLEMENTS_FILE
    orders_file = orders_file or config.ORDERS_FILE

    with open(transactions_file, 'r') as f:
        transactions_data = json.load(f)
    transactions = transactions_data.get('items', [])

    with open(settlements_file, 'r') as f:
        settlements_data = json.load(f)
    settlements = settlements_data.get('items', [])

    merchant_orders = []
    with open(orders_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            merchant_orders.append(row)

    transactions_by_id = {t['id']: t for t in transactions}
    transactions_by_order = {t.get('order_id'): t for t in transactions if t.get('order_id')}

    settlement_transactions = []
    for s in settlements:
        for tx_id in s.get('transactions', []):
            settlement_transactions.append({
                'settlement_id': s['id'],
                'transaction_id': tx_id,
                'settlement_amount': s['amount']
            })

    results = {'matched': [], 'flags': []}

    for order in merchant_orders:
        order_id = order['order_id']
        order_amount = int(order['amount'])
        tx = transactions_by_order.get(order_id)

        if not tx:
            results['flags'].append({
                'type': 'ORPHAN_ORDER',
                'order_id': order_id,
                'message': f"Order {order_id} ({inr(order_amount)}) has no corresponding Razorpay payment."
            })
            continue

        tx_id = tx['id']
        tx_amount = tx['amount']
        matching_settlements = [s for s in settlement_transactions if s['transaction_id'] == tx_id]

        if len(matching_settlements) == 0:
            results['flags'].append({
                'type': 'PAYMENT_NOT_SETTLED',
                'order_id': order_id,
                'transaction_id': tx_id,
                'message': f"Payment {tx_id} for order {order_id} ({inr(tx_amount)}) was captured but not found in any settlement."
            })
        elif len(matching_settlements) > 1:
            results['flags'].append({
                'type': 'DUPLICATE_SETTLEMENT',
                'order_id': order_id,
                'transaction_id': tx_id,
                'message': f"Payment {tx_id} for order {order_id} appears in {len(matching_settlements)} settlements (possible duplicate credit)."
            })
        else:
            settlement = matching_settlements[0]
            settlement_amount = settlement['settlement_amount']
            if tx_amount != settlement_amount:
                results['flags'].append({
                    'type': 'AMOUNT_MISMATCH',
                    'order_id': order_id,
                    'transaction_id': tx_id,
                    'message': f"Payment {tx_id} was {inr(tx_amount)} but settled as {inr(settlement_amount)}. Difference: {inr(tx_amount - settlement_amount)} (fee or error)."
                })
            else:
                results['matched'].append({
                    'order_id': order_id,
                    'transaction_id': tx_id,
                    'amount': tx_amount
                })

    for tx in transactions:
        if tx.get('order_id') not in [o['order_id'] for o in merchant_orders]:
            results['flags'].append({
                'type': 'PAYMENT_WITHOUT_ORDER',
                'order_id': tx.get('order_id'),
                'transaction_id': tx['id'],
                'message': f"Payment {tx['id']} ({inr(tx['amount'])}) has no matching order record from merchant."
            })

    known_tx_ids = set(transactions_by_id.keys())
    for s in settlement_transactions:
        if s['transaction_id'] not in known_tx_ids:
            results['flags'].append({
                'type': 'UNKNOWN_SETTLEMENT_TRANSACTION',
                'settlement_id': s['settlement_id'],
                'transaction_id': s['transaction_id'],
                'message': f"Settlement {s['settlement_id']} references unknown transaction {s['transaction_id']}."
            })

    return results


if __name__ == "__main__":
    results = run_reconciliation()
    with open(config.RAW_REPORT_FILE, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"Report saved to {config.RAW_REPORT_FILE}")
