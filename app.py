import datetime
import json
import os
import re
import time
import urllib.parse
import urllib.request
import streamlit as st

# ================= 1. 页面基本配置 =================
st.set_page_config(
    page_title="AI 智能股票盯盘、全时段实时行情与资产终端",
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
  now_bjt = datetime.datetime.now(
      datetime.timezone(datetime.timedelta(hours=8))
  )
  timestamp = now_bjt.strftime("%Y-%m-%d %H:%M:%S")
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

BUILTIN_STOCKS = [
    ("TSLA", "特斯拉 (Tesla)", "美股 (USD)"),
    ("NVDA", "英伟达 (Nvidia)", "美股 (USD)"),
    ("AAPL", "苹果 (Apple)", "美股 (USD)"),
    ("MSFT", "微软 (Microsoft)", "美股 (USD)"),
    ("GOOGL", "谷歌 (Alphabet)", "美股 (USD)"),
    ("AMZN", "亚马逊 (Amazon)", "美股 (USD)"),
    ("META", "Meta Platforms", "美股 (USD)"),
    ("AMD", "超威半导体 (AMD)", "美股 (USD)"),
    ("PLTR", "Palantir", "美股 (USD)"),
    ("COIN", "Coinbase", "美股 (USD)"),
    ("MSTR", "MicroStrategy", "美股 (USD)"),
    ("TSM", "台积电 (TSMC)", "美股 (USD)"),
    ("BABA", "阿里巴巴 (美股)", "美股 (USD)"),
    ("00700.HK", "腾讯控股", "港股 (HKD)"),
    ("09988.HK", "阿里巴巴-W", "港股 (HKD)"),
    ("03690.HK", "美团-W", "港股 (HKD)"),
    ("01810.HK", "小米集团-W", "港股 (HKD)"),
    ("01211.HK", "比亚迪股份", "港股 (HKD)"),
    ("600519.SS", "贵州茅台", "A股 (RMB)"),
    ("300750.SZ", "宁德时代", "A股 (RMB)"),
    ("002594.SZ", "比亚迪 (A股)", "A股 (RMB)"),
    ("688256.SS", "寒武纪-U", "A股 (RMB)"),
]

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
          "detail": "加载全时段(盘前/盘中/盘后/24h)实时行情与快讯引擎完成",
      }],
  )
if "search_results" not in st.session_state:
  st.session_state.search_results = []


# ================= 3. 市场交易时段精准判定函数 =================
def get_global_market_clocks():
  """获取当前北京时间与美东时间，并判断美股/港股/A股当前所处的交易时段"""
  utc_now = datetime.datetime.now(datetime.timezone.utc)
  bjt_now = utc_now.astimezone(datetime.timezone(datetime.timedelta(hours=8)))
  # 美东夏令时 UTC-4 (3月-11月)，冬令时 UTC-5
  et_offset = -4 if 3 <= utc_now.month <= 11 else -5
  et_now = utc_now.astimezone(
      datetime.timezone(datetime.timedelta(hours=et_offset))
  )

  # 1. 美股时段判定
  et_hm = et_now.hour * 100 + et_now.minute
  if et_now.weekday() >= 5:
    us_session = "🌌 周末休市 / 24h夜盘待命"
  elif 400 <= et_hm < 930:
    us_session = "🌅 美股盘前交易 (Pre-Market)"
  elif 930 <= et_hm < 1600:
    us_session = "🟢 美股盘中交易 (Regular)"
  elif 1600 <= et_hm < 2000:
    us_session = "🌙 美股盘后交易 (After-Hours)"
  else:
    us_session = "🌌 美股24小时夜盘 / 休市时段 (Overnight)"

  # 2. 港股时段判定
  bjt_hm = bjt_now.hour * 100 + bjt_now.minute
  if bjt_now.weekday() >= 5:
    hk_session = "🔴 港股周末休市"
  elif 900 <= bjt_hm < 930:
    hk_session = "🌅 港股盘前竞价"
  elif (930 <= bjt_hm < 1200) or (1300 <= bjt_hm < 1600):
    hk_session = "🟢 港股盘中交易"
  elif 1200 <= bjt_hm < 1300:
    hk_session = "⏸️ 港股午间休市"
  elif 1600 <= bjt_hm <= 1610:
    hk_session = "🌙 港股收市竞价"
  else:
    hk_session = "🔴 港股已收盘"

  # 3. A股时段判定
  if bjt_now.weekday() >= 5:
    cn_session = "🔴 A股周末休市"
  elif 915 <= bjt_hm < 925:
    cn_session = "🌅 A股盘前集合竞价"
  elif (930 <= bjt_hm < 1130) or (1300 <= bjt_hm < 1500):
    cn_session = "🟢 A股盘中交易"
  elif 1130 <= bjt_hm < 1300:
    cn_session = "⏸️ A股午间休市"
  else:
    cn_session = "🔴 A股已收盘"

  return {
      "bjt_str": bjt_now.strftime("%Y-%m-%d %H:%M:%S"),
      "et_str": et_now.strftime("%Y-%m-%d %H:%M:%S"),
      "us_session": us_session,
      "hk_session": hk_session,
      "cn_session": cn_session,
  }


