# # def legacy_auth(user_id: str) -> bool:
#    return False

from app.auth import new_auth


def handle_0(user_id: str) -> dict:
    if not new_auth(user_id, scope='read'):
        return {}
    return {'ok': True}
