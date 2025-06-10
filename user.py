import streamlit as st
import pandas as pd
from datetime import datetime
import os
from passlib.context import CryptContext

# Password hashing configuration
pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    default="pbkdf2_sha256",
    pbkdf2_sha256__default_rounds=30000
)


# === User DB Handler ===
class UserDatabase:
    def __init__(self, data_dir="parking_data"):
        self.users_file = os.path.join(data_dir, "users.csv")
        self.data_dir = data_dir
        self.init_users()

    def init_users(self):
        os.makedirs(self.data_dir, exist_ok=True)
        if not os.path.exists(self.users_file):
            df = pd.DataFrame(columns=[
                "username", "password_hash", "points", "created_at", "last_login"
            ])
            df.to_csv(self.users_file, index=False)

    def hash_password(self, password):
        return pwd_context.hash(password)

    def verify_password(self, password, hashed):
        return pwd_context.verify(password, hashed)

    def load_users(self):
        return pd.read_csv(self.users_file)

    def save_users(self, df):
        df.to_csv(self.users_file, index=False)

    def signup(self, username, password):
        df = self.load_users()
        if username in df['username'].values:
            return False, "Username already exists."
        new_user = pd.DataFrame([{
            "username": username,
            "password_hash": self.hash_password(password),
            "points": 10,  # First login reward
            "created_at": datetime.now().isoformat(),
            "last_login": datetime.now().isoformat()
        }])
        df = pd.concat([df, new_user], ignore_index=True)
        self.save_users(df)
        return True, "Signup successful. You've earned 10 points!"

    def login(self, username, password):
        df = self.load_users()
        user_row = df[df['username'] == username]
        if not user_row.empty:
            hashed = user_row.iloc[0]['password_hash']
            if self.verify_password(password, hashed):
                index = user_row.index[0]
                df.at[index, 'last_login'] = datetime.now().isoformat()
                df.at[index, 'points'] += 10  # Login reward
                self.save_users(df)
                return True, df.loc[index].to_dict()
        return False, "Invalid username or password."

    def add_points(self, username, points):
        df = self.load_users()
        if username in df['username'].values:
            idx = df[df['username'] == username].index[0]
            df.at[idx, 'points'] += points
            self.save_users(df)

    def get_user_points(self, username):
        df = self.load_users()
        if username in df['username'].values:
            return int(df[df['username'] == username]['points'].values[0])
        return 0

    def redeem_reward(self, username, cost):
        df = self.load_users()
        if username in df['username'].values:
            idx = df[df['username'] == username].index[0]
            if int(df.at[idx, 'points']) >= cost:
                df.at[idx, 'points'] -= cost
                self.save_users(df)
                return True
        return False


# === UI Render ===
def render_user_login_page():
    st.header("👤 User Portal")

    db = UserDatabase()

    if 'user_logged_in' not in st.session_state:
        st.session_state.user_logged_in = False
        st.session_state.user_data = {}

    if not st.session_state.user_logged_in:
        tabs = st.tabs(["🔐 Login", "📝 Sign Up"])

        with tabs[0]:
            with st.form("user_login"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                login_btn = st.form_submit_button("Login")
                if login_btn:
                    success, user_or_msg = db.login(username, password)
                    if success:
                        st.session_state.user_logged_in = True
                        st.session_state.user_data = user_or_msg
                        st.success(f"Welcome back, {username}! (+10 points)")
                        st.rerun()
                    else:
                        st.error(user_or_msg)

        with tabs[1]:
            with st.form("user_signup"):
                new_user = st.text_input("Choose a Username")
                new_pass = st.text_input("Choose a Password", type="password")
                signup_btn = st.form_submit_button("Sign Up")
                if signup_btn:
                    success, msg = db.signup(new_user, new_pass)
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)
    else:
        user = st.session_state.user_data
        st.success(f"Logged in as: {user['username']}")
        points = db.get_user_points(user['username'])
        st.metric("🏆 Your Points", points)

        st.subheader("🎁 Redeem Your Points")
        reward_options = {
            "🎟️ Free Cinema Ticket (300 pts)": 300,
            "🛒 20% Off Supermarket Discount (200 pts)": 200,
            "☕ Free Coffee (100 pts)": 100,
        }
        reward = st.selectbox("Choose a reward:", list(reward_options.keys()))
        if st.button("Redeem"):
            cost = reward_options[reward]
            success = db.redeem_reward(user['username'], cost)
            if success:
                st.success(f"✅ Successfully redeemed: {reward}")
            else:
                st.error("❌ Not enough points.")

        if st.button("🔓 Logout"):
            st.session_state.user_logged_in = False
            st.session_state.user_data = {}
            st.rerun()