# ================= 4. 全时段实时股价引擎 (支持盘前/盘中/盘后/24h) =================
def normalize_stock_symbol(raw_symbol, market_hint=None):
  sym = raw_symbol.strip().upper()
  if not sym:
    return "", market_hint or "美股 (USD)"
  if sym.endswith((".SS", ".SZ", ".BJ")):
    return sym, "A股 (RMB)"
  if sym.endswith(".HK"):
    code_part = sym.replace(".HK", "")
    if code_part.isdigit():
      code_part = (
          code_part.zfill(5) if len(code_part) == 5 else code_part.zfill(4)
      )
    return f"{code_part}.HK", "港股 (HKD)"
  if sym.isdigit():
    if len(sym) == 6:
      if sym.startswith(("6", "5", "9")):
        return f"{sym}.SS", "A股 (RMB)"
      elif sym.startswith(("0", "1", "2", "3")):
        return f"{sym}.SZ", "A股 (RMB)"
      else:
        return f"{sym}.BJ", "A股 (RMB)"
    elif 1 <= len(sym) <= 5:
      padded = sym.zfill(5) if len(sym) == 5 else sym.zfill(4)
      return f"{padded}.HK", "港股 (HKD)"
  return sym, market_hint or "美股 (USD)"


@st.cache_data(ttl=8)
def fetch_full_session_quote(symbol, manual_fallback=100.0):
  """原生直连 Yahoo v8 PrePost 接口 + 腾讯实时行情接口，无需第三方库，

  精准返回：当前主价格、所属时段(盘前/盘中/盘后/收盘)、常规盘价、盘前盘后扩展价、更新时间。
  """
  sym = symbol.strip().upper()
  bjt_tz = datetime.timezone(datetime.timedelta(hours=8))
  et_tz = datetime.timezone(datetime.timedelta(hours=-4))
  now_bjt_str = datetime.datetime.now(bjt_tz).strftime("%H:%M:%S")

  if sym == "SPACEX":
    return {
        "active_price": float(manual_fallback),
        "active_chg_pct": 0.0,
        "session_tag": "🔒 私募/未上市估值",
        "reg_price": float(manual_fallback),
        "reg_chg_pct": 0.0,
        "ext_price": None,
        "ext_chg_pct": None,
        "ext_label": "无盘前盘后",
        "prev_close": float(manual_fallback),
        "update_time": now_bjt_str,
        "source": "手动私募估值",
    }

  # --- 通道 1：Yahoo Finance v8 1分钟级全时段接口 (含 Pre-Market & After-Hours) ---
  for host in ["query2.finance.yahoo.com", "query1.finance.yahoo.com"]:
    try:
      url = f"https://{host}/v8/finance/chart/{urllib.parse.quote(sym)}?interval=1m&range=2d&includePrePost=true"
      req = urllib.request.Request(
          url,
          headers={
              "User-Agent": (
                  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
              )
          },
      )
      with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        res = data.get("chart", {}).get("result", [])
        if res:
          meta = res[0].get("meta", {})
          reg_price = float(meta.get("regularMarketPrice") or manual_fallback)
          prev_close = float(
              meta.get("chartPreviousClose")
              or meta.get("previousClose")
              or reg_price
          )
          reg_time_ts = meta.get("regularMarketTime") or 0
          reg_chg_pct = (
              ((reg_price - prev_close) / prev_close * 100.0)
              if prev_close > 0
              else 0.0
          )

          timestamps = res[0].get("timestamp") or []
          quotes = res[0].get("indicators", {}).get("quote", [{}])[0]
          closes = quotes.get("close") or []

          # 寻找最新一笔 1 分钟真实成交价（含盘前、盘中、盘后）
          latest_tick_p = reg_price
          latest_tick_ts = reg_time_ts
          for ts_val, c_val in zip(reversed(timestamps), reversed(closes)):
            if c_val is not None and float(c_val) > 0:
              latest_tick_p = float(c_val)
              latest_tick_ts = int(ts_val)
              break

          # 判断最新成交价属于哪个时段
          is_us_stock = not sym.endswith((".SS", ".SZ", ".BJ", ".HK"))
          ext_price = None
          ext_chg_pct = None
          ext_label = "常规收盘"
          session_tag = "🟢 盘中实时"

          if is_us_stock and latest_tick_ts > 0:
            tick_et = datetime.datetime.fromtimestamp(latest_tick_ts, tz=et_tz)
            hm = tick_et.hour * 100 + tick_et.minute
            tick_bjt_str = datetime.datetime.fromtimestamp(
                latest_tick_ts, tz=bjt_tz
            ).strftime("%m-%d %H:%M:%S")

            # 获取交易周期边界
            periods = meta.get("currentTradingPeriod", {})
            reg_start = periods.get("regular", {}).get("start", 0)
            reg_end = periods.get("regular", {}).get("end", 0)

            if 400 <= hm < 930:
              session_tag = "🌅 美股盘前价 (Pre-Market)"
              ext_label = "🌅 盘前最新"
              ext_price = round(latest_tick_p, 2)
              ext_chg_pct = (
                  ((ext_price - reg_price) / reg_price * 100.0)
                  if reg_price > 0
                  else 0.0
              )
              active_price = ext_price
              active_chg_pct = (
                  ((active_price - prev_close) / prev_close * 100.0)
                  if prev_close > 0
                  else 0.0
              )
            elif 1600 <= hm <= 2005 or (reg_end > 0 and latest_tick_ts > reg_end):
              session_tag = "🌙 美股盘后价 (After-Hours)"
              ext_label = "🌙 盘后最新"
              ext_price = round(latest_tick_p, 2)
              ext_chg_pct = (
                  ((ext_price - reg_price) / reg_price * 100.0)
                  if reg_price > 0
                  else 0.0
              )
              active_price = ext_price
              active_chg_pct = (
                  ((active_price - prev_close) / prev_close * 100.0)
                  if prev_close > 0
                  else 0.0
              )
            elif 930 <= hm < 1600:
              session_tag = "🟢 美股盘中实时 (Regular)"
              active_price = round(latest_tick_p, 2)
              reg_price = active_price
              reg_chg_pct = (
                  ((reg_price - prev_close) / prev_close * 100.0)
                  if prev_close > 0
                  else 0.0
              )
              active_chg_pct = reg_chg_pct
            else:
              session_tag = "🌌 24h夜盘/最新收盘"
              active_price = round(latest_tick_p, 2)
              active_chg_pct = (
                  ((active_price - prev_close) / prev_close * 100.0)
                  if prev_close > 0
                  else 0.0
              )
          else:
            # 港股或A股
            tick_bjt_str = (
                datetime.datetime.fromtimestamp(
                    latest_tick_ts, tz=bjt_tz
                ).strftime("%m-%d %H:%M:%S")
                if latest_tick_ts > 0
                else now_bjt_str
            )
            clocks = get_global_market_clocks()
            session_tag = (
                clocks["hk_session"]
                if sym.endswith(".HK")
                else clocks["cn_session"]
            )
            active_price = round(latest_tick_p, 2)
            active_chg_pct = (
                ((active_price - prev_close) / prev_close * 100.0)
                if prev_close > 0
                else 0.0
            )

          return {
              "active_price": round(active_price, 2),
              "active_chg_pct": round(active_chg_pct, 2),
              "session_tag": session_tag,
              "reg_price": round(reg_price, 2),
              "reg_chg_pct": round(reg_chg_pct, 2),
              "ext_price": ext_price,
              "ext_chg_pct": (
                  round(ext_chg_pct, 2) if ext_chg_pct is not None else None
              ),
              "ext_label": ext_label,
              "prev_close": round(prev_close, 2),
              "update_time": tick_bjt_str,
              "source": "Yahoo v8 全时段实时流",
          }
    except Exception:
      continue

  # --- 通道 2：腾讯财经全球实时行情接口 (高速备用通道，支持美股/港股/A股) ---
  try:
    if sym.endswith(".SS"):
      q_code = f"sh{sym.replace('.SS', '')}"
    elif sym.endswith(".SZ"):
      q_code = f"sz{sym.replace('.SZ', '')}"
    elif sym.endswith(".HK"):
      hk_num = sym.replace(".HK", "").zfill(5)
      q_code = f"hk{hk_num}"
    else:
      q_code = f"us{sym}"

    t_url = f"http://qt.gtimg.cn/q={q_code}"
    req_t = urllib.request.Request(t_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req_t, timeout=4) as resp_t:
      raw_t = resp_t.read().decode("gbk", errors="ignore")
      parts = raw_t.split("~")
      if len(parts) > 32 and float(parts[3] or 0) > 0:
        cur_p = float(parts[3])
        prev_c = float(parts[4]) if float(parts[4] or 0) > 0 else cur_p
        chg_p = (
            float(parts[32])
            if parts[32]
            else ((cur_p - prev_c) / prev_c * 100.0)
        )
        t_time = parts[30] if parts[30] else now_bjt_str
        clocks = get_global_market_clocks()
        s_tag = (
            clocks["us_session"]
            if q_code.startswith("us")
            else (
                clocks["hk_session"]
                if q_code.startswith("hk")
                else clocks["cn_session"]
            )
        )
        return {
            "active_price": round(cur_p, 2),
            "active_chg_pct": round(chg_p, 2),
            "session_tag": s_tag,
            "reg_price": round(cur_p, 2),
            "reg_chg_pct": round(chg_p, 2),
            "ext_price": None,
            "ext_chg_pct": None,
            "ext_label": "常规行情",
            "prev_close": round(prev_c, 2),
            "update_time": t_time,
            "source": "腾讯全球实时接口",
        }
  except Exception:
    pass

  # --- 通道 3：兜底校准价格 ---
  return {
      "active_price": round(float(manual_fallback), 2),
      "active_chg_pct": 0.0,
      "session_tag": "📌 离线兜底价",
      "reg_price": round(float(manual_fallback), 2),
      "reg_chg_pct": 0.0,
      "ext_price": None,
      "ext_chg_pct": None,
      "ext_label": "无扩展行情",
      "prev_close": round(float(manual_fallback), 2),
      "update_time": now_bjt_str,
      "source": "本地校准兜底",
  }


