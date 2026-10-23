import streamlit as st
import pandas as pd
import requests
from datetime import datetime, date
import re
import urllib.parse

# ================= 設定區 =================
st.set_page_config(page_title="家庭小金庫系統", page_icon="🪙", layout="wide")

# 請替換為您的 Google Apps Script 網頁應用程式網址與部署 URL
GAS_URL = st.secrets.get("GAS_URL", "https://script.google.com/macros/s/AKfycbxfSRHmom9AE2qVilpbGDFShNu1JgQDq1jw1IBPrzqVwrBDKh3XqK7hs4fxG3JLzp61/exec")
APP_BASE_URL = st.secrets.get("APP_BASE_URL", "http://localhost:8501")

# ================= 輔助函式 =================
def clean_date_str(val):
    """將任何英文日期字串 (如 Fri Jul 11 2025...) 強制轉為純數字 2025/07/11"""
    if pd.isna(val) or not str(val).strip():
        return ""
    s = str(val).strip()
    m = re.match(r"^(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})", s)
    if m:
        return f"{int(m.group(1)):04d}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"
    s_clean = re.sub(r"\s*\(.*?\)", "", s)
    s_clean = re.sub(r"\s*GMT[+-]\d{4}", "", s_clean)
    try:
        dt = pd.to_datetime(s_clean)
        return dt.strftime("%Y/%m/%d")
    except Exception:
        return s

@st.cache_data(ttl=10)
def fetch_all_data():
    resp = requests.get(GAS_URL, timeout=15)
    resp.raise_for_status()
    return resp.json()

def calculate_account_metrics(records, available_ratio, interest_rate):
    """計算本金餘額、年利率累積利息、含息總餘額、含息可用餘額"""
    today = date.today()
    total_income = 0
    total_expense = 0
    total_interest = 0.0
    last_valid_date = today

    cleaned_records = []
    running_principal = 0

    for r in records:
        d_str = clean_date_str(r.get("date", ""))
        inc = int(float(r.get("income", 0) or 0))
        exp = int(float(r.get("expense", 0) or 0))
        note = str(r.get("note", "") or "")

        if d_str:
            try:
                tx_date = datetime.strptime(d_str, "%Y/%m/%d").date()
                last_valid_date = tx_date
            except Exception:
                tx_date = last_valid_date
        else:
            tx_date = last_valid_date
            d_str = tx_date.strftime("%Y/%m/%d")

        # 計算該筆收支距今天數與單利年息
        days_held = max(0, (today - tx_date).days)
        net_flow = inc - exp
        total_interest += net_flow * float(interest_rate) * (days_held / 365.0)

        total_income += inc
        total_expense += exp
        running_principal += net_flow

        cleaned_records.append({
            "日期": d_str,
            "收入": inc,
            "支出": exp,
            "備註": note,
            "餘額": running_principal
        })

    earned_interest = max(0, int(round(total_interest)))
    principal_balance = total_income - total_expense
    
    # 1. 總餘額 (本金餘額 + 利息)
    total_balance_with_interest = principal_balance + earned_interest
    
    # 2. 可用總額度 (總收入 * 可用比例 + 利息) 與 目前可用金額
    available_quota = int(round(total_income * float(available_ratio))) + earned_interest
    available_balance = available_quota - total_expense
    locked_savings = total_balance_with_interest - available_balance

    return {
        "records": cleaned_records,
        "total_income": total_income,
        "total_expense": total_expense,
        "principal_balance": principal_balance,
        "interest": earned_interest,
        "total_balance": total_balance_with_interest,
        "available_quota": available_quota,
        "available_balance": available_balance,
        "locked_savings": locked_savings
    }

