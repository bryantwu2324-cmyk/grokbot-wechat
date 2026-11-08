"""Who may cross the bridge. The default is deny."""

def _text(value):
    if value is None:
        return ""
    return str(value).strip()


def classify(message, owner_id, bot_id):
    """Return (decision, reason). decision is 'accept' or 'reject'.

    Accept only a direct user message from the account that scanned the QR.
    Groups and every other sender are rejected. No field here is logged by
    the caller except the reason and the message id.
    """
    if not isinstance(message, dict):
        return "reject", "not-an-object"
    if message.get("message_type") != 1:
        return "reject", "not-user-message"
    if _text(message.get("group_id")):
        return "reject", "group"
    owner_id = _text(owner_id)
    sender = _text(message.get("from_user_id"))
    if not owner_id or sender != owner_id:
        return "reject", "not-owner"
    bot_id = _text(bot_id)
    recipient = _text(message.get("to_user_id"))
    if not bot_id:
        return "reject", "bot-id-missing"
    if recipient and recipient != bot_id:
        return "reject", "unexpected-recipient"
    return "accept", "owner"