# ================= 5. 全市场搜索与 7x24 小时实时财经快讯引擎 =================
@st.cache_data(ttl=30)
def fetch_7x24_live_briefs():
  """直连新浪 7x24 小时全球财经实时电报流，秒开且每分钟实时滚动更新"""
  flashes = []
  try:
    url = "https://zhibo.sina.com.cn/api/zhibo/feed?page=1&page_size=10&zhibo_id=152"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.sina.com.cn",
        },
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
      data = json.loads(resp.read().decode("utf-8"))
      feed_list = (
          data.get("result", {})
          .get("data", {})
          .get("feed", {})
          .get("list", [])
      )
      for item in feed_list:
        ctime = item.get("create_time", "")
        text = re.sub(r"<[^>]+>", "", item.get("rich_text", "")).strip()
        if text:
          flashes.append(
              {"time": ctime, "category": "⚡ 7×24实时电报", "content": text}
          )
  except Exception:
    pass

  if not flashes:
    now_str = datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=8))
    ).strftime("%Y-%m-%d %H:%M")
    flashes = [
        {
            "time": now_str,
            "category": "🔥 宏观与市场流动性",
            "content": (
                "全球资本市场维持对核心利率路径与科技股财报的密切追踪，"
                "盘前盘后资金在半导体、AI算力与智能驾驶龙头标的交投活跃。"
            ),
        },
        {
            "time": now_str,
            "category": "⚡ 美股全时段交易提示",
            "content": (
                "美股盘前(美东04:00起)与盘后(美东16:00-20:00)常受财报发布与突发消息驱动出现剧烈波动，"
                "建议结合三道买入防线分批挂单。"
            ),
        },
    ]
  return flashes


