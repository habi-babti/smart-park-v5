import streamlit as st
import pandas as pd
from datetime import datetime
import os
from notifier import send_email_notification, send_sms_notification, notify_user
import json
import plotly.express as px


def render_system_settings_page(db, anpr_integration=None):
    st.header("🔧 System Settings")

    # ──────── CRITICAL SYSTEM CONTROL ──────── #
    st.subheader("🚨 Critical System Control")

    # Load system status
    system_config_file = os.path.join(db.data_dir, "system_config.json")

    # Initialize system config if it doesn't exist
    if not os.path.exists(system_config_file):
        default_config = {
            "system_enabled": True,
            "anpr_enabled": True,
            "reservations_enabled": True,
            "last_updated": datetime.now().isoformat(),
            "updated_by": "system"
        }
        with open(system_config_file, 'w') as f:
            json.dump(default_config, f, indent=2)

    # Load current config
    with open(system_config_file, 'r') as f:
        system_config = json.load(f)

    # Display current system status
    system_enabled = system_config.get("system_enabled", True)
    anpr_enabled = system_config.get("anpr_enabled", True)
    reservations_enabled = system_config.get("reservations_enabled", True)

    # Status indicators
    col1, col2, col3 = st.columns(3)

    with col1:
        status_icon = "🟢" if system_enabled else "🔴"
        st.metric("Overall System", f"{status_icon} {'ACTIVE' if system_enabled else 'DISABLED'}")

    with col2:
        anpr_icon = "🟢" if anpr_enabled else "🔴"
        st.metric("ANPR System", f"{anpr_icon} {'ACTIVE' if anpr_enabled else 'DISABLED'}")

    with col3:
        res_icon = "🟢" if reservations_enabled else "🔴"
        st.metric("Reservations", f"{res_icon} {'ACTIVE' if reservations_enabled else 'DISABLED'}")

    st.markdown("---")

    # Master system control
    st.subheader("🎛️ Master System Control")

    if system_enabled:
        st.error("⚠️ **DANGER ZONE**: This will completely disable the entire SmartPark system!")

        col1, col2 = st.columns([3, 1])
        with col1:
            st.write("**What happens when you disable the system:**")
            st.write("• 🚫 All new reservations will be blocked")
            st.write("• 🛑 ANPR monitoring will stop immediately")
            st.write("• 📵 No notifications will be sent")
            st.write("• 🔒 Users will see maintenance mode message")
            st.write("• 📊 Analytics will show system as offline")

        with col2:
            disable_reason = st.text_area("Reason for disabling system:",
                                          placeholder="e.g., Emergency maintenance, System upgrade, Security issue")

        if st.button("🔴 DISABLE ENTIRE SYSTEM", type="primary"):
            if disable_reason.strip():
                # Stop ANPR monitoring if active
                if anpr_integration and hasattr(st.session_state,
                                                'monitoring_active') and st.session_state.monitoring_active:
                    anpr_integration.stop_monitoring()
                    st.session_state.monitoring_active = False

                # Update system config
                system_config.update({
                    "system_enabled": False,
                    "anpr_enabled": False,
                    "reservations_enabled": False,
                    "last_updated": datetime.now().isoformat(),
                    "updated_by": "admin",
                    "disable_reason": disable_reason.strip(),
                    "disabled_at": datetime.now().isoformat()
                })

                with open(system_config_file, 'w') as f:
                    json.dump(system_config, f, indent=2)

                st.error("🚨 SYSTEM DISABLED! All SmartPark services are now offline.")
                st.success(f"✅ Reason logged: {disable_reason}")

                # Log the action
                log_system_action("SYSTEM_DISABLED", disable_reason, db)

                st.rerun()
            else:
                st.warning("⚠️ Please provide a reason for disabling the system.")

    else:
        st.success("✅ **SYSTEM RECOVERY**: Click below to re-enable SmartPark services")

        st.write("**What happens when you enable the system:**")
        st.write("• ✅ All services will be restored")
        st.write("• 🎥 ANPR monitoring can be restarted")
        st.write("• 📝 New reservations will be accepted")
        st.write("• 📱 Notifications will resume")
        st.write("• 🔓 Users will have full access")

        enable_reason = st.text_area("Reason for enabling system:",
                                     placeholder="e.g., Maintenance completed, System upgraded, Issue resolved")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("🟢 ENABLE ENTIRE SYSTEM", type="primary"):
                if enable_reason.strip():
                    system_config.update({
                        "system_enabled": True,
                        "anpr_enabled": True,
                        "reservations_enabled": True,
                        "last_updated": datetime.now().isoformat(),
                        "updated_by": "admin",
                        "enable_reason": enable_reason.strip(),
                        "enabled_at": datetime.now().isoformat()
                    })

                    # Remove disable-related fields
                    system_config.pop("disable_reason", None)
                    system_config.pop("disabled_at", None)

                    with open(system_config_file, 'w') as f:
                        json.dump(system_config, f, indent=2)

                    st.success("🎉 SYSTEM ENABLED! All SmartPark services are now online.")

                    # Log the action
                    log_system_action("SYSTEM_ENABLED", enable_reason, db)

                    st.rerun()
                else:
                    st.warning("⚠️ Please provide a reason for enabling the system.")

        with col2:
            if st.button("🔧 ENABLE WITH CUSTOM SETTINGS"):
                if enable_reason.strip():
                    # Show granular controls
                    st.session_state.show_granular_controls = True
                    st.rerun()

    # Granular controls (when enabling with custom settings)
    if hasattr(st.session_state, 'show_granular_controls') and st.session_state.show_granular_controls:
        st.subheader("🎛️ Granular System Controls")

        new_anpr = st.checkbox("Enable ANPR System", value=True)
        new_reservations = st.checkbox("Enable Reservation System", value=True)

        if st.button("✅ Apply Custom Settings"):
            system_config.update({
                "system_enabled": True,
                "anpr_enabled": new_anpr,
                "reservations_enabled": new_reservations,
                "last_updated": datetime.now().isoformat(),
                "updated_by": "admin",
                "enable_reason": enable_reason.strip(),
                "enabled_at": datetime.now().isoformat()
            })

            with open(system_config_file, 'w') as f:
                json.dump(system_config, f, indent=2)

            st.success("✅ Custom system settings applied!")
            st.session_state.show_granular_controls = False
            st.rerun()

    st.markdown("---")

    # ──────── SYSTEM STATUS LOGS ──────── #
    st.subheader("📋 System Status History")

    system_log_file = os.path.join(db.data_dir, "system_actions_log.csv")
    if os.path.exists(system_log_file):
        logs_df = pd.read_csv(system_log_file)
        if not logs_df.empty:
            st.dataframe(logs_df.tail(10).sort_values('timestamp', ascending=False), use_container_width=True)
        else:
            st.info("No system action history yet.")
    else:
        st.info("No system action history yet.")

    st.markdown("---")

    # ──────── CONFIGURATION OPTIONS ──────── #
    st.subheader("⚙️ Configuration Settings")

    st.text_input("🚫 Blacklist Plate Number")
    st.multiselect("🚧 Disable Zones for Reservation", ["A", "B", "S", "E"])

    spot_id = st.selectbox("🔧 Set Spot Under Maintenance", db.get_parking_spots()['spot_id'])
    maintenance_until = st.date_input("📅 Maintenance Until")
    if st.button("🛠️ Apply Maintenance"):
        db.update_spot_status(spot_id, "maintenance", reserved_until=maintenance_until.isoformat())
        st.success(f"✅ {spot_id} set under maintenance until {maintenance_until}")

    st.number_input("🎁 Points Per Reservation", 10, 100, 50)
    st.number_input("🏅 Points to Discount Conversion (per 100)", 1, 10, 5)

    # ──────── RESET TOOLS ──────── #
    st.subheader("🧼 System Cleanup Tools")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("🔄 Reset Parking Spots"):
            db.initialize_parking_spots()
            st.success("✅ Parking spots have been reset.")
            st.rerun()

    with col2:
        if st.button("🧹 Clear Reservation History"):
            empty_df = pd.DataFrame(
                columns=['id', 'spot_id', 'plate_number', 'customer_name', 'customer_email', 'customer_phone',
                         'start_time', 'end_time', 'duration_minutes', 'status', 'created_at'])
            empty_df.to_csv(db.reservations_file, index=False)
            st.success("🧼 Reservation history cleared.")
            st.rerun()

    st.subheader("💣 Factory Reset (Danger Zone)")

    if st.button("🔥 FULL SYSTEM RESET"):
        db.full_factory_reset()
        st.session_state.clear()
        st.error("System fully reset. All data cleared, CSVs reinitialized, session wiped.")
        st.rerun()


