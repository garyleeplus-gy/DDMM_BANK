import streamlit as st
import pandas as pd
import requests
from datetime import datetime, date
import urllib.parse

# ================= 網頁基本設定 =================
st.set_page_config(page_title="爸媽銀行數位存摺", page_icon="🏦", layout="wide")

GAS_URL = st.secrets.get("gas_url", "請替換成你的_Apps_Script_網址")
ADMIN_PIN = st.secrets.get("admin_pin", "8888")

def get_auto_base_url():
    try:
        host = st.context.headers.get("Host", "")
        if host:
            protocol = "http" if ("localhost" in host or "127.0.0.1" in host) else "https"
            return f"{protocol}://{host}"
    except Exception:
        pass
    return ""

@st.cache_data(ttl=30)
def load_all_data():
    if not GAS_URL.startswith("https://script.google.com/"):
        st.warning("⚠️ 請先在 Streamlit Secrets 設定正確的 `gas_url`！")
        st.stop()
    resp = requests.get(GAS_URL, timeout=20)
    resp.raise_for_status()
    return resp.json()

def post_to_sheet(payload):
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

# 計算依年利率與持有天數產生的利息
def calculate_interest(records, annual_rate):
    """
    根據每一筆收入的日期到今天的天數，計算累積年利息。
    公式：利息 = 存款金額 × 年利率 × (持有天數 / 365)
    """
    total_interest = 0.0
    today = date.today()
    for r in records:
        inc = r.get("income", 0)
        d_str = r.get("date", "")
        if inc > 0 and d_str:
            try:
                # 嘗試解析各種日期格式
                d_obj = None
                for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S"):
                    try:
                        d_obj = datetime.strptime(d_str.split()[0], fmt.split()[0]).date()
                        break
                    except ValueError:
                        continue
                if d_obj:
                    days = (today - d_obj).days
                    if days > 0:
                        interest_item = inc * annual_rate * (days / 365.0)
                        total_interest += interest_item
            except Exception:
                pass
    return int(round(total_interest))

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
        st.caption("目前為「小孩查帳模式」，輸入密碼即可解鎖管理後台與設定。")

    if st.button("🔄 強制重新讀取試算表", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# 判斷是否為「小孩掃 QR Code 進入」（無密碼且網址帶有 kid 參數）
is_kid_scan = (url_kid in kid_keys and not is_admin)

# ================= 選擇帳戶 =================
if is_kid_scan:
    selected_kid = url_kid
else:
    default_idx = kid_keys.index(url_kid) if url_kid in kid_keys else 0
    selected_kid = st.selectbox(
        "選擇要查看的小孩帳戶 (支援最多 5 名)：",
        options=kid_keys,
        index=default_idx,
        format_func=lambda k: f"{data[k]['name']} ({k})"
    )

account = data[selected_kid]
name = account.get("name", "小朋友")
ratio = float(account.get("available_ratio", 0.30))
annual_rate = float(account.get("annual_interest_rate", 0.05))
records = account.get("records", [])

if "records" not in account:
    st.error("⚠️ 請更新 Google Apps Script 版本以支援 5 名小孩與新資料結構！")
    st.stop()

# 處理 DataFrame 與計算金額
if records:
    df = pd.DataFrame(records)
    df.columns = ["日期", "收入", "支出", "備註", "餘額"]
else:
    df = pd.DataFrame(columns=["日期", "收入", "支出", "備註", "餘額"])

total_income = int(df["收入"].sum()) if not df.empty else 0
total_expense = int(df["支出"].sum()) if not df.empty else 0
base_balance = total_income - total_expense

# 計算利息並併入總餘額與可用金額
earned_interest = calculate_interest(records, annual_rate)
total_balance = base_balance + earned_interest                 # 總存款（含利息）
total_available_quota = round(total_income * ratio)          # 可用金額總額度
spendable_now = max(0, total_available_quota - total_expense + earned_interest) # 目前可花金額

# ================= 📱 小孩專屬掃碼檢視（童趣時速表介面） =================
if is_kid_scan:
    st.markdown(f"<h1 style='text-align: center; color: #4A90E2;'>✨ {name}的專屬財富時速表 ✨</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>隨時掌握你的存錢進度，錢錢正在長大中！</p>", unsafe_allow_html=True)
    st.markdown("---")
    
    # 用醒目的視覺儀表板呈現
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            label="🚀 目前可花金額 (時速)", 
            value=f"${spendable_now:,}", 
            delta="可以自由花用的零用錢",
            delta_color="normal"
        )
    with col2:
        st.metric(
            label="💰 總存款餘額 (含利息)", 
            value=f"${total_balance:,}", 
            delta=f"含銀行紅利利息 +${earned_interest:,}",
            delta_color="off"
        )
    with col3:
        st.metric(
            label="📈 銀行滾入利息", 
            value=f"${earned_interest:,}", 
            delta=f"年利率 {int(annual_rate*100)}%",
            delta_color="normal"
        )
    
    st.markdown("---")
    st.markdown("### 🎯 存錢加油進度條")
    # 趣味進度條
    progress_val = min(spendable_now / max(total_available_quota, 1), 1.0)
    st.progress(progress_val, text=f"可用額度使用比例：{int(progress_val * 100)}%")
    
    st.markdown("### 📖 最近的存錢紀錄")
    if not df.empty:
        st.dataframe(df.tail(5), use_container_width=True, hide_index=True)
    else:
        st.info("目前還沒有交易紀錄喔！")
        
    st.stop() # 小孩模式到此為止，不顯示後台編輯器