@st.cache_data(ttl=600)
def search_all_markets(keyword):
  kw = keyword.strip()
  if not kw:
    return []
  results = []
  seen = set()
  try:
    sina_url = f"https://suggest3.sinajs.cn/suggest/key={urllib.parse.quote(kw)}"
    req = urllib.request.Request(
        sina_url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.sina.com.cn",
        },
    )
    with urllib.request.urlopen(req, timeout=4) as resp:
      raw_text = resp.read().decode("gbk", errors="ignore")
      match = re.search(r'="([^"]+)"', raw_text)
      if match:
        for item in match.group(1).split(";"):
          parts = item.split(",")
          if len(parts) >= 5:
            mkt_type, code, full_code, cn_name = (
                parts[1],
                parts[2].upper(),
                parts[3].upper(),
                parts[4],
            )
            std_sym, mkt_label = None, None
            if mkt_type in ["11", "12", "81"]:
              std_sym = (
                  f"{code}.SS"
                  if full_code.startswith("SH")
                  else (
                      f"{code}.SZ"
                      if full_code.startswith("SZ")
                      else f"{code}.BJ"
                  )
              )
              mkt_label = "A股 (RMB)"
            elif mkt_type in ["31", "33"]:
              std_sym = f"{code}.HK"
              mkt_label = "港股 (HKD)"
            elif mkt_type in ["41", "42"]:
              std_sym = code.replace(".", "-")
              mkt_label = "美股 (USD)"
            if std_sym and std_sym not in seen:
              seen.add(std_sym)
              results.append({
                  "symbol": std_sym,
                  "name": cn_name,
                  "market": mkt_label,
                  "display": f"[{mkt_label}] {cn_name} ({std_sym})",
              })
  except Exception:
    pass

  for b_sym, b_name, b_mkt in BUILTIN_STOCKS:
    if (
        kw.upper() in b_sym.upper() or kw.lower() in b_name.lower()
    ) and b_sym not in seen:
      seen.add(b_sym)
      results.append({
          "symbol": b_sym,
          "name": b_name,
          "market": b_mkt,
          "display": f"[{b_mkt}] {b_name} ({b_sym})",
      })
  return results


# ================= 6. Server酱 微信推送函数 =================
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
    return False, f"网络异常或接口拒绝: {str(e)}"


