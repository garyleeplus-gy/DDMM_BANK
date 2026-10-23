import streamlit as st
import pandas as pd
import gspread
from datetime import datetime
import urllib.parse

# ================= 網頁基本設定 =================
st.set_page_config(page_title="爸媽銀行 Parents' Bank", page_icon="🏦", layout="centered")

ADMIN_PIN = st.secrets.get("admin_pin", "8888")  # 可在 Secrets 設定，未設定則預設 8888

# ================= Google Sheets 連線與自動建表 =================
@st.cache_resource
def get_gsheet_workbook():
    """建立 Google Sheets 連線（使用快取保持連線）"""
     credentials = dict(st.secrets["gcp_service_account"])
    gc = gspread.service_account_from_dict(credentials)
    sheet_url = st.secrets["sheet_url"]
    return gc.open_by_url(sheet_url)

def init_sheets_if_needed(sh):
    """若試算表為空，自動建立 accounts 與 history 分頁及預設資料"""
    existing_titles = [ws.title for ws in sh.worksheets()]
    
    # 1. 建立與初始化 accounts 分頁
    if "accounts" not in existing_titles:
        acc_ws = sh.add_worksheet(title="accounts", rows=20, cols=10)
        acc_ws.append_row(["kid_id", "name", "balance", "available_ratio", "wish_item", "wish_price"])
        acc_ws.append_rows([
            ["kid1", "哥哥", 1000, 0.30, "寶可夢卡牌禮盒", 450],
            ["kid2", "妹妹", 800, 0.30, "角落生物文具組", 300]
        ])
    
    # 2. 建立與初始化 history 分頁
    if "history" not in existing_titles:
        hist_ws = sh.add_worksheet(title="history", rows=500, cols=10)
        hist_ws.append_row(["kid_id", "date", "type", "amount", "note", "balance_after"])
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        hist_ws.append_rows([
            ["kid1", now_str, "➕ 存款", 1000, "開戶初始獎勵金", 1000],
            ["kid2", now_str, "➕ 存款", 800, "開戶初始獎勵金", 800]
        ])

@st.cache_data(ttl=60)
def load_all_data():
    """從 Google Sheets 讀取最新帳戶與交易紀錄（快取 60 秒加速掃碼載入）"""
    sh = get_gsheet_workbook()
    init_sheets_if_needed(sh)
    
    acc_ws = sh.worksheet("accounts")
    hist_ws = sh.worksheet("history")
    
    acc_records = acc_ws.get_all_records()
    hist_records = hist_ws.get_all_records()
    
    data = {}
    for row in acc_records:
        kid_id = str(row["kid_id"])
        data[kid_id] = {
            "name": str(row["name"]),
            "balance": int(row["balance"]),
            "available_ratio": float(row["available_ratio"]),
            "wish_item": str(row["wish_item"]),
            "wish_price": int(row["wish_price"]),
            "history": []
        }
        
    for h in hist_records:
        kid_id = str(h["kid_id"])
        if kid_id in data:
            data[kid_id]["history"].append({
                "date": str(h["date"]),
                "type": str(h["type"]),
                "amount": int(h["amount"]),
                "note": str(h["note"]),
                "balance_after": int(h["balance_after"])
            })
            
    return data

def update_account_in_sheet(kid_id, new_balance=None, new_name=None, new_ratio=None, new_wish=None, new_wish_price=None):
    """更新 accounts 分頁中指定小孩的資料"""
    sh = get_gsheet_workbook()
    acc_ws = sh.worksheet("accounts")
    cell = acc_ws.find(kid_id, in_column=1)
    row_idx = cell.row
    
    if new_name is not None:
        acc_ws.update_cell(row_idx, 2, new_name)
    if new_balance is not None:
        acc_ws.update_cell(row_idx, 3, int(new_balance))
    if new_ratio is not None:
        acc_ws.update_cell(row_idx, 4, float(new_ratio))
    if new_wish is not None:
        acc_ws.update_cell(row_idx, 5, new_wish)
    if new_wish_price is not None:
        acc_ws.update_cell(row_idx, 6, int(new_wish_price))
        
    st.cache_data.clear()

