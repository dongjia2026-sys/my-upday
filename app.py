import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import google.generativeai as genai
from datetime import datetime

# ================= 页面基础设置 =================
st.set_page_config(
    page_title="我的私人股票盯盘参谋",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义大字体与卡片样式，适配手机与电脑阅读
st.markdown("""
<style>
    .signal-box {
        padding: 20px;
        border-radius: 12px;
        margin-bottom: 20px;
        font-size: 18px;
        line-height: 1.6;
    }
    .buy-zone-card {
        padding: 18px;
        border-radius: 10px;
        background-color: #f0fdf4;
        border-left: 6px solid #16a34a;
        margin-bottom: 15px;
    }
    .deep-zone-card {
        padding: 18px;
        border-radius: 10px;
        background-color: #eff6ff;
        border-left: 6px solid #2563eb;
        margin-bottom: 15px;
    }
</style>
""", unsafe_allow_html=True)

# ================= 侧边栏：自选股与设置 =================
st.sidebar.title("🧭 盯盘参谋控制台")
st.sidebar.markdown("无需懂金融术语，自动拉取华尔街底层数据并翻译成大白话结论。")

# 默认预设用户关心的标的
default_Watchlist = {
    "SPCX (SpaceX 太空探索)": "SPCX",
    "DRAM (内存芯片 ETF)": "DRAM",
    "MU (美光科技 - 内存巨头)": "MU",
    "NVDA (英伟达 - AI算力)": "NVDA",
    "TSLA (特斯拉)": "TSLA",
    "SPY (标普500美股大盘)": "SPY"
}

selected_label = st.sidebar.selectbox(
    "📌 选择要体检的股票 / ETF：",
    options=list(default_Watchlist.keys()) + ["🔍 手动输入其他股票代码..."]
)

if selected_label == "🔍 手动输入其他股票代码...":
    ticker_symbol = st.sidebar.text_input("请输入美股代码（如 AAPL、AMD）：", value="AAPL").upper().strip()
else:
    ticker_symbol = default_Watchlist[selected_label]

st.sidebar.markdown("---")
st.sidebar.subheader("🤖 可选：接入 AI 新闻翻译官")
gemini_api_key = st.sidebar.text_input(
    "填入 Gemini API Key（选填，不填也可正常算买点）：",
    type="password",
    help="如果填入免费申请的 Gemini API Key，软件会自动把最新英文财经新闻翻译总结成中文利好/利空。"
)

# ================= 核心数据抓取与指标计算函数 =================
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
                # 兼容不同版本的 yfinance 新闻结构
                title = item.get("title") or item.get("content", {}).get("title", "")
                if title:
                    news_list.append(title)
    except Exception:
        pass
        
    return hist, info, news_list

def calculate_indicators(df):
    data = df.copy()
    # 均线系统
    data["SMA20"] = data["Close"].rolling(window=20, min_periods=5).mean()
    data["SMA50"] = data["Close"].rolling(window=50, min_periods=10).mean()
    data["SMA200"] = data["Close"].rolling(window=200, min_periods=30).mean()
    
    # 布林带 (20日, 2倍标准差)
    std20 = data["Close"].rolling(window=20, min_periods=5).std()
    data["BB_Upper"] = data["SMA20"] + 2 * std20
    data["BB_Lower"] = data["SMA20"] - 2 * std20
    
    # 14日 RSI (情绪温度计)
    delta = data["Close"].diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=14, min_periods=5).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=14, min_periods=5).mean()
    rs = gain / loss.replace(0, np.nan)
    data["RSI"] = 100 - (100 / (1 + rs))
    data["RSI"] = data["RSI"].fillna(50)
    
    return data

# ================= 主界面渲染 =================
st.title(f"📊 每日股票自动体检报告：{ticker_symbol}")
st.caption(f"数据更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} | 数据源：Yahoo Finance 实时/收盘底层行情")

with st.spinner(f"正在为您调取 {ticker_symbol} 的华尔街行情、均线支撑与机构底牌..."):
    hist, info, news_titles = fetch_stock_data(ticker_symbol)

if hist is None or hist.empty or len(hist) < 5:
    st.error(f"⚠️ 未能找到代码为 `{ticker_symbol}` 的足够交易数据，请检查股票代码拼写是否正确。")
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

# 提取华尔街机构数据（若为ETF可能无机构目标价，自动兼容）
target_mean = info.get("targetMeanPrice")
target_low = info.get("targetLowPrice")
target_high = info.get("targetHighPrice")
pe_ratio = info.get("trailingPE") or info.get("forwardPE")
short_name = info.get("shortName") or info.get("longName") or ticker_symbol

