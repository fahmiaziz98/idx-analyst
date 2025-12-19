"""
IDX Analyst Chatbot Interface
Secure, modern chat interface for IDX Analyst AI.
"""

import time

import requests
import streamlit as st

# Configuration
API_BASE_URL = "http://localhost:7860"
PAGE_TITLE = "IDX Analyst AI"
PAGE_ICON = "📈"

st.set_page_config(
    page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout="wide", initial_sidebar_state="expanded"
)

# ===== State Management =====
from http.cookies import SimpleCookie
from streamlit.web.server.websocket_headers import _get_websocket_headers

if "messages" not in st.session_state:
    st.session_state["messages"] = []

if "user_info" not in st.session_state:
    st.session_state["user_info"] = None

def get_access_token_from_cookies() -> str | None:
    """Extract access_token from browser cookies via WebSocket headers"""
    headers = _get_websocket_headers()
    if not headers:
        return None
    
    cookie_header = headers.get("Cookie")
    if not cookie_header:
        return None
    
    cookie = SimpleCookie()
    try:
        cookie.load(cookie_header)
        if "access_token" in cookie:
            return cookie["access_token"].value
    except Exception:
        pass
        
    return None

def init_auth_state():
    """Handle authentication via cookies"""
    # Try to get token from cookies
    token = get_access_token_from_cookies()
    
    if token:
        st.session_state["jwt_token"] = token
        
        # Verify token and get user info if not present
        if not st.session_state["user_info"]:
            user = get_current_user(token)
            if user:
                st.session_state["user_info"] = user
            else:
                # Token invalid/expired
                st.session_state["jwt_token"] = None
    else:
        st.session_state["jwt_token"] = None


def logout():
    """Call backend logout and clear session"""
    if "jwt_token" in st.session_state and st.session_state["jwt_token"]:
        try:
            headers = {"Authorization": f"Bearer {st.session_state['jwt_token']}"}
            requests.post(f"{API_BASE_URL}/api/v1/auth/logout", headers=headers)
        except Exception:
            pass
            
    if "jwt_token" in st.session_state:
        del st.session_state["jwt_token"]
    if "user_info" in st.session_state:
        del st.session_state["user_info"]
    if "messages" in st.session_state:
        st.session_state["messages"] = []
    
    # Rerun to show login page
    st.rerun()


# ===== API Client =====
def get_current_user(token: str) -> dict | None:
    """Fetch user info using JWT"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(f"{API_BASE_URL}/api/v1/auth/me", headers=headers)
        return resp.json() if resp.status_code == 200 else None
    except Exception:
        return None


def send_chat_message(prompt: str, token: str) -> dict | None:
    """Send message history to backend and get response"""
    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {"messages": prompt}

        with st.spinner("AI is thinking..."):
            resp = requests.post(f"{API_BASE_URL}/api/v1/chat/", headers=headers, json=payload)

            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code in [401, 403]:
                st.error("Session expired. Please login again.")
                time.sleep(2)
                logout()
            else:
                st.error(f"Error: {resp.status_code} - {resp.text}")
                return None
    except Exception as e:
        st.error(f"Connection Error: {e}")
        return None


# ===== UI Components =====
def render_login_page():
    """Render attractive login page"""
    st.markdown(
        """
        <style>
        .login-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify_content: center;
            padding: 50px;
            text-align: center;
        }
        .title {
            font-size: 3em;
            font-weight: bold;
            color: #1E3A8A; /* Dark Blue */
            margin-bottom: 20px;
        }
        .subtitle {
            font-size: 1.2em;
            color: #6B7280;
            margin-bottom: 40px;
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
            '<div class="subtitle">AI-Powered Financial Analyst Assistant</div>',
            unsafe_allow_html=True,
        )

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
                    <img src="https://www.google.com/favicon.ico" width="24" height="24" style="background: white; border-radius: 50%; padding: 2px;">
                    Continue with Google
                </button>
            </a>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)


def render_chat_interface():
    """Render main chat interface"""
    user = st.session_state["user_info"]

    # --- Sidebar ---
    with st.sidebar:
        st.markdown(f"### {PAGE_ICON} IDX Analyst")
        st.divider()

        if user:
            col_avatar, col_info = st.columns([1, 3])
            with col_avatar:
                if user.get("avatar_url"):
                    st.image(user["avatar_url"], width=50)
            with col_info:
                st.write(f"**{user.get('name', 'User')}**")
                st.caption(user.get("email"))

        st.divider()
        if st.button("New Chat", use_container_width=True):
            st.session_state["messages"] = []
            st.rerun()

        st.divider()
        if st.button("Log Out", type="secondary", use_container_width=True):
            logout()

    # --- Main Chat Area ---
    # Display message history
    for msg in st.session_state["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat Input
    if prompt := st.chat_input("Ask about Indonesian stocks..."):
        # 1. Display user message
        with st.chat_message("user"):
            st.markdown(prompt)

        st.session_state["messages"].append({"role": "user", "content": prompt})

        # 2. Get AI Response
        response_data = send_chat_message(prompt, st.session_state["jwt_token"])

        if response_data:
            ai_content = response_data.get("response", "Sorry, I couldn't process that.")

            with st.chat_message("assistant"):
                st.markdown(ai_content)

            st.session_state["messages"].append({"role": "assistant", "content": ai_content})


# ===== Main Loop =====
def main():
    init_auth_state()

    if "jwt_token" in st.session_state and st.session_state["jwt_token"]:
        render_chat_interface()
    else:
        render_login_page()


if __name__ == "__main__":
    main()