def render_speedometer_html(name, total_balance, available_balance, interest, available_quota):
    """繪製小孩容易理解的時速表/能量儀表板（無空行與縮排，避免被 Streamlit 誤判為程式碼區塊）"""
    ratio = max(0.0, min(1.0, available_balance / max(available_quota, 1)))
    angle = -90 + (ratio * 180)
    
    if ratio >= 0.6:
        status_text = "🟢 能量滿滿！可以安心規劃小願望"
        needle_color = "#10b981"
    elif ratio >= 0.25:
        status_text = "🟡 能量適中！花錢前記得想一想喔"
        needle_color = "#f59e0b"
    else:
        status_text = "🔴 快沒油啦！多存一點錢讓指針往右跑吧"
        needle_color = "#ef4444"

    raw_html = f"""
<div style="font-family: 'Microsoft JhengHei', sans-serif; max-width: 680px; margin: 0 auto; padding: 24px 20px; background: linear-gradient(145deg, #ffffff, #f3f6fb); border-radius: 24px; box-shadow: 0 10px 25px rgba(0,0,0,0.08); text-align: center;">
<h2 style="margin-bottom: 6px; color: #1e293b; font-size: 30px; font-weight: 900;">🪙 {name}的小金庫</h2>
<p style="color: #64748b; margin-top: 0; margin-bottom: 12px; font-size: 16px;">{status_text}</p>
<div style="position: relative; width: 320px; height: 185px; margin: 10px auto 5px auto;">
<svg viewBox="0 0 200 115" width="100%" height="100%">
<path d="M 20 100 A 80 80 0 0 1 60 30.7" fill="none" stroke="#ef4444" stroke-width="18" stroke-linecap="round"/>
<path d="M 63 29 A 80 80 0 0 1 137 29" fill="none" stroke="#f59e0b" stroke-width="18" />
<path d="M 140 30.7 A 80 80 0 0 1 180 100" fill="none" stroke="#10b981" stroke-width="18" stroke-linecap="round"/>
<text x="15" y="114" font-size="9" fill="#64748b" text-anchor="middle">$0</text>
<text x="100" y="14" font-size="9" fill="#64748b" text-anchor="middle">一半</text>
<text x="185" y="114" font-size="9" fill="#64748b" text-anchor="middle">${available_quota:,}</text>
<g transform="translate(100, 100) rotate({angle})">
<polygon points="-4,0 0,-72 4,0" fill="{needle_color}" />
<circle cx="0" cy="0" r="8" fill="#1e293b" />
</g>
</svg>
</div>
<div style="margin-top: -10px; margin-bottom: 24px;">
<span style="font-size: 15px; color: #475569; font-weight: bold;">目前可花用指針位置：</span>
<span style="font-size: 26px; font-weight: 900; color: {needle_color};">${available_balance:,}</span>
</div>
<div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 10px;">
<div style="background: #ecfdf5; border: 2px solid #6ee7b7; border-radius: 18px; padding: 16px 8px;">
<div style="font-size: 28px;">🚀</div>
<div style="font-size: 15px; color: #065f46; font-weight: bold; margin-top: 4px;">可用金額</div>
<div style="font-size: 26px; font-weight: 900; color: #047857; margin-top: 4px;">${available_balance:,}</div>
<div style="font-size: 12px; color: #059669;">現在可以花的錢</div>
</div>
<div style="background: #eff6ff; border: 2px solid #93c5fd; border-radius: 18px; padding: 16px 8px;">
<div style="font-size: 28px;">🏦</div>
<div style="font-size: 15px; color: #1e40af; font-weight: bold; margin-top: 4px;">總餘額</div>
<div style="font-size: 26px; font-weight: 900; color: #1d4ed8; margin-top: 4px;">${total_balance:,}</div>
<div style="font-size: 12px; color: #2563eb;">存摺裡的全部錢</div>
</div>
<div style="background: #fefce8; border: 2px solid #fde047; border-radius: 18px; padding: 16px 8px;">
<div style="font-size: 28px;">🌱</div>
<div style="font-size: 15px; color: #854d0e; font-weight: bold; margin-top: 4px;">利息獎勵</div>
<div style="font-size: 26px; font-weight: 900; color: #ca8a04; margin-top: 4px;">+${interest:,}</div>
<div style="font-size: 12px; color: #a16207;">存錢長出來的小錢</div>
</div>
</div>
</div>
"""
    return "\n".join(line.strip() for line in raw_html.splitlines() if line.strip())

