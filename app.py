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
    .mini-widget { padding: 16px; border-radius: 12px; background: linear-gradient(135deg, #0f172a, #1e293b); color: #f8fafc; box-shadow: 0 6px 16px rgba(0,0,0,0.2); margin-bottom: 16px; border: 1px solid #334155; }
    .lazy-report { padding: 20px; border-radius: 12px; background-color: #f8fafc; border: 2px solid #cbd5e1; margin-bottom: 20px; }
    .black-swan-alert { padding: 18px; border-radius: 10px; background-color: #fef2f2; border-left: 6px solid #dc2626; margin-bottom: 20px; }
    .good-news-alert { padding: 18px; border-radius: 10px; background-color: #f0fdf4; border-left: 6px solid #16a34a; margin-bottom: 20px; }
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
        f"【{datetime.now().strftime('%Y-%m-%d %H:%M')}】系统初始化档案：默认持有 10 股，成本均价 120.0"
    ]
if "locked_targets" not in st.session_state:
    st.session_state.locked_targets = {}
if "last_pushed_signal" not in st.session_state:
    st.session_state.last_pushed_signal = ""

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
st.sidebar.markdown("稳态双防线 · 黑天鹅雷达 · 桌面小窗")

# 1. 桌面精简小窗口模式开关
is_mini_mode = st.sidebar.toggle(
    "🖥️ 开启桌面精简小窗口模式",
    value=False,
    help="开启后界面收缩为极简深色悬浮卡片，把浏览器窗口拉小即可挂在桌面角落盯盘"
)

# 2. 多市场标的切换
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
    ticker_symbol = st.sidebar.text_input("请输入股票代码 (如 AAPL 或 600519.SS)：", value="NVDA").upper().strip()

currency_sym = "¥" if ticker_symbol.endswith((".SS", ".SZ", ".HK")) else "$"

st.sidebar.markdown("---")
st.sidebar.subheader("🎯 终极目标与真实底仓校准")
target_total_shares = st.sidebar.number_input("你最终想要持有的总股数 (如100股):", min_value=1, value=100, step=10)

st.sidebar.markdown("✏️ **随时自由修改当前手里的底仓：**")
new_held_shares = st.sidebar.number_input("当前手里实际已持有股数:", min_value=0, value=st.session_state.held_shares, step=1)
new_avg_cost = st.sidebar.number_input(f"当前手里的平均买入成本 ({currency_sym}):", min_value=0.0, value=st.session_state.avg_cost, step=1.0)

if st.sidebar.button("💾 保存底仓修改并记入日志"):
    if new_held_shares != st.session_state.held_shares or new_avg_cost != st.session_state.avg_cost:
        old_s, old_c = st.session_state.held_shares, st.session_state.avg_cost
        st.session_state.held_shares = new_held_shares
        st.session_state.avg_cost = new_avg_cost
        st.session_state.last_check_date = datetime.now()
        log_entry = f"【{datetime.now().strftime('%Y-%m-%d %H:%M')}】手动校准底仓：从 {old_s}股({currency_sym}{old_c}) 更新为 {new_held_shares}股({currency_sym}{new_avg_cost})"
        st.session_state.audit_logs.insert(0, log_entry)
        st.sidebar.success("✅ 底仓已更新并写入历史审计日志！")
    else:
        st.session_state.last_check_date = datetime.now()
        log_entry = f"【{datetime.now().strftime('%Y-%m-%d %H:%M')}】定期核对确认：底仓保持 {new_held_shares}股({currency_sym}{new_avg_cost}) 不变"
        st.session_state.audit_logs.insert(0, log_entry)
        st.sidebar.info("✅ 已更新核对时间，底仓数据未变动。")

st.sidebar.markdown("---")
st.sidebar.subheader("🛡️ 防线价格锁定控制")
lock_defense = st.sidebar.checkbox(
    "🔒 锁定当前第一/第二防线挂单价",
    value=False,
    help="勾选后，第一防线与第二防线价格将被彻底锁死，方便你在盈立证券长期挂单，绝不随盘面变动"
)

st.sidebar.markdown("---")
st.sidebar.subheader("📱 手机微信秒级弹窗配置")
enable_push = st.sidebar.checkbox("开启买点与黑天鹅微信实时弹窗", value=True)
serverchan_key = st.sidebar.text_input("填入 Server酱 SendKey:", type="password")
if st.sidebar.button("🔔 发送一条测试弹窗到手机微信"):
    if serverchan_key:
        ok = send_wechat_alert(
            serverchan_key,
            f"【测试成功】{ticker_symbol} 盯盘哨兵已连接",
            "你的手机微信已成功绑定 AI 投资管家！当股价触及第一/第二稳态防线，或发生突发黑天鹅/重大利好时，将第一时间弹窗通知你。"
        )
        if ok:
            st.sidebar.success("✅ 发送成功！请看一眼你的手机微信。")
        else:
            st.sidebar.error("❌ 发送失败，请检查 SendKey 是否正确。")
    else:
        st.sidebar.warning("⚠️ 请先在上方输入框填入 SendKey。")

# ================= 核心数据抓取与技术/情绪指标计算 =================
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
    data["Vol_Avg20"] = data["Volume"].rolling(window=20, min_periods=5).mean()

    delta = data["Close"].diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=14, min_periods=5).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=14, min_periods=5).mean()
    rs = gain / loss.replace(0, np.nan)
    data["RSI"] = (100 - (100 / (1 + rs))).fillna(50)
    return data

# 获取数据
hist, info, news_titles = fetch_all_market_data(ticker_symbol)
if hist is None or hist.empty or len(hist) < 5:
    st.error(f"⚠️ 暂未获取到 `{ticker_symbol}` 的行情数据，请检查代码拼写或稍后刷新。")
    st.stop()

df = calculate_indicators(hist)
latest = df.iloc[-1]
prev = df.iloc[-2] if len(df) > 1 else latest

current_price = float(latest["Close"])
daily_change_pct = ((current_price - float(prev["Close"])) / float(prev["Close"])) * 100
rsi = float(latest["RSI"])
vol_ratio = float(latest["Volume"] / latest["Vol_Avg20"]) if latest["Vol_Avg20"] > 0 else 1.0

# ================= 长期稳态双防线计算（不随每日现价乱飘） =================
# 采用历史 180 天与 1 年的客观大周期结构分位数 + 200日牛熊均线，排除 current_price 干扰
 historical_window = df.iloc[:-1] if len(df) > 20 else df
sma200_anchor = float(historical_window["SMA200"].dropna().iloc[-1]) if not historical_window["SMA200"].dropna().empty else float(historical_window["Low"].min())
q35_support = float(historical_window["Low"].tail(180).quantile(0.35))
q15_support = float(historical_window["Low"].tail(250).quantile(0.15))

# 第一防线（常规结构支撑区）与 第二防线（深度黄金坑极限支撑区）
calc_line1 = round(max(q35_support, sma200_anchor * 0.98), 2)
calc_line2 = round(min(q15_support, calc_line1 * 0.90), 2)

# 如果用户勾选了“锁定防线价格”，则完全固定不变
if lock_defense:
    if ticker_symbol not in st.session_state.locked_targets:
        st.session_state.locked_targets[ticker_symbol] = (calc_line1, calc_line2)
    defense_line_1, defense_line_2 = st.session_state.locked_targets[ticker_symbol]
else:
    defense_line_1, defense_line_2 = calc_line1, calc_line2
    st.session_state.locked_targets[ticker_symbol] = (defense_line_1, defense_line_2)

line1_low, line1_high = round(defense_line_1 * 0.99, 2), round(defense_line_1 * 1.01, 2)
line2_low, line2_high = round(defense_line_2 * 0.99, 2), round(defense_line_2 * 1.01, 2)

# ================= 突发黑天鹅 / 重大利好秒级雷达判定 =================
is_black_swan = daily_change_pct <= -4.5 or (daily_change_pct <= -3.0 and vol_ratio >= 1.8)
is_major_catalyst = daily_change_pct >= 4.5 or (daily_change_pct >= 3.0 and vol_ratio >= 1.8)

# ================= 100 股长线分批建仓与最终成本精算 =================
shares_needed = max(0, target_total_shares - st.session_state.held_shares)
batch_line1_shares = int(np.ceil(shares_needed * 0.5))
batch_line2_shares = shares_needed - batch_line1_shares

current_total_cost = st.session_state.held_shares * st.session_state.avg_cost
if shares_needed > 0:
    planned_add_cost = (batch_line1_shares * defense_line_1) + (batch_line2_shares * defense_line_2)
    predicted_final_cost = (current_total_cost + planned_add_cost) / target_total_shares
else:
    predicted_final_cost = st.session_state.avg_cost

# 判断当前所处防线状态
if shares_needed == 0:
    status_badge = "🎉 已满仓达成目标"
    action_conclusion = f"🎉 **恭喜！你已持有 {st.session_state.held_shares} 股，圆满达成 {target_total_shares} 股长线目标！** 当前安心持有即可。"
elif current_price <= line2_high:
    status_badge = "🚨 触及第二防线（黄金坑）"
    action_conclusion = f"🟢 **触发第二防线（极限黄金坑）！** 现价（**{currency_sym}{current_price:.2f}**）已跌入第二防线（**{currency_sym}{line2_low} - {currency_sym}{line2_high}**），建议立即执行第二梯队建仓（买入 **{batch_line2_shares} 股**）！"
elif current_price <= line1_high:
    status_badge = "🟢 触及第一防线（可建仓）"
    action_conclusion = f"🟢 **触发第一防线（常规支撑位）！** 现价（**{currency_sym}{current_price:.2f}**）已进入第一防线（**{currency_sym}{line1_low} - {currency_sym}{line1_high}**），建议执行第一梯队建仓（买入 **{batch_line1_shares} 股**），其余 **{batch_line2_shares} 股**继续在第二防线（**{currency_sym}{defense_line_2}**）挂单蹲守！"
else:
    status_badge = "⏳ 现价偏高（挂单蹲守中）"
    action_conclusion = (
        f"🔴 **先别追高，提前挂单守株待兔！** 当前现价（**{currency_sym}{current_price:.2f}**）高于稳态防线。请直接在盈立证券 App 分两批挂好长期限价单："
        f"**第一防线挂单 {currency_sym}{defense_line_1}（买 {batch_line1_shares} 股）**，"
        f"**第二防线挂单 {currency_sym}{defense_line_2}（买 {batch_line2_shares} 股）**。挂好后无需天天盯盘！"
    )

# ================= 自动微信推送触发逻辑（含防重复机制） =================
if enable_push and serverchan_key:
    trigger_reason = ""
    if is_black_swan:
        trigger_reason = f"🚨【突发黑天鹅警报】{ticker_symbol} 放量暴跌 {daily_change_pct:.2f}%"
    elif is_major_catalyst:
        trigger_reason = f"🔥【突发重大利好】{ticker_symbol} 放量暴涨 {daily_change_pct:+.2f}%"
    elif shares_needed > 0 and current_price <= line2_high:
        trigger_reason = f"🟢【触及第二防线】{ticker_symbol} 现价 {currency_sym}{current_price:.2f}"
    elif shares_needed > 0 and current_price <= line1_high:
        trigger_reason = f"🟢【触及第一防线】{ticker_symbol} 现价 {currency_sym}{current_price:.2f}"

    signal_key = f"{ticker_symbol}_{ datetime.now().strftime('%Y-%m-%d') }_{trigger_reason[:10]}"
    if trigger_reason and st.session_state.last_pushed_signal != signal_key:
        push_body = (
            f"**最新现价：** {currency_sym}{current_price:.2f} ({daily_change_pct:+.2f}%)\n\n"
            f"**第一防线挂单价：** {currency_sym}{defense_line_1}（规划买 {batch_line1_shares} 股）\n\n"
            f"**第二防线挂单价：** {currency_sym}{defense_line_2}（规划买 {batch_line2_shares} 股）\n\n"
            f"**最新突发消息：** {news_titles[0] if news_titles else '请留意盘面异动'}\n\n"
            f"**AI 应对方案：** {action_conclusion}"
        )
        if send_wechat_alert(serverchan_key, trigger_reason, push_body):
            st.session_state.last_pushed_signal = signal_key

# ================= 模式 A：桌面精简小窗口模式渲染 =================
if is_mini_mode:
    alert_banner = ""
    if is_black_swan:
        alert_banner = f"<p style='margin:6px 0; color:#f87171; font-weight:bold;'>🚨 突发黑天鹅异动：放量暴跌 {daily_change_pct:.2f}% ({vol_ratio:.1f}倍量)，建议暂停第一防线接刀，退守第二防线！</p>"
    elif is_major_catalyst:
        alert_banner = f"<p style='margin:6px 0; color:#4ade80; font-weight:bold;'>🔥 突发重大利好：放量暴涨 {daily_change_pct:+.2f}% ({vol_ratio:.1f}倍量)，大资金抢筹明显！</p>"

    st.markdown(f"""
    <div class="mini-widget">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <span style="font-size:18px; font-weight:bold; color:#38bdf8;">📌 {ticker_symbol} 桌面盯盘小窗</span>
            <span style="font-size:13px; background:#334155; padding:3px 8px; border-radius:6px;">{status_badge}</span>
        </div>
        <p style="margin:5px 0; font-size:17px;">💰 <b>实时现价：</b> {currency_sym}{current_price:.2f} <span style="color:{'#4ade80' if daily_change_pct>=0 else '#f87171'};">({daily_change_pct:+.2f}%)</span></p>
        <p style="margin:5px 0; font-size:15px;">🛡️ <b>第一防线 (买{batch_line1_shares}股)：</b> <span style="color:#4ade80; font-weight:bold;">{currency_sym}{defense_line_1}</span> （区间 {currency_sym}{line1_low}-{line1_high}）</p>
        <p style="margin:5px 0; font-size:15px;">🛡️ <b>第二防线 (买{batch_line2_shares}股)：</b> <span style="color:#facc15; font-weight:bold;">{currency_sym}{defense_line_2}</span> （区间 {currency_sym}{line2_low}-{line2_high}）</p>
        <p style="margin:5px 0; font-size:14px; color:#cbd5e1;">📦 <b>长线进度：</b> 已持 {st.session_state.held_shares} 股 (均价 {currency_sym}{st.session_state.avg_cost}) | 差 {shares_needed} 股满 {target_total_shares} 股 (预计最终均价 {currency_sym}{predicted_final_cost:.2f})</p>
        {alert_banner}
    </div>
    """, unsafe_allow_html=True)
    st.caption("💡 提示：点击左上角 `<<` 收起侧边栏，并将浏览器窗口拉小放在桌面角落，即可作为常驻桌面悬浮窗。")
    st.stop()

# ================= 模式 B：正常完整指挥所模式渲染 =================
st.title(f"📊 {ticker_symbol} 私人 AI 投研管家与长线筹码指挥所")

# 1. 温和定期对账提醒横幅
days_since_check = (datetime.now() - st.session_state.last_check_date).days
check_status_text = (
    f"距离你上次核对底仓已过去 <b>{days_since_check} 天</b>，请抽空去盈立证券看一眼底仓是否有变动！"
    if days_since_check >= 7
    else f"上次核对时间：{st.session_state.last_check_date.strftime('%Y-%m-%d %H:%M')}（状态最新）。"
)
st.markdown(f"""
<div class="reminder-box">
    💡 <b>管家定期对账提醒：</b> 你当前登记的持仓为 <b>{st.session_state.held_shares} 股</b>，平均成本 <b>{currency_sym}{st.session_state.avg_cost}</b>，距离 {target_total_shares} 股目标还差 <b>{shares_needed} 股</b>。{check_status_text} 如有买卖请随时在左侧边栏校准。
</div>
""", unsafe_allow_html=True)

# 2. 突发黑天鹅 / 重大利好秒级监控警报框
if is_black_swan:
    st.markdown(f"""
    <div class="black-swan-alert">
        <h4 style="margin-top:0; color:#991b1b;">🚨 【秒级突发黑天鹅警报】检测到剧烈砸盘 / 突发利空！（今日暴跌 {daily_change_pct:.2f}%，成交量放大 {vol_ratio:.1f} 倍）</h4>
        <p style="margin-bottom:6px; color:#1f2937;"><b>最新突发消息：</b> {news_titles[0] if news_titles else '市场出现突发性地缘/宏观或行业恐慌抛售'}</p>
        <p style="margin-bottom:0; color:#991b1b;"><b>⚡ AI 紧急部署方案调整：</b> 短期空头情绪极度宣泄，切勿盲目在半山腰满仓接飞刀！建议将原定在<b>第一防线（{currency_sym}{defense_line_1}）</b>的挂单撤下或减半，主力资金退守至更安全的<b>第二防线（{currency_sym}{defense_line_2}）</b>等待恐慌盘洗尽！</p>
    </div>
    """, unsafe_allow_html=True)
elif is_major_catalyst:
    st.markdown(f"""
    <div class="good-news-alert">
        <h4 style="margin-top:0; color:#166534;">🔥 【秒级重大利好警报】检测到大资金抢筹 / 重磅订单利好爆发！（今日大涨 {daily_change_pct:+.2f}%，成交量放大 {vol_ratio:.1f} 倍）</h4>
        <p style="margin-bottom:6px; color:#1f2937;"><b>最新突发消息：</b> {news_titles[0] if news_titles else '公司或行业迎来重磅利好催化，机构资金加速流入'}</p>
        <p style="margin-bottom:0; color:#166534;"><b>⚡ AI 紧急部署方案调整：</b> 重大利好驱动下股价底部中枢将上移。如果你手里还差 <b>{shares_needed} 股</b>未买齐，建议在回踩 20 日均线（<b>{currency_sym}{float(latest['SMA20']):.2f}</b>）附近先行小步建仓 20% 筹码，其余筹码继续锚定第一防线（<b>{currency_sym}{defense_line_1}</b>）！</p>
    </div>
    """, unsafe_allow_html=True)

# 3. 一分钟懒人极简简报（情绪 + 机构底牌 + 新闻 + 结论）
st.subheader("☕ 一分钟懒人极简简报（零门槛大白话版）")

inst_hold = info.get("heldPercentInstitutions", None)
inst_text = f"华尔街大机构目前锁定了该股 **{inst_hold*100:.1f}%** 的筹码，主力护盘底气充足。" if inst_hold else "大资金与机构目前处于常态化持仓博弈中。"
target_mean = info.get("targetMeanPrice", None)
target_text = f"机构分析师给出的长线共识目标均价在 **{currency_sym}{target_mean}** 附近。" if target_mean else ""

if rsi > 70:
    mood_text = f"🔥 **极度过热（RSI={rsi:.1f}，游资与散户正在疯狂追高）** —— 绝不在人声鼎沸时冲动买单，耐心等回落！"
elif rsi < 35:
    mood_text = f"🧊 **过度恐慌（RSI={rsi:.1f}，市场正在非理性错杀甩卖）** —— 别人恐慌我贪婪，重点盯防第一、第二防线捡便宜筹码！"
else:
    mood_text = f"🌤️ **情绪平稳（RSI={rsi:.1f}，正常换手洗盘期）** —— 没有极端疯涨或暴跌，挂好限价单守株待兔即可。"

st.markdown(f"""
<div class="lazy-report">
    <p style="font-size:16px; margin-bottom:10px;"><b>1. 🌡️ 今日市场情绪与游资动向：</b> {mood_text}</p>
    <p style="font-size:16px; margin-bottom:10px;"><b>2. 🐳 财报基本面与大资金底牌：</b> {inst_text} {target_text}</p>
    <p style="font-size:16px; margin-bottom:10px;"><b>3. 📰 最新全球时事与公司动态：</b> {news_titles[0] if news_titles else '今日暂无影响长线逻辑的极端突发负面新闻，公司业务正常运转。'}</p>
    <hr style="margin:12px 0;">
    <p style="font-size:18px; margin-bottom:0; color:#0f172a;"><b>🎯 最终长期作战与挂单方案：</b> {action_conclusion}</p>
</div>
""", unsafe_allow_html=True)

# 4. 100 股长期稳态双防线建仓指挥台
st.subheader(f"🧮 {target_total_shares} 股长期稳态双防线建仓指挥台")
c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    st.metric("📦 距离目标还差", f"{shares_needed} 股", f"已持 {st.session_state.held_shares} / 目标 {target_total_shares} 股")
with c2:
    st.metric("💰 当前最新市价", f"{currency_sym}{current_price:.2f}", f"{daily_change_pct:+.2f}%")
with c3:
    st.metric("🛡️ 第一防线 (常规挂单价)", f"{currency_sym}{defense_line_1}", f"规划买入 {batch_line1_shares} 股")
with c4:
    st.metric("🛡️ 第二防线 (极限黄金坑)", f"{currency_sym}{defense_line_2}", f"规划买入 {batch_line2_shares} 股")
with c5:
    st.metric("📉 买满100股预计最终均价", f"{currency_sym}{predicted_final_cost:.2f}", f"当前成本 {currency_sym}{st.session_state.avg_cost}")

# 5. 历史修改与责任追溯审计日志
with st.expander("📜 查看底仓变更历史与操作责任审计日志（点击展开）"):
    st.markdown("<div class='log-box'>", unsafe_allow_html=True)
    for log in st.session_state.audit_logs:
        st.write(log)
    st.markdown("</div>", unsafe_allow_html=True)

# 6. K线走势与双防线可视化图
st.subheader("📈 股价走势与长期稳态第一/第二防线作战地图")
fig = go.Figure()
fig.add_trace(go.Scatter(x=df.index, y=df["Close"], mode="lines", name="收盘价", line=dict(color="#0f172a", width=2)))
fig.add_trace(go.Scatter(x=df.index, y=df["SMA20"], mode="lines", name="20日短期趋势线", line=dict(color="#f59e0b", width=1.5, dash="dot")))
fig.add_trace(go.Scatter(x=df.index, y=df["SMA200"], mode="lines", name="200日长期牛熊分界线", line=dict(color="#3b82f6", width=1.8)))

# 绘制第一防线与第二防线固定带
fig.add_hrect(
    y0=line1_low, y1=line1_high,
    fillcolor="#22c55e", opacity=0.25,
    line_width=1, line_color="#16a34a",
    annotation_text=f"第一防线挂单区 ({currency_sym}{defense_line_1} | 买{batch_line1_shares}股)",
    annotation_position="top left"
)
fig.add_hrect(
    y0=line2_low, y1=line2_high,
    fillcolor="#eab308", opacity=0.25,
    line_width=1, line_color="#ca8a04",
    annotation_text=f"第二防线极限黄金坑 ({currency_sym}{defense_line_2} | 买{batch_line2_shares}股)",
    annotation_position="bottom left"
)

fig.update_layout(height=450, margin=dict(l=10, r=10, t=30, b=10), hovermode="x unified")
st.plotly_chart(fig, use_container_width=True)
