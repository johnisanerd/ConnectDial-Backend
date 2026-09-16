# notifications/utils.py
from firebase_admin import messaging

from connectdial.firebase_admin import get_firebase_app


def send_fcm_notification(token, title, body):
    """Send a message to a specific device via FCM."""
    get_firebase_app()

    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        token=token,
        android=messaging.AndroidConfig(
            priority='high',
            notification=messaging.AndroidNotification(
                channel_id='default_channel_id',
                click_action='OPEN_NOTIF_ACTIVITY',
            ),
        ),
    )

    try:
        return messaging.send(message)
    except Exception as exc:
        print(f"❌ Firebase Error: {exc}")
        return None