# ================= 主程式流程 =================
try:
    all_data = fetch_all_data()
except Exception as e:
    st.error(f"無法連線至 Google 試算表，請確認 GAS_URL 設定是否正確：{e}")
    st.stop()

kid_ids = list(all_data.keys())
if not kid_ids:
    st.warning("目前尚無小孩帳戶資料。")
    st.stop()

# 檢查網址參數是否為掃描 QR Code 進入 (例如 ?kid=kid1)
query_params = st.query_params
qr_kid_id = query_params.get("kid", None)

# 若為掃描 QR Code 進入，直接顯示小孩專屬小金庫頁面
if qr_kid_id and qr_kid_id in all_data:
    kid_info = all_data[qr_kid_id]
    metrics = calculate_account_metrics(
        kid_info.get("records", []),
        kid_info.get("available_ratio", 0.3),
        kid_info.get("interest_rate", 0.05)
    )
    st.markdown(
        render_speedometer_html(
            kid_info["name"],
            metrics["total_balance"],
            metrics["available_balance"],
            metrics["interest"],
            metrics["available_quota"]
        ),
        unsafe_allow_html=True
    )
    st.stop()

# ================= 爸媽管理與完整檢視模式 =================
st.sidebar.title("👨‍👩‍👧‍👦 小金庫管理後台")
selected_kid = st.sidebar.selectbox(
    "選擇小孩帳戶",
    options=kid_ids,
    format_func=lambda k: f"{all_data[k]['name']}的小金庫 ({k})"
)

view_mode = st.sidebar.radio("切換檢視畫面", ["📊 爸媽管理與存摺明細", "🪙 預覽小孩小金庫時速表"])

current_kid = all_data[selected_kid]
cur_ratio = float(current_kid.get("available_ratio", 0.30))
cur_rate = float(current_kid.get("interest_rate", 0.05))
metrics = calculate_account_metrics(current_kid.get("records", []), cur_ratio, cur_rate)

# 側邊欄：QR Code 產生器
st.sidebar.markdown("---")
st.sidebar.subheader(f"📱 {current_kid['name']}的小金庫 QR Code")
kid_qr_url = f"{APP_BASE_URL}/?kid={selected_kid}"
qr_img_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={urllib.parse.quote(kid_qr_url)}"
st.sidebar.image(qr_img_url, caption=f"掃描查看 {current_kid['name']}的小金庫", width=180)
st.sidebar.caption(f"專屬連結：`{kid_qr_url}`")

# 側邊欄：爸媽設定區 (含年利率設定)
st.sidebar.markdown("---")
with st.sidebar.expander("⚙️ 修改當前小孩設定 (比例 / 年利率)", expanded=False):
    new_name = st.text_input("小孩名稱", value=current_kid["name"])
    new_ratio_pct = st.slider("可用額度比例 (%)", min_value=0, max_value=100, value=int(round(cur_ratio * 100)), step=5)
    new_rate_pct = st.number_input("年利率 (%)", min_value=0.0, max_value=100.0, value=round(cur_rate * 100, 1), step=0.5)
    
    if st.button("💾 儲存設定", use_container_width=True):
        payload = {
            "action": "update_settings",
            "kid_id": selected_kid,
            "new_name": new_name,
            "new_ratio": new_ratio_pct / 100.0,
            "new_interest_rate": new_rate_pct / 100.0
        }
        requests.post(GAS_URL, json=payload)
        st.cache_data.clear()
        st.success("設定已更新！")
        st.rerun()

