"""
FIXED Streamlit App with Proper OAuth Flow and Token Refresh

Changes from original:
1. Extract token from URL parameter after OAuth redirect
2. Clear token from URL for security
3. Add automatic token refresh before expiry
4. Proper session state management
5. Better error handling for expired tokens
6. Improved UI/UX

Key Improvements:
- No more reliance on unreliable _get_websocket_headers()
- Token properly extracted from URL parameter
- Automatic refresh prevents forced re-login
- Clean URL after token extraction
"""

import time
from datetime import datetime, timedelta
from typing import Optional

from jose import jwt
import requests
import streamlit as st

# ===== Configuration =====
API_BASE_URL = "http://localhost:7860"
PAGE_TITLE = "IDX Analyst AI"
PAGE_ICON = "📈"

st.set_page_config(
    page_title=PAGE_TITLE, 
    page_icon=PAGE_ICON, 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# ===== Helper Functions =====

def decode_jwt_without_verification(token: str) -> Optional[dict]:
    """
    Decode JWT token without signature verification to check expiry.
    Used only for timing token refresh, not for security validation.
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded token payload or None if invalid
    """
    try:
        # Decode without verification (just to read expiry time)
        return jwt.decode(token, options={"verify_signature": False})
    except Exception:
        return None


def is_token_expiring_soon(token: str, threshold_seconds: int = 60) -> bool:
    """
    Check if token will expire within threshold_seconds.
    
    Args:
        token: JWT token string
        threshold_seconds: Seconds before expiry to consider "expiring soon"
        
    Returns:
        True if token expires within threshold, False otherwise
    """
    payload = decode_jwt_without_verification(token)
    if not payload or "exp" not in payload:
        return True  # Treat invalid tokens as expired
    
    expiry_time = datetime.fromtimestamp(payload["exp"])
    time_until_expiry = expiry_time - datetime.now()
    
    return time_until_expiry.total_seconds() < threshold_seconds


def refresh_access_token(current_token: str) -> Optional[str]:
    """
    Attempt to refresh access token using /auth/refresh endpoint.
    
    Args:
        current_token: Current (potentially expiring) access token
        
    Returns:
        New access token if refresh successful, None otherwise
    """
    try:
        # Use stored refresh token if available
        refresh_token = st.session_state.get("refresh_token")
        
        if not refresh_token:
            st.error("❌ No refresh token available")
            return None

        # Send refresh token as Bearer token (as expected by backend fallback)
        headers = {"Authorization": f"Bearer {refresh_token}"}
        
        response = requests.post(
            f"{API_BASE_URL}/api/v1/auth/refresh",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            new_token = data.get("access_token")
            st.success("✅ Token refreshed successfully")
            return new_token
        else:
            st.warning(f"⚠️ Token refresh failed: {response.status_code}")
            return None
            
    except Exception as e:
        st.error(f"❌ Token refresh error: {e}")
        return None


def get_current_user(token: str) -> Optional[dict]:
    """
    Fetch user info using JWT token.
    
    Args:
        token: JWT access token
        
    Returns:
        User info dict if valid, None otherwise
    """
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(
            f"{API_BASE_URL}/api/v1/auth/me", 
            headers=headers,
            timeout=10
        )
        
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 401:
            st.warning("⚠️ Session expired - attempting to refresh...")
            return None
        else:
            st.error(f"❌ Failed to get user info: {resp.status_code}")
            return None
            
    except Exception as e:
        st.error(f"❌ Connection error: {e}")
        return None


def send_chat_message(prompt: str, token: str) -> Optional[dict]:
    """
    Send chat message to backend and get response.
    
    Args:
        prompt: User's message
        token: JWT access token
        
    Returns:
        Response dict if successful, None otherwise
    """
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        payload = {"messages": prompt}

        with st.spinner("🤖 AI is thinking..."):
            resp = requests.post(
                f"{API_BASE_URL}/api/v1/chat/",
                headers=headers,
                json=payload,
                timeout=600
            )

            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 401:
                st.error("🔒 Session expired. Please refresh or login again.")
                return None
            else:
                st.error(f"❌ Error {resp.status_code}: {resp.text}")
                return None
                
    except requests.exceptions.Timeout:
        st.error("⏱️ Request timed out. Please try again.")
        return None
    except Exception as e:
        st.error(f"❌ Connection error: {e}")
        return None


def logout():
    """
    Logout user by calling backend and clearing session.
    """
    if "jwt_token" in st.session_state and st.session_state["jwt_token"]:
        try:
            # We use access token for logout
            headers = {"Authorization": f"Bearer {st.session_state['jwt_token']}"}
            requests.post(
                f"{API_BASE_URL}/api/v1/auth/logout",
                headers=headers,
                timeout=10
            )
        except Exception as e:
            st.warning(f"⚠️ Logout request failed: {e}")

    # Clear all session state
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    
    st.success("👋 Logged out successfully")
    time.sleep(1)
    st.rerun()


# ===== State Initialization =====

def init_auth_state():
    """
    Initialize authentication state from URL parameter or existing session.
    
    This is the KEY FIX for OAuth flow:
    1. Check URL for 'token' parameter (from OAuth callback)
    2. If found, store in session_state and clear URL
    3. If not found, check if token already in session_state
    4. Validate token and get user info
    5. Check if token needs refresh
    """
    # Initialize session state if not present
    if "messages" not in st.session_state:
        st.session_state["messages"] = []
    
    # ===== STEP 1: Extract token from URL parameter =====
    # This is set by OAuth callback: /callback?token=xxx&refresh_token=yyy
    query_params = st.query_params
    
    if "token" in query_params:
        token = query_params["token"]
        st.session_state["jwt_token"] = token
        
        # Capture refresh token if present
        if "refresh_token" in query_params:
            st.session_state["refresh_token"] = query_params["refresh_token"]
        
        # Clear token from URL for security
        # Prevents token from being visible in browser history
        st.query_params.clear()
        
        st.success("✅ Login successful! Welcome back.")
        time.sleep(1)
        st.rerun()
    
    # ===== STEP 2: Check existing token in session =====
    if "jwt_token" in st.session_state and st.session_state["jwt_token"]:
        token = st.session_state["jwt_token"]
        
        # ===== STEP 3: Check if token needs refresh =====
        if is_token_expiring_soon(token, threshold_seconds=60):
            st.info("🔄 Token expiring soon, refreshing...")
            new_token = refresh_access_token(token)
            
            if new_token:
                st.session_state["jwt_token"] = new_token
                token = new_token
            else:
                st.error("❌ Failed to refresh token. Please login again.")
                logout()
                return
        
        # ===== STEP 4: Get user info if not already loaded =====
        if "user_info" not in st.session_state or not st.session_state["user_info"]:
            user = get_current_user(token)
            
            if user:
                st.session_state["user_info"] = user
            else:
                # Token invalid or expired, try to refresh
                st.warning("⚠️ Token validation failed, attempting refresh...")
                new_token = refresh_access_token(token)
                
                if new_token:
                    st.session_state["jwt_token"] = new_token
                    user = get_current_user(new_token)
                    if user:
                        st.session_state["user_info"] = user
                    else:
                        # Refresh failed, logout
                        st.error("❌ Session expired. Please login again.")
                        logout()
                else:
                    logout()
    else:
        # No token in session, user not logged in
        st.session_state["jwt_token"] = None
        st.session_state["user_info"] = None


# ===== UI Components =====

def render_login_page():
    """
    Render attractive login page with Google OAuth button.
    """
    st.markdown(
        """
        <style>
        .login-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 50px;
            text-align: center;
        }
        .title {
            font-size: 3em;
            font-weight: bold;
            color: #1E3A8A;
            margin-bottom: 20px;
        }
        .subtitle {
            font-size: 1.2em;
            color: #6B7280;
            margin-bottom: 40px;
        }
        .feature-box {
            background: #F3F4F6;
            padding: 20px;
            border-radius: 12px;
            margin: 10px 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.markdown('<div class="login-container">', unsafe_allow_html=True)
        st.markdown(f'<div class="title">{PAGE_ICON} {PAGE_TITLE}</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="subtitle">AI-Powered Indonesian Financial Analyst</div>',
            unsafe_allow_html=True,
        )
        
        # Features
        st.markdown('<div class="feature-box">📊 Analyze financial reports</div>', unsafe_allow_html=True)
        st.markdown('<div class="feature-box">🔍 Deep research capabilities</div>', unsafe_allow_html=True)
        st.markdown('<div class="feature-box">💡 Intelligent insights</div>', unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)

        # OAuth Login Button
        login_url = f"{API_BASE_URL}/api/v1/auth/login"

        st.markdown(
            f"""
            <a href="{login_url}" target="_self" style="text-decoration: none;">
                <button style="
                    background-color: #4285F4;
                    color: white;
                    padding: 15px 30px;
                    border: none;
                    border-radius: 8px;
                    font-size: 18px;
                    font-weight: 500;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    gap: 12px;
                    width: 100%;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                    transition: transform 0.2s;
                ">
                    <img src="https://www.google.com/favicon.ico" width="24" height="24" 
                         style="background: white; border-radius: 50%; padding: 2px;">
                    Continue with Google
                </button>
            </a>
            """,
            unsafe_allow_html=True,
        )
        
        st.markdown("</div>", unsafe_allow_html=True)
        
        # Info box
        with st.expander("ℹ️ About this app"):
            st.markdown("""
            This is a testing interface for the IDX Analyst API.
            
            **Features:**
            - Secure Google OAuth authentication
            - Automatic token refresh (no re-login needed)
            - Real-time chat with AI analyst
            - Access to Indonesian financial data
            
            **Note:** This Streamlit interface is for testing only.
            Production will use React frontend with better UX.
            """)


def render_chat_interface():
    """
    Render main chat interface with sidebar and message history.
    """
    user = st.session_state.get("user_info")

    # ===== Sidebar =====
    with st.sidebar:
        st.markdown(f"### {PAGE_ICON} {PAGE_TITLE}")
        st.divider()

        # User info
        if user:
            col_avatar, col_info = st.columns([1, 3])
            with col_avatar:
                if user.get("avatar_url"):
                    st.image(user["avatar_url"], width=50)
                else:
                    st.markdown("👤")
            with col_info:
                st.write(f"**{user.get('name', 'User')}**")
                st.caption(user.get("email", ""))
                if user.get("role"):
                    role_emoji = "👑" if user["role"] == "admin" else "👤"
                    st.caption(f"{role_emoji} {user['role'].title()}")

        st.divider()
        
        # Token info (for debugging)
        with st.expander("🔐 Session Info"):
            if "jwt_token" in st.session_state:
                payload = decode_jwt_without_verification(st.session_state["jwt_token"])
                if payload:
                    exp_time = datetime.fromtimestamp(payload["exp"])
                    time_left = exp_time - datetime.now()
                    
                    st.write(f"⏰ Token expires in:")
                    st.write(f"{int(time_left.total_seconds() / 60)} minutes")
                    
                    if time_left.total_seconds() < 60:
                        st.warning("⚠️ Token expiring soon!")
        
        st.divider()
        
        # Actions
        if st.button("🆕 New Chat", use_container_width=True):
            st.session_state["messages"] = []
            st.rerun()

        if st.button("🔄 Refresh Token", use_container_width=True):
            if "jwt_token" in st.session_state:
                new_token = refresh_access_token(st.session_state["jwt_token"])
                if new_token:
                    st.session_state["jwt_token"] = new_token
                    st.success("✅ Token refreshed!")
                    time.sleep(1)
                    st.rerun()

        st.divider()
        
        if st.button("🚪 Logout", type="secondary", use_container_width=True):
            logout()

    # ===== Main Chat Area =====
    st.title(f"{PAGE_ICON} Chat with IDX Analyst")
    
    # Display message history
    for msg in st.session_state["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    if prompt := st.chat_input("Ask about Indonesian stocks... (e.g., 'Analyze BBCA performance in 2024')"):
        # # Check token validity before sending
        # if is_token_expiring_soon(st.session_state["jwt_token"], threshold_seconds=60):
        #     st.info("🔄 Refreshing token before sending message...")
        #     new_token = refresh_access_token(st.session_state["jwt_token"])
        #     if new_token:
        #         st.session_state["jwt_token"] = new_token
        #     else:
        #         st.error("❌ Failed to refresh token. Please logout and login again.")
        #         return
        
        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)
        
        st.session_state["messages"].append({"role": "user", "content": prompt})

        # Get AI response
        response_data = send_chat_message(prompt, st.session_state["jwt_token"])

        if response_data:
            ai_content = response_data.get("response", "Sorry, I couldn't process that.")

            with st.chat_message("assistant"):
                st.markdown(ai_content)

            st.session_state["messages"].append({"role": "assistant", "content": ai_content})
        else:
            st.error("Failed to get response. Please try again or refresh your session.")


# ===== Main Application =====

def main():
    """
    Main application entry point.
    """
    # Initialize auth state (checks URL params, refreshes token if needed)
    init_auth_state()

    # Render appropriate UI based on auth state
    if st.session_state.get("jwt_token") and st.session_state.get("user_info"):
        render_chat_interface()
    else:
        render_login_page()


if __name__ == "__main__":
    main()