def add_transaction_to_sheet(kid_id, tx_type, amount, note, balance_after):
    """在 history 分頁最上方（第 2 列）插入一筆新交易紀錄"""
    sh = get_gsheet_workbook()
    hist_ws = sh.worksheet("history")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    hist_ws.insert_row([kid_id, now_str, tx_type, int(amount), note, int(balance_after)], index=2)
    st.cache_data.clear()

# ================= 載入資料與錯誤防護 =================
try:
    data = load_all_data()
except Exception as e:
    st.error("⚠️ 無法連線至 Google Sheets，請確認 Streamlit Secrets 設定與試算表共用權限是否正確。")
    st.exception(e)
    st.stop()

# ================= 讀取網址 QR Code 參數 =================
query_params = st.query_params
url_kid = query_params.get("kid", None)

st.title("🏦 爸媽銀行數位存摺")

kid_keys = list(data.keys())
if url_kid in kid_keys:
    selected_kid = url_kid
    st.caption(f"📱 已透過專屬 QR Code 登入 **{data[selected_kid]['name']}** 的帳戶")
else:
    selected_kid = st.selectbox(
        "請選擇要查看的小孩帳戶：",
        options=kid_keys,
        format_func=lambda k: f"{data[k]['name']} ({k})"
    )

account = data[selected_kid]
total_balance = account["balance"]
ratio = account["available_ratio"]
available_amount = int(total_balance * ratio)
locked_amount = total_balance - available_amount

# ================= 1. 核心資產儀表板 =================
st.markdown("### 💰 我的金庫狀態")
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(label="帳戶總餘額", value=f"${total_balance:,}")
with col2:
    st.metric(
        label=f"🟢 可用零用金 ({int(ratio*100)}%)", 
        value=f"${available_amount:,}",
        delta="可自由花用"
    )
with col3:
    st.metric(
        label=f"🔒 夢想儲蓄金 ({int((1-ratio)*100)}%)", 
        value=f"${locked_amount:,}",
        delta="生利息保護中",
        delta_color="off"
    )

st.info(
    f"💡 **理財小提醒**：你目前最多可以動用 **${available_amount:,}** 元！"
    f"剩下的 **${locked_amount:,}** 元正在銀行裡幫你長大喔！"
)

# ================= 2. 許願池進度條 =================
st.markdown("---")
st.markdown(f"### 🎯 夢想許願池：**{account['wish_item']}** (目標 ${account['wish_price']:,})")

if account["wish_price"] > 0:
    progress = min(available_amount / account["wish_price"], 1.0)
    st.progress(progress)
    if available_amount >= account["wish_price"]:
        st.success(f"🎉 太棒了！你的「可用零用金」已經存夠買【{account['wish_item']}】囉！可以找爸媽討論兌現！")
    else:
        shortfall = account["wish_price"] - available_amount
        st.caption(f"距離目標還差 **${shortfall:,}** 元的可用額度（換算總存款需再存約 **${int(shortfall/ratio):,}** 元）")

# ================= 3. 交易明細紀錄 =================
st.markdown("---")
st.markdown("### 📜 存摺交易紀錄")
if account["history"]:
    df = pd.DataFrame(account["history"])
    df.columns = ["時間", "類型", "金額", "備註說明", "交易後總餘額"]
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.write("尚無交易紀錄")