# ================= 💻 爸媽完整管理後台介面 =================
st.title(f"🏦 爸媽銀行數位存摺 - 【{name}】的管理後台")

st.markdown("### 📊 帳戶金額總覽（含複利利息）")
c1, c2, c3, c4 = st.columns(4)

with c1:
    st.metric(label="🟢 目前可花金額 (餘額)", value=f"${spendable_now:,}", delta="現在可以動用的錢")
with c2:
    st.metric(label="💰 總存款 (含利息)", value=f"${total_balance:,}", delta=f"本金 ${base_balance:,} + 利息 ${earned_interest:,}", delta_color="off")
with c3:
    st.metric(label=f"📈 累積紅利利息 ({int(annual_rate*100)}%年利率)", value=f"${earned_interest:,}")
with c4:
    st.metric(label="💸 累計已支出", value=f"${total_expense:,}")

st.markdown("---")

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

# ================= 3. 側邊欄：5 名小孩設定與 QR Code =================
with st.sidebar:
    st.markdown("---")
    st.subheader(f"⚙️ 【{name}】帳戶與利息設定")
    new_name = st.text_input("小孩名稱", value=name)
    new_ratio = st.slider("可用金額比例 (%)", 10, 100, int(ratio * 100), 5)
    
    # 新增年利率設定填入
    new_interest_pct = st.number_input("年利率設定 (%)", min_value=0.0, max_value=50.0, value=float(annual_rate * 100), step=0.5)
    
    if st.button("儲存帳戶與利率設定", use_container_width=True):
        post_to_sheet({
            "action": "update_settings",
            "kid_id": selected_kid,
            "new_name": new_name,
            "new_ratio": new_ratio / 100.0,
            "new_interest_rate": new_interest_pct / 100.0
        })
        st.success("設定已更新！")
        st.rerun()

    st.markdown("---")
    st.subheader("🖨️ 專屬查帳 QR Code")
    auto_url = get_auto_base_url()
    raw_url = st.text_input(
        "你的 Streamlit 網址",
        value=auto_url if auto_url else "https://你的網址.streamlit.app"
    )
    clean_base_url = raw_url.split("?")[0].rstrip("/")
    target_url = f"{clean_base_url}/?kid={selected_kid}"
    
    if "你的網址" not in clean_base_url and clean_base_url.startswith("http"):
        encoded_url = urllib.parse.quote(target_url, safe="")
        qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=220x220&data={encoded_url}"
        st.image(qr_api_url, caption=f"掃描直接看【{name}】的童趣時速表")
        st.code(target_url, language="text")
