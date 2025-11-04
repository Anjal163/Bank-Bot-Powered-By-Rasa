from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from pymongo import MongoClient

class ActionShowTransactions(Action):

    def name(self) -> str:
        return "action_show_recent_transactions"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: dict):

        # Connect to MongoDB
        client = MongoClient("mongodb://localhost:27017/")
        db = client["Bankbot"]
        transactions = db["transactions"]

        # Get account number (you can modify this to extract from slot)
        account_number = "12345678"

        # Fetch last 3 transactions
        recent_txns = list(transactions.find(
            {"account_number": account_number}
        ).sort("date", -1).limit(3))

        if not recent_txns:
            dispatcher.utter_message(text="No recent transactions found.")
            return []

        # Format the reply
        reply = "Here are your recent transactions:\n"
        for txn in recent_txns:
            reply += f"- {txn['date']}: {txn['description']} ₹{txn['amount']}\n"

        dispatcher.utter_message(text=reply)
        return []
