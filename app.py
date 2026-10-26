import json
import os
import streamlit as st
import urllib.parse
import urllib.request

# 页面基本配置
st.set_page_config(
    page_title="AssetHorizon - 资产底仓与微信提醒看板",
    page_icon="📊",
    layout="centered",
)

# ----------------- 本地 JSON 数据持久化函数 -----------------
DATA_FILE = "portfolio_data.json"


def load_data():
  if os.path.exists(DATA_FILE):
    try:
      with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
    except Exception:
      pass
  # 默认初始数据
  return [
      {"name": "特斯拉 (TSLA)", "shares": 10, "cost": 120.0, "target": 100},
      {"name": "SpaceX", "shares": 30, "cost": 140.0, "target": 150},
      {"name": "英伟达 (NVDA)", "shares": 15, "cost": 110.0, "target": 80},
  ]


def save_data(data):
  with open(DATA_FILE, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=4)


# 初始化 Session State
if "stocks" not in st.session_state:
  st.session_state.stocks = load_data()


# ----------------- 模块一：个股底仓与终极目标校准看板 -----------------
st.title("📊 真实底仓与终极目标校准看板")
st.markdown(
    "管理您的每一支个股持仓、成本价以及长期终极目标股数。所有数据将安全保存在服务器本地。"
)

with st.expander("➕ 添加 / 修改个股持仓", expanded=True):
  col1, col2 = st.columns(2)
  with col1:
    stock_name = st.text_input(
        "股票名称 / 股票代码", placeholder="例如: 特斯拉 (TSLA)"
    )
  with col2:
    current_shares = st.number_input(
        "当前持有股数", min_value=0.0, step=1.0, value=10.0
    )

  col3, col4 = st.columns(2)
  with col3:
    current_cost = st.number_input(
        "当前成本价 (USD / RMB)", min_value=0.0, step=0.01, value=120.0
    )
  with col4:
    target_shares = st.number_input(
        "终极目标持有总股数", min_value=1.0, step=1.0, value=100.0
    )

  if st.button("💾 保存底仓到数据库", type="primary"):
    if stock_name.strip():
      st.session_state.stocks.append({
          "name": stock_name.strip(),
          "shares": current_shares,
          "cost": current_cost,
          "target": target_shares,
      })
      save_data(st.session_state.stocks)
      st.success(f"成功添加持仓：{stock_name}！")
      st.rerun()
    else:
      st.warning("请输入有效的股票名称或代码！")

st.markdown("### 📋 当前持仓明细列表")

if len(st.session_state.stocks) == 0:
  st.info("暂无持仓数据，请在上方添加。")
else:
  # 展示表格与删除功能
  for idx, s in enumerate(st.session_state.stocks):
    invested = s["shares"] * s["cost"]
    rate = (s["shares"] / s["target"] * 100) if s["target"] > 0 else 0

    cols = st.columns([2, 1.5, 1.5, 2, 1.5, 1.5, 1])
    cols[0].markdown(f"**{s['name']}**")
    cols[1].text(f"{s['shares']} 股")
    cols[2].text(f"${s['cost']:.2f}")
    cols[3].text(f"${invested:.2f}")
    cols[4].text(f"{s['target']} 股")
    cols[5].markdown(f"**{rate:.1f}%**")

    if cols[6].button("🗑️", key=f"del_{idx}", help="删除此项"):
      st.session_state.stocks.pop(idx)
      save_data(st.session_state.stocks)
      st.rerun()

st.markdown("---")

# ----------------- 模块二：Server酱微信弹窗配置与网页端自检 -----------------
st.title("🔔 微信弹窗配置 (Server酱 API Key)")
st.markdown(
    "配置您的 Server酱 SendKey。点击测试后，网页端将直接通过 Python 后端进行"
    " API 自检并返回回执结果。"
)

# 简单的 Key 存储文件
KEY_FILE = "server_key.json"


def load_key():
  if os.path.exists(KEY_FILE):
    try:
      with open(KEY_FILE, "r") as f:
        return json.load(f).get("key", "")
    except Exception:
      pass
  return ""


def save_key(k):
  with open(KEY_FILE, "w") as f:
    json.dump({"key": k}, f)


current_key = load_key()
send_key_input = st.text_input(
    "Server酱 SendKey",
    value=current_key,
    type="password",
    placeholder="请输入您的 Server酱 SendKey (sctp... / SCU...)",
)

col_s1, col_s2 = st.columns(2)
with col_s1:
  if st.button("💾 保存配置"):
    if send_key_input.strip():
      save_key(send_key_input.strip())
      st.success("✅ Server酱配置已成功保存！")
    else:
      st.warning("请输入有效的 Key")

with col_s2:
  test_push = st.button(
      "🚀 运行网页端自检并发送测试", type="secondary"
  )

if test_push:
  key_to_test = send_key_input.strip()
  if not key_to_test:
    st.error("❌ 错误：SendKey 不能为空！")
  else:
    save_key(key_to_test)
    st.info("⏳ 正在通过 Python 后端向 Server酱 API 发送测试请求...")

    title = urllib.parse.quote("【Streamlit后端自检】资产管理系统测试弹窗")
    desp = urllib.parse.quote(
        "如果您在手机微信上看到了这条消息，说明 Python 后端与 Server酱 API"
        " 链路完全跑通！"
    )
    url = f"https://sctapi.ftqq.com/{key_to_test}.send?title={title}&desp={desp}"

    try:
      req = urllib.request.Request(url, method="GET")
      with urllib.request.urlopen(req, timeout=10) as response:
        res_body = response.read().decode("utf-8")
        res_json = json.loads(res_body)

        # 检查 Server酱 返回码
        if (
            res_json.get("code") == 0
            or res_json.get("errno") == 0
            or "pushid" in res_json
        ):
          st.success("✅ 网页端自检成功！API 响应正常，请检查手机微信！")
          st.json(res_json)
        else:
          st.error(f"❌ API 返回异常：\n{json.dumps(res_json, indent=2)}")
    except Exception as e:
      st.error(f"❌ 网络请求或服务器连接失败：{str(e)}")
