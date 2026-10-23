import os
import requests

TG_TOKEN = "8905260026:AAHXExujNUHsGbGbldHiESGETsk-OMTXc0w"
TG_CHAT_ID = "945498377"

def send_telegram(text):
    if not (TG_TOKEN and TG_CHAT_ID):
        print("Missing credentials.")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    resp = requests.post(url, data={"chat_id": TG_CHAT_ID, "text": text}, timeout=10)
    print("Telegram Response:", resp.status_code, resp.text)

if __name__ == "__main__":
    print("Sending test message...")
    send_telegram("🔔 SUCCESS! Your Nifty Scanner cloud connection is working perfectly.")
    
