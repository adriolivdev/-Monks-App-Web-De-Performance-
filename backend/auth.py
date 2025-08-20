# backend/auth.py
def authenticate(users_dict, username_or_email, password):
    """
    users_dict: { "user1": {"password": "xxx", "role": "admin"}, ... }
    """
    user = users_dict.get(username_or_email)
    if not user:
        return None
    if user.get("password") != password:
        return None
    return user

def get_current_user(session_obj):
    return session_obj.get("user")

def logout_user(session_obj):
    session_obj.clear()