def log_system_action(action, reason, db):
    """Log system enable/disable actions"""
    system_log_file = os.path.join(db.data_dir, "system_actions_log.csv")

    if not os.path.exists(system_log_file):
        log_df = pd.DataFrame(columns=['timestamp', 'action', 'reason', 'admin'])
    else:
        log_df = pd.read_csv(system_log_file)

    new_entry = pd.DataFrame([{
        'timestamp': datetime.now().isoformat(),
        'action': action,
        'reason': reason,
        'admin': 'admin'  # You can modify this to get actual admin username
    }])

    log_df = pd.concat([log_df, new_entry], ignore_index=True)
    log_df.to_csv(system_log_file, index=False)


def check_system_status(db):
    """Function to check if system is enabled - use this in other parts of your app"""
    system_config_file = os.path.join(db.data_dir, "system_config.json")

    if not os.path.exists(system_config_file):
        return {"system_enabled": True, "anpr_enabled": True, "reservations_enabled": True}

    with open(system_config_file, 'r') as f:
        return json.load(f)


def render_system_maintenance_message():
    """Display maintenance message when system is disabled"""
    st.error("🚨 **SYSTEM MAINTENANCE MODE**")
    st.write("The SmartPark system is currently offline for maintenance.")
    st.write("• 🚫 New reservations are temporarily disabled")
    st.write("• 🛑 ANPR monitoring is offline")
    st.write("• 📞 For urgent parking needs, please contact support")
    st.info("We apologize for the inconvenience. Normal service will resume shortly.")


