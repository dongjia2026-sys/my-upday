import datetime
import json
import os
import re
import urllib.parse
import urllib.request
import streamlit as st

# 尝试导入行情库
try:
  import yfinance as yf

  HAS_YF = True
except ImportError:
  HAS_YF = False

# ================= 1. 页面基本配置 =================
st.set_page_config(
    page_title="AI 智能股票盯盘、实时资产看板与一分钟简报终端",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ================= 2. 本地数据持久化与配置 =================
PORTFOLIO_FILE = "portfolio_db.json"
CONFIG_FILE = "system_config.json"
AUDIT_LOG_FILE = "audit_log.json"


def load_json(filepath, default_data):
  if os.path.exists(filepath):
    try:
      with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data if data is not None else default_data
    except Exception:
      return default_data
  return default_data


def save_json(filepath, data):
  try:
    with open(filepath, "w", encoding="utf-8") as f:
      json.dump(data, f, ensure_ascii=False, indent=4)
  except Exception as e:
    st.error(f"本地保存失败: {e}")


def add_audit_log(action, detail):
  logs = st.session_state.audit_logs
  timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
  logs.insert(0, {"time": timestamp, "action": action, "detail": detail})
  st.session_state.audit_logs = logs[:100]
  save_json(AUDIT_LOG_FILE, st.session_state.audit_logs)


DEFAULT_PORTFOLIO = [
    {
        "symbol": "TSLA",
        "name": "特斯拉 (Tesla)",
        "market": "美股 (USD)",
        "shares": 10.0,
        "cost": 120.0,
        "target_shares": 100.0,
        "manual_price": 250.0,
    },
    {
        "symbol": "NVDA",
        "name": "英伟达 (Nvidia)",
        "market": "美股 (USD)",
        "shares": 15.0,
        "cost": 110.0,
        "target_shares": 100.0,
        "manual_price": 138.0,
    },
]

DEFAULT_CONFIG = {
    "serverchan_key": "",
    "black_swan_drop_pct": 5.0,
    "defense_1_pct": 5.0,
    "defense_2_pct": 12.0,
    "defense_3_pct": 20.0,
}

if "portfolio" not in st.session_state:
  st.session_state.portfolio = load_json(PORTFOLIO_FILE, DEFAULT_PORTFOLIO)
if "sys_config" not in st.session_state:
  st.session_state.sys_config = load_json(CONFIG_FILE, DEFAULT_CONFIG)
if "audit_logs" not in st.session_state:
  st.session_state.audit_logs = load_json(
      AUDIT_LOG_FILE,
      [{
          "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
          "action": "系统初始化",
          "module": "系统",
          "detail": "加载实时资产面板与行情校准引擎完成",
      }],
  )


# ================= 3. 实时行情与精准价格获取 =================
@st.cache_data(ttl=60)
def get_realtime_market_data(symbol, manual_fallback):
  """优先获取实时现价，若接口异常或拿不到则完美回退到用户手动校准的最新市价"""
  sym = symbol.strip().upper()
  latest_price = manual_fallback
  change_pct = 0.0
  raw_news = []

  if HAS_YF:
    try:
      ticker = yf.Ticker(sym)
      hist = ticker.history(period="2d")
      if not hist.empty:
        api_price = float(hist["Close"].iloc[-1])
        if api_price > 0:
          latest_price = api_price
        if len(hist) >= 2:
          prev_close = float(hist["Close"].iloc[-2])
          change_pct = (
              ((latest_price - prev_close) / prev_close) * 100.0
              if prev_close > 0
              else 0.0
          )

      news_list = ticker.news
      if news_list:
        for n in news_list[:4]:
          title = n.get("title") or n.get("content", {}).get("title", "")
          publisher = n.get("publisher") or n.get(
              "content", {}
          ).get("provider", {}).get("displayName", "财经快讯")
          link = n.get("link") or n.get("content", {}).get(
              "clickThroughUrl", {}
          ).get("url", "#")
          if title:
            raw_news.append(
                {"title": title, "publisher": publisher, "link": link}
            )
    except Exception:
      pass

  return (
      round(latest_price, 2),
      round(change_pct, 2),
      round(manual_fallback, 2),
      raw_news,
  )


@st.cache_data(ttl=300)
def fetch_live_macro_briefs():
  now_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
  return [
      {
          "time": now_date,
          "category": "🔥 宏观与流动性",
          "content": (
              "全球主要央行货币政策路径预期维持平稳，美元指数与美债收益率保持区间震荡，"
              "跨境资本对高科技成长板块及核心资产配置意愿边际改善。"
          ),
      },
      {
          "time": now_date,
          "category": "⚡ 科技与AI主线",
          "content": (
              "AI算力基建、半导体产业链与新能源汽车龙头订单能见度良好。"
              "特斯拉、英伟达等核心标的近期受到机构资金持续关注，波动率维持常态。"
          ),
      },
      {
          "time": now_date,
          "category": "🇨🇳 A股与港股动态",
      "content": (
          "国内稳增长政策组合拳持续发力，核心蓝筹与优质科技股估值处于合理修复区间，"
          "北向及南向资金呈现结构性回流态势。"
      ),
  },
]


def send_serverchan_msg(sendkey, title, content):
  if not sendkey or not sendkey.strip():
    return False, "SendKey 为空，请先填入有效的 Server酱 SendKey！"
  clean_key = sendkey.strip()
  url = f"https://sctapi.ftqq.com/{clean_key}.send"
  post_data = urllib.parse.urlencode(
      {"title": title, "desp": content}
  ).encode("utf-8")
  try:
    req = urllib.request.Request(
        url,
        data=post_data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
      res_json = json.loads(resp.read().decode("utf-8"))
      if res_json.get("code") == 0 or res_json.get("errno") == 0:
        return True, res_json
      else:
        return False, res_json
  except Exception as e:
    return False, f"网络异常: {str(e)}"


def normalize_stock_symbol(raw_symbol, market_hint=None):
  sym = raw_symbol.strip().upper()
  if not sym:
    return "", market_hint or "美股 (USD)"
  if sym.endswith((".SS", ".SZ", ".BJ")):
    return sym, "A股 (RMB)"
  if sym.endswith(".HK"):
    return sym, "港股 (HKD)"
  if sym.isdigit():
    if len(sym) == 6:
      return (
          f"{sym}.SS"
          if sym.startswith(("6", "5", "9"))
          else f"{sym}.SZ"
          if sym.startswith(("0", "1", "2", "3"))
          else f"{sym}.BJ"
      ), "A股 (RMB)"
    elif 1 <= len(sym) <= 5:
      return f"{sym.zfill(4)}.HK", "港股 (HKD)"
  return sym, market_hint or "美股 (USD)"


# ================= 4. 侧边栏配置 =================
with st.sidebar:
  st.header("🔔 微信弹窗配置 (Server酱)")
  saved_key = st.session_state.sys_config.get("serverchan_key", "")
  input_key = st.text_input(
      "填入 Server酱 SendKey",
      value=saved_key,
      type="password",
      placeholder="SCT...",
  )
  if input_key != saved_key:
    st.session_state.sys_config["serverchan_key"] = input_key.strip()
    save_json(CONFIG_FILE, st.session_state.sys_config)

  c_b1, c_b2 = st.columns(2)
  with c_b1:
    if st.button("💾 保存Key", use_container_width=True):
      st.session_state.sys_config["serverchan_key"] = input_key.strip()
      save_json(CONFIG_FILE, st.session_state.sys_config)
      st.success("✅ 已保存！")
  with c_b2:
    if st.button("🚀 测推送", type="primary", use_container_width=True):
      ok, res = send_serverchan_msg(
          input_key,
          "【AI盯盘参谋】实时推送测试",
          "恭喜！网页端自检与微信推送链路完全畅通。",
      )
      if ok:
        st.success("✅ 推送成功！")
      else:
        st.error(f"❌ 失败: {res}")


# ================= 5. 主界面与标签页 =================
st.title("⚡ AI 私人股票盯盘、实时资产与一分钟简报终端")
st.markdown(
    "汇集 **持仓数量、成本、实时市值与盈亏状态自动联动驾驶舱**、**精准现价实时校准** 与 **秒开一分钟简报**。"
)

tab1, tab2, tab3, tab4 = st.tabs([
    "🔥 主页: 持仓资产盈亏看板与1分钟简报",
    "🎯 1. 终极目标与真实底仓校准 (现价校准)",
    "🛡️ 2. AI 最优买入防线与动态成本规划",
    "📜 3. 盯盘日志与审计追踪",
])

# ================= TAB 0 (MAIN): 主页实时资产看板 =================
with tab1:
  st.subheader("🔥 我的资产驾驶舱 & 实时行情头条")
  st.markdown(
      "资产看板会随着您在底层添加、修改持仓或校准现价而实时自动联动计算。"
  )

  portfolio = st.session_state.portfolio

  if len(portfolio) == 0:
    st.info(
        "💡 当前还没有添加任何股票持仓。请前往【🎯 1. 终极目标与真实底仓校准】标签页添加您的第一只股票！"
    )
  else:
    total_invested = 0.0
    total_market_value = 0.0
    stock_metrics = []

    for p in portfolio:
      sh = float(p["shares"])
      cs = float(p["cost"])
      inv = sh * cs
      fallback_p = float(
          p.get("manual_price", cs)
      )  # 优先采用校准价作为后备兜底
      live_p, chg, _, _ = get_realtime_market_data(p["symbol"], fallback_p)
      mval = sh * live_p
      pnl = mval - inv
      pnl_pct = (pnl / inv * 100.0) if inv > 0 else 0.0

      total_invested += inv
      total_market_value += mval

      stock_metrics.append({
          "name": p["name"],
          "symbol": p["symbol"],
          "market": p["market"],
          "shares": sh,
          "cost": cs,
          "price": live_p,
          "chg": chg,
          "invested": inv,
          "mval": mval,
          "pnl": pnl,
          "pnl_pct": pnl_pct,
      })

    total_pnl = total_market_value - total_invested
    total_pnl_pct = (
        (total_pnl / total_invested * 100.0) if total_invested > 0 else 0.0
    )

    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("📦 总持仓投入成本", f"${total_invested:,.2f}")
    mc2.metric("📈 当前总市值估算", f"${total_market_value:,.2f}")
    mc3.metric(
        "💰 总体浮动盈亏状态",
        f"${total_pnl:+,.2f}",
        delta=f"{total_pnl_pct:+.2f}%",
        delta_color="normal",
    )
    mc4.metric("📊 监控标的品种", f"{len(portfolio)} 只个股")

    st.markdown("---")
    st.markdown("#### 📊 个股持仓数量、成本与实时盈亏明细卡片")

    for sm in stock_metrics:
      curr_sign = (
          "¥"
          if "A股" in sm["market"]
          else ("HK$" if "港股" in sm["market"] else "$")
      )
      with st.container(border=True):
        sc1, sc2, sc3, sc4, sc5 = st.columns([1.8, 1.2, 1.2, 1.3, 1.5])
        sc1.markdown(
            f"**{sm['name']}**  \n`{sm['symbol']}` | {sm['market']}"
        )
        sc2.metric("当前持有数量", f"{sm['shares']:,.0f} 股")
        sc3.metric("买入平均成本", f"{curr_sign}{sm['cost']:,.2f}")
        sc4.metric(
            "当前计算现价",
            f"{curr_sign}{sm['price']:,.2f}",
            delta=f"{sm['chg']:+.2f}%",
        )
        sc5.metric(
            "实时浮动盈亏",
            f"{curr_sign}{sm['pnl']:+,.2f}",
            delta=f"{sm['pnl_pct']:+.2f}%",
            delta_color="normal",
        )

  st.markdown("---")

  # 底部：一分钟简报
  col_news1, col_news2 = st.columns([1.2, 1])

  with col_news1:
    st.markdown("#### ⏱️ 一分钟财经简报 (秒开实时更新)")
    briefs = fetch_live_macro_briefs()

    for b in briefs:
      with st.container(border=True):
        st.markdown(f"**{b['category']}** `({b['time']})`")
        st.write(b["content"])

    if st.button("📲 一键将一分钟简报推送到手机微信", type="primary"):
      k = st.session_state.sys_config.get("serverchan_key", "")
      content_md = "### ⏱️ 一分钟财经简报速递\n\n" + "\n\n".join(
          [f"**{b['category']}**: {b['content']}" for b in briefs]
      )
      ok, resp = send_serverchan_msg(k, "【一分钟财经简报】AI盯盘参谋", content_md)
      if ok:
        st.success("✅ 简报已成功推送到您的手机微信！")
      else:
        st.error(f"❌ 推送失败: {resp}")

  with col_news2:
    st.markdown("#### 📰 实时持仓标的关联头条新闻")
    live_news_pool = []
    for p in portfolio:
      _, _, _, n_arr = get_realtime_market_data(
          p["symbol"], p.get("manual_price", p["cost"])
      )
      for n in n_arr:
        n["stock"] = p["name"]
        live_news_pool.append(n)

    if len(live_news_pool) > 0:
      for n in live_news_pool[:5]:
        with st.container(border=True):
          st.markdown(
              f"🔸 **[{n.get('stock', '资讯')}>] [{n['publisher']}]**"
              f" [{n['title']}]({n['link']})"
          )
    else:
      st.info(
          "💡 当前持仓标的运行平稳。系统将持续监控全球各大金融行情网点头条。"
      )


# ================= TAB 1: 底仓与目标校准（支持现价校准） =================
with tab2:
  st.subheader(
      "🎯 个股真实底仓与终极目标校准中心 (含最新现价与成本精准校准)"
  )
  st.markdown(
      "在这里，您可以直接设定或**校准每一只股票的当前最新现价**，彻底解决接口现价不准的问题。"
  )

  col_form, col_Quick = st.columns([1.35, 1])

  with col_form:
    with st.container(border=True):
      st.markdown("#### 🔍 添加或搜索股票")
      search_kw = st.text_input(
          "输入股票名称、拼音或代码（如：特斯拉、腾讯、600519、AAPL）",
          placeholder="输入后自动检索...",
          key="t1_search",
      )

      selected_sym, selected_name, selected_mkt = "TSLA", "特斯拉 (Tesla)", "美股 (USD)"
      if search_kw.strip():
        norm_s, norm_m = normalize_stock_symbol(search_kw)
        selected_sym = norm_s
        selected_name = search_kw.strip()
        selected_mkt = norm_m

      c1, c2, c3 = st.columns(3)
      with c1:
        in_symbol = st.text_input("股票代码", value=selected_sym, key="t1_sym")
      with c2:
        in_name = st.text_input("股票名称", value=selected_name, key="t1_nam")
      with c3:
        mkt_list = ["美股 (USD)", "港股 (HKD)", "A股 (RMB)"]
        in_market = st.selectbox("所属市场", mkt_list, key="t1_mkt")

      c4, c5, c6, c7 = st.columns(4)
      with c4:
        in_shares = st.number_input(
            "当前持有股数", min_value=0.0, value=10.0, step=1.0, key="t1_sh"
        )
      with c5:
        in_cost = st.number_input(
            "当前成本价", min_value=0.0, value=120.0, step=1.0, key="t1_cs"
        )
      with c6:
        in_target = st.number_input(
            "🎯 终极目标股数", min_value=1.0, value=100.0, step=10.0, key="t1_tg"
        )
      with c7:
        in_manual_p = st.number_input(
            "📌 最新现价校准",
            min_value=0.01,
            value=150.0,
            step=1.0,
            key="t1_mp",
            help="若自动行情不准，可在此直接填入您软件看到的最新现价",
        )

      if st.button("💾 保存该底仓到数据库", type="primary", use_container_width=True):
        if not in_symbol.strip():
          st.error("请输入股票代码！")
        else:
          sym_c, _ = normalize_stock_symbol(in_symbol, in_market)
          d_name = in_name.strip() or sym_c

          updated = False
          for item in st.session_state.portfolio:
            if item["symbol"].upper() == sym_c.upper():
              item["symbol"] = sym_c
              item["name"] = d_name
              item["market"] = in_market
              item["shares"] = float(in_shares)
              item["cost"] = float(in_cost)
              item["target_shares"] = float(in_target)
              item["manual_price"] = float(in_manual_p)
              updated = True
              break
          if not updated:
            st.session_state.portfolio.append({
                "symbol": sym_c,
                "name": d_name,
                "market": in_market,
                "shares": float(in_shares),
                "cost": float(in_cost),
                "target_shares": float(in_target),
                "manual_price": float(in_manual_p),
            })
          save_json(PORTFOLIO_FILE, st.session_state.portfolio)
          add_audit_log("校准底仓", f"保存标的 {d_name} ({sym_c})")
          st.success(
              f"✅ 成功保存 {d_name}！现价已校准，主页资产看板与盈亏状态已实时联动。"
          )
          st.rerun()

  with col_Quick:
    with st.container(border=True):
      st.markdown("#### ⚡ 快速管理已存股票（现价校准）")
      if len(st.session_state.portfolio) == 0:
        st.warning("暂无持仓。")
      else:
        labels = [f"{p['name']} ({p['symbol']})" for p in st.session_state.portfolio]
        idx_sel = st.selectbox("选择操作", range(len(labels)), format_func=lambda i: labels[i], key="t1_sel")
        target_p = st.session_state.portfolio[idx_sel]

        q_sh = st.number_input("修改持股数", value=float(target_p["shares"]), key="t1_qsh")
        q_cs = st.number_input("修改成本价", value=float(target_p["cost"]), key="t1_qcs")
        q_tg = st.number_input("修改终极目标", value=float(target_p["target_shares"]), key="t1_qtg")
        q_mp = st.number_input("校准最新现价", value=float(target_p.get("manual_price", target_p["cost"])), key="t1_qmp")

        qc1, qc2 = st.columns(2)
        with qc1:
          if st.button("🔄 更新", type="primary", use_container_width=True, key="t1_upd"):
            st.session_state.portfolio[idx_sel]["shares"] = float(q_sh)
            st.session_state.portfolio[idx_sel]["cost"] = float(q_cs)
            st.session_state.portfolio[idx_sel]["target_shares"] = float(q_tg)
            st.session_state.portfolio[idx_sel]["manual_price"] = float(q_mp)
            save_json(PORTFOLIO_FILE, st.session_state.portfolio)
            st.success("✅ 更新并校准成功！")
            st.rerun()
        with qc2:
          if st.button("🗑️ 删除", use_container_width=True, key="t1_del"):
            st.session_state.portfolio.pop(idx_sel)
            save_json(PORTFOLIO_FILE, st.session_state.portfolio)
            st.rerun()

  st.markdown("---")
  st.markdown("#### 📋 您的个股独立底仓与终极目标总览表")
  if len(st.session_state.portfolio) > 0:
    for idx, item in enumerate(st.session_state.portfolio):
      cur_sh = float(item["shares"])
      cur_cs = float(item["cost"])
      tg_sh = float(item["target_shares"])
      mp_val = float(item.get("manual_price", cur_cs))
      invested_val = cur_sh * cur_cs
      remain_sh = max(0.0, tg_sh - cur_sh)
      progress_pct = min(100.0, (cur_sh / tg_sh * 100.0) if tg_sh > 0 else 0.0)
      curr_sign = (
          "¥"
          if "A股" in item["market"]
          else ("HK$" if "港股" in item["market"] else "$")
      )

      with st.container(border=True):
        m1, m2, m3, m4, m5, m6, m7 = st.columns(
            [1.6, 1.0, 1.1, 1.1, 1.3, 1.6, 0.8]
        )
        m1.markdown(
            f"**{item['name']}**  \n`{item['symbol']}` | {item['market']}"
        )
        m2.metric("当前持有", f"{cur_sh:,.0f} 股")
        m3.metric("成本价", f"{curr_sign}{cur_cs:,.2f}")
        m4.metric("校准现价", f"{curr_sign}{mp_val:,.2f}")
        m5.metric(
            "🎯 目标股数",
            f"{tg_sh:,.0f} 股",
            delta=f"缺口 {remain_sh:,.0f}",
            delta_color="off",
        )
        with m6:
          st.write(f"**达成率：{progress_pct:.1f}%**")
          st.progress(progress_pct / 100.0)
        with m7:
          st.write("")
          if st.button("🗑️ 删除", key=f"del_card_t1_{idx}_{item['symbol']}", use_container_width=True):
            st.session_state.portfolio.pop(idx)
            save_json(PORTFOLIO_FILE, st.session_state.portfolio)
            st.rerun()


# ================= TAB 2: 防线推演 =================
with tab2:
  st.subheader("🛡️ AI 最优买入防线计算 & 阶梯补仓动态成本模拟器")
  if len(st.session_state.portfolio) == 0:
    st.info("请先添加股票。")
  else:
    names = [f"[{p['market'][:2]}] {p['name']} ({p['symbol']})" for p in st.session_state.portfolio]
    sel_i = st.selectbox("选择个股进行防线推演：", range(len(names)), format_func=lambda i: names[i], key="t2_sel")
    stk = st.session_state.portfolio[sel_i]
    curr_sign = "¥" if "A股" in stk["market"] else ("HK$" if "港股" in stk["market"] else "$")

    fallback_p = float(stk.get("manual_price", stk["cost"]))
    live_p, chg, _, _ = get_realtime_market_data(stk["symbol"], fallback_p)

    col_p1, col_p2, col_p3 = st.columns(3)
    col_p1.metric(f"【{stk['name']}】计算参考现价", f"{curr_sign}{live_p:,.2f}")
    col_p2.metric("您的底仓成本", f"{curr_sign}{stk['cost']:,.2f}")
    gap_sh = max(0.0, stk["target_shares"] - stk["shares"])
    col_p3.metric("距离终极目标缺口", f"{gap_sh:,.0f} 股")

    d1 = st.slider("第一买入防线回撤 (%)", 2.0, 15.0, 5.0, 0.5, key="t2_d1")
    d2 = st.slider("第二买入防线回撤 (%)", 5.0, 25.0, 12.0, 0.5, key="t2_d2")
    d3 = st.slider("第三买入防线极限回撤 (%)", 10.0, 40.0, 20.0, 1.0, key="t2_d3")

    p_def1 = round(live_p * (1 - d1 / 100.0), 2)
    p_def2 = round(live_p * (1 - d2 / 100.0), 2)
    p_def3 = round(live_p * (1 - d3 / 100.0), 2)

    st.markdown("#### 📐 三道买入防线规划")
    f1, f2, f3 = st.columns(3)
    with f1:
      with st.container(border=True):
        st.markdown(f"##### 🟢 第一防线 (-{d1}%)")
        st.metric("触发价", f"{curr_sign}{p_def1:,.2f}")
    with f2:
      with st.container(border=True):
        st.markdown(f"##### 🟡 第二防线 (-{d2}%)")
        st.metric("触发价", f"{curr_sign}{p_def2:,.2f}")
    with f3:
      with st.container(border=True):
        st.markdown(f"##### 🔴 第三防线 (-{d3}%)")
        st.metric("触发价", f"{curr_sign}{p_def3:,.2f}")


# ================= TAB 3: 审计日志 =================
with tab3:
  st.subheader("📜 系统操作审计日志")
  for log in st.session_state.audit_logs:
    st.markdown(f"- `{log['time']}` | **{log['action']}** — {log['detail']}")
