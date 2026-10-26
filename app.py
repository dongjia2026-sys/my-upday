import datetime
import json
import os
import urllib.parse
import urllib.request
import streamlit as st

# 尝试导入行情库（如未安装则自动降级为手动/基准价格模式，确保软件永不崩溃）
try:
  import yfinance as yf

  HAS_YF = True
except ImportError:
  HAS_YF = False

# ================= 1. 页面基本配置 =================
st.set_page_config(
    page_title="AI 智能股票盯盘与长线筹码规划终端",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ================= 2. 本地数据持久化与自动记忆机制 =================
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
  # 保留最近 100 条审计记录
  st.session_state.audit_logs = logs[:100]
  save_json(AUDIT_LOG_FILE, st.session_state.audit_logs)


# 默认初始底仓数据（按个股独立存储）
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
        "symbol": "SPACEX",
        "name": "SpaceX (未上市/私募)",
        "market": "私募/美股 (USD)",
        "shares": 30.0,
        "cost": 140.0,
        "target_shares": 150.0,
        "manual_price": 155.0,
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
    "black_swan_drop_pct": 5.0,  # 单日跌幅超过 5% 触发黑天鹅预警
    "defense_1_pct": 5.0,  # 第一买入防线回撤比例 (%)
    "defense_2_pct": 12.0,  # 第二买入防线回撤比例 (%)
    "defense_3_pct": 20.0,  # 第三买入防线极限回撤比例 (%)
}

# 初始化 Session State
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
          "detail": "加载个股独立底仓数据库与配置项完成",
      }],
  )


# ================= 3. Server酱 微信推送与网页端主动自检函数 =================
def send_serverchan_msg(sendkey, title, content):
  """向 Server酱 官方接口发起请求，返回 (是否成功: bool, 网页端回执详情: dict/str)"""
  if not sendkey or not sendkey.strip():
    return False, "SendKey 为空，请先在输入框中填入有效的 Server酱 SendKey！"

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
    with urllib.request.urlopen(req, timeout=10) as response:
      resp_text = response.read().decode("utf-8")
      resp_json = json.loads(resp_text)
      # Server酱 标准成功码为 code == 0 或 errno == 0
      if resp_json.get("code") == 0 or resp_json.get("errno") == 0:
        return True, resp_json
      else:
        return False, resp_json
  except Exception as e:
    return False, f"网络请求或接口异常: {str(e)}"


# ================= 4. 实时行情获取辅助函数 =================
@st.cache_data(ttl=120)
def fetch_live_price(symbol, fallback_price):
  """尝试获取美股/A股实时价格，若失败或为未上市股票（如SpaceX）则使用基准价"""
  if not HAS_YF or symbol.upper() in ["SPACEX"]:
    return fallback_price, 0.0, False
  try:
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="2d")
    if not hist.empty:
      latest_price = float(hist["Close"].iloc[-1])
      if len(hist) >= 2:
        prev_close = float(hist["Close"].iloc[-2])
        change_pct = ((latest_price - prev_close) / prev_close) * 100.0
      else:
        change_pct = 0.0
      return round(latest_price, 2), round(change_pct, 2), True
  except Exception:
    pass
  return fallback_price, 0.0, False


