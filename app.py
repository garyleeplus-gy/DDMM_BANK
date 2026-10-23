import streamlit as st
import pandas as pd
import requests
import json
from datetime import datetime
import urllib.parse

# ================= 網頁基本設定 =================
st.set_page_config(page_title="爸媽銀行數位存摺", page_icon="🏦", layout="wide")

GAS_URL = st.secrets.get("gas_url", "請替換成你的_Apps_Script_網址")
ADMIN_PIN = st.secrets.get("admin_pin", "8888")

# ================= 自動取得目前 Streamlit 真實網址 =================
def get_auto_base_url():
    try:
        host = st.context.headers.get("Host", "")
        if host:
            protocol = "http" if ("localhost" in host or "127.0.0.1" in host) else "https"
            return f"{protocol}://{host}"
    except Exception:
        pass
    return ""

# ================= Google Sheets 讀寫函數（防轉址卡死版） =================
@st.cache_data(ttl=30)
def load_all_data():
    if not GAS_URL.startswith("https://script.google.com/"):
        st.warning("⚠️ 請先在 Streamlit Secrets 設定正確的 `gas_url`！")
        st.stop()
    resp = requests.get(GAS_URL, timeout=20)
    resp.raise_for_status()
    return resp.json()

def post_to_sheet(payload):
    """
    透過 text/plain 與 allow_redirects=False 傳送資料：
    當 Google Apps Script 執行完 doPost 並回傳 302 時即代表寫入完成，
    直接略過後續轉址，徹底解決 Python 3.14 ReadTimeout 問題。
    """
    headers = {"Content-Type": "text/plain;charset=utf-8"}
    resp = requests.post(
        GAS_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        allow_redirects=False,
        timeout=30
    )
    if resp.status_code not in (200, 302):
        resp.raise_for_status()
    st.cache_data.clear()

def recalc_records(df_in):
    """由上而下自動重新計算每一列的『餘額』"""
    records = []
    running_balance = 0
    for _, row in df_in.iterrows():
        date_str = str(row.get("日期", "")).strip()
        if date_str in ("nan", "None"):
            date_str = ""
        inc = int(pd.to_numeric(row.get("收入", 0), errors="coerce") or 0)
        exp = int(pd.to_numeric(row.get("支出", 0), errors="coerce") or 0)
        note_str = str(row.get("備註", "")).strip()
        if note_str in ("nan", "None"):
            note_str = ""
        if not date_str and inc == 0 and exp == 0 and not note_str:
            continue
        running_balance += (inc - exp)
        records.append({
            "date": date_str,
            "income": inc,
            "expense": exp,
            "note": note_str,
            "balance": running_balance
        })
    return records

# ================= 載入資料 =================
try:
    data = load_all_data()
except Exception as e:
    st.error("⚠️ 無法讀取 Google 試算表，請確認 Apps Script 網址正確且權限為「所有人」。")
    st.exception(e)
    st.stop()

# ================= 讀取 QR Code 網址參數 =================
query_params = st.query_params
url_kid = query_params.get("kid", None)
if url_kid:
    url_kid = url_kid.split("/")[0].split("?")[0]

kid_keys = list(data.keys())

