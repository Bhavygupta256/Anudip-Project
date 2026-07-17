import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime
import time

# --- SECURE DOUBLE-VERIFICATION INITIALIZATION ---
CLOUD_DB_URL = None

# Attempt 1: Standard immediate lookup
if "postgres" in st.secrets:
    CLOUD_DB_URL = st.secrets["postgres"]["db_url"]
else:
    # Attempt 2: Secure System Loop. If it's a slow boot, wait 2 seconds and retry.
    time.sleep(2)
    st.cache_data.clear() 
    if "postgres" in st.secrets:
        CLOUD_DB_URL = st.secrets["postgres"]["db_url"]

# Final Safety Gate: If it STILL fails, completely shut down to protect the system.
if not CLOUD_DB_URL:
    st.error("🔒 Streamlit Security System is mounting database drivers. Please refresh the page in 5 seconds.")
    st.stop()


# --- DATABASE OPERATIONS ---
def init_db():
    conn = psycopg2.connect(CLOUD_DB_URL)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            account_number SERIAL PRIMARY KEY,
            holder_name TEXT NOT NULL,
            pin TEXT NOT NULL,
            balance REAL DEFAULT 0.0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id SERIAL PRIMARY KEY,
            account_number INTEGER,
            type TEXT,
            amount REAL,
            timestamp TEXT,
            FOREIGN KEY (account_number) REFERENCES accounts (account_number) ON DELETE CASCADE
        )
    ''')
    conn.commit()
    cursor.close()
    conn.close()

def get_connection():
    return psycopg2.connect(CLOUD_DB_URL)

def log_transaction(account_num, tx_type, amount):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO transactions (account_number, type, amount, timestamp) VALUES (%s, %s, %s, %s)",
        (account_num, tx_type, amount, now)
    )
    conn.commit()
    cursor.close()
    conn.close()

def verify_account(account_num, pin):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT balance, holder_name FROM accounts WHERE account_number = %s AND pin = %s", (account_num, pin))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result

def refresh_balance(account_num):
    """Helper to pull the newest balance from the cloud database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM accounts WHERE account_number = %s", (account_num,))
    res = cursor.fetchone()
    cursor.close()
    conn.close()
    return res[0] if res else 0.0


# --- INITIALIZE ON START ---
try:
    if CLOUD_DB_URL:
        init_db()
except Exception as e:
    st.error(f"Database Connection Error: {e}")


# --- TRACK SESSION STATE ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_acc = None
    st.session_state.user_name = None


# --- STREAMLIT USER INTERFACE ---
st.set_page_config(page_title="Virtual Cloud Bank", page_icon="🏦", layout="centered")
st.title("🏦 Virtual Cloud Banking System")


# SIDEBAR LOGOUT CONTROL
if st.session_state.logged_in:
    st.sidebar.write(f"👤 **User:** {st.session_state.user_name}")
    st.sidebar.write(f"💳 **Acc No:** {st.session_state.user_acc}")
    if st.sidebar.button("🚪 Secure Log Out", type="secondary"):
        st.session_state.logged_in = False
        st.session_state.user_acc = None
        st.session_state.user_name = None
        st.rerun()


# --- OPTION 1: USER IS NOT LOGGED IN ---
if not st.session_state.logged_in:
    tab1, tab2 = st.tabs(["🔑 Access Dashboard (Log In)", "📝 Open New Account"])
    
    with tab1:
        st.subheader("Account Login")
        login_acc = st.number_input("Account Number", step=1, value=0, key="login_acc")
        login_pin = st.text_input("Enter 4-Digit PIN", type="password", max_chars=4, key="login_pin")
        
        if st.button("Log In", type="primary"):
            res = verify_account(login_acc, login_pin)
            if res:
                st.session_state.logged_in = True
                st.session_state.user_acc = login_acc
                st.session_state.user_name = res[1]  # Safely extracts the holder name from database array
                st.success("Access Granted! Fetching workspace...")
                st.rerun()
            else:
                st.error("Invalid Account Number or PIN details.")
                
    with tab2:
        st.subheader("Register with the Bank")
        reg_name = st.text_input("Full Name", key="reg_name")
        reg_pin = st.text_input("Create 4-Digit PIN", type="password", max_chars=4, key="reg_pin")
        
        if st.button("Register Account"):
            if not reg_name or len(reg_pin) != 4 or not reg_pin.isdigit():
                st.error("Please provide a valid Name and a 4-digit numeric PIN.")
            else:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("INSERT INTO accounts (holder_name, pin, balance) VALUES (%s, %s, 0.0) RETURNING account_number", (reg_name, reg_pin))
                account_num = cursor.fetchone()[0]  # Safely extracts the raw generated integer ID
                conn.commit()
                cursor.close()
                conn.close()
                st.success(f"🎉 Account successfully created!")
                st.code(f"Your Account Number is: {account_num}", language="text")
                st.warning("Write down your Account Number. You need it to access your dashboard!")


# --- OPTION 2: USER IS SECURELY LOGGED IN ---
else:
    current_balance = refresh_balance(st.session_state.user_acc)
    
    st.metric(label=f"Welcome back, {st.session_state.user_name}! 👋 Current Balance", value=f"${current_balance:,.2f}")
    st.divider()

    menu_tabs = st.tabs(["💵 Deposit", "🏧 Withdraw", "💸 Transfer Funds", "📜 Statement & Analytics"])
    
    # --- TAB A: DEPOSIT ---
    with menu_tabs[0]:
        st.subheader("Deposit Funds")
        dep_amount = st.number_input("Amount to Deposit ($)", min_value=0.0, step=10.0, key="dep_amt")
        if st.button("Execute Deposit", type="primary"):
            if dep_amount <= 0:
                st.error("Deposit amount must be greater than zero.")
            else:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("UPDATE accounts SET balance = balance + %s WHERE account_number = %s", (dep_amount, st.session_state.user_acc))
                conn.commit()
                cursor.close()
                conn.close()
                log_transaction(st.session_state.user_acc, "Deposit", dep_amount)
                st.success(f"✅ Successfully deposited ${dep_amount:,.2f}!")
                st.rerun()

    # --- TAB B: WITHDRAW ---
    with menu_tabs[1]:
        st.subheader("Withdraw Cash")
        wd_amount = st.number_input("Amount to Withdraw ($)", min_value=0.0, step=10.0, key="wd_amt")
        if st.button("Execute Withdrawal"):
            if wd_amount <= 0 or wd_amount > current_balance:
                st.error("Invalid amount or insufficient funds available.")
            else:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("UPDATE accounts SET balance = balance - %s WHERE account_number = %s", (wd_amount, st.session_state.user_acc))
                conn.commit()
                cursor.close()
                conn.close()
                log_transaction(st.session_state.user_acc, "Withdrawal", wd_amount)
                st.success(f"✅ Successfully withdrew ${wd_amount:,.2f}!")
                st.rerun()

    # --- TAB C: TRANSFER FUNDS ---
    with menu_tabs[2]:
        st.subheader("Secure Interbank Transfer")
        dest_num = st.number_input("Recipient Account Number", step=1, value=0, key="dest_acc")
        tf_amount = st.number_input("Transfer Amount ($)", min_value=0.0, step=10.0, key="tf_amt")
        
        if st.button("Send Transfer", type="primary"):
            if st.session_state.user_acc == dest_num or tf_amount <= 0:
                st.error("Invalid transaction configuration parameters.")
            elif current_balance < tf_amount:
                st.error("Insufficient balance to fulfill transfer target.")
            else:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT account_number FROM accounts WHERE account_number = %s", (dest_num,))
                if not cursor.fetchone():
                    st.error("Target recipient account number does not exist.")
                    cursor.close()
                    conn.close()
                else:
                    cursor.execute("UPDATE accounts SET balance = balance - %s WHERE account_number = %s", (tf_amount, st.session_state.user_acc))
                    cursor.execute("UPDATE accounts SET balance = balance + %s WHERE account_number = %s", (tf_amount, dest_num))
                    conn.commit()
                    cursor.close()
                    conn.close()
                    log_transaction(st.session_state.user_acc, f"Transfer to #{dest_num}", tf_amount)
                    log_transaction(dest_num, f"Transfer from #{st.session_state.user_acc}", tf_amount)
                    st.success(f"🚀 Sent ${tf_amount:,.2f} to Account #{dest_num}!")
                    st.rerun()

        # --- TAB D: STATEMENT & ANALYTICS ---
    with menu_tabs[3]:
        st.subheader("Ledger Statement & Visual Balance Trend")
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT type, amount, timestamp FROM transactions WHERE account_number = %s ORDER BY transaction_id ASC", (st.session_state.user_acc,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not rows:
            st.info("No transaction history recorded yet. Your account balance trend will build automatically.")
        else:
            running_balance = 0.0
            history_chart_data = []
            display_table_data = []
            
            for type_str, amt, time_str in rows:
                if "Deposit" in type_str or "from" in type_str:
                    running_balance += amt
                else:
                    running_balance -= amt
                
                history_chart_data.append({"Timestamp": time_str, "Balance ($)": running_balance})
                display_table_data.append({"Operation Type": type_str, "Amount": f"${amt:,.2f}", "Timestamp": time_str})
            
            df = pd.DataFrame(history_chart_data)
            st.line_chart(df, x="Timestamp", y="Balance ($)")
            
            st.write("### Complete Audit Logs")
            st.dataframe(display_table_data[::-1], use_container_width=True)