# ================= 5. 侧边栏：Server酱微信弹窗配置 & 防线参数 =================
with st.sidebar:
  st.header("🔔 手机微信弹窗配置 (Server酱)")
  st.caption(
      "配置会自动持久化保存，二次打开网页绝不丢失。点击测试后网页端将先进行 API"
      " 自检。"
  )

  # 从持久化配置中自动回填 SendKey
  saved_key = st.session_state.sys_config.get("serverchan_key", "")
  input_key = st.text_input(
      "填入 Server酱 SendKey",
      value=saved_key,
      placeholder="例如: SCT123456... (填入后自动记忆)",
      help="前往 sct.ftqq.com 获取 SendKey",
  )

  # 只要输入框内容变化，立即自动保存，防止刷新丢失
  if input_key != saved_key:
    st.session_state.sys_config["serverchan_key"] = input_key.strip()
    save_json(CONFIG_FILE, st.session_state.sys_config)

  col_btn1, col_btn2 = st.columns(2)
  with col_btn1:
    if st.button("💾 保存 Key", use_container_width=True):
      st.session_state.sys_config["serverchan_key"] = input_key.strip()
      save_json(CONFIG_FILE, st.session_state.sys_config)
      add_audit_log("修改配置", "更新并持久化保存了 Server酱 SendKey")
      st.success("✅ Key 已永久保存！刷新网页不会清空。")

  with col_btn2:
    test_clicked = st.button(
        "🚀 自检并测试弹窗", type="primary", use_container_width=True
    )

  # 网页端主动自检反馈区
  if test_clicked:
    current_k = input_key.strip()
    st.session_state.sys_config["serverchan_key"] = current_k
    save_json(CONFIG_FILE, st.session_state.sys_config)

    with st.spinner("⏳ 网页端正在主动连接 Server酱 接口进行自检..."):
      ok, result = send_serverchan_msg(
          current_k,
          "【网页端自检成功】AI 股票盯盘参谋测试通知",
          f"**恭喜您！**\n\n网页端已完成 Server酱 API 自检，通信链路 100% 正常。\n\n- 当前管理个股数量：**{len(st.session_state.portfolio)} 只**\n- 自检时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
      )
      if ok:
        st.success(
            "✅ **网页端自检通过：发送成功！**\n\nServer酱服务器已确认接收，现在请查看您的手机微信弹窗！"
        )
        with st.expander("查看网页端 API 自检回执详情", expanded=False):
          st.json(result)
        add_audit_log("微信推送自检", "网页端主动测试推送成功 (Code: 0)")
      else:
        st.error(
            "❌ **网页端自检未通过：发送失败！**\n\n请检查您的 SendKey"
            " 是否填写正确或是否过期。"
        )
        st.code(str(result), language="json")
        add_audit_log("微信推送自检失败", f"失败原因: {result}")

  st.markdown("---")
  st.header("⚙️ AI 防线与黑天鹅参数")
  d1 = st.slider(
      "第一买入防线回撤 (%)",
      2.0,
      15.0,
      float(st.session_state.sys_config.get("defense_1_pct", 5.0)),
      0.5,
  )
  d2 = st.slider(
      "第二买入防线回撤 (%)",
      5.0,
      25.0,
      float(st.session_state.sys_config.get("defense_2_pct", 12.0)),
      0.5,
  )
  d3 = st.slider(
      "第三买入防线极限回撤 (%)",
      10.0,
      40.0,
      float(st.session_state.sys_config.get("defense_3_pct", 20.0)),
      1.0,
  )
  bs_drop = st.slider(
      "🦢 黑天鹅单日暴跌预警阈值 (%)",
      3.0,
      15.0,
      float(st.session_state.sys_config.get("black_swan_drop_pct", 5.0)),
      0.5,
  )

  if (
      d1 != st.session_state.sys_config.get("defense_1_pct")
      or d2 != st.session_state.sys_config.get("defense_2_pct")
      or d3 != st.session_state.sys_config.get("defense_3_pct")
      or bs_drop != st.session_state.sys_config.get("black_swan_drop_pct")
  ):
    st.session_state.sys_config.update({
        "defense_1_pct": d1,
        "defense_2_pct": d2,
        "defense_3_pct": d3,
        "black_swan_drop_pct": bs_drop,
    })
    save_json(CONFIG_FILE, st.session_state.sys_config)


# ================= 6. 主界面标题与核心导航 =================
st.title("🛡️ AI 私人股票盯盘参谋 & 终极筹码规划终端")
st.markdown(
    "支持 **美股 / A股 / 私募股权** 多市场个股独立底仓校准、**终极目标股数追踪**、**AI 最优买入防线推演** 与 **突发黑天鹅微信秒级预警**。"
)

tab1, tab2, tab3, tab4 = st.tabs([
    "🎯 1. 终极目标与真实底仓校准 (按个股)",
    "🛡️ 2. AI 最优买入防线与动态成本规划",
    "🦢 3. 实时盯盘与黑天鹅风险预警",
    "📜 4. 底仓变更审计日志",
])