# 側邊欄：爸媽行員登入區
with st.sidebar:
    st.header("🔐 爸媽管理後台")
    pin_input = st.text_input("輸入爸媽密碼解鎖編輯 (預設 8888)", type="password")
    is_admin = (pin_input == ADMIN_PIN)
    if is_admin:
        st.success("✅ 已開啟爸媽編輯模式！")
    else:
        st.caption("目前為「小孩查帳模式（唯讀）」，輸入密碼即可新增或直接修改表格。")

    if st.button("🔄 強制重新讀取試算表", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# 標題與帳戶切換
st.title("🏦 爸媽銀行數位存摺")

if url_kid in kid_keys and not is_admin:
    selected_kid = url_kid
    st.caption(f"📱 目前顯示：**{data[selected_kid]['name']}** 的專屬存摺")
else:
    default_idx = kid_keys.index(url_kid) if url_kid in kid_keys else 0
    selected_kid = st.selectbox(
        "選擇要查看或管理的帳戶：",
        options=kid_keys,
        index=default_idx,
        format_func=lambda k: f"{data[k]['name']} ({k})"
    )

account = data[selected_kid]

# 自動檢查 Apps Script 是否忘記更新部署版本
if "records" not in account:
    st.error(
        "⚠️ **偵測到你的 Google Apps Script 還在執行舊版程式！**\n\n"
        "請打開 Google 試算表的「擴充功能 → Apps Script」，貼上新版程式碼並按儲存後，務必點選右上角 "
        "**「部署」→「管理部署作業」→ 點選右上角「✏️ 編輯」→ 版本選擇「新版本」→ 按下「部署」**，才能啟用新版表格讀寫功能！"
    )
    st.stop()

ratio = float(account.get("available_ratio", 0.30))
if ratio > 1.0:  # 防呆：避免讀到舊版欄位數字
    ratio = 0.30
records = account.get("records", [])

# 轉換為 DataFrame 並計算頂部 Excel 看板數字
if records:
    df = pd.DataFrame(records)
    df.columns = ["日期", "收入", "支出", "備註", "餘額"]
else:
    df = pd.DataFrame(columns=["日期", "收入", "支出", "備註", "餘額"])

total_income = int(df["收入"].sum()) if not df.empty else 0
total_expense = int(df["支出"].sum()) if not df.empty else 0
total_balance = total_income - total_expense             # 總存款 (1732)
total_available_quota = round(total_income * ratio)      # 可用金額總額度 (600)
spendable_now = total_available_quota - total_expense    # 目前可花金額 (331~332)

# ================= 1. 頂部 Excel 摘要看板 =================
st.markdown("### 📊 帳戶金額總覽")
c1, c2, c3, c4 = st.columns(4)

with c1:
    st.metric(label="🟢 目前可花金額 (餘額)", value=f"${spendable_now:,}", delta="現在可以動用的錢")
with c2:
    st.metric(label="💰 總存款 (帳面餘額)", value=f"${total_balance:,}", delta=f"鎖定儲蓄 ${total_balance - spendable_now:,}", delta_color="off")
with c3:
    st.metric(label=f"🧮 可用總額度 ({int(ratio*100)}%)", value=f"${total_available_quota:,}")
with c4:
    st.metric(label="💸 累計已支出", value=f"${total_expense:,}")

# ================= 2. 存摺明細表（小孩唯讀 vs 爸媽直接編輯） =================
st.markdown("---")

if not is_admin:
    st.markdown("### 📖 收支明細表")
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    # 爸媽專屬：快速記一筆
    st.markdown("### ➕ 快速新增一筆收支")
    with st.form("quick_add_form", clear_on_submit=True):
        f1, f2, f3, f4 = st.columns([2, 2, 2, 4])
        with f1:
            new_date = st.text_input("日期", value=datetime.now().strftime("%Y/%m/%d"))
        with f2:
            new_inc = st.number_input("收入 (存入金額)", min_value=0, value=0, step=50)
        with f3:
            new_exp = st.number_input("支出 (領出金額)", min_value=0, value=0, step=10)
        with f4:
            new_note = st.text_input("備註內容 (例如：國語期末考100、買卡包)")
            
        submitted = st.form_submit_button("➕ 新增這筆紀錄並存檔", type="primary")
        if submitted:
            if new_inc == 0 and new_exp == 0:
                st.error("收入與支出不能同時為 0 喔！")
            elif new_exp > spendable_now and new_inc == 0:
                st.error(f"🚫 超出可花金額！目前可花金額只有 ${spendable_now} 元。")
            else:
                new_row = pd.DataFrame([{
                    "日期": new_date, "收入": new_inc, "支出": new_exp, "備註": new_note, "餘額": 0
                }])
                updated_df = pd.concat([df, new_row], ignore_index=True)
                updated_records = recalc_records(updated_df)
                with st.spinner("正在寫入 Google 試算表..."):
                    post_to_sheet({
                        "action": "save_table",
                        "kid_id": selected_kid,
                        "records": updated_records
                    })
                st.toast("✅ 已新增並同步至 Google 試算表！")
                st.rerun()

    # 爸媽專屬：像 Excel 一樣直接修改表格
    st.markdown("### ✏️ 手動修改存摺內容（可直接點選格子修改、新增或刪除列）")
    st.caption("💡 提示：直接點兩下表格內的文字或數字即可修改；修改完畢後請點擊下方的「💾 儲存表格修改」按鈕，系統會自動重算每一列的餘額並永久存入 Google Sheet！")
    
    edited_df = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "日期": st.column_config.TextColumn("日期 (YYYY/MM/DD)"),
            "收入": st.column_config.NumberColumn("收入", min_value=0, step=1, format="%d"),
            "支出": st.column_config.NumberColumn("支出", min_value=0, step=1, format="%d"),
            "備註": st.column_config.TextColumn("備註內容"),
            "餘額": st.column_config.NumberColumn("餘額 (存檔後自動重算)", disabled=True, format="%d")
        }
    )
    
    if st.button("💾 儲存表格修改並永久同步至 Google 試算表", type="primary"):
        updated_records = recalc_records(edited_df)
        with st.spinner("正在重新計算餘額並寫入 Google 試算表..."):
            post_to_sheet({
                "action": "save_table",
                "kid_id": selected_kid,
                "records": updated_records
            })
        st.success("✅ 表格修改已永久保存至 Google 試算表！")
        st.rerun()

# ================= 3. 側邊欄：設定與正確的 QR Code 產生器 =================
with st.sidebar:
    if is_admin:
        st.markdown("---")
        st.subheader("⚙️ 帳戶名稱與比例設定")
        new_name = st.text_input("小孩名稱", value=account["name"])
        new_ratio = st.slider("可用金額比例 (%)", 10, 100, int(ratio * 100), 5)
        if st.button("更新帳戶設定", use_container_width=True):
            post_to_sheet({
                "action": "update_settings",
                "kid_id": selected_kid,
                "new_name": new_name,
                "new_ratio": new_ratio / 100.0
            })
            st.success("已更新！")
            st.rerun()

    st.markdown("---")
    st.subheader("🖨️ 專屬查帳 QR Code")
    auto_url = get_auto_base_url()
    raw_url = st.text_input(
        "你的 Streamlit 網址（已自動偵測）",
        value=auto_url if auto_url else "https://請貼上你的網址.streamlit.app"
    )
    clean_base_url = raw_url.split("?")[0].rstrip("/")
    target_url = f"{clean_base_url}/?kid={selected_kid}"
    
    if "請貼上你的網址" not in clean_base_url and clean_base_url.startswith("http"):
        encoded_url = urllib.parse.quote(target_url, safe="")
        qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=220x220&data={encoded_url}"
        st.image(qr_api_url, caption=f"掃描直接看【{account['name']}】的存摺")
        st.code(target_url, language="text")
    else:
        st.warning("請在上方填入你部署後的 Streamlit 網址以產生正確的 QR Code。")