# ================= 核心算法：计算“第一买点”与“第二买点” =================
# 第一关注价位（稳健回调买点）：结合布林带下轨、20日低点与中期均线支撑
support_candidates_1 = [val for val in [bb_lower, low_20d, min(sma20, sma50)] if val < current_price]
if support_candidates_1:
    buy_zone_1_mid = np.median(support_candidates_1)
else:
    buy_zone_1_mid = current_price * 0.94  # 若当前处于极低位，取现价下方3%-6%

buy_zone_1_low = round(buy_zone_1_mid * 0.985, 2)
buy_zone_1_high = round(buy_zone_1_mid * 1.015, 2)

# 第二关注价位（黄金坑防守买点）：结合60日低点、长期200日均线、52周低点与机构最低目标价
support_candidates_2 = [low_60d, sma200, low_52w * 1.05]
if target_low and target_low < buy_zone_1_low:
    support_candidates_2.append(float(target_low))
valid_s2 = [val for val in support_candidates_2 if val < buy_zone_1_low]

if valid_s2:
    buy_zone_2_mid = np.median(valid_s2)
else:
    buy_zone_2_mid = buy_zone_1_low * 0.88

buy_zone_2_low = round(buy_zone_2_mid * 0.98, 2)
buy_zone_2_high = round(buy_zone_2_mid * 1.02, 2)

# ================= 红绿灯综合决策引擎 =================
reasons = []
score = 0  # 综合安全加分项

# 1. 判断趋势
if current_price >= sma20 and sma20 >= sma50:
    trend_status = "📈 处于上涨通道（短期均线在中期均线之上，买盘力量强）"
    score += 1
elif current_price < sma20 and current_price < sma50:
    trend_status = "📉 处于下跌通道（股价跌破20日与50日均线，短期抛压还没走完，俗称“飞刀未落地”）"
    score -= 1
else:
    trend_status = "〰️ 处于横盘震荡期（多空双方正在拉锯，方向尚未完全明朗）"

# 2. 判断 RSI 情绪温度
if rsi < 35:
    rsi_status = f"🥶 极度超卖（RSI={rsi:.1f}）：市场恐慌抛售过度，历史上往往接近短期反弹买点"
    score += 2
elif rsi > 70:
    rsi_status = f"🥵 严重过热（RSI={rsi:.1f}）：短期涨得太急，随时有获利盘抛售回调风险，切忌追高"
    score -= 2
else:
    rsi_status = f"😊 情绪正常（RSI={rsi:.1f}）：买卖情绪处于合理区间（35~70之间）"

# 3. 判断距离高点回撤与安全边际
if drawdown_from_high <= -20:
    reasons.append(f"距离年内高点（${high_52w:.2f}）已经回撤了 **{abs(drawdown_from_high):.1f}%**，挤掉了不少前期泡沫。")
    score += 1
elif drawdown_from_high >= -5:
    reasons.append(f"当前价格非常接近历史最高点（${high_52w:.2f}），上方短期追高性价比偏低。")

# 生成最终红绿灯信号
if score >= 1 and rsi <= 65:
    signal_color = "#dcfce7"
    border_color = "#16a34a"
    signal_title = "🟢 今日结论：可以分批关注 / 逢低吸纳"
    signal_summary = (
        f"**大白话建议：** 目前 {short_name} 具备较好的关注价值。如果您手里还没有仓位，可以在现价（**${current_price:.2f}**）或等待回踩 **第一关注区间（${buy_zone_1_low} - ${buy_zone_1_high}）** 时先买一小部分底仓，切记不要一次性把钱买光。"
    )
elif rsi > 70 or (current_price > sma20 * 1.12):
    signal_color = "#fee2e2"
    border_color = "#dc2626"
    signal_title = "🔴 今日结论：短期过热，千万别追高！"
    signal_summary = (
        f"**大白话建议：** 现在冲进去很容易当“接盘侠”。当前股价（**${current_price:.2f}**）短期涨得太急，情绪温度计（RSI={rsi:.1f}）已经发烫。好股票也要好价格，请耐心等它回调到 **${buy_zone_1_low} - ${buy_zone_1_high}** 附近再考虑出手。"
    )