# ================= TAB 1: 终极目标与真实底仓校准（按个股独立管理） =================
with tab1:
  st.subheader("🎯 个股真实底仓与终极目标校准中心")
  st.info(
      "💡 **设计说明**：每一只股票（如特斯拉、SpaceX、英伟达等）的价格和逻辑完全不同。请在此处**按单只股票分别选择/录入**您的股票名称、当前持股数、当前成本价以及未来想要持有的终极目标总股数。"
  )

  col_form, col_Quick = st.columns([1.2, 1])

  with col_form:
    with st.container(border=True):
      st.markdown("#### ➕ 新增 / 修改单只股票底仓")

      preset_choice = st.selectbox(
          "快速选择常用标的（或选择【自定义输入】添加任意美股/A股）",
          [
              "自定义输入...",
              "TSLA - 特斯拉 (Tesla)",
              "SPACEX - SpaceX (未上市/私募)",
              "NVDA - 英伟达 (Nvidia)",
              "AAPL - 苹果 (Apple)",
              "600519.SS - 贵州茅台 (A股)",
              "300750.SZ - 宁德时代 (A股)",
          ],
      )

      default_sym, default_name, default_mkt = "", "", "美股 (USD)"
      if preset_choice != "自定义输入...":
        parts = preset_choice.split(" - ")
        default_sym = parts[0].strip()
        default_name = parts[1].strip()
        if ".SS" in default_sym or ".SZ" in default_sym:
          default_mkt = "A股 (RMB)"
        elif default_sym == "SPACEX":
          default_mkt = "私募/美股 (USD)"

      c1, c2, c3 = st.columns(3)
      with c1:
        in_symbol = st.text_input(
            "股票代码 (Symbol)",
            value=default_sym,
            placeholder="如 TSLA / NVDA / 600519.SS",
        )
      with c2:
        in_name = st.text_input(
            "股票名称", value=default_name, placeholder="如 特斯拉 / SpaceX"
        )
      with c3:
        in_market = st.selectbox(
            "所属市场",
            ["美股 (USD)", "A股 (RMB)", "港股 (HKD)", "私募/美股 (USD)"],
            index=[
                "美股 (USD)",
                "A股 (RMB)",
                "港股 (HKD)",
                "私募/美股 (USD)",
            ].index(default_mkt),
        )

      c4, c5, c6, c7 = st.columns(4)
      with c4:
        in_shares = st.number_input(
            "当前手里持有股数", min_value=0.0, value=10.0, step=1.0
        )
      with c5:
        in_cost = st.number_input(
            "当前持仓成本价", min_value=0.0, value=120.0, step=1.0
        )
      with c6:
        in_target = st.number_input(
            "🎯 终极目标持有总股数", min_value=1.0, value=100.0, step=10.0
        )
      with c7:
        in_price = st.number_input(
            "当前参考市价", min_value=0.01, value=150.0, step=1.0
        )

      if st.button(
          "💾 保存该股票底仓与终极目标到数据库",
          type="primary",
          use_container_width=True,
      ):
        if not in_symbol.strip() and not in_name.strip():
          st.error("❌ 请至少填写【股票代码】或【股票名称】！")
        else:
          sym_code = (
              in_symbol.strip().upper()
              if in_symbol.strip()
              else in_name.strip().upper()
          )
          disp_name = in_name.strip() if in_name.strip() else sym_code

          # 检查是否已存在该股票，存在则更新校准，不存在则追加
          updated = False
          for item in st.session_state.portfolio:
            if (
                item["symbol"].upper() == sym_code
                or item["name"] == disp_name
            ):
              item["symbol"] = sym_code
              item["name"] = disp_name
              item["market"] = in_market
              item["shares"] = float(in_shares)
              item["cost"] = float(in_cost)
              item["target_shares"] = float(in_target)
              item["manual_price"] = float(in_price)
              updated = True
              break

          if not updated:
            st.session_state.portfolio.append({
                "symbol": sym_code,
                "name": disp_name,
                "market": in_market,
                "shares": float(in_shares),
                "cost": float(in_cost),
                "target_shares": float(in_target),
                "manual_price": float(in_price),
            })

          save_json(PORTFOLIO_FILE, st.session_state.portfolio)
          action_type = "校准更新底仓" if updated else "新增股票底仓"
          add_audit_log(
              action_type,
              f"标的: {disp_name}({sym_code}) | 当前持股: {in_shares}股 | 成本: {in_cost} | 终极目标: {in_target}股",
          )
          st.success(
              f"✅ 已成功保存【{disp_name} ({sym_code})】的真实底仓与终极目标！"
          )
          st.rerun()

  with col_Quick:
    with st.container(border=True):
      st.markdown("#### ⚡ 快速校准已存股票")
      if len(st.session_state.portfolio) == 0:
        st.warning("当前数据库为空，请在左侧添加您的第一只股票。")
      else:
        stock_labels = [
            f"{p['name']} ({p['symbol']})" for p in st.session_state.portfolio
        ]
        selected_idx = st.selectbox(
            "选择要直接修改的持仓标的",
            range(len(stock_labels)),
            format_func=lambda i: stock_labels[i],
        )
        sel_stock = st.session_state.portfolio[selected_idx]

        q_shares = st.number_input(
            f"修改【{sel_stock['name']}】当前持股数",
            min_value=0.0,
            value=float(sel_stock["shares"]),
            step=1.0,
            key="q_sh",
        )
        q_cost = st.number_input(
            f"修改【{sel_stock['name']}】当前成本价",
            min_value=0.0,
            value=float(sel_stock["cost"]),
            step=1.0,
            key="q_cs",
        )
        q_target = st.number_input(
            f"修改【{sel_stock['name']}】终极目标总股数",
            min_value=1.0,
            value=float(sel_stock["target_shares"]),
            step=10.0,
            key="q_tg",
        )

        col_q1, col_q2 = st.columns(2)
        with col_q1:
          if st.button(
              "🔄 立即更新此股", use_container_width=True, type="primary"
          ):
            st.session_state.portfolio[selected_idx]["shares"] = float(
                q_shares
            )
            st.session_state.portfolio[selected_idx]["cost"] = float(q_cost)
            st.session_state.portfolio[selected_idx]["target_shares"] = float(
                q_target
            )
            save_json(PORTFOLIO_FILE, st.session_state.portfolio)
            add_audit_log(
                "快速校准底仓",
                f"{sel_stock['name']} -> 持股:{q_shares}, 成本:{q_cost}, 终极目标:{q_target}股",
            )
            st.success("✅ 更新成功！")
            st.rerun()
        with col_q2:
          if st.button("🗑️ 删除此股票", use_container_width=True):
            removed = st.session_state.portfolio.pop(selected_idx)
            save_json(PORTFOLIO_FILE, st.session_state.portfolio)
            add_audit_log(
                "删除股票底仓", f"已移除 {removed['name']} ({removed['symbol']})"
            )
            st.rerun()

  st.markdown("---")
  st.markdown("#### 📋 您的个股独立底仓与终极目标总览表")
  if len(st.session_state.portfolio) > 0:
    for idx, item in enumerate(st.session_state.portfolio):
      cur_sh = float(item["shares"])
      cur_cs = float(item["cost"])
      tg_sh = float(item["target_shares"])
      invested_val = cur_sh * cur_cs
      remain_sh = max(0.0, tg_sh - cur_sh)
      progress_pct = min(100.0, (cur_sh / tg_sh * 100.0) if tg_sh > 0 else 0.0)

      with st.container(border=True):
        m1, m2, m3, m4, m5, m6 = st.columns([2, 1.2, 1.2, 1.5, 1.5, 2])
        m1.markdown(f"**{item['name']}**  \n`{item['symbol']}` | {item['market']}")
        m2.metric("当前持有股数", f"{cur_sh:,.0f} 股")
        m3.metric("当前底仓成本", f"${cur_cs:,.2f}")
        m4.metric("已投入总本金", f"${invested_val:,.2f}")
        m5.metric(
            "🎯 终极目标股数",
            f"{tg_sh:,.0f} 股",
            delta=f"还差 {remain_sh:,.0f} 股",
            delta_color="off",
        )
        with m6:
          st.write(f"**终极目标达成率：{progress_pct:.1f}%**")
          st.progress(progress_pct / 100.0)


