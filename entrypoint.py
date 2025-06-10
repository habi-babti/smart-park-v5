import streamlit as st
from user import render_user_login_page
import datetime
import pandas as pd
from difflib import SequenceMatcher
import re
import os

st.set_page_config(
    page_title="BASE-SmartPark",
    page_icon="🅿️",
    layout="wide",
    initial_sidebar_state="expanded"
)

from datetime import datetime
from web import (
    ParkingDatabase,
    render_enhanced_reservation_page,  # ✅ Fixed import name
    render_anpr_dashboard,
    get_anpr_integration
)
from admin import (
    render_analytics_page,
    render_system_settings_page,
    render_admin_spot_map,
    render_user_admin_panel,
    render_user_passwords_view
)


# Cache database
@st.cache_resource
def get_db():
    return ParkingDatabase()


# Cache ANPR integration
@st.cache_resource
def get_anpr():
    return get_anpr_integration()


# Init session state
def init_session():
    if 'admin_logged_in' not in st.session_state:
        st.session_state.admin_logged_in = False
    if 'admin_username' not in st.session_state:
        st.session_state.admin_username = ""
    if 'page_refresh' not in st.session_state:
        st.session_state.page_refresh = 0
    if 'user_plate' not in st.session_state:
        st.session_state.user_plate = ""


def render_dashboard_page(db):
    st.header("🏠 SmartPark Dashboard")

    # Get current data
    spots_df = db.get_parking_spots()
    reservations_df = db.get_reservations_history()

    # Summary statistics at the top
    st.subheader("📊 Parking Summary")

    if not spots_df.empty:
        # Calculate counts
        available_count = len(spots_df[spots_df['status'] == 'available'])
        occupied_count = len(spots_df[spots_df['status'] == 'occupied'])
        reserved_count = len(spots_df[spots_df['status'] == 'reserved'])

        # Display summary metrics
        col1, col2, col3 = st.columns(3)
        col1.metric("🟢 Available", available_count)
        col2.metric("🔴 Occupied", occupied_count)
        col3.metric("🟡 Reserved", reserved_count)

        # Show only available spots by default
        available_spots = spots_df[spots_df['status'] == 'available']

        # Detailed spot view at the bottom
        st.subheader("🅿️ Available Parking Spots")

        if not available_spots.empty:
            st.dataframe(
                available_spots,
                column_config={
                    "spot_id": "Spot ID",
                    "status": st.column_config.TextColumn("Status"),
                    "current_user": "Current User",
                    "reservation_time": st.column_config.DatetimeColumn(
                        "Reservation Time",
                        format="YYYY-MM-DD HH:mm"
                    )
                },
                hide_index=True,
                use_container_width=True
            )