else:
    signal_color = "#fef9c3"
    border_color = "#ca8a04"
    signal_title = "🟡 今日结论：多看少动，等待落入安全买点区"
    signal_summary = (
        f"**大白话建议：** 当前股价（**${current_price:.2f}**）处于下跌调整或震荡中途，短期下跌惯性还没完全停稳。**最聪明的做法是先别急着重仓抄底**，要么等它跌到下方 **${buy_zone_1_low} - ${buy_zone_1_high}** 支撑区再分批买，要么等它重新站稳20日均线（**${sma20:.2f}**）后再跟进。"
    )

# ================= 1. 顶部红绿灯大卡片 =================
st.markdown(f"""
<div class="signal-box" style="background-color: {signal_color}; border-left: 8px solid {border_color};">
    <h3 style="margin-top:0; color:#111827;">{signal_title}</h3>
    <p style="margin-bottom:0; color:#1f2937;">{signal_summary}</p>
</div>
""", unsafe_allow_html=True)

# ================= 2. 核心数据仪表盘（4大指标卡） =================
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("💰 最新收盘价格", f"${current_price:.2f}", f"{daily_change_pct:+.2f}% (今日涨跌)")
with col2:
    rsi_label = "超卖(偏冷)" if rsi < 35 else ("过热(危险)" if rsi > 70 else "正常温度")
    st.metric("🌡️ 情绪温度计 (RSI)", f"{rsi:.1f} 分", rsi_label, delta_color="off")
with col3:
    st.metric("📉 距年内最高点回撤", f"{drawdown_from_high:.1f}%", f"最高曾达 ${high_52w:.2f}", delta_color="off")
with col4:
    if target_mean:
        upside = ((float(target_mean) - current_price) / current_price) * 100
        st.metric("🏦 华尔街机构平均目标价", f"${float(target_mean):.2f}", f"潜在空间 {upside:+.1f}%")
    else:
        st.metric("📏 52周最低防守价", f"${low_52w:.2f}", "ETF/无单一机构目标价", delta_color="off")

st.markdown("---")

# ================= 3. 具体什么价位能买？（双区间挂单参考） =================
st.subheader("🎯 具体什么价位能买？（系统自动测算挂单区）")
z_col1, z_col2 = st.columns(2)

with z_col1:
    st.markdown(f"""
    <div class="buy-zone-card">
        <h4 style="margin-top:0; color:#166534;">🟢 第一关注价位（常规回调买点）：${buy_zone_1_low} – ${buy_zone_1_high}</h4>
        <p style="margin-bottom:0; color:#1f2937;">
        <b>为什么是这个价位？</b><br>
        这是系统结合<b>最近20天低点（${low_20d:.2f}）</b>、<b>布林带下轨支撑（${bb_lower:.2f}）</b>以及<b>均线防守位</b>算出的第一道防线。如果股价正常回调到这里且不再大跌，适合用<b>小仓位（如计划资金的30%）</b>分批买入。
        </p>
    </div>
    """, unsafe_allow_html=True)

with z_col2:
    st.markdown(f"""
    <div class="deep-zone-card">
        <h4 style="margin-top:0; color:#1e40af;">🛡️ 第二关注价位（大跌黄金坑买点）：${buy_zone_2_low} – ${buy_zone_2_high}</h4>
        <p style="margin-bottom:0; color:#1f2937;">
        <b>为什么是这个价位？</b><br>
        这是结合<b>过去60天深度低点（${low_60d:.2f}）</b>、<b>长期牛熊分界线（${sma200:.2f}）</b>算出的极限防守区。只有遇到大盘恐慌或突发利空大跌时才会砸到这里，一旦跌到这个区间，属于赔率极高的“黄金坑”。
        </p>
    </div>
    """, unsafe_allow_html=True)

# ================= 4. 眼见为实：股价走势与安全买点区间图 =================
st.subheader("📈 眼见为实：当前股价所处位置与绿色买点区")
fig = go.Figure()

# 绘制股价线与均线
fig.add_trace(go.Scatter(x=df.index, y=df["Close"], mode="lines", name="每日收盘价", line=dict(color="#111827", width=2.5)))
fig.add_trace(go.Scatter(x=df.index, y=df["SMA20"], mode="lines", name="20日短期均线", line=dict(color="#f59e0b", width=1.5, dash="dot")))
fig.add_trace(go.Scatter(x=df.index, y=df["SMA50"], mode="lines", name="50日中期均线", line=dict(color="#8b5cf6", width=1.5, dash="dash")))