# 側邊欄：新增小孩功能 (上限 5 名)
with st.sidebar.expander(f"➕ 新增小孩小金庫 ({len(kid_ids)} / 5)", expanded=False):
    if len(kid_ids) >= 5:
        st.info("已達 5 名小孩上限！")
    else:
        add_name = st.text_input("新小孩名稱", placeholder="例如：Ray")
        add_ratio_pct = st.slider("初始可用比例 (%)", 0, 100, 30, 5, key="add_ratio")
        add_rate_pct = st.number_input("初始年利率 (%)", 0.0, 100.0, 5.0, 0.5, key="add_rate")
        add_init_dep = st.number_input("開戶初始存款 ($)", min_value=0, value=500, step=100)
        
        if st.button("✨ 立即開戶", use_container_width=True):
            if not add_name.strip():
                st.warning("請輸入小孩名稱！")
            else:
                payload = {
                    "action": "add_kid",
                    "name": add_name.strip(),
                    "ratio": add_ratio_pct / 100.0,
                    "interest_rate": add_rate_pct / 100.0,
                    "initial_deposit": add_init_dep
                }
                res = requests.post(GAS_URL, json=payload).json()
                if res.get("status") == "ok":
                    st.cache_data.clear()
                    st.success(f"已成功建立 {add_name}的小金庫！")
                    st.rerun()
                else:
                    st.error(res.get("message", "新增失敗"))

# ================= 畫面顯示 =================
if view_mode == "🪙 預覽小孩小金庫時速表":
    st.markdown(
        render_speedometer_html(
            current_kid["name"],
            metrics["total_balance"],
            metrics["available_balance"],
            metrics["interest"],
            metrics["available_quota"]
        ),
        unsafe_allow_html=True
    )
else:
    st.subheader(f"🪙 {current_kid['name']}的小金庫 — 金額總覽")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("🟢 目前可花金額 (含息)", f"${metrics['available_balance']:,}", "現在可以動用的錢")
    col2.metric("💰 總餘額 (含息總存款)", f"${metrics['total_balance']:,}", f"本金 ${metrics['principal_balance']:,} + 利息 ${metrics['interest']:,}")
    col3.metric(f"🌱 累積利息 (年利率 {cur_rate*100:.1f}%)", f"${metrics['interest']:,}", f"鎖定儲蓄 ${metrics['locked_savings']:,}")
    col4.metric(f"🧮 可用總額度 ({int(cur_ratio*100)}%+息)", f"${metrics['available_quota']:,}")
    col5.metric("💸 累計已支出", f"${metrics['total_expense']:,}")

    st.markdown("---")
    st.subheader("📖 收支明細表")
    st.caption("💡 日期已自動轉為 `YYYY/MM/DD` 數字格式，可直接雙擊表格新增或修改，完成後點選下方「儲存存摺變動」。")

    df = pd.DataFrame(metrics["records"])
    if df.empty:
        df = pd.DataFrame(columns=["日期", "收入", "支出", "備註", "餘額"])

    edited_df = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "日期": st.column_config.TextColumn("日期 (YYYY/MM/DD)", default=date.today().strftime("%Y/%m/%d")),
            "收入": st.column_config.NumberColumn("收入", min_value=0, default=0, step=10),
            "支出": st.column_config.NumberColumn("支出", min_value=0, default=0, step=10),
            "備註": st.column_config.TextColumn("備註", default=""),
            "餘額": st.column_config.NumberColumn("本金餘額 (自動計算)", disabled=True)
        },
        key=f"editor_{selected_kid}"
    )

    if st.button("💾 儲存存摺變動 (同時修復雲端日期格式)", type="primary"):
        new_records = []
        running_bal = 0
        for _, row in edited_df.iterrows():
            d_val = clean_date_str(row.get("日期", ""))
            inc_val = int(float(row.get("收入", 0) or 0))
            exp_val = int(float(row.get("支出", 0) or 0))
            note_val = str(row.get("備註", "") or "")
            if not d_val and inc_val == 0 and exp_val == 0 and not note_val:
                continue
            running_bal += (inc_val - exp_val)
            new_records.append({
                "date": d_val,
                "income": inc_val,
                "expense": exp_val,
                "note": note_val,
                "balance": running_bal
            })

        payload = {
            "action": "save_table",
            "kid_id": selected_kid,
            "records": new_records
        }
        requests.post(GAS_URL, json=payload)
        st.cache_data.clear()
        st.success("✅ 存摺明細與數字日期格式已成功同步至 Google 試算表！")
        st.rerun()
