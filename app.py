import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import google.generativeai as genai
import requests
from datetime import datetime

# ================= 页面基础设置 =================
st.set_page_config(
    page_title="AI 智能股票盯盘与安卓通知参谋",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .signal-box { padding: 20px; border-radius: 12px; margin-bottom: 20px; font-size: 18px; line-height: 1.6; }
    .buy-zone-card { padding: 18px; border-radius: 10px; background-color: #f0fdf4; border-left: 6px solid #16a34a; margin-bottom: 15px; }
    .deep-zone-card { padding: 18px; border-radius: 10px; background-color: #eff6ff; border-left: 6px solid #2563eb; margin-bottom: 15px; }
</style>
""", unsafe_allow_html=True)

# ================= 侧边栏：多市场自选与安卓推送设置 =================
st.sidebar.title("🧭 智能盯盘与安卓通知控制台")
st.sidebar.markdown("专为安卓用户打造的美股/A股双市场盯盘参谋。")

market_type = st.sidebar.radio("🌐 选择市场区域：", ["美股大盘与 AI 巨头", "A 股 AI 算力/产业链", "🔍 手动输入自定义代码"])

if market_type == "美股大盘与 AI 巨头":
    us_watchlist = {
        "NVDA (英伟达 - AI算力霸主)": "NVDA",
        "TSLA (特斯拉)": "TSLA",
        "SPCX (SpaceX 太空探索)": "SPCX",
        "MU (美光科技 - 内存芯片)": "MU",
        "SPY (标普500美股大盘)": "SPY"
    }
    ticker_symbol = us_watchlist[st.sidebar.selectbox("选择美股标的：", options=list(us_watchlist.keys()))]
elif market_type == "A 股 AI 算力/产业链":
    cn_watchlist = {
        "工业富联 (601138.SS - 算力服务器代工)": "601138.SS",
        "中际旭创 (300308.SZ - AI光模块龙头)": "300308.SZ",
        "新易盛 (300502.SZ - 高速光模块)": "300502.SZ",
        "寒武纪 (688256.SS - 国产AI芯片)": "688256.SS"
    }
    ticker_symbol = cn_watchlist[st.sidebar.selectbox("选择 A 股标的：", options=list(cn_watchlist.keys()))]
else:
    ticker_symbol = st.sidebar.text_input("请输入股票代码（美股如 AAPL，A股如 000001.SZ）：", value="AAPL").upper().strip()

st.sidebar.markdown("---")
st.sidebar.subheader("📱 安卓手机通知栏推送配置")
enable_push = st.sidebar.checkbox("开启买点触发时微信/手机弹窗提醒")
serverchan_key = st.sidebar.text_input("填入 Server酱 SendKey (微信接收)：", type="password", help="免费注册 Server酱(sct.ftqq.com)，复制SendKey填入此处，买点触发时微信直接弹窗。")

gemini_api_key = st.sidebar.text_input("Gemini API Key (选填-新闻翻译)：", type="password")

# ================= 核心数据抓取与计算函数 =================
@st.cache_data(ttl=900)
def fetch_stock_data(symbol):
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="1y")
    info = {}
    try:
        info = ticker.info
    except Exception:
        info = {}
    
    news_list = []
    try:
        raw_news = ticker.news
        if raw_news:
            for item in raw_news[:6]:
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
    data["BB_Upper"] = data["SMA20"] + 2 * std20
    data["BB_Lower"] = data["SMA20"] - 2 * std20
    
    delta = data["Close"].diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=14, min_periods=5).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=14, min_periods=5).mean()
    rs = gain / loss.replace(0, np.nan)
    data["RSI"] = 100 - (100 / (1 + rs))
    data["RSI"] = data["RSI"].fillna(50)
    return data

# 发送微信/手机通知的函数
def send_android_push(key, title, desp):
    if not key:
        return False
    url = f"https://sctapi.ftqq.com/{key}.send"
    data = {"title": title, "desp": desp}
    try:
        res = requests.post(url, data=data, timeout=5)
        return res.status_code == 200
    except Exception:
        return False

# ================= 主界面渲染 =================
st.title(f"📊 全球AI巨头与算力链自动体检报告：{ticker_symbol}")
st.caption(f"数据更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} | 适配安卓手机实时盯盘")

with st.spinner(f"正在扫描 {ticker_symbol} 行情与支撑位..."):
    hist, info, news_titles = fetch_stock_data(ticker_symbol)

if hist is None or hist.empty or len(hist) < 5:
    st.error(f"⚠️ 未能找到代码为 `{ticker_symbol}` 的数据，请检查拼写。")
    st.stop()

df = calculate_indicators(hist)
latest = df.iloc[-1]
prev = df.iloc[-2] if len(df) > 1 else latest

current_price = float(latest["Close"])
daily_change_pct = ((current_price - float(prev["Close"])) / float(prev["Close"])) * 100

sma20 = float(latest["SMA20"])
sma50 = float(latest["SMA50"])
sma200 = float(latest["SMA200"]) if not np.isnan(latest["SMA200"]) else float(df["Low"].min())
bb_lower = float(latest["BB_Lower"]) if not np.isnan(latest["BB_Lower"]) else current_price * 0.95
rsi = float(latest["RSI"])

high_52w = float(df["High"].max())
low_52w = float(df["Low"].min())
low_20d = float(df["Low"].tail(20).min())
low_60d = float(df["Low"].tail(60).min())
drawdown_from_high = ((current_price - high_52w) / high_52w) * 100

target_mean = info.get("targetMeanPrice")
target_low = info.get("targetLowPrice")
short_name = info.get("shortName") or info.get("longName") or ticker_symbol

# 测算买点
support_candidates_1 = [val for val in [bb_lower, low_20d, min(sma20, sma50)] if val < current_price]
buy_zone_1_mid = np.median(support_candidates_1) if support_candidates_1 else current_price * 0.94
buy_zone_1_low = round(buy_zone_1_mid * 0.985, 2)
buy_zone_1_high = round(buy_zone_1_mid * 1.015, 2)

support_candidates_2 = [low_60d, sma200, low_52w * 1.05]
if target_low and target_low < buy_zone_1_low:
    support_candidates_2.append(float(target_low))
valid_s2 = [val for val in support_candidates_2 if val < buy_zone_1_low]
buy_zone_2_mid = np.median(valid_s2) if valid_s2 else buy_zone_1_low * 0.88
buy_zone_2_low = round(buy_zone_2_mid * 0.98, 2)
buy_zone_2_high = round(buy_zone_2_mid * 1.02, 2)

# 决策与通知触发
score = 0
if current_price >= sma20 and sma20 >= sma50:
    trend_status = "📈 强势上涨通道"
    score += 1
elif current_price < sma20 and current_price < sma50:
    trend_status = "📉 短期调整下行"
    score -= 1
else:
    trend_status = "〰️ 横盘震荡期"

if rsi < 35:
    rsi_status = f"🥶 极度超卖（RSI={rsi:.1f}）"
    score += 2
elif rsi > 70:
    rsi_status = f"🥵 严重过热（RSI={rsi:.1f}）"
    score -= 2
else:
    rsi_status = f"😊 情绪平稳（RSI={rsi:.1f}）"

if score >= 1 and rsi <= 65:
    signal_color = "#dcfce7"
    border_color = "#16a34a"
    signal_title = "🟢 今日结论：进入第一买点区，可分批低吸"
    signal_summary = f"当前价格 **${current_price:.2f}**，契合短期支撑。建议在 **${buy_zone_1_low} - ${buy_zone_1_high}** 附近分批建仓。"
    
    # 如果开启了推送且当前价格刚好掉进买点区，自动发微信通知到安卓手机
    if enable_push and serverchan_key and current_price <= buy_zone_1_high:
        push_title = f"【盯盘买点触发】{short_name} ({ticker_symbol})"
        push_content = f"当前价格: ${current_price:.2f}\n建议买入区间: ${buy_zone_1_low} - ${buy_zone_1_high}\n状态: 已进入第一买点支撑区，请及时查看！"
        send_android_push(serverchan_key, push_title, push_content)

elif rsi > 70:
    signal_color = "#fee2e2"
    border_color = "#dc2626"
    signal_title = "🔴 今日结论：短期过热，切忌盲目追高"
    signal_summary = f"当前价格 **${current_price:.2f}** 偏离均线较远，建议耐心等待回踩第一支撑位。"
else:
    signal_color = "#fef9c3"
    border_color = "#ca8a04"
    signal_title = "🟡 今日结论：多看少动，等待落入安全防线"
    signal_summary = f"当前价格 **${current_price:.2f}** 正在震荡，等待触及下方的安全买点区再行动。"

# 渲染页面
st.markdown(f"""
<div class="signal-box" style="background-color: {signal_color}; border-left: 8px solid {border_color};">
    <h3 style="margin-top:0; color:#111827;">{signal_title}</h3>
    <p style="margin-bottom:0; color:#1f2937;">{signal_summary}</p>
</div>
""", unsafe_allow_html=True)

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("💰 最新价格", f"${current_price:.2f}", f"{daily_change_pct:+.2f}%")
with col2:
    st.metric("🌡️ RSI 情绪温度", f"{rsi:.1f} 分")
with col3:
    st.metric("📉 距高点回撤", f"{drawdown_from_high:.1f}%")
with col4:
    if target_mean:
        st.metric("🏦 机构平均目标价", f"${float(target_mean):.2f}")
    else:
        st.metric("📏 52周最低支撑", f"${low_52w:.2f}")

st.markdown("---")

st.subheader("🎯 系统自动测算挂单买入区")
z_col1, z_col2 = st.columns(2)
with z_col1:
    st.markdown(f"""
    <div class="buy-zone-card">
        <h4 style="margin-top:0; color:#166534;">🟢 第一买点区：${buy_zone_1_low} – ${buy_zone_1_high}</h4>
        <p style="margin-bottom:0; color:#1f2937;">适合分批建仓的常规稳健防线。</p>
    </div>
    """, unsafe_allow_html=True)
with z_col2:
    st.markdown(f"""
    <div class="deep-zone-card">
        <h4 style="margin-top:0; color:#1e40af;">🛡️ 第二买点区：${buy_zone_2_low} – ${buy_zone_2_high}</h4>
        <p style="margin-bottom:0; color:#1f2937;">极端大跌下的黄金坑高安全边际区。</p>
    </div>
    """, unsafe_allow_html=True)

st.subheader("📈 股价走势与安全买点防线图")
fig = go.Figure()
fig.add_trace(go.Scatter(x=df.index, y=df["Close"], mode="lines", name="收盘价", line=dict(color="#111827", width=2)))
fig.add_trace(go.Scatter(x=df.index, y=df["SMA20"], mode="lines", name="20日均线", line=dict(color="#f59e0b", width=1.5, dash="dot")))
fig.add_hrect(y0=buy_zone_1_low, y1=buy_zone_1_high, fillcolor="#22c55e", opacity=0.2, line_width=1, line_color="#16a34a", annotation_text="第一买点区")
fig.update_layout(height=400, margin=dict(l=10, r=10, t=30, b=10), hovermode="x unified")
st.plotly_chart(fig, use_container_width=True)

st.subheader("📰 产业链核心新闻动态")
if news_titles:
    for idx, t in enumerate(news_titles[:4], 1):
        st.markdown(f"{idx}. {t}")
else:
    st.info("近期暂无重大突发头条新闻。")
