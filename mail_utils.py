from mailjet_rest import Client
import os
from dotenv import load_dotenv


load_dotenv()
API_KEY = os.environ['MJ_APIKEY_PUBLIC']
API_SECRET = os.environ['MJ_APIKEY_PRIVATE']

FROM = 'khanmustafakhan690@gmail.com'
TO = 'noxyra90@gmail.com'

mailjet = Client(auth=(API_KEY, API_SECRET), version="v3.1")

def send_mail(heading: str, message: str) -> bool:
    if not API_KEY or not API_SECRET or not FROM or not TO:
        print("Mail config missing — skipping email")
        return False

    data = {
        "Messages": [
            {
                "From": {"Email": FROM, "Name": "System Alert"},
                "To": [{"Email": TO, "Name": "Exception"}],
                "Subject": heading[:255],  # Mailjet limit safety
                "TextPart": message[:5000] # avoid payload rejection
            }
        ]
    }

    try:
        result = mailjet.send.create(data=data)
    except Exception as e:
        print(f"Mailjet exception: {e}")
        return False

    if result.status_code != 200:
        print(f"Mailjet HTTP error: {result.status_code}")
        return False

    resp = result.json()
    status = resp["Messages"][0].get("Status")

    if status != "success":
        print(f"Mailjet send failed: {resp}")
        return False

    return True

if __name__ == "__main__":
    send_mail("Exception in E", "This message is for testing purpose.")
     