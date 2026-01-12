import requests


# البيانات دي هتجيبها من: Meta for Developers -> App Settings -> Basic

APP_ID = "3852282268409989"

APP_SECRET = "5a9efbccdafb60cc439917efa545f019"


# التوكن القصير اللي لسه جايبه من الخطوة 2 (اللي كان جوه JSON)

SHORT_PAGE_TOKEN = "EAA2voVwu4IUBQSDqZA4P9WZCdD1iEulBQRn0pvXokyAXs4WZCz7TgPtflO6vbwJWBnmEdZCBDw4oUNty64OLd4hZClryJ2KvTE8Lpt3FcLm2DMFXlj56NRXOCHs06rHrPQ6bqx1znYZBF3MZA38fNddnGddDif1vYrhdDv93EgHHCNJqiDjFWvtkKgObtb9ZCiJ6wIu1PqhkJPuZASR1iCnB5FJcruudHR8tySYbaOZCPAHlMKpIvHr58tFFOjZATEZD"


def extend_token():

    url = (
        f"https://graph.facebook.com/v18.0/oauth/access_token?"
        f"grant_type=fb_exchange_token&"
        f"client_id={APP_ID}&"
        f"client_secret={APP_SECRET}&"
        f"fb_exchange_token={SHORT_PAGE_TOKEN}"
    )

    response = requests.get(url).json()

    if "access_token" in response:

        print("\n✅ مبروك يا كوماندا! ده التوكن الأبدي (60 يوم):")

        print(response["access_token"])

    else:

        print("❌ حصل مشكلة:", response)


if __name__ == "__main__":

    extend_token()
