import os
import json
from dotenv import load_dotenv
import razorpay

# Load environment variables from .env
load_dotenv()

KEY_ID = os.getenv("RAZORPAY_KEY_ID")
KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

if not KEY_ID or not KEY_SECRET:
    raise ValueError("Razorpay keys not found. Make sure .env file is correctly set up.")

# Create Razorpay client (automatically uses test mode if keys are test_*)
client = razorpay.Client(auth=(KEY_ID, KEY_SECRET))

def fetch_data():
    # Fetch last 10 transactions (payments)
    transactions = client.payment.all({"count": 10})
    
    # Fetch last 5 settlements
    settlements = client.settlement.all({"count": 5})
    
    # Save to JSON files for later use
    with open("transactions.json", "w") as f:
        json.dump(transactions, f, indent=2)
    
    with open("settlements.json", "w") as f:
        json.dump(settlements, f, indent=2)
    
    print("✅ Data fetched and saved.")
    print(f"   Transactions saved: {len(transactions.get('items', []))}")
    print(f"   Settlements saved: {len(settlements.get('items', []))}")

if __name__ == "__main__":
    fetch_data()