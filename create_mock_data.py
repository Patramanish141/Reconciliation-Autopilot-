import json
import csv

import config

# ------------------------------------------------------------
# 1. Mock Razorpay Transactions (payments)
# ------------------------------------------------------------
transactions = {
    "items": [
        {"id": "pay_101", "amount": 499900, "status": "captured", "created_at": 1690000000,
         "order_id": "ord_1001", "email": "customer1@example.com", "method": "upi"},
        {"id": "pay_102", "amount": 150000, "status": "captured", "created_at": 1690003600,
         "order_id": "ord_1002", "email": "customer2@example.com", "method": "card"},
        {"id": "pay_103", "amount": 89900, "status": "captured", "created_at": 1690007200,
         "order_id": "ord_1003", "email": "customer3@example.com", "method": "netbanking"},
        {"id": "pay_104", "amount": 200000, "status": "captured", "created_at": 1690010800,
         "order_id": "ord_1004", "email": "customer4@example.com", "method": "wallet"},
        {"id": "pay_105", "amount": 39900, "status": "captured", "created_at": 1690014400,
         "order_id": "ord_1005", "email": "customer5@example.com", "method": "upi"}
    ]
}

# ------------------------------------------------------------
# 2. Mock Razorpay Settlements (deliberate mismatches for demo)
# ------------------------------------------------------------
settlements = {
    "items": [
        {"id": "setl_2001", "amount": 487900, "created_at": 1690020000, "status": "processed",
         "transactions": ["pay_101"]},
        {"id": "setl_2002", "amount": 150000, "created_at": 1690023600, "status": "processed",
         "transactions": ["pay_102"]},
        {"id": "setl_2003", "amount": 89900, "created_at": 1690027200, "status": "processed",
         "transactions": ["pay_103"]},
        {"id": "setl_2004", "amount": 39900, "created_at": 1690030800, "status": "processed",
         "transactions": ["pay_105"]},
        {"id": "setl_2005", "amount": 39900, "created_at": 1690034400, "status": "processed",
         "transactions": ["pay_105"]}
    ]
}

# ------------------------------------------------------------
# 3. Mock Merchant Internal Orders (CSV)
# ------------------------------------------------------------
merchant_orders = [
    {"order_id": "ord_1001", "amount": 499900, "email": "customer1@example.com", "order_date": "2024-07-01"},
    {"order_id": "ord_1002", "amount": 150000, "email": "customer2@example.com", "order_date": "2024-07-02"},
    {"order_id": "ord_1003", "amount": 89900, "email": "customer3@example.com", "order_date": "2024-07-03"},
    {"order_id": "ord_1004", "amount": 200000, "email": "customer4@example.com", "order_date": "2024-07-04"},
    {"order_id": "ord_1005", "amount": 39900, "email": "customer5@example.com", "order_date": "2024-07-05"},
    {"order_id": "ord_1006", "amount": 120000, "email": "customer6@example.com", "order_date": "2024-07-06"}
]

def main():
    with open(config.TRANSACTIONS_FILE, "w") as f:
        json.dump(transactions, f, indent=2)

    with open(config.SETTLEMENTS_FILE, "w") as f:
        json.dump(settlements, f, indent=2)

    with open(config.ORDERS_FILE, "w", newline="") as f:
        fieldnames = ["order_id", "amount", "email", "order_date"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for order in merchant_orders:
            writer.writerow(order)

    print("Mock data created successfully.")
    print(f"   - {config.TRANSACTIONS_FILE} (5 payments)")
    print(f"   - {config.SETTLEMENTS_FILE} (5 settlements)")
    print(f"   - {config.ORDERS_FILE} (6 orders)")

if __name__ == "__main__":
    main()
