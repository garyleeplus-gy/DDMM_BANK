import streamlit as st
import json
import os
from datetime import datetime
import urllib.parse
import pandas as pd

# ================= 網頁基本設定 =================
st.set_page_config(page_title="爸媽銀行 Parents' Bank", page_icon="🏦", layout="centered")

DATA_FILE = "bank_data.json"
ADMIN_PIN = "8888"  # 爸媽管理後台預設密碼，可自行修改

# ================= 預設資料結構 =================
DEFAULT_DATA = {
    "kid1": {
        "name": "哥哥",
        "balance": 1000,
        "available_ratio": 0.30,  # 預設 30% 可用
        "wish_item": "寶可夢卡牌禮盒",
        "wish_price": 450,
        "history": [
            {"date": "2026-10-01 10:00", "type": "➕ 存款", "amount": 1000, "note": "開戶初始獎勵金", "balance_after": 1000}
        ]
    },
    "kid2": {
        "name": "妹妹",
        "balance": 800,
        "available_ratio": 0.30,
        "wish_item": "角落生物文具組",
        "wish_price": 300,
        "history": [
            {"date": "2026-10-01 10:00", "type": "➕ 存款", "amount": 800, "note": "開戶初始獎勵金", "balance_after": 800}
        ]
    }
}

# ================= 資料讀寫函數 =================
def load_data():
    if not os.path.exists(DATA_FILE):
        save_data(DEFAULT_DATA)
        return DEFAULT_DATA
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

data = load_data()

# ================= 讀取網址 QR Code 參數 =================
# 例如網址為 https://xxx.streamlit.app/?kid=kid1
query_params = st.query_params
url_kid = query_params.get("kid", None)

st.title("🏦 爸媽銀行數位存摺")

# 選擇帳戶邏輯（若刷 QR Code 進來則自動鎖定該帳戶）
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
    pin_input = st.text_input("請輸入行員密碼 (預設 8888)", type="password")
    
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
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                if "存款" in tx_type:
                    account["balance"] += tx_amount
                    account["history"].insert(0, {
                        "date": now_str,
                        "type": "➕ 存款",
                        "amount": tx_amount,
                        "note": tx_note,
                        "balance_after": account["balance"]
                    })
                    save_data(data)
                    st.toast("✅ 存款成功！")
                    st.rerun()
                else:
                    # 嚴格檢查：領錢不可超過「可用零用金」
                    if tx_amount > available_amount:
                        st.error(
                            f"🚫 餘額不足！目前可用額度只有 ${available_amount} 元，"
                            f"不能動用到鎖定的儲蓄金喔！"
                        )
                    else:
                        account["balance"] -= tx_amount
                        account["history"].insert(0, {
                            "date": now_str,
                            "type": "➖ 領錢",
                            "amount": -tx_amount,
                            "note": tx_note,
                            "balance_after": account["balance"]
                        })
                        save_data(data)
                        st.toast("✅ 提款成功！")
                        st.rerun()

        st.markdown("---")
        
        # --- B. 複利教育：一鍵發放利息 ---
        st.subheader("📈 複利教育：發放儲蓄利息")
        interest_rate = st.slider("本月利息獎勵比例 (%)", 1, 10, 3)
        interest_bonus = max(1, int(account["balance"] * (interest_rate / 100)))
        if st.button(f"🎁 發放 {interest_rate}% 利息 (+${interest_bonus}元)", use_container_width=True):
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            account["balance"] += interest_bonus
            account["history"].insert(0, {
                "date": now_str,
                "type": "🌟 利息",
                "amount": interest_bonus,
                "note": f"定存獎勵利息 ({interest_rate}%)",
                "balance_after": account["balance"]
            })
            save_data(data)
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
            account["name"] = new_name
            account["available_ratio"] = new_ratio / 100.0
            account["wish_item"] = new_wish
            account["wish_price"] = new_wish_price
            save_data(data)
            st.success("設定已更新！")
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
        st.caption("將此 QR Code 印出貼在孩子的書桌或存錢筒上，掃描即可直達專屬存摺！")