# ================= 7. 侧边栏：Server酱配置 & 自动刷新控制 =================
with st.sidebar:
  st.header("⚡ 实时刷新与盯盘控制")
  auto_refresh = st.toggle(
      "开启实时价格自动跳动 (每15秒)",
      value=False,
      help="开启后网页将每15秒自动拉取全球最新盘前/盘中/盘后价格",
  )
  if st.button(
      "🔄 立即强制刷新最新股价", type="primary", use_container_width=True
  ):
    st.cache_data.clear()
    st.rerun()

  st.markdown("---")
  st.header("🔔 微信弹窗配置 (Server酱)")
  saved_key = st.session_state.sys_config.get("serverchan_key", "")
  input_key = st.text_input(
      "填入 Server酱 SendKey (或 AppKey)",
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
      st.success("✅ 已永久保存！")
  with c_b2:
    if st.button("🚀 测推送", type="primary", use_container_width=True):
      ok, res = send_serverchan_msg(
          input_key,
          "【AI盯盘参谋】全时段实时推送测试",
          "恭喜！网页端自检通过，Server酱微信推送通道100%畅通！",
      )
      if ok:
        st.success("✅ 推送成功！请看微信。")
      else:
        st.error(f"❌ 失败: {res}")


# ================= 8. 顶部全球市场时钟与交易时段状态栏 =================
st.title("⚡ AI 私人股票盯盘、全时段实时行情与一分钟简报终端")

clocks = get_global_market_clocks()
with st.container(border=True):
  ck1, ck2, ck3, ck4 = st.columns(4)
  ck1.markdown(
      f"🕒 **北京时间 (BJT)**  \n`{clocks['bjt_str']}`  \n🇺🇸 **美东时间 (ET)**"
      f" `{clocks['et_str']}`"
  )
  ck2.markdown(f"**美股当前状态**  \n{clocks['us_session']}")
  ck3.markdown(f"**港股当前状态**  \n{clocks['hk_session']}")
  ck4.markdown(f"**A股当前状态**  \n{clocks['cn_session']}")

tab1, tab2, tab3, tab4 = st.tabs([
    "🔥 主页: 全时段实时股价(盘前/盘中/盘后) & 资产盈亏 & 1分钟快讯",
    "🎯 1. 终极目标与真实底仓校准 (支持全市场搜索)",
    "🛡️ 2. AI 最优买入防线与动态成本规划 (含防线逻辑简介)",
    "📜 3. 盯盘日志与审计追踪",
])

# ================= TAB 1: 主页全时段实时行情与资产驾驶舱 =================
with tab1:
  portfolio = st.session_state.portfolio

  if len(portfolio) == 0:
    st.info(
        "💡 当前还没有添加任何股票持仓。请前往【🎯 1. 终极目标与真实底仓校准】添加您的股票！"
    )
  else:
    total_invested = 0.0
    total_market_value = 0.0
    stock_rows = []

    for p in portfolio:
      sh = float(p["shares"])
      cs = float(p["cost"])
      inv = sh * cs
      fallback_p = float(p.get("manual_price", cs))
      q_info = fetch_full_session_quote(p["symbol"], fallback_p)

      active_p = q_info["active_price"]
      mval = sh * active_p
      pnl = mval - inv
      pnl_pct = (pnl / inv * 100.0) if inv > 0 else 0.0

      total_invested += inv
      total_market_value += mval

      stock_rows.append({
          "item": p,
          "q": q_info,
          "shares": sh,
          "cost": cs,
          "invested": inv,
          "mval": mval,
          "pnl": pnl,
          "pnl_pct": pnl_pct,
      })

    total_pnl = total_market_value - total_invested
    total_pnl_pct = (
        (total_pnl / total_invested * 100.0) if total_invested > 0 else 0.0
    )

    st.subheader("📦 我的持仓资产盈亏总览驾驶舱 (按全时段最新成交价实时计算)")
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("💰 总持仓投入本金", f"${total_invested:,.2f}")
    mc2.metric("📈 当前总市值 (含盘前/盘后)", f"${total_market_value:,.2f}")
    mc3.metric(
        "🔥 总体实时浮动盈亏",
        f"${total_pnl:+,.2f}",
        delta=f"{total_pnl_pct:+.2f}%",
        delta_color="normal",
    )
    mc4.metric("📊 持仓股票数量", f"{len(portfolio)} 只标的")

    st.markdown("---")
    st.subheader(
        "📊 个股全时段实时价格 (明确区分：盘前 / 盘中 / 盘后 / 24h) & 盈亏状态"
    )

    for row in stock_rows:
      p = row["item"]
      q = row["q"]
      curr_sign = (
          "¥"
          if "A股" in p["market"]
          else ("HK$" if "港股" in p["market"] else "$")
      )

      with st.container(border=True):
        c1, c2, c3, c4, c5, c6 = st.columns([1.8, 1.5, 1.5, 1.2, 1.2, 1.5])

        c1.markdown(
            f"**{p['name']}** (`{p['symbol']}`)  \n"
            f"时段: **{q['session_tag']}**  \n"
            f"🕒 更新: `{q['update_time']}`"
        )

        c2.metric(
            f"当前生效价 ({q['session_tag'][:4]})",
            f"{curr_sign}{q['active_price']:,.2f}",
            delta=f"{q['active_chg_pct']:+.2f}% (较昨收)",
        )

        # 分时段详情：同时展示常规盘价格与盘前/盘后扩展价格
        if q["ext_price"] is not None:
          c3.metric(
              f"{q['ext_label']} vs 常规收盘",
              f"{curr_sign}{q['ext_price']:,.2f}",
              delta=f"{q['ext_chg_pct']:+.2f}% (常规收 {curr_sign}{q['reg_price']})",
          )
        else:
          c3.metric(
              "常规盘价格 (Regular)",
              f"{curr_sign}{q['reg_price']:,.2f}",
              delta=f"昨收 {curr_sign}{q['prev_close']:,.2f}",
              delta_color="off",
          )

        c4.metric("持有股数", f"{row['shares']:,.0f} 股")
        c5.metric(
            "买入成本",
            f"{curr_sign}{row['cost']:,.2f}",
            delta=f"本金 {curr_sign}{row['invested']:,.0f}",
            delta_color="off",
        )
        c6.metric(
            "实时浮动盈亏",
            f"{curr_sign}{row['pnl']:+,.2f}",
            delta=f"{row['pnl_pct']:+.2f}%",
            delta_color="normal",
        )

  st.markdown("---")
  st.subheader("⏱️ 7×24小时一分钟实时财经简报 & 股价异动雷达")
  flashes = fetch_7x24_live_briefs()

  if st.button("📲 一键将最新一分钟财经简报推送到手机微信", type="primary"):
    k = st.session_state.sys_config.get("serverchan_key", "")
    md_text = "### ⚡ 7×24小时一分钟实时财经快讯\n\n" + "\n\n".join(
        [f"- **`[{f['time']}]`** {f['content']}" for f in flashes[:6]]
    )
    ok, resp = send_serverchan_msg(k, "【一分钟实时财经快讯】AI盯盘参谋", md_text)
    if ok:
      st.success("✅ 简报已成功推送到您的手机微信！")
    else:
      st.error(f"❌ 推送失败: {resp}")

  for f in flashes[:8]:
    with st.container(border=True):
      st.markdown(f"**{f['category']}** | 🕒 `{f['time']}`")
      st.write(f["content"])


# ================= TAB 2: 终极目标与真实底仓校准 =================
with tab2:
  st.subheader("🎯 个股真实底仓与终极目标校准中心 (全美股 / 全港股 / 全A股)")
  st.markdown(
      "在此处新增或修改任何股票，**主页的全时段实时看板与盈亏数据会自动同步加入**！"
  )

  col_form, col_Quick = st.columns([1.35, 1])

  with col_form:
    with st.container(border=True):
      st.markdown("#### 🔍 第一步：全网搜索或选择股票")
      s_col1, s_col2 = st.columns([3, 1])
      with s_col1:
        search_kw = st.text_input(
            "输入任意股票中文名、拼音或代码（如：特斯拉、腾讯、小米、AMD、600519）",
            key="search_kw_input",
        )
      with s_col2:
        st.write("")
        st.write("")
        do_s = st.button("🔍 搜索全市场", use_container_width=True)

      default_sym, default_name, default_mkt = "TSLA", "特斯拉 (Tesla)", "美股 (USD)"
      if do_s or search_kw.strip():
        st.session_state.search_results = search_all_markets(search_kw)

      if st.session_state.search_results:
        opts = [r["display"] for r in st.session_state.search_results]
        p_idx = st.selectbox(
            f"找到 {len(opts)} 个匹配标的，点击选择：",
            range(len(opts)),
            format_func=lambda i: opts[i],
        )
        picked = st.session_state.search_results[p_idx]
        default_sym, default_name, default_mkt = (
            picked["symbol"],
            picked["name"],
            picked["market"],
        )

      c1, c2, c3 = st.columns(3)
      with c1:
        in_symbol = st.text_input("股票代码", value=default_sym)
      with c2:
        in_name = st.text_input("股票名称", value=default_name)
      with c3:
        mkt_list = ["美股 (USD)", "港股 (HKD)", "A股 (RMB)", "私募/美股 (USD)"]
        _, auto_m = normalize_stock_symbol(in_symbol, default_mkt)
        m_idx = mkt_list.index(auto_m) if auto_m in mkt_list else 0
        in_market = st.selectbox("所属市场", mkt_list, index=m_idx)

      c4, c5, c6 = st.columns(3)
      with c4:
        in_shares = st.number_input(
            "当前持有股数", min_value=0.0, value=10.0, step=1.0
        )
      with c5:
        in_cost = st.number_input(
            "当前成本价", min_value=0.0, value=120.0, step=1.0
        )
      with c6:
        in_target = st.number_input(
            "🎯 终极目标总股数", min_value=1.0, value=100.0, step=10.0
        )

      if st.button(
          "💾 保存该股票底仓与终极目标",
          type="primary",
          use_container_width=True,
      ):
        if not in_symbol.strip():
          st.error("请输入股票代码！")
        else:
          sym_c, _ = normalize_stock_symbol(in_symbol, in_market)
          d_name = in_name.strip() or sym_c
          q_now = fetch_full_session_quote(sym_c, in_cost)

          updated = False
          for item in st.session_state.portfolio:
            if item["symbol"].upper() == sym_c.upper():
              item.update({
                  "symbol": sym_c,
                  "name": d_name,
                  "market": in_market,
                  "shares": float(in_shares),
                  "cost": float(in_cost),
                  "target_shares": float(in_target),
                  "manual_price": q_now["active_price"],
              })
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
                "manual_price": q_now["active_price"],
            })
          save_json(PORTFOLIO_FILE, st.session_state.portfolio)
          add_audit_log(
              "保存底仓",
              f"{d_name}({sym_c}) 持股:{in_shares} 成本:{in_cost} 目标:{in_target}股",
          )
          st.success(f"✅ 已保存 {d_name} ({sym_c})！主页已自动加入。")
          st.rerun()

  with col_Quick:
    with st.container(border=True):
      st.markdown("#### ⚡ 快速修改已存股票")
      if len(st.session_state.portfolio) == 0:
        st.warning("暂无持仓。")
      else:
        labels = [
            f"{p['name']} ({p['symbol']})" for p in st.session_state.portfolio
        ]
        idx_sel = st.selectbox(
            "选择要修改的股票",
            range(len(labels)),
            format_func=lambda i: labels[i],
        )
        tp = st.session_state.portfolio[idx_sel]

        q_sh = st.number_input("修改当前持股数", value=float(tp["shares"]))
        q_cs = st.number_input("修改当前成本价", value=float(tp["cost"]))
        q_tg = st.number_input(
            "修改终极目标股数", value=float(tp["target_shares"])
        )

        qc1, qc2 = st.columns(2)
        with qc1:
          if st.button("🔄 保存修改", type="primary", use_container_width=True):
            st.session_state.portfolio[idx_sel].update({
                "shares": float(q_sh),
                "cost": float(q_cs),
                "target_shares": float(q_tg),
            })
            save_json(PORTFOLIO_FILE, st.session_state.portfolio)
            add_audit_log(
                "修改底仓",
                f"{tp['name']} -> 持股:{q_sh} 成本:{q_cs} 目标:{q_tg}",
            )
            st.rerun()
        with qc2:
          if st.button("🗑️ 删除该股", use_container_width=True):
            removed = st.session_state.portfolio.pop(idx_sel)
            save_json(PORTFOLIO_FILE, st.session_state.portfolio)
            add_audit_log("删除底仓", f"移除 {removed['name']}")
            st.rerun()

  st.markdown("---")
  st.markdown("#### 📋 您的个股独立底仓与终极目标总览表（最右侧可直接删除）")
  for idx, item in enumerate(st.session_state.portfolio):
    cur_sh = float(item["shares"])
    cur_cs = float(item["cost"])
    tg_sh = float(item["target_shares"])
    q_data = fetch_full_session_quote(
        item["symbol"], item.get("manual_price", cur_cs)
    )
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
          [1.6, 1.0, 1.1, 1.3, 1.3, 1.5, 0.8]
      )
      m1.markdown(
          f"**{item['name']}**  \n`{item['symbol']}` | {q_data['session_tag']}"
      )
      m2.metric("持有股数", f"{cur_sh:,.0f} 股")
      m3.metric("底仓成本", f"{curr_sign}{cur_cs:,.2f}")
      m4.metric(
          "实时最新价",
          f"{curr_sign}{q_data['active_price']:,.2f}",
          delta=f"{q_data['active_chg_pct']:+.2f}%",
      )
      m5.metric(
          "🎯 终极目标",
          f"{tg_sh:,.0f} 股",
          delta=f"还差 {remain_sh:,.0f} 股",
          delta_color="off",
      )
      with m6:
        st.write(f"**达成率：{progress_pct:.1f}%**")
        st.progress(progress_pct / 100.0)
      with m7:
        st.write("")
        if st.button(
            "🗑️ 删除",
            key=f"del_row_{idx}_{item['symbol']}",
            use_container_width=True,
        ):
          st.session_state.portfolio.pop(idx)
          save_json(PORTFOLIO_FILE, st.session_state.portfolio)
          st.rerun()