# ================= 4. 側邊欄：爸媽行員管理後台 =================
with st.sidebar:
    st.header("🔐 爸媽行員專屬後台")
    pin_input = st.text_input("請輸入行員密碼", type="password")
    
    if pin_input == ADMIN_PIN:
        st.success("已解鎖行員權限！")
        
        # --- A. 存提款操作 ---
        st.subheader(f"💳 辦理【{account['name']}】存提款")
        tx_type = st.radio("交易類型", ["➕ 存款 (表現獎勵/紅包/零用錢)", "➖ 領錢 (花用可用額度)"])
        tx_amount = st.number_input("金額 (元)", min_value=1, value=50, step=10)
        tx_note = st.text_input("備註原因 (必填，例如：洗碗獎勵、買文具)")
        
        if st.button("確認執行交易", type="primary", use_container_width=True):
            if not tx_note.strip():
                st.error("請填寫備註原因，讓孩子知道錢的來龍去脈！")
            else:
                with st.spinner("正在寫入 Google 試算表..."):
                    if "存款" in tx_type:
                        new_bal = total_balance + tx_amount
                        update_account_in_sheet(selected_kid, new_balance=new_bal)
                        add_transaction_to_sheet(selected_kid, "➕ 存款", tx_amount, tx_note, new_bal)
                        st.toast("✅ 存款已同步至雲端試算表！")
                        st.rerun()
                    else:
                        if tx_amount > available_amount:
                            st.error(
                                f"🚫 餘額不足！目前可用額度只有 ${available_amount} 元，"
                                f"不能動用到鎖定的儲蓄金喔！"
                            )
                        else:
                            new_bal = total_balance - tx_amount
                            update_account_in_sheet(selected_kid, new_balance=new_bal)
                            add_transaction_to_sheet(selected_kid, "➖ 領錢", -tx_amount, tx_note, new_bal)
                            st.toast("✅ 提款已同步至雲端試算表！")
                            st.rerun()

        st.markdown("---")
        
        # --- B. 複利教育：一鍵發放利息 ---
        st.subheader("📈 複利教育：發放儲蓄利息")
        interest_rate = st.slider("本月利息獎勵比例 (%)", 1, 10, 3)
        interest_bonus = max(1, int(total_balance * (interest_rate / 100)))
        if st.button(f"🎁 發放 {interest_rate}% 利息 (+${interest_bonus}元)", use_container_width=True):
            with st.spinner("正在派發利息至試算表..."):
                new_bal = total_balance + interest_bonus
                update_account_in_sheet(selected_kid, new_balance=new_bal)
                add_transaction_to_sheet(
                    selected_kid, "🌟 利息", interest_bonus, 
                    f"定存獎勵利息 ({interest_rate}%)", new_bal
                )
                st.rerun()

        st.markdown("---")

        # --- C. 調整可用比例與許願目標 ---
        st.subheader("⚙️ 帳戶規則與許願池設定")
        new_name = st.text_input("小孩暱稱", value=account["name"])
        new_ratio = st.slider(
            "可用金額比例 (%)", 
            min_value=10, max_value=100, 
            value=int(account["available_ratio"] * 100), 
            step=5
        )
        new_wish = st.text_input("許願池目標名稱", value=account["wish_item"])
        new_wish_price = st.number_input("許願目標金額", min_value=10, value=account["wish_price"], step=50)
        
        if st.button("儲存帳戶設定", use_container_width=True):
            with st.spinner("正在更新試算表設定..."):
                update_account_in_sheet(
                    selected_kid,
                    new_name=new_name,
                    new_ratio=new_ratio / 100.0,
                    new_wish=new_wish,
                    new_wish_price=new_wish_price
                )
                st.success("設定已寫入 Google 試算表！")
                st.rerun()

        st.markdown("---")

        # --- D. 專屬 QR Code 產生器 ---
        st.subheader("🖨️ 專屬 QR Code 存摺卡")
        base_url = st.text_input("輸入部署後的 Streamlit 網址", value="https://your-app-name.streamlit.app")
        target_url = f"{base_url.rstrip('/')}/?kid={selected_kid}"
        encoded_url = urllib.parse.quote(target_url)
        qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=220x220&data={encoded_url}"
        
        st.image(qr_api_url, caption=f"{account['name']} 的專屬查帳 QR Code")
        st.code(target_url, language="text")
