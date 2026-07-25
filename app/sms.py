import threading

import requests


def _send_sync(twilio_config, message_text, recipient_phones):
    """Runs in a background thread. Never raises — a Twilio problem should
    never surface as an error to whoever just posted an urgent update."""
    if not recipient_phones:
        return

    account_sid = twilio_config.get("account_sid")
    auth_token = twilio_config.get("auth_token")
    from_number = twilio_config.get("from_number")

    if not (account_sid and auth_token and from_number):
        print("[sms] Twilio is not configured — skipping send. Set TWILIO_ACCOUNT_SID/AUTH_TOKEN/FROM_NUMBER in .env to enable texts.")
        return

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

    # Twilio's API sends one message per call (no BCC-style bulk endpoint),
    # so this loops per recipient. A failure on one number doesn't stop the rest.
    for phone in recipient_phones:
        try:
            resp = requests.post(
                url,
                data={"To": phone, "From": from_number, "Body": message_text},
                auth=(account_sid, auth_token),
                timeout=10,
            )
            if resp.status_code >= 300:
                print(f"[sms] Twilio rejected message to {phone}: {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            print(f"[sms] Failed to send text to {phone}: {e}")


def send_urgent_sms_async(twilio_config, message_text, recipient_phones):
    """Fire-and-forget: send urgent SMS alerts in a background thread so
    posting an update never waits on, or fails because of, Twilio."""
    if not recipient_phones:
        return
    thread = threading.Thread(
        target=_send_sync,
        args=(twilio_config, message_text, recipient_phones),
        daemon=True,
    )
    thread.start()