# ================= TAB 3: AI 最优买入防线与动态成本规划 =================
with tab3:
  st.subheader("🛡️ AI 最优买入防线计算 & 阶梯补仓动态成本模拟器")

  with st.expander(
      "📖 为什么我们要设立【第一、第二、第三道买入防线】？（点击查看科学逻辑简介）",
      expanded=True,
  ):
    st.markdown("""
        在股票长线投资中，散户最容易犯的错误就是**“高位一次性满仓”**或者**“大跌时因为恐惧不敢买、早早把子弹打光”**。因此我们采用机构经典的 **金字塔三道防线分批建仓法**：
        - **🟢 第一道防线（浅度回调位，通常设为现价回撤 -5% 左右，投入缺口 20% 筹码）**：
          **为什么选这里？** 这是股价日常波动或小级别技术回调的常见支撑位。用小仓位（20%）试探性吸筹，既能防止股票直接拉升踏空，又保留了 80% 的主力资金应对更深的下跌。
        - **🟡 第二道防线（黄金击球区，通常设为现价回撤 -12% 左右，投入缺口 30% 筹码）**：
          **为什么选这里？** 当市场出现阶段性恐慌或板块回调超 10% 时，往往进入高性价比的“黄金坑”。此时加大买入力度（30%），能显著把您的平均持仓成本向下拉低。
        - **🔴 第三道防线（极限铁底区，通常设为现价回撤 -20% 及以上，投入缺口 50% 重仓筹码）**：
          **为什么选这里？** 专为突发“黑天鹅”事件或非理性暴跌准备的终极底牌。当别人恐慌割肉时，您把最后也是最大的一笔资金（50%）全部打入，一举完成您的【终极目标股数】，把底仓成本摊薄到极致！
        """)

  if len(st.session_state.portfolio) == 0:
    st.info("请先添加股票。")
  else:
    names = [
        f"{p['name']} ({p['symbol']})" for p in st.session_state.portfolio
    ]
    sel_i = st.selectbox(
        "选择要推演买入防线的个股：",
        range(len(names)),
        format_func=lambda i: names[i],
    )
    stk = st.session_state.portfolio[sel_i]
    curr_sign = (
        "¥"
        if "A股" in stk["market"]
        else ("HK$" if "港股" in stk["market"] else "$")
    )

    q_stk = fetch_full_session_quote(
        stk["symbol"], stk.get("manual_price", stk["cost"])
    )
    live_p = q_stk["active_price"]
    gap_sh = max(0.0, stk["target_shares"] - stk["shares"])

    col_p1, col_p2, col_p3 = st.columns(3)
    col_p1.metric(
        f"【{stk['name']}】当前实时价 ({q_stk['session_tag']})",
        f"{curr_sign}{live_p:,.2f}",
        f"{q_stk['active_chg_pct']:+.2f}%",
    )
    col_p2.metric("您的当前底仓成本", f"{curr_sign}{stk['cost']:,.2f}")
    col_p3.metric("距离终极目标还差", f"{gap_sh:,.0f} 股")

    d1 = st.slider("第一道防线回调比例 (%)", 2.0, 15.0, 5.0, 0.5)
    d2 = st.slider("第二道防线回调比例 (%)", 5.0, 25.0, 12.0, 0.5)
    d3 = st.slider("第三道防线极限回调比例 (%)", 10.0, 40.0, 20.0, 1.0)

    p_def1 = round(live_p * (1 - d1 / 100.0), 2)
    p_def2 = round(live_p * (1 - d2 / 100.0), 2)
    p_def3 = round(live_p * (1 - d3 / 100.0), 2)

    b1 = round(gap_sh * 0.20, 1) if gap_sh > 0 else 10.0
    b2 = round(gap_sh * 0.30, 1) if gap_sh > 0 else 15.0
    b3 = round(gap_sh * 0.50, 1) if gap_sh > 0 else 25.0

    sh1 = stk["shares"] + b1
    cost1 = ((stk["shares"] * stk["cost"]) + (b1 * p_def1)) / sh1
    sh2 = sh1 + b2
    cost2 = ((sh1 * cost1) + (b2 * p_def2)) / sh2
    sh3 = sh2 + b3
    cost3 = ((sh2 * cost2) + (b3 * p_def3)) / sh3

    f1, f2, f3 = st.columns(3)
    with f1:
      with st.container(border=True):
        st.markdown(f"##### 🟢 第一防线 (-{d1}%)")
        st.metric("触发买入价", f"{curr_sign}{p_def1:,.2f}")
        st.write(f"- 建议买入：**{b1} 股**")
        st.write(f"- 补仓后摊薄成本：**{curr_sign}{cost1:,.2f}**")
    with f2:
      with st.container(border=True):
        st.markdown(f"##### 🟡 第二防线 (-{d2}%)")
        st.metric("触发买入价", f"{curr_sign}{p_def2:,.2f}")
        st.write(f"- 建议买入：**{b2} 股**")
        st.write(f"- 补仓后摊薄成本：**{curr_sign}{cost2:,.2f}**")
    with f3:
      with st.container(border=True):
        st.markdown(f"##### 🔴 第三防线 (-{d3}%)")
        st.metric("触发买入价", f"{curr_sign}{p_def3:,.2f}")
        st.write(f"- 建议抄底：**{b3} 股**")
        st.write(f"- 终极摊薄成本：**{curr_sign}{cost3:,.2f}**")


# ================= TAB 4: 审计日志 =================
with tab4:
  st.subheader("📜 底仓校准与系统操作审计日志")
  for log in st.session_state.audit_logs:
    st.markdown(f"- `{log['time']}` | **{log['action']}** — {log['detail']}")

# 自动实时刷新轮询
if auto_refresh:
  time.sleep(15)
  st.cache_data.clear()
  st.rerun()