# ================= TAB 2: AI 最优买入防线与动态成本规划 =================
with tab2:
  st.subheader("🛡️ AI 最优买入防线计算 & 阶梯补仓动态成本模拟器")
  st.markdown(
      "针对每一只股票独立计算 **3 道下跌买入防线**，并模拟在不同防线分批建仓后，您的底仓成本将被如何摊薄、距离终极目标股数还差多少。"
  )

  if len(st.session_state.portfolio) == 0:
    st.info("请先在第一个标签页中添加您的股票。")
  else:
    stock_names = [
        f"{p['name']} ({p['symbol']})" for p in st.session_state.portfolio
    ]
    sel_i = st.selectbox(
        "👉 选择要进行【买入防线与筹码规划】的个股：",
        range(len(stock_names)),
        format_func=lambda i: stock_names[i],
    )
    stk = st.session_state.portfolio[sel_i]

    live_p, chg_pct, is_live = fetch_live_price(
        stk["symbol"], stk.get("manual_price", stk["cost"])
    )

    col_p1, col_p2, col_p3, col_p4 = st.columns(4)
    base_price = col_p1.number_input(
        f"【{stk['name']}】当前基准市价",
        min_value=0.01,
        value=float(live_p),
        step=1.0,
    )
    if base_price != stk.get("manual_price"):
      st.session_state.portfolio[sel_i]["manual_price"] = base_price
      save_json(PORTFOLIO_FILE, st.session_state.portfolio)

    col_p2.metric("您的真实底仓成本", f"${stk['cost']:,.2f}")
    col_p3.metric("当前持有 / 终极目标", f"{stk['shares']:.0f} / {stk['target_shares']:.0f} 股")
    gap_shares = max(0.0, stk["target_shares"] - stk["shares"])
    col_p4.metric("距离终极目标缺口", f"{gap_shares:,.0f} 股")

    # 计算三道防线价格（基于当前市价与底仓成本的综合锚定）
    anchor_price = min(base_price, stk["cost"]) if stk["cost"] > 0 else base_price
    p_def1 = round(base_price * (1 - d1 / 100.0), 2)
    p_def2 = round(base_price * (1 - d2 / 100.0), 2)
    p_def3 = round(base_price * (1 - d3 / 100.0), 2)

    # 将缺口股数按 20% : 30% : 50% 金字塔模型分配到三道防线
    buy_sh1 = round(gap_shares * 0.20, 1) if gap_shares > 0 else 10.0
    buy_sh2 = round(gap_shares * 0.30, 1) if gap_shares > 0 else 15.0
    buy_sh3 = round(gap_shares * 0.50, 1) if gap_shares > 0 else 25.0

    st.markdown("#### 📐 金字塔三道买入防线推演表（按终极目标缺口 2:3:5 智能分配筹码）")

    # 第一防线计算
    new_sh1 = stk["shares"] + buy_sh1
    new_cost1 = (
        ((stk["shares"] * stk["cost"]) + (buy_sh1 * p_def1)) / new_sh1
        if new_sh1 > 0
        else p_def1
    )

    # 第二防线累计计算
    new_sh2 = new_sh1 + buy_sh2
    new_cost2 = (
        ((new_sh1 * new_cost1) + (buy_sh2 * p_def2)) / new_sh2
        if new_sh2 > 0
        else p_def2
    )

    # 第三防线累计计算
    new_sh3 = new_sh2 + buy_sh3
    new_cost3 = (
        ((new_sh2 * new_cost2) + (buy_sh3 * p_def3)) / new_sh3
        if new_sh3 > 0
        else p_def3
    )

    f1, f2, f3 = st.columns(3)
    with f1:
      with st.container(border=True):
        st.markdown(f"##### 🟢 第一防线 (回调 -{d1}%)")
        st.metric("触发买入价", f"${p_def1:,.2f}")
        st.write(f"- 建议吸筹：**{buy_sh1} 股** (约 ${buy_sh1 * p_def1:,.2f})")
        st.write(f"- 补仓后总持股：**{new_sh1} 股**")
        st.write(f"- 补仓后摊薄成本：**${new_cost1:,.2f}**")
    with f2:
      with st.container(border=True):
        st.markdown(f"##### 🟡 第二防线 (黄金坑 -{d2}%)")
        st.metric("触发买入价", f"${p_def2:,.2f}")
        st.write(f"- 建议加仓：**{buy_sh2} 股** (约 ${buy_sh2 * p_def2:,.2f})")
        st.write(f"- 累计总持股：**{new_sh2} 股**")
        st.write(f"- 累计摊薄成本：**${new_cost2:,.2f}**")
    with f3:
      with st.container(border=True):
        st.markdown(f"##### 🔴 第三防线 (极限铁底 -{d3}%)")
        st.metric("触发买入价", f"${p_def3:,.2f}")
        st.write(f"- 建议重仓抄底：**{buy_sh3} 股** (约 ${buy_sh3 * p_def3:,.2f})")
        st.write(f"- 终极达成总持股：**{new_sh3} 股**")
        st.write(f"- 终极摊薄成本：**${new_cost3:,.2f}**")

    if st.button(f"📲 将【{stk['name']}】防线挂单计划推送到手机微信"):
      k = st.session_state.sys_config.get("serverchan_key", "")
      msg_title = f"【买入防线计划】{stk['name']} ({stk['symbol']}) 筹码推演"
      msg_body = (
          f"### 🎯 {stk['name']} ({stk['symbol']}) 底仓与防线简报\n"
          f"- **当前底仓**：{stk['shares']} 股 (成本 ${stk['cost']})\n"
          f"- **终极目标**：{stk['target_shares']} 股 (还差 {gap_shares} 股)\n"
          f"- **当前市价**：${base_price}\n\n"
          f"---\n"
          f"1. **第一防线 (-{d1}%)**：**${p_def1}** | 建议买入 {buy_sh1} 股 -> 摊薄成本至 ${new_cost1:.2f}\n"
          f"2. **第二防线 (-{d2}%)**：**${p_def2}** | 建议买入 {buy_sh2} 股 -> 摊薄成本至 ${new_cost2:.2f}\n"
          f"3. **第三防线 (-{d3}%)**：**${p_def3}** | 建议买入 {buy_sh3} 股 -> 摊薄成本至 ${new_cost3:.2f}\n"
      )
      ok, resp = send_serverchan_msg(k, msg_title, msg_body)
      if ok:
        st.success("✅ 网页端自检并发送成功！防线挂单计划已推送至您的手机微信。")
      else:
        st.error(f"❌ 推送失败，网页端自检回执：{resp}")