# 画出第一关注买点带（浅绿色阴影）
fig.add_hrect(
    y0=buy_zone_1_low, y1=buy_zone_1_high,
    fillcolor="#22c55e", opacity=0.2, line_width=1, line_color="#16a34a",
    annotation_text=f"第一关注买点区 (${buy_zone_1_low}-${buy_zone_1_high})", annotation_position="top left"
)

# 画出第二关注黄金坑带（浅蓝色阴影）
fig.add_hrect(
    y0=buy_zone_2_low, y1=buy_zone_2_high,
    fillcolor="#3b82f6", opacity=0.2, line_width=1, line_color="#2563eb",
    annotation_text=f"第二黄金坑买点区 (${buy_zone_2_low}-${buy_zone_2_high})", annotation_position="bottom left"
)

fig.update_layout(
    height=450,
    margin=dict(l=10, r=10, t=30, b=10),
    xaxis_title="日期",
    yaxis_title="价格 (美元 USD)",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)
st.plotly_chart(fig, use_container_width=True)

# ================= 5. 说服你的“四大客观证据” =================
st.subheader("🔍 为什么给出上面的结论？（说服你的四大客观铁证）")

with st.expander("📌 铁证一：均线趋势与位置体检（已自动展开）", expanded=True):
    st.markdown(f"""
    * **当前趋势诊断：** {trend_status}
    * **关键防线对比：**
      * **20日均线（短期生命线）：** `${sma20:.2f}` —— 当前股价{'高于' if current_price >= sma20 else '低于'}该线。
      * **50日均线（中期强弱线）：** `${sma50:.2f}` —— 当前股价{'高于' if current_price >= sma50 else '低于'}该线。
      * **长期防守底座：** `${sma200:.2f}`
    * **情绪温度诊断：** {rsi_status}
    """)

with st.expander("🏦 铁证二：华尔街机构底牌与估值排雷（已自动展开）", expanded=True):
    if target_mean:
        st.markdown(f"""
        * **华尔街分析师目标价区间：** 最低看至 **${target_low}** | 平均看至 **${target_mean}** | 最高看至 **${target_high}**
        * **大白话解读：** 目前现价（${current_price:.2f}）{'低于华尔街平均目标价，说明机构普遍认为还有上涨空间' if current_price < float(target_mean) else '已经超过华尔街平均目标价，说明短期股价跑在了机构预期前面，需注意回调'}。
        """)
    else:
        st.markdown("* **标的屬性：** 该标的为 ETF（一篮子股票基金）或暂无单一机构目标价，重点看上方均线趋势与行业周期。")
    
    if pe_ratio:
        pe_comment = "估值非常高（包含极高未来预期，一旦财报或消息不及预期容易大跌）" if float(pe_ratio) > 60 else ("估值处于合理偏低区间" if float(pe_ratio) < 25 else "估值处于成长股正常水平")
        st.markdown(f"* **市盈率（P/E 估值倍数）：** **{float(pe_ratio):.1f} 倍** —— {pe_comment}。")

with st.expander("📰 铁证三：最新华尔街英文情报与 AI 大白话总结", expanded=True):
    if not news_titles:
        st.info("近期暂无新的重大英文头条新闻。")
    else:
        st.markdown("**系统抓取到的最新外网头条：**")
        for idx, t in enumerate(news_titles, 1):
            st.markdown(f"{idx}. {t}")
            
        if gemini_api_key:
            try:
                genai.configure(api_key=gemini_api_key)
                model = genai.GenerativeModel("gemini-2.5-flash")
                prompt = f"""
                你是一位零金融术语的私人股票参谋。请根据以下关于 {short_name} ({ticker_symbol}) 的最新英文财经新闻标题，以及当前股价 ${current_price:.2f}、52周最高 ${high_52w:.2f} 的背景，用3条简明扼要的中文大白话告诉用户：
                1. 最近市场在炒作它的什么利好或担心什么利空？
                2. 有没有普通散户容易忽略的风险？
                新闻列表：{news_titles}
                """
                with st.spinner("AI 正在为您把英文新闻翻译总结成中文内幕要点..."):
                    resp = model.generate_content(prompt)
                    st.success("🤖 **AI 投研参谋的新闻内幕解读：**\n\n" + resp.text)
            except Exception as e:
                st.warning(f"AI 解读调用未成功，请检查 API Key 是否正确（错误信息：{e}）")
        else:
            st.caption("💡 提示：如果您想让软件自动把上面的英文新闻总结成中文利好/利空，可以在左侧栏填入免费的 Gemini API Key。")