# ✅ Added missing admin login function
def render_admin_login_page():
    st.header("🔐 Admin Login")

    if st.session_state.admin_logged_in:
        st.success(f"✅ Logged in as: {st.session_state.admin_username}")
        if st.button("🚪 Logout"):
            st.session_state.admin_logged_in = False
            st.session_state.admin_username = ""
            st.rerun()
        return

    with st.form("admin_login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        if st.form_submit_button("🔑 Login"):
            # Simple admin check (you can enhance this with your database)
            if username == "admin" and password == "admin123":
                st.session_state.admin_logged_in = True
                st.session_state.admin_username = username
                st.success("✅ Login successful!")
                st.rerun()
            else:
                st.error("❌ Invalid credentials")


# Reservation status tracker (User)
def render_reservation_status_page(db):
    st.header("📟 Reservation Status Tracker")

    plate = st.text_input("🔍 Enter your license plate to track reservation")
    if plate:
        st.session_state.user_plate = plate.upper()

    if st.session_state.user_plate:
        df = db.get_reservations_history()
        res = df[df['plate_number'].str.upper() == st.session_state.user_plate]

        if res.empty:
            st.info("No reservation found for this plate.")
            return

        latest = res.sort_values("created_at", ascending=False).iloc[0]
        status = latest['status']
        spot_id = latest['spot_id']
        duration = latest['duration_minutes']
        start_time = latest.get('start_time', '')
        end_time = latest.get('end_time', '')
        detection_time = latest.get('detection_time', '')

        st.success(f"🅿️ Spot: {spot_id} | 👤 Name: {latest['customer_name']}")
        st.markdown(f"**Reservation Status**: `{status.upper()}`")

        if status == "waiting_detection":
            # Count time since created
            created_at = pd.to_datetime(latest['created_at'], errors='coerce')
            minutes_waiting = (datetime.now() - created_at).total_seconds() / 60

            st.warning(
                f"⏳ Waiting for arrival... Reservation will be cancelled in `{int(30 - minutes_waiting)}` minutes.")
            st.markdown("💡 You must be detected within 30 minutes.")

            # Cancel it if over time
            if minutes_waiting > 30:
                df.loc[res.index[-1], 'status'] = 'cancelled'
                db.update_spot_status(spot_id, 'available')
                df.to_csv(db.reservations_file, index=False)
                st.error("❌ Reservation cancelled due to no ANPR detection.")
                return

        elif status == "active":
            start = pd.to_datetime(start_time)
            end = pd.to_datetime(end_time)
            now = datetime.now()
            remaining = end - now

            if remaining.total_seconds() <= 0:
                st.error("⏱️ Reservation time has expired.")
            else:
                mins = int(remaining.total_seconds() // 60)
                secs = int(remaining.total_seconds() % 60)
                st.info(f"⏳ Time remaining: **{mins} min {secs} sec**")
                st.caption(f"📅 Total Duration: {duration} min")

        elif status == "cancelled":
            st.error("❌ This reservation was cancelled.")

        elif status == "expired":
            st.warning("⏱️ Reservation expired.")

        else:
            st.write(f"ℹ️ Reservation status: {status}")


def render_copilot_page(db):
    st.header("🤖 Your Copilot")

    st.markdown("### 💬 Suggested Questions")

    suggested_questions = [
        "How many available spots?",
        "What's the total number of spots?",
        "How many occupied/reserved/maintenance spots are there?",
        "Which is the busiest zone?",
        "What's the busiest time?",
        "How's parking today?"
    ]

    for q in suggested_questions:
        if st.button(q):
            st.chat_message("user").write(q)
            response = generate_copilot_response(q, db)
            st.chat_message("assistant").write(response)

    user_input = st.chat_input("e.g. 'When is the parking busiest?' or 'Clean expired reservations'")
    if user_input:
        st.chat_message("user").write(user_input)
        response = generate_copilot_response(user_input, db)
        st.chat_message("assistant").write(response)


def generate_copilot_response(user_input: str, db) -> str:
    # Handle empty input
    if not user_input or len(user_input.strip()) < 2:
        return "👋 Hi! Ask me about parking availability, zones, peak times, or maintenance tasks."

    user_lower = user_input.lower()

    # Helper function for fuzzy keyword matching
    def matches_keywords(keywords, threshold=0.6):
        for keyword in keywords:
            if keyword in user_lower:
                return True
            # Fuzzy matching
            if SequenceMatcher(None, keyword, user_lower).ratio() >= threshold:
                return True
            # Word-level matching
            keyword_words = keyword.split()
            input_words = user_lower.split()
            matches = sum(
                1 for kw in keyword_words if any(SequenceMatcher(None, kw, iw).ratio() >= 0.8 for iw in input_words))
            if matches >= len(keyword_words) * 0.7:
                return True
        return False

    try:
        spots = db.get_parking_spots()
        res = db.get_reservations_history()

        # SPECIFIC SPOT STATUS QUERIES (using regex for precision)
        if re.search(r'\b(how many|number of|count of|spots)\b.*\b(available|total|reserved|occupied|maintenance)\b',
                     user_lower):
            if "available" in user_lower:
                count = len(spots[spots["status"] == "available"])
                return f"There are currently **{count}** available spots."
            elif "total" in user_lower:
                count = len(spots)
                return f"There are a total of **{count}** parking spots in the system."
            elif "reserved" in user_lower:
                count = len(spots[spots["status"] == "reserved"])
                return f"There are currently **{count}** reserved spots."
            elif "occupied" in user_lower:
                count = len(spots[spots["status"] == "occupied"])
                return f"There are currently **{count}** occupied spots."
            elif "maintenance" in user_lower:
                count = len(spots[spots["status"] == "maintenance"])
                return f"There are currently **{count}** spots under maintenance."

        # GENERAL PARKING STATUS (fuzzy matching for casual queries)
        elif matches_keywords(['parking today', 'how\'s parking', 'parking status', 'current parking']) or re.search(
                r'\b(how\'s parking|parking status|current parking|parking today)\b', user_lower):
            available_count = len(spots[spots["status"] == "available"])
            total_count = len(spots)
            occupied_count = len(spots[spots["status"] == "occupied"])
            reserved_count = len(spots[spots["status"] == "reserved"])
            maintenance_count = len(spots[spots["status"] == "maintenance"])
            return (f"Currently, there are **{available_count}** available spots out of **{total_count}** total spots. "
                    f"**{occupied_count}** are occupied, **{reserved_count}** are reserved, "
                    f"and **{maintenance_count}** are under maintenance.")

        # ZONE ANALYSIS (with better error handling)
        elif matches_keywords(
                ['busiest zone', 'most used zone', 'popular zone', 'busy area', 'zone stats']) or re.search(
            r'\b(most used zone|busiest zone|popular zone)\b', user_lower):
            if not res.empty:
                res_copy = res.copy()
                res_copy["zone"] = res_copy["spot_id"].astype(str).str[0]
                zone_counts = res_copy["zone"].value_counts()
                if not zone_counts.empty:
                    top_zone = zone_counts.idxmax()
                    return f"The busiest zone historically is **Zone {top_zone}**."
                else:
                    return "I don't have enough reservation data to determine the busiest zone yet."
            else:
                return "No reservation history available to determine the busiest zone."

        # TIME ANALYSIS (with better error handling)
        elif matches_keywords(['busiest time', 'busy hour', 'peak time', 'rush hour', 'when busy']) or re.search(
                r'\b(time|hour)\b.*\b(busy|busiest)\b', user_lower):
            if not res.empty:
                res_copy = res.copy()
                res_copy["hour"] = pd.to_datetime(res_copy["start_time"]).dt.hour
                if not res_copy["hour"].empty:
                    top_hour = res_copy["hour"].value_counts().idxmax()
                    return f"The busiest hour is **{top_hour}:00**."
                else:
                    return "I don't have enough reservation data to determine the busiest hour yet."
            else:
                return "No reservation history available to determine the busiest time."

        # STATUS BREAKDOWN
        elif matches_keywords(['breakdown', 'summary', 'status', 'overview', 'total spots', 'all spots']):
            spots = db.get_parking_spots()
            status_counts = spots["status"].value_counts()
            total = len(spots)

            breakdown = []
            for status in ["available", "occupied", "reserved", "maintenance"]:
                count = status_counts.get(status, 0)
                percentage = (count / total * 100) if total > 0 else 0
                emoji = {"available": "✅", "occupied": "🚗", "reserved": "📅", "maintenance": "🔧"}.get(status, "📊")
                breakdown.append(f"{emoji} **{status.title()}**: {count} ({percentage:.1f}%)")

            return f"📊 **Parking Overview** ({total} total spots):\n" + "\n".join(breakdown)

        # MAINTENANCE INFO
        elif matches_keywords(['maintenance', 'broken', 'repair', 'out of order', 'maintenance spots']):
            spots = db.get_parking_spots()
            maintenance_spots = spots[spots["status"] == "maintenance"]
            count = len(maintenance_spots)

            if count == 0:
                return "✅ **No spots under maintenance** currently."
            else:
                spot_ids = ", ".join(maintenance_spots["spot_id"].tolist()[:5])
                more_text = f" (+{count - 5} more)" if count > 5 else ""
                return f"🔧 **{count} spots under maintenance**: {spot_ids}{more_text}"

        # COMMANDS (using regex for precision)
        elif re.search(r'\b(clear|clean|remove)\b.*\b(expired reservations|expired spots)\b',
                       user_lower) or matches_keywords(
            ['clean expired', 'clear expired', 'remove expired', 'cleanup', 'clean up']):
            db.clean_expired_reservations()
            return "✅ Expired reservations have been cleaned."

        elif re.search(r'\b(initialize|reset)\b.*\b(parking spots|spots)\b', user_lower) or matches_keywords(
                ['initialize', 'init spots', 'setup spots', 'create spots', 'reset spots']):
            db.initialize_parking_spots()
            return "✅ Parking spots have been initialized to their default state."

        # FALLBACK RESPONSE (improved suggestions)
        else:
            return ("I'm still learning. Here are some things you can ask me:\n"
                    "- How many available spots?\n"
                    "- What's the total number of spots?\n"
                    "- How many occupied/reserved/maintenance spots are there?\n"
                    "- Which is the busiest zone?\n"
                    "- What's the busiest time?\n"
                    "- How's parking today?")

    except Exception as e:
        return f"❌ Something went wrong: {str(e)}"


# Admin Spot Grid View with Manual Override
def render_admin_spot_grid(spots_df, db):
    st.header("🗺️ Live Spot Map - Admin Control")
    zones = spots_df['zone'].unique()
    zone_titles = {"B": "Regular", "A": "VIP", "S": "Staff", "E": "Emergency"}

    for zone in sorted(zones):
        st.subheader(f"Zone {zone} - {zone_titles.get(zone, '')}")
        zone_spots = spots_df[spots_df['zone'] == zone].sort_values('spot_id')
        cols = st.columns(5)
        for idx, (_, spot) in enumerate(zone_spots.iterrows()):
            with cols[idx % 5]:
                color = {
                    'available': '🟢',
                    'reserved': '🟡',
                    'occupied': '🔴',
                    'maintenance': '🔧'
                }.get(spot['status'], '⚪')
                label = f"{color} {spot['spot_id']}"
                st.markdown(label)

                if st.button(f"⚙️ Manage {spot['spot_id']}", key=f"{zone}-{spot['spot_id']}"):
                    with st.form(f"form-{spot['spot_id']}"):
                        new_status = st.selectbox("New Status", ["available", "reserved", "occupied", "maintenance"],
                                                  index=["available", "reserved", "occupied", "maintenance"].index(
                                                      spot['status']))
                        new_plate = st.text_input("Plate Number", spot['plate_number'])
                        reserved_by = st.text_input("Reserved By", spot['reserved_by'])
                        reserved_until = st.text_input("Reserved Until", spot['reserved_until'])
                        if st.form_submit_button("✅ Apply Changes"):
                            db.update_spot_status(spot['spot_id'], new_status, new_plate, reserved_by, reserved_until)
                            st.success(f"Updated {spot['spot_id']}")
                            st.rerun()


def render_user_admin_panel():
    from user import UserDatabase
    st.subheader("👥 User Accounts")

    db = UserDatabase()
    users_df = db.load_users()
    st.dataframe(users_df)

    if st.button("🔄 Refresh User List"):
        st.rerun()


def render_user_passwords_view():
    from user import UserDatabase
    st.subheader("🔑 View User Passwords")

    master_key = st.text_input("Enter admin password to reveal users' passwords", type="password")
    if master_key == "papitxo":
        db = UserDatabase()
        df = db.load_users()
        st.success("Access granted. Below are stored user passwords.")
        st.dataframe(df[['username', 'password_hash']].rename(columns={"password_hash": "password"}))
    else:
        st.info("🔒 Access locked. Enter correct admin key to continue.")


# App entrypoint
def main():
    init_session()
    db = get_db()
    anpr_integration = get_anpr()  # ✅ Initialize ANPR integration
    db.clean_expired_reservations()

    st.sidebar.title("🧭 SmartPark Navigation")
    pages = [
        "🏠 Dashboard",
        "🎫 Reservation",
        "🤖 BASE Copilot",
        "📟 Track Status",
        "👤 User Portal",
        "🔐 Admin Login"
    ]

    if st.session_state.admin_logged_in:
        pages += [
            "🎥 ANPR Control",
            "📊 Analytics",
            "🔧 System Settings",
            "🗺️ Admin Spot Map",
            "👥 Manage Users"
        ]

    selection = st.sidebar.radio("Choose a page", pages)

    # 🔄 Always get fresh data
    spots_df = db.get_parking_spots()
    reservations_df = db.get_reservations_history()

    # 🚦 Page routing
    if selection == "🏠 Dashboard":
        render_dashboard_page(db)

    elif selection == "🎫 Reservation":
        render_enhanced_reservation_page(spots_df, db,
                                         anpr_integration)

    elif selection == "🎥 ANPR Control":
        render_anpr_dashboard(db, anpr_integration)

    elif selection == "📟 Track Status":
        render_reservation_status_page(db)

    elif selection == "🔐 Admin Login":
        render_admin_login_page()

    elif selection == "👤 User Portal":
        render_user_login_page()

    elif selection == "📊 Analytics":
        render_analytics_page(spots_df, reservations_df)

    elif selection == "🔧 System Settings":
        render_system_settings_page(db)

    elif selection == "🗺️ Admin Spot Map":
        render_admin_spot_map(spots_df, db)

    elif selection == "👥 Manage Users":
        if st.session_state.get("admin_logged_in", False):
            render_user_admin_panel()
        else:
            st.warning("Admins only")

    elif selection == "🤖 BASE Copilot":
        render_copilot_page(db)


if __name__ == "__main__":
    main()