# ================= TAB 3: 实时盯盘与突发黑天鹅风险预警 =================
with tab3:
  st.subheader("🦢 双市场实时盯盘 & 突发黑天鹅风险监控雷达")
  st.markdown(
      f"当个股单日跌幅超过 **{bs_drop}%** 或跌破您的核心防线时，系统将自动亮起黑天鹅警报，支持一键发送微信紧急通知。"
  )

  if st.button("🔄 立即刷新全市场行情并扫描黑天鹅风险", type="primary"):
    st.cache_data.clear()

  alerts_triggered = []
  for p in st.session_state.portfolio:
    lp, chg, is_live_flag = fetch_live_price(
        p["symbol"], p.get("manual_price", p["cost"])
    )
    pnl_pct = ((lp - p["cost"]) / p["cost"] * 100.0) if p["cost"] > 0 else 0.0
    def1_line = round(lp * (1 - d1 / 100.0), 2)

    with st.container(border=True):
      c_a, c_b, c_c, c_d = st.columns([2, 1.5, 1.5, 2.5])
      c_a.markdown(
          f"**{p['name']} ({p['symbol']})**  \n状态:"
          f" {'🟢 实时行情' if is_live_flag else '🔵 基准估值'}"
      )
      c_b.metric("最新价格", f"${lp:,.2f}", f"{chg:+.2f}%")
      c_c.metric("底仓浮盈亏", f"{pnl_pct:+.2f}%", f"成本 ${p['cost']:,.2f}")

      if chg <= -bs_drop:
        c_d.error(
            f"🦢 **黑天鹅暴跌预警**：单日暴跌 {chg:.2f}%，已超阈值 (-{bs_drop}%)！"
        )
        alerts_triggered.append(
            f"- **{p['name']} ({p['symbol']})** 触发黑天鹅单日暴跌：{chg:.2f}% (现价 ${lp})"
        )
      elif lp <= p["cost"] * (1 - d1 / 100.0):
        c_d.warning(
            f"🛡️ **进入击球区**：现价 ${lp} 已低于成本防线 (-{d1}%)，建议关注分批吸筹！"
        )
        alerts_triggered.append(
            f"- **{p['name']} ({p['symbol']})** 跌入成本第一防线：现价 ${lp} (底仓成本 ${p['cost']})"
        )
      else:
        c_d.success("✅ 走势平稳，未触发极端黑天鹅异动。")

  if len(alerts_triggered) > 0:
    st.warning("⚠️ 检测到重点异动信号！")
    if st.button("🚨 一键将所有预警信号发送至手机微信", type="primary"):
      k = st.session_state.sys_config.get("serverchan_key", "")
      ok, resp = send_serverchan_msg(
          k,
          "🚨【黑天鹅/防线触发预警】AI 盯盘参谋紧急通知",
          "### 检测到以下个股触发关键阈值：\n\n" + "\n".join(alerts_triggered),
      )
      if ok:
        st.success("✅ 网页端自检通过，紧急预警已成功送达您的手机微信！")
      else:
        st.error(f"❌ 推送失败：{resp}")


# ================= TAB 4: 底仓变更时间戳审计日志 =================
with tab4:
  st.subheader("📜 底仓校准与系统操作审计日志")
  st.caption("每一次底仓股数修改、成本校准与微信推送测试均在此留痕，确保长线筹码管理可追溯。")

  if st.button("🧹 清空历史审计日志"):
    st.session_state.audit_logs = []
    save_json(AUDIT_LOG_FILE, [])
    st.rerun()

  for log in st.session_state.audit_logs:
    st.markdown(
        f"- `{log['time']}` | **{log['action']}** — {log['detail']}"
    )
