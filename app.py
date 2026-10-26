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
    .lazy-report { padding: 20px; border-radius: 12px; background-color: #f8fafc; border: 2px solid #cbd5e1; margin-bottom: 20px; }
    .black-swan-alert { padding: 18px; border-radius: 10px; background-color: #fef2f2; border-left: 6px solid #dc2626; margin-bottom: 20px; }
    .good-news-alert { padding: 18px; border-radius: 10px; background-color: #f0fdf4; border-left: 6px solid #16a34a; margin-bottom: 20px; }
    .buy-zone-card { padding: 18px; border-radius: 10px; background-color: #f0fdf4; border-left: 6px solid #16a34a; margin-bottom: 15px; }
    .plan-card { padding: 18px; border-radius: 10px; background-color: #faf5ff; border-left: 6px solid #9333ea; margin-bottom: 15px; }
    .reminder-box { padding: 12px 16px; border-radius: 8px; background-color: #fffbeb; border-left: 4px solid #f59e0b; margin-bottom: 15px; font-size: 15px; }
    .log-box { padding: 12px; border-radius: 8px; background-color: #f1f5f9; border: 1px solid #e2e8f0; font-size: 13px; }
</style>
""", unsafe_allow_html=True)

# ================= Session State 初始化 (底仓、日志与对账时间) =================
if "held_shares" not in st.session_state:
    st.session_state.held_shares = 10
if "avg_cost" not in st.session_state:
    st.session_state.avg_cost = 120.0
if "last_check_date" not in st.session_state:
    st.session_state.last_check_date = datetime.now()
if "audit_logs" not in st.session_state:
    st.session_state.audit_logs = [
        f"【{datetime.now().strftime('%Y-%m-%d %H:%M')}】系统初始化档案：默认持有 10 股，成本均价 $120.0"
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
st.sidebar.markdown("零金融门槛 · 自动算成本 · 突发风控")

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
        log_entry = f"【{datetime.now().strftime('%Y-%m-%d %H:%M')}】用户手动修改：从 {old_s}股(${old_c}) 变更为 {new_held_shares}股(${new_avg_cost}) [责任追溯：用户手动校准]"
        st.session_state.audit_logs.insert(0, log_entry)
        st.sidebar.success("✅ 底仓已同步！AI 已按最新数据重新规划长线方案。")
    else:
        st.session_state.last_check_date = datetime.now()
        st.sidebar.info("ℹ️ 确认完毕，底仓数据未变动。")

st.sidebar.markdown("---")
st.sidebar.subheader("📱 手机微信弹窗配置")
enable_push = st.sidebar.checkbox("开启买点与黑天鹅微信实时弹窗", value=True)
serverchan_key = st.sidebar.text_input("填入 Server酱 SendKey:", type="password")
if st.sidebar.button("🔔 发送一条测试弹窗到手机微信"):
    if serverchan_key:
        ok = send_wechat_alert(serverchan_key, f"【测试成功】{ticker_symbol} 盯盘哨兵已就绪", "你的手机微信已成功连接 AI 投资管家！遇到突发大新闻或跌入黄金买点时，将第一时间为您弹窗。")
        if ok:
            st.sidebar.success("✅ 发送成功！请看一眼你的手机微信。")
        else:
            st.sidebar.error("❌ 发送失败，请检查 SendKey 是否复制完整。")
    else:
        st.sidebar.warning("⚠️ 请先在上方输入框填入 SendKey。")

# ================= 核心数据抓取与技术/情绪计算 =================
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

def calculate_indicators(df):
    data = df.copy()
    data["SMA20"] = data["Close"].rolling(window=20, min_periods=5).mean()
    data["SMA50"] = data["Close"].rolling(window=50, min_periods=10).mean()
    data["SMA200"] = data["Close"].rolling(window=200, min_periods=30).mean()
    std20 = data["Close"].rolling(window=20, min_periods=5).std()
    data["BB_Lower"] = data["SMA20"] - 2 * std20
    data["Vol_Avg20"] = data["Volume"].rolling(window=20, min_periods=5).mean()
    
    delta = data["Close"].diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=14, min_periods=5).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=14, min_periods=5).mean()
    rs = gain / loss.replace(0, np.nan)
    data["RSI"] = (100 - (100 / (1 + rs))).fillna(50)
    return data

# ================= 主界面渲染 =================
st.title(f"📊 {ticker_symbol} 私人 AI 投研管家与筹码指挥所")

# 1. 温和定期对账提醒横幅
days_since_check = (datetime.now() - st.session_state.last_check_date).days
st.markdown(f"""
<div class="reminder-box">
    💡 <b>管家贴心提醒：</b> 你当前在软件登记的底仓为 <b>{st.session_state.held_shares} 股</b>（均价 <b>${st.session_state.avg_cost}</b>）。如果你近期在证券 App 里私下买卖过股票，记得随时在左侧边栏修改校准，以免影响 AI 为你计算 <b>{target_total_shares} 股</b>长线计划的精准度哦！
</div>
""", unsafe_allow_html=True)

with st.spinner("AI 正在实时扫描全球行情、机构动向、突发新闻与最优成本防线..."):
    hist, info, news_titles = fetch_all_market_data(ticker_symbol)

if hist is None or hist.empty or len(hist) < 5:
    st.error(f"⚠️ 暂未获取到 `{ticker_symbol}` 的行情数据，请检查代码拼写或稍后刷新。")
    st.stop()

df = calculate_indicators(hist)
latest = df.iloc[-1]
prev = df.iloc[-2] if len(df) > 1 else latest

current_price = float(latest["Close"])
daily_change_pct = ((current_price - float(prev["Close"])) / float(prev["Close"])) * 100
sma20 = float(latest["SMA20"])
sma50 = float(latest["SMA50"])
sma200 = float(latest["SMA200"]) if not np.isnan(latest["SMA200"]) else float(df["Low"].min())
bb_lower = float(latest["BB_Lower"]) if not np.isnan(latest["BB_Lower"]) else current_price * 0.94
rsi = float(latest["RSI"])
vol_ratio = float(latest["Volume"] / latest["Vol_Avg20"]) if latest["Vol_Avg20"] > 0 else 1.0

# ================= 2. 突发黑天鹅 / 重大异动秒级监控雷达 =================
is_black_swan_drop = daily_change_pct <= -4.5 or (daily_change_pct <= -3.0 and vol_ratio > 1.8)
is_super_rally = daily_change_pct >= 4.5 or (daily_change_pct >= 3.0 and vol_ratio > 1.8)

# 结合突发异动动态修正支撑防线
support_candidates = [val for val in [bb_lower, float(df["Low"].tail(20).min()), min(sma20, sma50), sma200] if val < current_price]
base_optimal_price = np.median(support_candidates) if support_candidates else current_price * 0.92

if is_black_swan_drop:
    # 突发利空砸盘，防线自动下移 4% 防止接飞刀
    optimal_buy_price = base_optimal_price * 0.96
    st.markdown(f"""
    <div class="black-swan-alert">
        <h4 style="margin-top:0; color:#991b1b;">🚨 【秒级突发警报】检测到市场剧烈砸盘 / 突发利空异动！（今日跌幅 {daily_change_pct:.2f}%，成交量放大 {vol_ratio:.1f} 倍）</h4>
        <p style="margin-bottom:0; color:#1f2937;">
        <b>大白话解读：</b> 当前可能有突发宏观消息、地缘冲突或大资金恐慌抛售。为保护你的资金安全，<b>AI 已自动将原本的买点防线向下紧急下调 4%</b>，切勿盲目提前抄底接飞刀！
        </p>
    </div>
    """, unsafe_allow_html=True)
elif is_super_rally:
    # 突发重大利好/超级大单，防线适度上移
    optimal_buy_price = base_optimal_price * 1.02
    st.markdown(f"""
    <div class="good-news-alert">
        <h4 style="margin-top:0; color:#166534;">🔥 【秒级突发利好】检测到大资金抢筹 / 重大利好爆发！（今日暴涨 {daily_change_pct:+.2f}%，成交量放大 {vol_ratio:.1f} 倍）</h4>
        <p style="margin-bottom:0; color:#1f2937;">
        <b>大白话解读：</b> 市场可能刚爆出核心大订单或超预期财报，机构与游资正在抱团涌入。AI 已将回踩建仓防线动态上调，避免你踏空长线行情。
        </p>
    </div>
    """, unsafe_allow_html=True)
else:
    optimal_buy_price = base_optimal_price

optimal_buy_low = round(optimal_buy_price * 0.985, 2)
optimal_buy_high = round(optimal_buy_price * 1.015, 2)

# 计算长线 100 股筹码缺口与预计最终成本
shares_needed = max(0, target_total_shares - st.session_state.held_shares)
current_total_cost = st.session_state.held_shares * st.session_state.avg_cost
if shares_needed > 0:
    predicted_final_cost = (current_total_cost + (shares_needed * optimal_buy_price)) / target_total_shares
    recommended_batch = max(1, min(int(shares_needed * 0.25), shares_needed))
else:
    predicted_final_cost = st.session_state.avg_cost
    recommended_batch = 0

# ================= 3. 一分钟懒人极简早报 (大白话解读) =================
st.subheader("☕ 一分钟懒人极简简报（零门槛大白话版）")

inst_hold = info.get("heldPercentInstitutions", None)
inst_text = f"华尔街大机构目前死死拿住了该股 **{inst_hold*100:.1f}%** 的筹码，主力底盘非常稳。" if inst_hold else "大资金与机构目前处于常态化持仓博弈中。"
target_mean = info.get("targetMeanPrice", None)
target_text = f"华尔街分析师给出的长线合理目标均价在 **${target_mean}** 附近。" if target_mean else ""

if rsi > 70:
    mood_text = "🔥 **极度过热（游资/散户正在疯狂追高）** —— 千万别在这个时候跟着冲动买单！"
elif rsi < 35:
    mood_text = "🧊 **过度恐慌（市场正在错杀甩卖）** —— 别人恐惧我贪婪，现在正是长线捡便宜筹码的好时候！"
else:
    mood_text = "🌤️ **情绪平稳（正常震荡洗盘）** —— 没有极端疯涨或暴跌，按既定计划守株待兔即可。"

action_conclusion = (
    f"🟢 **今天能不能买？能！** 当前现价（**${current_price:.2f}**）已经掉进 AI 算出的黄金便宜区间（**${optimal_buy_low} - ${optimal_buy_high}**），建议今天分批买入 **{recommended_batch} 股**！"
    if (shares_needed > 0 and current_price <= optimal_buy_high)
    else f"🔴 **今天能不能买？先别买，忍住！** 当前现价（**${current_price:.2f}**）还不够便宜。请提前在券商软件里挂好 **${optimal_buy_low} - ${optimal_buy_high}** 的低价买单，等它自己跌下来成交。"
)

st.markdown(f"""
<div class="lazy-report">
    <p style="font-size:16px; margin-bottom:10px;"><b>1. 🌡️ 今日市场情绪与游资动向：</b> {mood_text}</p>
    <p style="font-size:16px; margin-bottom:10px;"><b>2. 🐳 财报基本面与大资金底牌：</b> {inst_text} {target_text}</p>
    <p style="font-size:16px; margin-bottom:10px;"><b>3. 📰 最新全球时事与外媒风向：</b> {news_titles[0] if news_titles else '今日暂无影响长线逻辑的极端突发负面新闻，公司业务正常运转。'}</p>
    <hr style="margin:12px 0;">
    <p style="font-size:18px; margin-bottom:0; color:#0f172a;"><b>🎯 最终傻瓜式操作结论：</b> {action_conclusion}</p>
</div>
""", unsafe_allow_html=True)

# 触发条件时自动发微信通知
if enable_push and serverchan_key:
    if (shares_needed > 0 and current_price <= optimal_buy_high) or is_black_swan_drop or is_super_rally:
        alert_title = f"【AI管家提醒】{ticker_symbol} 现价 ${current_price:.2f} 触发关键信号！"
        alert_body = f"{action_conclusion}\n\nAI黄金买点区间：${optimal_buy_low} - ${optimal_buy_high}\n预计达成{target_total_shares}股后的最终均价：${predicted_final_cost:.2f}"
        send_wechat_alert(serverchan_key, alert_title, alert_body)

# ================= 4. 100股长线筹码与成本自动精算面板 =================
st.subheader(f"🧮 {target_total_shares} 股长线建仓进度与 AI 成本动态精算")
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("📦 距离目标还差", f"{shares_needed} 股", f"已持 {st.session_state.held_shares} / 目标 {target_total_shares} 股")
with c2:
    st.metric("💰 当前最新市价", f"${current_price:.2f}", f"{daily_change_pct:+.2f}%")
with c3:
    st.metric("🛡️ AI 算出的最佳买入价", f"${optimal_buy_low} - ${optimal_buy_high}", "动态支撑防线")
with c4:
    st.metric("📉 买满后的预计最终均价", f"${predicted_final_cost:.2f}", f"当前你的成本 ${st.session_state.avg_cost}")

# ================= 5. 历史修改与责任追溯审计日志 =================
with st.expander("📜 查看底仓变更历史与操作责任审计日志（点击展开）"):
    st.markdown("<div class='log-box'>", unsafe_allow_html=True)
    for log in st.session_state.audit_logs:
        st.write(log)
    st.markdown("</div>", unsafe_allow_html=True)

# ================= 6. K线走势与黄金买点防线图 =================
st.markdown("---")
st.subheader("📈 股价走势与 AI 黄金建仓防线可视化")
fig = go.Figure()
fig.add_trace(go.Scatter(x=df.index, y=df["Close"], mode="lines", name="收盘价", line=dict(color="#0f172a", width=2)))
fig.add_trace(go.Scatter(x=df.index, y=df["SMA20"], mode="lines", name="20日短期趋势线", line=dict(color="#f59e0b", width=1.5, dash="dot")))
fig.add_trace(go.Scatter(x=df.index, y=df["SMA200"], mode="lines", name="200日牛熊分界线", line=dict(color="#3b82f6", width=1.5)))
fig.add_hrect(
    y0=optimal_buy_low, y1=optimal_buy_high,
    fillcolor="#22c55e", opacity=0.25,
    line_width=1, line_color="#16a34a",
    annotation_text=f"AI 黄金买点区间 (${optimal_buy_low} - ${optimal_buy_high})"
)
fig.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10), hovermode="x unified")
st.plotly_chart(fig, use_container_width=True)
