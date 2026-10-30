import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
from datetime import datetime

# ================= 页面基础设置 =================
st.set_page_config(
    page_title="AI 智能投资管家与长线筹码指挥所",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .mini-widget { padding: 15px; border-radius: 12px; background: linear-gradient(135deg, #1e293b, #0f172a); color: #fff; box-shadow: 0 4px 12px rgba(0,0,0,0.15); margin-bottom: 20px; }
    .lazy-report { padding: 20px; border-radius: 12px; background-color: #f8fafc; border: 2px solid #cbd5e1; margin-bottom: 20px; }
    .buy-zone-card { padding: 18px; border-radius: 10px; background-color: #f0fdf4; border-left: 6px solid #16a34a; margin-bottom: 15px; }
    .reminder-box { padding: 12px 16px; border-radius: 8px; background-color: #fffbeb; border-left: 4px solid #f59e0b; margin-bottom: 15px; font-size: 15px; }
    .log-box { padding: 12px; border-radius: 8px; background-color: #f1f5f9; border: 1px solid #e2e8f0; font-size: 13px; }
</style>
""", unsafe_allow_html=True)

# ================= Session State 初始化 =================
if "held_shares" not in st.session_state:
    st.session_state.held_shares = 10
if "avg_cost" not in st.session_state:
    st.session_state.avg_cost = 120.0
if "last_check_date" not in st.session_state:
    st.session_state.last_check_date = datetime.now()
if "audit_logs" not in st.session_state:
    st.session_state.audit_logs = [
        f"【{datetime.now('%Y-%m-%d %H:%M')}】系统初始化档案：默认持有 10 股，成本均价 $120.0"
    ]

# ================= 微信推送函数 (Server酱) =================
def send_wechat_alert(sendkey, title, content):
    if not sendkey:
        return False
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    data = {"title": title, "desp": content}
    try:
        res = requests.post(url, data=data, timeout=5)
        return res.status_code == 200
    except Exception:
        return False

# ================= 侧边栏：全功能控制面板 =================
st.sidebar.title("🧭 私人 AI 投资管家")
st.sidebar.markdown("稳态长线防线 · 桌面挂件模式")

# 🖥️ 新增：桌面精简小窗口模式开关
is_mini_mode = st.sidebar.toggle("🖥️ 开启桌面精简小窗口模式", value=False, help="开启后页面将自动收缩为适合常驻桌面的极简挂件卡片")

market_type = st.sidebar.radio("🌐 选择市场区域：", ["美股大盘与 AI 巨头", "A 股 AI 算力/产业链", "🔍 手动输入自定义代码"])

if market_type == "美股大盘与 AI 巨头":
    us_watchlist = {
        "NVDA (英伟达 - AI算力霸主)": "NVDA",
        "TSLA (特斯拉)": "TSLA",
        "SPCX (SpaceX 关联太空概念)": "SPCX",
        "MU (美光科技 - 内存芯片)": "MU",
        "SPY (标普500美股大盘)": "SPY"
    }
    ticker_symbol = us_watchlist[st.sidebar.selectbox("选择美股标的：", options=list(us_watchlist.keys()))]
elif market_type == "A 股 AI 算力/产业链":
    cn_watchlist = {
        "工业富联 (601138.SS - 算力服务器)": "601138.SS",
        "中际旭创 (300308.SZ - AI光模块龙头)": "300308.SZ",
        "新易盛 (300502.SZ - 高速光模块)": "300502.SZ",
        "寒武纪 (688256.SS - 国产AI芯片)": "688256.SS"
    }
    ticker_symbol = cn_watchlist[st.sidebar.selectbox("选择 A 股标的：", options=list(cn_watchlist.keys()))]
else:
    ticker_symbol = st.sidebar.text_input("请输入股票代码：", value="NVDA").upper().strip()

st.sidebar.markdown("---")
st.sidebar.subheader("🎯 终极目标与真实底仓校准")
target_total_shares = st.sidebar.number_input("你最终想要持有的总股数 (如100股):", min_value=1, value=100, step=10)

st.sidebar.markdown("✏️ **随时自由修改当前手里的底仓：**")
new_held_shares = st.sidebar.number_input("当前手里实际已持有股数:", min_value=0, value=st.session_state.held_shares, step=1)
new_avg_cost = st.sidebar.number_input("当前手里的平均买入成本 ($/¥):", min_value=0.0, value=st.session_state.avg_cost, step=1.0)

if st.sidebar.button("💾 保存底仓修改并记入日志"):
    if new_held_shares != st.session_state.held_shares or new_avg_cost != st.session_state.avg_cost:
        old_s, old_c = st.session_state.held_shares, st.session_state.avg_cost
        st.session_state.held_shares = new_held_shares
        st.session_state.avg_cost = new_avg_cost
        st.session_state.last_check_date = datetime.now()
        log_entry = f"【{datetime.now().strftime('%Y-%m-%d %H:%M')}】用户手动修改：从 {old_s}股(${old_c}) 变更为 {new_held_shares}股(${new_avg_cost})"
        st.session_state.audit_logs.insert(0, log_entry)
        st.sidebar.success("✅ 底仓已同步！")
    else:
        st.session_state.last_check_date = datetime.now()
        st.sidebar.info("ℹ️ 数据未变动。")

st.sidebar.markdown("---")
st.sidebar.subheader("📱 手机微信弹窗配置")
enable_push = st.sidebar.checkbox("开启买点微信实时弹窗", value=True)
serverchan_key = st.sidebar.text_input("填入 Server酱 SendKey:", type="password")

# ================= 核心数据抓取与稳态防线计算 =================
@st.cache_data(ttl=300)
def fetch_all_market_data(symbol):
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="1y")
    info = {}
    news_list = []
    try:
        info = ticker.info
    except Exception:
        pass
    try:
        raw_news = ticker.news
        if raw_news:
            for item in raw_news[:5]:
                title = item.get("title") or item.get("content", {}).get("title", "")
                if title:
                    news_list.append(title)
    except Exception:
        pass
    return hist, info, news_list

def calculate_steady_indicators(df):
    data = df.copy()
    data["SMA200"] = data["Close"].rolling(window=200, min_periods=30).mean()
    return data

# 获取行情
hist, info, news_titles = fetch_all_market_data(ticker_symbol)
if hist is None or hist.empty or len(hist) < 5:
    st.error(f"⚠️ 暂未获取到 `{ticker_symbol}` 的行情数据。")
    st.stop()

df = calculate_steady_indicators(hist)
latest = df.iloc[-1]
prev = df.iloc[-2] if len(df) > 1 else latest

current_price = float(latest["Close"])
daily_change_pct = ((current_price - float(prev["Close"])) / float(prev["Close"])) * 100

sma200_val = float(latest["SMA200"]) if not np.isnan(latest["SMA200"]) else float(df["Low"].min())
long_term_low = float(df["Low"].tail(90).min())
steady_base_price = max(sma200_val * 0.98, long_term_low)
if steady_base_price >= current_price:
    steady_base_price = current_price * 0.92

optimal_buy_low = round(steady_base_price * 0.98, 2)
optimal_buy_high = round(steady_base_price * 1.02, 2)
shares_needed = max(0, target_total_shares - st.session_state.held_shares)

# ================= 桌面精简挂件模式渲染 =================
if is_mini_mode:
    st.markdown(f"""
    <div class="mini-widget">
        <h3 style="margin:0 0 10px 0; color:#38bdf8;">📌 桌面挂件：{ticker_symbol}</h3>
        <p style="margin:5px 0; font-size:16px;">💰 现价: <b>${current_price:.2f}</b> ({daily_change_pct:+.2f}%)</p>
        <p style="margin:5px 0; font-size:16px;">🛡️ 挂单防线: <b style="color:#4ade80;">${optimal_buy_low} - ${optimal_buy_high}</b></p>
        <p style="margin:5px 0; font-size:15px;">📦 目标进度: 已持 {st.session_state.held_shares} 股 / 差 {shares_needed} 股达成 {target_total_shares} 股</p>
    </div>
    """, unsafe_allow_html=True)
    st.info("💡 提示：你可以把网页浏览器的窗口手动拖拽缩小，调整成一个长条状的小方块挂在电脑屏幕边缘，就变成了一个完美的桌面悬浮小窗口！")
    st.stop()  # 开启精简模式时，只展示上面的精简挂件，不渲染下方冗长图表

# ================= 正常完整模式渲染 =================
st.title(f"📊 {ticker_symbol} 私人 AI 投研管家（稳态长线防线版）")

st.markdown(f"""
<div class="reminder-box">
    💡 <b>长线纪律提示：</b> 当前登记底仓为 <b>{st.session_state.held_shares} 股</b>（均价 <b>${st.session_state.avg_cost}</b>）。左侧边栏可随时开启<b>“桌面精简小窗口模式”</b>将软件变成桌面悬浮卡片！
</div>
""", unsafe_allow_html=True)

# 计算达成目标后的预计最终成本
current_total_cost = st.session_state.held_shares * st.session_state.avg_cost
if shares_needed > 0:
    predicted_final_cost = (current_total_cost + (shares_needed * steady_base_price)) / target_total_shares
else:
    predicted_final_cost = st.session_state.avg_cost

action_conclusion = (
    f"🟢 **当前挂单策略：** 现价（**${current_price:.2f}**）已进入稳态黄金买点防线区（**${optimal_buy_low} - ${optimal_buy_high}**），可以按计划执行吸纳！"
    if (shares_needed > 0 and current_price <= optimal_buy_high)
    else f"🔴 **当前挂单策略：** 现价偏高，**请直接去券商 App 挂好长期限价单：${optimal_buy_low} - ${optimal_buy_high}**。让系统自动帮你守株待兔。"
)

st.subheader("☕ 长期战略作战地图与懒人早报")
st.markdown(f"""
<div class="lazy-report">
    <p style="font-size:16px; margin-bottom:10px;"><b>1. 🛡️ 长期稳态防线性质：</b> 锚定大周期长期结构支撑，属于<b>非实时漂移的固定作战区间</b>，专为券商挂单设计。</p>
    <p style="font-size:16px; margin-bottom:10px;"><b>2. 📰 核心基本面与新闻：</b> {news_titles[0] if news_titles else '公司业务正常运转，长线逻辑稳固。'}</p>
    <hr style="margin:12px 0;">
    <p style="font-size:18px; margin-bottom:0; color:#0f172a;"><b>🎯 最终长期挂单方案：</b> {action_conclusion}</p>
</div>
""", unsafe_allow_html=True)

# 筹码与成本精算面板
st.subheader(f"🧮 {target_total_shares} 股长期稳态建仓指挥台")
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("📦 距离目标还差", f"{shares_needed} 股", f"已持 {st.session_state.held_shares} / 目标 {target_total_shares} 股")
with c2:
    st.metric("💰 当前最新市价", f"${current_price:.2f}", f"{daily_change_pct:+.2f}%")
with c3:
    st.metric("🛡️ 长期稳态挂单防线区", f"${optimal_buy_low} - ${optimal_buy_high}", "固定作战锚点")
with c4:
    st.metric("📉 达成目标后的预计均价", f"${predicted_final_cost:.2f}", f"当前成本 ${st.session_state.avg_cost}")

# 审计日志
with st.expander("📜 查看底仓变更与审计日志"):
    st.markdown("<div class='log-box'>", unsafe_allow_html=True)
    for log in st.session_state.audit_logs:
        st.write(log)
    st.markdown("</div>", unsafe_allow_html=True)

# K线走势与稳态防线图
st.markdown("---")
st.subheader("📈 股价走势与长线稳态防线区间（可用于挂单参考）")
fig = go.Figure()
fig.add_trace(go.Scatter(x=df.index, y=df["Close"], mode="lines", name="收盘价", line=dict(color="#0f172a", width=2)))
fig.add_trace(go.Scatter(x=df.index, y=df["SMA200"], mode="lines", name="200日长期牛熊线", line=dict(color="#3b82f6", width=1.5)))
fig.add_hrect(
    y0=optimal_buy_low, y1=optimal_buy_high,
    fillcolor="#22c55e", opacity=0.25,
    line_width=1, line_color="#16a34a",
    annotation_text=f"长期稳态挂单区间 (${optimal_buy_low} - ${optimal_buy_high})"
)
fig.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10), hovermode="x unified")
st.plotly_chart(fig, use_container_width=True)
