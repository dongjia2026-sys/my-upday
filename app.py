import json
import os
import streamlit as st
import urllib.parse
import urllib.request

# 页面基本配置
st.set_page_config(
    page_title="AssetHorizon - 个人资产与复利增长看板",
    page_icon="📊",
    layout="wide",
)

# ----------------- 数据持久化存储文件 -----------------
STOCK_FILE = "portfolio_stocks.json"
KEY_FILE = "server_key.json"


def load_stocks():
  if os.path.exists(STOCK_FILE):
    try:
      with open(STOCK_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
    except Exception:
      pass
  return [
      {"name": "特斯拉 (TSLA)", "shares": 10, "cost": 120.0, "target": 100},
      {"name": "SpaceX", "shares": 30, "cost": 140.0, "target": 150},
      {"name": "英伟达 (NVDA)", "shares": 15, "cost": 110.0, "target": 80},
  ]


def save_stocks(data):
  with open(STOCK_FILE, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=4)


def load_key():
  if os.path.exists(KEY_FILE):
    try:
      with open(KEY_FILE, "r") as f:
        return json.load(f).get("key", "")
    except Exception:
      pass
  return ""


def save_key(k):
  with open(KEY_FILE, "w", encoding="utf-8") as f:
    json.dump({"key": k}, f)


# 初始化 Session State
if "stocks" not in st.session_state:
  st.session_state.stocks = load_stocks()

# ================= 顶部导航 / 标题 =================
st.title("🚀 AssetHorizon 资产领航与复利模拟看板")
st.markdown(
    "集**真实底仓个股校准**、**财富复利增长模拟**与**Server酱微信实时推送**于一体的个人智能资产管理中心。"
)
st.markdown("---")

# ================= 模块一：真实底仓与终极目标校准看板 =================
st.header("📊 真实底仓与终极目标校准")
st.markdown(
    "您可以随时添加、管理每一支具体个股的持股数、成本价以及终极目标，系统将自动帮您计算总投入和目标达成率。"
)

with st.expander("➕ 添加 / 修改个股持仓", expanded=False):
  col1, col2 = st.columns(2)
  with col1:
    stock_name = st.text_input(
        "股票名称 / 股票代码",
        placeholder="例如: 特斯拉 (TSLA)",
        key="input_stock_name",
    )
  with col2:
    current_shares = st.number_input(
        "当前持有股数",
        min_value=0.0,
        step=1.0,
        value=10.0,
        key="input_current_shares",
    )

  col3, col4 = st.columns(2)
  with col3:
    current_cost = st.number_input(
        "当前成本价 (USD / RMB)",
        min_value=0.0,
        step=0.01,
        value=120.0,
        key="input_current_cost",
    )
  with col4:
    target_shares = st.number_input(
        "终极目标持有总股数",
        min_value=1.0,
        step=1.0,
        value=100.0,
        key="input_target_shares",
    )

  if st.button("💾 保存底仓到数据库", type="primary"):
    if stock_name.strip():
      st.session_state.stocks.append({
          "name": stock_name.strip(),
          "shares": current_shares,
          "cost": current_cost,
          "target": target_shares,
      })
      save_stocks(st.session_state.stocks)
      st.success(f"成功添加持仓：{stock_name}！")
      st.rerun()
    else:
      st.warning("请输入有效的股票名称或代码！")

st.markdown("### 📋 当前持仓明细列表")

if len(st.session_state.stocks) == 0:
  st.info("暂无持仓数据，请在上方添加。")
else:
  # 表头
  header_cols = st.columns([2, 1.5, 1.5, 2, 1.5, 1.5, 1])
  header_cols[0].markdown("**股票名称/代码**")
  header_cols[1].markdown("**当前持股**")
  header_cols[2].markdown("**平均成本**")
  header_cols[3].markdown("**当前市值/投入**")
  header_cols[4].markdown("**终极目标**")
  header_cols[5].markdown("**目标达成率**")
  header_cols[6].markdown("**操作**")

  for idx, s in enumerate(st.session_state.stocks):
    invested = s["shares"] * s["cost"]
    rate = (s["shares"] / s["target"] * 100) if s["target"] > 0 else 0

    cols = st.columns([2, 1.5, 1.5, 2, 1.5, 1.5, 1])
    cols[0].write(s["name"])
    cols[1].write(f"{s['shares']} 股")
    cols[2].write(f"${s['cost']:.2f}")
    cols[3].write(f"${invested:,.2f}")
    cols[4].write(f"{s['target']} 股")
    cols[5].markdown(f"**{rate:.1f}%**")

    if cols[6].button("🗑️", key=f"del_stock_{idx}", help="删除此项"):
      st.session_state.stocks.pop(idx)
      save_stocks(st.session_state.stocks)
      st.rerun()

st.markdown("---")

# ================= 模块二：财富复利与资产模拟计算器 =================
st.header("📈 富裕之路·复利增长与现金流模拟")
st.markdown(
    "根据您的月收入、支出、初始种子资金以及预期年化收益率，实时模拟未来的资产增长曲线。"
)

col_sim1, col_sim2 = st.columns(2)
with col_sim1:
  monthly_income = st.number_input(
      "月总收入 (万)", min_value=0.0, value=300.0, step=10.0
  )
  monthly_expense = st.number_input(
      "月总支出 (固定+变动, 万)", min_value=0.0, value=150.0, step=10.0
  )
  seed_money = st.number_input(
      "当前初始种子资金 (万)", min_value=0.0, value=2000.0, step=100.0
  )
with col_sim2:
  target_wealth = st.number_input(
      "目标总资产金额 (万)", min_value=10.0, value=10000.0, step=500.0
  )
  years = st.slider("目标投资期限 (年)", min_value=1, max_value=30, value=5)
  annual_rate = (
      st.slider("预期年化收益率 (%)", min_value=1.0, max_value=30.0, value=8.5)
      / 100.0
  )

monthly_save = max(0.0, monthly_income - monthly_expense)
st.info(
    f"💡 您的每月可支配净投资额为：**{monthly_save:,.1f} 万** （储蓄率："
    f" {(monthly_save/monthly_income*100) if monthly_income>0 else 0:.1f}%）"
)

# 复利计算核心逻辑
monthly_rate = annual_rate / 12.0
total_months = years * 12
future_wealth = seed_money
for _ in range(total_months):
  future_wealth = future_wealth * (1 + monthly_rate) + monthly_save

st.success(
    f"🎯 按照当前设定，**{years} 年后**您的预计总资产将达到："
    f" **{future_wealth:,.2f} 万**"
)

st.markdown("---")

# ================= 模块三：Server酱微信弹窗配置与网页端自检 =================
st.header("🔔 微信弹窗实时配置 (Server酱 API Key)")
st.markdown(
    "配置您的 Server酱 SendKey。点击测试后，网页端将通过后端主动向 API"
    " 发起自检请求，并在下方实时返回响应回执。"
)

current_key = load_key()
send_key_input = st.text_input(
    "Server酱 SendKey",
    value=current_key,
    type="password",
    placeholder="请输入您的 Server酱 SendKey (sctp... / SCU...)",
)

col_k1, col_k2 = st.columns(2)
with col_k1:
  if st.button("💾 保存配置到本地", type="primary"):
    if send_key_input.strip():
      save_key(send_key_input.strip())
      st.success("✅ Server酱配置已成功保存！")
    else:
      st.warning("请输入有效的 Key")

with col_k2:
  test_push = st.button("🚀 运行网页端自检并发送测试", type="secondary")

if test_push:
  key_to_test = send_key_input.strip()
  if not key_to_test:
    st.error("❌ 错误：SendKey 不能为空！")
  else:
    save_key(key_to_test)
    st.info("⏳ 正在向 Server酱 API 发送测试请求 (Self-Test)...")

    title = urllib.parse.quote("【AssetHorizon 网页端自检】系统测试弹窗")
    desp = urllib.parse.quote(
        "如果您在手机微信上看到了这条消息，说明网页端自检与 Server酱 API"
        " 链路完全跑通！"
    )
    url = f"https://sctapi.ftqq.com/{key_to_test}.send?title={title}&desp={desp}"

    try:
      req = urllib.request.Request(url, method="GET")
      with urllib.request.urlopen(req, timeout=10) as response:
        res_body = response.read().decode("utf-8")
        res_json = json.loads(res_body)

        if (
            res_json.get("code") == 0
            or res_json.get("errno") == 0
            or "pushid" in res_json
        ):
          st.success(
              "✅ 网页端自检成功！API 响应正常，请检查您的手机微信弹窗！"
          )
          st.json(res_json)
        else:
          st.error(f"❌ API 返回异常：\n{json.dumps(res_json, indent=2)}")
    except Exception as e:
      st.error(f"❌ 网络请求或服务器连接失败：{str(e)}")