# Export the enhanced functions
__all__ = [
    "render_system_settings_page",
    "log_system_action",
    "check_system_status",
    "render_system_maintenance_message"
]
def render_analytics_page(spots_df, reservations_df):
    st.header("📊 Analytics Dashboard")

    total_spots = len(spots_df)
    total_reservations = len(reservations_df)
    available_spots = len(spots_df[spots_df['status'] == 'available'])
    reserved_spots = len(spots_df[spots_df['status'] == 'reserved'])
    occupied_spots = len(spots_df[spots_df['status'] == 'occupied'])
    maintenance_spots = len(spots_df[spots_df['status'] == 'maintenance'])

    col1, col2, col3 = st.columns(3)
    col1.metric("🅿️ Total Spots", total_spots)
    col2.metric("📋 Total Reservations", total_reservations)
    col3.metric("🟢 Available Now", available_spots)

    col4, col5, col6 = st.columns(3)
    col4.metric("🟡 Reserved", reserved_spots)
    col5.metric("🔴 Occupied", occupied_spots)
    col6.metric("🔧 Maintenance", maintenance_spots)

    st.markdown("---")

    # 🔵 Current Spot Status Distribution (Pie Chart)
    st.subheader("📌 Current Spot Status Distribution")
    status_counts = spots_df['status'].value_counts().reset_index()
    status_counts.columns = ['status', 'count']

    fig = px.pie(
        status_counts,
        values='count',
        names='status',
        title="Distribution of Parking Spot Status"
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # 🟣 Reservation Time Distribution
    st.subheader("📈 Reservation Time Distribution")
    if not reservations_df.empty:
        reservations_df['start_time'] = pd.to_datetime(reservations_df['start_time'], errors='coerce')
        reservations_df = reservations_df.dropna(subset=['start_time'])
        reservations_df['end_time'] = pd.to_datetime(reservations_df['end_time'])

        fig2 = px.scatter(
            reservations_df,
            x="start_time",
            y="duration_minutes",
            color="status",
            hover_data=["plate_number", "spot_id"],
            title="Reservation Durations Over Time"
        )
        fig2.update_layout(
            xaxis_title="Start Time",
            yaxis_title="Duration (minutes)"
        )
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No reservation data available yet.")

    st.markdown("---")

    # 📋 Raw Reservation Table
    st.subheader("📋 Reservation History")
    st.dataframe(reservations_df.sort_values("created_at", ascending=False))

    st.subheader("📈 AI Suggestion Trends")
    try:
        df = pd.read_csv("parking_data/ai_recommendation_log.csv")
        st.dataframe(df.tail(20))
    except FileNotFoundError:
        st.info("AI recommendation log not found yet.")

    log_file = "parking_data/ai_recommendation_log.csv"
    if not os.path.exists(log_file):
        st.warning("No AI recommendation logs found yet.")
        return

    df = pd.read_csv(log_file)

    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    df = df.dropna(subset=['timestamp'])

    st.subheader("📈 Global Trends")
    st.write(f"Total AI Recommendations: {len(df)}")
    st.dataframe(df.tail(10), use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        zone_counts = df['zone'].value_counts()
        st.bar_chart(zone_counts)

    with col2:
        spot_counts = df['predicted_spot'].value_counts().head(10)
        st.bar_chart(spot_counts)

    st.subheader("⏰ Peak Recommendation Hours")
    df['hour'] = df['timestamp'].dt.hour
    st.bar_chart(df['hour'].value_counts().sort_index())

def render_admin_spot_map(spots_df, db):
    st.header("🗺️ Live Spot Map – Admin Control")

    zones = sorted(spots_df['zone'].unique())
    for zone in zones:
        st.subheader(f"Zone {zone}")
        zone_spots = spots_df[spots_df['zone'] == zone]

        for _, spot in zone_spots.iterrows():
            spot_status = str(spot['status']).strip().lower()
            status_icon = {
                "available": "🟢",
                "reserved": "🟡",
                "occupied": "🔴",
                "maintenance": "🔴"
            }.get(spot_status, "❓")

            with st.expander(f"{status_icon} {spot['spot_id']} – {spot_status.capitalize()}"):
                new_status = st.selectbox(
                    "Status",
                    ["available", "reserved", "occupied", "maintenance"],
                    index=["available", "reserved", "occupied", "maintenance"].index(spot_status),
                    key=f"status_{spot['spot_id']}"
                )

                # Only show these fields if status isn't "available"
                if new_status != "available":
                    new_plate = st.text_input("Plate Number",
                                              value=spot['plate_number'],
                                              key=f"plate_{spot['spot_id']}")
                    reserved_by = st.text_input("Reserved By",
                                                value=spot['reserved_by'],
                                                key=f"by_{spot['spot_id']}")
                    reserved_until = st.text_input("Reserved Until",
                                                   value=spot['reserved_until'],
                                                   key=f"until_{spot['spot_id']}")
                else:
                    # When status is available, clear these fields
                    new_plate = ""
                    reserved_by = ""
                    reserved_until = ""

                if st.button(f"✅ Apply to {spot['spot_id']}", key=f"btn_{spot['spot_id']}"):
                    # Update spot with cleared fields if status is available
                    db.update_spot_status(
                        spot_id=spot['spot_id'],
                        status=new_status,
                        plate_number=new_plate if new_status != "available" else "",
                        reserved_by=reserved_by if new_status != "available" else "",
                        reserved_until=reserved_until if new_status != "available" else ""
                    )
                    st.success(f"🔄 {spot['spot_id']} updated to '{new_status}'")

                    # 🔔 Notify next user if available
                    if new_status == "available":
                        next_user = db.notify_next_user_in_queue()
                        if next_user is not None:
                            msg = f"""
                            🚗 Hello {next_user['name']},

                            A SmartPark spot is now available and reserved for your plate: {next_user['plate_number']}.
                            Spot: {spot['spot_id']}
                            Please arrive within 30 minutes.
                            """
                            notify_user(next_user['contact'], msg)

                            db.add_reservation(
                                spot_id=spot['spot_id'],
                                plate_number=next_user['plate_number'],
                                name=next_user['name'],
                                duration=60
                            )

                            st.info(f"📩 Notified {next_user['name']} and reserved {spot['spot_id']}.")

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